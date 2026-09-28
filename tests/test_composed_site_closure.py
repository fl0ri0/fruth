"""Saved-site CSS coverage and exact retirement of obsolete composition repairs."""
import copy

import pytest

from fruth_server.responses_runtime import late_fill_has_actionable_repair_work
from tests.test_afm_preparation_handoffs import owner_fixture


@pytest.fixture
def site(tmp_path):
    owner = owner_fixture().late_fill_owner
    html, css = tmp_path / 'index.html', tmp_path / 'styles.css'
    images = [tmp_path / 'hero.png', tmp_path / 'listening.png']
    for image in images:
        image.write_bytes(b'fixture')
    html.write_text('<html><head><link rel="stylesheet" href="styles.css"></head><body>'
                    '<section class="hero"><img src="hero.png"></section>'
                    '<section class="listening"><img src="listening.png"></section></body></html>')
    css.write_text('img {max-width:100%;height:auto;}')
    payload = {'artifacts': [
        {'type': 'text', 'path': str(html), 'branch_id': 'html'},
        {'type': 'text', 'path': str(css), 'branch_id': 'css'},
        *[{'type': 'image', 'path': str(p), 'branch_id': f'image-{i}'} for i, p in enumerate(images)],
    ], 'late_fill': {'fill_results': [
        {'capability': 'image_generation', 'branch_id': f'image-{i}', 'saved_image_path': str(p)}
        for i, p in enumerate(images)
    ]}}
    return owner, payload, html, css, images


def gaps(site):
    owner, payload, *_ = site
    checks = owner._terminal_composed_site_image_composition_open_checks(payload)
    return checks[0]['unstyled_image_paths'] if checks else []


@pytest.mark.parametrize('style,missing', [
    ('.listening img {max-width:100%;height:auto}', [0]),  # Actual latest AFM output.
    ('.hero img {width:100%}', [1]),
    ('.hero, .listening {max-width:100%}', [0, 1]),
    ('img {object-fit:cover;height:auto}', [0, 1]),
    ('.absent img {width:100%}', [0, 1]),
    (':not(.hero) img {width:100%}', [0, 1]),
    ('.hero + img {width:100%}', [0, 1]),
    ('/* img {width:100%} */', [0, 1]),
    ('img {width:auto;max-width:none}', [0, 1]),
    ('img {max-width:100%;height:auto}', []),
    ('.hero > img, .listening img {width:100%}', []),
    ('body img {max-width:100%}', []),
])
def test_layout_covers_each_actual_image(site, style, missing):
    _, _, _, css, images = site
    css.write_text(style)
    assert gaps(site) == [str(images[i]) for i in missing]


def test_inline_style_does_not_size_sibling_image(site):
    _, _, html, css, images = site
    css.write_text('body {display:flex}')
    html.write_text(html.read_text().replace('src="hero.png"', 'src="hero.png" style="max-width:100%"'))
    assert gaps(site) == [str(images[1])]


def test_every_occurrence_requires_its_own_layout_evidence(site):
    _, _, html, css, images = site
    css.write_text('.hero img, .listening img {width:100%}')
    html.write_text(html.read_text().replace('</body>', '<img src="hero.png"></body>'))
    assert gaps(site) == [str(images[0])]


def test_page_styles_do_not_leak_across_pages_or_unlinked_files(site):
    _, payload, html, _, images = site
    html.write_text(html.read_text().replace('<link rel="stylesheet" href="styles.css">', ''))
    assert gaps(site) == [str(p) for p in images]
    other = html.with_name('other.html')
    other.write_text('<html><style>img {width:100%}</style><img src="hero.png"></html>')
    payload['artifacts'].append({'type': 'text', 'path': str(other), 'branch_id': 'other'})
    assert gaps(site) == [str(p) for p in images]


@pytest.mark.parametrize('kind', ['embedded', 'inline', 'picture', 'background'])
def test_layout_accepts_existing_embedded_inline_picture_and_background_bindings(site, kind):
    _, _, html, css, _ = site
    if kind == 'embedded':
        css.write_text('')
        html.write_text(html.read_text().replace('</head>', '<style>img {width:100%}</style></head>'))
    elif kind == 'inline':
        css.write_text('')
        html.write_text(html.read_text().replace('<img ', '<img style="max-width:100%" '))
    elif kind == 'picture':
        html.write_text(html.read_text().replace('<img src="hero.png">',
            '<picture><source srcset="hero.png"><img src="fallback.png"></picture>'))
    else:
        html.write_text(html.read_text().replace('<img src="hero.png">', ''))
        css.write_text('img {width:100%} .hero {background:url(hero.png) center/cover; height:20rem}')
    assert gaps(site) == []



