#!/usr/bin/env python3
"""Existing launchers → persisted identity → fresh-process cleanup, no model work.

Use an immutable guarded-runner source snapshot and a new temporary output root.
Only model discovery/metadata/readiness transport is substituted; Popen, identity,
registry writes, socket ownership and termination use the production owners.
"""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

SOURCE = None
WORK = None
OWNER = None
REGISTRY = None
OLLAMA = None
MLX = None
LLAMA = None
RECEIPTS = []
PY_LISTENER = '''import os,pathlib,signal,socket,sys,time
args=sys.argv[1:];port=int(args[args.index('--port')+1])
sock=socket.socket();sock.bind(('127.0.0.1',port));sock.listen()
def term(sig,frame):
 with pathlib.Path(os.environ['FIXTURE_EVENTS']).open('a') as f:f.write(str(os.getpid())+' TERM\\n')
 raise SystemExit(0)
signal.signal(signal.SIGTERM,term)
while not pathlib.Path(os.environ['FIXTURE_STOP']).exists():
 trigger=os.environ.get('FIXTURE_EXEC')
 if trigger and pathlib.Path(trigger).exists():
  pathlib.Path(trigger).unlink()
  os.execv(sys.executable,[sys.executable,os.environ['FIXTURE_REPLACEMENT'],'--port',str(port),'--changed'])
 time.sleep(.01)
'''
C_LISTENER = r'''
#include <arpa/inet.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>
static void term(int sig) { const char *p=getenv("FIXTURE_EVENTS"); FILE *f=fopen(p,"a"); if(f){fprintf(f,"%d TERM\n",getpid());fclose(f);} _exit(0); }
int main(int argc,char **argv){
 int port=atoi(getenv("FIXTURE_PORT")?getenv("FIXTURE_PORT"):"0");
 const char *host=getenv("OLLAMA_HOST");if(host&&strrchr(host,':'))port=atoi(strrchr(host,':')+1);
 for(int i=1;i+1<argc;i++)if(!strcmp(argv[i],"--port"))port=atoi(argv[i+1]);
 int s=socket(AF_INET,SOCK_STREAM,0);struct sockaddr_in a={0};a.sin_family=AF_INET;a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);a.sin_port=htons(port);
 if(bind(s,(struct sockaddr*)&a,sizeof(a))||listen(s,8))return 42;
 signal(SIGTERM,term);
 while(access(getenv("FIXTURE_STOP"),F_OK))usleep(10000);
 return 0;
}
'''


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def wait(predicate):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('Fixture readiness deadline')


