"""Explicit old-format fixtures; normal tests exercise the SQLite runtime."""
import sys

import pytest


def pytest_configure(config):
    config.addinivalue_line('markers','legacy_response_index: explicit simulation of pre-migration JSON history/owners')


@pytest.fixture(autouse=True)
def legacy_response_index_fixture(request,monkeypatch):
    if request.node.get_closest_marker('legacy_response_index') is None:
        return
    from fruth_services import response_frames as frames, events, state_flow
    loader=frames.load_response_frame_index
    verifier=frames.verify_response_frame_epoch
    def legacy_load(**kwargs):
        kwargs['allow_legacy_index']=True
        return loader(**kwargs)
    def legacy_verify(**kwargs):
        kwargs['allow_legacy_index']=True
        return verifier(**kwargs)
    def legacy_write(value,**kwargs):
        kwargs.pop('prior_ledger_state',None)
        kwargs.pop('source_frame_sha256',None)
        return frames._write_legacy_response_frame_index(value,**kwargs)
    legacy_write=state_flow.observe_state('response_index.write','ledger_representation','response_index',
                                          labels=('NEW_REPRESENTATION',))(legacy_write)
    legacy_write=events.timed_operation('write_response_frame_index',role='derived_recovery_index')(legacy_write)
    monkeypatch.setattr(frames,'check_response_frame_index_write',lambda **kwargs:None)
    monkeypatch.setattr(frames,'_initialize_response_frame_index_locked',lambda *args:None)
    monkeypatch.setattr(frames,'_write_response_frame_index',legacy_write)
    # Patch aliases captured by test/library imports as well as owner globals.
    for module in (request.module,frames,sys.modules.get('fruth_services.graph_rebase_readiness_registry')):
        if module:
            for name,value in list(vars(module).items()):
                if value is loader: monkeypatch.setattr(module,name,legacy_load)
                elif value is verifier: monkeypatch.setattr(module,name,legacy_verify)
