"""Commit finalized response truth and retain secondary durability outcomes.

The operation preserves preflight, Artifact Registry, canonical Ledger/Index and
Readiness ordering. Its exact storage operations are supplied by composition;
HTTP, request parsing, model execution and worker scheduling are unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from fruth_services.graph_rebase_readiness_registry import GraphRebaseReadinessRegistryError
from fruth_services.response_frames import ResponseFrameParentCASMismatch
from fruth_services.response_persistence import (
    ResponseFramePersistenceError, ResponsePersistenceError, attach_persistence_failure,
)
from fruth_services.response_lifecycle import _attach_response_status_semantics


@dataclass(frozen=True)
class ResponseFrameCommit:
    frames_dir: Path
    artifact_registry_ledger: Path
    persist_artifact_registry: Callable[..., Any]
    enrich_frame_for_append: Callable[..., dict[str, Any]]
    persist_frame: Callable[..., Any]
    append_frame_with_parent_cas: Callable[..., dict[str, Any]]
    register_readiness_observation: Callable[[Mapping[str, Any]], dict[str, Any]]
    publish_persistence_failure: Callable[[dict[str, Any]], None]

    def commit(self, framed_payload, *, expected_parent_frame_id=None, expected_parent_frame_sequence=None, _mark_step, _publish_finalize_timing):
        frame_persisted = False
        persistence_receipt = {}
        writer_entered = False
        registry_outcome = {'status': 'not_attempted'}
        step_started_at = time.perf_counter()
        # Migration guidance precedes Artifact Registry or Response Ledger writes.
        # This read-only preflight never initializes/migrates storage.
        from fruth_services.response_frames import check_response_frame_index_write
        try:
            check_response_frame_index_write(frames_dir=self.frames_dir)
        except Exception as exc:  # noqa: BLE001
            receipt = {
                'kind': 'fruth.response_persistence', 'version': 1,
                'status': 'not_committed', 'stage': 'prepare', 'index_status': 'not_attempted',
                'automatic_retry': False,
                'artifact_registry': {'status': 'not_attempted'},
                'error': {'code': getattr(exc, 'code', 'response_frame_persistence_failed'),
                          'message': str(exc), 'errno': getattr(exc, 'errno', None)},
            }
            failed_payload = attach_persistence_failure(framed_payload, receipt)
            _publish_finalize_timing(failed_payload)
            failed_payload = _attach_response_status_semantics(failed_payload)
            self.publish_persistence_failure(failed_payload)
            raise ResponsePersistenceError(failed_payload) from exc
        try:
            self.persist_artifact_registry(
                framed_payload,
                ledger_path=self.artifact_registry_ledger,
            )
            registry_outcome = {'status': 'published'}
        except Exception as exc:  # noqa: BLE001
            registry_outcome = {'status': 'failed', 'error': str(exc)}
            logging.warning("Could not append output artifact registry records: %s", exc)
        _mark_step('persist_output_artifact_registry_records', step_started_at)
        _publish_finalize_timing(framed_payload)
        step_started_at = time.perf_counter()
        try:
            if str(expected_parent_frame_id or '').strip():
                writer_entered = True
                append_result = self.append_frame_with_parent_cas(
                    framed_payload['response_frame'],
                    expected_parent_frame_id=str(expected_parent_frame_id).strip(),
                    expected_parent_frame_sequence=expected_parent_frame_sequence,
                    frames_dir=self.frames_dir,
                    receipt=persistence_receipt,
                )
                framed_payload['response_frame'] = append_result['response_frame']
            else:
                framed_payload['response_frame'] = self.enrich_frame_for_append(
                    framed_payload['response_frame'],
                    frames_dir=self.frames_dir,
                )
                writer_entered = True
                self.persist_frame(
                    framed_payload['response_frame'], frames_dir=self.frames_dir,
                    receipt=persistence_receipt,
                )
            frame_persisted = True
        except ResponseFrameParentCASMismatch:
            raise
        except Exception as exc:  # noqa: BLE001
            logging.warning("Could not append response frame: %s", exc)
            if isinstance(exc, ResponseFramePersistenceError):
                persistence_receipt = dict(exc.receipt)
                if exc.frame is not None:
                    framed_payload['response_frame'] = exc.frame
            else:
                # Includes preparation failures before the native writer and
                # unexpected failures without a trustworthy commit receipt.
                persistence_receipt = {
                    'kind': 'fruth.response_persistence', 'version': 1,
                    'status': 'uncertain' if writer_entered else 'not_committed',
                    'stage': 'finalizer' if writer_entered else 'prepare',
                    'automatic_retry': False,
                    'error': {'code': 'response_frame_persistence_failed',
                              'message': str(exc), 'errno': getattr(exc, 'errno', None)},
                }
            persistence_receipt['artifact_registry'] = registry_outcome
            if persistence_receipt.get('status') != 'committed':
                failed_payload = attach_persistence_failure(framed_payload, persistence_receipt)
                _mark_step('persist_response_frame', step_started_at)
                _publish_finalize_timing(failed_payload)
                failed_payload = _attach_response_status_semantics(failed_payload)
                self.publish_persistence_failure(failed_payload)
                raise ResponsePersistenceError(failed_payload) from exc
            # The canonical row is already fsynced. Index publication is a
            # separate repair, never permission to append/execute the work twice.
            frame_persisted = True
        persistence_receipt['artifact_registry'] = registry_outcome
        framed_payload['persistence'] = persistence_receipt
        _mark_step('persist_response_frame', step_started_at)
        if frame_persisted:
            step_started_at = time.perf_counter()
            try:
                registry_diagnostic = (
                    self.register_readiness_observation(
                        framed_payload
                    )
                )
            except GraphRebaseReadinessRegistryError as exc:
                registry_diagnostic = {
                    'kind': 'fruth.graph_rebase_readiness_registry_append',
                    'status': 'append_failed',
                    'runtime_effect': 'none',
                    'error': exc.as_dict(),
                }
            except Exception as exc:  # noqa: BLE001
                registry_diagnostic = {
                    'kind': 'fruth.graph_rebase_readiness_registry_append',
                    'status': 'append_failed',
                    'runtime_effect': 'none',
                    'error': {
                        'code': 'readiness_registry_unexpected_failure',
                        'message': str(exc),
                    },
                }
            registry_status = str(registry_diagnostic.get('status') or '')
            if registry_status in {
                'append_failed',
                'hydration_binding_mismatch',
                'hydration_failed',
                'selection_failed',
                'verification_failed',
            }:
                logging.warning(
                    'Graph-rebase readiness observation was not retained: %s',
                    registry_diagnostic,
                )
            framed_runtime = (
                dict(framed_payload.get('runtime') or {})
                if isinstance(framed_payload.get('runtime'), Mapping)
                else {}
            )
            developer_diagnostics = (
                dict(framed_runtime.get('developer_diagnostics') or {})
                if isinstance(
                    framed_runtime.get('developer_diagnostics'),
                    Mapping,
                )
                else {}
            )
            developer_diagnostics['graph_rebase_readiness_registry'] = (
                registry_diagnostic
            )
            framed_runtime['developer_diagnostics'] = developer_diagnostics
            framed_payload['runtime'] = framed_runtime
            _mark_step(
                'persist_graph_rebase_readiness_observation',
                step_started_at,
                status=registry_status,
            )
        return framed_payload
