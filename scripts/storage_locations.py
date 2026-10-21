#!/usr/bin/env python3
"""Operator-selected archive and Self-Attack locations; stdlib, no runtime imports."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys


CONFIG = Path('state/storage_locations.json')
DEFAULTS = {'archive': Path('.fruth_archiv'), 'self_attack': Path('state/self_attack')}
# A storage root must not overlap live state, code, or a cleanup input.
OWNED = ('state', 'artifacts', 'logs', 'outputs', 'scripts', 'tests', 'config',
         'docs', 'static', 'site', 'dist', 'fruth_research', 'fruth-upload',
         '00_backup', '.git', '.venv', 'fruth_core', 'fruth_server',
         'fruth_services', 'fruth_runtime', 'fruth_inference', 'fruth_integrations',
         '.pytest_cache', '.coverage', 'htmlcov', '.mypy_cache', '.ruff_cache',
         'model_ports.json')


@dataclass(frozen=True)
class Location:
    id: str
    path: Path
    read: bool
    write: bool


@dataclass(frozen=True)
class Store:
    locations: tuple[Location, ...]
    write_target: str | None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate storage configuration key: {key}')
        result[key] = value
    return result


def _keys(value, allowed, context):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError(f'Invalid fields in {context}; expected {", ".join(allowed)}')


def _bool(value, context):
    if type(value) is not bool:
        raise ValueError(f'{context} must be true or false')
    return value


def _path(raw, root):
    if not isinstance(raw, str) or not raw.strip() or any(ord(c) < 32 for c in raw):
        raise ValueError('Storage path must be a non-empty path without control characters')
    p = Path(raw).expanduser()
    return Path(os.path.abspath(p if p.is_absolute() else root / p))


def _overlap(a, b):
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def load(root: Path) -> dict[str, Store]:
    """Validate configuration without creating/probing files below data roots."""
    root = root.resolve()
    config = root / CONFIG
    if config.is_symlink():
        raise ValueError(f'Storage configuration must be a real file: {config}')
    try:
        raw = json.loads(config.read_text(), object_pairs_hook=_object)
    except FileNotFoundError:
        raw = {}
    _keys(raw, ('version', *DEFAULTS), 'storage configuration')
    version = raw.get('version', 1)
    if type(version) is not int or version != 1:
        raise ValueError('Unsupported storage configuration version; expected 1')
    stores = {}
    all_paths = []
    for kind, default in DEFAULTS.items():
        section = raw.get(kind, {})
        _keys(section, ('default_enabled', 'write_target', 'locations'), kind)
        enabled = _bool(section.get('default_enabled', True), f'{kind}.default_enabled')
        locations = [Location('default', root / default, enabled, enabled)]
        entries = section.get('locations', [])
        if not isinstance(entries, list):
            raise ValueError(f'{kind}.locations must be an array')
        ids = {'default'}
        for entry in entries:
            _keys(entry, ('id', 'path', 'read', 'write'), f'{kind}.locations')
            ident = entry.get('id')
            if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', ident) or ident in ids:
                raise ValueError(f'Invalid or duplicate {kind} location id: {ident!r}')
            ids.add(ident)
            path = _path(entry.get('path'), root)
            resolved = path.resolve()
            if resolved == root or root.is_relative_to(resolved):
                raise ValueError('Storage location cannot contain the checkout')
            if any(_overlap(resolved, (root / name).resolve()) for name in OWNED):
                raise ValueError(f'Storage location overlaps live/source paths: {path}')
            if resolved.is_relative_to(root) and '__pycache__' in resolved.relative_to(root).parts:
                raise ValueError(f'Storage location is inside a recursive cleanup target: {path}')
            locations.append(Location(ident, path,
                _bool(entry.get('read', True), f'{ident}.read'),
                _bool(entry.get('write', False), f'{ident}.write')))
        for location in locations:
            resolved = location.path.resolve()
            if any(_overlap(resolved, previous) for previous in all_paths):
                raise ValueError(f'Storage locations overlap: {location.path}')
            all_paths.append(resolved)
        target = section.get('write_target', 'default')
        if target is not None and (not isinstance(target, str) or target not in ids):
            raise ValueError(f'Unknown {kind}.write_target: {target!r}')
        if target is not None and not next(p for p in locations if p.id == target).write:
            raise ValueError(f'{kind}.write_target is disabled or read-only: {target}')
        stores[kind] = Store(tuple(locations), target)
    return stores


def write_root(root: Path, kind: str) -> Path:
    """An external root must already exist. Never create an absent drive path."""
    root = root.resolve()
    store = load(root)[kind]
    if store.write_target is None:
        raise ValueError(f'No write target enabled for {kind}')
    location = next(p for p in store.locations if p.id == store.write_target)
    path = location.path
    if path.resolve() != path or path.is_symlink():
        raise ValueError(f'Write location must be a real directory, not a symlink: {path}')
    if path.exists() and not path.is_dir():
        raise ValueError(f'Write location is not a directory: {path}')
    if location.id != 'default' and not path.is_dir():
        raise ValueError(f'Write location unavailable; no fallback: {path}')
    ancestor = path
    while not ancestor.exists():
        ancestor = ancestor.parent
    if not os.access(ancestor, os.W_OK | os.X_OK):
        raise ValueError(f'Write location is not writable: {path}')
    return path


def find(root: Path, kind: str, reference: str | Path) -> Path:
    """Find exact relative names across readable roots; never choose a duplicate."""
    root = root.resolve()
    store = load(root)[kind]
    ref = Path(reference)
    if ref.is_absolute():
        # Explicit existing paths remain usable, including historical evidence.
        if ref.exists():
            return ref.resolve()
        relatives = [ref.relative_to(p.path) for p in store.locations if ref.is_relative_to(p.path)]
        if len(relatives) != 1:
            raise FileNotFoundError(f'Unknown recorded storage root: {ref}')
        ref = relatives[0]
    elif len(ref.parts) > 1 and (Path.cwd() / ref).exists():
        return ref.resolve()
    if not ref.parts or any(part in ('.', '..') for part in ref.parts):
        raise ValueError('Use an exact storage-relative name without parent traversal')
    matches = []
    unavailable = []
    for location in store.locations:
        if not location.read:
            continue
        if not location.path.is_dir():
            unavailable.append(str(location.path))
            continue
        candidate = location.path / ref
        if candidate.exists():
            resolved = candidate.resolve()
            if not resolved.is_relative_to(location.path.resolve()):
                raise ValueError(f'Storage reference escapes its registered root: {candidate}')
            if resolved not in matches:
                matches.append(resolved)
    if len(matches) > 1:
        raise ValueError(f'Ambiguous storage reference {ref}; use an explicit path: {matches}')
    if matches:
        return matches[0]
    raise FileNotFoundError(f'Storage item not found: {ref}; unavailable roots: {unavailable}')


def describe(root: Path, kind: str, *, entries=False):
    store = load(root)[kind]
    result = {'kind': kind, 'write_target': store.write_target, 'locations': []}
    for location in store.locations:
        available = location.path.is_dir()
        row = dict(id=location.id, path=str(location.path), read=location.read,
                   write=location.write, available=available)
        if entries and location.read and available:
            row['directories'] = sorted(p.name for p in location.path.iterdir()
                                        if p.is_dir() and not p.is_symlink())
        result['locations'].append(row)
    return result


def evidence_path(root: Path, reference: str | Path, evidence_root: Path) -> Path:
    """Resolve a retained path only within the explicitly selected evidence tree.

    Missing absolute paths can move between registered roots with the exact
    relative suffix. An existing old copy cannot silently replace selected data.
    """
    evidence_root = evidence_root.resolve()
    path = Path(reference)
    if '..' in path.parts:
        raise ValueError('Evidence reference contains parent traversal')
    if not path.is_absolute():
        path = evidence_root / path
    if not path.resolve().is_relative_to(evidence_root):
        path = find(root, 'self_attack', path)
    path = path.resolve()
    if not path.is_relative_to(evidence_root):
        raise ValueError('Evidence reference is outside the selected evidence tree')
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('list', 'write-root'):
        p = commands.add_parser(name)
        p.add_argument('kind', choices=DEFAULTS)
    p = commands.add_parser('find')
    p.add_argument('kind', choices=DEFAULTS)
    p.add_argument('reference')
    commands.add_parser('status')
    commands.add_parser('protected-roots')
    args = parser.parse_args(argv)
    try:
        if args.command == 'find':
            print(find(args.root, args.kind, args.reference))
        elif args.command == 'write-root':
            print(write_root(args.root, args.kind))
        elif args.command == 'protected-roots':
            paths = set()
            for store in load(args.root).values():
                for location in store.locations:
                    paths.update((location.path, location.path.resolve()))
            for path in sorted(paths):
                print(path)
        elif args.command == 'list':
            print(json.dumps(describe(args.root, args.kind, entries=True), indent=2))
        else:
            print(json.dumps([describe(args.root, kind) for kind in DEFAULTS], indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Storage locations: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
