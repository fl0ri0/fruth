"""Native loader discovery contracts, with no native models or production state."""
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from helpers.image_model_metadata import read_image_snapshot_metadata, image_snapshot_fingerprint
from helpers.mlx_image_probe import describe_image_loaders
from fruth_runtime import mlx_model_manager as mlx


class FutureLoader:
    model_type = 'future_image_family'

    @classmethod
    def supports_model(cls, model):
        return Path(model, 'model_index.json').is_file()

    @classmethod
    def resolve_defaults(cls, model, *, model_path):
        assert model == str(model_path)
        return SimpleNamespace(steps=7, guidance=1.0)


class ImageLoaderDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (self.root/'model_index.json').write_text('{"_class_name":"FutureImagePipeline"}')
        (self.root/'weights.safetensors').write_bytes(b'fixture; never loaded')
        mlx._cached_mlx_image_loader.cache_clear()
        self.addCleanup(mlx._cached_mlx_image_loader.cache_clear)

    def test_new_family_and_renamed_model_need_no_model_name_allowlist(self):
        support = describe_image_loaders(self.root, lambda p: FutureLoader, lambda p: None)
        self.assertEqual(support['family'], 'future_image_family')
        self.assertEqual(support['modes'], ['generate'])
        self.assertEqual(support['defaults']['generate'], {'steps': 7, 'guidance': 1.0})
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={
                'image_endpoint_available': True, 'python_path': '/native/python', 'package_version': 'test'}), \
                patch.object(mlx, '_probe_mlx_image_loader', return_value=support):
            for name in ('community/artist-checkpoint', 'anything/renamed'):
                meta = mlx._read_mlx_snapshot_metadata(name, str(self.root))
                self.assertTrue(meta['snapshot_image_supported'])
                self.assertEqual(meta['inputs'], ['text'])
                self.assertEqual(meta['snapshot_model_type'], 'future_image_family')

    def test_generation_and_edit_are_independent_native_contracts(self):
        both = describe_image_loaders(self.root, lambda p: FutureLoader, lambda p: FutureLoader)
        self.assertEqual(both['modes'], ['generate', 'edit'])
        self.assertEqual(both['defaults']['edit']['steps'], 7)
        with self.assertRaisesRegex(ValueError, 'no generation loader'):
            describe_image_loaders(self.root, lambda p: None, lambda p: FutureLoader)

    def test_native_config_model_key_reaches_probe_after_manual_download(self):
        (self.root / 'model_index.json').unlink()
        (self.root / 'config.json').write_text('{"model":"future-diffusion-family", "dit":{}, "vae":{}}')
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={
                'image_endpoint_available': True, 'python_path': '/native/python'}), \
                patch.object(mlx, '_probe_mlx_image_loader', return_value={'error': 'Installed loader has no support'}) as probe:
            meta = mlx._read_mlx_snapshot_metadata('manually/renamed', str(self.root))
        probe.assert_called_once()
        self.assertFalse(meta['snapshot_image_supported'])
        self.assertEqual(meta['snapshot_image_issues'], ['Installed loader has no support'])

    def test_name_or_metadata_alone_cannot_make_a_checkpoint_runnable(self):
        meta = read_image_snapshot_metadata('official/famous-image', self.root)
        self.assertFalse(meta['snapshot_image_supported'])
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={
                'image_endpoint_available': True, 'python_path': '/native/python'}), \
                patch.object(mlx, '_probe_mlx_image_loader', return_value={'error': 'No native loader'}):
            meta = mlx._read_mlx_snapshot_metadata('official/famous-image', str(self.root))
            self.assertFalse(meta['snapshot_image_supported'])
            self.assertEqual(meta['snapshot_image_issues'], ['No native loader'])

    def test_missing_shard_blocks_before_native_probe_and_fingerprint_changes(self):
        before = image_snapshot_fingerprint(self.root)
        (self.root/'model.safetensors.index.json').write_text(json.dumps({'weight_map': {'x': 'missing.safetensors'}}))
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={}), \
                patch.object(mlx, '_probe_mlx_image_loader') as probe:
            meta = mlx._read_mlx_snapshot_metadata('new', str(self.root))
        probe.assert_not_called()
        self.assertIn('Missing checkpoint shard', meta['snapshot_image_issues'][0])
        self.assertNotEqual(before, image_snapshot_fingerprint(self.root))
        missing = image_snapshot_fingerprint(self.root)
        (self.root/'missing.safetensors').write_bytes(b'completed')
        self.assertNotEqual(missing, image_snapshot_fingerprint(self.root))

    def test_native_probe_is_bounded_offline_cached_and_checkpoint_sensitive(self):
        support = describe_image_loaders(self.root, lambda p: FutureLoader, lambda p: None)
        result = SimpleNamespace(returncode=0, stdout=json.dumps({'schema': 1, 'support': support}))
        with patch.object(mlx.subprocess, 'run', return_value=result) as execute:
            stamp = image_snapshot_fingerprint(self.root)
            for _ in range(2):
                self.assertEqual(mlx._probe_mlx_image_loader('/native/python', str(self.root), 'v1', stamp), support)
            self.assertEqual(execute.call_count, 1)
            args, kwargs = execute.call_args
            self.assertIn('-I', args[0]); self.assertIn('-B', args[0])
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertEqual(kwargs['timeout'], mlx.MLX_IMAGE_DISCOVERY_TIMEOUT_SEC)
            (self.root/'weights.safetensors').write_bytes(b'completed larger weight fixture')
            mlx._probe_mlx_image_loader('/native/python', str(self.root), 'v1', image_snapshot_fingerprint(self.root))
            self.assertEqual(execute.call_count, 2)

    def test_bad_native_response_or_timeout_does_not_advertise_support(self):
        for result in (SimpleNamespace(returncode=0, stdout='broken'),
                       SimpleNamespace(returncode=1, stdout='{"schema":1,"error":"not supported"}')):
            mlx._cached_mlx_image_loader.cache_clear()
            with patch.object(mlx.subprocess, 'run', return_value=result):
                self.assertIn('error', mlx._probe_mlx_image_loader('/python', str(self.root), 'v', ()))
        mlx._cached_mlx_image_loader.cache_clear()
        with patch.object(mlx.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 30)):
            self.assertIn('error', mlx._probe_mlx_image_loader('/python', str(self.root), 'v', ()))

    def test_transient_failure_does_not_stick_on_next_refresh(self):
        support = describe_image_loaders(self.root, lambda p: FutureLoader, lambda p: None)
        with patch.object(mlx.subprocess, 'run', side_effect=[
                subprocess.TimeoutExpired('probe', 30),
                SimpleNamespace(returncode=0, stdout=json.dumps({'schema': 1, 'support': support}))]) as run:
            self.assertIn('error', mlx._probe_mlx_image_loader('/python', str(self.root), 'v', ()))
            self.assertEqual(mlx._probe_mlx_image_loader('/python', str(self.root), 'v', ()), support)
        self.assertEqual(run.call_count, 2)

    def test_unavailable_edit_defaults_do_not_disable_generation(self):
        class BrokenEdit(FutureLoader):
            @classmethod
            def resolve_defaults(cls, model, *, model_path):
                raise ValueError('edit component missing')
        result = describe_image_loaders(self.root, lambda p: FutureLoader, lambda p: BrokenEdit)
        self.assertEqual(result['modes'], ['generate'])
        self.assertEqual(result['operation_issues']['edit'], 'edit component missing')

    def test_explicit_weight_manifest_can_use_nonstandard_component_directories(self):
        (self.root/'model_index.json').write_text(json.dumps({
            '_class_name': 'FutureImagePipeline', 'transformer': ['diffusers', 'Transformer'],
        }))
        (self.root/'manifest.json').write_text(json.dumps({'files': ['weights.safetensors']}))
        meta = read_image_snapshot_metadata('community/packed', self.root)
        self.assertEqual(meta['snapshot_image_prerequisite_issues'], [])
        (self.root/'weights.safetensors').unlink()
        self.assertTrue(read_image_snapshot_metadata('community/packed', self.root)['snapshot_image_prerequisite_issues'])
