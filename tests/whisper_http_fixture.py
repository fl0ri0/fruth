"""Run handler regressions over real HTTP, outside the offline runner's network guard.

Only ephemeral IPv4 loopback listeners, temporary WAVs and an injected provider
are used. No model loading, production state access or production services.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest


class CountingResult(unittest.TextTestResult):
    subtests_run = 0

    def addSubTest(self, test, subtest, error):
        self.subtests_run += 1
        super().addSubTest(test, subtest, error)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(source))
    sys.path.insert(0, str(source / 'tests'))
    import test_whisper_http_admission as fixture
    fixture.NATIVE_HTTP = True
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(fixture.WhisperAdmissionTests)
    identities = [test.id() for test in suite]
    with (args.output / 'http.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=CountingResult).run(suite)
    evidence = {
        'transport': 'real HTTP over ephemeral IPv4 loopback', 'tests': identities,
        'tests_run': result.testsRun, 'passed': result.wasSuccessful(),
        'subtests_run': result.subtests_run,
        'failures': [(test.id(), detail) for test, detail in result.failures],
        'errors': [(test.id(), detail) for test, detail in result.errors],
        'source_sha256': {name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in (
            'scripts/mlx_whisper_server.py', 'fruth_core/transports.py', 'fruth_core/http_contract.py',
            'tests/test_whisper_http_admission.py', 'tests/whisper_http_fixture.py')},
        'browser_exploitability_tested': False,
    }
    (args.output / 'results.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps({'passed': evidence['passed'], 'tests_run': result.testsRun, 'output': str(args.output)}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
