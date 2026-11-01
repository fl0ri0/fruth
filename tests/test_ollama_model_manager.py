import pytest
from process_launch_test_support import mock_launch_ownership
import fruth_runtime.ollama_model_manager as _ownership_owner_0

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fruth_runtime import ollama_model_manager


class OllamaModelManagerTests(unittest.TestCase):
    @patch('fruth_runtime.ollama_model_manager.subprocess.run')
    def test_pull_error_survives_terminal_spinner_frames(self, run):
        spinner = '\x1b[?2026h\x1b[?25l\x1b[1Gpulling manifest ⠋ \x1b[K\x1b[?25h\x1b[?2026l'
        diagnostic = 'Error: pull model manifest: registry request failed\nDetails: connection reset by peer'
        run.return_value = SimpleNamespace(returncode=1, stdout='', stderr=spinner * 100 + '\n' + diagnostic)

        ok, message = ollama_model_manager.pull_model('embeddinggemma-2:740m')

        self.assertFalse(ok)
        self.assertEqual(message, diagnostic)
        self.assertEqual(run.call_args.args[0], [ollama_model_manager.OLLAMA_CLI, 'pull', 'embeddinggemma-2:740m'])
        self.assertEqual(run.call_count, 1)

    @patch('fruth_runtime.ollama_model_manager.subprocess.run')
    def test_pull_plain_diagnostics_are_not_clipped_or_interpreted(self, run):
        diagnostic = 'Warning: registry returned additional detail\nError: ' + 'évidence [42] ' * 300
        run.return_value = SimpleNamespace(returncode=1, stdout='', stderr=diagnostic)

        self.assertEqual(ollama_model_manager.pull_model('test:tag'), (False, diagnostic.strip()))

    @patch('fruth_runtime.ollama_model_manager.subprocess.run')
    def test_pull_progress_only_stderr_does_not_hide_stdout_error(self, run):
        run.return_value = SimpleNamespace(returncode=1, stdout='\x1b[31mError: unavailable\x1b[0m',
                                          stderr='\rpulling manifest ⠙\r')
        self.assertEqual(ollama_model_manager.pull_model('test:tag'), (False, 'Error: unavailable'))

    @patch('fruth_runtime.ollama_model_manager.subprocess.run')
    def test_pull_terminal_controls_are_removed_and_exit_code_owns_success(self, run):
        cases = [
            (0, '\x1b[32msuccess\x1b[0m', '', True, 'success'),
            (1, '', '\x1b[32msuccess\x1b[0m', False, 'success'),
            (0, '', 'pulling manifest ⠋', True, 'Model test:tag was loaded successfully.'),
            (2, '', '\x1b[?25l', False, 'Pull failed for test:tag (exit code 2).'),
            (1, '', '\x1b]0;title\x07Error: blocked\x1b]0;done\x1b\\', False, 'Error: blocked'),
        ]
        for code, stdout, stderr, ok, message in cases:
            with self.subTest(code=code, stdout=stdout, stderr=stderr):
                run.return_value = SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)
                self.assertEqual(ollama_model_manager.pull_model('test:tag'), (ok, message))

    @patch('fruth_runtime.ollama_model_manager.subprocess.Popen')
    @patch('fruth_runtime.ollama_model_manager.is_port_listening', return_value=True)
    @patch('fruth_runtime.ollama_model_manager.inspect_listener', return_value=SimpleNamespace(
        record={'backend': 'ollama', 'runtime_service': 'ollama_default'}))
    def test_existing_default_server_is_reused_without_launching(
        self, _owned, _listening, start,
    ):
        self.assertTrue(ollama_model_manager.ensure_default_server_running())
        start.assert_not_called()

    @patch('fruth_runtime.ollama_model_manager.is_port_listening', side_effect=lambda port: port == 11436)
    def test_model_instance_allocation_skips_registered_and_occupied_ports(self, _listening):
        self.assertEqual(
            ollama_model_manager.find_free_port(start=11435, end=11440, used_ports={11435}),
            11437,
        )

    @patch('fruth_runtime.ollama_model_manager.time.sleep', return_value=None)
    @patch('fruth_runtime.ollama_model_manager.subprocess.Popen')
    @patch('fruth_runtime.ollama_model_manager.is_port_listening', side_effect=[False, True])
    @patch('fruth_runtime.ollama_model_manager.inspect_listener', return_value=SimpleNamespace(
        pid=33333, record={'backend': 'ollama', 'runtime_service': 'ollama_default'}))
    def test_ensure_default_server_running_rotates_default_server_log(
        self,
        _owned,
        _mock_is_port_listening,
        mock_popen,
        _mock_sleep,
    ):
        mock_popen.return_value = SimpleNamespace(pid=33333)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / 'logs'
            log_dir.mkdir(parents=True, exist_ok=True)
            stale_log = log_dir / 'ollama_default_server_11434.log'
            stale_log.write_text('old default\n', encoding='utf-8')

            with patch.object(ollama_model_manager, 'LOG_DIR', log_dir), \
                    patch.object(ollama_model_manager, 'CONFIG_FILE', Path(tmpdir) / 'model_ports.json'):
                ok = ollama_model_manager.ensure_default_server_running()
                self.assertTrue(ok)
                self.assertTrue(stale_log.exists())
                self.assertEqual(stale_log.read_text(encoding='utf-8'), '')
                archived_logs = list((log_dir / 'archive' / 'global').rglob('*.log'))
                self.assertEqual(len(archived_logs), 1)
                record, = ollama_model_manager.read_config()
                self.assertEqual(record['pid'], 33333)
                self.assertEqual(record['runtime_service'], 'ollama_default')
                self.assertIn('process_identity', record)
                self.assertIn('server_command', record)

    @patch('fruth_runtime.ollama_model_manager._observed_server_version', return_value='0.40.6')
    @patch('fruth_runtime.ollama_model_manager.wait_for_model_loaded', return_value=True)
    @patch('fruth_runtime.ollama_model_manager._fetch_model_metadata', return_value={})
    @patch('fruth_runtime.ollama_model_manager.is_port_listening', return_value=True)
    @patch('fruth_runtime.ollama_model_manager.subprocess.Popen')
    @patch('fruth_runtime.ollama_model_manager.time.sleep', return_value=None)
    @patch('fruth_runtime.ollama_model_manager.find_free_port', return_value=11435)
    @patch('fruth_runtime.ollama_model_manager.allocate_instance_id', return_value='qwen3-coder:latest-1')
    def test_start_model_records_active_ollama_instance_log_path(
        self,
        _mock_allocate_instance_id,
        _mock_find_free_port,
        _mock_sleep,
        mock_popen,
        _mock_is_port_listening,
        _mock_fetch_model_metadata,
        _mock_wait_for_model_loaded,
        _mock_server_version,
    ):
        mock_popen.side_effect = [
            SimpleNamespace(pid=11111),
            SimpleNamespace(pid=22222, terminate=lambda: None),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / 'logs'
            with patch.object(ollama_model_manager, 'LOG_DIR', log_dir):
                result = ollama_model_manager.start_model(
                    'qwen3-coder:latest',
                    used_ports=set(),
                    existing_instances=[],
                    capability='chat',
                    start_source='api_start_model',
                )

        self.assertIsNotNone(result)
        self.assertEqual(result['port'], 11435)
        self.assertEqual(
            result['log'],
            str(log_dir / 'ollama_server_qwen3-coder_latest-1_11435.log'),
        )
        self.assertEqual(result['start_source'], 'api_start_model')


if __name__ == '__main__':
    unittest.main()



@pytest.fixture(autouse=True)
def _mock_native_launch_evidence(monkeypatch):
    # This module mocks native launches; test the ownership OS boundary separately.
    mock_launch_ownership(monkeypatch, _ownership_owner_0)
