"""Execute the public lifecycle scripts without inspecting or signaling the host."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def shell_stack(tmp_path):
    root = tmp_path / 'checkout'
    root.mkdir()
    for name in ('fruth', 'start_multi_models.sh', 'stop_multi_models.sh', 'restart.sh'):
        shutil.copy2(SOURCE_ROOT / name, root / name)
    state = root / 'fixture'
    state.mkdir()
    (state / 'ports').write_text('')
    (state / 'events').write_text('')
    (root / 'model_ports.json').write_text('[]\n')
    (root / 'scripts').mkdir()
    (root / 'scripts/startup_model_manager.py').write_text('''
import os
from pathlib import Path
assert not any('GRAPH_REBASE_OPERATOR' in key for key in os.environ)
assert input() == ''
with Path('fixture/events').open('a') as stream:
    stream.write('model selection empty\\n')
raise SystemExit(int(os.environ.get('FIXTURE_MODEL_EXIT', '0')))
''')
    for package in ('fruth_core', 'fruth_runtime'):
        (root / package).mkdir()
        (root / package / '__init__.py').write_text('')
    (root / 'fruth_core/status.py').write_text(
        "from pathlib import Path\nDEFAULT_RUNTIME_STATUS_PATH = Path('state/runtime_status.json')\n"
    )
    (root / 'fruth_runtime/runtime_hygiene.py').write_text('''
from pathlib import Path
def finalize_runtime_shutdown(**kwargs):
    assert kwargs == dict(registry_path=Path('model_ports.json'),
                         status_path=Path('state/runtime_status.json'),
                         log_dir=Path('logs'), sync_external=False, preserve_agents=True)
    with Path('fixture/events').open('a') as stream:
        stream.write('shutdown hygiene\\n')
    return {'runtime_status_count': 0, 'archived_count': 0}
''')
    (root / 'fruth_runtime/runtime_log_hygiene.py').write_text('''
import os
from pathlib import Path
def prepare_clean_global_log(path, *, metadata):
    assert not any('GRAPH_REBASE_OPERATOR' in key for key in os.environ)
    assert path == Path('logs/flask_webserver.log')
    assert metadata == {'service': 'flask_webserver', 'port': 5011}
    with Path('fixture/events').open('a') as stream:
        stream.write('prepare web log\\n')
''')
    (root / 'fruth_webserver.py').write_text('''
import os
from pathlib import Path
assert os.environ.get('FRUTH_GRAPH_REBASE_OPERATOR_TOKEN') == 'dummy-startup-token'
assert os.environ.get('FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY') == 'dummy-startup-operator'
assert 'GRAPH_REBASE_OPERATOR_TOKEN' not in os.environ
assert 'GRAPH_REBASE_OPERATOR_IDENTITY' not in os.environ
state = Path('fixture')
with (state / 'events').open('a') as stream:
    stream.write('web start\\n')
if os.environ.get('FIXTURE_WEB_FAIL') != '1':
    (state / 'known-81009').touch()
    (state / 'live-81009').touch()
    with (state / 'ports').open('a') as stream:
        stream.write('5011 81009 python\\n')
(state / 'web-done').touch()
''')
    venv = root / '.venv/bin'
    venv.mkdir(parents=True)
    python = venv / 'python3'
    python.write_text(
        '#!/bin/bash\n'
        'if [[ "$1" == "-" && "$2" == "5011" ]]; then\n'
        '  cat >/dev/null\n'
        '  printf "probe 5011\\n" >> "$FIXTURE_STATE/events"\n'
        '  lsof -iTCP:5011 -sTCP:LISTEN -t >/dev/null\n'
        '  exit $?\n'
        'fi\n'
        f'exec {shlex.quote(sys.executable)} "$@"\n'
    )
    python.chmod(0o755)
    (venv / 'activate').write_text(f'export PATH={shlex.quote(str(venv))}:"$PATH"\n')
    hooks = state / 'shell-hooks'
    hooks.write_text(r'''
lsof() {
    local arg selection='' port pid command found=1
    for arg in "$@"; do
        [[ "$arg" == -iTCP:* ]] && selection="${arg#-iTCP:}"
    done
    while read -r port pid command; do
        [[ -f "$FIXTURE_STATE/live-$pid" ]] || continue
        if [[ -n "$selection" ]]; then
            if [[ "$selection" == *-* ]]; then
                (( port >= ${selection%-*} && port <= ${selection#*-} )) || continue
            else
                [[ "$port" == "$selection" ]] || continue
            fi
        fi
        found=0
        if [[ " $* " == *' -t '* ]]; then
            printf '%s\n' "$pid"
        else
            printf '%s %s TCP 127.0.0.1:%s (LISTEN)\n' "$command" "$pid" "$port"
        fi
    done < "$FIXTURE_STATE/ports"
    # lsof can emit matching listeners and still return 1 for unmatched selectors.
    [[ "${FIXTURE_PARTIAL_LSOF:-0}" == 1 && "$selection" != 5011 ]] && return 1
    return "$found"
}
pgrep() {
    [[ "$*" == '-f fruth_webserver.py' ]] || return 75
    [[ -f "$FIXTURE_STATE/live-81001" ]] || return 1
    printf '81001\n'
}
ps() {
    if [[ "$1" == '-p' ]]; then
        [[ -f "$FIXTURE_STATE/live-$2" ]]
    else
        return 0
    fi
}
kill() {
    local signal=TERM pid
    if [[ "$1" == '-9' ]]; then signal=KILL; shift; fi
    for pid in "$@"; do
        [[ -f "$FIXTURE_STATE/known-$pid" ]] || return 75
        printf 'kill %s %s\n' "$signal" "$pid" >> "$FIXTURE_STATE/events"
        if [[ "$signal" == KILL || ! -f "$FIXTURE_STATE/stubborn-$pid" ]]; then
            rm -f "$FIXTURE_STATE/live-$pid"
        fi
    done
}
sleep() {
    if [[ "$1" == 2 ]]; then
        local attempt
        for ((attempt=0; attempt<100; attempt++)); do
            [[ -f "$FIXTURE_STATE/web-done" ]] && return 0
            /bin/sleep 0.02
        done
        return 1
    fi
}
brew() { printf 'ollama none\n'; }
jq() {
    if [[ "$2" == *pid* && -f "$FIXTURE_STATE/registered-pids" ]]; then
        cat "$FIXTURE_STATE/registered-pids"
    fi
    return 0
}
open() { printf 'open %s\n' "$1" >> "$FIXTURE_STATE/events"; }
''')
    env = {key: value for key, value in os.environ.items()
           if key not in {'PYTHONPATH', 'PYTHONHOME', 'BASH_ENV'} and not key.startswith('FRUTH_')}
    env.update({
        'BASH_ENV': str(hooks),
        'FIXTURE_STATE': str(state),
        'PATH': f'{venv}:' + os.environ['PATH'],
        'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN': 'dummy-startup-token',
        'FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY': 'dummy-startup-operator',
        'GRAPH_REBASE_OPERATOR_TOKEN': 'dummy-inherited-internal-token',
        'GRAPH_REBASE_OPERATOR_IDENTITY': 'dummy-inherited-internal-operator',
    })

    def listener(port, pid, command='ollama', *, stubborn=False):
        (state / f'known-{pid}').touch()
        (state / f'live-{pid}').touch()
        if stubborn:
            (state / f'stubborn-{pid}').touch()
        with (state / 'ports').open('a') as stream:
            stream.write(f'{port} {pid} {command}\n')

    def run(command, **overrides):
        return subprocess.run(
            [str(root / 'fruth'), command], cwd=tmp_path, env={**env, **overrides},
            input='\n', text=True, capture_output=True, timeout=15,
        )

    return SimpleNamespace(root=root, state=state, listener=listener, run=run,
                           events=lambda: (state / 'events').read_text().splitlines())


@pytest.mark.parametrize('command', ['stop', 'shutdown', 'down'])
def test_stop_already_stopped_is_success(shell_stack, command):
    result = shell_stack.run(command)
    assert result.returncode == 0, result.stderr
    assert 'No running runtime server processes found to stop.' in result.stdout
    assert shell_stack.events() == ['shutdown hygiene']


@pytest.mark.parametrize('partial_lsof', ['0', '1'])
def test_stop_finds_default_server_without_registry_entries(shell_stack, partial_lsof):
    shell_stack.listener(11434, 81002)
    result = shell_stack.run('stop', FIXTURE_PARTIAL_LSOF=partial_lsof)
    assert result.returncode == 0, result.stderr
    assert shell_stack.events() == ['kill TERM 81002', 'shutdown hygiene']
    assert not (shell_stack.state / 'live-81002').exists()


def test_stop_webserver_then_all_backend_ranges_and_registered_pid(shell_stack):
    for port, pid in [(5011, 81001), (11434, 81002), (11435, 81003),
                      (11501, 81004), (11551, 81005), (12000, 81006)]:
        shell_stack.listener(port, pid, stubborn=pid in {81001, 81004})
    (shell_stack.state / 'registered-pids').write_text('81003\n81006\n81007\n')
    result = shell_stack.run('stop')
    assert result.returncode == 0, result.stderr
    events = shell_stack.events()
    assert events[:2] == ['kill TERM 81001', 'kill KILL 81001']
    assert events[-1] == 'shutdown hygiene'
    for pid in range(81001, 81007):
        assert events.count(f'kill TERM {pid}') == 1
        assert not (shell_stack.state / f'live-{pid}').exists()
    assert 'kill KILL 81004' in events
    assert not any('81007' in event for event in events)


@pytest.mark.parametrize('initial', ['stopped', 'default_only', 'running'])
def test_restart_runs_stop_then_start_even_with_no_models(shell_stack, initial):
    if initial != 'stopped':
        shell_stack.listener(11434, 81002)
    if initial == 'running':
        shell_stack.listener(5011, 81001, 'python')
        shell_stack.listener(11435, 81003)
    result = shell_stack.run('restart', FIXTURE_PARTIAL_LSOF='1')
    assert result.returncode == 0, result.stdout + result.stderr
    events = shell_stack.events()
    assert events[-6:] == ['shutdown hygiene', 'model selection empty', 'prepare web log',
                          'web start', 'probe 5011', 'open http://127.0.0.1:5011']
    assert 'Startup complete' in result.stdout
    assert 'Aborting restart' not in result.stdout


def test_start_reuses_existing_webserver_after_model_selection(shell_stack):
    shell_stack.listener(5011, 81001, 'python')
    result = shell_stack.run('start')
    assert result.returncode == 0, result.stderr
    assert 'already running on port 5011' in result.stdout
    assert shell_stack.events() == ['model selection empty']


@pytest.mark.parametrize('failure', ['model', 'web'])
def test_restart_keeps_original_abort_on_actual_start_failure(shell_stack, failure):
    overrides = {'FIXTURE_MODEL_EXIT': '23'} if failure == 'model' else {'FIXTURE_WEB_FAIL': '1'}
    result = shell_stack.run('restart', **overrides)
    assert result.returncode == 1, result.stdout + result.stderr
    assert 'start_multi_models.sh failed. Aborting restart.' in result.stdout
    assert not any(event.startswith('open ') for event in shell_stack.events())


def test_restart_keeps_original_abort_on_stop_script_failure(shell_stack):
    (shell_stack.root / 'stop_multi_models.sh').write_text('exit 23\n')
    result = shell_stack.run('restart')
    assert result.returncode == 1
    assert 'stop_multi_models.sh failed. Aborting restart.' in result.stdout
    assert shell_stack.events() == []


def test_status_observes_webserver_started_without_a_process_record(shell_stack):
    shell_stack.listener(5011, 81001, 'python')
    shell_stack.listener(11434, 81002)
    result = shell_stack.run('status')
    assert result.returncode == 0, result.stderr
    assert 'webserver (5011): running (pid 81001)' in result.stdout
    assert 'ollama default (11434): running (pid 81002)' in result.stdout
    assert not (shell_stack.root / 'state/control_plane.json').exists()


def test_removed_launcher_is_not_advertised_or_executable(shell_stack):
    help_result = shell_stack.run('help')
    assert help_result.returncode == 0
    assert 'control-plane' not in help_result.stdout
    result = shell_stack.run('control-plane')
    assert result.returncode == 2
    assert "unknown command 'control-plane'" in result.stdout + result.stderr
    assert shell_stack.events() == []
