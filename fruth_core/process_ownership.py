"""Checkout-bound process checks for maintenance and web startup.

Ports discover candidates, never authorize a signal. Model ownership requires the
existing registry's birth/command evidence; missing legacy evidence stays missing.
The webserver has no registry record: its exact Python/script command and cwd bind
it to this checkout. Rechecks narrow, but cannot eliminate, POSIX PID signal races.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

from fruth_core.process_identity import (
    _parsed_process_identity, process_identity, process_identity_matches,
)
from fruth_core.registry import read_registry_entries
from fruth_runtime.child_process_env import sanitized_child_process_env


class OwnershipError(RuntimeError):
    pass


@dataclass(frozen=True)
class OwnedListener:
    pid: int
    port: int
    root: Path
    identity: str
    webserver: bool
    record: dict | None


@dataclass(frozen=True)
class SpawnedProcess:
    """Evidence captured at Popen, carried by the launcher until registration."""
    child: subprocess.Popen
    pid: int
    root: Path
    identity: str
    command: tuple[str, ...]


FRAMEWORK_EXEC_TIMEOUT_SECONDS = 1.0


def capture_spawned_process(child, command):
    """Only call immediately after creating this child, never for discovered PIDs."""
    if (not isinstance(child.pid, int) or child.pid <= 1 or child.poll() is not None
            or not command or not all(isinstance(arg, str) and arg for arg in command)):
        raise OwnershipError('New child exited or lacks a valid launch command; ownership unresolved')
    root = Path.cwd().resolve()
    identity = _identity(child.pid)
    parsed = _parsed_process_identity(identity)
    if (not parsed or not _command_matches(parsed[1], command)
            or process_cwd(child.pid) != root or child.poll() is not None):
        raise OwnershipError(f'New child PID {child.pid}: launch identity unavailable or changed; left untouched')
    # macOS framework Python re-execs its companion binary during startup. Bind
    # the birth at Popen, then permit only that exact one-way executable transition
    # with unchanged argv/cwd and a live retained child. Never refresh later evidence.
    framework = _framework_python_executable(command[0])
    if framework is not None:
        final_command = ' '.join([framework, *command[1:]])
        deadline = time.monotonic() + FRAMEWORK_EXEC_TIMEOUT_SECONDS
        while parsed[1] != final_command:
            if child.poll() is not None or time.monotonic() >= deadline:
                raise OwnershipError(f'New child PID {child.pid}: framework exec unconfirmed; left untouched')
            observed = _identity(child.pid)
            next_parsed = _parsed_process_identity(observed)
            if (not next_parsed or next_parsed[0] != parsed[0]
                    or next_parsed[1] not in {parsed[1], final_command}):
                raise OwnershipError(f'New child PID {child.pid}: unexpected launch identity change; left untouched')
            identity, parsed = observed, next_parsed
            if parsed[1] != final_command:
                time.sleep(.01)
    spawned = SpawnedProcess(child, child.pid, root, identity, tuple(command))
    verify_spawned_process(spawned)
    return spawned


def verify_spawned_process(spawned, *, port=None):
    """Return the original evidence only while the same owned child remains live."""
    if spawned.child.pid != spawned.pid or spawned.child.poll() is not None:
        raise OwnershipError(f'New child PID {spawned.pid} exited or its handle changed')
    if process_cwd(spawned.pid) != spawned.root:
        raise OwnershipError(f'New child PID {spawned.pid}: checkout changed; left untouched')
    if port is not None and listener_pids(port) != [spawned.pid]:
        raise OwnershipError(f'Port {port} is not exclusively owned by new child PID {spawned.pid}')
    if (not process_identity_matches(_identity(spawned.pid), spawned.identity)
            or spawned.child.poll() is not None):
        raise OwnershipError(f'New child PID {spawned.pid}: process identity changed; left untouched')
    return {'process_identity': spawned.identity, 'server_command': list(spawned.command)}


def terminate_spawned_process(spawned):
    """Failure cleanup of this launch only; never fall back to a port occupant."""
    if spawned.child.pid != spawned.pid:
        raise OwnershipError('New child handle changed; left untouched')
    if spawned.child.poll() is not None:
        return
    verify_spawned_process(spawned)
    spawned.child.terminate()
    try:
        spawned.child.wait(timeout=1)
    except subprocess.TimeoutExpired:
        verify_spawned_process(spawned)
        spawned.child.kill()
        spawned.child.wait(timeout=1)


def _observe(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=5,
                              env=sanitized_child_process_env())
    except (OSError, subprocess.SubprocessError) as exc:
        raise OwnershipError(f'Process observation unavailable: {exc}') from exc


def listener_pids(port):
    result = _observe(['lsof', '-w', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'])
    lines = result.stdout.splitlines()
    if (result.returncode not in (0, 1) or result.stderr.strip()
            or any(not line.isdecimal() or int(line) <= 1 for line in lines)
            or (result.returncode == 0 and not lines)):
        raise OwnershipError(f'Listener discovery failed on port {port}')
    return sorted({int(line) for line in lines})


def process_cwd(pid):
    result = _observe(['lsof', '-w', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'])
    names = [line[1:] for line in result.stdout.splitlines() if line.startswith('n')]
    if (result.returncode or result.stderr.strip() or len(names) != 1
            or not Path(names[0]).is_absolute()):
        raise OwnershipError(f'Working directory unavailable for PID {pid}')
    return Path(names[0]).resolve()


def _identity(pid):
    try:
        return process_identity(pid)
    except (OSError, subprocess.SubprocessError) as exc:
        raise OwnershipError(f'Identity unavailable for PID {pid}: {exc}') from exc


def _exited(pid):
    result = _observe(['ps', '-p', str(pid), '-o', 'stat='])
    if result.stderr.strip():
        return False
    return ((result.returncode == 1 and not result.stdout.strip())
            or (result.returncode == 0 and result.stdout.strip().startswith('Z')))


def _records(root, pid, port):
    # The established reader handles legacy layouts, without pruning or writing.
    try:
        entries = read_registry_entries(root / 'model_ports.json', strict=True)
    except (OSError, ValueError) as exc:
        raise OwnershipError('Runtime registry unreadable or malformed; ownership unresolved') from exc
    return [entry for entry in entries
            if str(entry.get('pid')) == str(pid) or str(entry.get('port')) == str(port)]


def _framework_python_executable(executable):
    path = Path(executable)
    if sys.platform != 'darwin' or not path.is_absolute():
        return None
    resolved = path.resolve()
    # macOS framework Python execs this exact companion executable. Do not use
    # basename or substring matching to admit an arbitrary interpreter.
    app = resolved.parent.parent / 'Resources/Python.app/Contents/MacOS/Python'
    if resolved.name.startswith('python') and app.is_file():
        return str(app.resolve())
    return None


def _executable_variants(executable):
    path = Path(executable)
    if not path.is_absolute():
        return {executable}
    variants = {executable, str(path.resolve())}
    framework = _framework_python_executable(executable)
    if framework is not None:
        variants.add(framework)
    return variants


def _command_matches(observed, command):
    return observed in {' '.join([exe, *command[1:]]) for exe in _executable_variants(command[0])}


def _web_command(command, root):
    executables = _executable_variants(sys.executable)
    python = root / '.venv/bin/python3'
    if python.is_file():
        executables.update(_executable_variants(str(python)))
    scripts = {'fruth_webserver.py', './fruth_webserver.py', str(root / 'fruth_webserver.py')}
    return command in {f'{exe} {script}' for exe in executables for script in scripts}


def inspect_listener(root, port, *, webserver=False):
    root = Path(root).resolve()
    pids = listener_pids(port)
    if not pids:
        return None
    if len(pids) != 1:
        raise OwnershipError(f'Port {port}: conflicting listener PIDs {pids}; left untouched')
    pid = pids[0]
    identity = _identity(pid)
    parsed = _parsed_process_identity(identity)
    if not parsed or process_cwd(pid) != root:
        raise OwnershipError(f'Port {port}, PID {pid}: missing identity or another checkout; left untouched')
    records = _records(root, pid, port)
    record = None
    if webserver:
        if records or not _web_command(parsed[1], root):
            raise OwnershipError(f'Port {port}, PID {pid}: not this checkout\'s verified Fruth webserver; left untouched')
    else:
        if len(records) != 1:
            raise OwnershipError(f'Port {port}, PID {pid}: missing or conflicting registry ownership; left untouched')
        record = records[0]
        command = record.get('server_command')
        if (record.get('agent') or record.get('backend') not in {'ollama', 'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'}
                or str(record.get('pid')) != str(pid) or str(record.get('port')) != str(port)
                or not process_identity_matches(identity, record.get('process_identity'))
                or not isinstance(command, list) or not command
                or not all(isinstance(arg, str) and arg for arg in command)
                or not _command_matches(parsed[1], command)):
            raise OwnershipError(f'Port {port}, PID {pid}: stale, missing or conflicting registry identity; left untouched')
    owned = OwnedListener(pid, port, root, identity, webserver, record)
    revalidate(owned)
    return owned


def revalidate(owned, *, require_listener=True):
    records = _records(owned.root, owned.pid, owned.port)
    if records != ([] if owned.record is None else [owned.record]):
        raise OwnershipError(f'PID {owned.pid}: registry ownership changed; left untouched')
    if process_cwd(owned.pid) != owned.root:
        raise OwnershipError(f'PID {owned.pid}: checkout identity changed; left untouched')
    pids = listener_pids(owned.port)
    if pids != [owned.pid] and (require_listener or pids):
        raise OwnershipError(f'Port {owned.port}: listener identity changed; left untouched')
    # Last observation before the caller can signal: compare birth AND command.
    if not process_identity_matches(_identity(owned.pid), owned.identity):
        raise OwnershipError(f'PID {owned.pid}: process identity changed; left untouched')


def stop_listener(root, port, *, webserver=False, dry_run=False, grace=1.0):
    owned = inspect_listener(root, port, webserver=webserver)
    if owned is None:
        return
    if dry_run:
        print(f'[dry-run] Would stop verified PID {owned.pid} on port {port}; identity will be rechecked before each signal')
        return
    revalidate(owned)
    os.kill(owned.pid, signal.SIGTERM)
    print(f'Sent SIGTERM to verified PID {owned.pid} on port {port}')
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if not _identity(owned.pid):
            if _exited(owned.pid):
                break
            raise OwnershipError(f'PID {owned.pid}: identity unavailable after SIGTERM; stop unresolved')
        try:
            revalidate(owned, require_listener=False)
        except OwnershipError:
            # A cooperative child can exit between the identity and cwd/listener
            # observations. Accept only confirmed exit, never merely lost evidence;
            # the final listener check below still rejects a replacement service.
            if not _exited(owned.pid):
                raise
            break
        time.sleep(.05)
    else:
        revalidate(owned, require_listener=False)
        os.kill(owned.pid, signal.SIGKILL)
        print(f'Sent SIGKILL to reverified PID {owned.pid} on port {port}')
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline and process_identity_matches(_identity(owned.pid), owned.identity):
            time.sleep(.05)
        if not _exited(owned.pid):
            raise OwnershipError(f'PID {owned.pid}: exit not confirmed after SIGKILL; stop unresolved')
    # A replacement listener is unresolved, even when our original process exited.
    if listener_pids(port):
        raise OwnershipError(f'Port {port}: listener remains after stop; maintenance aborted')


def check_webserver(root, port, *, expected_pid=None):
    owned = inspect_listener(root, port, webserver=True)
    if owned is None:
        return None
    if expected_pid is not None and owned.pid != expected_pid:
        raise OwnershipError(f'Port {port}: listener is not the launched webserver PID {expected_pid}')
    revalidate(owned)
    return owned


def launch_webserver(root, port):
    root = Path(root).resolve()
    if check_webserver(root, port) is not None:
        raise OwnershipError(f'Port {port}: listener appeared before launch; retry startup to verify reuse')
    with (root / 'logs/flask_webserver.log').open('ab') as log:
        child = subprocess.Popen([sys.executable, str(root / 'fruth_webserver.py')],
                                 cwd=root, stdin=subprocess.DEVNULL, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    # Retain the child handle: an exited child cannot be mistaken for a reused PID.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise OwnershipError(f'Webserver PID {child.pid} exited with status {child.returncode}; see logs/flask_webserver.log')
        owned = check_webserver(root, port, expected_pid=child.pid)
        if owned is not None:
            if child.poll() is not None:
                raise OwnershipError(f'Webserver PID {child.pid} exited during verification')
            return owned
        time.sleep(.05)
    raise OwnershipError(f'Webserver PID {child.pid} has no verified listener on port {port}; see logs/flask_webserver.log')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('cleanup', 'check-webserver', 'launch-webserver'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--port', type=int, default=5011)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'cleanup':
            unresolved = False
            for port in (5011, *range(11434, 11551)):
                try:
                    stop_listener(args.root, port, webserver=port == 5011, dry_run=args.dry_run)
                except (OwnershipError, OSError) as exc:
                    unresolved = True
                    print(f'Unresolved ownership: {exc}', file=sys.stderr)
            return 1 if unresolved else 0
        if args.dry_run:
            parser.error('--dry-run applies only to cleanup')
        owned = (launch_webserver(args.root, args.port) if args.action == 'launch-webserver'
                 else check_webserver(args.root, args.port))
        if owned is None:
            return 3  # Vacant; distinct from unresolved/error.
        print(f'Verified Fruth webserver PID {owned.pid} on port {args.port}')
        return 0
    except (OwnershipError, OSError) as exc:
        print(f'Fruth ownership check failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
