"""Image adapter contracts; execution does not own artifact acceptance or closure."""

from __future__ import annotations

import base64
import hashlib
import io
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Fruth's bounded native image transport envelope. A loader may be stricter.
MLX_IMAGE_MIN_SIDE = 256
MLX_IMAGE_MAX_SIDE = 2048
MLX_IMAGE_SIDE_STEP = 16


@dataclass(frozen=True)
class ImageRequest:
    model: str
    prompt: str
    width: int | None = None
    height: int | None = None
    seed: int | None = None
    reference_b64: str | None = None
    timeout_sec: int = 600
    steps: int | None = None


class ImageAdapterError(RuntimeError):
    """A provider result cannot satisfy the image transport contract."""


def parse_mlx_image_control(raw: Any, name: str) -> int:
    """Parse JSON integers or multipart decimal strings without clamping."""
    if type(raw) is int:
        value = raw
    elif isinstance(raw, str) and re.fullmatch(r'[0-9]+', raw.strip()):
        value = int(raw.strip())
    else:
        raise ValueError(f'Image {name} must be an integer.')
    if name == 'seed':
        if not 0 <= value <= 2_147_483_647:
            raise ValueError('Image seed must be between 0 and 2147483647.')
    elif name == 'steps':
        if value < 1:
            raise ValueError('Image steps must be a positive integer.')
    elif name in {'width', 'height'}:
        if not MLX_IMAGE_MIN_SIDE <= value <= MLX_IMAGE_MAX_SIDE or value % MLX_IMAGE_SIDE_STEP:
            raise ValueError('MLX image dimensions must be multiples of 16 between 256 and 2048.')
    else:
        raise ValueError('Unknown image control.')
    return value


def supports_image_steps(backend: str, package: str, metadata: dict) -> bool:
    return bool(
        backend == 'mlx' and package == 'mlx_vlm'
        and metadata.get('image_transport') == 'mlx_vlm_images_v1'
        and 'steps' in (metadata.get('image_request_controls') or [])
    )


def validate_image_steps(raw: Any, metadata: dict) -> int:
    value = parse_mlx_image_control(raw, 'steps')
    minimum = metadata.get('image_steps_min', 1)
    if type(minimum) is not int or minimum < 1:
        raise ValueError('Invalid image steps contract for the selected instance.')
    if value < minimum:
        raise ValueError(f'Image steps must be at least {minimum} for this loader.')
    return value


def select_image_adapter(backend: str, package: str, metadata: dict, *, editing: bool) -> str:
    if backend == 'ollama':
        return 'ollama_images_v1'
    if (backend == 'mlx' and package == 'mlx_vlm'
            and metadata.get('image_transport') == 'mlx_vlm_images_v1'
            and ('edit' if editing else 'generate') in metadata.get('image_modes', [])):
        return 'mlx_vlm_images_v1'
    raise ValueError('Selected instance has no qualified image adapter for this operation.')


def _image_decoder():
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageAdapterError(
            'Pillow is required for MLX image execution. Update the Fruth '
            'environment from requirements.txt before using this adapter.'
        ) from exc
    return Image


def _image_bytes(token: str, *, png_only: bool = False) -> tuple[bytes, int, int]:
    Image = _image_decoder()

    if token.startswith('data:'):
        header, separator, token = token.partition(',')
        if not separator or not header.startswith('data:image/') or not header.endswith(';base64'):
            raise ValueError('Image must use a base64 image payload.')
    raw = base64.b64decode(token, validate=True)
    with Image.open(io.BytesIO(raw)) as image:
        if png_only and image.format != 'PNG':
            raise ValueError('Image endpoint returned a non-PNG result.')
        width, height = image.size
        image.verify()
    # verify() alone need not decode pixels. Reject truncated streams as well.
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
    return raw, width, height


