"""Narrow maintained-test subprocess routes; native containment is macOS Seatbelt.

This is a trusted-test harness, not a security boundary against Python tests that
modify the harness itself. Audit hooks do not propagate into native children.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import textwrap
import time
import threading

NODE_MODULES = frozenset(('test_frontend_apple_fm.py', 'test_frontend_apple_pcc.py',
    'test_frontend_codex_target.py', 'test_frontend_external_multifile_transport.py',
    'test_frontend_reference_selection.py', 'test_frontend_message_state.py', 'test_landing_routes.py'))
SHELL_MODULES = frozenset(('test_stack_shutdown.py', 'test_clean_repo_state_policy.py',
                         'test_cleanup_target_inventory.py'))
CLI_MODULES = frozenset(('test_operator_scripts.py', 'test_self_learning.py',
    'test_response_frames.py', 'test_graph_rebase_readiness_registry.py',
    'test_fruth_run_monitor_projection.py', 'test_runtime_contract_knobs.py',
    'test_cleanup_target_inventory.py', 'test_landing_routes.py', 'test_self_attack.py'))
CLI_SCRIPTS = {
    'test_response_frames.py': {'attest_response_frame_index.py'},
    'test_graph_rebase_readiness_registry.py': {'sync_graph_rebase_readiness_registry.py'},
    'test_fruth_run_monitor_projection.py': {'fruth_run_monitor.py'},
    'test_cleanup_target_inventory.py': {'fruthctl.py'},
    'test_operator_scripts.py': {'sync_model_providers.py', 'cleanup_model_providers.py', 'unsync_model_providers.py'},
    'test_self_learning.py': {'manage_self_learning_policy.py', 'build_self_learning_eval_cases.py'},
}
# These tools implement the already-maintained disposable shell fixtures. No PATH
# directory, arbitrary installed binary, package manager, fm or shortcuts is admitted.
SHELL_TOOLS = ('/bin/bash', '/bin/sh', '/bin/cat', '/bin/cp', '/bin/date', '/bin/echo',
    '/bin/mkdir', '/bin/mv', '/bin/rm', '/bin/sleep', '/bin/ls', '/usr/bin/basename',
    '/usr/bin/dirname', '/usr/bin/env', '/usr/bin/find', '/usr/bin/grep', '/usr/bin/head',
    '/usr/bin/sed', '/usr/bin/sort', '/usr/bin/tail', '/usr/bin/tr', '/usr/bin/uname',
    '/usr/bin/nohup', '/usr/bin/seq', '/usr/bin/wc', '/usr/bin/touch', '/usr/bin/awk', '/usr/bin/readlink')
CHILD_SECONDS = 30  # external per-child watchdog, in addition to the job deadline


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def node_programs(source, module):
    """Only literal programs in the selected, hashed maintained module.

    The reference-selection helper wraps a literal body; AFM has four fixed
    metadata values. No arbitrary interpolation, eval of Python, or regex holes.
    """
    tree = ast.parse((source / 'tests' / module).read_text())
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    programs = {v for v in literals if '\n' in v and ('require(' in v or v.startswith('import json,os,pathlib,'))}
    for value in literals:
        if 'METADATA_SOURCE' in value:
            programs.update(value.replace('METADATA_SOURCE', json.dumps(v))
                            for v in ('missing', 'catalog', 'instance', 'unavailable'))
    if module == 'test_frontend_reference_selection.py':
        wrappers = [n for n in ast.walk(tree) if isinstance(n, ast.BinOp)
                    and isinstance(n.op, ast.Add) and isinstance(n.left, ast.BinOp)
                    and isinstance(n.left.left, ast.Constant) and isinstance(n.left.right, ast.Name)
                    and n.left.right.id == 'body' and isinstance(n.right, ast.Constant)]
        for node in wrappers:
            programs.update(node.left.left.value + body + node.right.value for body in literals)
    return programs | {textwrap.dedent(p) for p in programs}


def native_profile(*, reads, writes, executables, observe=False):
    q = json.dumps
    lines = ['(version 1)', '(deny default)', '(allow process-fork sysctl-read)',
             '(allow signal (target same-sandbox))',
             '(allow file-read-metadata)',
             '(allow file-read* (literal "/"))',
             '(allow file-map-executable)',
             '(allow file-read* (subpath "/System") (subpath "/usr/lib") '
             '(subpath "/Library/Apple") (literal "/dev/null") (literal "/dev/urandom") '
             '(literal "/dev/random"))',
             '(allow file-read* file-write* (subpath "/dev/fd"))',
             '(allow file-write* (literal "/dev/null"))']
    for path in reads:
        lines.append(f'(allow file-read* (subpath {q(str(path))}))')
    for path in writes:
        lines.append(f'(allow file-read* file-write* (subpath {q(str(path))}))')
    for path in executables:
        lines.append(f'(allow process-exec* file-read* (literal {q(str(path))}))')
    if observe:
        lines.append('(allow process-info*)')  # only exact owned-PID ps argv is admitted
    return '\n'.join(lines) + '\n'


class ProcessRoutes:
    def __init__(self, *, source, work, environment, manifest):
        self.source, self.work = Path(source), Path(work)
        self.environment = dict(environment)
        self.manifest = dict(manifest)
        self.active = None
        self.pending = None
        self.children = {}
        self.events = []
        self.original = subprocess.Popen
        self.node = shutil.which('node', path=environment.get('PATH'))
        self.python = str(Path(sys.executable).resolve())
        self.programs = {m: node_programs(self.source, m) for m in NODE_MODULES
                         if (self.source / 'tests' / m).is_file()}
        self.binary_hashes = {}
        self.journal = work / 'processes.jsonl'
        self.deadlines = {}

    def record(self, event, **fields):
        row = dict(event=event, epoch=time.time(), nodeid=self.active, **fields)
        self.events.append(row)
        with self.journal.open('a') as stream:
            stream.write(json.dumps(row, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    def temporary(self, value):
        path = Path(value)
        if not path.is_absolute() or path != path.resolve() or not path.is_relative_to(self.work / 'temporary'):
            raise PermissionError('Process route requires a physical phase temporary path')
        return path

    def source_file(self, path):
        path = Path(path)
        if not path.is_absolute() or path != path.resolve():
            raise PermissionError('Source path is not physical and absolute')
        rel = str(path.relative_to(self.source))
        if self.manifest.get(rel) != digest(path):
            raise PermissionError('Process route source identity changed')
        return path

    def environment_for(self, supplied, module):
        baseline = dict(self.environment)
        for key in ('PYTEST_CURRENT_TEST', 'PYTEST_VERSION', 'FRUTH_LINEAGE_CONTEXT'):
            if key in os.environ:
                baseline[key] = os.environ[key]
        env = dict(os.environ if supplied is None else supplied)
        # Explicit minimal dry-run environment is itself a maintained contract.
        if module == 'test_landing_routes.py' and env == {'PATH': '/usr/bin:/bin', 'FRUTH_DRY_RUN_OPEN': '1'}:
            return dict(env, HOME=str(self.work / 'temporary'), TMPDIR=str(self.work / 'temporary'))
        allowed = {}
        if env.get('PYTEST_CURRENT_TEST') in {self.active + ' (setup)', self.active + ' (call)'}:
            allowed['PYTEST_CURRENT_TEST'] = env['PYTEST_CURRENT_TEST']
        if module in SHELL_MODULES:
            for key in ('BASH_ENV', 'FIXTURE_STATE', 'READINESS_ARGS_FILE', 'CHROME_ARGS_FILE'):
                if key in env:
                    allowed[key] = str(self.temporary(env[key]))
            for key, choices in {'FIXTURE_PARTIAL_LSOF': {'0','1'}, 'FIXTURE_MODEL_EXIT': {'23'},
                                 'FIXTURE_WEB_FAIL': {'1'}, 'FIXTURE_PIP_EXIT': {'0','23'}}.items():
                if key in env and env[key] in choices:
                    allowed[key] = env[key]
            # Fixture PATH additions must be physical disposable bin directories.
            parts = env.get('PATH', '').split(os.pathsep)
            base = baseline.get('PATH', '').split(os.pathsep)
            if len(parts) > len(base) and parts[-len(base):] == base:
                for p in parts[:-len(base)]: self.temporary(p)
                allowed['PATH'] = env['PATH']
            for key, value in {'FRUTH_GRAPH_REBASE_OPERATOR_TOKEN':'dummy-startup-token',
                'FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY':'dummy-startup-operator',
                'GRAPH_REBASE_OPERATOR_TOKEN':'dummy-inherited-internal-token',
                'GRAPH_REBASE_OPERATOR_IDENTITY':'dummy-inherited-internal-operator'}.items():
                if env.get(key) == value: allowed[key] = value
            # shell_stack deliberately removes all FRUTH context from the child.
            if module == 'test_stack_shutdown.py':
                baseline = {k:v for k,v in baseline.items() if not k.startswith('FRUTH_')}
        if module == 'test_cleanup_target_inventory.py' and 'PYTHONPATH' in env:
            allowed['PYTHONPATH'] = str(self.source)
        if module == 'test_operator_scripts.py':
            if 'HOME' in env: allowed['HOME'] = str(self.temporary(env['HOME']))
            allowed['FRUTH_WEB_BASE'] = 'http://127.0.0.1:9'
        if module == 'test_runtime_contract_knobs.py':
            allowed.update(PYTHONPATH='.', FRUTH_MULTI_MATERIALIZATION_MAX_PARALLEL_WORKERS='2')
        if module == 'test_child_process_env.py':
            allowed.update(FRUTH_GRAPH_REBASE_OPERATOR_TOKEN='canonical-token',
                FRUTH_GRAPH_REBASE_OPERATOR_IDENTITY='canonical-identity',
                GRAPH_REBASE_OPERATOR_TOKEN='preexported-token', GRAPH_REBASE_OPERATOR_IDENTITY='preexported-identity')
        if module == 'test_codex_execution.py':
            for key in ('FAKE_CODEX_CALL_LOG', 'FAKE_CODEX_STATUS_COUNTER',
                        'FAKE_CODEX_EXEC_CAPTURE', 'CODEX_HOME', 'FRUTH_CODEX_EXECUTABLE'):
                if key in env:
                    allowed[key] = str(self.temporary(env[key]))
            choices = {
                'FAKE_CODEX_MODE': {'success', 'auth_required', 'status_error',
                    'exec_timeout', 'exec_fail', 'exec_loud_fail', 'exec_empty',
                    'exec_large', 'exec_warning'},
                'FAKE_CODEX_OUTPUT': {'safe final text'},
                'OPENAI_API_KEY': {'preserved-auth-mechanism', 'sk-super-secret-value'},
            }
            for key, values in choices.items():
                if env.get(key) in values:
                    allowed[key] = env[key]
            if env.get('PATH') != baseline.get('PATH'):
                allowed['PATH'] = str(self.temporary(env['PATH']))
        if module == 'test_native_process_routes.py' and supplied is not None and env.get('LC_ALL') == env.get('LANG') == 'C':
            # Capture's production owner pins locale and strips these dummy secrets.
            allowed.update(LC_ALL='C', LANG='C')
        expected = dict(baseline, **allowed)
        if env != expected:
            raise PermissionError('Process route environment mismatch: ' + ','.join(sorted(
                k for k in set(env) | set(expected) if env.get(k) != expected.get(k))))
        env.setdefault('HOME', str(self.work / 'temporary'))
        return env

    def classify(self, argv, cwd, supplied_env):
        if not self.active or not isinstance(argv, (list, tuple)) or not all(isinstance(a, str) for a in argv):
            raise PermissionError('No maintained process route')
        module = self.active.split('::')[0].split('/')[-1]
        self.source_file(self.source / 'tests' / module)
        cwd = Path(cwd or os.getcwd()).absolute()
        if cwd != self.source: self.temporary(cwd)
        env = self.environment_for(supplied_env, module)
        command = list(argv)
        executables = []
        fixture = None
        route = None
        if module == 'test_codex_execution.py':
            executable = self.temporary(argv[0])
            self.codex_fixture(executable)
            self.temporary(cwd)
            args = list(argv[1:])
            prefix = ['exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
                      '--skip-git-repo-check', '--sandbox', 'read-only', '--color',
                      'never', '--output-last-message', str(cwd / 'last-message.txt')]
            if args not in (['--version'], ['login', 'status']):
                if args[:len(prefix)] != prefix or args[-1:] != ['-']:
                    raise PermissionError('Fake Codex arguments differ from the bridge contract')
                images = args[len(prefix):-1]
                if len(images) % 2:
                    raise PermissionError('Fake Codex image arguments differ')
                for flag, image in zip(images[::2], images[1::2]):
                    import re
                    if (flag != '--image' or not re.fullmatch(r'inputs/input-0[1-5]\.(bmp|gif|jpeg|jpg|png|tif|tiff|webp)', image)
                            or not self.temporary(cwd / image).is_file()):
                        raise PermissionError('Fake Codex image path is not a staged input')
            route = 'codex-fixture'
            executables.extend([sys.executable, self.python,
                str(Path(sys.base_prefix).resolve() / 'Resources/Python.app/Contents/MacOS/Python')])
        elif module in NODE_MODULES and len(argv) in (3,4) and argv[:2] == ['node','-e']:
            if cwd != self.source or argv[2] not in self.programs[module] or not self.node:
                raise PermissionError('Unrecognized maintained Node program/cwd')
            if len(argv) == 4:
                if module != 'test_frontend_reference_selection.py' or not isinstance(json.loads(argv[3]), dict):
                    raise PermissionError('Unexpected Node fixture arguments')
            command[0] = str(Path(self.node).resolve()); route = 'node'
            env['OPENSSL_CONF'] = '/dev/null'
        elif module == 'test_native_process_routes.py' and argv == ['/bin/sleep', '30']:
            route = 'owned-sleep'
        elif module == 'test_native_process_routes.py' and len(argv) == 8 and argv[:3] == ['ps','-ww','-p'] and argv[4:] == ['-o','lstart=','-o','command=']:
            child = self.children.get(int(argv[3]))
            if child is None or child.poll() is not None or getattr(child, '_route', None) != 'owned-sleep':
                raise PermissionError('ps target is not a live owned disposable process')
            command[0] = '/bin/ps'; route = 'owned-ps'
        elif (module == 'test_native_process_routes.py' and len(argv) == 5
              and argv[:2] == [sys.executable, '-c']):
            programs = node_programs(self.source, module)
            if argv[2] not in programs or argv[3] != str(self.work.parent / 'native-outside-canary'):
                raise PermissionError('Native rejection program/path differs')
            child = self.children.get(int(argv[4]))
            if child is None or child.poll() is not None or getattr(child, '_route', None) != 'owned-sleep':
                raise PermissionError('Rejection control target is not owned')
            route = 'native-rejections'
        elif module in SHELL_MODULES and argv[0] != sys.executable:
            script = Path(argv[1]) if argv[0] in ('bash','/bin/bash') and len(argv)>1 else Path(argv[0])
            self.temporary(script)
            if script.name not in ('fruth','clean_repo_state.sh'):
                raise PermissionError('Unsupported fixture entrypoint')
            args = argv[2:] if argv[0] in ('bash','/bin/bash') else argv[1:]
            words = {'clean','reset-state','archiv','archive','--archive','--full','--forget-inference',
                     '--dry-run','--empty-state','--archiv','--reset-chrome-file-access-prompt','--reset-registry','--reset-llama-catalog'}
            if module == 'test_stack_shutdown.py':
                words = {'start','stop','shutdown','down','restart','status','help','control-plane'}
                if len(args) != 1: raise PermissionError('Unexpected lifecycle fixture arguments')
            if any(a not in words for a in args): raise PermissionError('Unsupported shell arguments')
            # Entrypoint must be an unmodified staged owner. Deliberately altered
            # stop script and fake modules remain contained fixture dependencies.
            if digest(script) != self.manifest.get(script.name):
                raise PermissionError('Fixture entrypoint differs from staged source')
            fixture = script.parent.parent
            self.temporary(fixture)
            if module == 'test_stack_shutdown.py':
                if env.get('BASH_ENV') != str(script.parent / 'fixture/shell-hooks') or env.get('FIXTURE_STATE') != str(script.parent / 'fixture'):
                    raise PermissionError('Lifecycle hooks/state do not belong to fixture')
                tree = ast.parse((self.source / 'tests/test_stack_shutdown.py').read_text())
                strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                base = next(v for v in strings if v.startswith('\nlsof()'))
                extra = next(v for v in strings if v.startswith('\npython3()'))
                if Path(env['BASH_ENV']).read_text() not in {base, base + extra}:
                    raise PermissionError('Lifecycle hooks differ from maintained fixture')
            command = ['/bin/bash', str(script), *args]; route = 'shell-fixture'
            if module == 'test_stack_shutdown.py':
                executables.append(str(script.parent / '.venv/bin/python3'))
            executables.extend(SHELL_TOOLS)
        elif module == 'test_child_process_env.py' and len(argv) == 4 and argv[:2] == ['/bin/bash','-c']:
            startup = self.source_file(self.source / 'start_multi_models.sh')
            prefix = startup.read_text().partition(': "${FRUTH_MULTI_MATERIALIZATION_MAX_PARALLEL_WORKERS:=4}"')[0]
            expected = prefix + "\nprintf 'CAPTURED:%s|%s\\n' " + '"$GRAPH_REBASE_OPERATOR_TOKEN" "$GRAPH_REBASE_OPERATOR_IDENTITY"\n' + 'env\n'
            if argv[2:] != [expected, str(startup)] or cwd != self.source:
                raise PermissionError('Startup capture program differs')
            route = 'shell-capture'; executables.extend(SHELL_TOOLS)
        elif module == 'test_landing_routes.py' and argv[0] == str(self.source / 'fruth') and argv[1:] in (['dashboard'], ['version'], ['--version']):
            if cwd != self.source: raise PermissionError('CLI cwd differs')
            self.source_file(argv[0]); command = ['/bin/bash', *argv]; route = 'shell-display'; executables.extend(SHELL_TOOLS)
            # Bash may create here-document backing files in cwd. Public display
            # commands resolve their owner from argv, so keep cwd disposable.
            cwd = self.work / 'temporary'
        elif module in CLI_MODULES and argv[0] == sys.executable and len(argv)>=2:
            if argv[1] == '-c':
                code = argv[2]
                fixed = {'test_landing_routes.py': 'from fruth_core.version import __version__; print(f"Fruth {__version__}")',
                         'test_runtime_contract_knobs.py': 'import fruth_webserver; print(fruth_webserver._MULTI_MATERIALIZATION_RUNTIME.max_parallel_workers)'}
                if module == 'test_self_attack.py' and self.active.endswith('::test_hard_deadline_kills_diagnostic_subprocess_without_waiting_for_its_own_timeout'):
                    prefix = 'import pathlib,time; time.sleep(.6); pathlib.Path('
                    suffix = ').touch()'
                    if not code.startswith(prefix) or not code.endswith(suffix):
                        raise PermissionError('Unknown deadline fixture program')
                    marker = ast.literal_eval(code[len(prefix):-len(suffix)])
                    if self.temporary(marker).name != 'child-survived':
                        raise PermissionError('Deadline fixture output differs')
                    fixed[module] = code
                if len(argv) != 3 or code != fixed.get(module):
                    raise PermissionError('Unknown Python inline program')
            else:
                script = Path(argv[1]); script = script if script.is_absolute() else cwd / script
                if script.name not in CLI_SCRIPTS.get(module, set()): raise PermissionError('Unknown owner CLI')
                if module == 'test_operator_scripts.py':
                    self.temporary(script)
                    if digest(script) != self.manifest.get('scripts/' + script.name): raise PermissionError('Copied owner drift')
                    fixture = script.parent.parent.parent
                else: self.source_file(script)
                self.cli_arguments(module, script.name, argv[2:])
            route = 'python-cli'
        if route is None:
            raise PermissionError('No exact maintained subprocess route for ' + module)
        executables.append(command[0])
        if command[0] == sys.executable or route.startswith('shell'):
            executables.extend([self.python, str(Path(sys.base_prefix).resolve() / 'Resources/Python.app/Contents/MacOS/Python')])
        if route.startswith('shell'):
            executables.extend([sys.executable, self.python])
            # Shell uses python3 through PATH; pin it to the runner interpreter.
            bindir = self.work / 'python-bin'
            bindir.mkdir(exist_ok=True)
            shim = bindir / 'python3'
            if not shim.exists():
                shim.write_text('#!/bin/sh\nexec ' + __import__('shlex').quote(sys.executable) + ' "$@"\n')
                shim.chmod(0o755)
            executables.append(str(shim))
            env['PATH'] = str(bindir) + os.pathsep + env.get('PATH','')
        snapshot = {str(command[0]): digest(command[0])} if route == 'codex-fixture' else {}
        if fixture:
            # Capture all fixture bytes, reject symlink escapes, and allow exec
            # only existing executable scripts in this one disposable fixture.
            for p in fixture.rglob('*'):
                if p.is_symlink(): raise PermissionError('Fixture symlink is not admitted')
                if p.is_file():
                    snapshot[str(p)] = digest(p)
                    if os.access(p, os.X_OK) and p.suffix != '.py':
                        self.fixture_executable(p, module)
                        executables.append(str(p))
        return route, command, cwd, env, executables, snapshot

    def codex_fixture(self, path):
        """Only the exact disposable script from the selected, hashed test owner."""
        source = self.source_file(self.source / 'tests/test_codex_execution.py')
        tree = ast.parse(source.read_text())
        body = next(n.value.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'FAKE_CODEX_SOURCE' for t in n.targets)
                    and isinstance(n.value, ast.Constant))
        if (not path.is_file() or not os.access(path, os.X_OK)
                or path.read_text() != f'#!{sys.executable}\n{body}'):
            raise PermissionError('Executable differs from maintained fake Codex')

    def validate_launch_options(self, route, positional, kw):
        allowed = {'stdin', 'stdout', 'stderr', 'bufsize', 'text', 'encoding', 'errors',
                   'universal_newlines', 'cwd', 'env', 'close_fds'}
        # The real bridge owns a session for timeout cancellation. Only this exact
        # non-spawning, finite fake may leave the worker group; never a general opt-in.
        if route == 'codex-fixture' and kw.get('start_new_session') is True:
            allowed.add('start_new_session')
        if positional or set(kw) - allowed:
            raise PermissionError('Unsupported process launch options')
        if route == 'codex-fixture' and kw.get('start_new_session') is not True:
            raise PermissionError('Fake Codex requires the production new-session contract')

    def fixture_executable(self, path, module):
        body = path.read_text()
        if path.name in {'fruth','start_multi_models.sh','stop_multi_models.sh','restart.sh','clean_repo_state.sh'}:
            if digest(path) == self.manifest.get(path.name) or body in {'#!/bin/sh\nexit 0\n','exit 23\n'}:
                return
        if path.name in {'lsof','uname','tccutil','pip3'}:
            literals = set()
            for name in ('test_stack_shutdown.py','test_clean_repo_state_policy.py','test_cleanup_target_inventory.py'):
                tree = ast.parse((self.source / 'tests' / name).read_text())
                literals.update(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value,str))
            if body in literals and body.startswith('#!'):
                return
        if path.name == 'python3' and module == 'test_stack_shutdown.py':
            tree = ast.parse((self.source / 'tests/test_stack_shutdown.py').read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.JoinedStr):
                    values = []
                    for value in node.values:
                        if isinstance(value, ast.Constant): values.append(value.value)
                        elif ast.unparse(value.value) == 'shlex.quote(sys.executable)': values.append(shlex.quote(sys.executable))
                        else: break
                    else:
                        if body == ''.join(values) and body.startswith('#!/bin/bash'):
                            return
        # Copied Python owner files may retain executable mode; their interpreter
        # invocation remains inside the same fixture sandbox and source binding.
        if path.suffix == '.py' and digest(path) == self.manifest.get('scripts/' + path.name):
            return
        raise PermissionError('Unrecognized executable fixture: ' + str(path))

    def cli_arguments(self, module, script, args):
        if script in {'sync_model_providers.py','cleanup_model_providers.py','unsync_model_providers.py'}:
            if args: raise PermissionError('Operator entrypoint arguments')
            return
        if script == 'fruth_run_monitor.py':
            if args != ['--help']: raise PermissionError('Monitor may only show help')
            return
        if script == 'fruthctl.py':
            if args != ['inference','--reset-learning-state','--json']: raise PermissionError('Fixture reset arguments')
            return
        paths = {'--frames-dir','--response-frames-dir','--registry','--snapshot','--report','--frames',
                 '--graph-rebase-corpus-dir','--self-learning-dir','--output','--accepted-policy'}
        flags = {'--check-only','--require-all-settled','--shell-summary','--progress','--no-persist','--merge-existing'}
        values = {'--frame-limit': {'1','20'}, '--max-cases': {'1','100'}, '--reviewer': {'test'},
                  '--note': {'cli promote test'}, '--reason': {'cli enable test'}}
        if script == 'attest_response_frame_index.py':
            if len(args) != 2 or args[0] != '--frames-dir': raise PermissionError('Attestation arguments')
        elif script == 'sync_graph_rebase_readiness_registry.py':
            if len(args) != 8 or args[::2][:2] != ['--response-frames-dir','--registry'] or args[4:] != ['--check-only','--require-all-settled','--shell-summary','--progress']:
                raise PermissionError('Readiness arguments')
        elif script not in {'manage_self_learning_policy.py','build_self_learning_eval_cases.py'}:
            raise PermissionError('Unknown CLI schema')
        shape = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in paths:
                self.temporary(args[i+1]); shape.extend([arg, '<path>']); i += 2
            elif arg in flags or (script == 'manage_self_learning_policy.py' and arg in {'init','promote','enable'}): shape.append(arg); i += 1
            elif arg in values and args[i+1] in values[arg]: shape.extend(args[i:i+2]); i += 2
            elif arg == '--candidate-id' and script == 'manage_self_learning_policy.py' and __import__('re').fullmatch(r'[A-Za-z0-9_.:-]+', args[i+1]): shape.extend([arg, '<id>']); i += 2
            else: raise PermissionError('Unsupported CLI argument: ' + arg)
        if script == 'manage_self_learning_policy.py':
            patterns = [
                ['--snapshot','<path>','init'],
                ['--snapshot','<path>','promote','--report','<path>','--candidate-id','<id>','--reviewer','test','--note','cli promote test'],
                ['--snapshot','<path>','enable','--reviewer','test','--reason','cli enable test']]
            if shape not in patterns: raise PermissionError('Policy CLI shape differs')
        if script == 'build_self_learning_eval_cases.py':
            frames = ['--frames','<path>']
            corpus = ['--graph-rebase-corpus-dir','<path>','--self-learning-dir','<path>']
            outputs = ['--output','<path>','--report','<path>','--accepted-policy','<path>']
            merge = frames + outputs + corpus
            patterns = [frames + corpus + ['--frame-limit','1','--max-cases','100','--no-persist'],
                frames * 2 + corpus + ['--frame-limit','20','--max-cases','100','--no-persist'],
                merge + ['--frame-limit','20','--max-cases','1','--merge-existing','--no-persist'],
                merge + ['--frame-limit','20','--max-cases','1','--merge-existing'],
                merge + ['--merge-existing']]
            if shape not in patterns: raise PermissionError('Learning CLI shape differs')

    def admitted(self, executable, argv, cwd, env):
        return self.pending == (executable, argv, cwd, env)

    def install(self):
        owner = self
        class RoutedPopen(owner.original):
            def __init__(self, args, *positional, **kw):
                # The original strict cold gate still owns cold child admission.
                if isinstance(args, list) and len(args)>2 and args[2] == str(owner.source / 'tests/cold_process_child.py'):
                    super().__init__(args, *positional, **kw)
                    return
                try:
                    route, command, cwd, env, executables, snapshot = owner.classify(args, kw.get('cwd'), kw.get('env'))
                    owner.validate_launch_options(route, positional, kw)
                except (PermissionError, ValueError, OSError, IndexError) as exc:
                    owner.record('rejected', argv=args, reason=str(exc))
                    raise PermissionError(str(exc)) from exc
                if sys.platform != 'darwin' or not Path('/usr/bin/sandbox-exec').exists():
                    owner.record('rejected', reason='Native test containment unavailable')
                    raise PermissionError('Native test containment unavailable; no unguarded fallback')
                reads = [owner.source, Path(sys.base_prefix), Path(sys.prefix), Path('/opt/homebrew/opt'), Path('/opt/homebrew/Cellar')]
                profile = native_profile(reads=reads, writes=[owner.work / 'temporary'],
                                         executables=executables, observe=route == 'owned-ps')
                # ps is an Apple setuid platform binary; copying invalidates its
                # platform execution policy. This read-only observation is exact-
                # argv/owned-PID admitted, explicitly NOT OS-sandboxed.
                launch = command if route == 'owned-ps' else ['/usr/bin/sandbox-exec','-p',profile,*command]
                kw.update(cwd=str(cwd), env=env, close_fds=True)
                binary_hashes = {p:digest(p) for p in set(executables) if Path(p).is_file()}
                binary_hashes['/usr/bin/sandbox-exec'] = digest('/usr/bin/sandbox-exec')
                for path, identity in binary_hashes.items():
                    previous = owner.binary_hashes.setdefault(path, identity)
                    if previous != identity:
                        owner.record('rejected', reason='Executable identity changed', path=path)
                        raise PermissionError('Executable identity changed')
                owner.pending = (launch[0], launch, str(cwd), env)
                try:
                    super().__init__(launch, **kw)
                except OSError as exc:
                    owner.record('launch_error', argv=command, reason=str(exc))
                    raise
                finally:
                    owner.pending = None
                self._route = route
                self._owned_pid = self.pid
                self._recorded_exit = False
                owner.children[self.pid] = self
                owner.deadlines[self.pid] = time.monotonic() + CHILD_SECONDS
                self._watchdog = threading.Timer(CHILD_SECONDS, self._expire)
                self._watchdog.daemon = True
                self._watchdog.start()
                owner.record('start', pid=self.pid, route=route, argv=command, cwd=str(cwd), environment=env,
                    executable_sha256=binary_hashes, deadline_monotonic=owner.deadlines[self.pid],
                    process_group=os.getpgid(self.pid),
                    session_id=os.getsid(self.pid),
                    fixture_sha256=snapshot, profile=None if route == 'owned-ps' else profile,
                    containment='exact read-only owned-PID observation; no OS sandbox' if route == 'owned-ps' else 'macOS Seatbelt',
                    source_file_map_sha256=hashlib.sha256(json.dumps(owner.manifest,sort_keys=True).encode()).hexdigest())
            def send_signal(self, sig):
                if hasattr(self, '_owned_pid') and (self.pid != self._owned_pid or owner.children.get(self.pid) is not self):
                    raise PermissionError('Child signal ownership changed')
                return super().send_signal(sig)
            def communicate(self, *args, **kwargs):
                result = super().communicate(*args, **kwargs)
                if hasattr(self, '_route') and self.returncode:
                    owner.record('diagnostic', pid=self.pid, stderr=str(result[1]))
                return result
            def _expire(self):
                if self.poll() is None:
                    owner.record('child_deadline', pid=self.pid)
                    self.kill()
                    self.wait(timeout=2)
            def _record_exit(self):
                if hasattr(self, '_recorded_exit') and self.returncode is not None and not self._recorded_exit:
                    self._recorded_exit = True
                    self._watchdog.cancel()
                    owner.record('exit', pid=self.pid, returncode=self.returncode)
            def poll(self):
                result = super().poll(); self._record_exit(); return result
            def wait(self, timeout=None):
                result = super().wait(timeout=timeout); self._record_exit(); return result
        subprocess.Popen = RoutedPopen

    def reap_item(self):
        for process in list(self.children.values()):
            if process.poll() is None:
                self.record('cleanup', pid=process.pid)
                process.terminate()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=2)

    def finish(self):
        self.reap_item()
        subprocess.Popen = self.original
