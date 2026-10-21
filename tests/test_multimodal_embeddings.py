"""Model/adapter intersection and real owner wiring, with isolated media."""

import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from werkzeug.datastructures import FileStorage

from fruth_core.embeddings import encode_embedding_inputs, media_embedding_input
from fruth_inference.router import select_embedding_instance
from fruth_runtime import mlx_model_manager as mlx
from helpers.model_capabilities import (
    build_ollama_show_summary, build_registry_metadata, embedding_input_modalities,
    infer_supported_capabilities,
)
from helpers.tts_model_metadata import read_snapshot_model_metadata
from tests.test_embedding_backend_contract import helper, owner, runtime_checks, snapshot


def png():
    stream = io.BytesIO()
    Image.new('RGB', (8, 8), 'red').save(stream, format='PNG')
    return stream.getvalue()


def multimodal(backend='ollama'):
    item = helper(backend)
    if backend == 'ollama':
        item['backend_metadata'] = build_ollama_show_summary(
            {'capabilities': ['embedding', 'vision', 'audio']}, server_version='0.40.6',
        )
    else:
        item['backend_metadata'].update(embedding_input_format='mlx_vlm_image_v1',
                                        embedding_input_modalities=['text', 'image', 'audio'])
    return item


class MultimodalEmbeddingTests(unittest.TestCase):
    def test_dynamic_modalities_require_model_and_native_contract(self):
        for version, caps, expected in (
            ('0.40.6', ['embedding', 'vision', 'audio'], ['text', 'image', 'audio']),
            ('0.40.6', ['embedding'], ['text']),
            ('0.32.1', ['embedding', 'vision', 'audio'], ['text']),
            ('', ['embedding', 'vision', 'audio'], ['text']),
        ):
            with self.subTest(version=version, caps=caps):
                metadata = {'backend_metadata': build_ollama_show_summary({'capabilities': caps}, server_version=version)}
                record = build_registry_metadata('arbitrary-renamed-model', 'ollama', 'embedding', metadata=metadata)
                self.assertEqual(record['inputs'], expected)
                self.assertEqual(infer_supported_capabilities('arbitrary', 'ollama', 'embedding', metadata=record), ['embedding'])
        self.assertEqual(embedding_input_modalities('mlx', multimodal('mlx')), ['text', 'image'])
        self.assertEqual(embedding_input_modalities('llama_cpp', multimodal('mlx')), ['text'])
        self.assertEqual(embedding_input_modalities('ollama', {'routing_summary': 'invalid'}), ['text'])
        self.assertEqual(embedding_input_modalities('ollama', {'backend_metadata': {
            'embedding_input_format': 'ollama_multimodal_v1', 'embedding_input_modalities': 'text/image/audio',
        }}), ['text'])

    def test_native_payloads_preserve_media_bytes_order_and_text(self):
        image = media_embedding_input('image', png())
        audio = media_embedding_input('audio', b'RIFF fixture, native decoder validates audio')
        items = ['task: unchanged Grüezi', image, audio, 'last']
        wire, evidence = encode_embedding_inputs(items, backend='ollama', transport='ollama_api_embed', instance=multimodal())
        self.assertEqual(wire, items)
        self.assertEqual([item['index'] for item in evidence], [1, 2])
        selected = select_embedding_instance([multimodal('mlx')])
        wire, _ = encode_embedding_inputs(items[:2], backend='mlx', transport='openai_embeddings', instance=selected)
        self.assertEqual(wire[1]['image_url']['url'], 'data:image/png;base64,' + image['image'])

    def test_unsupported_and_invalid_inputs_reject_before_http(self):
        cases = [({'audio': base64.b64encode(b'x').decode()}, 'mlx'),
                 ({'image': 'https://example.com/a.png'}, 'ollama'),
                 ({'image': base64.b64encode(b'not an image').decode()}, 'ollama'),
                 ({'video': 'AA=='}, 'ollama'), ({'audio': ''}, 'ollama'),
                 ({'image': 'AA==', 'text': 'ambiguous'}, 'ollama')]
        for item, backend in cases:
            with self.subTest(item=item, backend=backend):
                post = Mock()
                with self.assertRaises((ValueError, OSError)):
                    owner(post)._execute_embedding_backend_request(
                        target_port=1, model_name='encoder', backend=backend, inputs=[item],
                        embedding_transport='ollama_api_embed' if backend == 'ollama' else 'openai_embeddings',
                        instance=multimodal(backend),
                    )
                post.assert_not_called()

    def test_response_identity_and_entire_batch_are_required(self):
        for body in ({'model': 'wrong', 'embeddings': [[1, 0], [0, 1]]},
                     {'model': 'encoder', 'embeddings': [[1, 0]]},
                     {'model': 'encoder', 'embeddings': [[1, 0], [0, 0]]}):
            with self.subTest(body=body):
                response = Mock()
                response.json.return_value = body
                with self.assertRaises(ValueError):
                    owner(Mock(return_value=response))._execute_embedding_backend_request(
                        target_port=1, model_name='encoder', backend='ollama',
                        inputs=['text', media_embedding_input('image', png())], instance=multimodal(),
                    )

    def test_current_upload_becomes_advisory_hint_without_consuming_stream(self):
        for kind, name, raw in (('image', 'a.png', png()), ('audio', 'a.wav', b'RIFF fixture')):
            with self.subTest(kind=kind):
                upload = FileStorage(stream=io.BytesIO(raw), filename=name)
                upload.stream.seek(2)
                context = {'prompt': 'describe this', 'request_attachment': {
                    'file_kind': kind, 'has_explicit_file': True, 'upload_filename': name}, 'runtime': {}}
                response = Mock()
                response.json.return_value = {'model': '/local/encoder', 'embeddings': [[1, 0], [1, 0], [0, 1]]}
                post = Mock(return_value=response)
                candidates = [{'kind': 'capability', 'capability': 'chat', 'text': 'conversation'}]
                with patch('fruth_server.inference_route_runtime.build_embedding_route_candidates', return_value=candidates):
                    owner(post).attach_embedding_hints_to_route_context(context, runtime_manifest={}, instances=[multimodal()], upload=upload)
                self.assertEqual(upload.stream.tell(), 2)
                payload = post.call_args.kwargs['json']
                self.assertFalse(payload['truncate'])
                self.assertEqual(base64.b64decode(payload['input'][2][kind]), raw)
                hints = context['runtime']['embedding_hints']
                self.assertEqual(hints['top_capabilities'][0]['score'], 1.0)
                self.assertTrue(hints['media'][0]['advisory_only'])
                self.assertEqual(hints['media'][0]['similarities']['top_capabilities'][0]['score'], 0.0)
                self.assertNotIn(base64.b64encode(raw).decode(), json.dumps(context))
                self.assertTrue(context['runtime']['embedding_helper']['media']['attached'])

    def test_web_composition_preserves_upload_and_qualified_metadata(self):
        import fruth_webserver as web
        upload = FileStorage(stream=io.BytesIO(png()), filename='selected.png')
        context = {'prompt': 'describe this', 'runtime': {}, 'request_attachment': {
            'file_kind': 'image', 'has_explicit_file': True, 'upload_filename': 'selected.png'}}
        instance = multimodal()
        instance['routing_summary'] = web._build_instance_routing_summary(instance, instance['runtime_status'])
        # Exercise the actual web -> owner -> web executor -> HTTP composition.
        response = Mock()
        response.json.return_value = {'model': '/local/encoder', 'embeddings': [[1, 0], [1, 0], [0, 1]]}
        candidates = [{'kind': 'capability', 'capability': 'chat', 'text': 'conversation'}]
        with patch('fruth_webserver.requests.post', return_value=response) as post, \
                patch('fruth_server.inference_route_runtime.build_embedding_route_candidates', return_value=candidates):
            web._attach_embedding_hints_to_route_context(context, runtime_manifest={}, instances=[instance], upload=upload)
        self.assertTrue(context['runtime']['embedding_helper']['media']['attached'])
        self.assertEqual(len(post.call_args.kwargs['json']['input']), 3)

    def test_available_models_api_exposes_modalities_without_generation_claims(self):
        import fruth_webserver as web
        from tests.http_client import api_client
        instance = multimodal()
        instance['name'] = instance['model']
        with patch('fruth_webserver.list_available_models', return_value=[instance]), \
                patch('fruth_webserver.load_running_instances', return_value=[]), \
                patch('fruth_webserver.merge_instances_with_runtime_status', return_value=[]), \
                patch('fruth_webserver.build_backend_fabric_snapshot', return_value={}):
            response = api_client(web.app).get('/api/available_models')
        self.assertEqual(response.status_code, 200)
        model = response.get_json()['models'][0]
        self.assertEqual(model['inputs'], ['text', 'image', 'audio'])
        self.assertEqual(model['outputs'], ['embedding'])
        self.assertEqual(model['supported_capabilities'], ['embedding'])

    def test_media_item_limit_fails_before_reading_any_reference(self):
        runtime = owner()
        resolve = Mock()
        runtime.hooks['resolve_saved_file_input_path'] = resolve
        context = {'selected_reference_artifacts': [{'type': 'image', 'path': str(i)} for i in range(9)]}
        inputs, status = runtime._embedding_media_inputs(context, select_embedding_instance([multimodal()]))
        self.assertEqual(inputs, [])
        self.assertEqual(status['reason'], 'media_input_failed')
        resolve.assert_not_called()

    def test_unsupported_media_is_not_read_and_text_path_survives(self):
        upload = Mock()
        context = {'request_attachment': {'file_kind': 'audio', 'has_explicit_file': True}}
        inputs, status = owner()._embedding_media_inputs(context, select_embedding_instance([multimodal('mlx')]), upload=upload)
        self.assertEqual(inputs, [])
        self.assertEqual(status['reason'], 'unsupported_media')
        upload.stream.read.assert_not_called()
        context.update(prompt='describe this', runtime={})
        response = Mock()
        response.json.return_value = {'data': [{'index': 0, 'embedding': [1, 0]},
                                              {'index': 1, 'embedding': [0, 1]}]}
        post = Mock(return_value=response)
        with patch('fruth_server.inference_route_runtime.build_embedding_route_candidates', return_value=[
                {'kind': 'capability', 'capability': 'chat', 'text': 'conversation'}]):
            owner(post).attach_embedding_hints_to_route_context(
                context, runtime_manifest={}, instances=[multimodal('mlx')], upload=upload,
            )
        self.assertTrue(context['runtime']['embedding_helper']['attached'])
        self.assertFalse(context['runtime']['embedding_helper']['media']['attached'])
        self.assertEqual(post.call_args.kwargs['json']['input'], ['describe this', 'conversation'])
        upload.stream.read.assert_not_called()

    def test_history_is_not_read_selected_reference_uses_existing_resolver(self):
        runtime = owner()
        resolver = Mock()
        runtime.hooks['resolve_saved_file_input_path'] = resolver
        instance = select_embedding_instance([multimodal()])
        context = {'recent_artifacts': [{'type': 'image', 'path': '/forbidden/history.png'}],
                   'latest_artifacts': {'image': {'path': '/forbidden/history.png'}}}
        self.assertEqual(runtime._embedding_media_inputs(context, instance)[0], [])
        resolver.assert_not_called()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'selected.png'
            path.write_bytes(png())
            resolver.return_value = path
            context['selected_reference_artifacts'] = [{'type': 'image', 'path': '/api/saved/selected.png'}]
            inputs, status = runtime._embedding_media_inputs(context, instance)
            self.assertEqual(len(inputs), 1)
            self.assertEqual(status['reason'], 'prepared')
            resolver.assert_called_once_with('/api/saved/selected.png')

    def test_budget_rejects_without_clipping_and_upload_position_recovers(self):
        upload = FileStorage(stream=io.BytesIO(b'1234567890'), filename='a.wav')
        upload.stream.seek(4)
        context = {'request_attachment': {'file_kind': 'audio', 'has_explicit_file': True}}
        with patch('fruth_server.inference_route_runtime.EMBEDDING_MEDIA_MAX_BYTES', 4):
            inputs, status = owner()._embedding_media_inputs(context, select_embedding_instance([multimodal()]), upload=upload)
        self.assertEqual(inputs, [])
        self.assertEqual(status['reason'], 'media_input_failed')
        self.assertEqual(upload.stream.tell(), 4)

    def test_mlx_image_discovery_requires_processor_and_native_image_adapter(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(mlx, '_mlx_package_runtime_check', return_value=runtime_checks()):
            root = snapshot(Path(temp) / 'renamed')
            metadata = read_snapshot_model_metadata('renamed', str(root))
            contract = mlx._mlx_contract_details('renamed', 'embedding', metadata)
            self.assertEqual(embedding_input_modalities('mlx', contract), ['text'])
            (root / 'preprocessor_config.json').write_text('{"image_processor_type":"FixtureImageProcessor"}')
            metadata = read_snapshot_model_metadata('renamed', str(root))
            contract = mlx._mlx_contract_details('renamed', 'embedding', metadata)
            self.assertEqual(embedding_input_modalities('mlx', contract), ['text', 'image'])
            record = build_registry_metadata('renamed', 'mlx', 'embedding', metadata=contract)
            self.assertEqual(record['inputs'], ['text', 'image'])


if __name__ == '__main__':
    unittest.main()
