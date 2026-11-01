#!/usr/bin/env python3
"""Minimal HTTP server for MLX Whisper transcription."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# The launcher executes this file directly with the MLX environment's Python.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fruth_core.http_contract import HTTP_ACTION_HEADER, HTTP_ACTION_VALUE


def _allowed_authorities(bind_host: str, server_address: tuple) -> set[str]:
    """Use only listener configuration, never Host/Origin/forwarding headers."""
    hosts = {"127.0.0.1", "localhost", "::1", bind_host, server_address[0]}
    hosts -= {"", "0.0.0.0", "::"}
    port = server_address[1]
    names = {f"[{host.lower()}]" if ":" in host else host.lower() for host in hosts}
    authorities = {f"{name}:{port}" for name in names}
    if port == 80:
        authorities.update(names)
    return authorities


def _admission_error(handler: BaseHTTPRequestHandler, bind_host: str, *, action: bool):
    authorities = _allowed_authorities(bind_host, handler.server.server_address)
    hosts = handler.headers.get_all("Host", [])
    if len(hosts) != 1 or hosts[0].lower() not in authorities:
        return "Host is not permitted for the Whisper adapter.", "HTTP_HOST_NOT_ALLOWED", 400
    origins = handler.headers.get_all("Origin", [])
    if origins and (len(origins) != 1 or origins[0] not in {f"http://{authority}" for authority in authorities}):
        return "Origin is not permitted for the Whisper adapter.", "HTTP_ORIGIN_NOT_ALLOWED", 403
    if action and handler.headers.get_all(HTTP_ACTION_HEADER, []) != [HTTP_ACTION_VALUE]:
        return (
            f"An intentional API action requires {HTTP_ACTION_HEADER}: {HTTP_ACTION_VALUE}.",
            "HTTP_ACTION_REQUIRED", 403,
        )
    return None


def _json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _load_request_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    def invalid_constant(value: str):
        raise ValueError(f"Invalid JSON constant: {value}")

    lengths = handler.headers.get_all("Content-Length", [])
    if (handler.headers.get_all("Transfer-Encoding") or len(lengths) != 1
            or not lengths[0].isascii() or not lengths[0].isdigit()):
        raise ValueError("A single positive Content-Length and no Transfer-Encoding are required.")
    length = int(lengths[0])
    if length <= 0:
        raise ValueError("A non-empty JSON body is required.")
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise ValueError("Incomplete JSON body.")
    return json.loads(raw.decode("utf-8"), parse_constant=invalid_constant)


def build_handler(model_path: str, *, host: str = "127.0.0.1"):
    class WhisperHandler(BaseHTTPRequestHandler):
        server_version = "mlx-whisper-server/0.1"

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            print(f"[mlx-whisper] {self.address_string()} - {format % args}")

        def _admit(self, *, action: bool = False) -> bool:
            error = _admission_error(self, host, action=action)
            if error is None:
                return True
            message, code, status = error
            _json_response(self, {"error": message, "error_code": code}, status=status)
            return False

        def _unsupported_method(self) -> None:
            if self._admit():
                _json_response(self, {"error": "Method not allowed", "error_code": "HTTP_METHOD_NOT_ALLOWED"}, status=405)

        do_OPTIONS = _unsupported_method
        do_HEAD = _unsupported_method
        do_PUT = _unsupported_method
        do_PATCH = _unsupported_method
        do_DELETE = _unsupported_method
        do_TRACE = _unsupported_method
        do_CONNECT = _unsupported_method

        def do_GET(self) -> None:  # noqa: N802
            if not self._admit():
                return
            if self.path.rstrip("/") == "/healthz":
                _json_response(
                    self,
                    {
                        "ok": True,
                        "capability": "speech_to_text",
                        "backend": "mlx",
                        "model_path": model_path,
                    },
                    status=200,
                )
                return
            _json_response(self, {"error": "Not found"}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            if not self._admit(action=True):
                return
            if self.path.rstrip("/") not in {"/v1/audio/transcriptions", "/api/transcribe"}:
                _json_response(self, {"error": "Not found"}, status=404)
                return

            media_types = self.headers.get_all("Content-Type", [])
            if (len(media_types) != 1
                    or media_types[0].split(";", 1)[0].strip().lower() != "application/json"):
                _json_response(self, {"error": "Whisper requires application/json.", "error_code": "WHISPER_UNSUPPORTED_MEDIA_TYPE"}, status=415)
                return

            try:
                payload = _load_request_json(self)
            except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
                _json_response(self, {"error": f"Invalid JSON body: {exc}", "error_code": "WHISPER_INVALID_JSON"}, status=400)
                return

            if not isinstance(payload, dict):
                _json_response(self, {"error": "Whisper requires a JSON object.", "error_code": "WHISPER_OBJECT_REQUIRED"}, status=400)
                return
            audio_path = payload.get("audio_path")
            if not isinstance(audio_path, str) or not audio_path.strip() or "\x00" in audio_path:
                _json_response(self, {"error": "Parameter 'audio_path' must be a non-empty path string.", "error_code": "WHISPER_INVALID_AUDIO_PATH"}, status=400)
                return
            audio_path = audio_path.strip()
            try:
                audio_path.encode("utf-8")
            except UnicodeError:
                _json_response(self, {"error": "Parameter 'audio_path' must be valid UTF-8.", "error_code": "WHISPER_INVALID_AUDIO_PATH"}, status=400)
                return

            try:
                exists = Path(audio_path).exists()
            except (OSError, ValueError):
                _json_response(self, {"error": "Parameter 'audio_path' is not a usable filesystem path.", "error_code": "WHISPER_INVALID_AUDIO_PATH"}, status=400)
                return
            if not exists:
                _json_response(self, {"error": f"Audio file was not found: {audio_path}"}, status=400)
                return

            language = payload.get("language")
            if isinstance(language, str):
                language = language.strip() or None
            else:
                language = None

            task = payload.get("task")
            if not isinstance(task, str) or not task.strip():
                task = "transcribe"

            word_timestamps = bool(payload.get("word_timestamps", False))

            try:
                from mlx_whisper import transcribe as whisper_transcribe

                result = whisper_transcribe(
                    audio_path,
                    path_or_hf_repo=model_path,
                    verbose=False,
                    language=language,
                    task=task,
                    word_timestamps=word_timestamps,
                )
            except Exception as exc:  # noqa: BLE001
                _json_response(self, {"error": str(exc)}, status=500)
                return

            _json_response(
                self,
                {
                    "text": result.get("text", ""),
                    "segments": result.get("segments", []),
                    "language": result.get("language"),
                    "model_path": model_path,
                },
                status=200,
            )

    return WhisperHandler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    handler_cls = build_handler(args.model_path, host=args.host)
    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    print(
        f"[mlx-whisper] serving on http://{args.host}:{args.port} "
        f"with model path: {args.model_path}"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
