# Backend Fabric

This note describes the normalized backend discovery and lifecycle contract above
Ollama, MLX, llama.cpp, local Apple Foundation Models, and the Apple PCC Shortcuts bridge.

## Purpose

Fruth already had two strong truth layers:

- `model_ports.json` for stable instance registry truth
- `state/runtime_status.json` for cached readiness and backend observations, subordinate to current process/port/backend facts

The backend fabric supplies one shared summary that answers:

- which local backend variants are installed at all,
- which are fully runnable,
- which are partially installed or otherwise degraded,
- which are currently auto-wired into Fruth through models or active instances,
- and which lifecycle actions Fruth expects each backend variant to support.

That shared summary is the backend fabric.

It also supplies backend facts for provider-neutral routing in Fruth's interpretive inference layer. The layer should not hardcode provider families; it should consume the merged runtime/control-plane truth that backend fabric helps normalize.

Backend fabric is capability/runtime evidence. It is not promotion authority. A backend being runnable means a promoted branch can potentially execute there; it does not turn a possible image/audio/chat branch into owed work by itself. Candidate promotion, workload tasks, closure review, and artifact truth remain owned by the Responses runtime contract.

## Current Implementation State

Backend fabric is now an implemented control-plane evidence surface, not just a direction note.

It summarizes:

- running instances from `model_ports.json` plus merged `state/runtime_status.json`
- cached runtime-status evidence by default, with runtime probes reserved for explicit refresh, lifecycle, or execution paths
- available-model catalog aggregation when requested
- backend-native package/contract metadata such as `backend_package`, `backend_contract`, runtime controls, and source facts
- catalog counts that distinguish runnable models from cached-only or otherwise non-runnable sources

It does not own durable response truth. Response frames, successor ledgers, the selected response Index, work trees, outputs, and artifact dossiers remain part of the Responses/runtime substrate, not the backend-fabric contract.

## Current Variants

The current contract covers:

- `apple_fm` (Apple AI, installed `fm serve`, API model `system`)
- `apple_pcc` (Apple PCC, installed Shortcuts, API model `auto`)
- `ollama`
- `llama_cpp`
- `mlx_lm`
- `mlx_vlm`
- `mlx_audio`
- `mlx_whisper`

`llama.cpp` is now part of the current contract as the `llama_cpp` backend variant.

In the current runtime slice, Fruth also treats backend-native cache/runtime knobs as part of the truthful contract. For `llama.cpp`, that means the runtime probe and registered instance metadata can expose launch defaults such as prompt caching, KV offload, and Flash Attention mode when the installed `llama-server` supports those flags.

The same contract now applies more truthfully to MLX variants:

- `mlx_lm` exposes the server-side cache knobs it actually supports, such as `prefill_step_size`, `prompt_cache_size`, and `prompt_cache_bytes`.
- `mlx_vlm` exposes its real KV-cache launch knobs, including `kv_bits`, `kv_quant_scheme`, `kv_group_size`, `max_kv_size`, and `quantized_kv_start`.
- Fruth preserves active MLX launch defaults into instance metadata and runtime-status payloads, so the UI and control plane can report the effective cache mode instead of only showing a package label.

This is intentionally backend-native truth, not prompt-side emulation. `mlx_vlm` TurboQuant settings are treated as process launch settings because the upstream server applies them process-wide at startup.

`llama.cpp` source-aware handling is now part of the same maintenance surface as the other local backends:

- the pull/download and start/remove surfaces can register a local `.gguf` path or pull a GGUF Hugging Face repo for `llama.cpp`,
- pulled sources persist into a Fruth-managed catalog under `state/`,
- available-model payloads carry source truth such as `hf_repo`, `hf_file`, or `model_path`,
- and running `llama.cpp` instances can enrich runtime metadata from the live `/v1/models` endpoint instead of relying only on static registry facts.

Catalog discovery remains broader than startup eligibility. A backend can have visible cached/catalog sources without those sources being runnable yet on the current machine. In that case the normalized payload should preserve the source entry with a cached-only state and an explicit reason instead of pretending it is startable.

For `llama.cpp` pull/download behavior, Fruth now expects a non-interactive Hugging Face download path rather than abusing `llama-cli` as a downloader. When the system `hf` binary is not on `PATH`, Fruth also checks the MLX virtualenv sibling `hf` binary so the existing local MLX toolchain can satisfy `llama.cpp` catalog pulls.

Apple AI exposes local text chat, image analysis and streaming, with missing CLI/license/model
prerequisites represented explicitly. It does not offer pull/remove or variant
selection. Its instance metadata preserves source/time and raw `/v1/models`
observations. Optional macOS 27 Swift discovery records the host-default AFM
variant and context size under `backend_metadata.system_model`, with source/time.
Startup and catalog descriptions show these values. This cached host observation
does not fill the exact HTTP server's unknown variant, revision or context fields,
and a failed metadata probe does not make an otherwise runnable backend unavailable.
Its session controls also expose explicit OCR and barcode image modes when local
`fm respond --help` advertises them. These use a separate CLI session with verified
tool-result evidence; they do not advertise general HTTP tool-calling support.
See [Apple Foundation Models](APPLE_FOUNDATION_MODELS.md) for its tested transport
contract and context limitation in interpretive inference.

## Payload Shape

