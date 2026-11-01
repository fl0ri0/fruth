"""Process-local one-use permission and exact identity for pending continuation.

Persisted records can constrain this authority but cannot create it. The scoped
reader resolves canonical request truth; dispatch, claims and publication stay
with the worker, which revalidates at each existing use boundary.
"""

from __future__ import annotations

from typing import Callable
from fruth_services.response_persistence import response_persistence_blocked
import copy
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional
from fruth_server.response_lookup_runtime import response_wire_frame_identity
from fruth_server.responses_runtime import ResponseMutationConflict, require_response_mutation_base


C9_CONTROL_CONTINUATION_MAX_HANDOFFS = 1


@dataclass(eq=False)
class _PendingContinuationChain:
    """Process-local execution permission; never restored from response JSON."""

    admission: dict[str, Any]
    contracts: dict[str, dict[str, Any]]
    request: dict[str, Any]
    submitted: set[str] = field(default_factory=set)
    attempts: int = 0
    lock: Any = field(default_factory=threading.Lock, repr=False)

    def take_attempt(self) -> bool:
        with self.lock:
            if self.attempts >= C9_CONTROL_CONTINUATION_MAX_HANDOFFS:
                return False
            self.attempts += 1
            return True


@dataclass(eq=False)
class _PendingContinuation:
    chain: _PendingContinuationChain
    base: dict[str, Any]
    scope: Optional[frozenset[str]] = None
    submitted: bool = False
    entered: bool = False
    wave_active: bool = False

    def take_submission(self) -> bool:
        with self.chain.lock:
            if self.submitted or self.scope is None:
                return False
            self.submitted = True
            return True

    def take_entry(self) -> bool:
        with self.chain.lock:
            if self.entered:
                return False
            self.entered = True
            return True

