"""Offline Research workflow tests; every data path is under a temporary root."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from fruth_research import review

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('research_curate', HERE / 'gold-core/curate.py')
curate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(curate)


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.research = self.root / 'fruth_research'
        self.corpus = self.research / 'gold-core'
        (self.corpus / 'cases').mkdir(parents=True)
        shutil.copyfile(HERE / 'gold-core/schema.json', self.corpus / 'schema.json')
        review.write_json(self.corpus / 'manifest.json', {'schema_version': '1.0.0', 'corpus_version': 'v0', 'case_count': 0})
        self.source = self.root / 'state/self_learning/eval_cases.jsonl'
        self.source.parent.mkdir(parents=True)
        self.item = dict(case_id='eval-test', response_id='resp-test', case_kind='fulfilled_graph_contract',
                         severity='positive', layer='closure', summary='Test', evidence='synthetic')
        self.source.write_bytes(review.queue.encoded(self.item) + b'\n')
        self.queue_dir = self.research / 'candidates'
        review.queue.sync_candidates(self.source, self.queue_dir, root=self.root)
        self.ledger = self.root / 'state/response_frames/responses.jsonl'
        self.ledger.parent.mkdir()
        self.frame = dict(response_id='resp-test', frame_id='frame-1', frame_sequence=1,
                          current_state={'lifecycle_state': 'completed'}, frame_relation={})
        self.ledger.write_bytes(review.queue.encoded(self.frame) + b'\n')
        self.case = json.loads((HERE.parent / 'tests/testdata/research-gold-case.json').read_text())
        self.case['source'].update(response_ids=['resp-test'], eval_case_ids=['eval-test'], evidence_refs=[
            review.reference(self.source, self.root, 'eval', 'Exact source annotation.', byte_offset=0,
                             byte_length=self.source.stat().st_size)])
        self.case['adjudication']['evidence_refs'] = ['eval']
        self.case['evidence_assertions'] = [{'ref_id': 'eval', 'pointer': '/case_id', 'equals': 'eval-test'}]
        self.input = self.root / 'reviewed-case.json'
        self.save_case()

    def save_case(self):
        review.write_json(self.input, self.case)

    def test_audit_membership_is_not_adjudication(self):
        before = self.source.read_bytes()
        result = review.audit(self.root)
        self.assertEqual(result['membership_counts'], {'present': 1})
        self.assertEqual(result['annotation_binding_counts'], {'verified': 1})
        self.assertEqual(result['candidates'][0]['disposition'], 'unreviewed')
        self.assertEqual(self.source.read_bytes(), before)

    def test_audit_broken_lineage(self):
        frame = dict(self.frame, frame_id='frame-2', frame_sequence=2, frame_relation={'parent_frame_id': 'wrong'})
        with self.ledger.open('ab') as stream:
            stream.write(review.queue.encoded(frame) + b'\n')
        result = review.audit(self.root)
        self.assertEqual(result['membership_counts'], {'broken_lineage': 1})
        with self.assertRaisesRegex(ValueError, 'broken lineage'):
            review.inspect_response(self.root, result, 'resp-test')

    def test_inspect_detects_missing_sidecar(self):
        self.frame['external_snapshots'] = {'items': {'runtime': {
            'kind': 'fruth.response_frame_snapshot_ref', 'path': 'snapshots/absent.json', 'sha256': '0' * 64}}}
        self.ledger.write_bytes(review.queue.encoded(self.frame) + b'\n')
        result = review.inspect_response(self.root, review.audit(self.root), 'resp-test')
        self.assertEqual(result['failed_sidecars'], ['snapshots/absent.json'])

    def test_exact_binding_rejects_rewrite(self):
        result = review.audit(self.root)
        self.ledger.write_text('{}\n')
        with self.assertRaises(ValueError):
            review.inspect_response(self.root, result, 'resp-test')

    def test_annotation_tamper(self):
        self.source.write_text('{}\n')
        self.assertEqual(review.audit(self.root)['annotation_binding_counts'], {'unverified': 1})

    def test_prepare_does_not_promote(self):
        before = (self.queue_dir / 'candidates.jsonl').read_bytes()
        self.assertEqual(curate.curate(self.root, [self.input])['status'], 'prepared')
        self.assertEqual(list((self.corpus / 'cases').glob('*.json')), [])
        self.assertEqual((self.queue_dir / 'candidates.jsonl').read_bytes(), before)

    def test_apply_retains_exact_bytes_and_is_idempotent(self):
        result = curate.curate(self.root, [self.input], apply=True)
        self.assertEqual(result['validation']['case_count'], 1)
        self.source.unlink()
        self.assertEqual(review.gold.validate(self.corpus, [])['case_count'], 1)
        row = next(iter(review.queue.read_queue(self.queue_dir).values()))
        self.assertEqual(row['review']['disposition'], 'promoted')
        self.assertEqual(curate.curate(self.root, [self.input], apply=True)['status'], 'unchanged')

    def test_conflicting_case_rejected(self):
        curate.curate(self.root, [self.input], apply=True)
        self.case['title'] = 'Conflicting bytes'
        self.save_case()
        with self.assertRaisesRegex(ValueError, 'immutable'):
            curate.curate(self.root, [self.input], apply=True)

    def test_addition_preserves_old_cases_and_retained_bytes(self):
        curate.curate(self.root, [self.input], apply=True)
        old = (self.corpus / 'cases/gc-test.json').read_bytes()
        store = self.research / 'retained-evidence/gold-core-v0'
        entries = review.evidence.load_store(store)
        self.case['case_id'] = 'gc-distinct'
        self.case['semantic_dedup']['intent_shape'] = 'distinct-contract'
        self.save_case()
        result = curate.curate(self.root, [self.input], apply=True)
        self.assertEqual(result['validation']['case_count'], 2)
        self.assertEqual(result['added_evidence_bytes'], 0)
        self.assertEqual((self.corpus / 'cases/gc-test.json').read_bytes(), old)
        for e in entries.values():
            self.assertEqual(review.gold.digest(store / e['retained_path']), e['retained_sha256'])
        row = next(iter(review.queue.read_queue(self.queue_dir).values()))
        self.assertEqual(row['review']['gold_case_ids'], ['gc-distinct', 'gc-test'])

    def test_unbound_candidate_not_promoted(self):
        self.case['source']['response_ids'] = ['different-response']
        self.save_case()
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            curate.curate(self.root, [self.input], apply=True)

    def test_source_drift_prevents_publication(self):
        original = review.evidence.retain
        def changed(*args):
            result = original(*args)
            with (self.corpus / 'manifest.json').open('a') as stream:
                stream.write('\n')
            return result
        with mock.patch.object(review.evidence, 'retain', changed):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                curate.curate(self.root, [self.input], apply=True)
        self.assertEqual(list((self.corpus / 'cases').glob('*.json')), [])

    def test_invalid_assertion_never_promotes(self):
        self.case['evidence_assertions'][0]['equals'] = 'wrong'
        self.save_case()
        with self.assertRaisesRegex(ValueError, 'assertion mismatch'):
            curate.curate(self.root, [self.input], apply=True)
        self.assertEqual(next(iter(review.queue.read_queue(self.queue_dir).values()))['review']['disposition'], 'unreviewed')

    def test_duplicate_semantics_rejected_and_original_unchanged(self):
        curate.curate(self.root, [self.input], apply=True)
        original = (self.corpus / 'cases/gc-test.json').read_bytes()
        self.case['case_id'] = 'gc-duplicate'
        self.save_case()
        with self.assertRaisesRegex(ValueError, 'duplicate semantic key'):
            curate.curate(self.root, [self.input], apply=True)
        self.assertEqual((self.corpus / 'cases/gc-test.json').read_bytes(), original)

    def test_interrupted_publication_can_resume(self):
        def interrupted(research, pending):
            journal = review.gold.read_json(pending / 'journal.json')
            op = journal['operations'][0]
            target = research / op['target']
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pending / op['source'], target)
            raise OSError('interrupted')
        with mock.patch.object(curate, 'finish', interrupted):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                curate.curate(self.root, [self.input], apply=True)
        result = curate.curate(self.root, resume=True)
        self.assertEqual(result['validation']['case_count'], 1)
        self.assertFalse((self.research / '.curation-pending').exists())

    def test_recovery_conflict_does_not_overwrite_queue(self):
        with mock.patch.object(curate, 'finish', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                curate.curate(self.root, [self.input], apply=True)
        path = self.queue_dir / 'candidates.jsonl'
        path.write_bytes(path.read_bytes() + b'\n')
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'recovery conflict'):
            curate.curate(self.root, resume=True)
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
