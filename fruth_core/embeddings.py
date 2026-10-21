"""Bounded, ordered embedding inputs for the existing native transports."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io

from helpers.model_capabilities import embedding_input_modalities

# These bound optional semantic helper work, not the caller's generation input.
EMBEDDING_MEDIA_MAX_BYTES = 32 * 1024 * 1024
EMBEDDING_MEDIA_MAX_ITEMS = 8


def media_embedding_input(kind: str, data: bytes) -> dict:
    if kind not in {'image', 'audio'} or not data:
        raise ValueError('Embedding media requires non-empty image or audio bytes.')
    if len(data) > EMBEDDING_MEDIA_MAX_BYTES:
        raise ValueError('Embedding media exceeds the 32 MiB helper budget.')
    return {kind: base64.b64encode(data).decode('ascii')}


def encode_embedding_inputs(inputs: list, *, backend: str, transport: str, instance: dict) -> tuple[list, list[dict]]:
    """Return native inputs and byte provenance; never fetch URLs or reinterpret text."""
    if not isinstance(inputs, list) or not inputs:
        raise ValueError('Embedding inputs must be a non-empty ordered batch.')
    allowed = embedding_input_modalities(backend, instance)
    encoded, media = [], []
    total_bytes = 0
    for index, item in enumerate(inputs):
        if isinstance(item, str):
            if 'text' not in allowed:
                raise ValueError('Selected embedding adapter does not accept text.')
            encoded.append(item)
            continue
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError('Each embedding item must be text or one image/audio base64 object.')
        kind, token = next(iter(item.items()))
        if kind not in {'image', 'audio'} or kind not in allowed:
            raise ValueError(f'Selected embedding model/adapter does not accept {kind!r}.')
        if not isinstance(token, str) or len(token) > 4 * ((EMBEDDING_MEDIA_MAX_BYTES + 2) // 3):
            raise ValueError('Embedding media must be bounded inline base64.')
        try:
            raw = base64.b64decode(token, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError('Embedding media must be valid inline base64, not a path or URL.') from exc
        total_bytes += len(raw)
        if not raw or total_bytes > EMBEDDING_MEDIA_MAX_BYTES or len(media) >= EMBEDDING_MEDIA_MAX_ITEMS:
            raise ValueError('Embedding media exceeds the 32 MiB / 8 item helper budget or is empty.')
        mime = None
        if kind == 'image':
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as image:
                mime = Image.MIME.get(image.format)
                image.verify()
            if not mime or not mime.startswith('image/'):
                raise ValueError('Embedding image has no recognized image format.')
        # Audio format decoding belongs to the selected native decoder. Failure
        # rejects the whole batch; a non-empty byte string is not audio evidence.
        if transport == 'ollama_api_embed' and backend == 'ollama':
            encoded.append({kind: token})
        elif transport == 'openai_embeddings' and backend == 'mlx' and kind == 'image':
            encoded.append({'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{token}'}})
        else:
            raise ValueError('Selected embedding transport has no adapter for this modality.')
        media.append({'index': index, 'modality': kind, 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest()})
    return encoded, media
