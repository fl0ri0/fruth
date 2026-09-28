import unittest
from unittest.mock import patch

from fruth_core.backend_fabric import build_backend_fabric_snapshot
from fruth_runtime import apple_pcc_model_manager as pcc


class BackendFabricTests(unittest.TestCase):
    def setUp(self):
        pcc = patch('fruth_core.backend_fabric.describe_apple_pcc_runtime_probe',
                    return_value={'runtime_state': 'missing', 'issues': []})
        pcc.start()
        self.addCleanup(pcc.stop)
        afm = patch('fruth_core.backend_fabric.describe_apple_fm_runtime_probe',
                    return_value={'runtime_state': 'missing', 'issues': []})
        afm.start()
        self.addCleanup(afm.stop)
    @patch('fruth_core.backend_fabric.describe_llama_cpp_runtime_probe')
    @patch('fruth_core.backend_fabric.describe_mlx_runtime_variants')
    @patch('fruth_core.backend_fabric.describe_ollama_runtime_probe')
    def test_snapshot_reports_runtime_and_wiring_states(
        self,
        mock_ollama_probe,
        mock_mlx_variants,
        mock_llama_cpp_probe,
    ):
        mock_ollama_probe.return_value = {
            'backend_id': 'ollama',
            'family': 'ollama',
            'variant': 'ollama',
            'label': 'Ollama',
            'runtime_state': 'runnable',
            'operations': {'discover': True, 'start_instance': True},
            'detection': {'cli_detected': True},
            'issues': [],
        }
        mock_llama_cpp_probe.return_value = {
            'backend_id': 'llama_cpp',
            'family': 'llama.cpp',
            'variant': 'llama_cpp',
            'label': 'llama.cpp',
            'runtime_state': 'runnable',
            'operations': {'discover': True, 'start_instance': True},
            'detection': {'server_detected': True, 'cli_detected': True},
            'issues': [],
        }
        mock_mlx_variants.return_value = {
            'mlx_lm': {
                'backend_id': 'mlx_lm',
                'family': 'mlx',
                'variant': 'mlx_lm',
                'label': 'MLX LM',
                'runtime_state': 'runnable',
                'operations': {'discover': True, 'start_instance': True},
                'detection': {'python_resolved': True},
                'issues': [],
            },
            'mlx_vlm': {
                'backend_id': 'mlx_vlm',
                'family': 'mlx',
                'variant': 'mlx_vlm',
                'label': 'MLX VLM',
                'runtime_state': 'degraded',
                'operations': {'discover': True, 'start_instance': False},
                'detection': {'python_resolved': True, 'runtime_module_available': False},
                'issues': ['mlx_vlm missing'],
            },
            'mlx_audio': {
                'backend_id': 'mlx_audio',
                'family': 'mlx',
                'variant': 'mlx_audio',
                'label': 'MLX Audio',
                'runtime_state': 'runnable',
                'operations': {'discover': True, 'start_instance': True},
                'detection': {'python_resolved': True},
                'issues': [],
            },
            'mlx_whisper': {
                'backend_id': 'mlx_whisper',
                'family': 'mlx',
                'variant': 'mlx_whisper',
                'label': 'MLX Whisper',
                'runtime_state': 'missing',
                'operations': {'discover': True, 'start_instance': False},
                'detection': {'python_resolved': False},
                'issues': ['mlx_whisper missing'],
            },
        }

        payload = build_backend_fabric_snapshot(
            instances=[
                {'instance_id': 'gemma4:26b-1', 'backend': 'ollama', 'model': 'gemma4:26b'},
                {
                    'instance_id': 'mlx-community__Qwen3-TTS-12Hz-0.6B-Base-bf16-mlx-11502',
                    'backend': 'mlx',
                    'backend_package': 'mlx_audio',
                    'model': 'mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16',
                },
            ],
            available_models=[
                {'backend': 'ollama', 'model': 'gemma4:26b'},
                {
                    'backend': 'llama_cpp',
                    'backend_package': 'llama_cpp',
                    'model': 'gemma-3-1b-it-Q4_K_M',
                    'runnable': True,
                },
                {'backend': 'mlx', 'backend_package': 'mlx_lm', 'model': 'mlx-community/Qwen3.5-9B-MLX-4bit'},
                {
                    'backend': 'mlx',
                    'backend_package': 'mlx_vlm',
                    'model': 'mlx-community/GLM-OCR-bf16',
                    'runnable': False,
                    'disabled_reason': 'Required runtime module is not importable.',
                },
            ],
        )

        by_id = {item['backend_id']: item for item in payload['backends']}
        self.assertEqual(by_id['ollama']['runtime_state'], 'runnable')
        self.assertEqual(by_id['ollama']['auto_wiring_state'], 'active')
        self.assertEqual(by_id['llama_cpp']['runtime_state'], 'runnable')
        self.assertEqual(by_id['llama_cpp']['auto_wiring_state'], 'discoverable')
        self.assertEqual(by_id['mlx_lm']['auto_wiring_state'], 'discoverable')
        self.assertEqual(by_id['mlx_vlm']['runtime_state'], 'degraded')
        self.assertEqual(by_id['mlx_vlm']['catalog']['cached_only_model_count'], 1)
        self.assertIn('Required runtime module is not importable.', by_id['mlx_vlm']['issues'])
        self.assertEqual(by_id['mlx_audio']['auto_wiring_state'], 'active')
        self.assertEqual(by_id['mlx_whisper']['runtime_state'], 'missing')
        self.assertEqual(payload['summary']['runtime_runnable_backend_count'], 4)
        self.assertEqual(payload['summary']['runtime_degraded_backend_count'], 1)
        self.assertEqual(payload['summary']['runtime_missing_backend_count'], 3)
        self.assertEqual(payload['summary']['wiring_active_backend_count'], 2)
        self.assertEqual(payload['summary']['wiring_discoverable_backend_count'], 2)


class PassivePCCFabricTests(unittest.TestCase):
    def test_afm_only_snapshots_do_not_contact_shortcuts_or_native_pcc_metadata(self):
        with (
            patch.object(pcc, '_shortcut_installation_observation', None),
            patch.object(pcc, 'list_pcc_shortcuts', side_effect=AssertionError('Unrequested Shortcuts discovery')) as listing,
            patch.object(pcc, 'pcc_sdk_metadata', side_effect=AssertionError('Unrequested PCC metadata')) as sdk,
            patch('fruth_core.backend_fabric.describe_apple_fm_runtime_probe', return_value={'runtime_state': 'runnable'}),
            patch('fruth_core.backend_fabric.describe_ollama_runtime_probe', return_value={'runtime_state': 'missing'}),
            patch('fruth_core.backend_fabric.describe_llama_cpp_runtime_probe', return_value={'runtime_state': 'missing'}),
            patch('fruth_core.backend_fabric.describe_mlx_runtime_variants', return_value={}),
        ):
            for _ in range(3):
                snapshot = build_backend_fabric_snapshot(instances=[
                    {'instance_id': 'apple_fm:system:11601', 'backend': 'apple_fm', 'model': 'system'}])
                item = next(item for item in snapshot['backends'] if item['backend_id'] == 'apple_pcc')
                self.assertEqual(item['detection']['status'], 'not_observed')
                self.assertIsNone(item['detection']['observed_at'])
                self.assertFalse(item['auto_wireable'])
            listing.assert_not_called()
            sdk.assert_not_called()


if __name__ == '__main__':
    unittest.main()