class LaunchChains(unittest.TestCase):
    def setUp(self):
        self.root = WORK / self._testMethodName
        self.root.mkdir()
        os.chdir(self.root)
        (self.root / 'logs').mkdir()
        (self.root / 'model_ports.json').write_text('[]')
        self.stack = contextlib.ExitStack()
        self.children = []
        self.events = self.root / 'signals'
        self.events.touch()
        self.stop = self.root / 'stop-fixtures'
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_STOP=str(self.stop), FIXTURE_EVENTS=str(self.events)))
        # Spy only: retain handles for teardown without changing executable/argv.
        original = subprocess.Popen
        def tracked(*args, **kwargs):
            p = original(*args, **kwargs)
            self.children.append(p)
            return p
        self.stack.enter_context(patch.object(subprocess, 'Popen', side_effect=tracked))
        for manager in (OLLAMA, MLX, LLAMA):
            self.stack.enter_context(patch.object(manager, 'CONFIG_FILE', self.root / 'model_ports.json'))
            self.stack.enter_context(patch.object(manager, 'LOG_DIR', self.root / 'logs'))
        self.stack.enter_context(patch.object(OLLAMA, 'OLLAMA_CLI', str(WORK / 'listener')))
        self.stack.enter_context(patch.object(LLAMA, 'resolve_llama_server_bin', return_value=str(WORK / 'listener')))

    def tearDown(self):
        self.stop.touch()  # Only fixtures watch this private cooperative stop file.
        for p in self.children:
            try: p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.fail(f'Owned fixture {p.pid} did not exit cooperatively; no unverified signal sent')
        self.stack.close()
        RECEIPTS.append({'case': self._testMethodName, 'children': [{'pid': p.pid, 'exit': p.returncode} for p in self.children],
                         'signals': self.events.read_text()})
        os.chdir(WORK)

    def cleanup(self, record):
        # New interpreter: no retained launch object or in-memory ownership map.
        code = ('from fruth_core.process_ownership import stop_listener; import sys; '
                'stop_listener(sys.argv[1], int(sys.argv[2]))')
        env = dict(os.environ, PYTHONPATH=str(SOURCE), PYTHONDONTWRITEBYTECODE='1')
        r = subprocess.run([sys.executable, '-B', '-c', code, str(self.root), str(record['port'])],
                           cwd=self.root, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"Sent SIGTERM to verified PID {record['pid']}", r.stdout)
        self.assertIn(f"{record['pid']} TERM", self.events.read_text())
        return {'pid': record['pid'], 'port': record['port'], 'identity': record['process_identity'],
                'command': record['server_command'], 'cleanup': r.stdout}

    def record_for(self, pid):
        entries = REGISTRY.read_registry_entries(self.root / 'model_ports.json', strict=True)
        records = [r for r in entries if r.get('pid') == pid]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(record['process_identity'])
        self.assertTrue(record['server_command'])
        owned = OWNER.inspect_listener(self.root, record['port'])
        self.assertEqual(owned.pid, pid)
        return record

    def default(self):
        port = free_port()
        self.stack.enter_context(patch.object(OLLAMA, 'DEFAULT_SERVER_PORT', port))
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_PORT=str(port)))
        self.assertTrue(OLLAMA.ensure_default_server_running())
        record, = REGISTRY.read_registry_entries(self.root / 'model_ports.json')
        return self.record_for(record['pid'])

    def test_default_launch_reuse_snapshot_preservation_and_cleanup(self):
        record = self.default()
        before = (self.root / 'model_ports.json').read_bytes()
        self.assertTrue(OLLAMA.ensure_default_server_running())
        self.assertEqual((self.root / 'model_ports.json').read_bytes(), before)
        self.assertEqual(REGISTRY.list_runtime_entries(path=self.root / 'model_ports.json', prune=False), [])
        from scripts import startup_model_manager as startup
        with patch.object(startup, 'CONFIG_PATH', self.root / 'model_ports.json'):
            startup._write_registry_once([])  # snapshot taken before default discovery
        self.assertEqual(self.record_for(record['pid'])['process_identity'], record['process_identity'])
        (self.root / 'receipt.json').write_text(json.dumps(self.cleanup(record), indent=2))

    def test_ollama_regular_model_launch_persistence_and_cleanup(self):
        default = self.default()
        rows = []
        # All three return branches must preserve the captured evidence.
        for capability in ('chat', 'embedding', 'image_generation'):
            port = free_port()
            with patch.object(OLLAMA, 'find_free_port', return_value=port), \
                 patch.object(OLLAMA, '_fetch_model_metadata', return_value={}), \
                 patch.object(OLLAMA, '_observed_server_version', return_value=''), \
                 patch.object(OLLAMA, 'wait_for_model_loaded', return_value=True), \
                 patch.object(OLLAMA, 'wait_for_embedding_model_loaded', return_value=True):
                record = OLLAMA.start_model_instance('fixture-'+capability, capability=capability, start_source='frontend_button')
            self.assertIsNotNone(record)
            rows.append(self.cleanup(self.record_for(record['pid'])))
        rows.append(self.cleanup(self.record_for(default['pid'])))
        (self.root / 'receipt.json').write_text(json.dumps(rows, indent=2))

    def test_mlx_regular_launch_variants_persist_and_cleanup(self):
        variants = [('mlx_lm','chat'), ('mlx_vlm','vision_analysis'), ('mlx_audio','text_to_speech'),
                    ('mlx_whisper','speech_to_text'), ('mlx_vlm','embedding'), ('mlx_vlm','image_generation')]
        for module in ('mlx_lm', 'mlx_vlm', 'mlx_audio'):
            (self.root / module).mkdir()
            (self.root / module / '__init__.py').write_text('')
            (self.root / module / 'server.py').write_text(PY_LISTENER)
        script = self.root / 'fixture_server.py'
        script.write_text(PY_LISTENER)
        rows = []
        for kind, capability in variants:
            model = self.root / ('model-'+capability)
            model.mkdir(); (model / 'config.json').write_text('{}')
            repo = 'fixture/whisper' if kind == 'mlx_whisper' else 'fixture/'+capability
            snapshot = {'repo': repo, 'path': str(model), 'mlx_server': kind}
            port = free_port()
            with patch.object(MLX, 'find_mlx_snapshots', return_value=[snapshot]), \
                 patch.object(MLX, 'resolve_mlx_python', return_value=sys.executable), \
                 patch.object(MLX, '_mlx_discovery_details', return_value={'runnable': True}), \
                 patch.object(MLX, '_mlx_lm_launch_defaults', return_value={}), \
                 patch.object(MLX, '_mlx_vlm_launch_defaults', return_value={}), \
                 patch.object(MLX, 'IMAGE_SERVER_SCRIPT', script), \
                 patch.object(MLX, 'SPEECH_SERVER_SCRIPT', script), \
                 patch.object(MLX, 'schedule_recent_mlx_instance_reconciliation'):
                record = MLX.start_mlx_model(repo, str(model), port, capability=capability, start_source='frontend_button')
            rows.append(self.cleanup(self.record_for(record['pid'])))
        (self.root / 'receipt.json').write_text(json.dumps(rows, indent=2))

    def test_llama_regular_launch_persists_and_cleanup(self):
        port = free_port()
        model = self.root / 'fixture.gguf';model.write_bytes(b'fixture')
        source = {'display_name':'fixture', 'source_kind':'local_gguf', 'model_path':str(model)}
        with patch.object(LLAMA, '_resolve_model_source', return_value=source), \
             patch.object(LLAMA, '_next_free_port', return_value=port), \
             patch.object(LLAMA, '_llama_cpp_launch_defaults', return_value={}), \
             patch.object(LLAMA, '_wait_for_server_ready', side_effect=lambda p: (wait(lambda: bool(OWNER.listener_pids(p))) or True)):
            record = LLAMA.start_llama_cpp_instance('fixture', str(model), port, start_source='frontend_button')
        (self.root / 'receipt.json').write_text(json.dumps(self.cleanup(self.record_for(record['pid'])), indent=2))

    def test_foreign_default_is_not_adopted_or_signaled(self):
        port = free_port()
        self.stack.enter_context(patch.object(OLLAMA, 'DEFAULT_SERVER_PORT', port))
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_PORT=str(port)))
        child = subprocess.Popen([str(WORK/'listener'), 'serve'], cwd=self.root)
        wait(lambda: bool(OWNER.listener_pids(port)))
        for content in ('[]', '{bad'):
            (self.root / 'model_ports.json').write_text(content)
            self.assertFalse(OLLAMA.ensure_default_server_running())
            self.assertEqual((self.root / 'model_ports.json').read_text(), content)
            self.assertIsNone(child.poll())
            self.assertEqual(self.events.read_text(), '')

    def test_stale_and_conflicting_default_evidence_not_repaired(self):
        record = self.default()
        for records in ([{**record, 'process_identity': record['process_identity']+' changed'}],
                        [{**record, 'process_identity': ''}], [record, {**record, 'instance_id':'conflict'}]):
            (self.root / 'model_ports.json').write_text(json.dumps(records))
            before = (self.root / 'model_ports.json').read_bytes()
            self.assertFalse(OLLAMA.ensure_default_server_running())
            self.assertEqual((self.root / 'model_ports.json').read_bytes(), before)
            self.assertEqual(self.events.read_text(), '')

    def test_other_checkout_default_is_not_adopted(self):
        other = self.root / 'other-checkout'
        other.mkdir(); (other / 'model_ports.json').write_text('[]')
        port = free_port()
        self.stack.enter_context(patch.object(OLLAMA, 'DEFAULT_SERVER_PORT', port))
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_PORT=str(port)))
        os.chdir(other)
        try:
            with patch.object(OLLAMA, 'CONFIG_FILE', other / 'model_ports.json'), \
                 patch.object(OLLAMA, 'LOG_DIR', other / 'logs'):
                self.assertTrue(OLLAMA.ensure_default_server_running())
        finally:
            os.chdir(self.root)
        content = (other / 'model_ports.json').read_bytes()
        (self.root / 'model_ports.json').write_bytes(content)
        self.assertFalse(OLLAMA.ensure_default_server_running())
        self.assertEqual((self.root / 'model_ports.json').read_bytes(), content)
        self.assertEqual(len(OWNER.listener_pids(port)), 1)
        self.assertEqual(self.events.read_text(), '')

    def test_default_listener_appearing_during_launch_is_not_adopted(self):
        port = free_port()
        self.stack.enter_context(patch.object(OLLAMA, 'DEFAULT_SERVER_PORT', port))
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_PORT=str(port)))
        foreign = []
        original = OLLAMA.prepare_clean_global_log
        def appear(*args, **kwargs):
            original(*args, **kwargs)
            foreign.append(subprocess.Popen([str(WORK / 'listener'), 'foreign']))
            wait(lambda: OWNER.listener_pids(port) == [foreign[0].pid])
        with patch.object(OLLAMA, 'prepare_clean_global_log', side_effect=appear):
            self.assertFalse(OLLAMA.ensure_default_server_running())
        self.assertIsNone(foreign[0].poll())
        self.assertEqual((self.root / 'model_ports.json').read_text(), '[]')
        self.assertEqual(self.events.read_text(), '')

    def test_mlx_exec_change_before_registration_is_never_recaptured(self):
        package = self.root / 'mlx_lm'; package.mkdir()
        (package / '__init__.py').touch(); (package / 'server.py').write_text(PY_LISTENER)
        replacement = self.root / 'replacement.py'; replacement.write_text(PY_LISTENER)
        trigger = self.root / 'exec-now'
        self.stack.enter_context(patch.dict(os.environ, FIXTURE_EXEC=str(trigger), FIXTURE_REPLACEMENT=str(replacement)))
        model = self.root / 'model'; model.mkdir(); (model / 'config.json').write_text('{}')
        port = free_port()
        snapshot = {'repo': 'fixture/chat', 'path': str(model), 'mlx_server': 'mlx_lm'}
        pids = []
        def readiness(p):
            wait(lambda: bool(OWNER.listener_pids(p)))
            pids.extend(OWNER.listener_pids(p))
            trigger.touch()
            wait(lambda: str(replacement) in OWNER.process_identity(pids[0]) and OWNER.listener_pids(p) == pids)
            return True
        with patch.object(MLX, 'find_mlx_snapshots', return_value=[snapshot]), \
             patch.object(MLX, 'resolve_mlx_python', return_value=sys.executable), \
             patch.object(MLX, '_mlx_discovery_details', return_value={'runnable': True}), \
             patch.object(MLX, '_mlx_lm_launch_defaults', return_value={}), \
             patch.object(MLX, 'wait_for_port', side_effect=readiness):
            with self.assertRaisesRegex(OWNER.OwnershipError, 'identity changed'):
                MLX.start_mlx_model('fixture/chat', str(model), port, start_source='frontend_button')
        self.assertEqual(OWNER.listener_pids(port), pids)
        self.assertEqual((self.root / 'model_ports.json').read_text(), '[]')
        self.assertEqual(self.events.read_text(), '')


