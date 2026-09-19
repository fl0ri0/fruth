import unittest

from fruth_inference.semantic_role_profile import (
    build_self_modification_contract,
    build_semantic_role_profile,
)
from fruth_inference.semantic_roles import build_semantic_role_catalog, normalize_semantic_role_ids, semantic_role


class SemanticRoleTests(unittest.TestCase):
    def test_internal_intent_hint_synonyms_preserve_original_orientation(self):
        expected = {
            'worker': 'worker', 'build': 'worker', 'builder': 'worker', 'execute': 'worker',
            'improviser': 'improviser', 'creative': 'improviser', 'improvise': 'improviser',
            'repair': 'repair', 'fix': 'repair', 'healer': 'repair',
            'explorer': 'explorer', 'investigate': 'explorer', 'research': 'explorer',
        }
        for hint, mode in expected.items():
            for value in (hint, '  ' + hint.upper() + '  '):
                with self.subTest(hint=value):
                    profile = build_semantic_role_profile({'intent': {'temperament_hint': value}})
                    self.assertEqual(profile['mode'], mode)
                    self.assertEqual(profile['mode_source'], 'intent')
                    self.assertEqual(profile['runtime_orientation']['runtime_effect'], 'none')

    def test_profile_respects_explicit_role_ids_without_runtime_authority(self):
        profile = build_semantic_role_profile(
            {
                'runtime': {
                    'inference_issues': [],
                    'inference_self_healing_hints': [],
                }
            },
            request_meta={
                'semantic_role_ids': ['repairer', 'evidence_reasoner', 'doubt_challenger'],
            },
        )

        self.assertEqual(profile['kind'], 'fruth.semantic_role_profile')
        self.assertEqual(profile['mode'], 'explicit_roles')
        self.assertEqual(profile['mode_source'], 'request')
        self.assertIn('repairer', profile['semantic_role_ids'])
        self.assertIn('evidence_reasoner', profile['semantic_role_ids'])
        self.assertEqual(profile['runtime_orientation']['planner_timeout_bonus_sec'], 0)
        self.assertEqual(profile['runtime_orientation']['authority'], 'semantic_role_metadata_only')
        self.assertEqual(profile['semantic_role_orientation']['authority'], 'advisory_read_model_only')
        self.assertIn('repairer', profile['semantic_role_orientation']['suggested_semantic_review_lenses'])
        self.assertNotIn('deliberation_orientation', profile)
        self.assertIn('policies', profile['self_modification']['allowed_surfaces'])

    def test_profile_infers_improviser_from_intent(self):
        profile = build_semantic_role_profile(
            {
                'prompt': 'Imagine a mystical village and write a lyrical story about it.',
                'runtime': {
                    'inference_issues': [],
                    'inference_self_healing_hints': [],
                },
            },
        )

        self.assertEqual(profile['mode'], 'improviser')
        self.assertEqual(profile['mode_source'], 'intent')
        self.assertIn('possibility_expander', profile['semantic_role_ids'])
        self.assertIn('quality_reviewer', profile['semantic_role_orientation']['suggested_semantic_review_lenses'])

    def test_profile_promotes_repair_orientation_for_retry_failure(self):
        profile = build_semantic_role_profile(
            {
                'runtime': {
                    'inference_issues': [],
                    'inference_self_healing_hints': [{'kind': 'avoid_degraded_runtime_paths'}],
                }
            },
            retry_failure={
                'failed_instance_id': 'chat-1',
                'status_code': 503,
            },
        )

        self.assertEqual(profile['mode'], 'repair')
        self.assertEqual(profile['mode_source'], 'retry_failure')
        self.assertTrue(profile['signals']['retry_failure_active'])
        self.assertEqual(profile['runtime_orientation']['prioritize_recovery'], 'advisory_orientation_only')

    def test_catalog_exposes_canonical_roles_and_self_modification_boundary(self):
        role_catalog = build_semantic_role_catalog()
        contract = build_self_modification_contract()

        self.assertIn('possibility_expander', {item['role_id'] for item in role_catalog})
        self.assertIn('doubt_challenger', {item['role_id'] for item in role_catalog})
        self.assertIn('transition_committer', {item['role_id'] for item in role_catalog})
        self.assertFalse(contract['silent_runtime_code_rewrites_allowed'])
        self.assertIn('artifact_plans', contract['allowed_surfaces'])

    def test_old_role_names_normalize_to_global_semantic_roles(self):
        self.assertEqual(semantic_role('coder')['role_id'], 'materializer')
        self.assertEqual(semantic_role('risk-analyst')['role_id'], 'risk_sentinel')
        self.assertEqual(semantic_role('Sokratischer Interviewer')['role_id'], 'doubt_challenger')
        self.assertEqual(
            normalize_semantic_role_ids(['possibility_expander', 'structural_planner', 'integrator']),
            ['possibility_expander', 'structural_planner', 'integrator'],
        )

    def test_repair_roles_ask_for_resolving_evidence_rebinds(self):
        repairer = semantic_role('repairer')
        evidence_reasoner = semantic_role('evidence_reasoner')

        self.assertIn('rebind_dependency_evidence', repairer['allowed_advisory_actions'])
        self.assertIn('resolving_runtime_evidence', repairer['evidence_requirements'])
        self.assertTrue(
            any('runtime already contain concrete evidence' in question for question in repairer['focus_questions'])
        )
        self.assertIn('rebind_dependency_evidence', evidence_reasoner['allowed_advisory_actions'])
        self.assertIn('rebind_candidate', evidence_reasoner['evidence_requirements'])
        self.assertIn('rebind candidate', evidence_reasoner['success_definition'])
        self.assertTrue(
            any('rebound to the blocked branch' in question for question in evidence_reasoner['focus_questions'])
        )

    def test_artifact_kind_obligations_are_explicit_in_semantic_roles(self):
        structural_planner = semantic_role('structural_planner')
        materializer = semantic_role('materializer')
        quality_reviewer = semantic_role('quality_reviewer')

        self.assertIn('missing_artifact_kind_obligation', structural_planner['failure_modes'])
        self.assertIn('requested_artifact_kinds', structural_planner['evidence_requirements'])
        self.assertTrue(
            any('requested artifact kinds' in question for question in structural_planner['focus_questions'])
        )
        self.assertTrue(
            any('image-before-page work' in question for question in structural_planner['focus_questions'])
        )

        self.assertIn('artifact_kind_mismatch', materializer['failure_modes'])
        self.assertIn('owed_artifact_kind', materializer['evidence_requirements'])
        self.assertTrue(
            any('image prompt' in question for question in materializer['focus_questions'])
        )

        self.assertIn('missing_requested_artifact_kind', quality_reviewer['failure_modes'])
        self.assertIn('artifact_registry', quality_reviewer['evidence_requirements'])
        self.assertIn('requested_artifact_kinds', quality_reviewer['evidence_requirements'])
        self.assertTrue(
            any('every requested artifact kind' in question for question in quality_reviewer['focus_questions'])
        )

    def test_explicit_roles_do_not_gain_runtime_authority(self):
        expected_boundary = {
            'planner_timeout': 'explicit_developer_flags_only',
            'branch_topology': 'runtime_contracts_only',
            'payload_authority': 'branch_local_contracts_only',
            'promotion': 'promotion_review_only',
            'waiver': 'closure_or_contract_truth_only',
            'supersession': 'closure_or_contract_truth_only',
            'execution': 'runtime_contracts_only',
            'freeze': 'closure_truth_only',
            'runtime_effect': 'none',
        }
        for semantic_role_ids in ([role['role_id']] for role in build_semantic_role_catalog()):
            with self.subTest(semantic_role_ids=semantic_role_ids):
                profile = build_semantic_role_profile({}, request_meta={'semantic_role_ids': semantic_role_ids})

                self.assertEqual(profile['runtime_orientation']['planner_timeout_bonus_sec'], 0)
                self.assertFalse(profile['runtime_orientation']['allow_branching'])
                self.assertEqual(profile['runtime_orientation']['runtime_effect'], 'none')
                self.assertEqual(profile['authority_boundary'], expected_boundary)
                self.assertEqual(profile['semantic_role_orientation']['authority'], 'advisory_read_model_only')
                self.assertIn('Runtime/Contracts/Closure decide truth', profile['semantic_role_orientation']['non_authority_boundary'])


if __name__ == '__main__':
    unittest.main()
