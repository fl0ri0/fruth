"""Isolated image adapter contracts; no native weights, services or inference."""

import base64
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import requests

from fruth_core.image_generation import ImageAdapterError, ImageRequest, mlx_vlm_image_request, select_image_adapter
from fruth_core.inference import InferArtifacts, InferContext, dispatch_infer_request
from fruth_core.status import _fetch_backend_runtime_metadata
from fruth_core.transports import ollama_openai_image_generation
from fruth_runtime import mlx_model_manager as mlx
from helpers.tts_model_metadata import read_snapshot_model_metadata
from helpers.model_capabilities import build_registry_metadata


def png(width=256, height=256):
    stream = io.BytesIO()
    Image.new('RGB', (width, height), (20, 90, 150)).save(stream, format='PNG')
    return stream.getvalue()


def native_response(seed=42):
    return {'data': [{'b64_json': base64.b64encode(png()).decode(),
                      'width': 256, 'height': 256, 'seed': seed, 'mime_type': 'image/png'}]}


def transport(body=None, callback=None):
    response = Mock()
    response.json.return_value = native_response() if body is None else body
    client = Mock()
    client.post.side_effect = callback or (lambda *args, **kwargs: response)
    return client, response


def snapshot(root, family='flux2', *, complete=True):
    root.mkdir(parents=True, exist_ok=True)
    if family == 'flux2':
        pipeline = 'Flux2KleinPipeline'
        transformer = {'num_layers': 5, 'num_single_layers': 20, 'num_attention_heads': 24, 'joint_attention_dim': 7680}
        tokenizer = 'tokenizer'
    else:
        pipeline = 'QwenImage21Pipeline'
        transformer = {'num_layers': 32, 'num_attention_heads': 32, 'attention_head_dim': 128, 'context_in_dim': 4096}
        tokenizer = 'processor'
    (root / 'model_index.json').write_text(json.dumps({'_class_name': pipeline, **{key: ['fixture', key] for key in ('transformer', 'text_encoder', 'vae')}}))
    for component in ('transformer', 'text_encoder', 'vae'):
        directory = root / component
        directory.mkdir()
        (directory / 'config.json').write_text(json.dumps(transformer if component == 'transformer' else {'synthetic': True}))
        if complete:
            (directory / 'weights.safetensors').write_bytes(b'synthetic prerequisite only')
    (root / tokenizer).mkdir()
    (root / tokenizer / 'tokenizer.json').write_text('{}')
    return root


def native_loader_fixture(python, path, version, fingerprint):
    pipeline = json.loads((Path(path) / 'model_index.json').read_text())['_class_name']
    family = {'Flux2KleinPipeline': 'flux2', 'QwenImage21Pipeline': 'qwen_image',
              'ZImagePipeline': 'z_image'}.get(pipeline)
    if not family:
        return {'error': 'No installed loader for fixture pipeline.'}
    return {'family': family, 'modes': ['generate', 'edit'], 'steps_min': 2 if family == 'z_image' else 1,
            'defaults': {'generate': {'steps': 9 if family == 'z_image' else 30, 'guidance': 1.0}},
            'generation_class': 'synthetic.native.ImageLoader'}


def checks():
    return {'python_resolved': True, 'runtime_module_available': True, 'python_path': '/mock/python',
            'image_endpoint_available': True, 'package_version': '0.7.8'}


def context():
    return InferContext(
        instance_id='image', backend='mlx', capability='image_generation', model_name='display',
        request_model='/local/snapshot', port=11501, prompt='a blue bird', user_prompt='a blue bird',
        infer_timeout_sec=37, pdf_page_timeout_sec=60, pdf_max_image_side=2400, pdf_synthesize=False,
        backend_package='mlx_vlm', backend_metadata={'image_transport': 'mlx_vlm_images_v1', 'image_modes': ['generate', 'edit']},
        image_width=256, image_height=256, image_seed=42,
    )


class ImageBackendContractTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(mlx, '_probe_mlx_image_loader', side_effect=native_loader_fixture))
        self.enterContext(patch.object(mlx, '_mlx_package_runtime_check', return_value=checks()))

    def test_optional_steps_reach_native_generation_and_edit_unchanged(self):
        for reference in (None, base64.b64encode(png()).decode()):
            for steps in (None, 1, 20, 101):
                with self.subTest(edit=bool(reference), steps=steps):
                    client, _ = transport()
                    result = mlx_vlm_image_request(11501, ImageRequest(
                        '/local/snapshot', 'a blue bird', reference_b64=reference, steps=steps,
                    ), client)
                    sent = client.post.call_args.kwargs['json']
                    self.assertEqual(sent.get('steps'), steps)
                    self.assertEqual('steps' in sent, steps is not None)
                    evidence = result['image_execution']
                    self.assertEqual(evidence['requested_controls'].get('steps'), steps)
                    self.assertEqual(evidence['sent_controls'].get('steps'), steps)
                    self.assertNotIn('reported_steps', evidence)

    def test_invalid_native_steps_never_call_provider(self):
        for steps in (0, -1, True, 1.5, '20'):
            with self.subTest(steps=steps):
                client, _ = transport()
                with self.assertRaises(ValueError):
                    mlx_vlm_image_request(11501, ImageRequest('/local/snapshot', 'bird', steps=steps), client)
                client.post.assert_not_called()

    def test_native_generation_preserves_controls_and_exact_result(self):
        client, _ = transport()
        result = mlx_vlm_image_request(11501, ImageRequest('/local/snapshot', 'a blue bird', 256, 256, 42, timeout_sec=37), client)
        client.post.assert_called_once_with('http://127.0.0.1:11501/v1/images/generations', json={
            'model': '/local/snapshot', 'prompt': 'a blue bird', 'n': 1,
            'response_format': 'b64_json', 'output_format': 'png', 'width': 256, 'height': 256, 'seed': 42,
        }, timeout=37)
        self.assertEqual(base64.b64decode(result['image_data_url'].split(',')[1]), png())
        self.assertEqual(result['image_execution']['result']['sha256'], hashlib.sha256(png()).hexdigest())
        self.assertEqual(result['image_execution']['requested_controls'], result['image_execution']['sent_controls'])

    def test_edit_supplies_owned_exact_reference_and_removes_it_after_call(self):
        source = png(16, 16)
        observed = []
        client, response = transport()
        def post(url, *, json, timeout):
            self.assertTrue(url.endswith('/v1/images/edits'))
            path = Path(json['image'])
            self.assertEqual(path.read_bytes(), source)
            observed.append(path)
            return response
        client.post.side_effect = post
        result = mlx_vlm_image_request(11501, ImageRequest('/local/snapshot', 'edit', reference_b64=base64.b64encode(source).decode()), client)
        self.assertFalse(observed[0].exists())
        self.assertEqual(result['image_execution']['reference']['sha256'], hashlib.sha256(source).hexdigest())
        self.assertNotIn(str(observed[0]), json.dumps(result))

    def test_reference_mutation_rejects_even_valid_provider_result(self):
        client, response = transport()
        observed = []
        def post(*args, **kwargs):
            path = Path(kwargs['json']['image']); observed.append(path)
            path.write_bytes(png(8, 8))
            return response
        client.post.side_effect = post
        with self.assertRaises(ImageAdapterError):
            mlx_vlm_image_request(11501, ImageRequest('model', 'edit', reference_b64=base64.b64encode(png()).decode()), client)
        self.assertFalse(observed[0].exists())

    def test_invalid_reference_is_rejected_before_provider_call(self):
        for source in ('not base64!', base64.b64encode(b'not an image').decode(), 'https://example.com/image.png'):
            with self.subTest(source=source):
                client, _ = transport()
                with self.assertRaises(ValueError):
                    mlx_vlm_image_request(11501, ImageRequest('model', 'edit', reference_b64=source), client)
                client.post.assert_not_called()

    def test_result_faults_cannot_become_saved_images(self):
        changes = [
            {'b64_json': ''}, {'b64_json': 'not base64!'},
            {'b64_json': base64.b64encode(b'not image bytes').decode()},
            {'width': 31}, {'height': True}, {'seed': 43}, {'seed': None},
            {'seed': True}, {'path': '/tmp/unrequested.png'}, {'url': 'https://example.com/x'},
            {'mime_type': 'image/jpeg'},
        ]
        for change in changes:
            with self.subTest(change=change):
                body = native_response(); body['data'][0].update(change)
                client, _ = transport(body)
                with self.assertRaises(ImageAdapterError):
                    mlx_vlm_image_request(11501, ImageRequest('model', 'draw', 256, 256, 42), client)
        for body in ({'data': []}, {'data': native_response()['data'] * 2}, {'error': 'rejected'}, []):
            with self.subTest(body=body):
                with self.assertRaises(ImageAdapterError):
                    mlx_vlm_image_request(11501, ImageRequest('model', 'draw'), transport(body)[0])

    def test_requested_dimensions_must_match_bytes_even_when_provider_metadata_agrees(self):
        with self.assertRaises(ImageAdapterError):
            mlx_vlm_image_request(11501, ImageRequest('model', 'draw', 512, 256), transport()[0])

    def test_native_dimension_bounds_reject_before_provider_call(self):
        for width, height in ((64, 256), (4096, 256), (257, 256), (True, 256), (256, None)):
            with self.subTest(width=width, height=height):
                client, _ = transport()
                with self.assertRaises(ValueError):
                    mlx_vlm_image_request(11501, ImageRequest('model', 'draw', width, height), client)
                client.post.assert_not_called()

    def test_missing_decoder_rejects_before_provider_call(self):
        client, _ = transport()
        with patch.dict('sys.modules', {'PIL': None}), self.assertRaisesRegex(ImageAdapterError, 'Pillow is required'):
            mlx_vlm_image_request(11501, ImageRequest('model', 'draw'), client)
        client.post.assert_not_called()

    def test_unspecified_seed_is_reported_without_inventing_requested_control(self):
        result = mlx_vlm_image_request(11501, ImageRequest('model', 'draw'), transport()[0])
        self.assertEqual(result['seed'], 42)
        self.assertEqual(result['image_execution']['requested_controls'], {})

    def test_http_errors_and_timeouts_never_retry_or_change_protocol(self):
        for failure in (requests.Timeout('bounded timeout'), requests.HTTPError('rejected')):
            with self.subTest(failure=type(failure).__name__):
                client, _ = transport(); client.post.side_effect = failure
                with self.assertRaises(type(failure)):
                    mlx_vlm_image_request(11501, ImageRequest('model', 'draw'), client)
                self.assertEqual(client.post.call_count, 1)

    def test_unknown_or_edit_incapable_engine_is_rejected_before_execution(self):
        for backend, package, meta in (
            ('mlx', 'mlx_lm', {}), ('mlx', 'mflux', {}), ('llama_cpp', 'llama_cpp', {}),
            ('mlx', 'mlx_vlm', {'image_transport': 'mlx_vlm_images_v1', 'image_modes': ['generate']}),
        ):
            with self.subTest(backend=backend, package=package):
                with self.assertRaises(ValueError):
                    select_image_adapter(backend, package, meta, editing=True)
        self.assertEqual(select_image_adapter('ollama', '', {}, editing=True), 'ollama_images_v1')

    def test_dispatch_uses_selected_request_model_and_existing_persistence_owner(self):
        client, _ = transport()
        saved = Mock(return_value='/tmp/owned.png')
        provider = Mock(side_effect=lambda port, req: mlx_vlm_image_request(port, req, client))
        payload, status = dispatch_infer_request(context(), InferArtifacts(), {
            'mlx_vlm_image_request': provider, 'persist_image_data_url_locally': saved,
            'ollama_generate': Mock(side_effect=AssertionError('wrong backend')),
        })
        self.assertEqual(status, 200)
        self.assertEqual(provider.call_args.args[1].model, '/local/snapshot')
        saved.assert_called_once_with(payload['image_data_url'], 'display')
        self.assertEqual(payload['result']['image_execution'], payload['image_execution'])
        self.assertEqual(payload['saved_image_path'], '/tmp/owned.png')

    def test_failed_result_never_calls_writer_and_missing_write_cannot_succeed(self):
        saved = Mock()
        payload, status = dispatch_infer_request(context(), InferArtifacts(), {
            'mlx_vlm_image_request': Mock(side_effect=ImageAdapterError('wrong digest')),
            'persist_image_data_url_locally': saved,
        })
        self.assertEqual(status, 502); saved.assert_not_called()
        payload, status = dispatch_infer_request(context(), InferArtifacts(), {
            'mlx_vlm_image_request': lambda p, req: mlx_vlm_image_request(p, req, transport()[0]),
            'persist_image_data_url_locally': Mock(return_value=None),
        })
        self.assertEqual(status, 502)

    def test_ollama_requested_seed_is_sent_but_not_claimed_as_observed(self):
        client, response = transport(); response.status_code = 200
        ollama_openai_image_generation(11434, 'flux', 'draw', client, seed=7, timeout_sec=23)
        self.assertEqual(client.post.call_args.kwargs['json']['seed'], 7)
        self.assertEqual(client.post.call_args.kwargs['timeout'], 23)
        payload, status = dispatch_infer_request(replace(context(), backend='ollama'), InferArtifacts(), {
            'ollama_openai_image_generation': lambda *args, **kwargs: 'data:image/png;base64,' + base64.b64encode(png()).decode(),
            'persist_image_data_url_locally': lambda *args: '/tmp/result.png',
            'extract_generate_content': lambda data: '',
        })
        self.assertEqual(status, 200)
        self.assertIsNone(payload['seed'])
        self.assertEqual(payload['image_execution']['requested_seed'], 42)

    def test_diffusion_snapshot_qualification_and_missing_layout(self):
        for family, model in (
            ('flux2', 'black-forest-labs/FLUX.2-klein-4B'),
            ('qwen_image', 'Qwen/Qwen-Image-2.1'),
            ('qwen_image', 'mlx-community/Qwen-Image-2.1-MLX-4bit'),
        ):
            with self.subTest(family=family), tempfile.TemporaryDirectory() as tmp:
                root = snapshot(Path(tmp) / 'snapshot', family)
                metadata = mlx._read_mlx_snapshot_metadata(model, str(root))
                self.assertTrue(metadata['snapshot_image_supported'])
                self.assertEqual(metadata['provider_capabilities'], ['image_generation'])
                self.assertEqual(metadata['snapshot_model_type'], family)
                (root / 'vae/weights.safetensors').unlink()
                self.assertFalse(mlx._read_mlx_snapshot_metadata(model, str(root))['snapshot_image_supported'])

    def test_names_cannot_admit_unknown_or_mismatched_image_architecture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = snapshot(Path(tmp) / 'snapshot', 'qwen_image')
            self.assertFalse(read_snapshot_model_metadata('Qwen/Qwen-Image-3.0', str(root))['snapshot_image_supported'])
            (root / 'transformer/config.json').write_text('{"num_layers": 99}')
            self.assertFalse(read_snapshot_model_metadata('Qwen/Qwen-Image-2.1', str(root))['snapshot_image_supported'])
            self.assertEqual(mlx._server_kind_for_capability('image_generation'), 'mlx_vlm')

    def test_model_names_do_not_override_native_layout_or_sampling_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = snapshot(Path(tmp) / 'custom-name', 'qwen_image')
            meta = mlx._read_mlx_snapshot_metadata('community/custom-name', str(root))
            self.assertTrue(meta['snapshot_image_supported'])
            self.assertEqual(meta['snapshot_model_type'], 'qwen_image')
            self.assertEqual(meta['snapshot_image_loader']['defaults']['generate']['steps'], 30)
            with patch.object(mlx, '_probe_mlx_image_loader', return_value={'error': 'Invalid native variant'}):
                self.assertFalse(mlx._read_mlx_snapshot_metadata('Qwen/Qwen-Image-2.1', str(root))['snapshot_image_supported'])

    def test_catalog_instance_and_status_agree_on_image_contract(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mlx, '_mlx_package_runtime_check', return_value=checks()), patch.object(mlx, '_python_module_available', return_value=True):
            root = snapshot(Path(tmp) / 'models--Qwen--Qwen-Image-2.1/snapshots/rev', 'qwen_image')
            with patch.object(mlx, 'CACHE_DIR', Path(tmp)):
                catalog = mlx.find_hf_cached_models()
            self.assertEqual(len(catalog), 1)
            self.assertTrue(catalog[0]['runnable'])
            record = mlx.build_instance_record('Qwen/Qwen-Image-2.1', str(root), 11501, Path(tmp) / 'log')
            self.assertEqual(record['provider_capabilities'], ['image_generation'])
            self.assertEqual(record['inputs'], ['text', 'image'])
            self.assertEqual(record['outputs'], ['image'])
            self.assertEqual(record['supported_capabilities'], ['image_generation'])
            self.assertTrue(record['features']['vision_input'])
            self.assertEqual(record['mlx_server'], 'mlx_vlm')
            self.assertEqual(record['backend_metadata']['runtime_knobs'], [])
            self.assertIn('steps', record['backend_metadata']['image_request_controls'])
            runtime = _fetch_backend_runtime_metadata(record)
            self.assertIn('images_edits_url', runtime)
            self.assertNotIn('chat_completions_url', runtime)

    def test_image_edit_input_does_not_advertise_chat_or_vision_analysis(self):
        for modes in ([], ['generate'], ['generate', 'edit']):
            with self.subTest(modes=modes):
                record = build_registry_metadata('image', 'mlx', 'image_generation', metadata={
                    'provider_capabilities': ['image_generation'], 'inputs': ['text', 'image'], 'outputs': ['image'],
                    'image_modes': ['generate', 'edit'], 'backend_metadata': {'image_modes': modes},
                })
                self.assertEqual(record['supported_capabilities'], ['image_generation'])
                self.assertEqual('image' in record['inputs'], 'edit' in modes)
                self.assertFalse(record['text_capable'])

    def test_missing_package_support_keeps_image_cached_only(self):
        metadata = {'snapshot_image_supported': True, 'snapshot_model_type': 'flux2'}
        with patch.object(mlx, '_mlx_package_runtime_check', return_value={**checks(), 'image_endpoint_available': False}), patch.object(mlx, '_python_module_available', return_value=True):
            detail = mlx._mlx_discovery_details('flux', 'image_generation', config_present=True, metadata=metadata)
            self.assertFalse(detail['runnable'])
            self.assertIn('image endpoint', detail['disabled_reason'])

    def test_image_launch_uses_image_preload_offline_without_chat_knobs(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(mlx, 'LOG_DIR', Path(tmp)), patch.object(mlx, 'prepare_clean_runtime_log'), patch.object(mlx, 'resolve_mlx_python', return_value='/mock/python'), patch.object(mlx.subprocess, 'Popen') as launch:
            launch.return_value.pid = 123
            mlx.launch_vlm_server(11501, image_model='/local/snapshot')
            args, kwargs = launch.call_args
            self.assertEqual(args[0][:4], ['/mock/python', '-I', '-B', str(mlx.IMAGE_SERVER_SCRIPT)])
            self.assertEqual(args[0][-2:], ['--image-model', '/local/snapshot'])
            self.assertEqual(kwargs['env']['HF_HUB_OFFLINE'], '1')
            self.assertNotIn('--kv-quant-scheme', args[0])
            with self.assertRaises(ValueError):
                mlx.launch_vlm_server(11501, embedding_model='embed', image_model='image')
            with self.assertRaises(ValueError):
                mlx.launch_vlm_server(11501, {'kv_bits': 4}, image_model='image')

    def test_start_rechecks_layout_and_selects_image_loader_without_registry_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = snapshot(Path(tmp) / 'snapshot')
            model = 'black-forest-labs/FLUX.2-klein-4B'
            with (
                patch.object(mlx, 'find_mlx_snapshots', return_value=[{'repo': model, 'path': str(root), 'mlx_server': 'mlx_lm'}]),
                patch.object(mlx, 'port_in_use', return_value=False),
                patch.object(mlx, 'wait_for_port', return_value=True),
                patch.object(mlx, '_mlx_package_runtime_check', return_value=checks()),
                patch.object(mlx, '_python_module_available', return_value=True),
                patch.object(mlx, 'launch_vlm_server', return_value=(Path(tmp) / 'log', 123)) as launch,
                patch.object(mlx, 'register_mlx_instance') as register,
            ):
                record = mlx.start_mlx_model(model, preferred_port=11501, register_instance=False, prune_registry=False, start_source='api_start_model')
                launch.assert_called_once_with(11501, image_model=str(root))
                self.assertEqual(record['capability'], 'image_generation')
                self.assertEqual(record['request_model'], str(root))
                register.assert_not_called()
                launch.reset_mock()
                (root / 'vae/weights.safetensors').unlink()
                with self.assertRaisesRegex(RuntimeError, 'weights'):
                    mlx.start_mlx_model(model, preferred_port=11501, register_instance=False, prune_registry=False, start_source='api_start_model')
                launch.assert_not_called()


class ImageBackendStartApiTests(unittest.TestCase):
    """Frontend start request through real lifecycle, discovery and MLX owners."""

    def setUp(self):
        import fruth_webserver as web
        from tests.http_client import api_client

        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.model = 'mlx-community/Qwen-Image-2.1-MLX-4bit'
        self.snapshot = snapshot(
            self.root / 'cache/models--mlx-community--Qwen-Image-2.1-MLX-4bit/snapshots/rev',
            'qwen_image',
        )
        self.registry = self.root / 'model_ports.json'
        self.client = api_client(web.app)
        self.enterContext(patch.object(mlx, 'CACHE_DIR', self.root / 'cache'))
        self.enterContext(patch.object(mlx, 'CONFIG_FILE', self.registry))
        self.enterContext(patch('fruth_core.lifecycle.START_INSTANCE_LOCK_PATH', self.root / 'start.lock'))
        self.enterContext(patch('fruth_core.status._port_listening', return_value=True))
        self.enterContext(patch.object(web, 'RUNTIME_STATUS_PATH', self.root / 'status.json'))
        self.enterContext(patch.object(web, 'load_running_instances', return_value=[]))
        self.enterContext(patch.object(web, '_log_unified_event'))
        self.enterContext(patch.object(web, '_log_runtime_status_transition'))
        self.enterContext(patch.object(mlx, 'prune_stale_mlx_entries'))
        self.enterContext(patch.object(mlx, 'schedule_recent_mlx_instance_reconciliation'))
        self.enterContext(patch.object(mlx, '_probe_mlx_image_loader', side_effect=native_loader_fixture))
        self.runtime_check = self.enterContext(patch.object(mlx, '_mlx_package_runtime_check', return_value=checks()))
        self.enterContext(patch.object(mlx, '_python_module_available', return_value=True))
        self.enterContext(patch.object(mlx, 'port_in_use', return_value=False))
        self.enterContext(patch.object(mlx, 'wait_for_port', return_value=True))
        self.launch = self.enterContext(patch.object(mlx, 'launch_vlm_server', return_value=(self.root / 'image.log', 123)))

    def start(self, **overrides):
        return self.client.post('/api/start_model', json={
            'model': self.model, 'backend': 'mlx', 'capability': 'image_generation',
            'model_path': str(self.snapshot), 'preferred_port': 11501,
            'start_source': 'frontend_button', **overrides,
        })

    def test_frontend_start_reaches_qualified_image_loader_and_registry(self):
        response = self.start()
        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload['status'], 'started')
        self.assertEqual(payload['start_source'], 'frontend_button')
        instance = payload['instance']
        self.assertEqual(instance['model'], self.model)
        self.assertEqual(instance['capability'], 'image_generation')
        self.assertEqual(instance['supported_capabilities'], ['image_generation'])
        self.assertEqual(instance['backend_package'], 'mlx_vlm')
        self.assertEqual(instance['request_model'], str(self.snapshot))
        self.assertEqual(instance['backend_metadata']['image_transport'], 'mlx_vlm_images_v1')
        self.launch.assert_called_once_with(11501, image_model=str(self.snapshot))
        saved = mlx.load_config_entries()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]['instance_id'], instance['instance_id'])
        self.assertEqual(saved[0]['start_source'], 'frontend_button')
        self.assertEqual(saved[0]['request_model'], str(self.snapshot))

    def test_api_start_infers_image_capability_from_snapshot(self):
        response = self.start(capability=None, start_source='api_start_model')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['instance']['capability'], 'image_generation')
        self.launch.assert_called_once_with(11501, image_model=str(self.snapshot))

    def test_frontend_start_uses_native_contract_for_renamed_image_family(self):
        (self.snapshot / 'model_index.json').write_text(json.dumps({
            '_class_name': 'ZImagePipeline', **{key: ['fixture', key] for key in ('transformer', 'text_encoder', 'vae')},
        }))
        response = self.start()
        self.assertEqual(response.status_code, 200, response.get_json())
        instance = response.get_json()['instance']
        self.assertEqual(instance['snapshot_model_type'], 'z_image')
        self.assertEqual(instance['backend_metadata']['image_steps_min'], 2)
        self.assertEqual(instance['backend_metadata']['image_sampling_defaults']['generate']['steps'], 9)
        self.launch.assert_called_once_with(11501, image_model=str(self.snapshot))

    def test_frontend_start_keeps_package_layout_and_chat_control_gates(self):
        for fault in ('missing_endpoint', 'missing_weights', 'chat_controls'):
            with self.subTest(fault=fault):
                if fault == 'missing_endpoint':
                    self.runtime_check.return_value = {**checks(), 'image_endpoint_available': False}
                weights = self.snapshot / 'vae/weights.safetensors'
                if fault == 'missing_weights':
                    weights.unlink()
                response = self.start(**({'launch_defaults': {'kv_bits': 4}} if fault == 'chat_controls' else {}))
                self.assertEqual(response.status_code, 400, response.get_json())
                self.assertNotIn('Unsupported start type', response.get_json()['error'])
                self.launch.assert_not_called()
                self.assertFalse(self.registry.exists())
                self.runtime_check.return_value = checks()
                if fault == 'missing_weights':
                    weights.write_bytes(b'synthetic prerequisite only')

    def test_start_rejects_forbidden_source_and_unsupported_backend_pair(self):
        for overrides in ({'start_source': 'route_selection'}, {'backend': 'llama_cpp'}):
            with self.subTest(overrides=overrides):
                response = self.start(**overrides)
                self.assertEqual(response.status_code, 400, response.get_json())
                self.launch.assert_not_called()
                self.assertFalse(self.registry.exists())


