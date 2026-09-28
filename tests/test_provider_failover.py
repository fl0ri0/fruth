"""Offline provider recovery: request identity survives a different executor."""
import copy
from contextlib import ExitStack
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import requests
import fruth_webserver as server
from fruth_server.backend_transport_runtime import provider_failover_reason
from fruth_server.responses_request_runtime import PROVIDER_FAILOVER_MAX_ATTEMPTS
from tests import test_responses_api as existing


def http_error(status=500, message='You have reached the usage limit for this model. Please try again later.'):
    response = requests.Response()
    response.status_code = status
    response._content = ('{"error": "' + message + '"}').encode()
    response.headers['Content-Type'] = 'application/json'
    return requests.HTTPError(message, response=response)


def instance(name, backend, port, vision=False):
    return {'instance_id': name, 'model': name, 'backend': backend, 'port': port,
            'capability': 'chat', 'provider_capabilities': ['chat', 'vision_analysis'] if vision else ['chat'],
            'inputs': ['text', 'image'] if vision else ['text'],
            'runtime_status': {'readiness': 'ready', 'activity': 'idle'}}


class ProviderFailureClassificationTests(unittest.TestCase):
    def test_availability_errors(self):
        for error in (http_error(), http_error(429), http_error(503, 'Unavailable'),
                      requests.Timeout('slow'), requests.ConnectionError('closed')):
            with self.subTest(error=str(error)):
                self.assertIsNotNone(provider_failover_reason(str(error), exception=error))

    def test_content_request_and_evidence_errors_do_not_authorize_failover(self):
        for message in ('Safety guardrail violation', 'BLOCKED: cannot comply',
                        'Content policy refusal', 'invalid request',
                        "The session's transcript exceeded the model's context size.",
                        'audio integrity check failed', 'transcript mismatch',
                        'artifact missing', 'digest mismatch', 'unexpected parser exception'):
            with self.subTest(message=message):
                self.assertIsNone(provider_failover_reason(message, exception=ValueError(message), status_code=500))
        self.assertIsNone(provider_failover_reason('model unavailable', exception=http_error(400)))
        self.assertIsNone(provider_failover_reason('content filter rejected request', exception=http_error(503)))
        self.assertIsNone(provider_failover_reason('Unknown internal failure', status_code=500))