PCC installation discovery invokes `shortcuts list`, so ordinary backend-fabric,
runtime-manifest and routing snapshots must not perform it. They project the last
explicit catalog/start observation from the existing PCC owner, retaining its
`detection.observed_at` and marking `detection.cached=true`. Before discovery in
this server process, `detection.status=not_observed`, `observed_at=null` and an
advisory `runtime_state=degraded` distinguish unknown installation from a missing
shortcut or confirmed readiness. Explicit model-catalog discovery and PCC start
refresh installation prerequisites; actual PCC execution alone runs the inference
shortcut. A cached observation never verifies cloud access. The observation cache
is process-local and resets when Fruth restarts; passive reads never fill it.

Apple PCC uses an explicitly started loopback adapter and the ordinary instance,
transport and preferred-II paths. Its `runnable` state proves the bridge and at
least one uniquely named shortcut are installed; cloud account access is checked
only during execution. The catalog's separate `setup_available`
flag identifies missing bundled shortcuts that can be opened for user-confirmed
import; it does not make the model runnable. Only explicit Models setup or
interactive startup selection opens previews. Passive snapshots and ordinary
model starts never open them. Selection prefers Pro and falls back once to Cloud for
confirmed Pro access/availability errors. It supports text and image input,
including model-based OCR; native scanner and audio tools are not exposed. Inference-owned calls
receive the full ordinary inference policy and scoped Fruth roles. Direct chat
gets no automatic Fruth policy or role. Optional `backend_metadata.sdk_model` observes the
default native PCC API's context size; it never fills unknown exact Shortcuts
context/variant fields. Fresh `backend_runtime.last_execution` is a last-call
observation, while response-local `pcc_execution` identifies the call's shortcut
target and fallback evidence. See the [PCC guide](../fruth_integrations/shortcuts/README.md).

The normalized payload is built by `fruth_core/backend_fabric.py`.

Top-level fields:

- `schema_version`
- `generated_at`
- `backends`
- `summary`

Each backend item includes:

- `backend_id`
- `family`
- `variant`
- `label`
- `runtime_state`
- `auto_wiring_state`
- `auto_detected`
- `auto_wireable`
- `catalog`
- `instance_ids`
- `operations`
- `detection`
- `issues`

## State Meanings

`runtime_state` describes install/runtime availability:

- `runnable`
  The required local runtime pieces are present.
- `degraded`
  The backend is partially present but not fully usable.
- `missing`
  The required local runtime pieces are not present.

`auto_wiring_state` describes how that backend variant currently participates in Fruth:

- `active`
  Fruth already has one or more running instances for that variant.
- `discoverable`
  No active instance is running, but Fruth can already see runnable models/catalog entries for that variant.
- `unwired`
  The backend runtime is installed, but Fruth currently has nothing to wire for that variant.
- `degraded`
  The backend variant is only partially available.
- `missing`
  The backend variant is absent.

Catalog-state note:

- backend fabric counts distinguish `available_model_count`, `runnable_model_count`, and `cached_only_model_count`
- `cached_only` means Fruth can see the source snapshot or catalog record, but the current backend/runtime contract cannot launch it yet
- operator/startup surfaces should treat cached-only entries as discovery truth, not as runnable start targets

Active-runtime note:

- `active` means there is at least one running instance for that backend variant
- `discoverable` means the backend has runnable catalog/model evidence but no running instance yet
- `cached_only` catalog evidence must not promote a backend to `discoverable`; it remains source truth until the runtime can launch it
- backend fabric may expose active runtime capability, but only the resolver/runtime may execute a promoted branch against that capability

## API Surfaces

The backend fabric is now published through:

- `/api/runtime_manifest`
  Active routing/runtime view plus `backend_fabric`
- `/api/available_models`
  Available model catalog plus `backend_fabric`
- `/api/backend_fabric`
  Direct backend-fabric view

`/api/backend_fabric` is an observer surface. By default it merges running instances with cached `state/runtime_status.json` truth and must not probe or rewrite runtime status. `?refresh=true` is the explicit refresh path and may update runtime-status facts; the response carries compact `runtime_truth` metadata so clients can distinguish cached from refreshed truth.

`/api/backend_fabric?with_catalog=true` may perform the deeper available-model aggregation that `available_models` already uses. Without that flag, the route stays closer to the currently active runtime view. Catalog inclusion and runtime refresh are separate choices: `with_catalog=true` adds catalog breadth, while `refresh=true` opts into fresh runtime-status probing.

## Contract Intent

This contract is intentionally additive:

- it does not replace `model_ports.json`
- it does not replace `state/runtime_status.json`
- it does not replace backend/catalog source files such as `state/llama_cpp_catalog.json`
- it does not replace backend-specific lifecycle code
- it does not replace Responses truth surfaces such as response frames, work trees, output slots, outputs, or artifact dossiers

Instead, it gives the rest of Fruth one stable substrate summary so new backends can plug into the same control-plane shape.

Interpretive inference/runtime-intelligence note:

- backend fabric is not a second router, but it helps keep routing provider-neutral
- The interpretive inference layer consumes the normalized backend/runtime facts together with `model_ports.json`, `state/runtime_status.json`, and live session-control schemas
- that lets Auto choose among live instances by actual controls, modality support, runtime health, and backend-native traits instead of a hand-maintained provider preference list
- branch-local materialization uses backend fabric only after a promoted contract exists; missing runtime support may block or fail that branch, while missing upstream artifacts should become `repair_dependency_chain` rather than same-backend retry
