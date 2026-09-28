# Canonical Stack

For a practical repo-navigation view, read [Architecture Map](ARCHITECTURE_MAP.md). This note focuses on the layered model and canonical boundaries.

The stack is the implementation body for Fruth's deeper state model:

```text
Intent -> possibility space -> relevance -> promoted contracts -> runtime truth -> review -> freeze
```

Each layer exists to make that loop executable, inspectable, persistent, and available to external clients.

`fruth` is now organized around five primary layers:

## 1. `runtime core`

Authoritative local runtime substrate.

- Model lifecycle and ports
- `model_ports.json` as source of truth
- `state/runtime_status.json` as the dynamic runtime-status registry beside the stable model registry
- `state/llama_cpp_catalog.json` as the durable source catalog for pulled/registered llama.cpp models
- `fruth_core/backend_fabric.py` as the normalized backend discovery/lifecycle contract layer above backend-specific runtime managers
- `state/chat_history/` as the canonical durable history store for active UI conversations, including the Responses workbench, lineage rotation state, and the persisted message/request payloads that rebuild the frontend timeline
- `artifacts/` as the canonical user-visible artifact tree, with generated outputs stored in typed buckets under `artifacts/`, saved request inputs under `artifacts/inputs/`, and audit/report outputs under `artifacts/audits/`
- Ollama + MLX + llama.cpp + [Apple AI](APPLE_FOUNDATION_MODELS.md) runtime handling
- Optional [Apple PCC](../fruth_integrations/shortcuts/README.md) through a locally managed Shortcuts bridge, with model execution in Apple's cloud
- Capability-aware startup/stop
- Backend-native runtime defaults surfaced in registry/status metadata where supported
- manual external integration sync hooks for Codex

Primary package surface:

- `fruth_runtime/ollama_model_manager.py`
- `fruth_runtime/llama_cpp_model_manager.py`
- `fruth_runtime/mlx_model_manager.py`
- `fruth_runtime/apple_fm_model_manager.py`
- `fruth_runtime/apple_pcc_model_manager.py`
- `fruth_integrations/shortcuts/`
- `fruth_runtime/registry.py`
- `fruth_runtime/lifecycle.py`
- `fruth_runtime/status.py`
- `fruth_core/backend_fabric.py`

Compatibility backbone:

- `fruth_core/registry.py`
- `fruth_core/lifecycle.py`

## 2. `service layer`

Runtime-adjacent product services built on top of the substrate.

- public execution contract is canonical `/api/responses`; lower-level chat and infer routes remain below that layer only as backward-compatibility wrappers, not as the preferred internal execution path
- Responses payload parsing, envelope shaping, artifact shaping, response-frame snapshots, non-default control snapshots, explicit settings-artifact promotion, and synthetic streaming events
- chat and infer dispatch
- file intake
- scoped internal file tools for policy/memory/artifact files
- scoped internal command tools for control-plane loops
- infer history/cache
- transport and artifact helpers
- OCR/PDF helpers
- Interpretive inference runtime intelligence:
  - request phase graph derivation plus Auto routing from merged per-instance runtime truth
  - pure candidate normalization and promotion review through `fruth_inference/candidate_contracts.py`
  - `candidate_graph` plus `promotion_review` as the general possibility-to-contract layer for outputs, workload tasks, context, references, evidence, repairs, continuations, and learning hints
  - deterministic `review_criteria` as runtime/closure checks, with `semantic_review_criteria` reserved for demand-gated semantic review
  - current-turn-only intake hygiene for fresh turns, with old history/artifacts admitted only as explicit reference or continuation context
  - capability-safe interpretive inference preference boundaries for Auto routing
  - file-backed semantic roles projected into advisory `semantic_role_profile`; explicit `semantic_role_ids` select advisory orientation only
  - post-route detail-fill / control-hint extraction
  - resolver/detail-fill and graph closure review aware of late fill with successor-frame updates
  - branch-local continuation: downstream branches consume their own payloads, prompts, dependency artifacts, and evidence instead of rerunning the full root prompt
  - artifact dossiers as the read-side evidence surface for durable artifact identity, provenance, enrichments, linked messages/responses, and availability
  - structured text/file artifact envelopes such as `output_obligations[].content` are unwrapped to the payload content before persistence
  - route preview/runtime metadata plus archive/diagnostic interpretive inference memory and bounded self-observation support
  - interpretive inference-owned image/audio requests now default to prepare-first on chat with downstream materialization branches; plain chat may still end at phase 1
  - local backend model calls execute selected phases or materialize branches; graph/runtime truth decides fulfillment
  - visible file/artifact claims are truth-gated against runtime outputs before freeze

