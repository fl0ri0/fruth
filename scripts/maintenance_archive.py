#!/usr/bin/env python3
"""Space preflight and verified copies for clean_repo_state.sh (no source removal)."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys


# Extra room for filesystem metadata, modest growth and unrelated disk activity.
MIN_FREE_MARGIN_BYTES = 256 * 1024 * 1024
COPY_MARGIN_PERCENT = 5


def inventory(path: Path) -> dict[str, tuple]:
    """Do not follow evidence symlinks or silently omit unreadable entries."""
    result = {}

    def visit(current: Path) -> None:
        info = current.lstat()
        mode = info.st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
            raise ValueError(f'Unsupported archive entry: {current}')
        result[str(current.relative_to(path))] = (
            mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
            info.st_dev, info.st_ino,
            os.readlink(current) if stat.S_ISLNK(mode) else None,
        )
        if stat.S_ISDIR(mode):
            with os.scandir(current) as entries:
                for entry in entries:
                    visit(Path(entry.path))

    visit(path)
    return result


def file_bytes(entries: dict[str, tuple]) -> int:
    return sum(row[1] for row in entries.values() if not stat.S_ISDIR(row[0]))


def preflight(root: Path, destination: Path, paths: list[str]) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Archive destination already exists; preserve it: {destination}')
    ancestor = destination.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if destination.parent.resolve() != root / '.ollmo_archiv':
        raise ValueError('Archive base must be a real repo-local .ollmo_archiv directory')
    total = 0
    for relative in paths:
        source = root / relative
        if source.is_symlink():
            raise ValueError(f'Archive copy scope must not be a symlink: {source}')
        if not source.exists():
            continue
        if not source.resolve().is_relative_to(root):
            raise ValueError(f'Archive copy scope leaves the checkout: {source}')
        entries = inventory(source)
        size = file_bytes(entries)
        total += size
        print(f'archive copy bytes: {relative} = {size}', flush=True)
        if relative in ('state/self_attack', 'state/benchmarks', 'state/diagnostics'):
            for child in sorted(source.iterdir()):
                print(f'  snapshot evidence (source stays active): {child.relative_to(root)}', flush=True)
    margin = max(MIN_FREE_MARGIN_BYTES, (total * COPY_MARGIN_PERCENT + 99) // 100)
    free = shutil.disk_usage(ancestor).free
    print(f'archive space: selected_copy_bytes={total} destination_free_bytes={free} '
          f'safety_margin_bytes={margin} required_bytes={total + margin}', flush=True)
    print(f'archive destination: {destination}', flush=True)
    if free < total + margin:
        raise ValueError('Insufficient destination disk space; no archive copy or cleanup started')


def digest(path: Path) -> bytes:
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.digest()


def verified_copy(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise ValueError(f'Archive copy scope must not be a symlink: {source}')
    before = inventory(source)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f'Archive copy destination already exists: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination)
    copied = inventory(destination)
    if before.keys() != copied.keys():
        raise ValueError(f'Archive tree verification failed: {source}')
    for relative, row in before.items():
        other = copied[relative]
        if row[0] != other[0] or row[6] != other[6]:
            raise ValueError(f'Archive entry verification failed: {source / relative}')
        if stat.S_ISREG(row[0]):
            source_file = source if relative == '.' else source / relative
            copied_file = destination if relative == '.' else destination / relative
            if row[1] != other[1] or digest(source_file) != digest(copied_file):
                raise ValueError(f'Archive byte verification failed: {source / relative}')
    if inventory(source) != before or inventory(destination) != copied:
        raise ValueError(f'Archive source or destination changed during verification: {source}')
    print(f'verified archive copy: {source} -> {destination}', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preview = commands.add_parser('preflight')
    preview.add_argument('root', type=Path)
    preview.add_argument('destination', type=Path)
    preview.add_argument('paths', nargs='*')
    copy = commands.add_parser('copy')
    copy.add_argument('source', type=Path)
    copy.add_argument('destination', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'preflight':
            preflight(args.root.resolve(), args.destination.absolute(), args.paths)
        else:
            verified_copy(args.source, args.destination)
    except (OSError, ValueError, shutil.Error) as exc:
        print(f'Archive aborted: {exc}. Sources and any partial archive are retained.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
