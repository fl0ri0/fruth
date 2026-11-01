"""Ownership half of an already-mocked native launch boundary in contract tests.

Actual capture/verification is tested in test_process_launch_ownership and the
native launch fixture. Never use these synthetic records as native evidence.
"""
from types import SimpleNamespace


def mock_launch_ownership(monkeypatch, *managers):
    for manager in managers:
        monkeypatch.setattr(manager, 'capture_spawned_process',
                            lambda child, command: SimpleNamespace(child=child, pid=child.pid, command=command))
        monkeypatch.setattr(manager, 'verify_spawned_process',
                            lambda spawned, **kwargs: {
                                'process_identity': 'Sat Oct 31 09:30:00 2026 /fixture/server',
                                'server_command': ['/fixture/server'],
                            })
        monkeypatch.setattr(manager, 'terminate_spawned_process', lambda spawned: spawned.child.terminate())
