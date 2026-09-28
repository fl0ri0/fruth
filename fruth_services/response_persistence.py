"""Storage outcomes, separate from semantic fulfillment and model failures."""

from __future__ import annotations

from collections.abc import Mapping
import copy
import errno
from typing import Any


def response_persistence_blocked(payload: Mapping[str, Any]) -> bool:
    receipt = payload.get('persistence')
    return isinstance(receipt, Mapping) and receipt.get('status') in {
        'not_committed', 'uncertain',
    }


class ResponseFramePersistenceError(OSError):
    """The writer retains what it knows, including a post-fsync Index failure."""

    def __init__(self, cause: Exception, receipt: Mapping[str, Any], *, frame=None):
        super().__init__(getattr(cause, 'errno', None), str(cause))
        self.receipt = copy.deepcopy(dict(receipt))
        self.receipt['error'] = {
            'code': getattr(cause, 'code', 'response_frame_persistence_failed'),
            'message': str(cause),
            'errno': getattr(cause, 'errno', None),
        }
        self.frame = frame


class ResponsePersistenceError(RuntimeError):
    """A finalizer failure carrying saved outputs without authorizing a retry."""

    def __init__(self, payload: Mapping[str, Any]):
        self.response_payload = dict(payload)
        receipt = self.response_payload.get('persistence') or {}
        storage_error = receipt.get('error') or {}
        self.status_code = 507 if storage_error.get('errno') == errno.ENOSPC else 503
        super().__init__(
            'Response storage is not confirmed. Preserve the response and inspect '
            'its Ledger before recovery; do not rerun the request automatically.'
        )


def attach_persistence_failure(payload: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Block delivery/continuation while leaving the candidate frozen frame intact."""
    result = dict(payload)
    result['persistence'] = dict(receipt)
    result['persistence']['work_lifecycle_state'] = payload.get('lifecycle_state')
    result['status'] = 'incomplete'
    result['lifecycle_state'] = 'blocked'
    result['error'] = {
        'code': 'response_persistence_failed',
        'message': (
            'Response storage is not confirmed. Saved outputs may already exist. '
            'Inspect this response and its Ledger before recovery; do not repeat '
            'the request automatically.'
        ),
        'retryable': False,
        'recovery_action': 'inspect_response_persistence',
        'response_id': payload.get('id') or payload.get('response_id'),
        'commit_status': receipt.get('status'),
        'stage': receipt.get('stage'),
    }
    return result
