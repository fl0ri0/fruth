"""Describe local image checkpoints without importing a native model loader."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def image_snapshot_fingerprint(root: Path) -> tuple:
    """Stat metadata and weight links; a finished download invalidates cache."""
    rows = []
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.suffix not in {'.json', '.safetensors', '.model', '.txt', '.jinja'}:
            continue
        info = path.stat()
        rows.append((str(path.relative_to(root)), info.st_size, info.st_mtime_ns, info.st_ino))
    return tuple(rows)


def read_image_snapshot_metadata(model_name: str, root: Path) -> dict[str, Any]:
    """Candidacy and prerequisites, never a model-name allowlist.

    Native support is resolved by the MLX discovery/lifecycle owner. File presence
    is not tensor validation or proof of successful generation.
    """
    index = _read_object(root / 'model_index.json')
    config = _read_object(root / 'config.json')
    manifest = _read_object(root / 'manifest.json')
    pipeline = str(index.get('_class_name') or '')
    kind = str(config.get('model_type') or config.get('model') or '')
    candidate = bool(index.get('vae') and (index.get('transformer') or index.get('unet'))) or any(
        token in (pipeline + ' ' + kind).lower() for token in ('image', 'flux', 'diffusion')
    ) or bool(manifest and (root / 'transformer-packed-mflux').is_dir())
    if not candidate:
        return {}
    problems = []
    if not any(p.is_file() and p.stat().st_size > 0 for p in root.rglob('*.safetensors')):
        problems.append('Missing image checkpoint weights.')
    manifest_files = []
    entries = manifest.get('files', [])
    if not isinstance(entries, list):
        problems.append('Invalid image manifest file list.')
        entries = []
    for entry in entries:
        name = entry if isinstance(entry, str) else None
        if isinstance(entry, dict):
            name = next((entry.get(key) for key in ('remote_path', 'path', 'filename', 'name')
                         if entry.get(key)), None)
        if isinstance(name, str) and name.endswith('.safetensors'):
            manifest_files.append(name)
    for name in manifest_files:
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            problems.append('Invalid weight path in image manifest.')
        elif not path.is_file() or path.stat().st_size == 0:
            problems.append(f'Missing image manifest weight: {name}.')
    # Check declared components without imposing one architecture's layout.
    for component, declaration in index.items():
        # A native manifest may bind packed weights to different directories
        # from the standard Diffusers component descriptors (e.g. Bonsai).
        if manifest_files:
            break
        if component.startswith('_') or not isinstance(declaration, list) or not any(declaration):
            continue
        if component in {'transformer', 'text_encoder', 'text_encoder_2', 'vae', 'unet'}:
            directory = root / component
            if not _read_object(directory / 'config.json'):
                problems.append(f'Missing or invalid {component}/config.json.')
            if not any(p.is_file() and p.stat().st_size > 0 for p in directory.glob('*.safetensors')):
                problems.append(f'Missing {component} weights.')
    for path in root.rglob('*.safetensors.index.json'):
        weight_map = _read_object(path).get('weight_map')
        if not isinstance(weight_map, dict) or not weight_map:
            problems.append(f'Invalid weight index: {path.relative_to(root)}.')
            continue
        for name in weight_map.values():
            if not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts:
                problems.append(f'Invalid shard path in {path.relative_to(root)}.')
                break
            shard = path.parent / name
            if not shard.is_file() or shard.stat().st_size == 0:
                problems.append(f'Missing checkpoint shard: {name}.')
                break
    return {
        'provider_capabilities': ['image_generation'], 'inputs': ['text'], 'outputs': ['image'],
        'snapshot_image_pipeline': pipeline or kind or 'image_manifest',
        'snapshot_model_type': kind, 'snapshot_image_variant': None,
        'snapshot_image_supported': False, 'snapshot_image_prerequisite_issues': problems,
        'snapshot_image_issues': problems or ['Installed MLX-VLM image loader has not been checked.'],
        'image_modes': [],
    }
