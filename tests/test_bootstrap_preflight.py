"""Pure preflight contracts; actual pip/venv evidence uses the separate fixture."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import bootstrap_preflight as preflight


@pytest.mark.parametrize('version,tls,info,valid', [
    ((3, 11, 0), 'OpenSSL 1.1.1', (1, 1, 1), True),
    ((3, 14, 0), 'OpenSSL 4.0.3', (4, 0, 3), True),
    ((3, 10, 9), 'OpenSSL 3.0.0', (3, 0, 0), False),
    ((3, 11, 0), 'LibreSSL 3.0.0', (3, 0, 0), False),
    ((3, 11, 0), 'OpenSSL 1.1.0', (1, 1, 0), False),
])
def test_interpreter_contract(monkeypatch, version, tls, info, valid):
    monkeypatch.setattr(preflight.sys, 'version_info', version)
    monkeypatch.setattr(preflight.ssl, 'OPENSSL_VERSION', tls)
    monkeypatch.setattr(preflight.ssl, 'OPENSSL_VERSION_INFO', info)
    if valid:
        preflight.check_interpreter()
    else:
        with pytest.raises(preflight.PreflightError):
            preflight.check_interpreter()


@pytest.mark.parametrize('prefix,base,valid', [('main', 'base', True), ('backend', 'base', False), ('main', 'main', False)])
def test_selected_interpreter_belongs_to_main_venv(tmp_path, monkeypatch, prefix, base, valid):
    monkeypatch.setattr(preflight.sys, 'prefix', str(tmp_path / prefix))
    monkeypatch.setattr(preflight.sys, 'base_prefix', str(tmp_path / base))
    if valid:
        preflight.check_interpreter(tmp_path / 'main')
    else:
        with pytest.raises(preflight.PreflightError, match='does not belong'):
            preflight.check_interpreter(tmp_path / 'main')


@pytest.mark.parametrize('requirement', [
    'https://example.invalid/project.whl', 'name @ https://example.invalid/file.whl',
    './project', '/project', '../project', '-e project', '-r other.txt',
    '--find-links https://example.invalid', 'name --index-url https://example.invalid',
    'name[extra]', 'name==1 \\', '${REQUIREMENT}', 'name; os_name == "${OS}"',
    'name; os_name == "posix" --find-links /tmp', 'local.whl', 'local.tar.gz',
    'name; os_name == "posix" -r remote.txt', 'name; os_name == "posix" -e ./project',
    'local.zip', 'local.tar.bz2', 'local.tgz', 'local.tar.xz', '', '# comment only',
])
def test_unsafe_or_unsupported_manifest_fails_before_pip(tmp_path, monkeypatch, requirement):
    manifest = tmp_path / 'requirements.txt'
    manifest.write_text(requirement + '\n')
    monkeypatch.setattr(preflight.subprocess, 'run', lambda *a, **k: pytest.fail('pip executed'))
    with pytest.raises(preflight.PreflightError):
        preflight.read_requirements(manifest)


def test_named_manifest_and_platform_markers(tmp_path):
    manifest = tmp_path / 'requirements.txt'
    manifest.write_text('# comment\nRequests\nPillow>=12.3,<13 # inline\n'
                        'pyobjc-framework-Quartz ; sys_platform == "darwin"\n'
                        'name!=1.0,~=2.1\n')
    assert preflight.read_requirements(manifest) == (
        'Requests\nPillow>=12.3,<13\n'
        'pyobjc-framework-Quartz ; sys_platform == "darwin"\nname!=1.0,~=2.1\n')
    with pytest.raises(preflight.PreflightError, match='Cannot read'):
        preflight.read_requirements(tmp_path / 'missing')


@pytest.mark.parametrize('version', ['21.2.4', '22.1', 'unknown', None])
def test_missing_or_unsupported_pip_fails_without_subprocess(monkeypatch, version):
    def get_version(name):
        assert name == 'pip'
        if version is None:
            raise preflight.metadata.PackageNotFoundError(name)
        return version
    monkeypatch.setattr(preflight.metadata, 'version', get_version)
    monkeypatch.setattr(preflight.subprocess, 'run', lambda *a, **k: pytest.fail('pip executed'))
    with pytest.raises(preflight.PreflightError, match='pip >=22.2'):
        preflight.check_environment('Requests\n')


@pytest.mark.parametrize('failure', [None, 'install', 'check'])
def test_public_pip_cli_is_offline_readonly_and_checks_both_layers(monkeypatch, failure):
    monkeypatch.setattr(preflight.metadata, 'version', lambda name: '22.2')
    monkeypatch.setenv('PIP_CONFIG_FILE', '/unwanted/config')
    monkeypatch.setenv('PIP_FIND_LINKS', 'https://example.invalid')
    monkeypatch.setenv('PIP_TARGET', '/unwanted/target')
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:5] == [preflight.sys.executable, '-I', '-B', '-m', 'pip']
        assert '--isolated' in command and '--no-cache-dir' in command
        assert '--disable-pip-version-check' in command and '--no-input' in command
        assert {k: v for k, v in kwargs['env'].items() if k.startswith('PIP_')} == {'PIP_CONFIG_FILE': preflight.os.devnull}
        manifest = Path(kwargs['cwd']) / 'requirements.txt'
        assert manifest.read_text() == 'Requests\n'
        if 'install' in command:
            for option in ('--dry-run', '--no-index', '--no-deps', '--only-binary=:all:'):
                assert option in command
            assert command[-2:] == ['-r', str(manifest)]
        else:
            assert command[-1] == 'check'
        return SimpleNamespace(returncode=int(failure in command) if failure else 0,
                               stdout='missing or incompatible fixture package')

    monkeypatch.setattr(preflight.subprocess, 'run', run)
    if failure:
        with pytest.raises(preflight.PreflightError, match='missing or incompatible'):
            preflight.check_environment('Requests\n')
    else:
        preflight.check_environment('Requests\n')
    assert len(calls) == (1 if failure == 'install' else 2)
    assert not Path(calls[0][-1]).exists()