def test_script_layout_evidence_cannot_hide_unstyled_concrete_occurrence(site):
    _, payload, html, css, images = site
    script = html.with_name('app.js')
    script.write_text('const image = "hero.png"; card.innerHTML = `<img class="room-image" src="${image}">`;')
    payload['artifacts'].append({'type': 'text', 'path': str(script), 'branch_id': 'app'})
    html.write_text(html.read_text().replace('</body>', '<script src="app.js"></script></body>'))
    css.write_text('.room-image, .listening img {width:100%}')
    assert gaps(site) == [str(images[0])]


def failed_repair(html):
    return {
        'branch_id': 'branch-repair-html', 'phase_id': 'repair-phase', 'status': 'failed',
        'capability': 'chat', 'output_type': 'text', 'repair_contract_id': 'contract-html',
        'content_payload_source': 'closure_composed_site_image_composition',
        'text_artifact_source': 'closure_composed_site_image_composition',
        'text_artifact_target_path': str(html), 'text_artifact_extension': 'html',
        'error': {'code': 'TEXT_ARTIFACT_REPAIR_OUTPUT_MISSING'},
        'recovery_state': {'status': 'candidate', 'branch_id': 'branch-repair-html'},
    }


def repair_state(branch, *, other=False):
    contract = {key: value for key, value in branch.items()
                if key in {'branch_id', 'phase_id', 'text_artifact_target_path',
                           'text_artifact_extension', 'text_artifact_source'}}
    contract.update(contract_id=branch['repair_contract_id'], auto_execute=True,
                    repair_work_available=True, repair_action='retry_same_branch')
    candidate = {'branch_id': branch['branch_id'], 'status': 'candidate'}
    contracts = [contract]
    candidates = [candidate]
    if other:
        contracts.append({**contract, 'contract_id': 'other', 'branch_id': 'other'})
        candidates.append({**candidate, 'branch_id': 'other'})
    return {
        'status': 'partial_failed', 'partial_failure': True,
        'final_materialization_contract_status': 'fulfilled',
        'failed_branches': [branch], 'completed_branches': [],
        'recovery_candidates': candidates, 'repair_rebuild_contracts': contracts,
        'repair_action': 'retry_same_branch',
        'repair_loop': {'status': 'promoted', 'promoted_contracts': contracts,
                        'auto_execute': True, 'repair_work_available': True},
    }


def test_partial_css_repair_does_not_supersede_failed_html_repair(site):
    owner, payload, html, css, _ = site
    css.write_text('.listening img {max-width:100%;height:auto}')
    state = repair_state(failed_repair(html))
    assert owner._supersede_resolved_composition_repairs(payload, state) == state


@pytest.mark.parametrize('other', [False, True])
def test_supersession_retires_only_exact_recovery_and_contract(site, other):
    owner, payload, html, _, _ = site
    branch = failed_repair(html)
    state = repair_state(branch, other=other)
    original = copy.deepcopy(state)
    result = owner._supersede_resolved_composition_repairs(payload, state)
    assert state == original
    assert result['failed_branches'] == []
    done = result['completed_branches'][0]
    assert done['status'] == 'superseded'  # No invented successful repair execution.
    assert done['superseded_failure']['error'] == branch['error']
    assert done['supersession_evidence']['target_sha256']
    assert [b['branch_id'] for b in result['recovery_candidates']] == (['other'] if other else [])
    loop = result['repair_loop']
    assert [c['branch_id'] for c in loop['promoted_contracts']] == (['other'] if other else [])
    assert loop['resolved_contracts'][0]['supersession_evidence'] == done['supersession_evidence']
    assert late_fill_has_actionable_repair_work(result) is other
    assert owner._supersede_resolved_composition_repairs(payload, result) == result


@pytest.mark.parametrize('mismatch', ['branch_id', 'phase_id', 'text_artifact_target_path'])
def test_supersession_does_not_settle_conflicting_contract_identity(site, mismatch):
    owner, payload, html, _, _ = site
    state = repair_state(failed_repair(html))
    state['repair_loop']['promoted_contracts'][0][mismatch] = 'different'
    result = owner._supersede_resolved_composition_repairs(payload, state)
    assert result['repair_loop']['status'] == 'promoted'
    assert late_fill_has_actionable_repair_work(result)


def test_persisted_superseded_label_alone_cannot_settle_repair(site):
    owner, _, html, _, _ = site
    branch = failed_repair(html)
    state = repair_state(branch)
    state['failed_branches'] = []
    state['completed_branches'] = [{**branch, 'status': 'superseded'}]
    assert owner._reconcile_terminal_satisfied_repair_loop(state) == state


@pytest.mark.parametrize('mismatch', ['phase_id', 'text_artifact_target_path'])
def test_supersession_preserves_conflicting_recovery_identity(site, mismatch):
    owner, payload, html, _, _ = site
    state = repair_state(failed_repair(html))
    state['recovery_candidates'][0][mismatch] = 'different'
    state['recovery_state'] = dict(state['recovery_candidates'][0])
    result = owner._supersede_resolved_composition_repairs(payload, state)
    assert result['recovery_candidates'] == state['recovery_candidates']
    assert result['recovery_state'] == state['recovery_state']
