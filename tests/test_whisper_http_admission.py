"""Actual handler wire tests; native fixture repeats them on disposable TCP."""
import http.client
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch
import wave

import requests

from fruth_core.transports import whisper_transcribe
from scripts import mlx_whisper_server as adapter


NATIVE_HTTP = False


class MemorySocket:
    def __init__(self, request):
        self.request = request
        self.reply = bytearray()

    def makefile(self, mode, *args):
        return io.BytesIO(self.request)

    def sendall(self, data):
        self.reply.extend(data)


class WhisperAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='whisper-http-')
        self.addCleanup(self.temporary.cleanup)
        self.audio = Path(self.temporary.name) / 'input.wav'
        with wave.open(str(self.audio), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b'\x01\x00' * 80)
        self.original_bytes = self.audio.read_bytes()
        self.path_accesses = []
        self.provider_calls = []
        self.provider_failure = None

        def supplied_path(value):
            self.path_accesses.append(value)
            return Path(value)

        def transcribe(path, **options):
            self.provider_calls.append((path, options, Path(path).read_bytes()))
            if self.provider_failure:
                raise RuntimeError(self.provider_failure)
            return {'text': 'fixture transcript', 'segments': [{'text': 'fixture transcript'}], 'language': 'en'}

        self.path_patch = patch.object(adapter, 'Path', side_effect=supplied_path)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.provider_patch = patch.dict(sys.modules, {'mlx_whisper': types.SimpleNamespace(transcribe=transcribe)})
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        self.handler = adapter.build_handler('fixture-model')
        self.log_patch = patch.object(self.handler, 'log_message', lambda *args: None)
        self.log_patch.start()
        self.addCleanup(self.log_patch.stop)
        if NATIVE_HTTP:
            self.server = adapter.ThreadingHTTPServer(('127.0.0.1', 0), self.handler)
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
            self.thread.start()
            self.addCleanup(self.stop_server)
        else:
            self.server = types.SimpleNamespace(server_address=('127.0.0.1', 43127))
        self.port = self.server.server_address[1]

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def exchange(self, *, headers=None, body=None, method='POST', path='/v1/audio/transcriptions'):
        if body is None:
            body = json.dumps({'audio_path': str(self.audio)}).encode()
        if headers is None:
            headers = self.headers(body)
        raw = f'{method} {path} HTTP/1.1\r\n'.encode()
        raw += b''.join(f'{name}: {value}\r\n'.encode() for name, value in headers)
        raw += b'\r\n' + body
        if NATIVE_HTTP:
            connection = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            try:
                connection.sendall(raw)
                # Also lets truncated Content-Length cases return a response.
                connection.shutdown(socket.SHUT_WR)
                response = http.client.HTTPResponse(connection, method=method)
                response.begin()
                data = response.read()
                result = response.status, dict(response.getheaders()), data
                response.close()
                return result
            finally:
                connection.close()
        connection = MemorySocket(raw)
        self.handler(connection, ('127.0.0.1', 12345), self.server)
        response = http.client.HTTPResponse(MemorySocket(bytes(connection.reply)), method=method)
        response.begin()
        return response.status, dict(response.getheaders()), response.read()

    def headers(self, body=None, **overrides):
        if body is None:
            body = json.dumps({'audio_path': str(self.audio)}).encode()
        result = {'Host': f'127.0.0.1:{self.port}', 'X-Fruth-Action': '1',
                  'Content-Type': 'application/json', 'Content-Length': str(len(body))}
        result.update(overrides)
        return [(name, value) for name, value in result.items() if value is not None]

    def rejected(self, expected_status, expected_code, **request):
        accesses, calls = len(self.path_accesses), len(self.provider_calls)
        status, headers, body = self.exchange(**request)
        self.assertEqual(status, expected_status, body)
        if request.get('method') != 'HEAD':
            data = json.loads(body)
            self.assertIsInstance(data['error'], str)
            self.assertEqual(data['error_code'], expected_code)
        self.assertFalse(any(name.lower().startswith('access-control-') for name in headers))
        self.assertEqual(len(self.path_accesses), accesses, 'Rejected request accessed supplied path')
        self.assertEqual(len(self.provider_calls), calls, 'Rejected request dispatched provider')
        self.assertEqual(self.audio.read_bytes(), self.original_bytes)
        self.assertEqual(list(self.audio.parent.iterdir()), [self.audio])

    def test_original_foreign_plain_request_is_rejected(self):
        self.rejected(400, 'HTTP_HOST_NOT_ALLOWED', headers=self.headers(**{
            'Host': 'foreign.invalid', 'Origin': 'http://foreign.invalid',
            'Content-Type': 'text/plain', 'X-Fruth-Action': None}))

    def test_foreign_missing_malformed_and_duplicate_hosts(self):
        for host in (None, '', 'foreign.invalid', f'foreign.invalid:{self.port}',
                     '127.0.0.1', f'localhost:{self.port + 1}', f'localhost.:{self.port}',
                     f'127.0.0.1:{self.port}@foreign.invalid', f'localhost:{self.port},foreign.invalid',
                     f'0.0.0.0:{self.port}'):
            with self.subTest(host=host):
                self.rejected(400, 'HTTP_HOST_NOT_ALLOWED', headers=self.headers(**{'Host': host}))
        self.rejected(400, 'HTTP_HOST_NOT_ALLOWED', headers=self.headers() + [('Host', f'localhost:{self.port}')])
        self.rejected(400, 'HTTP_HOST_NOT_ALLOWED', headers=self.headers(**{
            'Host': 'foreign.invalid', 'X-Forwarded-Host': f'localhost:{self.port}',
            'Forwarded': f'host=localhost:{self.port}'}))

    def test_foreign_empty_opaque_malformed_and_duplicate_origins(self):
        for origin in ('http://foreign.invalid', 'null', '', f'https://localhost:{self.port}',
                       f'http://localhost:{self.port + 1}', f'http://localhost:{self.port}/',
                       f'http://user@localhost:{self.port}', f'http://localhost:{self.port}?x=1',
                       f'http://LOCALHOST:{self.port}'):
            with self.subTest(origin=origin):
                self.rejected(403, 'HTTP_ORIGIN_NOT_ALLOWED', headers=self.headers(**{'Origin': origin}))
        self.rejected(403, 'HTTP_ORIGIN_NOT_ALLOWED', headers=self.headers() + [
            ('Origin', f'http://localhost:{self.port}'), ('Origin', f'http://localhost:{self.port}')])

    def test_action_required_with_and_without_origin(self):
        for origin in (None, f'http://localhost:{self.port}'):
            for marker in (None, '', '0', 'true', '1, 1', '1 '):
                with self.subTest(origin=origin, marker=marker):
                    self.rejected(403, 'HTTP_ACTION_REQUIRED', headers=self.headers(**{
                        'Origin': origin, 'X-Fruth-Action': marker}))
        self.rejected(403, 'HTTP_ACTION_REQUIRED', headers=self.headers() + [('X-Fruth-Action', '1')])
        self.rejected(403, 'HTTP_ACTION_REQUIRED', path='/api/transcribe?X-Fruth-Action=1',
                      headers=self.headers(**{'X-Fruth-Action': None}))

    def test_json_media_type_required(self):
        for media_type in (None, '', 'text/plain', 'text/plain; charset=UTF-8',
                           'application/x-www-form-urlencoded', 'multipart/form-data; boundary=fixture',
                           'application/octet-stream', 'application/jsonp', 'application/problem+json'):
            with self.subTest(media_type=media_type):
                self.rejected(415, 'WHISPER_UNSUPPORTED_MEDIA_TYPE',
                              headers=self.headers(**{'Content-Type': media_type}))
        self.rejected(415, 'WHISPER_UNSUPPORTED_MEDIA_TYPE', headers=self.headers() + [('Content-Type', 'application/json')])

    def test_malformed_and_invalidly_encoded_json(self):
        for body in (b'', b' ', b'{', b'{"audio_path":}', b'{"audio_path":"\xff"}',
                     b'{"audio_path":"x", "extra": NaN}', b'{"extra": Infinity}', b'[' * 2000 + b']' * 2000):
            with self.subTest(body=body):
                self.rejected(400, 'WHISPER_INVALID_JSON', body=body, headers=self.headers(body))

    def test_invalid_body_framing(self):
        for length in (None, '', 'invalid', '-1', '1.5', '+10', '0', '999999', str(2**100)):
            with self.subTest(length=length):
                self.rejected(400, 'WHISPER_INVALID_JSON', headers=self.headers(**{'Content-Length': length}))
        self.rejected(400, 'WHISPER_INVALID_JSON', headers=self.headers() + [('Content-Length', '1')])
        self.rejected(400, 'WHISPER_INVALID_JSON', headers=self.headers(**{'Transfer-Encoding': 'chunked'}))

    def test_non_object_payloads(self):
        for payload in (None, [], ['audio.wav'], 'audio.wav', 1, True):
            with self.subTest(payload=payload):
                body = json.dumps(payload).encode()
                self.rejected(400, 'WHISPER_OBJECT_REQUIRED', body=body, headers=self.headers(body))

    def test_invalid_required_audio_path(self):
        for payload in ({}, *({'audio_path': value} for value in (None, '', '   ', 1, True, [], {}, 'bad\x00path', '\ud800'))):
            with self.subTest(payload=payload):
                body = json.dumps(payload).encode()
                self.rejected(400, 'WHISPER_INVALID_AUDIO_PATH', body=body, headers=self.headers(body))

    def test_preflight_grants_no_submission_permission(self):
        for origin, status, code in (('http://foreign.invalid', 403, 'HTTP_ORIGIN_NOT_ALLOWED'),
                                     (f'http://localhost:{self.port}', 405, 'HTTP_METHOD_NOT_ALLOWED')):
            with self.subTest(origin=origin):
                self.rejected(status, code, method='OPTIONS', headers=self.headers(**{
                    'Origin': origin, 'X-Fruth-Action': None,
                    'Access-Control-Request-Method': 'POST',
                    'Access-Control-Request-Headers': 'content-type,x-fruth-action'}))

    def test_unsupported_methods_do_not_dispatch(self):
        for method in ('PUT', 'PATCH', 'DELETE', 'TRACE', 'CONNECT', 'HEAD'):
            with self.subTest(method=method):
                self.rejected(405, 'HTTP_METHOD_NOT_ALLOWED', method=method)

    def test_aliases_host_variants_and_json_parameters(self):
        for path in ('/v1/audio/transcriptions', '/api/transcribe', '/v1/audio/transcriptions/', '/api/transcribe/'):
            for host in (f'127.0.0.1:{self.port}', f'localhost:{self.port}', f'[::1]:{self.port}', f'LOCALHOST:{self.port}'):
                for content_type in ('application/json', 'application/json; charset=utf-8', 'Application/JSON; charset="UTF-8"'):
                    with self.subTest(path=path, host=host, content_type=content_type):
                        before = len(self.provider_calls)
                        status, headers, body = self.exchange(path=path, headers=self.headers(**{
                            'Host': host, 'Origin': f'http://{host.lower()}', 'Content-Type': content_type}))
                        self.assertEqual(status, 200, body)
                        self.assertEqual(len(self.provider_calls), before + 1)
                        self.assertEqual(json.loads(body)['text'], 'fixture transcript')
                        self.assertFalse(any(name.lower().startswith('access-control-') for name in headers))

    def client(self):
        if NATIVE_HTTP:
            client = requests.Session()
            client.trust_env = False
            self.addCleanup(client.close)
            return client
        def post(url, *, json: dict, headers, timeout):
            self.assertEqual(url, f'http://127.0.0.1:{self.port}/v1/audio/transcriptions')
            self.assertEqual(timeout, 600)
            self.assertEqual(headers, {'X-Fruth-Action': '1'})
            body = __import__('json').dumps(json).encode()
            status, _, raw = self.exchange(body=body, headers=self.headers(body, **headers))
            response = requests.Response()
            response.status_code = status
            response._content = raw
            return response
        return types.SimpleNamespace(post=post)

    def test_production_client_preserves_dispatch_and_response(self):
        result = whisper_transcribe(self.port, self.audio, self.client(), task='translate', language='de')
        self.assertEqual(result, {'text': 'fixture transcript', 'segments': [{'text': 'fixture transcript'}],
                                  'language': 'en', 'model_path': 'fixture-model'})
        self.assertEqual(self.path_accesses, [str(self.audio)])
        self.assertEqual(self.provider_calls, [(str(self.audio), {
            'path_or_hf_repo': 'fixture-model', 'verbose': False, 'language': 'de',
            'task': 'translate', 'word_timestamps': False}, self.original_bytes)])

    def test_optional_fields_and_defaults_remain_compatible(self):
        payload = {'audio_path': f' {self.audio} ', 'language': ' de ', 'task': 'translate', 'word_timestamps': True}
        body = json.dumps(payload).encode()
        self.assertEqual(self.exchange(body=body, headers=self.headers(body))[0], 200)
        self.assertEqual(self.provider_calls[0][1]['word_timestamps'], True)
        self.assertEqual(self.provider_calls[0][1]['language'], 'de')
        self.assertEqual(self.exchange()[0], 200)
        self.assertEqual(self.provider_calls[1][1]['task'], 'transcribe')
        self.assertIsNone(self.provider_calls[1][1]['language'])

    def test_provider_failure_is_500_and_client_raises(self):
        self.provider_failure = 'fixture provider failure'
        status, _, body = self.exchange()
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(body), {'error': 'fixture provider failure'})
        self.assertEqual(len(self.provider_calls), 1)
        with self.assertRaises(requests.HTTPError):
            whisper_transcribe(self.port, self.audio, self.client())
        self.assertEqual(len(self.provider_calls), 2)

    def test_missing_file_is_explicit_error_without_provider(self):
        body = json.dumps({'audio_path': str(self.audio.parent / 'missing.wav')}).encode()
        status, _, raw = self.exchange(body=body, headers=self.headers(body))
        self.assertEqual(status, 400)
        self.assertIn('Audio file was not found', json.loads(raw)['error'])
        self.assertEqual(len(self.path_accesses), 1)
        self.assertEqual(self.provider_calls, [])

    def test_health_remains_passive_but_admits_host_and_origin(self):
        status, _, body = self.exchange(method='GET', path='/healthz', headers=self.headers(**{'X-Fruth-Action': None}))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['model_path'], 'fixture-model')
        self.assertEqual(self.path_accesses, [])
        self.assertEqual(self.provider_calls, [])
        self.rejected(400, 'HTTP_HOST_NOT_ALLOWED', method='GET', path='/healthz', headers=self.headers(**{'Host': 'foreign.invalid'}))
        self.rejected(403, 'HTTP_ORIGIN_NOT_ALLOWED', method='GET', path='/healthz', headers=self.headers(**{'Origin': 'null'}))

    def test_filesystem_error_is_reported_without_provider(self):
        self.path_patch.stop()
        with patch.object(adapter, 'Path') as path:
            path.return_value.exists.side_effect = OSError('fixture path error')
            status, _, body = self.exchange()
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)['error_code'], 'WHISPER_INVALID_AUDIO_PATH')
        self.assertEqual(self.provider_calls, [])