Durable completion and secondary observation have separate boundaries. The
finalizer constructs accepted frame/output truth, attempts Artifact Registry
persistence, then writes verified CAS, the Ledger and the derived Index. Relevant
settled Readiness retention follows synchronously and cannot roll back the frame
or authorize execution. Ordinary persistence errors are currently logged and may
leave a live result, so completion/delivery alone is not a durability receipt.
See [Responses Contract](RESPONSES_CONTRACT.md#finalization-and-durable-completion)
and the [current owner map](ARCHITECTURE_MAP.md#durable-state-continuation-and-observer-owners).

Primary package surface:

- `fruth_services/inference.py`
- `fruth_services/responses.py`
- `fruth_services/response_frames.py`
- `fruth_services/frame_planning.py`
- `fruth_services/control_snapshots.py`
- `fruth_services/settings_artifacts.py`
- `fruth_orchestration/working_frame.py`
- `fruth_services/file_inputs.py`
- `fruth_services/scoped_file_tools.py`
- `fruth_services/scoped_command_tools.py`
- `fruth_services/history.py`
- `fruth_services/transports.py`
- `fruth_services/ocr_pdf.py`
- `fruth_services/chat_history.py`
- `fruth_services/events.py`
- `fruth_inference/payload.py`
- `fruth_inference/semantic_role_profile.py`
- `fruth_inference/semantic_roles/registry.py`
- `fruth_inference/semantic_roles/registry.py`
- `fruth_inference/semantic_roles/*.md`
- `fruth_inference/router.py`
- `fruth_inference/control_hints.py`
- `fruth_inference/request_phase_graph.py`
- `fruth_inference/candidate_contracts.py`
- `fruth_inference/execution_planner.py`
- `fruth_inference/memory.py`

Compatibility backbone:

- `fruth_core/inference.py`
- `fruth_core/file_inputs.py`
- `fruth_core/history.py`
- `fruth_core/transports.py`
- `fruth_core/ocr_pdf.py`

## 3. `fruth ui`

Operator control room.

- Model management
- Arena comparisons
- Speech/image/vision flows
- Artifact access and logs
- Responses workbench `Auto` routing, preview, and conversation rotation surfaces
- fresh-draft/current-thread-first main workspaces instead of one merged history stream
- durable `History` archive surfaces for reopening older chats independently of the currently running instance set
- durable conversation replay through modular frontend history/rendering helpers

Primary implementation:

- `fruth_webserver.py`
- `fruth_server/infer_runtime.py` for infer request-shaping/execution ownership
- `fruth_server/infer_postprocess.py` for generated-image infer post-processing ownership
- `fruth_server/responses_runtime.py` for mutable Responses lookup/stream/late fill in-flight ownership
- `fruth_server/responses_request_runtime.py` for canonical `/api/responses` orchestration and batch-image dimension shaping ownership
- `fruth_server/request_intake_runtime.py` for request-intake normalization, explicit-target recovery, selected-reference extraction, and interpretive inference preference coercion ownership
- `fruth_server/response_semantics_runtime.py` for selected-reference semantics, prepare-phase contracts, semantic phase payloads, graph closure review construction, resolver deferred-gap shaping under `execution_planner`, and late fill state ownership
- `fruth_server/model_control_runtime.py` for backend-fabric, available-models, and lifecycle route-body ownership
- `fruth_server/infer_support_runtime.py` for input-artifact persistence, generic file/audio/PDF intake support, explicit infer-history retrieval, and PDF event logging; incoming PDFs are processed afresh
- `fruth_server/late_fill_runtime.py` for late fill branch resolver/executor ownership
- `fruth_server/inference_route_runtime.py` for interpretive inference route-manifest/context/auto-route plus route-support ownership
- `fruth_server/inference_route_runtime.py` also owns current-turn-only route-context hygiene and backend chat-message normalization for fresh turns
- `fruth_server/backend_transport_runtime.py` for provider request/stream/media adapter ownership
- `fruth_server/chat_runtime.py` for chat lifecycle and chat-streaming orchestration ownership
- `fruth_webUI.html` as the page shell, root state, startup wiring, and remaining inline conversation-timeline glue
- `static/ui/messages.js`
- `static/ui/conversations.js`
- `static/ui/settings-history.js`
- `static/ui/models.js`
- `static/ui/message-state.js`
- `static/ui/request-lifecycle.js`
- `static/ui/request-transport.js`
- `static/ui/voice-input.js`

Current frontend history contract:

- `message.artifacts[]` is the canonical reusable-file ledger for both user inputs and assistant outputs
- `message.outputs[]` is the canonical public output surface persisted in history; `output_slots` and `output_branches` remain richer substrate projections beside it
- `request_snapshot` stores durable request metadata and keeps `input_artifacts[]` only for explicit user-side inputs
- selected reference artifacts/messages are conversation-scoped next-turn anchors, not global workbench state
- conversation lineage is rebuilt from persisted conversation metadata plus slot history ids returned by the chat-history service
- active workspace panes render the selected/current conversation, while older durable chats reopen from archive/history surfaces instead of being merged into the active thread pane

## 4. Scripts

Executable command/operator surface.

- `scripts/fruthctl.py`
- `scripts/startup_model_manager.py`
- `scripts/sync_model_providers.py`
- `scripts/cleanup_model_providers.py`
- `scripts/mlx_whisper_server.py`
- optional diagnostics/utilities such as `scripts/model_provider_overview.py` and `scripts/probe_provider_concurrency.py`
- `scripts/fruthctl.py inference` as the CLI surface for runtime-intelligence summaries

The provider sync/cleanup scripts are operator entrypoints. Their external-client implementation lives under `fruth_integrations/`.

## 5. External Integrations

Consumers and client tunnels for the local runtime substrate.

- shared downstream sync orchestration
- Codex config sync
- current Codex client sync/unsync boundary
- declarative adapter-manifest metadata for external-client docks

Primary implementation:

- `fruth_integrations/downstream_sync.py`
- `fruth_integrations/registry.py`
- `fruth_integrations/adapter_manifest.py`
- `fruth_integrations/provider_sync.py`
- `fruth_integrations/provider_unsync.py`
- `fruth_integrations/codex/config_sync.py`
- `fruth_integrations/codex/provider_cleanup.py`
- `fruth_integrations/codex/provider_unsync.py`
- `FRUTH_INFERENCE.md` as the canonical interpretive inference runtime-policy source
- `FRUTH_FOR_AGENTS.md` as the human/operator and external-client guide

Operator entrypoints:

- `scripts/sync_model_providers.py`
- `scripts/unsync_model_providers.py`
- `scripts/cleanup_model_providers.py`

Adapter contract note:

- Codex sync remains OpenAI-compatible and targets Fruth control-plane `/v1` provider URLs.
- shared external-client orchestration should live under `fruth_integrations/` instead of being folded into general startup.

## Output Layout

User-visible artifacts now live under:

- `artifacts/audio/`
- `artifacts/images/`
- `artifacts/ocr/`
- `artifacts/transcripts/`
- `artifacts/documents/`
- `artifacts/manifests/`
- `artifacts/benchmarks/`
- `artifacts/settings/`
- `artifacts/inputs/`
- `state/response_frames/responses.jsonl`

Mutable/frozen request-state note:

- live request orchestration now uses `fruth_orchestration/working_frame.py`
- the live working frame keeps explicit `possibility_space`, `candidate_graph`, `promotion_review`, and `closure` state while a request remains fluid
- final frozen snapshots still persist through `fruth_services/response_frames.py`
- graph-patch reopen after a terminal frame is represented as successor/reopen truth with parent-frame lineage, not as mutation of the old frozen frame
- canonical Responses payloads may expose `runtime.graph_closure_review`, which records pre-freeze fulfillment/pending/blocked truth for the request phase graph
- Archive/diagnostic interpretive inference memory surfaces can still read recent frozen working-frame outcomes from `state/response_frames/responses.jsonl` together with event-derived learnings and self-observations, while active self-learning keeps retained sidecars under `state/self_learning/retained_sidecars/`; live routing no longer consumes a separate derived memory chain

Naming policy:

- timestamp-first UTC filenames for better chronological sorting in Finder/terminal
- collision-safe suffixing when multiple outputs would otherwise share the same timestamp/name stem

## Startup policy

Default startup should favor the canonical stack:

1. Start/manage models.
2. Start the current Flask UI/API.
3. Leave external client projections untouched unless the operator explicitly runs a sync command.

External integration sync belongs to explicit operator hooks such as `./fruth sync`, not to start/stop/restart lifecycle points.

Startup selection should stay capability-aware and runnable-only:

- interactive startup surfaces should offer only sources Fruth can actually launch now
- cached-only discovery entries remain visible through `/api/available_models` and backend-fabric views, but they are not start choices until the required backend contract is available

Canonical project environment:

- `.venv/`

The current HTTP control-plane implementation is Flask.

## Current Boundary

The canonical stack above is the implemented Fruth 0.1 runtime boundary.

Interpretive inference note:

- The interpretive inference layer is part of the current canonical stack
- The interpretive inference layer is not the whole of Fruth; it is the semantic/current-turn interpretation layer inside the larger runtime/control-plane substrate
- The interpretive inference layer owns intent anchoring and graph derivation; the resolver and late fill continue open graph obligations; runtime closure review decides what is real before freeze
- file-backed semantic roles now live in `fruth_inference/semantic_roles/*.md` and compile into advisory orientation frames via `semantic_role_profile`; explicit `semantic_role_ids` remain advisory and must not shape resolver patience, branch topology, payloads, or runtime truth outside the decision contract
- its job is provider-neutral runtime intelligence inside the control plane:
  - route from live per-instance truth
  - freeze every interpretive inference-owned request into `request_phase_graph`
  - surface route/runtime metadata back to the UI and clients
  - stay short of full orchestration
