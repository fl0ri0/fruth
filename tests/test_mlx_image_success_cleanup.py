"""Native image residency cleanup, without models or production state."""
import asyncio
import gc
import json
import sys
import tempfile
import unittest
import weakref
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from helpers import mlx_image_server as owner
from fruth_runtime import mlx_model_manager as manager


class ImageCleanupTests(unittest.TestCase):
    def run_response(self, *, path='/v1/images/generations', method='POST', status=200,
                     cleanup=None, fail_send=False):
        events, messages = [], []
        encoded = json.dumps({'data': [{'b64_json': 'exact bytes', 'seed': 19}]}).encode()

        async def app(scope, receive, send):
            events.append('serialized')
            await send({'type': 'http.response.start', 'status': status,
                        'headers': [(b'content-type', b'application/json')]})
            await send({'type': 'http.response.body', 'body': encoded, 'more_body': False})

        def release():
            events.append('cleanup')
            if cleanup:
                cleanup()

        async def send(message):
            events.append(message['type'])
            if fail_send:
                raise ConnectionError('client disconnected')
            messages.append(message)

        async def receive():
            return {'type': 'http.request', 'body': b''}

        middleware = owner.ImageRequestCleanup(app, cleanup=release)
        asyncio.run(middleware({'type': 'http', 'path': path, 'method': method}, receive, send))
        return events, messages, encoded

    def test_both_native_aliases_for_generation_and_edit_preserve_bytes_and_headers(self):
        for path in owner.IMAGE_PATHS:
            with self.subTest(path=path):
                events, messages, encoded = self.run_response(path=path)
                self.assertEqual(events, ['serialized', 'cleanup',
                                         'http.response.start', 'http.response.body'])
                self.assertEqual(messages[0]['headers'], [(b'content-type', b'application/json')])
                self.assertEqual(messages[1]['body'], encoded)
                self.assertFalse(messages[1]['more_body'])

    def test_failed_requests_preserve_error_bytes_and_release_idle_models(self):
        for status in (400, 500, 307):
            with self.subTest(status=status):
                events, messages, encoded = self.run_response(status=status)
                self.assertEqual(events.count('cleanup'), 1)
                self.assertEqual(messages[0]['status'], status)
                self.assertEqual(messages[1]['body'], encoded)

    def test_nonimage_routes_do_not_cleanup(self):
        for kwargs in ({'path': '/v1/chat/completions'}, {'path': '/v1/embeddings'},
                       {'path': '/v1/images/generations/unknown'}, {'method': 'GET'}):
            with self.subTest(kwargs=kwargs):
                events, _, _ = self.run_response(**kwargs)
                self.assertNotIn('cleanup', events)

    def test_cleanup_failure_keeps_success_response_without_retry(self):
        cleanup = Mock(side_effect=RuntimeError('fixture cleanup error'))
        with self.assertLogs(owner.LOGGER, level='ERROR') as logs:
            _, messages, encoded = self.run_response(cleanup=cleanup)
        self.assertEqual(cleanup.call_count, 1)
        self.assertEqual(messages[0]['status'], 200)
        self.assertEqual(messages[1]['body'], encoded)
        self.assertIn('cleanup failed', ''.join(logs.output))

    def test_client_disconnect_does_not_prevent_completed_request_cleanup(self):
        cleanup = Mock()
        with self.assertRaisesRegex(ConnectionError, 'disconnected'):
            self.run_response(cleanup=cleanup, fail_send=True)
        cleanup.assert_called_once_with()

    def test_serialization_failure_releases_idle_models_and_preserves_exception(self):
        cleanup = Mock()

        async def app(scope, receive, send):
            raise ValueError('cannot serialize output')

        with self.assertRaisesRegex(ValueError, 'serialize'):
            asyncio.run(owner.ImageRequestCleanup(app, cleanup=cleanup)(
                {'type': 'http', 'method': 'POST', 'path': '/v1/images/generations'},
                None, None))
        cleanup.assert_called_once_with()

    def test_lifespan_passes_through(self):
        cleanup = Mock()
        scopes = []

        async def app(scope, receive, send):
            scopes.append(scope)

        asyncio.run(owner.ImageRequestCleanup(app, cleanup=cleanup)(
            {'type': 'lifespan'}, None, None))
        self.assertEqual(scopes, [{'type': 'lifespan'}])
        cleanup.assert_not_called()

    def test_cleanup_order_releases_unreachable_buffers_and_keeps_live_model(self):
        class Buffer:
            pass

        model = Buffer()
        unused = Buffer()
        unused.cycle = unused
        unused_ref = weakref.ref(unused)
        del unused
        events = []

        def clear():
            events.append('clear')
            self.assertIsNone(unused_ref())
            self.assertIs(mx.model, model)

        mx = SimpleNamespace(
            model=model, synchronize=lambda: events.append('sync'), clear_cache=clear,
            get_cache_memory=Mock(side_effect=[1024, 0]), get_active_memory=lambda: 512)
        original_collect = gc.collect
        # Use the real collector without recursing through the patched owner module.
        with patch.object(owner.gc, 'collect', side_effect=lambda: (
                events.append('collect'), original_collect())[-1]):
            with self.assertLogs(owner.LOGGER, level='INFO') as logs:
                owner.release_image_cache(mx)
        self.assertEqual(events, ['sync', 'collect', 'clear'])
        self.assertIn('cache_before_bytes=1024 cache_after_bytes=0 active_after_bytes=512',
                      ''.join(logs.output))

    def test_main_registers_middleware_on_native_app_before_native_cli(self):
        mlx = ModuleType('mlx')
        mlx.core = ModuleType('mlx.core')
        vlm = ModuleType('mlx_vlm')
        vlm.server = ModuleType('mlx_vlm.server')
        events = []
        vlm.server.app = SimpleNamespace(add_middleware=lambda *a, **kw: events.append((a, kw)))
        vlm.server.main = lambda: events.append('native CLI')
        vlm.server._unload_model_cache_group = Mock(return_value=True)
        with patch.dict(sys.modules, {'mlx': mlx, 'mlx.core': mlx.core,
                                     'mlx_vlm': vlm, 'mlx_vlm.server': vlm.server}), \
                patch.object(sys, 'argv', ['launcher', '--image-model', '/fixture/model']):
            owner.main()
        self.assertEqual(events[0][0], (owner.ImageRequestCleanup,))
        self.assertEqual(events[1], 'native CLI')
        with patch.object(owner, 'release_image_cache') as release:
            events[0][1]['cleanup']()
        release.assert_called_once_with(
            mlx.core, unload=vlm.server._unload_model_cache_group)

    def test_native_unload_support_is_required_before_starting_server(self):
        mlx, vlm = ModuleType('mlx'), ModuleType('mlx_vlm')
        mlx.core, vlm.server = ModuleType('mlx.core'), ModuleType('mlx_vlm.server')
        vlm.server.main = Mock()
        with patch.dict(sys.modules, {'mlx': mlx, 'mlx.core': mlx.core,
                                     'mlx_vlm': vlm, 'mlx_vlm.server': vlm.server}), \
                patch.object(sys, 'argv', ['launcher', '--image-model', '/fixture/model']):
            with self.assertRaisesRegex(SystemExit, 'per-kind model unloading'):
                owner.main()
        vlm.server.main.assert_not_called()

    def test_unload_releases_both_image_groups_and_preserves_other_kinds(self):
        class Model:
            pass

        caches = {kind: Model() for kind in (*owner.IMAGE_CACHE_GROUPS, 'text_generation',
                                           'embedding', 'tts')}
        refs = {kind: weakref.ref(model) for kind, model in caches.items()}
        events = []

        def unload(kind):
            events.append(kind)
            return caches.pop(kind, None) is not None

        def clear():
            events.append('clear')
            self.assertTrue(all(refs[k]() is None for k in owner.IMAGE_CACHE_GROUPS))
            self.assertTrue(all(refs[k]() is caches[k] for k in caches))

        mx = SimpleNamespace(synchronize=lambda: events.append('sync'),
                             clear_cache=clear, get_cache_memory=lambda: 0,
                             get_active_memory=lambda: 128 * len(caches))
        with self.assertLogs(owner.LOGGER, level='INFO') as logs:
            owner.release_image_cache(mx, unload=unload)
        self.assertEqual(events, ['sync', 'image_generation', 'image_edit', 'clear'])
        self.assertIn('unloaded_groups=image_generation,image_edit', ''.join(logs.output))

    def test_overlap_defers_release_until_last_delivery_finishes(self):
        async def scenario(first_to_finish):
            delivered = [asyncio.Event(), asyncio.Event()]
            finish = [asyncio.Event(), asyncio.Event()]
            entered = []
            cleanup = Mock()

            async def app(scope, receive, send):
                index = scope['index']
                entered.append(index)
                await send({'type': 'http.response.start', 'status': 200})
                await send({'type': 'http.response.body', 'body': bytes([index])})
                delivered[index].set()
                await finish[index].wait()

            async def send(message):
                pass

            middleware = owner.ImageRequestCleanup(app, cleanup=cleanup)
            # First request cleans before delivery, then a second starts while
            # delivery is still in progress. Its cleanup must wait for the first.
            first = asyncio.create_task(middleware(
                {'type': 'http', 'method': 'POST', 'path': '/v1/images/generations',
                 'index': 0}, None, send))
            await delivered[0].wait()
            cleanup.assert_called_once_with()
            cleanup.reset_mock()
            second = asyncio.create_task(middleware(
                {'type': 'http', 'method': 'POST', 'path': '/v1/images/edits',
                 'index': 1}, None, send))
            await delivered[1].wait()
            cleanup.assert_not_called()
            tasks = (first, second)
            finish[first_to_finish].set()
            await tasks[first_to_finish]
            cleanup.assert_not_called()
            finish[1 - first_to_finish].set()
            await tasks[1 - first_to_finish]
            cleanup.assert_called_once_with()
            self.assertEqual(middleware.active_requests, 0)
            self.assertEqual(entered, [0, 1])
        for first_to_finish in (0, 1):
            with self.subTest(first_to_finish=first_to_finish):
                asyncio.run(scenario(first_to_finish))

    def test_waiting_request_prevents_unload_and_cancellation_releases_last_owner(self):
        async def scenario():
            waiting, unblock = asyncio.Event(), asyncio.Event()
            cleanup = Mock()

            async def app(scope, receive, send):
                if scope['path'].endswith('/edits'):
                    waiting.set()
                    await unblock.wait()
                else:
                    await send({'type': 'http.response.start', 'status': 200})

            async def send(message):
                pass

            middleware = owner.ImageRequestCleanup(app, cleanup=cleanup)
            pending = asyncio.create_task(middleware(
                {'type': 'http', 'method': 'POST', 'path': '/images/edits'}, None, send))
            await waiting.wait()
            await middleware({'type': 'http', 'method': 'POST',
                              'path': '/images/generations'}, None, send)
            cleanup.assert_not_called()
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
            cleanup.assert_called_once_with()
            self.assertEqual(middleware.active_requests, 0)
        asyncio.run(scenario())

    def test_reload_and_nonimage_launch_are_rejected_before_native_imports(self):
        for args in (['--image-model', '/fixture/model', '--reload'], ['--model', 'chat']):
            with self.subTest(args=args), patch.object(sys, 'argv', ['launcher', *args]):
                with self.assertRaises(SystemExit):
                    owner.main()

    def test_missing_launcher_fails_before_process_start(self):
        with patch.object(manager, 'IMAGE_SERVER_SCRIPT', Path('/nonexistent/fixture.py')), \
                patch.object(manager, 'resolve_mlx_python', return_value='/fixture/python'), \
                patch.object(manager.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'launcher is missing'):
                manager.launch_vlm_server(11501, image_model='/fixture/model')
        launch.assert_not_called()

    def test_chat_and_embedding_retain_the_native_module_launcher(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(manager, 'LOG_DIR', Path(tmp)), \
                patch.object(manager, 'prepare_clean_runtime_log'), \
                patch.object(manager, 'resolve_mlx_python', return_value='/fixture/python'), \
                patch.object(manager.subprocess, 'Popen') as launch:
            for kwargs in ({}, {'embedding_model': '/fixture/model'}):
                manager.launch_vlm_server(11502, **kwargs)
                self.assertEqual(launch.call_args.args[0][:3],
                                 ['/fixture/python', '-m', 'mlx_vlm.server'])


if __name__ == '__main__':
    unittest.main()