class ProviderFailoverApiTests(unittest.TestCase):
    # Reuse the existing temporary frame/registry/history fixtures without
    # inheriting (and collecting) the entire Responses suite again.
    setUp = existing.ResponsesApiTests.setUp
    tearDown = existing.ResponsesApiTests.tearDown

    def run_request(self, *, instances=None, preferences=None, errors=None, extra=None, direct=False,
                    stream=False, file_path=None, callback=None, deltas=None):
        pool = instances or [instance('pcc', 'apple_pcc', 11651),
                             instance('gemma', 'ollama', 11435),
                             instance('afm', 'apple_fm', 11601)]
        first = pool[0]
        route = {'instance_id': first['instance_id'], 'instance': first, 'capability': 'chat',
                 'route_source': 'inference_carried', 'route_runtime': {
                     'inference_preferences': preferences or {},
                     'accepted_task_identity': {'phase_id': 'answer', 'dependency_ids': ['saved-source']},
                 }}
        payload = {'input': 'Explain this source.', 'response_id': 'resp_provider_failover',
                   'inference_route': not direct, 'capability': 'chat', 'stream': stream,
                   'selected_reference_artifacts': [{'type': 'message', 'content': 'Exact saved source.',
                                                     'message_id': 'msg_saved_source', 'artifact_ref': 'msg_saved_source'}]}
        if direct:
            payload['instance_id'] = first['instance_id']
        if file_path:
            payload['file_path'] = str(file_path)
        payload.update(extra or {})
        outcomes = iter(errors if errors is not None else [http_error(), 'A grounded explanation.'])
        calls = []
        self.handoffs = []
        real_policy = server._inject_inference_runtime_policy_into_chat_messages
        def policy(messages, **kwargs):
            self.handoffs.append(copy.deepcopy(kwargs))
            return real_policy(messages, **kwargs)
        def execute(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            value = next(outcomes)
            if callback:
                callback(kwargs)
            if isinstance(value, Exception):
                raise value
            return value
        def infer(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            value = next(outcomes)
            if isinstance(value, Exception):
                return {'error': str(value)}, 500
            return {'content': value, 'capability': 'chat', 'mode': 'chat'}, 200
        def prepare(data, **kwargs):
            return data, kwargs['route_info'], {}, {}
        with ExitStack() as stack:
            for name, value in (
                ('load_running_instances', pool), ('merge_instances_with_runtime_status', pool),
                ('_resolve_inference_auto_route', (route, None)), ('_lookup_instance', first),
            ):
                stack.enter_context(patch.object(server, name, return_value=value))
            stack.enter_context(patch.object(server, '_inject_inference_runtime_policy_into_chat_messages', side_effect=policy))
            planner = stack.enter_context(patch.object(server, '_prepare_effective_request_data', side_effect=prepare))
            resolver = stack.enter_context(patch.object(server, '_resolve_responses_target_instance', wraps=server._resolve_responses_target_instance))
            stack.enter_context(patch.object(server, '_execute_chat_backend_request', side_effect=execute))
            stack.enter_context(patch.object(server, '_invoke_internal_api_json_route', side_effect=infer))
            if stream:
                stack.enter_context(patch.object(server, '_open_openai_chat_stream', side_effect=execute))
                stack.enter_context(patch.object(server, '_open_ollama_chat_stream', side_effect=lambda **kw: (execute(**kw), kw['target_port'])))
                stack.enter_context(patch.object(server, '_iter_openai_stream_deltas', return_value=deltas if deltas is not None else iter(['A grounded explanation.'])))
                stack.enter_context(patch.object(server, '_iter_ollama_stream_deltas', return_value=deltas if deltas is not None else iter(['A grounded explanation.'])))
            response = self.client.post('/api/responses', json=payload)
            response.get_data()
            response_id = payload.get('response_id') or next(iter(server._RESPONSE_LOOKUP))
            saved = self.client.get(f'/api/responses/{response_id}?view=debug').get_json()
        return response, saved, calls, planner, resolver

    def test_preferred_fallback_then_automatic_preserves_request_and_evidence(self):
        prefs = {'primary_mode': 'prefer', 'primary_target': {'model': 'pcc', 'backend': 'apple_pcc'},
                 'fallback_target': {'model': 'afm', 'backend': 'apple_fm'}}
        response, saved, calls, planner, resolver = self.run_request(
            preferences=prefs, errors=[http_error(), requests.Timeout(), 'A grounded explanation.'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['backend'] for c in calls], ['apple_pcc', 'apple_fm', 'ollama'])
        self.assertEqual(planner.call_count, 1)
        for call in calls:
            text = str(call['messages'])
            self.assertIn('Explain this source.', text)
            self.assertIn('Exact saved source.', text)
        audit = saved['runtime']['provider_failover']
        self.assertEqual([a['instance_id'] for a in audit['attempts']], ['pcc', 'afm'])
        self.assertEqual(audit['selected_instance_id'], 'gemma')
        self.assertEqual(saved['response_frame']['runtime']['provider_failover'], audit)
        self.assertEqual(saved['runtime']['accepted_task_identity']['dependency_ids'], ['saved-source'])
        self.assertEqual(resolver.call_args.kwargs['excluded_instance_ids'], ['pcc', 'afm'])
        self.assertEqual(saved['output_text'], 'A grounded explanation.')
        self.assertEqual(saved['instance_id'], 'gemma')
        graphs = [h['request_payload']['inference_preview']['working_frame']['request_phase_graph'] for h in self.handoffs]
        self.assertTrue(all(graph == graphs[0] for graph in graphs[1:]))

    def test_without_preferences_uses_existing_automatic_selection(self):
        response, saved, calls, _, _ = self.run_request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]['target_port'], calls[1]['target_port'])
        self.assertEqual(saved['runtime']['provider_failover']['attempts'][0]['reason'], 'provider_usage_limit')

    def test_direct_and_locked_requests_do_not_switch(self):
        for options in ({'direct': True}, {'preferences': {'primary_mode': 'lock', 'primary_target': {'model': 'pcc'}}}):
            with self.subTest(options=options):
                response, _, calls, _, _ = self.run_request(**options, errors=[http_error()])
                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(calls), 1)

    def test_refusal_and_invalid_request_do_not_switch(self):
        for error in (http_error(500, 'Safety guardrail violation'), http_error(400, 'Invalid request'),
                      http_error(502, 'The model cannot provide a response for this request. Please revise the request and try again.'),
                      ValueError('audio integrity mismatch')):
            with self.subTest(error=str(error)):
                response, _, calls, _, _ = self.run_request(errors=[error])
                self.assertEqual(response.status_code, 500)
                self.assertEqual(len(calls), 1)

    def test_no_alternative_records_failed_attempt(self):
        response, saved, calls, _, _ = self.run_request(instances=[instance('pcc', 'apple_pcc', 11651)], errors=[http_error()])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(calls), 1)
        self.assertEqual(saved['runtime']['provider_failover']['stop_reason'], 'no_compatible_running_alternative')

    def test_exhaustion_never_retries_an_instance_or_exceeds_budget(self):
        pool = [instance('model-' + str(i), 'ollama', 11434+i) for i in range(6)]
        response, saved, calls, _, _ = self.run_request(instances=pool, errors=[requests.Timeout()] * 6)
        self.assertEqual(response.status_code, 504)
        ports = [c['target_port'] for c in calls]
        self.assertEqual(len(ports), PROVIDER_FAILOVER_MAX_ATTEMPTS)
        self.assertEqual(len(set(ports)), len(ports))
        self.assertEqual(saved['runtime']['provider_failover']['stop_reason'], 'attempt_limit')

    def test_stream_open_failure_retries_before_any_output(self):
        response, saved, calls, planner, _ = self.run_request(stream=True, errors=[http_error(), Mock()])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(planner.call_count, 1)
        self.assertEqual(saved['output_text'], 'A grounded explanation.')
        self.assertEqual(saved['runtime']['provider_failover']['attempts'][0]['instance_id'], 'pcc')

    def test_file_retry_keeps_exact_input_and_skips_text_only_fallback(self):
        source = Path(self._runtime_tmpdir.name) / 'source.png'
        from tests.fake_backends.fixtures import tiny_png_bytes
        source.write_bytes(tiny_png_bytes())
        pool = [instance('pcc', 'apple_pcc', 11651, True), instance('afm', 'apple_fm', 11601),
                instance('vision', 'mlx', 11602, True)]
        response, saved, calls, planner, _ = self.run_request(
            instances=pool, file_path=source, preferences={'primary_mode': 'prefer', 'fallback_target': {'model': 'afm'}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual([c['payload']['instance_id'] for c in calls], ['pcc', 'vision'])
        self.assertTrue(all(c['payload']['file_path'] == str(source) for c in calls))
        self.assertEqual(source.read_bytes(), tiny_png_bytes())
        self.assertEqual(planner.call_count, 1)

    def test_control_incompatible_fallback_is_skipped_without_dropping_controls(self):
        pool = [instance('gemma', 'ollama', 11435), instance('pcc', 'apple_pcc', 11651),
                instance('afm', 'apple_fm', 11601)]
        response, saved, calls, _, _ = self.run_request(
            instances=pool, extra={'temperature': 0.4, 'max_tokens': 2400},
            preferences={'primary_mode': 'prefer', 'fallback_target': {'model': 'pcc'}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['backend'] for c in calls], ['ollama', 'apple_fm'])
        self.assertTrue(all(c['temperature'] == 0.4 and c['max_tokens'] == 2400 for c in calls))

    def test_stream_exhaustion_persists_all_attempts_on_same_response(self):
        pool = [instance('pcc', 'apple_pcc', 11651), instance('afm', 'apple_fm', 11601)]
        response, saved, calls, _, _ = self.run_request(instances=pool, stream=True, errors=[http_error(), http_error()])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(calls), 2)
        self.assertEqual(saved['id'], 'resp_provider_failover')
        self.assertEqual([a['instance_id'] for a in saved['runtime']['provider_failover']['attempts']], ['pcc', 'afm'])
        self.assertEqual(saved['runtime']['provider_failover']['stop_reason'], 'no_compatible_running_alternative')

    def test_stream_failure_after_content_does_not_switch_producers(self):
        def partial():
            yield 'Partial answer.'
            raise requests.ConnectionError('connection reset')
        response, saved, calls, _, _ = self.run_request(stream=True, errors=[Mock()], deltas=partial())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertIn('response.failed', response.get_data(as_text=True))
        self.assertNotIn('provider_failover', saved.get('runtime') or {})

    def test_each_backend_can_fail_over(self):
        for backend in ('ollama', 'mlx', 'llama_cpp', 'apple_fm', 'apple_pcc'):
            with self.subTest(backend=backend):
                pool = [instance('primary', backend, 12001), instance('alternative', 'ollama', 12002)]
                response, saved, calls, _, _ = self.run_request(instances=pool, errors=[requests.ConnectionError(), 'Recovered.'])
                self.assertEqual(response.status_code, 200)
                self.assertEqual([c['target_port'] for c in calls], [12001, 12002])
                self.assertEqual(saved['output_text'], 'Recovered.')

    def test_text_file_can_fail_over_to_text_only_provider(self):
        source = Path(self._runtime_tmpdir.name) / 'source.txt'
        source.write_text('Exact original file content.')
        pool = [instance('pcc', 'apple_pcc', 11651), instance('text', 'ollama', 11435)]
        response, _, calls, _, _ = self.run_request(instances=pool, file_path=source)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c['payload']['instance_id'] for c in calls], ['pcc', 'text'])
        self.assertTrue(all(c['payload']['file_path'] == str(source) for c in calls))
        self.assertEqual(source.read_text(), 'Exact original file content.')

    def test_stream_retry_retains_generated_response_id_without_orphan_lookup(self):
        response, saved, calls, _, _ = self.run_request(stream=True, extra={'response_id': None}, errors=[http_error(), Mock()])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(server._RESPONSE_LOOKUP), 1)
        self.assertEqual(saved['id'], next(iter(server._RESPONSE_LOOKUP)))
        self.assertEqual(saved['output_text'], 'A grounded explanation.')