class WhisperListenerConfigurationTests(unittest.TestCase):
    def test_cli_preserves_default_and_configured_bind_and_port(self):
        for extra, expected_host in (([], '127.0.0.1'), (['--host', 'localhost'], 'localhost'),
                                     (['--host', '0.0.0.0'], '0.0.0.0')):
            with self.subTest(host=expected_host), patch.object(sys, 'argv', [
                'mlx_whisper_server.py', '--model-path', 'fixture-model', '--port', '43212', *extra
            ]), patch.object(adapter, 'build_handler') as build, patch.object(adapter, 'ThreadingHTTPServer') as server:
                adapter.main()
                build.assert_called_once_with('fixture-model', host=expected_host)
                server.assert_called_once_with((expected_host, 43212), build.return_value)
                server.return_value.serve_forever.assert_called_once_with()

    def test_explicit_bind_name_address_and_actual_port(self):
        self.assertEqual(adapter._allowed_authorities('transcriber.local', ('192.0.2.7', 43210)), {
            'transcriber.local:43210', '192.0.2.7:43210',
            '127.0.0.1:43210', 'localhost:43210', '[::1]:43210'})

    def test_wildcard_bind_does_not_authorize_wildcard_hosts(self):
        for address in ('0.0.0.0', '::', ''):
            self.assertEqual(adapter._allowed_authorities(address, (address, 43211)), {
                '127.0.0.1:43211', 'localhost:43211', '[::1]:43211'})

    def test_http_default_port_accepts_explicit_and_implicit_authority(self):
        authorities = adapter._allowed_authorities('127.0.0.1', ('127.0.0.1', 80))
        self.assertEqual(authorities, {'127.0.0.1', 'localhost', '[::1]', '127.0.0.1:80', 'localhost:80', '[::1]:80'})
