#!/usr/bin/env python3
"""Explicit native bootstrap qualification with disposable venvs/local wheels.

Not an ordinary pytest route. Requires macOS sandbox-exec; never runs a backend,
service, real model selector or the production launcher in the production root.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile


SOURCE = Path(__file__).resolve().parents[1]
FILES = ('start_multi_models.sh', 'scripts/bootstrap_preflight.py')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel(directory, name, version, requires=()):
    """Create a valid inert wheel; pip performs all actual installations."""
    stem = f'{name}-{version}.dist-info'
    files = {
        f'{stem}/METADATA': ('Metadata-Version: 2.1\nName: ' + name.replace('_', '-') +
                            '\nVersion: ' + version + '\n' +
                            ''.join('Requires-Dist: ' + item + '\n' for item in requires)).encode(),
        f'{stem}/WHEEL': b'Wheel-Version: 1.0\nGenerator: fruth-bootstrap-fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
        f'{name}/__init__.py': b'raise RuntimeError("Preflight must not import dependency code")\n',
    }
    rows = [(name, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('='), str(len(data)))
            for name, data in files.items()]
    rows.append((f'{stem}/RECORD', '', ''))
    output = io.StringIO()
    csv.writer(output).writerows(rows)
    files[f'{stem}/RECORD'] = output.getvalue().encode()
    path = directory / f'{name}-{version}-py3-none-any.whl'
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def tree_identity(root):
    return {str(p.relative_to(root)): ('symlink:' + os.readlink(p) if p.is_symlink() else digest(p))
            for p in sorted(root.rglob('*')) if p.is_symlink() or p.is_file()}


class Fixture:
    def __init__(self, output, python):
        self.output, self.python = output, python
        output.mkdir(exist_ok=False)
        self.work = output / 'disposable'
        self.work.mkdir()
        self.records = []
        self.wheels = self.work / 'wheels'
        self.wheels.mkdir()
        wheel(self.wheels, 'fruth_bootstrap_leaf', '1.0')
        wheel(self.wheels, 'fruth_bootstrap_leaf', '2.0')
        wheel(self.wheels, 'fruth_bootstrap_parent', '1.0', ['fruth-bootstrap-leaf==1.0'])
        self.base = self.work / 'base-bin'
        self.base.mkdir()
        (self.base / 'python3').symlink_to(python)
        self.temp = self.work / 'tmp'
        self.temp.mkdir()
        self.env = dict(PATH=str(self.base) + ':/usr/bin:/bin', HOME=str(self.work),
                        TMPDIR=str(self.temp), LANG='en_US.UTF-8',
                        PYTHONDONTWRITEBYTECODE='1', PIP_NO_INDEX='1',
                        PIP_FIND_LINKS=str(self.wheels), PIP_NO_CACHE_DIR='1',
                        PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK='1')
        self.profile = '(version 1)(allow default)(deny network*)'
        self.save('source.json', {name: digest(SOURCE / name) for name in (*FILES, 'tests/python_bootstrap_fixture.py')})
        self.save('wheels.json', {p.name: digest(p) for p in self.wheels.iterdir()})

    def save(self, name, value):
        (self.output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

    def command(self, label, argv, cwd, env=None):
        started = time.monotonic()
        command = ['/usr/bin/sandbox-exec', '-p', self.profile, *map(str, argv)]
        result = subprocess.run(command, cwd=cwd, env=env or self.env,
                                text=True, capture_output=True, timeout=120)
        record = dict(label=label, command=command, cwd=str(cwd), exit=result.returncode,
                      stdout=result.stdout, stderr=result.stderr,
                      elapsed_seconds=time.monotonic() - started)
        self.records.append(record)
        self.save('commands.json', self.records)
        return result

    def checkout(self, label, requirements='fruth-bootstrap-parent==1.0\n'):
        root = self.work / label
        root.mkdir()
        for name in FILES:
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, dest)
        (root / 'requirements.txt').write_text(requirements)
        for package in ('fruth_core', 'fruth_runtime', 'fruth_server', 'fruth_inference'):
            (root / package).mkdir()
            (root / package / '__init__.py').write_text(
                "from pathlib import Path\nPath('UNEXPECTED_IMPORT').touch()\nraise RuntimeError('Fruth import during preflight')\n")
        (root / 'scripts/startup_model_manager.py').write_text(
            "import json, sys\nfrom pathlib import Path\n"
            "Path('boundary.json').write_text(json.dumps({'executable':sys.executable,'prefix':sys.prefix}))\n"
            "raise SystemExit(73)\n")
        return root

    def launch(self, label, root, ready=False, fresh=False, env=None):
        boundary = root / 'boundary.json'
        boundary.unlink(missing_ok=True)
        before = tree_identity(root / '.venv') if not fresh else None
        result = self.command(label, ['/bin/bash', root / 'start_multi_models.sh'], root, env)
        assert result.returncode == 1, (label, result.stdout, result.stderr)
        assert boundary.exists() == ready, (label, result.stdout, result.stderr)
        assert not any((root / name).exists() for name in ('state', 'artifacts', 'logs', 'UNEXPECTED_IMPORT'))
        if not fresh:
            assert tree_identity(root / '.venv') == before, label + ': environment changed'
            assert 'Installing dependencies' not in result.stdout
        if ready:
            assert Path(json.loads(boundary.read_text())['prefix']).resolve() == (root / '.venv').resolve()
            assert Path(json.loads(boundary.read_text())['executable']) == root / '.venv/bin/python3'
        else:
            assert 'Step 1.5' not in result.stdout and 'Step 2' not in result.stdout
        return result

    def pip(self, root, *args):
        result = self.command('explicit disposable pip ' + ' '.join(args),
                              [root / '.venv/bin/python3', '-B', '-m', 'pip', *args], root)
        assert result.returncode == 0, result.stderr

    def run(self):
        # Prove the actual child envelope denies both IPv4 and DNS operations.
        result = self.command('network denial control', [self.python, '-I', '-B', '-c',
            'import errno,socket\ns=socket.socket()\n'
            'try: s.bind(("127.0.0.1",0))\n'
            'except OSError as e: assert e.errno in (errno.EPERM,errno.EACCES), repr(e)\n'
            'else: raise SystemExit("unexpected network permission")\n'], self.work)
        assert result.returncode == 0, result.stderr
        healthy = self.checkout('healthy')
        first = self.launch('fresh real bootstrap', healthy, ready=True, fresh=True)
        assert first.stdout.count('Installing dependencies') == 1
        metadata = self.command('actual environment identity', [healthy / '.venv/bin/python3', '-I', '-B', '-c',
            'import sys, ssl, json, importlib.metadata as m; print(json.dumps(dict(python=sys.version,prefix=sys.prefix,tls=ssl.OPENSSL_VERSION,packages=sorted((d.metadata["Name"],d.version) for d in m.distributions()))))'], healthy)
        assert metadata.returncode == 0
        self.save('environment.json', json.loads(metadata.stdout))
        bad_path = dict(self.env, PATH='/usr/bin:/bin')
        self.launch('healthy existing with Apple PATH Python', healthy, ready=True, env=bad_path)
        (healthy / 'requirements.txt').write_text('fruth-bootstrap-parent>=0.5,<2\n'
            'fruth-bootstrap-absent; sys_platform == "never-active"\n')
        self.launch('changed satisfied and inactive marker', healthy, ready=True)
        # Config/env cannot force network, local-project metadata or report writes.
        config = self.work / 'pip.conf'
        config.write_text('[global]\nfind-links = https://example.invalid\n[install]\nignore-installed = true\n')
        hostile = dict(self.env, PIP_CONFIG_FILE=str(config), PIP_FIND_LINKS='https://example.invalid',
                       PIP_REQUIREMENT=str(self.work / 'absent.txt'), PIP_TARGET=str(self.work / 'target'),
                       PIP_REPORT=str(self.work / 'report.json'), PIP_IGNORE_INSTALLED='1')
        self.launch('hostile pip settings ignored', healthy, ready=True, env=hostile)
        assert not (self.work / 'target').exists() and not (self.work / 'report.json').exists()
        for label, content in [('missing-direct', 'fruth-bootstrap-absent\n'),
                               ('incompatible-direct', 'fruth-bootstrap-parent>=9\n'),
                               ('active-marker-missing', 'fruth-bootstrap-absent; sys_platform == "darwin"\n'),
                               ('unsafe-url', 'name @ https://example.invalid/source.tar.gz\n'),
                               ('unsafe-marker-option', 'name; os_name == "posix" -r https://example.invalid/req.txt\n'),
                               ('unsafe-local', './project\n'), ('unsafe-extra', 'fruth-bootstrap-parent[extra]\n')]:
            (healthy / 'requirements.txt').write_text(content)
            self.launch(label, healthy)
        # An existing local project with a named requirement must never be built.
        project = healthy / 'fruth-bootstrap-absent'
        project.mkdir()
        (project / 'setup.py').write_text("from pathlib import Path\nPath('BUILD_HOOK_RAN').touch()\nraise RuntimeError('hook')\n")
        (healthy / 'requirements.txt').write_text('fruth-bootstrap-absent\n')
        self.launch('bare name does not build local project', healthy)
        assert not (project / 'BUILD_HOOK_RAN').exists()
        (healthy / 'requirements.txt').write_text('fruth-bootstrap-parent==1.0\n')
        self.pip(healthy, 'uninstall', '-y', 'fruth-bootstrap-leaf')
        assert 'transitive' in self.launch('missing transitive', healthy).stderr
        self.pip(healthy, 'install', 'fruth-bootstrap-leaf==2.0')
        assert 'transitive' in self.launch('incompatible transitive', healthy).stderr
        self.pip(healthy, 'install', 'fruth-bootstrap-leaf==1.0')
        self.launch('explicit disposable repair', healthy, ready=True)
        manifest = healthy / 'requirements.txt'
        manifest.unlink()
        self.launch('missing manifest existing', healthy)
        manifest.write_text('fruth-bootstrap-parent==1.0\n')
        executable = healthy / '.venv/bin/python3'
        original_link = os.readlink(executable)
        executable.unlink()
        self.launch('missing interpreter', healthy)
        executable.symlink_to('missing-base-python')
        self.launch('broken interpreter symlink', healthy)
        executable.unlink()
        executable.write_text('#!/bin/sh\nexit 87\n')
        executable.chmod(0o755)
        self.launch('executable fails to run', healthy)
        executable.unlink()
        # A shell wrapper to the base interpreter is executable but is not this venv.
        import shlex
        executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(self.python)) + ' "$@"\n')
        executable.chmod(0o755)
        self.launch('wrong interpreter prefix', healthy)
        executable.unlink()
        executable.symlink_to(original_link)
        self.launch('valid interpreter restored', healthy, ready=True)
        failed = self.checkout('failed-install', 'fruth-bootstrap-parent\nfruth-bootstrap-absent\n')
        assert 'Failed to install dependencies' in self.launch('real failed installation', failed, fresh=True).stdout
        assert (failed / '.venv').is_dir()
        self.launch('retry after real installation failure', failed)
        missing = self.checkout('missing-manifest')
        (missing / 'requirements.txt').unlink()
        self.launch('missing manifest fresh', missing)
        assert not (missing / '.venv').exists()
        unsuitable = self.checkout('unsuitable-base')
        self.launch('Apple PATH rejected before creation', unsuitable, env=bad_path)
        assert not (unsuitable / '.venv').exists()
        dangling = self.checkout('dangling-venv')
        (dangling / '.venv').symlink_to(dangling / 'absent')
        self.launch('dangling venv not recreated', dangling)
        assert (dangling / '.venv').is_symlink()
        # Independently isolate Python/TLS boundaries in the actual helper path.
        helper = healthy / 'scripts/bootstrap_preflight.py'
        original = helper.read_text()
        for label, mutation in [('synthetic old Python', 'sys.version_info = (3, 10, 0)'),
                                ('synthetic LibreSSL', 'ssl.OPENSSL_VERSION = "LibreSSL 3.0.0"'),
                                ('synthetic old OpenSSL', 'ssl.OPENSSL_VERSION_INFO = (1, 1, 0)')]:
            helper.write_text(original.replace('import tempfile\n', 'import tempfile\n' + mutation + '\n'))
            self.launch(label, healthy)
        helper.write_text(original)
        self.save('completion.json', dict(passed=True, commands=len(self.records),
            real_installation='local fixture wheels only', network='native deny network*',
            model_execution=False, production_mutation=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').exists():
        parser.error('This explicit fixture requires macOS sandbox-exec; do not run without containment.')
    fixture = Fixture(args.output.resolve(), args.python.absolute())
    try:
        fixture.run()
    except BaseException:
        import traceback
        fixture.save('failure.json', dict(error=traceback.format_exc(), commands=len(fixture.records)))
        raise
    print(json.dumps(dict(passed=True, output=str(fixture.output), commands=len(fixture.records))))


if __name__ == '__main__':
    main()