@dataclass(frozen=True)
class PendingContinuationAuthority:
    branch_id: Callable[[Any], str]
    normalize_late_fill_branches: Callable[..., list[dict[str, Any]]]
    load_latest_response_state: Callable[[str], dict[str, Any]]

    @staticmethod
    def _pending_contract(record: Mapping[str, Any]) -> dict[str, Any]:
        # Unknown fields remain binding. Do not expand this operational allowlist
        # to recover a missing or changed semantic contract.
        return {key: copy.deepcopy(value) for key, value in record.items()
                if key not in {'status', 'updated_at', 'timing', 'scheduling_policy'}}

    @classmethod
    def _pending_accepted_evidence(cls, value):
        # Frame compaction removes transport bytes, timestamps and empty values.
        # Preserve every other (including unknown) identity/evidence field.
        if isinstance(value, Mapping):
            return {key: cls._pending_accepted_evidence(item) for key, item in value.items()
                    if key not in {'created_at', 'updated_at', 'started_at', 'completed_at',
                                   'failed_at', 'image_data_url'} and item not in (None, '', [], {})}
        if isinstance(value, list):
            return [cls._pending_accepted_evidence(item) for item in value]
        return value

    def _new_pending_continuation(self, payload, request_payload):
        late = payload.get('late_fill') or {}
        graph = (payload.get('runtime') or {}).get('request_phase_graph') or {}
        pending = self.normalize_late_fill_branches(late.get('pending_branches'))
        obligations = graph.get('output_obligations') or []
        contracts = {}
        for branch in pending:
            branch_id = self.branch_id(branch)
            if (not branch_id or branch_id in contracts
                    or branch.get('contract_state') != 'promoted'
                    or not any(item.get('obligation_id') == branch.get('obligation_id')
                               and item.get('branch_id') == branch_id
                               and item.get('phase_id') == branch.get('phase_id')
                               and item.get('contract_state') == 'promoted'
                               for item in obligations if isinstance(item, Mapping))):
                return None
            contracts[branch_id] = copy.deepcopy(branch)
        if not contracts:
            return None
        admission = copy.deepcopy(payload)
        admission.setdefault('response_frame', {})['request'] = copy.deepcopy(self._pending_frame_request(payload))
        chain = _PendingContinuationChain(admission, contracts, copy.deepcopy(request_payload))
        return _PendingContinuation(chain, copy.deepcopy(payload))

    @staticmethod
    def _pending_execution_binding(payload):
        late = payload.get('late_fill') or {}
        return tuple(copy.deepcopy(late.get(name) or {}) for name in (
            'successor_reopen_execution', 'terminal_closure_repair_reopen', 'partial_rebase_execution'))

    def _pending_frame_request(self, payload):
        # Live and wire carriers can represent different compaction passes of
        # the same request. Resolve through the existing passive canonical owner
        # even when a carrier is present, bound to this exact frame.
        if not callable(self.load_latest_response_state):
            raise ResponseMutationConflict('pending continuation canonical request unavailable')
        durable = self.load_latest_response_state(str(payload.get('id') or ''))
        frame = durable.get('response_frame') or {}
        if not durable.get('ok') or (frame.get('frame_id'), frame.get('frame_sequence')) != response_wire_frame_identity(payload):
            raise ResponseMutationConflict('pending continuation canonical request frame changed')
        return frame.get('request')

    def _require_pending_continuation(self, context, current, *, exact_frame=True):
        if not isinstance(context, _PendingContinuation) or not current:
            raise ResponseMutationConflict('pending continuation context unavailable')
        base, admission = context.base, context.chain.admission
        if response_persistence_blocked(current) or current.get('id') != admission.get('id'):
            raise ResponseMutationConflict('pending continuation response/storage changed')
        if exact_frame:
            # Preserve normal same-frame control handling; a durable version or
            # execution change still rejects before any new dispatch.
            expected = {**base, 'late_fill': {**(base.get('late_fill') or {}),
                        'branch_controls': (current.get('late_fill') or {}).get('branch_controls', []),
                        'cancelled_branches': (current.get('late_fill') or {}).get('cancelled_branches', [])}}
            require_response_mutation_base(expected, current)
        # Execution operational status can advance; its immutable identity cannot.
        if self._pending_execution_identity(base) != self._pending_execution_identity(current):
            raise ResponseMutationConflict('pending continuation execution changed')
        for execution in self._pending_execution_binding(current):
            if str(execution.get('status') or '').lower() in {
                    'completed', 'fulfilled', 'failed', 'cancelled', 'waived', 'superseded'}:
                raise ResponseMutationConflict('pending continuation execution is terminal')
        current_request = self._pending_frame_request(current)
        # Admission captured the canonical request while its frame was current.
        # Never resolve that old snapshot against the newer current frame. Every
        # canonical request field (including unknown fields) remains binding.
        if ((admission.get('runtime') or {}).get('request_phase_graph')
                != (current.get('runtime') or {}).get('request_phase_graph')
                or admission.get('request') != current.get('request')
                or admission.get('request_meta') != current.get('request_meta')
                or (admission.get('response_frame') or {}).get('request') != current_request):
            raise ResponseMutationConflict('pending continuation admission changed')
        if context.scope is not None:
            for branch in (current.get('late_fill') or {}).get('pending_branches', []):
                branch_id = self.branch_id(branch)
                if branch_id not in context.chain.contracts:
                    raise ResponseMutationConflict('pending continuation scope widened')
                if branch_id not in context.chain.submitted and self._pending_contract(branch) != self._pending_contract(context.chain.contracts[branch_id]):
                    raise ResponseMutationConflict('pending continuation local contract changed')
        prior = (base.get('late_fill') or {}).get('fill_results') or []
        accepted = (current.get('late_fill') or {}).get('fill_results') or []
        if any(self._pending_accepted_evidence(result) not in [self._pending_accepted_evidence(r) for r in accepted]
               for result in prior):
            raise ResponseMutationConflict('pending continuation accepted evidence changed')

    @staticmethod
    def _pending_execution_identity(payload):
        late = payload.get('late_fill') or {}
        return tuple(tuple(copy.deepcopy((late.get(name) or {}).get(key)) for key in keys)
            for name, keys in (
                ('successor_reopen_execution', ('successor_execution_key', 'parent_response_id',
                    'parent_frame_id', 'parent_frame_sequence', 'successor_graph_digest', 'scheduled_branch_ids')),
                ('terminal_closure_repair_reopen', ('execution_key',)),
                ('partial_rebase_execution', ('execution_key',))))

