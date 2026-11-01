"""Test evidence uses actual filesystem capacity, with optional explicit quotas."""
from types import SimpleNamespace

import pytest

from scripts import run_tests as runner


def capacity(monkeypatch, tmp_path, *, used, free, additional=0, limit=None):
    monkeypatch.setattr(runner, 'allocated', lambda root: used)
    monkeypatch.setattr(runner.shutil, 'disk_usage',
                        lambda root: SimpleNamespace(total=1024**4, free=free))
    return runner.storage_snapshot(tmp_path, additional_bytes=additional, stop_bytes=limit)


def test_large_retained_evidence_does_not_create_an_implicit_quota(monkeypatch, tmp_path):
    value = capacity(monkeypatch, tmp_path, used=50 * 1024**3, free=100 * 1024**3)
    assert value['stop_reason'] is None
    assert value['allocated_bytes'] == 50 * 1024**3
    assert value['explicit_stop_bytes'] is None


@pytest.mark.parametrize('additional', [0, 2 * 1024**3])
def test_free_space_guard_accounts_for_staging_and_receipt_headroom(monkeypatch, tmp_path, additional):
    value = capacity(monkeypatch, tmp_path, used=0,
                     free=runner.MIN_FREE_BYTES + additional - 1, additional=additional)
    assert value['stop_reason'] == 'insufficient_free_disk'
    value = capacity(monkeypatch, tmp_path, used=0,
                     free=runner.MIN_FREE_BYTES + additional, additional=additional)
    assert value['stop_reason'] is None


def test_explicit_task_quota_is_still_enforced(monkeypatch, tmp_path):
    value = capacity(monkeypatch, tmp_path, used=100, free=100 * 1024**3,
                     additional=20, limit=120)
    assert value['stop_reason'] == 'explicit_task_storage_limit'


@pytest.mark.parametrize('limit', [0, -1, True, '100'])
def test_invalid_explicit_quota_fails_closed(tmp_path, limit):
    with pytest.raises(ValueError, match='positive integer'):
        runner.storage_snapshot(tmp_path, stop_bytes=limit)
