"""Validator contract tests: synthetic evidence only, entirely in temporary roots."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gold_validate', HERE / 'validate.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.corpus = self.root / 'corpus'
        (self.corpus / 'cases').mkdir(parents=True)
        (self.root / 'state').mkdir()
        (self.corpus / 'schema.json').write_bytes((HERE / 'schema.json').read_bytes())
        self.evidence = self.root / 'state' / 'evidence.json'
        self.evidence.write_text('{"status":"passed"}\n')
        # Use a synthetic fixture; no active Gold dataset or historical evidence is required.
        self.case = json.loads((HERE.parents[1] / 'tests/testdata/research-gold-case.json').read_text())
        self.case['case_id'] = 'gc-test'
        self.case['source'].update(response_ids=[], frame_ids=[], eval_case_ids=[], evidence_refs=[{
            'ref_id': 'evidence', 'root_kind': 'state', 'path': 'evidence.json',
            'sha256': validator.digest(self.evidence), 'purpose': 'Synthetic fixture.'}])
        self.case['adjudication']['evidence_refs'] = ['evidence']
        self.case['evidence_assertions'] = [{'ref_id': 'evidence', 'pointer': '/status', 'equals': 'passed'}]

    def write(self, cases=None):
        cases = cases or [self.case]
        for c in cases:
            (self.corpus / 'cases' / (c['case_id'] + '.json')).write_text(json.dumps(c))
        manifest = {'schema_version': '1.0.0', 'corpus_version': 'v0', 'case_count': len(cases),
                    'case_ids': sorted(c['case_id'] for c in cases), **validator.counts(cases)}
        (self.corpus / 'manifest.json').write_text(json.dumps(manifest))

    def check(self, roots=None):
        return validator.validate(self.corpus, roots or [self.root])

    def test_valid(self):
        self.write()
        self.assertEqual(self.check()['case_count'], 1)

    def test_digest_tamper(self):
        self.write()
        self.evidence.write_text('{"status":"failed"}')
        with self.assertRaisesRegex(validator.Invalid, 'digest mismatch'):
            self.check()

    def test_missing_evidence(self):
        self.write()
        self.evidence.unlink()
        with self.assertRaisesRegex(validator.Invalid, 'missing evidence'):
            self.check()

    def test_path_escape(self):
        self.case['source']['evidence_refs'][0]['path'] = '../evidence.json'
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'unsafe evidence path'):
            self.check()

    def test_symlink_escape(self):
        outside = self.root / 'outside.json'
        outside.write_bytes(self.evidence.read_bytes())
        self.evidence.unlink()
        self.evidence.symlink_to(outside)
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'escaping evidence symlink'):
            self.check()

    def test_missing_required_label(self):
        self.write()
        path = self.corpus / 'cases' / 'gc-test.json'
        c = json.loads(path.read_text())
        del c['expected_outcome']
        path.write_text(json.dumps(c))
        with self.assertRaisesRegex(validator.Invalid, 'missing required'):
            self.check()

    def test_manifest_disagreement(self):
        self.write()
        p = self.corpus / 'manifest.json'
        m = json.loads(p.read_text())
        m['counts_by_case_role'] = {}
        p.write_text(json.dumps(m))
        with self.assertRaisesRegex(validator.Invalid, 'manifest counts_by_case_role'):
            self.check()

    def test_duplicate_id(self):
        self.write()
        (self.corpus / 'cases' / 'gc-zduplicate.json').write_text(json.dumps(self.case))
        with self.assertRaisesRegex(validator.Invalid, 'duplicate case id'):
            self.check()

    def test_duplicate_semantic_key(self):
        other = deepcopy(self.case)
        other['case_id'] = 'gc-other'
        other['title'] = 'A different prompt title cannot defeat semantic deduplication'
        self.write([self.case, other])
        with self.assertRaisesRegex(validator.Invalid, 'duplicate semantic key'):
            self.check()

    def test_explicit_duplicate_rationale(self):
        other = deepcopy(self.case)
        other['case_id'] = 'gc-other'
        for c in (self.case, other):
            c['semantic_dedup']['duplicate_rationale'] = 'Explicit provider comparison fixture.'
        self.write([self.case, other])
        self.assertEqual(self.check()['case_count'], 2)

    def test_correct_negative_cannot_require_fulfillment(self):
        self.case['case_role'] = 'correct_negative'
        self.case['contract']['requires_fulfillment'] = True
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'correct negative requires fulfillment'):
            self.check()

    def test_defect_cannot_be_expected_behavior(self):
        self.case['case_role'] = 'defect_regression'
        self.case['historical_result'] = 'defect'
        self.case['historical_observation'].update(
            violation=self.case['contract']['desired_behavior'], causal_classification='fixture')
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'historical defect used as gold contract'):
            self.check()

    def test_unresolved_adjudication(self):
        self.case['adjudication']['status'] = 'unresolved'
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'uncertain case promoted'):
            self.check()

    def test_recorded_fact_mismatch(self):
        self.case['evidence_assertions'][0]['equals'] = 'failed'
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'evidence assertion mismatch'):
            self.check()

    def test_byte_range_survives_append(self):
        data = self.evidence.read_bytes()
        ref = self.case['source']['evidence_refs'][0]
        ref.update(byte_offset=0, byte_length=len(data), sha256=hashlib.sha256(data).hexdigest())
        self.write()
        with self.evidence.open('ab') as handle:
            handle.write(b'{"later":"successor"}\n')
        self.assertEqual(self.check()['case_count'], 1)

    def test_wrong_byte_range(self):
        ref = self.case['source']['evidence_refs'][0]
        ref.update(byte_offset=1, byte_length=self.evidence.stat().st_size)
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'short evidence range'):
            self.check()

    def test_explicit_archive_relocation(self):
        archive = self.root / 'archive'
        (archive / 'state').mkdir(parents=True)
        self.evidence.rename(archive / 'state' / 'evidence.json')
        self.write()
        self.assertEqual(self.check([archive])['case_count'], 1)

    def test_corrupt_live_file_not_hidden_by_archive(self):
        archive = self.root / 'archive'
        (archive / 'state').mkdir(parents=True)
        (archive / 'state' / 'evidence.json').write_bytes(self.evidence.read_bytes())
        self.write()
        self.evidence.write_text('corrupt')
        with self.assertRaisesRegex(validator.Invalid, 'digest mismatch'):
            self.check([self.root, archive])

    def test_unsupported_schema_keyword(self):
        self.write()
        p = self.corpus / 'schema.json'
        schema = json.loads(p.read_text())
        schema['unsupported'] = True
        p.write_text(json.dumps(schema))
        with self.assertRaisesRegex(validator.Invalid, 'unsupported schema keywords'):
            self.check()

    def test_duplicate_json_property(self):
        self.write()
        self.evidence.write_text('{"status":"passed","status":"failed"}')
        self.case['source']['evidence_refs'][0]['sha256'] = validator.digest(self.evidence)
        self.write()
        with self.assertRaisesRegex(validator.Invalid, 'duplicate JSON key'):
            self.check()


if __name__ == '__main__':
    unittest.main()
