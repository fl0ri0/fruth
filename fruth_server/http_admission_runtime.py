"""Admission for Fruth's browser HTTP channel, before route effects."""

from __future__ import annotations

from urllib.parse import urlsplit

from flask import current_app, jsonify, request
from werkzeug.exceptions import BadRequest

from fruth_core.file_inputs import parse_bool
from fruth_core.http_contract import HTTP_ACTION_HEADER, HTTP_ACTION_VALUE


HTTP_ALLOWED_ORIGINS_CONFIG = 'FRUTH_HTTP_ALLOWED_ORIGINS'
_ASSET_READ_ENDPOINTS = {
    'api_preview_saved_artifact_asset',
    'api_view_saved_artifact_asset',
}
_ACTION_GET_ENDPOINTS = {'api_preview_saved_artifact'}
_CORS_HEADERS = (
    'Content-Type, X-Fruth-Action, Authorization, '
    'X-Fruth-Graph-Rebase-Operator, X-Fruth-Graph-Rebase-Operator-Token'
)


def _trusted_origins() -> tuple[str, ...]:
    """Fail closed for malformed server configuration, never reflect request values."""
    configured = current_app.config.get(HTTP_ALLOWED_ORIGINS_CONFIG, ())
    if not isinstance(configured, (tuple, list)):
        return ()
    result = []
    for origin in configured:
        if not isinstance(origin, str):
            continue
        try:
            parsed = urlsplit(origin)
            _ = parsed.port
        except ValueError:
            continue
        if (
            parsed.scheme in {'http', 'https'} and parsed.hostname
            and parsed.username is None and parsed.password is None
            and not parsed.path and not parsed.query and not parsed.fragment
            and origin == f'{parsed.scheme}://{parsed.netloc}'
            and not any(char.isspace() for char in origin)
        ):
            result.append(origin)
    return tuple(result)


def _is_api_request() -> bool:
    return request.path.startswith(('/api/', '/v1/'))


def _is_asset_read() -> bool:
    return request.method in {'GET', 'HEAD'} and request.endpoint in _ASSET_READ_ENDPOINTS


def _error(message: str, code: str, status: int):
    return jsonify({'error': message, 'error_code': code}), status


def admit_api_request():
    if not _is_api_request():
        return None
    origins = _trusted_origins()
    authorities = {urlsplit(origin).netloc.lower() for origin in origins}
    # Read the direct Host, even when a deployment supplies forwarding headers.
    # Authorities include the configured port; neither headers nor Origin can
    # extend this server-owned allowlist.
    supplied_host = request.environ.get('HTTP_HOST', '')
    if supplied_host.lower() not in authorities:
        return _error('Host is not permitted for the Fruth API.', 'HTTP_HOST_NOT_ALLOWED', 400)
    if _is_asset_read():
        # These confined read capabilities keep their existing wildcard CORS,
        # token/path/lease checks and sandbox. They confer no mutation authority.
        return None
    if 'HTTP_ORIGIN' in request.environ and request.headers.get('Origin') not in origins:
        return _error('Origin is not permitted for the Fruth API.', 'HTTP_ORIGIN_NOT_ALLOWED', 403)
    effectful = request.method not in {'GET', 'HEAD', 'OPTIONS'}
    effectful = effectful or (
        request.method in {'GET', 'HEAD'}
        and (parse_bool(request.args.get('refresh'), default=False)
             or request.endpoint in _ACTION_GET_ENDPOINTS)
    )
    if effectful and request.headers.get(HTTP_ACTION_HEADER) != HTTP_ACTION_VALUE:
        return _error(
            f'An intentional API action requires {HTTP_ACTION_HEADER}: {HTTP_ACTION_VALUE}.',
            'HTTP_ACTION_REQUIRED', 403,
        )
    return None


def apply_api_cors(response):
    if not _is_api_request() or _is_asset_read():
        return response
    origin = request.headers.get('Origin')
    if origin in _trusted_origins():
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Expose-Headers'] = 'X-Fruth-Preview-Url'
        response.vary.add('Origin')
        if request.method == 'OPTIONS':
            response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS'
            response.headers['Access-Control-Allow-Headers'] = _CORS_HEADERS
    return response


def parse_preference_object():
    """Return (object, error) without invoking preference persistence."""
    if not request.is_json:
        return None, _error(
            'Inference preferences require a JSON object media type.',
            'PREFERENCES_UNSUPPORTED_MEDIA_TYPE', 415,
        )
    try:
        payload = request.get_json()
    except BadRequest:
        return None, _error(
            'Inference preferences require a non-empty, valid JSON body.',
            'PREFERENCES_INVALID_JSON', 400,
        )
    if not isinstance(payload, dict):
        return None, _error(
            'Inference preferences must be a JSON object.',
            'PREFERENCES_OBJECT_REQUIRED', 400,
        )
    return payload, None