def main():
    global SOURCE, WORK, OWNER, REGISTRY, OLLAMA, MLX, LLAMA
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();SOURCE=args.source.resolve();WORK=args.output.resolve();WORK.mkdir()
    os.chdir(WORK);sys.path.insert(0,str(SOURCE))
    from fruth_core import process_ownership,registry
    from fruth_runtime import ollama_model_manager,mlx_model_manager,llama_cpp_model_manager
    OWNER,REGISTRY,OLLAMA,MLX,LLAMA=process_ownership,registry,ollama_model_manager,mlx_model_manager,llama_cpp_model_manager
    code=WORK/'listener.c';code.write_text(C_LISTENER)
    subprocess.run(['/usr/bin/clang','-O0',str(code),'-o',str(WORK/'listener')],check=True,capture_output=True,text=True)
    files=['fruth_core/process_ownership.py','fruth_core/process_identity.py','fruth_core/registry.py',
           'fruth_runtime/ollama_model_manager.py','fruth_runtime/mlx_model_manager.py','fruth_runtime/llama_cpp_model_manager.py','scripts/startup_model_manager.py']
    hashes={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in files}
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LaunchChains))
    assert hashes=={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in files}
    (WORK/'results.json').write_text(json.dumps(dict(tests=result.testsRun,passed=result.wasSuccessful(),source=hashes,
        fixture_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cases=RECEIPTS,
        failures=[(str(t),msg) for t,msg in result.failures+result.errors]),indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
