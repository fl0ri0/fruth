import pytest
from process_launch_test_support import mock_launch_ownership
import fruth_runtime.mlx_model_manager as _ownership_owner_0
import fruth_runtime.llama_cpp_model_manager as _ownership_owner_1

from types import SimpleNamespace
"""Offline text-embedding contracts across existing backend owners."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from helpers.tts_model_metadata import read_snapshot_model_metadata
from fruth_core.status import _fetch_backend_runtime_metadata
from fruth_inference.router import (
    build_embedding_hints_from_vectors,
    select_embedding_instance,
    validate_embedding_batch,
)
from fruth_runtime import llama_cpp_model_manager as llama
from fruth_runtime import mlx_model_manager as mlx
from fruth_server.inference_route_runtime import InferenceRouteRuntimeOwner


def helper(backend='mlx', instance_id='helper', model='encoder'):
    return {
        'instance_id': instance_id, 'model': model, 'request_model': '/local/encoder',
        'backend': backend, 'capability': 'embedding', 'port': 11512,
        'inputs': ['text'], 'outputs': ['embedding'],
        'runtime_status': {'readiness': 'ready', 'activity': 'idle'},
        'backend_metadata': {'native_endpoint_paths': ['/v1/embeddings']},
    }


def owner(post=None):
    runtime = InferenceRouteRuntimeOwner(
        hooks={'requests_post': post or Mock(), 'chat_timeout_seconds': lambda *_: 30,
               'candidate_matches_inference_preference': lambda *_: True},
        wrapper_capability_aliases={}, max_recent_messages=4,
    )
    runtime.hooks['execute_embedding_backend_request'] = runtime._execute_embedding_backend_request
    return runtime


def runtime_checks():
    return {'python_resolved': True, 'runtime_module_available': True,
            'runtime_dependencies_ready': True, 'python_path': '/fixture/python',
            'package_version': '0.7.8', 'embedding_endpoint_available': True}


def snapshot(root, model_type='embedding_gemma2', pipeline='feature-extraction'):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'config.json').write_text(json.dumps({'model_type': model_type, 'vision_config': {}}))
    (root / 'README.md').write_text(f'---\npipeline_tag: {pipeline}\ntags:\n  - multimodal\n---\n')
    return root


class EmbeddingBackendContractTests(unittest.TestCase):
    def test_equal_candidates_use_stable_identity_not_backend_priority(self):
        for backend in ('mlx', 'llama_cpp'):
            with self.subTest(backend=backend):
                candidates = [helper('ollama', 'a'), helper(backend, 'z')]
                for ordered in (candidates, list(reversed(candidates))):
                    self.assertEqual(select_embedding_instance(ordered)['instance_id'], 'z')
                preferred = {'backend': 'ollama', 'model': 'encoder', 'instance_id': 'a'}
                self.assertEqual(select_embedding_instance(candidates, preferred)['instance_id'], 'a')

    def test_missing_preference_preserves_existing_available_helper_fallback(self):
        self.assertEqual(select_embedding_instance(
            [helper()], {'backend': 'ollama', 'model': 'unavailable'},
        )['instance_id'], 'helper')

    def test_ready_chat_with_no_embedding_or_image_only_encoder_is_not_eligible(self):
        for changes in (
            {'capability': 'chat', 'outputs': ['text']},
            {'backend_metadata': {'native_endpoint_paths': ['/v1/chat/completions']}},
            {'inputs': ['image']},
            {'runtime_status': {'readiness': 'stopped'}},
            {'runtime_status': {'readiness': 'unreachable'}},
            {'runtime_status': {'readiness': 'failed'}},
        ):
            with self.subTest(changes=changes):
                self.assertIsNone(select_embedding_instance([{**helper(), **changes}]))

    def test_degraded_observation_alone_does_not_exclude_supported_helper(self):
        candidate = helper()
        candidate['runtime_status']['readiness'] = 'degraded'
        self.assertIsNotNone(select_embedding_instance([candidate]))

    def test_transport_preserves_unicode_prefixes_order_and_selected_model(self):
        inputs = ['task: sentence similarity | query: Grüezi 世界', 'task: sentence similarity | query: café']
        for backend, transport, body, path in (
            ('ollama', 'ollama_api_embed', {'embeddings': [[1, 0], [0, 1]]}, '/api/embed'),
            ('mlx', 'openai_embeddings', {'data': [
                {'index': 1, 'embedding': [0, 1]}, {'index': 0, 'embedding': [1, 0]},
            ]}, '/v1/embeddings'),
            ('llama_cpp', 'openai_embeddings', {'data': [
                {'index': 0, 'embedding': [1, 0]}, {'index': 1, 'embedding': [0, 1]},
            ]}, '/v1/embeddings'),
        ):
            with self.subTest(backend=backend):
                response = Mock()
                response.json.return_value = body
                post = Mock(return_value=response)
                instance = select_embedding_instance([helper(backend)])
                result = owner(post)._execute_embedding_backend_request(
                    target_port=11512, model_name='encoder', backend=backend, inputs=inputs,
                    request_model_override=instance['request_model'],
                    embedding_transport=transport, instance=instance,
                )
                self.assertEqual(result, [[1.0, 0.0], [0.0, 1.0]])
                post.assert_called_once_with(
                    'http://127.0.0.1:11512' + path,
                    json={'model': '/local/encoder', 'input': inputs}, timeout=30,
                )

    def test_ambiguous_openai_indices_are_rejected(self):
        runtime = owner()
        for indices in ((0, 0), (1, 2), (-1, 0), ('0', 1), (False, 1), (None, 1), (0.0, 1)):
            with self.subTest(indices=indices), self.assertRaises(ValueError):
                runtime._parse_embedding_backend_response(
                    {'data': [{'index': index, 'embedding': [1, 0]} for index in indices]},
                    'openai_embeddings',
                )
        with self.assertRaises(ValueError):
            runtime._parse_embedding_backend_response({'data': [None, {'index': 0, 'embedding': [1]}]}, 'openai_embeddings')

    def test_invalid_vectors_reject_the_complete_batch(self):
        for invalid in ([0, 0], [True, 1], [float('nan'), 1], [float('inf'), 1],
                        [1], ['1', 0], [[1], [0]], [], [10**1000, 0]):
            with self.subTest(invalid=str(invalid)[:50]):
                with self.assertRaises(ValueError):
                    validate_embedding_batch([[1, 0], invalid])
                self.assertIsNone(build_embedding_hints_from_vectors(
                    [1, 0], [{'kind': 'capability', 'capability': 'chat'},
                             {'kind': 'capability', 'capability': 'vision_analysis'}],
                    [[1, 0], invalid],
                ))

    def test_finite_extreme_vectors_keep_stable_cosine(self):
        for scale in (1e308, 1e-308, 1):
            with self.subTest(scale=scale):
                hints = build_embedding_hints_from_vectors(
                    [scale, scale], [{'kind': 'capability', 'capability': 'chat'}], [[scale, scale]],
                )
                score = hints['top_capabilities'][0]['score']
                self.assertTrue(math.isfinite(score))
                self.assertEqual(score, 1.0)

    def test_count_mismatch_and_nontext_inputs_fail_without_partial_results(self):
        response = Mock()
        response.json.return_value = {'embeddings': [[1, 0]]}
        post = Mock(return_value=response)
        runtime = owner(post)
        with self.assertRaises(ValueError):
            runtime._execute_embedding_backend_request(
                target_port=11512, model_name='encoder', backend='ollama', inputs=['a', 'b'],
            )
        post.reset_mock()
        with self.assertRaises(ValueError):
            runtime._execute_embedding_backend_request(
                target_port=11512, model_name='encoder', backend='ollama', inputs=[{'image': 'x'}],
            )
        post.assert_not_called()

    def test_failure_refresh_removes_stale_hints_and_records_fallback(self):
        candidates = [{'kind': 'capability', 'capability': 'chat', 'text': 'chat'}]
        for failure in ('unavailable', 'timeout', 'http', 'malformed'):
            with self.subTest(failure=failure):
                response = Mock()
                response.json.return_value = {'data': [{'index': 0, 'embedding': [float('nan')]}]}
                post = Mock(return_value=response)
                if failure == 'timeout':
                    post.side_effect = TimeoutError('bounded fixture timeout')
                if failure == 'http':
                    response.raise_for_status.side_effect = RuntimeError('HTTP fixture failure')
                runtime = owner(post)
                context = {'prompt': 'hello', 'runtime': {'embedding_hints': {'old_model': 'old'}}}
                with patch('fruth_server.inference_route_runtime.build_embedding_route_candidates', return_value=candidates):
                    runtime.attach_embedding_hints_to_route_context(
                        context, runtime_manifest={}, instances=[] if failure == 'unavailable' else [helper()],
                    )
                self.assertNotIn('embedding_hints', context['runtime'])
                status = context['runtime']['embedding_helper']
                self.assertFalse(status['attached'])
                self.assertEqual(status['reason'], 'no_supported_embedding_helper' if failure == 'unavailable' else 'helper_execution_failed')
                self.assertLessEqual(post.call_count, 1)

    def test_helper_attaches_same_valid_hint_through_each_backend(self):
        candidates = [
            {'kind': 'capability', 'capability': 'chat', 'text': 'conversation'},
            {'kind': 'capability', 'capability': 'vision_analysis', 'text': 'read image'},
        ]
        vectors = [[1, 0], [1, 0], [0, 1]]
        for backend in ('ollama', 'mlx', 'llama_cpp'):
            with self.subTest(backend=backend):
                response = Mock()
                response.json.return_value = (
                    {'embeddings': vectors} if backend == 'ollama' else
                    {'data': [{'index': i, 'embedding': vectors[i]} for i in (2, 0, 1)]}
                )
                post = Mock(return_value=response)
                context = {'prompt': 'hello', 'runtime': {}}
                with patch('fruth_server.inference_route_runtime.build_embedding_route_candidates', return_value=candidates):
                    owner(post).attach_embedding_hints_to_route_context(context, runtime_manifest={}, instances=[helper(backend)])
                self.assertTrue(context['runtime']['embedding_helper']['attached'])
                self.assertEqual(context['runtime']['embedding_helper']['backend'], backend)
                hints = context['runtime']['embedding_hints']
                self.assertEqual(hints['top_capabilities'][0]['capability'], 'chat')
                self.assertEqual(hints['embedding_model'], 'encoder')
                self.assertEqual(post.call_args.kwargs['json'], {
                    'model': '/local/encoder', 'input': ['hello', 'conversation', 'read image'],
                })
                self.assertEqual(post.call_count, 1)

    def test_metadata_recognizes_embedding_before_vision_but_not_names_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for kind, pipeline in (('embedding_gemma2', ''), ('qwen3', 'feature-extraction'), ('gemma3_text', 'sentence-similarity')):
                with self.subTest(kind=kind):
                    snapshot(root, kind, pipeline)
                    metadata = read_snapshot_model_metadata('neutral-name', str(root))
                    self.assertEqual(metadata['provider_capabilities'], ['embedding'])
                    self.assertEqual(metadata['inputs'], ['text'])
                    self.assertEqual(metadata['outputs'], ['embedding'])
            (root / 'README.md').unlink()
            (root / 'config.json').write_text('{"model_type": "qwen3"}')
            self.assertNotIn('provider_capabilities', read_snapshot_model_metadata('embedding-name', str(root)))

    def test_mlx_discovery_record_selection_and_no_chat_advertisement(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(mlx, '_mlx_package_runtime_check', return_value=runtime_checks()), \
             patch.object(mlx, '_python_module_available', return_value=True):
            cache = Path(temp)
            root = snapshot(cache / 'models--fixture--encoder' / 'snapshots' / 'revision')
            with patch.object(mlx, 'CACHE_DIR', cache):
                discovered = mlx.find_hf_cached_models()
            self.assertEqual(len(discovered), 1)
            self.assertTrue(discovered[0]['runnable'])
            self.assertEqual(discovered[0]['mlx_server'], 'mlx_vlm')
            record = mlx.build_instance_record('fixture/encoder', str(root), 11512, cache / 'fixture.log')
            record['runtime_status'] = {'readiness': 'ready', 'activity': 'idle'}
            selected = select_embedding_instance([record])
            self.assertEqual(selected['embedding_transport'], 'openai_embeddings')
            self.assertEqual(selected['request_model'], str(root))
            self.assertEqual(record['supported_capabilities'], ['embedding'])
            self.assertFalse(record['text_capable'])
            self.assertNotIn('/v1/chat/completions', record['backend_metadata']['native_endpoint_paths'])
            with patch('fruth_core.status._fetch_json') as fetch:
                runtime_metadata = _fetch_backend_runtime_metadata(record)
            fetch.assert_not_called()
            self.assertEqual(runtime_metadata['embeddings_url'], 'http://127.0.0.1:11512/v1/embeddings')
            self.assertNotIn('chat_completions_url', runtime_metadata)

    def test_mlx_discovery_rejects_missing_endpoint_model_module_or_unknown_type(self):
        for change, model_type, module_available in (
            ({'embedding_endpoint_available': False}, 'embedding_gemma2', True),
            ({}, 'embedding_gemma2', False), ({}, 'gemma4', True), ({}, '', True),
        ):
            with self.subTest(change=change, model_type=model_type, module_available=module_available), \
                 patch.object(mlx, '_mlx_package_runtime_check', return_value={**runtime_checks(), **change}), \
                 patch.object(mlx, '_python_module_available', return_value=module_available):
                details = mlx._mlx_discovery_details(
                    'fixture/encoder', 'embedding', config_present=True,
                    metadata={'snapshot_model_type': model_type},
                )
                self.assertFalse(details['runnable'])
                self.assertEqual(details['discovery_state'], 'cached_only')
                self.assertTrue(details['disabled_reason'])

    def test_old_mlx_package_does_not_advertise_an_embedding_endpoint(self):
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={**runtime_checks(), 'embedding_endpoint_available': False}):
            details = mlx._mlx_contract_details('fixture/encoder', 'embedding')
        record = {**helper(), **details}
        self.assertIsNone(select_embedding_instance([record]))

    def test_mlx_runtime_checks_require_both_embedding_server_and_loader(self):
        for missing in ('', 'mlx_vlm.server.embeddings', 'mlx_vlm.embedding_loader'):
            with self.subTest(missing=missing):
                mlx._mlx_package_runtime_check.cache_clear()
                try:
                    with patch.object(mlx, 'resolve_mlx_python', return_value='/fixture/python'), \
                         patch.object(mlx, '_python_package_version', return_value='0.7.8'), \
                         patch.object(mlx, '_python_module_available', side_effect=lambda _python, module: module != missing):
                        checks = mlx._mlx_package_runtime_check('mlx_vlm')
                    self.assertEqual(checks['embedding_endpoint_available'], not bool(missing))
                finally:
                    mlx._mlx_package_runtime_check.cache_clear()

    def test_mlx_embedding_remap_uses_encoder_not_generation_module(self):
        with patch.object(mlx, '_mlx_package_runtime_check', return_value=runtime_checks()), \
             patch.object(mlx, '_python_module_available', return_value=True) as available:
            details = mlx._mlx_discovery_details('fixture/encoder', 'embedding', config_present=True,
                                                metadata={'snapshot_model_type': 'qwen3'})
        self.assertTrue(details['runnable'])
        available.assert_called_once_with('/fixture/python', 'mlx_vlm.models.qwen3_embedding')

    def test_token_embedding_layout_remains_cached_only(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(mlx, '_mlx_package_runtime_check', return_value=runtime_checks()):
            root = snapshot(Path(temp), model_type='lfm2')
            (root / '1_Dense').mkdir()
            (root / '1_Dense' / 'config.json').write_text('{"out_features": 128}')
            metadata = read_snapshot_model_metadata('fixture/encoder', str(root))
            details = mlx._mlx_discovery_details('fixture/encoder', 'embedding', config_present=True, metadata=metadata)
            self.assertFalse(details['runnable'])

    def test_mlx_embedding_start_and_launcher_bind_exact_local_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = snapshot(Path(temp) / 'model')
            with patch.object(mlx, 'find_mlx_snapshots', return_value=[{'repo': 'fixture/encoder', 'path': str(root)}]), \
                 patch.object(mlx, 'port_in_use', return_value=False), \
                 patch.object(mlx, '_mlx_package_runtime_check', return_value=runtime_checks()), \
                 patch.object(mlx, '_python_module_available', return_value=True), \
                 patch.object(mlx, 'wait_for_port', return_value=True), \
                 patch.object(mlx, 'launch_vlm_server', return_value=(Path(temp) / 'launch.log', SimpleNamespace(pid=123))) as launch, \
                 patch.object(mlx, 'launch') as launch_chat, \
                 patch.object(mlx, 'schedule_recent_mlx_instance_reconciliation'), \
                 patch.object(mlx, 'register_mlx_instance') as register:
                record = mlx.start_mlx_model('fixture/encoder', preferred_port=11512,
                                            register_instance=False, prune_registry=False,
                                            start_source='api_start_model')
                launch.assert_called_once_with(11512, embedding_model=str(root))
                launch_chat.assert_not_called()
                register.assert_not_called()
                self.assertEqual(record['request_model'], str(root))
                with self.assertRaisesRegex(ValueError, 'generation launch controls'):
                    mlx.start_mlx_model('fixture/encoder', preferred_port=11512,
                                        register_instance=False, prune_registry=False,
                                        launch_defaults={'kv_bits': 4}, start_source='api_start_model')
                self.assertEqual(launch.call_count, 1)
                with patch.object(mlx, '_mlx_package_runtime_check', return_value={**runtime_checks(), 'embedding_endpoint_available': False}):
                    with self.assertRaisesRegex(RuntimeError, 'embedding endpoint/loader'):
                        mlx.start_mlx_model('fixture/encoder', preferred_port=11512,
                                            register_instance=False, prune_registry=False,
                                            start_source='api_start_model')
                self.assertEqual(launch.call_count, 1)
            with patch.object(mlx, 'LOG_DIR', Path(temp)), \
                 patch.object(mlx, 'resolve_mlx_python', return_value='/fixture/python'), \
                 patch.object(mlx.subprocess, 'Popen') as popen:
                mlx.launch_vlm_server(11512, embedding_model=str(root))
            cmd = popen.call_args.args[0]
            self.assertEqual(cmd[cmd.index('--embedding-model') + 1], str(root))
            self.assertNotIn('--model', cmd)
            self.assertNotIn('--kv-bits', cmd)

    def test_llama_embedding_contract_is_not_chat(self):
        with tempfile.TemporaryDirectory() as temp:
            root = snapshot(Path(temp) / 'models--fixture--encoder' / 'snapshots' / 'revision')
            model = root / 'encoder.gguf'
            model.write_bytes(b'fixture-not-a-model')
            for declared in (None, 'embedding', 'chat'):
                with self.subTest(declared=declared):
                    record = llama.build_instance_record(
                        'fixture/encoder', source_kind='local_gguf', port=11512,
                        log_path=root / 'fixture.log', capability=declared, model_path=str(model),
                    )
                    self.assertEqual(record['supported_capabilities'], ['embedding'])
                    self.assertEqual(record['outputs'], ['embedding'])
                    self.assertEqual(record['inputs'], ['text'])
                    record['runtime_status'] = {'readiness': 'ready'}
                    self.assertEqual(select_embedding_instance([record])['embedding_transport'], 'openai_embeddings')
                    with patch('fruth_core.status._fetch_json', return_value={'data': [{'id': 'encoder'}]}):
                        metadata = _fetch_backend_runtime_metadata(record)
                    self.assertIn('embeddings_url', metadata)
                    self.assertNotIn('chat_completions_url', metadata)
            (root / 'README.md').unlink()
            (root / 'config.json').unlink()
            record = llama.build_instance_record('standalone', source_kind='local_gguf', port=11512,
                                                log_path=root / 'fixture.log', capability='embedding', model_path=str(model))
            self.assertEqual(record['supported_capabilities'], ['embedding'])

    def test_llama_unbound_sibling_readme_does_not_reclassify_standalone_gguf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = snapshot(Path(temp))
            model = root / 'unrelated-chat.gguf'
            model.write_bytes(b'fixture-not-a-model')
            record = llama.build_instance_record('unrelated-chat', source_kind='local_gguf',
                                                port=11512, log_path=root / 'fixture.log', model_path=str(model))
            self.assertEqual(record['capability'], 'chat')
            self.assertNotIn('embedding', record['provider_capabilities'])

    def test_llama_snapshot_discovery_and_start_use_embedding_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            root = snapshot(Path(temp) / 'models--fixture--encoder' / 'snapshots' / 'revision')
            model = root / 'encoder.gguf'
            model.write_bytes(b'fixture-not-a-model')
            with patch.object(llama, '_local_gguf_entries', return_value=[model]), \
                 patch.object(llama, 'describe_llama_cpp_runtime_probe', return_value={'runtime_state': 'runnable'}):
                items = llama.list_local_gguf_models()
            self.assertEqual(items[0]['capability'], 'embedding')
            with patch.object(llama, 'LOG_DIR', root), \
                 patch.object(llama, 'resolve_llama_server_bin', return_value='/fixture/llama-server'), \
                 patch.object(llama, '_prune_stale_llama_cpp_entries'), \
                 patch.object(llama, '_next_free_port', return_value=11512), \
                 patch.object(llama, '_resolve_model_source', return_value={
                     'display_name': 'fixture/encoder', 'source_kind': 'local_gguf', 'model_path': str(model)}), \
                 patch.object(llama, '_llama_cpp_launch_defaults', return_value={}), \
                 patch.object(llama, '_wait_for_server_ready', return_value=True), \
                 patch.object(llama.subprocess, 'Popen', return_value=Mock(pid=123)) as popen:
                record = llama.start_llama_cpp_instance('fixture/encoder', register_instance=False, capability='chat',
                                                    start_source='api_start_model')
            self.assertIn('--embedding', popen.call_args.args[0])
            self.assertEqual(record['capability'], 'embedding')


if __name__ == '__main__':
    unittest.main()



@pytest.fixture(autouse=True)
def _mock_native_launch_evidence(monkeypatch):
    # This module mocks native launches; test the ownership OS boundary separately.
    mock_launch_ownership(monkeypatch, _ownership_owner_0, _ownership_owner_1)
