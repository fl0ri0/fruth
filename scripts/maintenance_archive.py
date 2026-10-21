#!/usr/bin/env python3
"""Space preflight, verified copies and copy-before-remove archive moves."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys

if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.storage_locations import write_root


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
    selected = write_root(root, 'archive')
    if destination.parent != selected or destination.parent.resolve() != selected:
        raise ValueError('Archive base must be the selected real directory (default: repo-local .fruth_archiv)')
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


def verified_move(source: Path, destination: Path) -> None:
    """External archival: verify every byte before removing this source entry."""
    before = inventory(source)
    verified_copy(source, destination)
    if inventory(source) != before:
        raise ValueError(f'Archive source changed before removal: {source}')
    if source.is_dir():
        shutil.rmtree(source)
    else:
        source.unlink()


def clean_local_self_attack_runs(root: Path, *, dry_run: bool) -> None:
    """Full archive rotates local run directories, never external stores or links."""
    root = root.resolve()
    source = root / 'state/self_attack'
    if source.is_symlink() or source.resolve() != source:
        raise ValueError(f'Local campaign cleanup root must be a real checkout directory: {source}')
    if not source.exists():
        return
    if not source.is_dir() or os.path.ismount(source):
        raise ValueError(f'Invalid local campaign cleanup root: {source}')
    device = source.stat().st_dev
    targets = []
    for child in sorted(source.iterdir()):
        if child.is_symlink() or not child.is_dir():
            continue  # Keep monitor helpers, Finder aliases and symlinks.
        entries = inventory(child)
        if os.path.ismount(child) or any(row[4] != device for row in entries.values()):
            raise ValueError(f'Local campaign cleanup must not cross a mounted store: {child}')
        targets.append(child)
    # Validate every selected tree before deleting any. Nested symlinks are not followed.
    for child in targets:
        if dry_run:
            print(f'[dry-run] remove local self-attack run without archiving: {child}', flush=True)
        else:
            if child.is_symlink() or child.resolve() != child:
                raise ValueError(f'Local campaign cleanup target changed: {child}')
            shutil.rmtree(child)
            print(f'removed local self-attack run without archiving: {child}', flush=True)


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
    move = commands.add_parser('move-verified')
    move.add_argument('source', type=Path)
    move.add_argument('destination', type=Path)
    cleanup = commands.add_parser('clean-local-self-attack-runs')
    cleanup.add_argument('root', type=Path)
    cleanup.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'clean-local-self-attack-runs':
            clean_local_self_attack_runs(args.root, dry_run=args.dry_run)
        elif args.command == 'preflight':
            preflight(args.root.resolve(), args.destination.absolute(), args.paths)
        elif args.command == 'move-verified':
            verified_move(args.source, args.destination)
        else:
            verified_copy(args.source, args.destination)
    except (OSError, ValueError, shutil.Error) as exc:
        print(f'Archive aborted: {exc}. Unmoved sources and partial archive are retained; '
              'earlier verified moves may have completed.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
