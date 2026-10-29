"""Native caller-to-saved-result controls, using isolated controlled transport."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.fake_backends.fixtures import tiny_png_bytes
from tests.test_bare_filename_intake import REQUEST, FILES
from tests.test_explicit_file_contract_preservation import obligation_identities
from tests.test_instruction_admission_contract import settle
from tests.test_relative_file_exclusion import native_owners, reply, PROMPTS


# Independently declared provider content and saved-byte oracle. The caller's
# bare names do not specify these bodies; this proves materialization/binding,
# not semantic review accuracy or image meaning.
EXPECTED = {
    'note.txt': b'Controlled note payload: alpha-17.\n',
    'status.json': b'{"status":"ok","sequence":17}\n',
}


def run_named_file_request(tmp_path, extra_proposal, *, include_images=False, explicit_targets=False):
    prompt = REQUEST if include_images else 'Create note.txt. Create status.json. Do not create other files.'
    record = {'request': prompt, 'extra_provider_proposal': extra_proposal,
              'expected_bytes': {k: v.decode() for k, v in EXPECTED.items()}}
    def provider(call, index):
        if index == 1:
            output = reply(PROMPTS) if include_images else 'Preparation complete.'
            if extra_proposal:
                output += '\n\nCreate unrequested.txt containing an extra deliverable.'
            return output
        output = ('<artifact identifier="note.txt" type="text/plain">'
                  'Controlled note payload: alpha-17.</artifact>\n'
                  '<artifact identifier="status.json" type="application/json">'
                  '{"status":"ok","sequence":17}</artifact>')
        if extra_proposal:
            output += ('\n<artifact identifier="unrequested.txt" type="text/plain">'
                       'Unauthorized same-extension file.</artifact>')
        return output

    label = f'bare-native-images-{include_images}-extras-{extra_proposal}-targets-{explicit_targets}'
    request = {'response_id': label, 'prompt': prompt,
               'inference_route': True, 'developer_flags': {'embedding_signals_enabled': False}}
    if explicit_targets:
        request['text_artifact_requests'] = [
            {'source_name': name, 'extension': extension,
             'target_path': str(tmp_path / 'artifacts/documents' / (name + '.' + extension))}
            for name, extension in sorted(FILES)]
        record['explicit_targets'] = deepcopy(request['text_artifact_requests'])
    try:
        with native_owners(tmp_path, provider) as harness:
            try:
                initial, status = harness.post_response(request)
                assert status == 200
                record['initial_lifecycle'] = initial.get('lifecycle_state')
                final = settle(harness, initial, request)
                graph = final['runtime']['request_phase_graph']
                record.update(lifecycle=final['lifecycle_state'],
                    closure={k:final['runtime'].get('graph_closure_review',{}).get(k)
                             for k in ('status','completion_basis','content_requirement_count',
                                       'unresolved_content_requirement_count')},
                    terminal={k:final.get('late_fill',{}).get(k) for k in ('status',
                        'final_materialization_contract_status','materialization_contract_open_checks')},
                    obligations=graph['intent_obligations'],
                    output_obligations=graph['output_obligations'],
                    branches=[{k:b.get(k) for k in ('branch_id','phase_id','depends_on',
                        'text_artifact_source_name','text_artifact_extension','artifact_request')}
                        for b in graph['downstream_branches']],
                    outputs=final['outputs'],
                    artifacts=[{k:a.get(k) for k in ('artifact_ref','path','name','extension',
                        'branch_id','phase_id','file_sha256','text_artifact_request',
                        'text_artifact_saved_evidence')} for a in final['artifacts']],
                    results=[{k:r.get(k) for k in ('branch_id','phase_id','status','saved_text_path',
                        'saved_text_artifacts','text_artifact_saved_evidence','error')}
                        for r in final.get('late_fill',{}).get('fill_results',[])])
                assert graph['prompt'] == prompt
                assert obligation_identities(graph) == FILES
                images = list(harness.images_dir.rglob('*.png'))
                docs = [p for p in harness.documents_dir.rglob('*') if p.is_file()]
                # Native storage uses unique physical names unless the caller
                # supplies exact targets. Canonical names and accepted result
                # bindings must still be precisely the caller's named files.
                text_artifacts = [a for a in final['artifacts']
                                  if a.get('path') and Path(a['path']) in docs]
                by_name = {a['name'] + Path(a['path']).suffix: a for a in text_artifacts}
                assert len(docs) == len(text_artifacts) == len(by_name) == 2
                assert set(by_name) == set(EXPECTED)
                for name, artifact in by_name.items():
                    saved_path = Path(artifact['path'])
                    assert saved_path.read_bytes() == EXPECTED[name]
                    assert saved_path.name == name or saved_path.name.endswith('_' + name)
                    if explicit_targets:
                        assert saved_path == tmp_path / 'artifacts/documents' / name
                file_results = [r for r in final.get('late_fill',{}).get('fill_results',[])
                                if r.get('saved_text_artifacts')]
                assert len(file_results) == 2
                for result in file_results:
                    assert len(result['saved_text_artifacts']) == 1
                    saved = result['saved_text_artifacts'][0]
                    binding = saved['artifact_request']
                    name = binding['source_name'] + '.' + binding['extension']
                    assert name in EXPECTED
                    assert saved['path'] == by_name[name]['path']
                    assert result['branch_id'] == by_name[name]['branch_id']
                    assert result['phase_id'] == by_name[name]['phase_id']
                image_calls = [c for c in harness.provider_calls
                               if c['url'].endswith(('/api/generate', '/v1/images/generations'))]
                assert [c['request']['prompt'] for c in image_calls] == (PROMPTS if include_images else [])
                assert len(images) == (2 if include_images else 0)
                assert all(p.read_bytes() == tiny_png_bytes() for p in images)
                assert not [p for p in harness.audio_dir.rglob('*') if p.is_file()]
                outputs = [o for o in final['outputs'] if o.get('artifact_ref')]
                assert len(outputs) == (4 if include_images else 2) and all(o['status'] == 'fulfilled' for o in outputs)
                assert len({o['artifact_ref'] for o in outputs}) == len(outputs)
                artifacts = {a['artifact_ref']:a for a in final['artifacts'] if a.get('artifact_ref')}
                assert {Path(artifacts[o['artifact_ref']]['path']) for o in outputs} == set(images + docs)
                expected_owners = {(b['branch_id'], b['phase_id']) for b in graph['downstream_branches']}
                assert {(o['branch_id'], o['phase_id']) for o in outputs} == expected_owners
                assert all(b['depends_on'] == ['phase-1'] for b in graph['downstream_branches'])
                record['effects_and_bindings_passed'] = True
                harness.clear_response_lookup()
                recovered = harness.response_state(final['id'])
                assert recovered['ok']
                assert recovered['response_payload']['outputs'] == final['outputs']
                record['recovered'] = {'lifecycle': recovered['response_payload']['lifecycle_state'],
                                       'outputs': recovered['response_payload']['outputs']}
                assert final['lifecycle_state'] == 'completed'
                assert recovered['response_payload']['lifecycle_state'] == 'completed'
                assert final['runtime']['graph_closure_review']['status'] == 'fulfilled'
                assert recovered['response_payload']['runtime']['graph_closure_review']['status'] == 'fulfilled'
            finally:
                record['provider_calls'] = deepcopy(harness.provider_calls)
                record['saved'] = [{'path':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
                                   'bytes':p.stat().st_size}
                                  for folder in (harness.images_dir,harness.documents_dir,harness.audio_dir)
                                  for p in folder.rglob('*') if p.is_file()]
    finally:
        path = Path(os.environ['FRUTH_A1_EVIDENCE_DIR']) / (label + '.json')
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')


@pytest.mark.parametrize('extra_proposal,explicit_targets', [(False, False), (True, False)])
def test_bare_named_files_execute_and_recover(tmp_path, extra_proposal, explicit_targets):
    run_named_file_request(tmp_path, extra_proposal, explicit_targets=explicit_targets)
