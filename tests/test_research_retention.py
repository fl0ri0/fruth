"""Synthetic exact-byte retention and deterministic resolution fault tests."""
import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest

HERE = Path(__file__).resolve().parents[1] / 'fruth_research/gold-core'
spec = importlib.util.spec_from_file_location('gold_fixture', HERE / 'test_validate.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
validator = fixture.validator
evidence = validator.evidence


@pytest.fixture
def sample():
    case = fixture.ValidatorTests()
    case.setUp()
    case.root = case.root.resolve()
    case.corpus = case.corpus.resolve()
    case.evidence = case.evidence.resolve()
    case.write()
    yield case
    case.doCleanups()


def retain(sample):
    store = sample.root / 'retained'
    manifest = evidence.retain(sample.corpus, sample.root, store)
    return store, manifest


def test_deterministic_inventory_retention_and_live_precedence(sample):
    first = evidence.enumerate_dependencies(sample.corpus)
    assert first == evidence.enumerate_dependencies(sample.corpus)
    store, manifest = retain(sample)
    entry, = manifest['evidence']
    assert entry['original_source_file_sha256'] == entry['original']['sha256']
    assert (store / entry['retained_path']).read_bytes() == sample.evidence.read_bytes()
    assert manifest['dependency_count'] == 1
    assert validator.validate(sample.corpus, [], retained=store)['case_count'] == 1
    sample.evidence.write_text('{"status":"wrong"}')
    with pytest.raises(validator.Invalid, match='digest mismatch'):
        validator.validate(sample.corpus, [sample.root], retained=store)
    sample.evidence.unlink()
    assert validator.validate(sample.corpus, [sample.root], retained=store)['case_count'] == 1
    (store / entry['retained_path']).write_text('corrupted retained')
    with pytest.raises(validator.Invalid, match='digest mismatch'):
        validator.validate(sample.corpus, [sample.root], retained=store)


def test_range_preserves_original_offsets_and_exact_json_bytes(sample):
    raw = b'prefix ignored\n' + sample.evidence.read_bytes() + b'trailer ignored\n'
    selected = sample.evidence.read_bytes()
    sample.evidence.write_bytes(raw)
    ref = sample.case['source']['evidence_refs'][0]
    ref.update(byte_offset=len(b'prefix ignored\n'), byte_length=len(selected))
    sample.write()
    store, manifest = retain(sample)
    entry, = manifest['evidence']
    assert entry['original']['byte_offset'] == len(b'prefix ignored\n')
    assert entry['original']['byte_length'] == len(selected)
    assert entry['original_source_file_sha256'] == validator.digest(sample.evidence)
    assert (store / entry['retained_path']).read_bytes() == selected
    sample.evidence.unlink()
    assert validator.validate(sample.corpus, [sample.root], retained=store)['case_count'] == 1


def test_explicit_archive_last_and_corrupt_store_never_falls_through(sample):
    store, manifest = retain(sample)
    archive = sample.root / 'archive'
    (archive / 'state').mkdir(parents=True)
    shutil.copy2(sample.evidence, archive / 'state/evidence.json')
    sample.evidence.unlink()
    assert validator.validate(sample.corpus, [sample.root], retained=sample.root / 'absent', archives=[archive])['case_count'] == 1
    (store / manifest['evidence'][0]['retained_path']).unlink()
    with pytest.raises(validator.Invalid, match='missing retained'):
        validator.validate(sample.corpus, [sample.root], retained=store, archives=[archive])
    (store / 'manifest.json').write_text('{}')
    with pytest.raises(validator.Invalid, match='not complete'):
        validator.validate(sample.corpus, [sample.root], retained=store, archives=[archive])


def test_space_and_wrong_source_abort_before_copy(sample, monkeypatch):
    destination = sample.root / 'retain'
    with monkeypatch.context() as m:
        m.setattr(evidence.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0))
        with pytest.raises(ValueError, match='insufficient disk'):
            evidence.retain(sample.corpus, sample.root, destination)
    assert not destination.exists()
    sample.evidence.write_text('wrong')
    with pytest.raises(ValueError, match='digest mismatch'):
        evidence.retain(sample.corpus, sample.root, destination)
    assert not destination.exists()


def test_moving_source_and_copy_corruption_do_not_publish(sample, monkeypatch):
    original = evidence.selected_digest
    def corrupt_after_copy(path, ref):
        if '.partial-' in str(path):
            path.write_bytes(b'bad copy')
        return original(path, ref)
    with monkeypatch.context() as m:
        m.setattr(evidence, 'selected_digest', corrupt_after_copy)
        with pytest.raises(ValueError, match='verification failed'):
            retain(sample)
    assert not (sample.root / 'retained').exists()
    assert sample.evidence.read_bytes() == b'{"status":"passed"}\n'
    def move_after_copy(path, ref):
        result = original(path, ref)
        if '.partial-' in str(path):
            sample.evidence.write_bytes(sample.evidence.read_bytes() + b' ')
        return result
    monkeypatch.setattr(evidence, 'selected_digest', move_after_copy)
    with pytest.raises(ValueError, match='source moved'):
        retain(sample)
    assert not (sample.root / 'retained').exists()


def test_collision_and_symlink_destination(sample):
    store, _ = retain(sample)
    with pytest.raises(ValueError, match='exists'):
        evidence.retain(sample.corpus, sample.root, store)
    linked = sample.root / 'linked'
    linked.symlink_to(store, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        evidence.retain(sample.corpus, sample.root, linked / 'child')