def mlx_vlm_image_request(port: int, request: ImageRequest, requests_module) -> dict[str, Any]:
    """Native JSON generation/edit transport with Fruth-owned reference lifetime.

    No URL fetches, provider output paths, extra models or alternate-protocol retry.
    Returned bytes still pass through the existing artifact persistence owner.
    """
    if not request.model or not request.prompt:
        raise ValueError('Image model and prompt are required.')
    if (request.width is None) != (request.height is None):
        raise ValueError('Image width and height must be supplied together.')
    for value in (request.width, request.height):
        if value is not None and (
            type(value) is not int or not MLX_IMAGE_MIN_SIDE <= value <= MLX_IMAGE_MAX_SIDE
            or value % MLX_IMAGE_SIDE_STEP
        ):
            raise ValueError('MLX image dimensions must be multiples of 16 between 256 and 2048.')
    if request.seed is not None and (type(request.seed) is not int or request.seed < 0):
        raise ValueError('Image seed must be a nonnegative integer.')
    if request.steps is not None:
        if type(request.steps) is not int:
            raise ValueError('Image steps must be a positive integer.')
        parse_mlx_image_control(request.steps, 'steps')
    if request.timeout_sec <= 0:
        raise ValueError('Image request requires a positive timeout.')
    # Fail before costly native generation if an existing environment has not
    # yet installed the declared decoding dependency.
    _image_decoder()
    payload: dict[str, Any] = {
        'model': request.model, 'prompt': request.prompt, 'n': 1,
        'response_format': 'b64_json', 'output_format': 'png',
    }
    for key in ('width', 'height', 'seed', 'steps'):
        value = getattr(request, key)
        if value is not None:
            payload[key] = value
    path = '/v1/images/edits' if request.reference_b64 else '/v1/images/generations'
    reference_evidence = None
    with tempfile.TemporaryDirectory(prefix='fruth-image-reference-') as temporary:
        reference = None
        if request.reference_b64:
            try:
                raw, width, height = _image_bytes(request.reference_b64)
            except Exception as exc:
                raise ValueError(f'Invalid image reference: {exc}') from exc
            reference = Path(temporary) / 'reference.image'
            reference.write_bytes(raw)
            reference_evidence = {
                'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw),
                'width': width, 'height': height,
            }
            payload['image'] = str(reference)
        response = requests_module.post(
            f'http://127.0.0.1:{port}{path}', json=payload, timeout=request.timeout_sec,
        )
        response.raise_for_status()
        try:
            body = response.json()
            if reference is not None and hashlib.sha256(reference.read_bytes()).hexdigest() != reference_evidence['sha256']:
                raise ValueError('Reference image changed during execution.')
            if not isinstance(body, dict) or body.get('error'):
                raise ValueError('Image endpoint returned an error or malformed envelope.')
            entries = body.get('data')
            if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
                raise ValueError('Image endpoint must return exactly one image.')
            item = entries[0]
            if item.get('path') or item.get('url'):
                raise ValueError('Image endpoint returned an unauthorized output location.')
            token = item.get('b64_json')
            if not isinstance(token, str) or not token:
                raise ValueError('Image endpoint returned no image bytes.')
            raw, width, height = _image_bytes(token, png_only=True)
            for key, actual in (('width', width), ('height', height)):
                claimed = item.get(key)
                if type(claimed) is not int or claimed != actual:
                    raise ValueError(f'Image {key} evidence does not match decoded bytes.')
                requested = getattr(request, key)
                if requested is not None and actual != requested:
                    raise ValueError(f'Image {key} does not satisfy the request.')
            seed = item.get('seed')
            if type(seed) is not int or seed < 0:
                raise ValueError('Image endpoint returned no valid effective seed.')
            if request.seed is not None and seed != request.seed:
                raise ValueError('Image seed evidence conflicts with the requested seed.')
            if item.get('mime_type', 'image/png') != 'image/png':
                raise ValueError('Image MIME evidence conflicts with PNG bytes.')
        except Exception as exc:
            raise ImageAdapterError(f'Invalid image result evidence: {exc}') from exc
    evidence = {
        'adapter': 'mlx_vlm_images_v1', 'model': request.model, 'endpoint': path,
        'requested_controls': {key: getattr(request, key) for key in ('width', 'height', 'seed', 'steps') if getattr(request, key) is not None},
        'sent_controls': {key: payload[key] for key in ('width', 'height', 'seed', 'steps') if key in payload},
        'reported_seed': seed,
        'result': {'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw),
                   'width': width, 'height': height, 'mime_type': 'image/png'},
        'reference': reference_evidence,
    }
    return {'image_data_url': 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii'),
            'seed': seed, 'image_execution': evidence}
