#!/usr/bin/env python3
"""Offline startup checks. No Fruth imports, package imports or installation.

Pip >=22.2 owns requirement/marker evaluation. Only the named-package subset
below may reach its dry-run CLI: arbitrary pip manifests can run build hooks even
in a dry run. Keep this admission check separate from dependency resolution.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile


class PreflightError(Exception):
    pass


# One named distribution, optional comma-separated version constraints, optional
# PEP 508 marker. No extras: pip check does not validate optional extra edges.
_NAME = r'[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?'
_SPEC = r'(?:===|==|!=|~=|<=|>=|<|>)\s*[A-Za-z0-9.*+!_-]+'
_REQUIREMENT = re.compile(rf'{_NAME}\s*(?:{_SPEC}(?:\s*,\s*{_SPEC})*)?\s*(?:;[^\r\n]+)?')
_ARCHIVE = re.compile(r'\.(?:whl|zip|tar|tar\.gz|tgz|tar\.bz2|tbz2?|tar\.xz|txz|tar\.lz|tlz)$', re.I)


def check_interpreter(venv: Path | None = None) -> None:
    if sys.version_info < (3, 11):
        raise PreflightError('Fruth requires Python 3.11 or newer; selected ' + sys.version.split()[0])
    if not ssl.OPENSSL_VERSION.startswith('OpenSSL ') or ssl.OPENSSL_VERSION_INFO < (1, 1, 1):
        raise PreflightError('Fruth requires OpenSSL 1.1.1 or newer (not LibreSSL); selected ' + ssl.OPENSSL_VERSION)
    if venv is not None and (Path(sys.prefix).resolve() != venv.resolve() or sys.prefix == sys.base_prefix):
        raise PreflightError('Selected interpreter does not belong to the main venv: ' + str(venv))


def read_requirements(path: Path) -> str:
    try:
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise PreflightError('Cannot read requirements manifest: ' + str(path)) from exc
    lines = []
    for number, raw in enumerate(content.splitlines(), 1):
        line = re.split(r'\s+#', raw.strip(), maxsplit=1)[0].strip()
        if not line or line.startswith('#'):
            continue
        # Reject pip expansion/continuation/options even inside a marker. Marker
        # syntax itself is validated by pip, not by a second requirement parser.
        name = re.match(_NAME, line)
        if ('\\' in line or '$' in line or re.search(r'(^|\s)-', line) or
                (name and _ARCHIVE.search(name.group())) or
                not _REQUIREMENT.fullmatch(line)):
            raise PreflightError(
                f'Unsupported startup requirement at {path}:{number}. Use one named '
                'package with optional version constraints and platform markers per line; '
                'URLs, local projects, extras, includes and pip options are not supported.'
            )
        lines.append(line)
    if not lines:
        raise PreflightError('Requirements manifest has no named requirements: ' + str(path))
    return '\n'.join(lines) + '\n'


def check_environment(requirements: str) -> None:
    try:
        version = metadata.version('pip')
    except metadata.PackageNotFoundError as exc:
        raise PreflightError('pip is missing; offline startup checks require pip >=22.2.') from exc
    parts = re.match(r'^(\d+)\.(\d+)(?:\.|$)', version)
    if not parts or tuple(map(int, parts.groups())) < (22, 2):
        raise PreflightError(f'Offline startup checks require pip >=22.2; found {version}.')
    env = {key: value for key, value in os.environ.items() if not key.startswith('PIP_')}
    env['PIP_CONFIG_FILE'] = os.devnull
    command = [sys.executable, '-I', '-B', '-m', 'pip', '--isolated',
               '--disable-pip-version-check', '--no-input', '--no-cache-dir']
    # Use the admitted bytes, never reopen an unvalidated manifest in pip. The
    # temporary file is outside Fruth state and removed on both success/failure.
    with tempfile.TemporaryDirectory(prefix='fruth-preflight-') as directory:
        manifest = Path(directory) / 'requirements.txt'
        manifest.write_text(requirements, encoding='utf-8')
        checks = [
            ('Active direct requirements are not satisfied',
             ['install', '--dry-run', '--no-index', '--no-deps', '--only-binary=:all:', '-r', str(manifest)]),
            ('Installed transitive dependencies are inconsistent', ['check']),
        ]
        for reason, arguments in checks:
            # A bare package name must not resolve to a same-named local project
            # in the caller's checkout. This directory contains only our manifest.
            result = subprocess.run(command + arguments, cwd=directory, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            if result.returncode:
                raise PreflightError(reason + ':\n' + result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requirements', type=Path, required=True)
    parser.add_argument('--venv', type=Path)
    parser.add_argument('--interpreter-only', action='store_true',
                        help='Validate interpreter and manifest before creating/installing a venv')
    args = parser.parse_args()
    try:
        check_interpreter(args.venv)
        requirements = read_requirements(args.requirements)
        if not args.interpreter_only:
            check_environment(requirements)
    except (PreflightError, OSError) as exc:
        print('Startup preflight failed: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
