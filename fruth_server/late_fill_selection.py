"""Late Fill selection within an already dependency-ready wave.

Preserves ready-before-wait ordering, oldest due groups and resource priorities.
It selects records only: claims, dispatch, retries and publication are owned by
the continuation worker. Candidate routing consumes the same scheduling context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import math
import time
from typing import Any, Mapping, Optional
from fruth_core.text_artifacts import TEXT_ARTIFACT_EXTENSIONS


def _late_fill_instance_is_mlx_vlm(instance: Mapping[str, Any]) -> bool:
    runtime_status = instance.get('runtime_status') if isinstance(instance.get('runtime_status'), Mapping) else {}
    backend = str(instance.get('backend') or runtime_status.get('backend') or '').strip().lower()
    backend_package = str(instance.get('backend_package') or runtime_status.get('backend_package') or '').strip().lower()
    backend_contract = str(instance.get('backend_contract') or runtime_status.get('backend_contract') or '').strip().lower()
    mlx_server = str(instance.get('mlx_server') or runtime_status.get('mlx_server') or '').strip().lower()
    server_kind = str(instance.get('server_kind') or runtime_status.get('server_kind') or '').strip().lower()
    return (
        backend_package == 'mlx_vlm'
        or backend_contract.startswith('mlx_vlm')
        or mlx_server == 'mlx_vlm'
        or server_kind == 'mlx_vlm'
        or (backend == 'mlx' and 'vlm' in backend_package)
    )

@dataclass(frozen=True)
class LateFillSelection:
    branch_capability: Callable[[Mapping[str, Any]], Optional[str]]
    image_generation_capability: Callable[[], str]
    clock: Callable[[], float]

    @staticmethod
    def _artifact_gap_is_required_text_materialization(artifact_gap: Optional[Mapping[str, Any]]) -> bool:
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        artifact_request = gap.get('artifact_request') if isinstance(gap.get('artifact_request'), Mapping) else {}
        text_artifact_requests = (
            gap.get('text_artifact_requests')
            if isinstance(gap.get('text_artifact_requests'), list)
            else []
        )
        extension = str(
            gap.get('text_artifact_extension')
            or artifact_request.get('extension')
            or ''
        ).strip().lower().lstrip('.')
        if not extension:
            for item in text_artifact_requests:
                if isinstance(item, Mapping):
                    extension = str(item.get('extension') or '').strip().lower().lstrip('.')
                    if extension:
                        break
        stage_direction = str(gap.get('stage_direction') or '').strip()
        return (
            stage_direction == 'materialize_requested_text_artifact'
            and (
                gap.get('requires_artifact') is True
                or bool(artifact_request)
                or extension in TEXT_ARTIFACT_EXTENSIONS
            )
            and extension in TEXT_ARTIFACT_EXTENSIONS
        )

    @staticmethod
    def _artifact_gap_is_required_image_materialization(artifact_gap: Optional[Mapping[str, Any]]) -> bool:
        gap = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        capability = str(
            gap.get('expected_capability')
            or gap.get('capability')
            or ''
        ).strip().lower()
        output_type = str(gap.get('output_type') or gap.get('artifact_type') or '').strip().lower()
        return (
            capability == 'image_generation'
            or output_type == 'image'
        ) and (
            gap.get('requires_artifact') is True
            or output_type == 'image'
            or bool(str(gap.get('artifact_prompt') or '').strip())
        )

    @staticmethod
    def _prefer_non_mlx_vlm_for_required_text_candidates(
        candidates: list[dict[str, Any]],
        artifact_gap: Optional[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if not LateFillSelection._artifact_gap_is_required_text_materialization(artifact_gap):
            return candidates
        non_mlx_candidates = [
            entry
            for entry in candidates
            if isinstance(entry, dict) and not _late_fill_instance_is_mlx_vlm(entry)
        ]
        return non_mlx_candidates or candidates

    @staticmethod
    def _runtime_scheduling_flag_enabled(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on', 'allow', 'allowed'}
        return False

    @staticmethod
    def _instance_identity_text(instance: Optional[Mapping[str, Any]]) -> str:
        payload = instance if isinstance(instance, Mapping) else {}
        runtime_status = payload.get('runtime_status') if isinstance(payload.get('runtime_status'), Mapping) else {}
        values: list[str] = []
        for source in (payload, runtime_status):
            for key in (
                'instance_id',
                'model',
                'model_name',
                'requested_model',
                'selected_model',
                'backend',
                'backend_package',
                'backend_contract',
                'server_kind',
                'capability',
            ):
                token = str(source.get(key) or '').strip()
                if token:
                    values.append(token)
        return ' '.join(values).lower()

    @classmethod
    def _late_fill_instance_is_large_chat_candidate(cls, instance: Optional[Mapping[str, Any]]) -> bool:
        payload = instance if isinstance(instance, Mapping) else {}
        capability = str(payload.get('capability') or '').strip().lower()
        text = cls._instance_identity_text(payload)
        return capability == 'chat' and ('gemma4:26b' in text or '26b' in text)

    @classmethod
    def _late_fill_instance_is_lightweight_chat_candidate(cls, instance: Optional[Mapping[str, Any]]) -> bool:
        payload = instance if isinstance(instance, Mapping) else {}
        capability = str(payload.get('capability') or '').strip().lower()
        if capability and capability != 'chat':
            return False
        if cls._late_fill_instance_is_large_chat_candidate(payload):
            return False
        text = cls._instance_identity_text(payload)
        return any(
            marker in text
            for marker in (
                'gemma4:e4b',
                'e4b',
                'granite',
                '8b',
                'lightweight',
                'small',
                'mini',
            )
        )

    @classmethod
    def _runtime_scheduling_context(
        cls,
        artifact_gap: Optional[Mapping[str, Any]],
        source_route_payload: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        gap_payload = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        route_payload = source_route_payload if isinstance(source_route_payload, Mapping) else {}
        for payload in (route_payload, gap_payload):
            nested_context = payload.get('runtime_scheduling_context') if isinstance(payload.get('runtime_scheduling_context'), Mapping) else {}
            context.update(dict(nested_context))
        for key in (
            'active_image_generation',
            'active_capabilities',
            'selected_chat_model_class',
            'selected_chat_model',
            'selected_chat_instance_id',
            'allow_gpu_heavy_concurrency',
            'repair_scope',
            'resource_class',
            'dependency_policy',
        ):
            for payload in (route_payload, gap_payload):
                value = payload.get(key)
                if value not in (None, '', [], {}):
                    context[key] = value
        route_instance = route_payload.get('instance') if isinstance(route_payload.get('instance'), Mapping) else {}
        if route_instance:
            context.setdefault('selected_chat_instance_id', route_instance.get('instance_id'))
            context.setdefault('selected_chat_model', route_instance.get('model') or route_instance.get('model_name'))
            if cls._late_fill_instance_is_lightweight_chat_candidate(route_instance):
                context.setdefault('selected_chat_model_class', 'lightweight')
            elif cls._late_fill_instance_is_large_chat_candidate(route_instance):
                context.setdefault('selected_chat_model_class', 'large')
        return {key: value for key, value in context.items() if value not in (None, '', [], {})}

    @classmethod
    def _runtime_context_has_active_image_generation(
        cls,
        artifact_gap: Optional[Mapping[str, Any]],
        source_route_payload: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        context = cls._runtime_scheduling_context(artifact_gap, source_route_payload)
        if cls._runtime_scheduling_flag_enabled(context.get('active_image_generation')):
            return True
        active_capabilities = context.get('active_capabilities')
        if isinstance(active_capabilities, list):
            return any(str(item or '').strip().lower() == 'image_generation' for item in active_capabilities)
        return str(active_capabilities or '').strip().lower() == 'image_generation'

    @classmethod
    def _runtime_context_prefers_lightweight_chat(
        cls,
        artifact_gap: Optional[Mapping[str, Any]],
        source_route_payload: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        context = cls._runtime_scheduling_context(artifact_gap, source_route_payload)
        model_class = str(context.get('selected_chat_model_class') or '').strip().lower()
        if model_class in {'lightweight', 'small', 'mini'}:
            return True
        selected_model = str(context.get('selected_chat_model') or '').strip().lower()
        if selected_model and any(marker in selected_model for marker in ('gemma4:e4b', 'e4b', 'granite', '8b')):
            return True
        return False

    @classmethod
    def _prefer_lightweight_chat_for_required_text_candidates(
        cls,
        candidates: list[dict[str, Any]],
        artifact_gap: Optional[Mapping[str, Any]],
        source_route_payload: Optional[Mapping[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        if not cls._artifact_gap_is_required_text_materialization(artifact_gap):
            return candidates
        active_image_generation = cls._runtime_context_has_active_image_generation(
            artifact_gap,
            source_route_payload,
        )
        lightweight_target = cls._runtime_context_prefers_lightweight_chat(
            artifact_gap,
            source_route_payload,
        )
        if not active_image_generation and not lightweight_target:
            return candidates
        lightweight_candidates = [
            entry
            for entry in candidates
            if isinstance(entry, dict) and cls._late_fill_instance_is_lightweight_chat_candidate(entry)
        ]
        if lightweight_candidates:
            return lightweight_candidates
        if active_image_generation:
            non_large_candidates = [
                entry
                for entry in candidates
                if isinstance(entry, dict) and not cls._late_fill_instance_is_large_chat_candidate(entry)
            ]
            if non_large_candidates:
                return non_large_candidates
        return candidates

    def _branch_is_image_generation(self, branch: Mapping[str, Any]) -> bool:
        return (
            self.branch_capability(branch) == self.image_generation_capability()
            or str(branch.get('output_type') or branch.get('artifact_type') or '').strip().lower() == 'image'
        )

    def _branch_is_required_image_materialization(self, branch: Mapping[str, Any]) -> bool:
        if not isinstance(branch, Mapping) or not self._branch_is_image_generation(branch):
            return False
        output_contract = (
            branch.get('output_contract')
            if isinstance(branch.get('output_contract'), Mapping)
            else {}
        )
        if branch.get('required') is False or output_contract.get('required') is False:
            return False
        if branch.get('optional') is True or output_contract.get('optional') is True:
            return False
        return self._artifact_gap_is_required_image_materialization(branch) or self._branch_is_image_generation(branch)

    def _branch_is_required_text_artifact(self, branch: Mapping[str, Any]) -> bool:
        return self._artifact_gap_is_required_text_materialization(branch)

    def _branch_is_required_artifact(self, branch: Mapping[str, Any]) -> bool:
        return (
            self._branch_is_image_generation(branch)
            or self._branch_is_required_text_artifact(branch)
            or branch.get('requires_artifact') is True
            or isinstance(branch.get('artifact_request'), Mapping)
        )

    def _branch_is_optional_advisory_helper(self, branch: Mapping[str, Any]) -> bool:
        if self._branch_is_required_artifact(branch):
            return False
        stage_direction = str(branch.get('stage_direction') or '').strip().lower()
        helper_text = ' '.join(
            str(branch.get(key) or '').strip().lower()
            for key in (
                'branch_id',
                'phase_id',
                'stage_direction',
                'role',
                'kind',
                'task_kind',
                'helper_kind',
                'description',
            )
            if str(branch.get(key) or '').strip()
        )
        return (
            stage_direction in {'run_global_semantic_closure_review', 'run_branch_semantic_review'}
            or any(
                marker in helper_text
                for marker in (
                    'semantic_review',
                    'semantic review',
                    'advisory',
                    'helper',
                    'image_state_enrichment',
                    'generated_image_state',
                )
            )
        )

    def _branch_scheduling_context(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        gap_payload = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        for payload in (gap_payload, branch):
            nested_context = payload.get('runtime_scheduling_context') if isinstance(payload.get('runtime_scheduling_context'), Mapping) else {}
            context.update(dict(nested_context))
            for key in ('repair_scope', 'resource_class', 'dependency_policy'):
                value = payload.get(key)
                if value not in (None, '', [], {}):
                    context[key] = value
        return {key: value for key, value in context.items() if value not in (None, '', [], {})}

    def _branch_is_target_artifact_snapshot_text_repair(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        capability = str(self.branch_capability(branch) or branch.get('capability') or '').strip().lower()
        if capability and capability != 'chat':
            return False
        output_type = str(branch.get('output_type') or branch.get('artifact_type') or '').strip().lower()
        if output_type and output_type not in {'text', 'code', 'document', 'html', 'css', 'json', 'markdown'}:
            return False
        context = self._branch_scheduling_context(branch, None)
        dependency_policy = str(context.get('dependency_policy') or '').strip().lower()
        if dependency_policy == 'target_artifact_snapshot_only':
            return True
        repair_scope = str(context.get('repair_scope') or '').strip().lower()
        resource_class = str(context.get('resource_class') or '').strip().lower()
        if repair_scope in {'syntax_only', 'text_artifact_syntax'} and resource_class in {'text_io', 'local_text_io'}:
            return True
        artifact_request = (
            branch.get('artifact_request')
            if isinstance(branch.get('artifact_request'), Mapping)
            else {}
        )
        target_path = str(
            branch.get('text_artifact_target_path')
            or artifact_request.get('target_path')
            or ''
        ).strip()
        role = str(branch.get('role') or '').strip()
        check_kind = str(branch.get('check_kind') or '').strip()
        content_payload_source = str(branch.get('content_payload_source') or '').strip()
        text_artifact_source = str(
            branch.get('text_artifact_source')
            or artifact_request.get('source')
            or ''
        ).strip()
        return bool(
            target_path
            and (
                check_kind == 'text_artifact_syntax_sanity'
                or role == 'text_artifact_syntax_repair'
                or content_payload_source == 'closure_text_artifact_syntax_sanity'
                or text_artifact_source == 'closure_syntax_repair'
            )
        )

    def _branch_conflicts_with_active_image_generation(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        if self._branch_is_target_artifact_snapshot_text_repair(branch, artifact_gap):
            return False
        capability = str(self.branch_capability(branch) or '').strip().lower()
        if capability == 'chat':
            return True
        if capability in {'vision_analysis', 'image_analysis'}:
            return True
        return self._branch_is_optional_advisory_helper(branch)

    def _branch_allows_gpu_heavy_concurrency(
        self,
        branch: Mapping[str, Any],
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        gap_payload = artifact_gap if isinstance(artifact_gap, Mapping) else {}
        context = self._branch_scheduling_context(branch, gap_payload)
        if self._branch_is_target_artifact_snapshot_text_repair(branch, gap_payload):
            return True
        for value in (
            branch.get('allow_gpu_heavy_concurrency'),
            gap_payload.get('allow_gpu_heavy_concurrency'),
            context.get('allow_gpu_heavy_concurrency'),
            context.get('explicit_allow_gpu_heavy_concurrency'),
        ):
            if self._runtime_scheduling_flag_enabled(value):
                return True
        return False

    def shape_active_late_fill_branches(
        self,
        active_branches: list[dict[str, Any]],
        *,
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        branches = [dict(branch) for branch in active_branches if isinstance(branch, dict)]
        if len(branches) <= 1:
            return branches, {}
        if all(self._branch_allows_gpu_heavy_concurrency(branch, artifact_gap) for branch in branches):
            return branches, {}
        required_image_branches = [branch for branch in branches if self._branch_is_image_generation(branch)]
        if required_image_branches:
            non_conflicting = [
                branch
                for branch in branches
                if self._branch_is_image_generation(branch)
                or self._branch_allows_gpu_heavy_concurrency(branch, artifact_gap)
                or not self._branch_conflicts_with_active_image_generation(branch, artifact_gap)
            ]
            if len(non_conflicting) < len(branches):
                deferred = len(branches) - len(non_conflicting)
                return non_conflicting, {
                    'gpu_heavy_guard': 'deferred_non_image_branches',
                    'reason': 'required_image_generation_first',
                    'original_branch_count': len(branches),
                    'scheduled_branch_count': len(non_conflicting),
                    'deferred_branch_count': deferred,
                }
        required_artifact_branches = [
            branch
            for branch in branches
            if self._branch_is_required_artifact(branch)
        ]
        optional_helper_branches = [
            branch
            for branch in branches
            if self._branch_is_optional_advisory_helper(branch)
        ]
        if required_artifact_branches and optional_helper_branches and len(required_artifact_branches) < len(branches):
            deferred = len(branches) - len(required_artifact_branches)
            return required_artifact_branches, {
                'gpu_heavy_guard': 'deferred_optional_helpers',
                'reason': 'required_artifact_closure_first',
                'original_branch_count': len(branches),
                'scheduled_branch_count': len(required_artifact_branches),
                'deferred_branch_count': deferred,
                }
        return branches, {}

    def select_active_late_fill_branches(
        self,
        dependency_ready_branches: list[dict[str, Any]],
        *,
        artifact_gap: Optional[Mapping[str, Any]] = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Select current work before applying resource priorities.

        A known availability wait must not reserve a resource ahead of ready
        siblings. When only waits remain, advancing the oldest due group
        prevents a permanently unavailable high-priority capability from owning
        every recheck. Existing wait deadlines supply the ordering; no new queue
        or execution authority is introduced.
        """
        ready: list[dict[str, Any]] = []
        due_waits: list[tuple[float, dict[str, Any]]] = []
        now = self.clock()
        for branch in dependency_ready_branches:
            wait = branch.get('availability_wait')
            if not isinstance(wait, Mapping) or not wait:
                ready.append(branch)
            elif self.availability_wait_delay(branch, clock=self.clock) <= 0:
                try:
                    deadline = float(wait.get('next_check_epoch') or 0)
                except (TypeError, ValueError, OverflowError):
                    deadline = 0.0
                # The delay helper also admits stale future timestamps after
                # clock movement. Revalidate those instead of sorting them last.
                if not math.isfinite(deadline) or deadline > now:
                    deadline = 0.0
                due_waits.append((deadline, branch))
        policy: dict[str, Any] = {}
        if ready:
            selected = ready
            if len(ready) < len(dependency_ready_branches):
                policy['availability_selection'] = 'ready_before_wait_rechecks'
        elif due_waits:
            oldest_due = min(deadline for deadline, _ in due_waits)
            selected = [branch for deadline, branch in due_waits if deadline == oldest_due]
            policy['availability_selection'] = 'oldest_due_waits'
        else:
            return [], {}
        if policy:
            policy['availability_deferred_branch_count'] = (
                len(dependency_ready_branches) - len(selected)
            )
        active, resource_policy = self.shape_active_late_fill_branches(
            selected, artifact_gap=artifact_gap,
        )
        return active, {**resource_policy, **policy}

    @staticmethod
    def availability_wait_delay(
        branch: Mapping[str, Any], *, clock: Callable[[], float] = time.time,
    ) -> float:
        wait = branch.get('availability_wait')
        if not isinstance(wait, Mapping):
            return 0.0
        try:
            remaining = float(wait.get('next_check_epoch') or 0) - clock()
            # A future timestamp beyond the supported poll range is stale
            # after clock movement; revalidate rather than hide the work.
            return 0.0 if remaining > 60 else max(0.0, remaining)
        except (TypeError, ValueError):
            return 0.0

