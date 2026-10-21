"""Exec-only cold writer/reader entrypoint. Install isolation before runtime imports."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
sys.dont_write_bytecode = True
ROLE, INPUT, OUTPUT = sys.argv[1:]
INPUT, OUTPUT = Path(INPUT).resolve(), Path(OUTPUT).resolve()
PLAN = Path(os.environ['FRUTH_COLD_PLAN']).resolve()
ROOT = Path(os.environ['FRUTH_COLD_PRODUCTION']).resolve()
violations = []
substrate = None


def guard(event, values):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.bind', 'socket.getaddrinfo',
                 'subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.fork', 'os.forkpty'}:
        violations.append({'event': event})
        raise PermissionError('cold child external I/O denied: ' + event)
    raw_paths, write = [], False
    if event == 'open':
        raw_paths = values[:1]
        mode, flags = values[1:3]
        write = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
            isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
    elif event in {'os.listdir', 'os.scandir'}:
        raw_paths = values[:1]
    elif event in {'os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime'}:
        raw_paths, write = values[:1], True
    elif event in {'os.rename', 'os.link', 'os.symlink'}:
        raw_paths, write = values[:2], True
    for raw in raw_paths:
        if not isinstance(raw, (str, bytes, os.PathLike)):
            continue
        path = Path(os.fsdecode(raw)).resolve()
        forbidden = any(path == ROOT / name or (ROOT / name) in path.parents for name in
            ('state', 'artifacts', 'logs', '.fruth_archiv', 'model_ports.json', 'config',
             'fruth_research/retained-evidence', 'fruth_research/candidates'))
        if write:
            forbidden |= not (path == Path(os.devnull) or path.is_relative_to(PLAN))
            forbidden |= bool(ROLE == 'reader' and substrate and path.is_relative_to(substrate))
        # Writer receipts and supervisor expectations must never enter a reader.
        if ROLE == 'reader' and not write and path.is_relative_to(INPUT.parent):
            forbidden |= path.name.startswith(('writer', 'expected', 'checkpoint'))
        if forbidden:
            violations.append({'event': event, 'path': str(path), 'write': bool(write)})
            raise PermissionError('cold child protected access denied')


sys.addaudithook(guard)
tempfile.tempdir = os.environ['TMPDIR']
config = json.loads(INPUT.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(root):
    return {str(p.relative_to(root)): sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}


def save(path, value):
    with path.open('w') as stream:
        json.dump(value, stream, sort_keys=True, default=str)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def writer():
    import socket
    previous = socket.has_ipv6; socket.has_ipv6 = False
    try:
        import requests
    finally:
        socket.has_ipv6 = previous
    from copy import deepcopy
    from unittest.mock import patch
    from tests.test_persistence_recovery_study import PersistenceStudy, rf, web
    from tests.cold_process_oracle import evidence, semantic

    # Retain the one existing fixture root at its original identity for readers.
    # Cleanup belongs to the coordinator after every subprocess has exited.
    native_temp = tempfile.TemporaryDirectory
    class RetainedTemporaryDirectory(native_temp):
        def cleanup(self):
            self._finalizer.detach()

    class ColdWriter(PersistenceStudy):
        def install_storage_observers(self):
            super().install_storage_observers()
            native_compact = rf.compact_response_frame_for_ledger
            native_finalize = web._finalize_response_frame_payload
            def compact(value, **kwargs):
                self.raw_frame = deepcopy(value)
                return native_compact(value, **kwargs)
            def finalize(value, *args, **kwargs):
                if any(r.get('branch_id') == self.pending for r in value.get('late_fill', {}).get('fill_results', [])):
                    self.accepted_payload = deepcopy(value)
                return native_finalize(value, *args, **kwargs)
            self.stack.enter_context(patch.object(rf, 'compact_response_frame_for_ledger', compact))
            self.stack.enter_context(patch.object(web, '_finalize_response_frame_payload', finalize))
        def op(self, name, **kwargs):
            super().op(name, **kwargs)
            boundary = {'kill_partial': 'partial_prefix_flushed', 'kill_fsync': 'ledger_fsync_enter',
                        'kill_index_selector': 'selector_publish_enter'}.get(config['seam'])
            if self.target_write and name == boundary:
                save(OUTPUT, checkpoint(self, boundary))
                print('COLD_BOUNDARY_READY', flush=True)
                # Parent SIGKILLs only after reading this explicit handshake.
                sys.stdin.readline()
                raise AssertionError('termination boundary unexpectedly resumed')

    def checkpoint(s, boundary=None):
        raw = s.raw_frame
        payload = s.accepted_payload
        parent_frame = s.parent['response_frame']
        record = {'pid': os.getpid(), 'root': str(s.root), 'frames_root': str(s.frames_root),
            'boundary': boundary, 'seam': config['seam'], 'transitions': s.transition_count,
            'parent_length': len(s.parent_ledger), 'parent_sha256': sha(s.parent_ledger),
            'parent': {'frame_id': parent_frame['frame_id'], 'frame_sequence': parent_frame['frame_sequence'],
                'semantic': semantic(s.parent), 'outputs': evidence(parent_frame['output']['outputs'])},
            'candidate': {'frame_id': raw['frame_id'], 'frame_sequence': raw['frame_sequence'],
                'semantic': semantic(payload), 'outputs': evidence(raw['output']['outputs'])},
            'response_id': payload['id'], 'branches': [s.sibling, s.target, s.pending],
            'control_status': s.control_result['status_code'], 'operations': s.ops,
            'provider_calls': s.engine.harness.provider_calls, 'entries': s.entries,
            'claims': s.claim_events, 'artifacts': tree(s.engine.harness.artifacts_dir),
            'saved_index': {name: data.hex() for name, data in s.saved_index.items()},
            'expected_png_sha256': sha(s.engine.model.png), 'violations': violations}
        if boundary is None:
            record.update(receipt=s.candidate['persistence'], observed=s.observed)
        return record

    seam = config['seam'].removeprefix('reported_').removeprefix('kill_')
    with patch.object(tempfile, 'TemporaryDirectory', RetainedTemporaryDirectory):
        s = ColdWriter(seam, config['reverse'])
        try:
            s.prepare()
            save(OUTPUT, checkpoint(s))
        finally:
            s.close()
    print('COLD_WRITER_EXIT', flush=True)


def reader():
    global substrate
    from contextlib import ExitStack
    from unittest.mock import patch
    # Suppress only the platform IPv6 capability probe during dependency import.
    import socket
    previous = socket.has_ipv6; socket.has_ipv6 = False
    try:
        import requests
    finally:
        socket.has_ipv6 = previous
    import fruth_webserver as web
    from fruth_services import response_frames as rf
    from fruth_server.late_fill_runtime import LateFillRuntimeOwner
    from tests.http_client import api_client
    from tests.cold_process_oracle import semantic, evidence
    substrate = Path(config['root']).resolve()
    frames = substrate / 'state/response_frames'
    initial = tree(substrate)
    effects = []
    def forbidden(name):
        def invoke(*args, **kwargs):
            effects.append(name)
            raise AssertionError('cold reader attempted ' + name)
        return invoke
    fresh = not web._RESPONSE_LOOKUP and not web._RESPONSE_LATE_FILL_IN_FLIGHT and not web._RESPONSES_RUNTIME._mutation_locks
    with ExitStack() as stack:
        for name, value in {
            'RESPONSE_FRAMES_DIR': frames,
            'ARTIFACT_REGISTRY_LEDGER': substrate / 'state/artifact_registry.jsonl',
            'CONFIG_FILE_NAME': str(substrate / 'model_ports.json'),
            'RUNTIME_STATUS_PATH': substrate / 'state/runtime_status.json',
            'CHAT_HISTORY_DIR': substrate / 'state/chat_history',
            'INFERENCE_PREFERENCES_PATH': substrate / 'state/inference_preferences.json',
        }.items():
            stack.enter_context(patch.object(web, name, value))
        for name in ('_schedule_response_late_fill', '_claim_response_late_fill', '_release_response_late_fill',
                     '_schedule_post_response_substrate_hygiene', '_execute_chat_backend_request',
                     '_invoke_internal_api_json_route'):
            stack.enter_context(patch.object(web, name, forbidden(name)))
        stack.enter_context(patch.object(LateFillRuntimeOwner, 'schedule_response_late_fill', forbidden('owner_schedule')))
        stack.enter_context(patch.object(web.requests, 'post', forbidden('provider')))
        result = rf.load_latest_response_state(config['response_id'], frames_dir=frames)
        payload = result.get('response_payload', {})
        frame = result.get('response_frame', {})
        public, retries = [], []
        with api_client(web.app) as client:
            for view in ('default', 'ui', 'status', 'debug', 'truth', 'full'):
                response = client.get('/api/responses/' + config['response_id'],
                    query_string={} if view == 'default' else {'view': view})
                value = response.get_json()
                public.append({'view': view, 'status_code': response.status_code,
                    'persistence': value.get('persistence'),
                    'frame_id': value.get('frame_id') or value.get('response_frame', {}).get('frame_id'),
                    'status': value.get('status'), 'lifecycle': value.get('lifecycle_state'),
                    'error': value.get('error'),
                    'semantic': semantic(value) if view in {'truth', 'full'} else None})
            for branch in config['branches']:
                response = client.post('/api/responses/' + config['response_id'] + '/late_fill/retry',
                                       json={'branch_id': branch})
                retries.append(response.status_code)
        artifact_observations = []
        for item in payload.get('late_fill', {}).get('fill_results', []):
            path = item.get('saved_image_path')
            if path:
                target = Path(path).resolve()
                assert target.is_relative_to(substrate / 'artifacts')
                artifact_observations.append({'branch': item['branch_id'], 'ref': item.get('artifact_ref'),
                    'sha256': sha(target.read_bytes()) if target.exists() else None,
                    'bindings_valid': all(a.get('artifact_ref') == item.get('artifact_ref') and
                        a.get('branch_id') == item['branch_id'] for a in item.get('artifacts', []))})
        ledger = (frames / 'responses.jsonl').read_bytes()
        record = {'pid': os.getpid(), 'fresh': fresh, 'ok': result.get('ok'),
            'response_id': payload.get('id'), 'frame_id': frame.get('frame_id'),
            'frame_sequence': frame.get('frame_sequence'), 'semantic': semantic(payload),
            'outputs': evidence(frame.get('output', {}).get('outputs', [])),
            'persistence': payload.get('persistence'), 'errors': result.get('errors'),
            'error': result.get('error'), 'index_used': result.get('index_used'),
            'ledger_fallback_used': result.get('ledger_fallback_used'),
            'public': public, 'retry_codes': retries, 'effects': effects,
            'claims_after': len(web._RESPONSE_LATE_FILL_IN_FLIGHT),
            'storage_unchanged': initial == tree(substrate), 'tree_sha256': tree(substrate),
            'ledger_sha256': sha(ledger), 'ledger_length': len(ledger),
            'artifacts': artifact_observations, 'violations': violations,
            'canonical_loads': 1, 'public_gets': 6, 'explicit_retries': 3}
        save(OUTPUT, record)


if __name__ == '__main__':
    try:
        (writer if ROLE == 'writer' else reader)()
    except BaseException as exc:
        save(OUTPUT.with_suffix('.error.json'), {'pid': os.getpid(), 'error': repr(exc),
            'traceback': traceback.format_exc(), 'violations': violations})
        raise
