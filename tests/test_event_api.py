import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from fruth_webserver import app


class EventApiTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('fruth_webserver.read_events')
    def test_event_history_route_uses_event_log_reader(self, mock_read_events):
        mock_read_events.return_value = [
            {'id': 'event-1', 'category': 'chat', 'action': 'request', 'status': 'ok'}
        ]

        response = self.client.get('/api/event_history?category=chat&limit=10')

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['items'][0]['id'], 'event-1')
        mock_read_events.assert_called_once()

    def test_inference_status_reads_recent_events_without_loading_whole_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            log = root / 'events.jsonl'
            log.write_text(''.join(json.dumps({'id': str(n), 'message': str(n), 'category': 'chat',
                                             'action': 'request', 'status': 'ok'}) + '\n'
                                   for n in range(30)))
            native_read = Path.read_text

            def forbid_whole_log(target, *args, **kwargs):
                if target == log:
                    raise AssertionError('status must not load the entire event log')
                return native_read(target, *args, **kwargs)

            with patch('fruth_webserver.EVENT_LOG_PATH', log), \
                    patch('fruth_webserver.FLASK_LOG_PATH', root / 'runtime.log'), \
                    patch('fruth_webserver.load_running_instances', return_value=[]), \
                    patch('fruth_webserver.merge_instances_with_runtime_status', return_value=[]), \
                    patch('fruth_inference.payload._build_self_learning_payload', return_value={'status': 'completed'}) as learning, \
                    patch('fruth_inference.payload.DEFAULT_ACCEPTED_LEARNING_POLICY_PATH', root / 'policy.json'), \
                    patch.object(Path, 'read_text', side_effect=forbid_whole_log, autospec=True):
                response = self.client.get('/api/inference')
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual([e['message'] for e in payload['recent_events']], [str(n) for n in range(29, 21, -1)])
            self.assertEqual(payload['self_learning']['status'], 'completed')
            learning.assert_called_once()


if __name__ == '__main__':
    unittest.main()
