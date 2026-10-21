"""Metadata-only native probe; tests inject loader classes without native imports."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def describe_image_loaders(root: Path, generation_resolver, edit_resolver) -> dict:
    if not root.is_dir():
        raise ValueError('An existing local checkpoint directory is required.')
    model = str(root)
    generation = generation_resolver(model)
    if generation is None or not generation.supports_model(model):
        raise ValueError('Installed MLX-VLM has no generation loader for this local checkpoint.')
    family = str(generation.model_type)
    modes, defaults, issues = ['generate'], {}, {}
    for mode, loader in (('generate', generation), ('edit', edit_resolver(model))):
        if loader is None or not loader.supports_model(model):
            continue
        try:
            sampling = loader.resolve_defaults(model, model_path=root)
        except Exception as exc:
            if mode == 'generate':
                raise
            issues[mode] = str(exc)
            continue
        if mode == 'edit':
            modes.append(mode)
        defaults[mode] = {'steps': sampling.steps, 'guidance': sampling.guidance}
    return {'family': family, 'modes': modes, 'defaults': defaults, 'operation_issues': issues,
            'generation_class': generation.__module__ + '.' + generation.__name__,
            # Native operation constraint, not a model-ID allowlist.
            'steps_min': 2 if family == 'z_image' else 1}


def main():
    root = Path(sys.argv[1]).expanduser().absolute()
    if not root.is_dir():
        raise ValueError('An existing local checkpoint directory is required.')

    def metadata_only(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo'}:
            raise RuntimeError('Network access is forbidden in image discovery.')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            if str(args[0]).lower().endswith(('.safetensors', '.gguf', '.bin', '.pt', '.pth')):
                raise RuntimeError('Weight reads are forbidden in image discovery.')

    sys.addaudithook(metadata_only)
    import mlx.core as mx
    from mlx_vlm.generate.image import image_generation_model_class
    from mlx_vlm.generate.edit_image import image_edit_model_class

    def no_weights(*args, **kwargs):
        raise RuntimeError('Weight loading is forbidden in image discovery.')

    mx.load = no_weights
    return describe_image_loaders(root, image_generation_model_class, image_edit_model_class)


if __name__ == '__main__':
    try:
        print(json.dumps({'schema': 1, 'support': main()}))
    except Exception as exc:
        print(json.dumps({'schema': 1, 'error': f'{type(exc).__name__}: {exc}'}))
        sys.exit(1)
