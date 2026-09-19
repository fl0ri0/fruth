import unittest

from fruth_inference.request_meta import (
    MAX_PLANNER_TIMEOUT_MS,
    MIN_PLANNER_TIMEOUT_MS,
    apply_request_meta_to_route_context,
    normalize_request_meta,
)


class InferenceRequestMetaTests(unittest.TestCase):
    def test_canonical_role_list_filters_invalid_values_without_accepting_mode_aliases(self):
        for value in ('repair', ['coder'], {'repairer': True}, ['Repairer'], [None, 7]):
            with self.subTest(value=value):
                result = normalize_request_meta({'semantic_role_ids': value})
                self.assertEqual(result['semantic_role_ids'], [])
                self.assertIsNone(result['semantic_role_ids_source'])
        result = normalize_request_meta({'semantic_role_ids': ['repairer', 'missing', 'repairer', 'evidence_reasoner']})
        self.assertEqual(result['semantic_role_ids'], ['repairer', 'evidence_reasoner'])

    def test_role_list_form_input_and_top_level_precedence(self):
        result = normalize_request_meta({
            'request_meta': {'semantic_role_ids': ['materializer']},
            'semantic_role_ids': '["repairer", "evidence_reasoner"]',
        })
        self.assertEqual(result['semantic_role_ids'], ['repairer', 'evidence_reasoner'])
        cleared = normalize_request_meta({
            'request_meta': {'semantic_role_ids': ['materializer']}, 'semantic_role_ids': [],
        })
        self.assertEqual(cleared['semantic_role_ids'], [])

    def test_normalize_request_meta_defaults_to_embedding_helper_and_no_planner_override(self):
        request_meta = normalize_request_meta({})

        self.assertTrue(request_meta['developer_flags']['embedding_signals_enabled'])
        self.assertIsNone(request_meta['developer_flags']['planner_timeout_ms'])
        self.assertEqual(request_meta['developer_flags']['accepted_learning_authority'], 'soft_hint')

    def test_normalize_request_meta_ignores_retired_routing_flags_and_clamps_planner_timeout(self):
        request_meta = normalize_request_meta(
            {
                'role': 'diagnostics',
                'semantic_role_ids': ['repairer', 'evidence_reasoner', 'doubt_challenger'],
                'developer_flags': (
                    '{"heuristics_enabled":"false","semantic_router_required":"true",'
                    '"router_timeout_ms":"10","planner_timeout_ms":"999999999"}'
                ),
                'executionProfile': '{"dry_run": true}',
            }
        )

        self.assertEqual(request_meta['semantic_role_ids'], ['repairer', 'evidence_reasoner', 'doubt_challenger'])
        self.assertEqual(request_meta['semantic_role_ids_source'], 'request')
        self.assertIsNone(request_meta['capability_hint'])
        self.assertIsNone(request_meta['capability_hint_source'])
        self.assertTrue(request_meta['developer_flags']['embedding_signals_enabled'])
        self.assertEqual(request_meta['developer_flags']['planner_timeout_ms'], MAX_PLANNER_TIMEOUT_MS)

    def test_normalize_request_meta_uses_embedding_signals_clamps_timeout_and_ignores_drc_flags(self):
        request_meta = normalize_request_meta(
            {
                'developer_flags': {
                    'embedding_signals_enabled': False,
                    'inference_plan_refinement_mode': 'compare',
                    'semantic_handoff_review_mode': 'on',
                    'planner_timeout_ms': '10',
                }
            }
        )

        self.assertFalse(request_meta['developer_flags']['embedding_signals_enabled'])
        self.assertNotIn('inference_plan_refinement_mode', request_meta['developer_flags'])
        self.assertNotIn('semantic_handoff_review_mode', request_meta['developer_flags'])
        self.assertEqual(request_meta['developer_flags']['planner_timeout_ms'], MIN_PLANNER_TIMEOUT_MS)
        self.assertEqual(request_meta['developer_flags']['accepted_learning_authority'], 'soft_hint')

    def test_normalize_request_meta_accepts_bounded_learning_authority_levels(self):
        request_meta = normalize_request_meta(
            {
                'request_meta': {
                    'developer_flags': {
                        'acceptedLearningAuthority': 'preferred',
                    },
                },
            }
        )
        invalid = normalize_request_meta(
            {
                'developer_flags': {
                    'accepted_learning_authority': 'silent-auto-mutate',
                },
            }
        )

        self.assertEqual(request_meta['developer_flags']['accepted_learning_authority'], 'preferred')
        self.assertEqual(invalid['developer_flags']['accepted_learning_authority'], 'soft_hint')

    def test_normalize_request_meta_accepts_nested_request_meta_envelope(self):
        request_meta = normalize_request_meta(
            {
                'request_meta': {
                    'semantic_role_ids': ['possibility_expander', 'materializer', 'quality_reviewer'],
                    'capability_hint': 'text_to_speech',
                    'developer_flags': {
                        'embedding_signals_enabled': False,
                    },
                }
            }
        )

        self.assertEqual(request_meta['semantic_role_ids'], ['possibility_expander', 'materializer', 'quality_reviewer'])
        self.assertEqual(request_meta['capability_hint'], 'text_to_speech')
        self.assertEqual(request_meta['capability_hint_source'], 'request')
        self.assertFalse(request_meta['developer_flags']['embedding_signals_enabled'])

    def test_apply_request_meta_to_route_context_attaches_compact_meta(self):
        route_context = {
            'recent_messages': [
                {'role': 'user', 'content': 'prefer german'},
            ],
            'runtime': {},
        }

        updated = apply_request_meta_to_route_context(
            route_context,
            normalize_request_meta(
                {
                    'developer_flags': {
                        'embedding_signals_enabled': False,
                    }
                }
            ),
        )

        self.assertIn('request_meta', updated)
        self.assertEqual(updated['recent_messages'], [{'role': 'user', 'content': 'prefer german'}])
        self.assertFalse(updated['runtime']['request_meta']['developer_flags']['embedding_signals_enabled'])


if __name__ == '__main__':
    unittest.main()