class ImageBackendApiTests(unittest.TestCase):
    """Real HTTP/transport/writer/provenance path with a synthetic native server."""

    def setUp(self):
        import fruth_webserver as web
        from tests.http_client import api_client
        self.web = web
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.client = api_client(web.app)
        self.registry = self.root / 'artifacts.jsonl'
        self.instance = {
            'instance_id': 'mlx-image', 'backend': 'mlx', 'backend_package': 'mlx_vlm',
            'port': 11501, 'model': 'black-forest-labs/FLUX.2-klein-4B',
            'request_model': str(self.root / 'snapshot'), 'capability': 'image_generation',
            'backend_metadata': {'image_transport': 'mlx_vlm_images_v1', 'image_modes': ['generate', 'edit'],
                                 'image_request_controls': ['width', 'height', 'seed', 'steps']},
        }
        self.enterContext(patch.object(web, '_lookup_instance', return_value=self.instance))
        self.enterContext(patch.object(web, 'ARTIFACT_REGISTRY_LEDGER', self.registry))
        self.enterContext(patch('fruth_core.transports.ARTIFACT_OUTPUTS_IMAGES_DIR', self.root / 'images'))
        self.enterContext(patch('fruth_core.status._port_listening', return_value=True))
        self.enterContext(patch.object(web, '_schedule_post_response_substrate_hygiene'))
        self.enterContext(patch.object(web._GENERATED_IMAGE_POSTPROCESS, 'schedule_generated_image_payload_enrichment', side_effect=lambda payload: dict(payload)))
        for name in ('record_instance_activity', 'record_instance_success', 'record_instance_failure'):
            self.enterContext(patch.object(web, name, return_value=({}, {'readiness': 'ready'})))
        self.native, self.response = transport()
        self.enterContext(patch.object(web._BACKEND_TRANSPORT_RUNTIME, 'mlx_vlm_image_request', side_effect=lambda port, request: mlx_vlm_image_request(port, request, self.native)))
        self.ollama = self.enterContext(patch.object(web, '_ollama_generate', side_effect=AssertionError('wrong backend')))

    def assert_saved_evidence(self, payload, *, requested_seed):
        from fruth_services.artifact_registry import find_generated_image_provenance
        from fruth_services.responses import build_canonical_response_payload
        saved = Path(payload['saved_image_path'])
        self.assertEqual(saved.read_bytes(), png())
        self.assertEqual(saved.parent, self.root / 'images')
        evidence = payload['image_execution']
        self.assertEqual(evidence['result']['sha256'], hashlib.sha256(saved.read_bytes()).hexdigest())
        record = find_generated_image_provenance(str(saved), ledger_path=self.registry)
        # The registry omits empty optional mappings/None. Every nonempty fact
        # must remain identical, including requested seed and both byte digests.
        self.assertEqual(record['image_execution'], {key: value for key, value in evidence.items() if value not in (None, {})})
        self.assertEqual(record['output']['seed'], 42)
        self.assertEqual(record['request'].get('seed'), requested_seed)
        canonical = build_canonical_response_payload(
            instance_id='mlx-image', model_name=self.instance['model'], backend='mlx',
            capability='image_generation', mode=payload['mode'], output_text=payload['content'],
            source_payload=payload,
        )
        roundtrip = json.loads(json.dumps(canonical))
        self.assertEqual(roundtrip['runtime']['image_execution'], evidence)
        self.ollama.assert_not_called()

    def test_http_generation_keeps_requested_and_reported_seed_distinct(self):
        for requested_seed in (42, None):
            with self.subTest(requested_seed=requested_seed):
                request = {'instance_id': 'mlx-image', 'prompt': 'draw a blue bird'}
                if requested_seed is not None:
                    request['seed'] = requested_seed
                reply = self.client.post('/api/infer', json=request)
                self.assertEqual(reply.status_code, 200, reply.get_json())
                self.assert_saved_evidence(reply.get_json(), requested_seed=requested_seed)
                self.assertEqual(self.native.post.call_args.kwargs['json']['model'], self.instance['request_model'])

    def test_http_steps_are_optional_and_preserved_in_saved_and_canonical_evidence(self):
        for steps in (None, '', 1, 20, '12'):
            with self.subTest(steps=steps):
                reply = self.client.post('/api/infer', json={
                    'instance_id': 'mlx-image', 'prompt': 'draw a blue bird', 'steps': steps,
                })
                self.assertEqual(reply.status_code, 200, reply.get_json())
                expected = int(steps) if steps not in (None, '') else None
                sent = self.native.post.call_args.kwargs['json']
                self.assertEqual(sent.get('steps'), expected)
                self.assertEqual('steps' in sent, expected is not None)
                self.assertEqual(reply.get_json()['image_execution']['requested_controls'].get('steps'), expected)
                self.assert_saved_evidence(reply.get_json(), requested_seed=None)

    def test_http_loader_minimum_rejects_before_provider_dispatch(self):
        self.instance['backend_metadata']['image_steps_min'] = 2
        response = self.client.post('/api/infer', json={
            'instance_id': 'mlx-image', 'prompt': 'draw', 'steps': 1,
        })
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertIn('at least 2', response.get_json()['error'])
        self.native.post.assert_not_called()
        self.assertFalse(self.registry.exists())

    def test_http_steps_reject_unsupported_instances_before_dispatch(self):
        for instance in (
            {**self.instance, 'backend': 'ollama'},
            {**self.instance, 'backend_metadata': {**self.instance['backend_metadata'], 'image_request_controls': []}},
        ):
            with self.subTest(instance=instance), patch.object(self.web, '_lookup_instance', return_value=instance):
                reply = self.client.post('/api/infer', json={
                    'instance_id': 'mlx-image', 'prompt': 'draw', 'steps': 12,
                })
                self.assertEqual(reply.status_code, 400, reply.get_json())
                self.assertIn('does not support image steps', reply.get_json()['error'])
        self.native.post.assert_not_called()
        self.ollama.assert_not_called()
        self.assertFalse(self.registry.exists())

    def test_responses_route_forwards_steps_to_real_image_adapter(self):
        reply = self.client.post('/api/responses', json={
            'instance_id': 'mlx-image', 'input': 'a flying island', 'steps': 12,
        })
        self.assertEqual(reply.status_code, 200, reply.get_json())
        self.native.post.assert_called_once()
        self.assertEqual(self.native.post.call_args.kwargs['json']['steps'], 12)
        response_id = reply.get_json()['id']
        # Debug is a bounded graph observation, not the full runtime evidence.
        # Evict this test's live record so the truth read also exercises recovery.
        self.web._RESPONSE_LOOKUP.pop(response_id, None)
        recovered = self.client.get(f'/api/responses/{response_id}?view=truth')
        self.assertEqual(recovered.status_code, 200, recovered.get_json())
        saved = recovered.get_json()
        evidence = saved['runtime']['image_execution']
        self.assertEqual(evidence['requested_controls']['steps'], 12)
        self.assertEqual(evidence['sent_controls']['steps'], 12)
        self.assertNotIn('reported_steps', evidence)
        self.native.post.assert_called_once()  # Recovery must not regenerate.

    def test_control_snapshot_keeps_explicit_steps_without_inventing_defaults(self):
        from fruth_services.control_snapshots import build_control_snapshot
        explicit = build_control_snapshot(request_payload={'steps': '12'})
        self.assertEqual(explicit['values']['image']['steps'], 12)
        omitted = build_control_snapshot(request_payload={})
        self.assertNotIn('steps', (omitted or {}).get('values', {}).get('image', {}))

    def test_http_edit_retains_exact_uploaded_reference(self):
        reference = png(64, 64)
        captured = []
        def post(url, **kwargs):
            self.assertTrue(url.endswith('/v1/images/edits'))
            path = Path(kwargs['json']['image'])
            self.assertEqual(path.read_bytes(), reference)
            captured.append(path)
            return self.response
        self.native.post.side_effect = post
        reply = self.client.post('/api/infer', data={
            'instance_id': 'mlx-image', 'prompt': 'make the background green',
            'width': '256', 'height': '256', 'seed': '42',
            'steps': '12',
            'file': (io.BytesIO(reference), 'reference.png'),
        }, content_type='multipart/form-data')
        self.assertEqual(reply.status_code, 200, reply.get_json())
        payload = reply.get_json()
        self.assertEqual(payload['mode'], 'image_generation_edit')
        self.assertEqual(payload['image_execution']['reference']['sha256'], hashlib.sha256(reference).hexdigest())
        self.assertFalse(captured[0].exists())
        self.assertEqual(self.native.post.call_args.kwargs['json']['steps'], 12)
        self.assertEqual(payload['image_execution']['sent_controls']['steps'], 12)
        self.assert_saved_evidence(payload, requested_seed=42)

    def test_http_cannot_override_bound_image_model_backend_or_capability(self):
        for override in ({'model': 'other/model'}, {'request_model': '/other/snapshot'},
                         {'backend': 'ollama'}, {'capability': 'chat'}):
            with self.subTest(override=override):
                reply = self.client.post('/api/infer', json={'instance_id': 'mlx-image', 'prompt': 'draw', **override})
                self.assertEqual(reply.status_code, 400)
        self.native.post.assert_not_called()
        self.ollama.assert_not_called()
        self.assertFalse(self.registry.exists())
        self.assertFalse((self.root / 'images').exists())

    def test_http_invalid_provider_image_creates_no_artifact_or_provenance(self):
        body = native_response(); body['data'][0]['width'] = 999
        self.response.json.return_value = body
        reply = self.client.post('/api/infer', json={'instance_id': 'mlx-image', 'prompt': 'draw'})
        self.assertEqual(reply.status_code, 502)
        self.assertFalse(self.registry.exists())
        self.assertFalse((self.root / 'images').exists())
        self.ollama.assert_not_called()

    def test_http_invalid_controls_are_not_defaulted_clamped_or_dispatched(self):
        for controls in (
            {'width': 'bad', 'height': 256}, {'width': 255, 'height': 256},
            {'width': 4096, 'height': 256}, {'width': True, 'height': 256},
            {'seed': -1}, {'seed': 2_147_483_648}, {'seed': True}, {'seed': 'bad'},
            {'steps': 0}, {'steps': -1}, {'steps': True}, {'steps': 1.5},
            {'steps': '1.5'}, {'steps': 'bad'}, {'steps': []},
        ):
            with self.subTest(controls=controls):
                reply = self.client.post('/api/infer', json={'instance_id': 'mlx-image', 'prompt': 'draw', **controls})
                self.assertEqual(reply.status_code, 400, reply.get_json())
        self.native.post.assert_not_called()
        self.assertFalse(self.registry.exists())
        self.assertFalse((self.root / 'images').exists())
