"""Authorized saved-artifact reads for semantic review evidence.

A supplied path resolver defines the read boundary. This adapter retains exact
file identity and bounded excerpts; it does not adjudicate review or fulfillment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import hashlib
from pathlib import Path
from typing import Any, Optional
from fruth_core.transports import TEXT_ARTIFACT_EXTENSIONS


@dataclass(frozen=True)
class SemanticArtifactReader:
    resolve_semantic_review_artifact_path: Optional[Callable[[str], Optional[Path]]]

    def _resolved_semantic_review_artifact_path(
        self,
        path_value: Any,
    ) -> Optional[Path]:
        raw_path = str(path_value or '').strip()
        resolver = self.resolve_semantic_review_artifact_path
        if not raw_path or not callable(resolver):
            return None
        try:
            resolved = resolver(raw_path)
            if resolved is None:
                return None
            path = Path(resolved).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        return path if path.is_file() else None

    def _global_semantic_text_artifact_excerpt(
        self,
        path_value: Any,
        *,
        byte_limit: int,
    ) -> dict[str, Any]:
        raw_path = str(path_value or '').strip()
        if not raw_path or byte_limit <= 0:
            return {}
        path = self._resolved_semantic_review_artifact_path(raw_path)
        if path is None:
            return {}
        if path.suffix.lower().lstrip('.') not in TEXT_ARTIFACT_EXTENSIONS:
            return {}
        try:
            size_bytes = path.stat().st_size
            if not path.is_file():
                return {}
            excerpt_marker = b'\n[... middle omitted ...]\n'
            excerpt_bytes = (
                byte_limit
                if size_bytes <= byte_limit
                else max(0, byte_limit - len(excerpt_marker))
            )
            head_size = excerpt_bytes if size_bytes <= byte_limit else (excerpt_bytes * 3) // 4
            tail_size = 0 if size_bytes <= byte_limit else excerpt_bytes - head_size
            digest = hashlib.sha256()
            head = bytearray()
            tail = bytearray()
            actual_size_bytes = 0
            with path.open('rb') as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    actual_size_bytes += len(chunk)
                    if len(head) < head_size:
                        head.extend(chunk[: head_size - len(head)])
                    if tail_size:
                        tail.extend(chunk)
                        if len(tail) > tail_size:
                            del tail[:-tail_size]
            truncated = actual_size_bytes > byte_limit
            if truncated and tail_size:
                content = bytes(head) + excerpt_marker + bytes(tail)
                mode = 'head_tail'
            else:
                content = bytes(head[:byte_limit])
                mode = 'head' if truncated else 'full'
        except (OSError, RuntimeError, ValueError):
            return {}
        return {
            'content_excerpt': content.decode('utf-8', errors='replace'),
            'content_excerpt_mode': mode,
            'content_excerpt_truncated': truncated,
            'content_source_size_bytes': actual_size_bytes,
            'current_content_sha256': digest.hexdigest(),
        }

    def _global_semantic_artifact_file_identity(
        self,
        path_value: Any,
    ) -> dict[str, Any]:
        raw_path = str(path_value or '').strip()
        if not raw_path:
            return {}
        path = self._resolved_semantic_review_artifact_path(raw_path)
        if path is None:
            return {'current_file_status': 'outside_allowed_artifact_roots'}
        try:
            if not path.is_file():
                return {'current_file_status': 'missing'}
            digest = hashlib.sha256()
            size_bytes = 0
            with path.open('rb') as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size_bytes += len(chunk)
        except (OSError, RuntimeError, ValueError):
            return {'current_file_status': 'unreadable'}
        return {
            'current_file_status': 'available',
            'current_file_size_bytes': size_bytes,
            'current_file_sha256': digest.hexdigest(),
        }

