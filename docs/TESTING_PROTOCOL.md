# TESTING PROTOCOL

Use this as the canonical test-routing and debugging guide for the affected
behavior. Start with focused checks, broaden for shared contracts or unresolved
risk, and run release validation when preparing a release. Once relevant checks
pass, repeat or broaden only for new changes, failures or unresolved concerns.
Prose-only edits ordinarily need static contract/link checks, not live inference.

For deterministic/fake conformance across the five intent/truth boundaries, run
`./fruth self-attack`. This does not run live models. An explicitly authorized
live sweep uses `--mode live --fake-evidence <matching-results.json>` or
`--live-after-fake`; it writes actual responses/artifacts through an already
running control plane. See [SELF_ATTACK.md](SELF_ATTACK.md) for oracles, discovered
profiles, full truth capture, budgets, reduction and regression replay.

Do not overthink. Just map the issue.

---

## Quick Debug Flow

For startup dependency behavior, run `tests/test_stack_shutdown.py`. Its shell
fixtures verify that existing environments never run pip on start/restart, even
after requirements change, while a new environment installs once and stops on
installation failure. All commands and environment files are isolated; tests do
not install packages or start real models.

1. Did it understand the request?
   → interpretive inference

2. Did it create the right work?
   → interpretive inference structure + `candidate_graph` / `promotion_review`

3. Did it execute the right thing?
   → Resolver / branch-local workload task

3a. Did route preview or route selection start or force-start anything?
   → Start-source boundary / runtime liveness guard

3b. Did an external downstream executor receive one bounded task without
    re-entering Fruth, while interpretive inference planning remained an internal Fruth role?
   → External downstream execution boundary

4. Is the output itself good?
   → Provider

5. Is state / continuation correct?
   → Runtime / late fill / graph closure review

5a. Do final linked artifacts resolve to saved local dependency paths?
   → Runtime / artifact registry / terminal rebind / repair-needed closure

5b. Did a known terminal/closure failure produce no graph-repair proposal?
   → Backend runtime evidence bridge / `fruth_services.graph_repair`

5c. Did `BLOCKED:` provider output become content or an artifact?
   → External-provider block projection / runtime truth gate

6. Does it feel right?
   → UX

---

## Short Mapping

- misunderstood → interpretive inference
- wrong branch / flow → interpretive inference, candidate graph, promotion review
- wrong execution → Resolver, branch-local payload, backend fabric
- recursive or widened external execution → downstream execution marker and bounded-task contract
- route-driven start → start-source guard, runtime liveness, model control
- bad output → Provider
- broken state → Runtime, response frame, artifact dossier
- unresolved generated links → artifact registry, terminal rebind, graph closure review
- counted image branch received a whole answer or selected data file → exact image-prompt cohort / branch-local handoff
- explicit image retry repeats `NO_COMPATIBLE_INSTANCE` while excluded providers are currently ready → exhausted-pool retry policy / live candidate truth
- a successful successor under the same response id has no new report → monitor frame identity / reference-export binding
- graph repair proposal missing despite runtime evidence → backend runtime evidence bridge, `graph_repair_proposals`, `graph_repair_reviews`
- graph repair patch staged/applied unexpectedly → `FRUTH_GRAPH_REPAIR_AUTONOMY`, `graph_patch_lifecycle`, `staged_graph_patches`, `applied_graph_patches`
- `BLOCKED:` provider text materialized as output content → external-provider block projection, artifact acceptance, late fill
- modality cue created work without a current-turn obligation → candidate graph, promotion review, Closure-repair authority
- bad feel → UX
- final text appears twice only after compact lookup/history hydration → response output ownership; test persisted wire projection and repeated hoisting without role sidecars
- graph-resolved preparation selects semantic roles but the execution call loses their guidance → shared root policy-message handoff; test role guidance and direct-request isolation across all four backends in `tests/test_inference_policy_scope.py`

## Current Failure Mapping

- possible work executed even though it was only reserved → promotion review
- a reserved, negated, or inferred modality cue creates executable or Closure-repair work without a promoted current-turn obligation → promotion/repair-authority regression
- required work missing from the graph → candidate extraction or graph closure repair
- an external branch-executor call lacks `[FRUTH_DOWNSTREAM_EXECUTION_V1]`, can recursively invoke Fruth, widens `<fruth_bounded_task>`, or applies the marker to interpretive inference planning → downstream execution-boundary regression
- downstream output beginning with `BLOCKED:` becomes artifact/materialization content, fulfillment, or Late Fill work instead of blocked runtime truth → external-provider block-projection regression
- later branch used the whole first answer → branch-local handoff
- two or more requested images run without the exact number of distinct branch-local prompts, an explicitly malformed count is treated as an absent single-image count, or a full website/code response becomes every image prompt → counted image-prompt contract regression
- an explicit image retry clears exclusion history, prefers an excluded provider over a ready non-excluded provider, reuses stale snapshot-only liveness, bypasses a missing prompt contract, or automatically retries again after failure → explicit image exhausted-pool policy regression
- a failed frame prevents a later same-response success frame from receiving its own monitor report, or reference export accepts a report for the wrong frame → frame-scoped observer/export regression
- image/audio follow-up text is hypothetical → missing evidence branch or artifact dossier
- TTS produces a non-empty but wrong recording and any non-empty STT transcript still closes the graph → TTS source-fidelity evidence gate regression
- TTS returns HTTP 200 plus a readable but silent, severely truncated, or mostly padded WAV and the audio slot still fulfills → output-side TTS integrity regression
- labelled/numbered TTS candidate speaks wrapper prose, transcript claims, code, or JSON → branch-local audio candidate extraction regression
- dependent STT runs without a digest-bound direct TTS producer result, or typed mismatch evidence disappears after frame normalization → dependency evidence fail-open/durability regression
- dependency artifact missing → `repair_dependency_chain`, not same-branch retry
- file artifact contains router JSON → text artifact payload extraction
- saved text syntax failure loses the target path/current bytes/issues or repeatedly regenerates the whole artifact → target-bound saved-text syntax recovery regression
- Interpretive inference route preview starts a model → start-source policy regression
- duplicate, placeholder, or template-variable links such as `{{IMG_PATH_1}}` survive in final HTML/CSS/media → linked-artifact closure regression
- a multi-page site closes after generated images were appended as an unstyled detached stack to the first HTML file, or room/item images remain unbound from their semantic records → composed-site image-role/layout closure regression
- a composed-site target repair disappears because its existing file is mistaken for new write evidence, or a bundle leaves a retained-input path unresolved after selecting its newer authoritative file → target-bound handoff/bundle-authority regression
- optional generated-image `image_state_enrichment` disappears without `pending_existing`, `skipped`, or a suppression reason → image-state enrichment transparency regression
- `proposal_count=0` even though there is `materialization_contract_unmet`, terminal pending work, duplicate artifact refs, fake artifact refs, or actionable blocked/repair/semantic-review surface mismatch → graph-repair runtime evidence bridge regression
- `reconcile_surface_state_or_reopen_contract` appears for advisory-only pending `controlled_attention_review`, `aspiration_review`, `commitment_review`, or reconsideration state → graph-repair surface-actionability classifier regression
- `redraw_scope_ladder_review` skips a smaller current-intent scope, treats accepted learning/advisory/degraded/provider/cache/frontend/monitor/UI-label evidence as authority, or allows duplicate artifact refs to project as successful final output when refs conflict → intent-aligned redraw scope regression
- explicit text/media/local-artifact fit promises complete without `intent_lens_review` aspiration evidence or whole-turn semantic-review promotion → current-intent closure regression
- Intent Lens attention adds duplicate `rebuild_from_promoted_obligations` repair when a concrete `intent_graph_adequacy` or branch-contract repair already exists → duplicate repair-promotion regression
- `apply_safe` mutates a graph for review-required/forbidden classes, terminal frozen frames, degraded-only evidence, backend-family route-health diagnostics, accepted-learning-only proof, or advisory-only surfaces → graph patch lifecycle/autonomy regression
- `apply_reviewed` mutates review-required graph work without `graph_patch_authorization.status=accepted`, runtime/operator authority, `allowed_autonomy=["apply_reviewed"]`, and evidence refs → graph patch authorization regression
- `apply_enforced` fails to resolve an absent `FRUTH_APPLY_ENFORCED_POLICY` to product-default `safe_v1`, applies with explicit `off`/`audit`, applies a class outside safe-v1, skips safe-additive risk classification, redraw-scope/current-evidence/idempotency/forbidden-evidence gates, or treats accepted learning/degraded/provider/frontend/monitor-only evidence as authority → enforced policy regression
- invalid `FRUTH_GRAPH_REPAIR_AUTONOMY` silently falls back to `off` without `raw_value` and `invalid_value` diagnostics → graph patch autonomy diagnostics regression
- `shadow` or `stage` creates branches, obligations, dependency edges, or late fill work → graph patch lifecycle regression
- terminal `apply_safe`/allowed `apply_enforced` mutates the frozen parent, stops at an inert `successor_reopen_requests[]` candidate, widens beyond the exact applied branch set, replays the root prompt, loses same-response parent lineage, or schedules the same successor key twice → terminal successor/reopen execution regression
- graph rebase proposal applies without runtime-computed diff and preservation proof, drops required obligations/artifact refs/review duties/lineage, relies on learning-only/provider/degraded/advisory evidence, or mutates a parent graph directly → graph rebase preservation regression
- absent `FRUTH_GRAPH_REBASE_AUTONOMY` is not visible as product-default non-executable `shadow`, `shadow` is treated as a separate layer/rung, `stage` creates executable work, explicit rebase `off` does not block `stage` and `authorize_partial` while retaining evidence-only adjudication, lower bounded additive repair is accidentally disabled, or full successor rebase executes under safe partial v1 → graph rebase lifecycle/autonomy regression
- readiness reads mutate runtime state, insufficient evidence reports a green gate, operator actions work without both the configured token and matching configured identity, credentials reach any child process, durable full/observation projections do not bind the same latest frame, accept caller-authored replay truth, cannot record a response-bound no-proposal false negative, permanently block on a false negative after one exact same-class replay-verified resolution, allow unknown/non-useful/duplicate resolution links, count unpaired registry/runtime stages, skip `adjudicate -> stage -> authorize_partial`, accept stale/wildcard/non-CAS identities or inline authorization, execute a stage record, consume a non-partial/full request, mutate the frozen parent, lose atomic parent CAS, schedule before successor persistence, accept missing/drifted current root truth, replay the root prompt through any phase/downstream prompt carrier even after source relabeling, or duplicate a consumed successor → reviewed partial rebase rollout regression
- `clean`/`archive` preserves `state/self_learning/` while deleting the response-frame sidecars it references, without `retention_manifest.json`, retained copies, or missing-sidecar diagnostics → self-learning retention regression
- public prose rename touches only docs/operator text → glossary review plus active-doc search is enough
- literal compatibility key rename touches request/runtime/history/replay payloads such as `planner_timeout_ms`, `runtime.execution_planner`, or `execution_planner_deferred_follow_up` → compatibility migration regression; require aliases or dual-read/dual-write before changing writers
- Interpretive inference, resolver, router, semantic-role, or injected-policy prompt wording changes → behavior-affecting prompt regression; require targeted route/resolver/Responses tests and live A/B checks when a local runtime is available

## Current Self-Healing Test Slices

For cross-backend chat/file/vision provider failover, run
`tests/test_provider_failover.py`, `tests/test_backend_transport_runtime.py`, and
the Responses routing/preference, self-heal, chat/stream and Apple transport
slices. Run in a disposable source checkout with empty temporary state and
network/subprocess execution blocked. Cover PCC quota -> configured fallback ->
automatic selection, exclusion/exhaustion, exact task/graph/reference identity,
saved attempt evidence, incompatible input/controls, fixed/locked targets,
refusal/invalid/evidence rejection, stream-open failure and no producer switch
after streamed output. These deterministic tests do not establish live provider
availability or turn the historical quota-limited PCC campaign into a full pass.

For the external downstream execution boundary, run:

    .venv/bin/python -m pytest tests/test_codex_runtime_bridge.py -q

The expected shape is that only an actual external branch-executor call starts
with `[FRUTH_DOWNSTREAM_EXECUTION_V1]`, carries one
`<fruth_bounded_task>` plus only promoted `<fruth_promoted_context>`, and forbids
recursive Fruth use or follow-up work. Interpretive inference planning itself remains unmarked
because it is a Fruth-internal runtime role, does not invoke the companion
skill, and receives manifest, model, and capability orientation from Fruth. An
external target selected after that planning still receives the downstream
marker. A result beginning with `BLOCKED:` must project blocked lifecycle,
output, and surface truth, create no artifact, and skip materialization,
Closure, and Late Fill.

For labelled/count TTS extraction, output-side WAV integrity, and TTS-to-STT semantic evidence, run:

    .venv/bin/python -m pytest tests/test_tts_audio_integrity.py -q
    .venv/bin/python -m pytest tests/test_response_semantics_runtime.py -q -k "tts or speech_to_text or audio_variant or semantic_evidence or audio_integrity"
    .venv/bin/python -m pytest tests/test_fake_backend_e2e.py -q -k "tts_stt_and_vision or silent_tts"

Include Markdown `#` narration headings in mixed website output, with plain or
text/audio-labelled fenced text. Only the labelled spoken body may feed TTS;
HTML/CSS, transcript and JSON siblings must stay out. Multiple narration sections
still require branch selection, and headings inside code do not establish a source.

The expected current shape is exact branch-local speakable payload selection, contiguous labelled candidate authority, exclusion of transcript/analysis/code/JSON siblings, durable exact final-prompt `tts_semantic_source`, deterministic source/file-bound PCM-WAV signal evidence, direct-producer-only `tts_stt_semantic_evidence`, harmless transcript normalization acceptance, and fail-closed silence/truncation/padding/malformed/missing/digest/binding handling. HTTP 200 or a non-empty WAV must not fulfill audio by itself. Expected text must never enter the STT request, downstream joins must stay unexecuted on mismatch, and a physically materialized wrong WAV remains diagnostic evidence rather than fulfillment.

For bounded TTS semantic regeneration, also run:

    .venv/bin/python -m pytest tests/test_tts_semantic_regeneration.py -q
    .venv/bin/python -m pytest tests/test_tts_semantic_checkpoint.py tests/test_response_frozen_lookup.py -q

Checkpoint observation must cover a durable read before live checkpoint
publication and another read afterward. Both reads must expose the identical
canonical frozen frame for the exact ID/sequence, including when a recovered
parent's durability envelope survives in live state. Keep current progress at
the top level; do not mix expanded finalizer and compact durable bodies under
one frozen identity. Exercise both successful and exhausted single repairs,
repeated reads, unchanged predecessor bytes, and foreign/stale identity guards.

The expected shape is a positive existing semantic mismatch with verified exact
producer/file binding, one durable consumed repair attempt, fresh artifact,
re-verification and normal Closure. Test unavailable/ambiguous/technical/binding
failures and cancellation as noneligible; duplicate callbacks and restart must
not reset the budget. Verify original evidence preservation, branch independence,
accepted artifact/frame/registry projection and failed-repair exhaustion. Fake
mechanics prove the policy; at most two explicitly authorized live cases prove
integration and must not be repeated until a natural mismatch appears.

For bounded vision evidence recovery, first run `tests/test_vision_evidence_recovery.py`
in the disposable, network-blocked checkout described below. Cover actual image
dispatch receipts for Ollama/MLX/llama.cpp, one alternate success, two rejected
answers, no available alternative, cancellation, exact producer/input binding,
changed or missing image bytes, and durable retry evidence/counters. A failed
instance must never be reused by this policy. The downstream join must execute
only after accepted vision evidence. Also run the dependency-evidence API tests,
the audio retry/regeneration tests, and the affected inference dispatch tests;
do not use live models merely to exercise the retry mechanism.

For counted image handoff, explicit exhausted-pool retry, and frame-scoped recovery evidence, run:

    .venv/bin/python -m pytest tests/test_response_semantics_runtime.py -q -k "image_prompt or incomplete_image"
    .venv/bin/python -m pytest tests/test_responses_api.py -q -k "image and (retry or batch or branch_contract)"

For terminal link-rebind write evidence and branch settlement, run:

    .venv/bin/python -m pytest tests/test_terminal_output_reconciliation.py -q
    .venv/bin/python -m pytest tests/test_responses_api.py -q -k "terminal_link_rebind or terminal_linked_artifact or terminal_materialization_contract"

Run these in the disposable checkout described below. Reproduce a lightweight
checkpoint whose public audio output is still pending after the producer settles.
Final linking must use the current accepted output, preserve exact bindings and
frozen parents, and pass Closure and the bundle link check without regenerating
media. Failed, cancelled, waived, superseded, unpublished or ambiguous media must
not become eligible from file existence or an older public-output claim. Shared
preparation also requires response-frame, canonical artifact and bundle coverage.

Keep both the minimized single-branch case and the four-image inline-CSS Hive
case. Applied link-rebind evidence carries exact branch/phase identity only
when an already-owned saved artifact/result and that branch's bounded repair
independently select the actual written transformation. Same-target pending
branches, unrelated revisions, conflicting identities, and different dependency
selections must not inherit the write. A coalesced physical write may produce
separate exact-owner records only after each owner passes this check. Repeated
rebinding must neither rewrite unchanged bytes nor append evidence. Legacy
identity-free records remain readable diagnostics, never retroactively attributed
write authority. Ledger and UI projections preserve optional branch identity.

For generated-site image placement and bounded cohort repair across single/multiple pages and external/embedded/inline CSS, run:

    .venv/bin/python -m pytest tests/test_composed_site_closure.py -q
    .venv/bin/python -m pytest tests/test_afm_preparation_handoffs.py -q

    .venv/bin/python -m pytest tests/test_response_semantics_runtime.py -q -k "composed_site_image_closure or composed_page"
    .venv/bin/python -m pytest tests/test_responses_api.py -q -k "authoritative_composed_site_image_repair"
    .venv/bin/python -m pytest tests/test_response_artifact_bundles.py -q
    .venv/bin/python -m pytest tests/test_fruth_run_monitor_projection.py tests/test_reference_run_export.py -q

Include the terminal `superseded_composition_recovery` API regression. Cover a
styled listening image with an unstyled hero, repeated occurrences, unlinked and
cross-page styles, inline styles, picture sources, and script-rendered cards.
Fresh exact supersession must retire its recovery candidate and repair contract
without accepting a missing repair body, losing failed-attempt evidence, or
closing conflicting/unrelated work. The final frame must clear stale partial
failure only after the substantive contract is fulfilled.

The expected shape is that `batch_prompt_expected_count >= 2` requires the exact number of non-empty branch-local prompts and a valid slot selection. Shared preparation prose, full HTML/CSS/JSON answers, selected room data, root prompts, and heuristically focused fragments must be removed and exposed as `incomplete_image_prompt_batch` before routing. A user-triggered retry after `NO_COMPATIBLE_INSTANCE` keeps all exclusions, prefers any ready non-excluded alternative, and may reuse one excluded provider only under `explicit_image_excluded_pool_retry_v1` after fresh live truth; the attempt cannot auto-follow up. Missing contracts and refresh failures fail closed. A failed frame and a later successful frame under one response id each receive one append-only report, while export accepts only evidence matching the authoritative latest frame and leaves the source ledger byte-identical.

For accepted-learning and graph-repair changes, run:

    .venv/bin/python -m pytest tests/test_graph_repair_self_healing.py tests/test_self_learning.py -q

Use this when touching `fruth_services/self_learning.py`, `fruth_services/graph_repair.py`, `fruth_services/self_learning_retention.py`, decision-contract learning/repair surfaces, or monitor learning/healing summaries. The expected current shape is that accepted learning remains soft orientation, backend runtime evidence can synthesize proposal-only graph repairs into response truth, advisory-only pending surfaces do not synthesize repair-needed graph work, actionable blocked/repair/semantic-review evidence remains repairable, monitor reviews are paired by `proposal_id` as observer summaries, validation rejects missing evidence, broad provider disablement requests, and accepted-learning-only proof, graph patch lifecycle honors `off`/`shadow`/`stage`/`apply_safe` idempotently, `apply_reviewed` requires explicit per-review `graph_patch_authorization`, duplicate lifecycle learning uses the final/informative record, self-learning reports retention integrity, redraw-scope learning stays `soft_hint_only`, and terminal successor/reopen outcomes remain soft eval evidence.

When touching reviewed graph rebase, include the validator, runtime producer, readiness evaluator, trusted operator registry, control-plane authentication, and partial successor owner. The expected current shape is a concrete backend-built candidate, post-repair Closure/scope precedence, no proposal during active Late Fill plus deterministic terminal candidate re-derivation, runtime-owned meaningful diff and preservation proof, no-op/digest/lost-dependency/same-ID or graph-wide semantic-drift/candidate-bookkeeping/partial-containment rejection, advisory interpretive inference feedback excluded from authority, and product-default non-executable `shadow` with truthful startup provenance. The canonical readiness report is read-only and evidence-gated. Promotion is exactly `adjudicate -> stage -> authorize_partial`; stage is durable audit-only, authorization is registry-trusted and exact-CAS-bound, explicit environment `off` wins, and only a gate-approved partial subtree may append one same-response branch-local successor before scheduling. False negatives remain historical but may be resolved only by one later exact same-class replay-verified useful proposal. Tests must cover missing and drifted current root truth at replay and apply, matching durable full/observation frame identities, phase/downstream prompt carriers (`phase_summary`, `stage_direction`, instructions, criteria), request preservation across successor frames, and credential stripping for direct backend/utility child-process spawns. Root-prompt fallback, parent mutation, full execution, stale lineage, widened scope, missing local execution contracts, and replay duplication must fail closed.

    .venv/bin/python -m pytest tests/test_graph_rebase_review.py tests/test_runtime_graph_rebase_shadow_producer.py tests/test_graph_rebase_readiness.py tests/test_graph_rebase_operator.py tests/test_graph_rebase_partial_successor.py -q

When touching enforced policy, include:

    .venv/bin/python -m pytest tests/test_apply_enforced_policy.py tests/test_graph_repair_self_healing.py tests/test_graph_rebase_review.py tests/test_self_learning.py -q

The expected current shape is default-deny `FRUTH_APPLY_ENFORCED_POLICY`, visible invalid/off/audit diagnostics, safe-v1 allowance only for narrow additive/identity classes, safe-additive risk classification required for safe-additive classes, duplicate artifact alias canonicalization only when refs are proven aliases, conflicting duplicate refs blocked, placeholder/output-slot/work-tree lineage preserved, learning-only and degraded/provider/frontend/monitor-only evidence rejected, full successor rebase blocked, and direct `apply_enforced` partial rebase audit-only/blocked. The separate exact operator-reviewed partial successor path must not be mistaken for enforced authority.

When touching intent-aligned repair/redraw scope selection, include:

    .venv/bin/python -m pytest tests/test_redraw_scope_ladder.py tests/test_response_frames.py::ResponseFrameTests::test_response_frame_canonicalizes_duplicate_artifact_aliases_in_final_projection tests/test_response_frames.py::ResponseFrameTests::test_response_frame_keeps_conflicting_duplicate_artifact_ref_repair_needed -q

The expected current shape is that Runtime exposes `redraw_scope_ladder_review`, reserved/additive/binding/identity scopes are considered before partial or full rebase, graph repair proposals only consume the scope as orientation, rebase proposals preserve bounded scope fields, duplicate refs are canonicalized only when proven aliases, and conflicting duplicate refs stay repair-needed.

For a direct TTS producer → STT input boundary, also run
`tests/test_fake_audio_dependency.py`,
`tests/test_same_response_audio_handoff.py`,
`tests/test_selected_audio_reference_binding.py`, and
`tests/test_tts_semantic_regeneration.py`. Exercise real canonical producer
creation, dependency and infer preparation, and internal infer dispatch before
Registry publication. Verify exact producer/ref selection with multiple audio
producers, reject missing/conflicting identities and HTTP-injected authority,
check current source/private-copy bytes, and compare later Registry/frame
identity. Mock only provider execution and host probes; do not pre-seed the
missing identity or skip the infer entrypoint.

Direct test invocations of Late Fill completion must use the isolated Flask
`TESTING` app context. This lets the existing scheduler keep successor work
inside the test boundary; assert no in-flight worker remains before fixture
teardown so later frame-store/CAS tests cannot receive escaped writes.

The fake integration must execute a same-response TTS → STT Late Fill chain,
decode the actual verified private WAV copy, retain semantic source evidence,
and exercise the unchanged `exact_source_binding` oracle. Separate direct TTS
and STT requests or verifier-only fixtures do not cover the private
`direct_audio_dependency` invoker interface. The fake boundary reuses Runtime's
identity/consumer/source-and-copy verification; it must not discard this
argument, mint authority from request JSON or substitute equal-content media.

For canonical artifact registration, run:

    .venv/bin/python -m pytest tests/test_canonical_artifact_registry.py tests/test_artifact_registry.py tests/test_artifact_dossiers.py tests/test_artifact_authority.py -q

Cover reconciled multi-artifact frames, exact refs and producer bindings,
successor recovery, stale top-level projections, alias promotion, equal-content
distinct files, idempotent refresh and existing missing/invalid-file behavior.
Then include response-frame/lookup, readiness-registry consumers and affected
API/fake-backend checks in a disposable checkout. Registry verification must
compare canonical IDs/refs/paths/digests, not file counts alone.

For local artifact path identity, also run:

    .venv/bin/python -m pytest tests/test_responses_api.py -q -k "artifact_path_identity"

Different path spellings under one artifact ref may alias only when all resolve
to the same existing local file. Relative paths use the Fruth checkout root,
never the caller's working directory or a basename search. Checksums alone do
not establish identity. Preserve original paths and branch/phase/provenance in
alias metadata. Distinct files with equal bytes or basenames, unresolved paths,
and incompatible types remain conflicting. Final lifecycle must honor blocked
artifact outputs, and slot hydration must preserve a frozen conflict; only a
new validated frame can replace that adjudication. Active execution, hard
terminal state, and unrelated open Closure checks retain their authority.

For generic intent-obligation graph adequacy, run:

    .venv/bin/python -m pytest tests/test_explicit_file_contract_preservation.py tests/test_inference_service.py tests/test_request_phase_graph_runtime.py tests/test_saved_file_consumer_path.py tests/test_saved_file_graph_rebuild.py tests/test_file_output_contract_boundaries.py -q

The explicit-file slice must preserve all accepted named files before model
output and across reduced detector/planner/response-graph results. Missing or
wrong-identity files must not yield fulfilled Closure; a complete set may close.
Keep JSON answer-format/source/negation boundaries, exact counts and identities,
extra-derived-file behavior, explicit release states and saved-file dependencies.
Plain-text semantic correctness remains separate from file-contract preservation.

For saved-file fulfilment shortcuts, run `tests/test_saved_file_consumer_path.py`
and the affected canonical-file/coalesced-result API tests in the disposable,
offline checkout described below. Cover files emitted before their branches run,
missing or changed producer/read evidence, reuse of complete proven records, and
a missing consumer result despite an existing output file. The full-worker
regression must still execute producer → saved read → consumer and close with
verified evidence; ordinary file reuse and deterministic syntax repair must
remain supported.

Include separate streamed draft paths with the same logical filenames as the
later branch outputs. A proven producer must close against its exact saved
identity, preserving the drafts and publishing only the final file set. A valid
draft must not conceal missing, changed, misbound or syntactically invalid
producer output, a conflicting explicit target, or duplicate producer results.
Keep the ordinary unbound multiple-file case ambiguous.

For the broader adequacy and runtime wiring boundary, also run:

    .venv/bin/python -m pytest tests/test_request_phase_graph_runtime.py tests/test_response_semantics_runtime.py tests/test_graph_repair_self_healing.py -q

Use this when touching `fruth_inference/intent_obligations.py`, `fruth_inference/request_phase_graph.py`, structural `intent_graph_adequacy`, or graph-repair bridges from adequacy checks. The expected current shape is that `request_phase_graph.intent_obligations` exposes text artifact, media artifact, evidence branch, dependency, and navigation promises; strong producer-before-consumer bindings such as generated local images before HTML consumers become executable dependency edges before work runs; missing executable edges surface as `intent_graph_adequacy_missing_dependency_edge`; and Runtime can validate/apply only a safe additive missing-dependency-edge patch. Advisory/provider/degraded/cache/liveness or accepted-learning-only signals must not create executable obligations or validate patches.

The same slice must prove that reserved, negated, or merely inferred modality
cues remain non-executable and do not create Closure-repair work unless a
current-turn obligation was explicitly promoted.

For cleanup/archive retention policy, run:

    .venv/bin/python -m pytest tests/test_maintenance_archive.py tests/test_clean_repo_state_policy.py tests/test_self_learning.py -q

Maintenance tests use temporary repositories, including CLI dry-runs. Cover whole
campaign copies and source/script preservation, internal report links, archive/cache
exclusions, insufficient space, changing sources, copy verification and move failure
before cleanup. A real checkout preview is a separate explicit read-only operation.

Dry-run output should include learning-retained and missing response-frame sidecar counts. `state/self_learning/retention_manifest.json` and `state/self_learning/retained_sidecars/` are the evidence continuity surfaces; missing refs should be visible diagnostics, not silent hydration gaps.

For response runtime lifecycle wiring, also run:

    .venv/bin/python -m pytest tests/test_response_semantics_runtime.py -q

For availability waiting, include `availability_wait` and `unavailable_preparation` tests in `tests/test_responses_api.py`, `tests/test_response_semantics_runtime.py`, and `tests/test_runtime_contract_knobs.py`. Fake-clock tests must show pending status, visible wait metadata, unchanged repair counters/targets, ready-sibling progress, one automatic execution after availability returns, and responsive cancellation. Hard-unavailable and excluded-only candidates must not create wait evidence. Run `tests/test_runtime_liveness.py` to preserve cooldown selectability semantics and `tests/test_response_wire.py` for compact wait projection.

`shadow` and `stage` must not mutate executable graph work and must carry non-executable `runtime_effect` values from lifecycle construction. `apply_safe` may apply only validated safe additive patches. On terminal/frozen parents, allowed safe additive repair must keep the parent blocked and byte-stable, persist an exact same-response successor relation, revalidate current autonomy/policy and patch/graph bindings, schedule only the applied owed branches through Late Fill, and keep repeated preparation idempotent. Request preparation and materialization-spec construction must both reject inherited root/assistant prompt recovery when the exact successor branch has no local payload. Same-key execution truth must progress from queued to running to one immutable terminal result across the complete Late Fill envelope, graph, request, and diagnostic projections; delayed queued/running or conflicting terminal callbacks must not restore pending/active branches, regress the canonical response lifecycle, or replace terminal truth. A fake-backend E2E must prove one branch-local backend execution and no root-prompt replay. Invalid graph repair autonomy values must stay safe `off` while surfacing diagnostics.

## Response-Ledger Lookup And Test Isolation

For recent-event reads, run `tests/test_event_log.py`,
`tests/test_event_log_tail.py`, `tests/test_event_api.py` and
`tests/test_causal_telemetry.py` in the disposable offline checkout. Compare
newest-first results and matching-event limits with the legacy reader across
filters, UTF-8/chunk boundaries, long records, malformed tails and line endings.
Count actual bytes to prove early stop once enough matching events are found;
rare filters may still require the full history. Check fresh append/replacement,
the initial end-of-file boundary and the real `/api/inference` event-read path.
Use synthetic temporary logs for tests and benchmarks, preserving history bytes.

For causal convergence observations, also run:

    .venv/bin/python -m pytest tests/test_causal_telemetry.py tests/test_self_attack_convergence.py tests/test_self_attack_production.py tests/test_fruth_run_monitor_projection.py -q

See `docs/CAUSAL_TELEMETRY.md` for event bounds, exact-identity proof gates and
inclusive persistence timings. Projected lenses are not model invocations;
historical or incomplete causality stays unknown. New observations must not
change owner outputs, retry/lock behavior, authority or durability boundaries.

When touching response lookup, index persistence, or `/api/responses/<id>` recovery, run:

    .venv/bin/python -m pytest tests/test_response_frames.py -q
    .venv/bin/python -m pytest tests/test_responses_api.py -q --durations=20

For Ledger commit outcomes and saved SVG isolation, also run
`tests/test_response_persistence.py` and `tests/test_storage_and_svg_api.py`.
Inject snapshot preparation, partial append, fsync and post-commit Index failures
in temporary roots. Compare recovery with old/missing indexes and preserve exact
parent CAS. Check that HTTP, stream and all lookup views retain storage failure,
keep saved work inspectable and refuse inference/branch retries. An unterminated
tail must stop append without changing existing bytes. SVG view, ordinary asset
and download routes must carry a script-free opaque-origin CSP sandbox while
preserving bytes and ordinary raster delivery. Run webserver-importing tests in
the disposable offline checkout described below.

For Index encoding and new-response parent-scan avoidance, include
`tests/test_response_index_append_cost.py`. Compare compact and legacy JSON
values, coverage digests and recovered state. Prove no parent scan for an absent
id only with a fresh complete map; retain scans for missing, stale, incomplete,
corrupt, legacy or physically replaced evidence, including same-byte replacement.
An omitted existing id must recover its parent CAS and monotonically increasing
sequence from the Ledger. Benchmark synthetic temporary maps; never rewrite or
attest production Index data as a test.

For standard SQLite Index generations also include `tests/test_response_index_default.py`,
`tests/test_sqlite_epoch_verification.py` and `tests/test_response_index_sqlite.py`
and, in the disposable offline checkout below,
`tests/test_response_index_sqlite_api.py`. Cover authenticated hit/absence paths,
exact ID scoping (a scoped map must not enumerate or prove another key absent),
AVL rotations, independently sealed coverage, self-consistent subset rejection,
missing/corrupt/replaced DB/Ledger/selector, incomplete/blocked/failed frames,
real process interruption during a transaction and after DB commit, concurrent
process parent CAS, read/write concurrency, restartable activation, reconstruction,
current-history rollback, relocated Epoch/Readiness retention and compaction.
Deleting canonical history must never turn reconstruction into empty genesis.
Readiness passes must recheck selector movement before reusing a verified map;
missing Ledger/selection with retained generations is not an empty epoch.
Verify first-write SQLite initialization, no JSON mirror or runtime fallback,
read-only missing/unmigrated roots, clear migration guidance before writes, and
current-history rollback that cannot enable JSON writes in current code. Legacy
format tests use explicitly marked temporary compatibility fixtures; normal tests
exercise SQLite. Epoch must audit every tree node and canonical entry and retain
final whole-DB hash/physical/selector guards without repeated JSON round trips.
Include node corruption outside the requested proof path: the independently
sealed post-commit DB state must invalidate that ordinary file change too.
Prove ordinary writes/reads do not invoke a whole-map digest, tree enumeration
or Ledger scan. `scripts/benchmark_response_frame_index.py` measures only
synthetic temporary roots at increasing sizes; report connection/fsync overhead,
index space and linear exceptional operations. See the
[Response Frame contract](RESPONSES_CONTRACT.md#response-frame). Do not perform production migration,
live inference or lifecycle work to validate this change.

For recursive snapshot preparation, include
`tests/test_response_snapshot_preparation.py`. It checks eliminated duplicate
preparation, byte/provenance equivalence, distinct media-file identities, changed
inputs/files, missing/corrupt repeated sidecars, and post-write verification
failure. Snapshot preparation reuse must never suppress fresh integrity checks.

For compaction-local child serialization reuse, include
`tests/test_snapshot_serialization_reuse.py` as well. It covers exact input and
normalization-policy matching, changed frame/sequence/source/epoch/map bindings,
same-byte authority replacement, fresh media and CAS verification, missing or
corrupt repeated sidecars, post-write failure, memory-budget fallback, immutable
metadata and concurrent operation isolation. Reuse changes preparation only;
root writes and every CAS check remain active.

For compaction-local size preparation, include
`tests/test_snapshot_size_preparation.py`. Only the pure JSON-safe byte-size
calculation may reuse exact private typed input bytes; split eligibility, path,
depth, sibling reservations, ref budgets, media provenance, occurrence metadata
and CAS verification still run normally. The separate 8 MiB representation budget
falls back to full preparation. Tests cover binding/policy/worker changes, unknown
inputs, immutable results, memory exhaustion and fresh media/CAS failure handling.

For epoch/map preparation changes, include
`tests/test_response_frame_epoch_verification.py`. It checks exact versus changed
entry bindings, relocated epochs, physical evidence changes during verification,
downstream map tampering, and rejection of old readiness after a successor or
same-byte file replacement. Private digest reuse must not extend file freshness.

For Readiness-pass Index reuse, include `tests/test_readiness_index_pass.py` and
`tests/test_graph_rebase_control_plane.py` in addition to those Epoch tests and
the existing observation/Registry suites. Cover complete-map proof counts,
per-response checks, Index/Ledger append and replacement, same-size/restored-mtime
corruption, stat-only guards, selection restart, missing/corrupt evidence,
process/thread/pass isolation, deterministic Registry equivalence and HTTP 409
after repeated movement. A stable pass must verify the map once without reusing
any response-specific authority. Evaluate scaling and the unchanged client timeout
on isolated valid histories; never use production Ledger/Index as writable test
fixtures or rerun the live Self-Attack corpus merely to validate this owner.

For the parsed-JSON normalization fast path, include
`tests/test_response_frame_normalization.py` with the frame, snapshot, Epoch,
Readiness observation/Registry and pass suites. Preserve canonical digests,
empty/reserved-field filtering, scalar values, mutable-output isolation, and
Mapping/Path/subclass behavior. Performance comparisons use synthetic temporary
histories or maps with identical normalized bytes; no integrity check or timeout
is relaxed.

For the finalizer's closed map ownership boundary, include
`tests/test_finalizer_closed_map_owner.py` with the Epoch, observation receipt,
Registry, frame persistence/parent-CAS/recovery, graph rebase and Readiness HTTP
suites. The test-only deep alias oracle must cover nested manifest refs, actual
returned observations, projections, Registry records, events and state summaries
while the owner is active. Prove one real first map proof and exactly two permitted
reuses; reject foreign/unadopted/consumed contexts, wrong phases/processes/threads,
physical movement and changed authority bindings. Check that reuse guards perform
only fixed metadata/stat work and that fallback, early results and exceptions
revoke the proof, including before Registry writes. Exercise diagnostics enabled.
Keep these deep test oracles out of clean benchmark runs. Preserve the ordinary
selection/hydration/retention signatures and the independent Readiness-pass
behavior. No live providers or Full Conformance are needed for this boundary.

`ResponsesApiTests` must redirect `fruth_webserver.RESPONSE_FRAMES_DIR` to a per-test temporary root. Tests must never scan or write the checkout's production `state/response_frames/responses.jsonl`. A globally fresh, coverage-verified response map may serve validated historical byte-offset hits and prove a missing response id without a ledger scan. Legacy, stale, incomplete, malformed, or corrupt coverage remains uncertain and must retain the safe full-ledger fallback. Do not weaken product timeout or state-transition limits merely to shorten this suite; first inspect duration output for missing mocks, unintended real subprocess/network work, or protected-state coupling.

For the explicit legacy-index boundary, include the `attest_response_frame_index` regressions in `tests/test_response_frames.py`. Attestation must stream rather than call `Path.read_text()` or `_iter_ledger_frames`, preserve the existing `responses` mapping exactly, reject missing ids/latest-coordinate drift/malformed rows/moving evidence without writing, and use an atomic replace only after exact verification. `scripts/attest_response_frame_index.py --check-only` is the operator preflight; tests use temporary roots or a copied temp index with a symlinked source ledger and must never attest the checkout's production index implicitly.

## Fake-Backend E2E Truth Harness

For saved-state follow-ups, run `tests/test_artifact_state_followups.py` with the
intent, inference-router, request-phase-graph, response-semantics and selected
reference owner suites. Cover exact predecessor text in both routing history and
Responses execution input; chat-only saved audio/image state; explicit fresh
media work; wrong-source/sibling evidence; changed/missing files; and immutable
parent truth. These owner checks need no model execution. The corresponding
`ResponsesApiTests.test_saved_artifact_state_followups_execute_chat_without_media_reinspection`
checks the real request path with deterministic providers, including stale media
previews, saved enrichment, exact prior text and zero new media calls. Include the
captured coordinated prohibition "Do not generate new audio or transcribe the
recording again": execution must remain chat with no new artifacts or
materialization or automatic semantic-review obligations. Cover negated and quoted STT cues and affirmative STT
after a prohibition. Also run `tests/test_inference_service.py` for saved-evidence
mentions combined with negated generation; explicit file requests must still
survive. Run these checks in a disposable physical checkout with external I/O
blocked, together with the
existing generated-image enrichment tests. Discovery probes must be fixture
isolated. Run the self-attack and shadow-corpus runner suites for client handoff
changes; completed campaign captures and verdicts must remain unchanged.

The saved-evidence fixture in `tests/fixtures/artifact_readback_audio.json`
reproduces the repeated diagnostic shape that overflowed AFM during follow-up
explanations. Keep exact source/consumer identities, digests, mismatch and negative
child verdicts while projecting shared evidence once. Its character-size check
detects diagnostic expansion; it is not an Apple tokenizer or live acceptance
test. For `saved_digest_equalities`, cover unequal byte/text representations with
a positive semantic word-match verdict, unequal same-representation hashes,
missing/malformed digests, uppercase hexadecimal values and conflicting saved
flags. Preserve original evidence and the existing context-size assertion. These
computed comparisons must not create a new semantic verdict or promote missing
evidence into proof. Run the claim-guard tests in `tests/test_response_semantics_runtime.py` too:
unsupported model prose and reserved/waived/cancelled candidates cannot create
image/audio repair obligations. Positive repair fixtures must supply an explicit
promoted obligation, not merely a capability named by the model.

For explanation completion, cover exact transcript echoes, explicit verbatim
readbacks and ordinary explanations completing without automatic review calls.
For separately contracted semantic criteria, retain malformed/failed review and
changed-answer/evidence invalidation checks, plus a positive explanation through
both branch and whole-turn review. Check that AFM's reference-only
history envelope preserves every text turn, the exact current request and system
instructions, is idempotent, and leaves other providers and typed multimodal/tool
messages intact. Include `tests/test_inference_policy_scope.py`,
`tests/test_apple_fm_backend.py` and `tests/test_semantic_review_verdict.py`.
An opt-in native replay should capture provider output and canonical output
separately. If review workers are stubbed to bound that probe, pending closure is
expected and the result cannot be reported as a completed native lifecycle test.

For selected-reference collections and retained audio handoff, run
`tests/test_frontend_reference_selection.py`,
`tests/test_frontend_message_state.py`,
`tests/test_frontend_external_multifile_transport.py`,
`tests/test_selected_reference_collection.py`,
`tests/test_selected_audio_reference_binding.py` and
`tests/test_request_intake_predecessor_context.py`. Cover n mixed/same-type
references through repeated normalization and history projection, exact
consumer input refs, ambiguous siblings, current source/Registry provenance,
path confinement, source/copy digest changes and the real infer preparation
boundary with a deterministic provider witness. Broaden with artifact/Registry,
phase graph, Late Fill, saved-file dependency, interpretive inference and fake-backend suites.
All files and source frames in these tests are temporary.

The frontend reference tests execute the actual JavaScript owners in Node VM.
Cover full-reply public text/artifacts, artifact-only replies, accumulating mixed
and same-type selections, idempotent duplicates, distinct source identities,
removal/clear and conversation isolation, snapshot reconstruction, JSON/SSE and
multipart submission. The UI-to-intake fixture must retain all exact source and
artifact bindings, a reply longer than 12,000 characters, canonical mismatch
evidence and wrong-source rejection. This verifies the request handoff without
running models; it is not a native browser or live provider conformance test.

Status-only host probes are external I/O even when inference providers are
mocked. The offline API fixtures must isolate those observations; do not allow
real model/network execution or change product status gates to pass validation.

`InferApiTests` redirects status storage and `fruth_webserver.OCR_EXPORT_DIR` to
per-test temporary paths and supplies fixture port liveness. The fake-backend
harness also supplies its own non-listening status observation; even preparation
stream tests must not probe host ports through real status bookkeeping.
Runtime-manifest fixtures supply their external-target inventory, and model
stop/start fixtures supply log-port observations. Fake Codex execution tests use
temporary synthetic executables; they must not invoke the host's installed CLI.
For public artifact selection, run `tests/test_artifact_authority.py` and
`tests/test_response_artifact_bundles.py`: an exact registered linked dependency
must preserve its logical identity, prefer current authoritative work and leave
conflicts unresolved. Include the Responses API and fake-backend E2E suites when
changing that shared projection.
Keep the real Markdown writer active in OCR persistence
checks and assert the saved path, exact bytes and output count there. Mocking
the provider and infer-history append alone does not isolate artifact writes:
successive `scan.pdf` tests can otherwise publish `scan.md`, `scan_2.md`, etc.
into the checkout's `artifacts/ocr/`. Those suffixes are filename-collision
counters, not PDF page identities. Never use historical OCR files as test
fixtures or remove them to make validation pass.

For PDF foundation changes, run `tests/test_ocr_pdf.py` on macOS with the Quartz
binding installed. Its temporary synthetic PDFs exercise real native rendering:
scanned/mixed pages, page selection/counts, rotation, nonzero crop/media origins,
annotations, crop retries, oversized-page pixel ceilings and explicit failures.
It does not perform OCR or invoke a model. PDFKit initialization requires access
to macOS application services; a restrictive process sandbox may abort before
Python can report an exception. Run native checks in a process with those services
available, keeping all documents and outputs temporary.

Run `tests/test_pdf_request_handling.py` and the PDF/OCR slice of
`tests/test_infer_api.py` in a disposable physical checkout with production state
absent and external I/O blocked. Mock status probes as well as providers. These
check native-page handoff to existing OCR, source digests, saved artifacts, mixed
text coverage, explicit controls and fresh execution for repeated incoming PDFs.
Include direct `chat` targets with image-capability metadata, single/multiple
scanned or mixed pages, full counts under page caps, exact selected transports,
per-page budgets, explicit text-first/text-only handling and visible empty-page
gaps. Apple OCR/barcode PDF checks must use fake native tools, retain source-PDF
and per-page receipt identities through canonical Responses, count verified empty
detections as processed, and reject tool/render failures without model fallback.
For direct Apple image analysis, exercise the real request builder with fake HTTP
responses: one ordered PNG per independent request, the exact prompt/instance,
and no frame instructions. Guardrail/refusal, timeout and connection failures on
the first or a later page must retain the failing page and completed coverage
through canonical error storage, preserve error status/budgets, and stop without
retry, OCR fallback or full-document success.
Keep single-image handling outside PDF preparation. The file-handoff cases in
`tests/test_codex_execution.py` and `tests/test_codex_runtime_bridge.py` verify that
file-aware agents receive original PDFs; use their fake executors, never a live
agent. These checks do not establish OCR accuracy or whole-pipeline conformance.

For PNG/SVG request typing and negative-format scope, run:

    .venv/bin/python -m pytest tests/test_inference_service.py tests/test_visual_materialization_intent.py tests/test_generated_image_artifact_routing.py -q

The generated-image routing regressions trace the exact HTML-IMAGE-SMOKE-01
prompt through candidates, promotion, obligations, phases, branches and Late
Fill eligibility. Their bounded fake-provider integration executes the real
branch preparation/execution and final materialization owners, verifies one
PNG producer followed by separate HTML/CSS files, and rejects filename/prose
as production evidence. It does not test the asynchronous scheduler or frame
persistence. All provider outputs and ledgers are temporary; no live image
generation is part of this suite. Broaden intent/extraction changes with the
interpretive inference routing, request-phase-graph and affected response-semantics tests.

The older `ResponsesApiTests` slice has an isolation limitation: direct calls to
late-fill completion outside a Flask application context can outlive per-test
patches and reach later tests as closure-repair workers. Its fixture also restores
checkout configuration files, and preview paths retain unmocked port/subprocess
probes. Do not describe this slice as fully offline or isolated merely because it
uses the Flask test client. Revalidate it in a disposable physical checkout with
production state absent and external I/O blocked; report blocked probes or leaked
worker calls separately from the request-typing regression result. Do not weaken
the runtime gates or test assertions to hide these isolation failures.

Run:

    .venv/bin/python -m pytest tests/test_fake_backend_e2e.py -q

Use this before interpretive inference self-learning changes or larger response-frame, artifact, late fill, or observer refactors. The harness patches `/api/responses` to deterministic test-only fake backends and writes only temp `artifacts/`, `state/response_frames/`, `state/artifact_registry.jsonl`, `state/chat_history/`, and `logs/` roots. Assertions are based on runtime truth fields and saved files, not model prose.

The harness also covers the current learning/healing truth boundary: fake `/api/responses` payloads must expose `runtime.request_phase_graph.intent_obligations`, local producer-before-consumer dependency edges, and structural `intent_graph_adequacy`; accepted-learning hints may surface as soft decision-contract orientation but must not create executable graph repair proposals, graph patch lifecycle truth, staged patches, or applied patches by themselves.

## Documentation and release static validation

For prose-only work, check local Markdown links and fragments, repository owner
paths, command flags and referenced config files against the current checkout.
Distinguish generated runtime paths and illustrative placeholders from shipped
files. Compare public references with `scripts/build_release_archive.py`:
`PUBLIC_DOCS`, `PUBLIC_CONFIG_PATHS`, `PUBLIC_INTEGRATION_DOC_PATHS`,
`PUBLIC_SHORTCUT_PATHS` and `RELEASE_SKILL_FILES` govern inclusion;
a file existing in a development checkout does not prove it is packaged.

The existing packaging/static checks mostly use temporary fixture source trees;
one read-only check also compares the checkout’s public `examples/` files with
the exact reference allowlist:

    .venv/bin/python -m pytest tests/test_release_archive.py -q

They validate allowlisting, exact manifest coverage, reproducibility and unsafe
archive rejection. Shortcut packaging fixtures use synthetic bytes: they check
the exact pair, preservation, missing-file errors and exclusion of unrelated
exports, including compatibility with archives that predate the pair. Before
distributing real shortcuts, separately inspect their actions and metadata and
check importability in Shortcuts. The packaging tests do not establish those
properties. They do not certify current runtime behavior or reproduce a
historical release. Inspect actual source selection as well when documenting
packaging; do not build/upload a release or run inference merely to validate prose.
No standalone repository-wide Markdown-link validator is currently provided.

Monitor entrypoint checks always exercise the packaged public script from a
separate working directory. The additional legacy local-state shim check runs
only when that development-only shim exists; public packages intentionally omit
it and report that one check as skipped. Do not add runtime state to a release
to satisfy the legacy compatibility check.

## Naming, Schema, And Prompt-Wording Changes

For docs-only public terminology cleanup, verify the glossary and active-doc search:

    rg -n "Planner|interpretive inference \\+ Planner|execution planner|follow-up generation" README.md FRUTH_INFERENCE.md FRUTH_FOR_AGENTS.md docs --glob '!docs/diagrams/**'

Expected: hits only where `docs/CANONICAL_GLOSSARY.md` names wording to avoid or where an exact compatibility identifier is backticked.

For compatibility key migrations involving resolver-named replacements for literal legacy keys, do not rely on prose review. Add or keep tests that prove dual-read and replay compatibility for request keys, runtime payload keys, late fill trigger strings, response frames, lookup payloads, and history hydration. Minimum automated suite:

    .venv/bin/python -m pytest tests/test_inference_execution_planner.py tests/test_responses_api.py tests/test_response_frames.py tests/test_working_frame.py -q -k "execution_planner or planner_timeout or planner_deferred or late_fill or response_frame or history"

For prompt or injected policy wording changes that reach interpretive inference routing, the resolver, semantic roles, or `FRUTH_INFERENCE.md`, run:

    .venv/bin/python -m pytest tests/test_inference_policy_scope.py -q
    .venv/bin/python -m pytest tests/test_inference_router.py tests/test_inference_execution_planner.py tests/test_semantic_roles.py -q
    .venv/bin/python -m pytest tests/test_responses_api.py -q -k "inference_route or inference_auto or inference_route_preview or inference_policy or runtime_policy or execution_planner or planner_deferred or late_fill"

Policy selection must cover complete ordinary-backend injection, AFM common+role
selection by the actual executor, mixed-backend cache/retry rebinding, preserved
custom-policy tails, visible malformed/missing projections, and streaming/nonstream
dispatch. AFM preparation must retain the exact workflow reference, bound only the
current task, and remain idempotent; other backends retain their existing framing.
Regression coverage must include indexed JSON image batches and malformed variants, preparation-only save/read responses in both transports, actual producer/read/consumer execution, and exact-target site repair without gallery insertion. Native preparation probes must inspect section payloads, counts and actual roles; a single saved JSON source uses raw data, and the real file-payload extractor must accept it.
Budget fixtures are estimates, not server context metadata. Record native token
counts and inspect actual content; a successful HTTP response is not semantic
equivalence or a completed reference workflow.

When a local chat-capable runtime is available, also compare a small live set: plain chat, write-then-speak, describe-then-image, selected-reference follow-up, latest-artifact edit, and each canonical semantic role selected through `semantic_role_ids`.

For structural Late Fill telemetry extraction, also run:

    .venv/bin/python -m pytest tests/test_late_fill_telemetry_extraction.py tests/test_saved_file_consumer_path.py -q

The worker fixtures inject local lookup/finalizer/fake execution dependencies and
check waves, publication order, availability identity, retry lineage, process/boot
bindings, causal-sink failure and the unchanged legacy timing-log failure path.
Save/read routing fixtures must explicitly mark their injected fake chat transport
live; do not weaken the production liveness or saved-file evidence gates.
Run API/E2E coverage in a disposable checkout as described above.

For bounded handoff/transition observations, additionally run:

    .venv/bin/python -m pytest tests/test_transition_telemetry.py tests/test_runtime_contract_knobs.py -q
    .venv/bin/python -m pytest tests/test_responses_api.py -q -k late_fill_branch_progress_updates_response_lookup_before_wave_terminal

These isolated tests cover exhausted observation budgets, paired reservation,
multiple branches/attempts, gate/result provenance, exceptions/aborts, callback
ordering and retained publication/drain waits. Persistence and hydration use
only temporary frame roots; no live-model or self-attack execution is needed.

For opt-in state-flow observation, first run:

    .venv/bin/python -m pytest tests/test_state_flow.py tests/test_transition_telemetry.py tests/test_causal_telemetry.py tests/test_response_snapshot_preparation.py tests/test_readiness_observation_reuse.py -q

Then include affected frame, lookup, readiness/registry, artifact, response
semantics and disposable-checkout API/E2E coverage. Instrumentation must preserve
canonical bytes, owner outputs/exceptions, existing checks and scheduling.
See [STATE_FLOW_DIAGNOSTICS](STATE_FLOW_DIAGNOSTICS.md) for scope bounds and
partial byte/timing coverage. No live submission is implicit in these tests.

### Research retention / candidate synchronization

For changes to Research preservation, candidate sync or Gold resolution, run:

```sh
.venv/bin/python -m pytest -q tests/test_maintenance_archive.py tests/test_clean_repo_state_policy.py tests/test_inference_reset_learning_state.py tests/test_self_learning.py tests/test_research_candidates.py tests/test_research_retention.py fruth_research/gold-core/test_validate.py fruth_research/test_review.py
```

Fixtures must use temporary runtime/Research roots. Read-only Gold validation is
separate from test execution. Real retained-evidence materialization needs explicit
authority, inventory, disk/source preflight and copied-byte verification. Never run
production cleanup, provider inference or Full Conformance to validate retention.


## Apple Foundation Models backend

For the PCC Shortcuts bridge and its normal instance integration, run:

    .venv/bin/python -m pytest tests/test_pcc_shortcut_bridge.py tests/test_pcc_vision.py tests/test_apple_pcc_backend.py tests/test_frontend_apple_pcc.py tests/test_inference_policy_scope.py -q

The focused `tests/test_responses_api.py -k pcc_responses` slice checks canonical
stream/nonstream execution evidence, rejection of unsupported public controls,
and native error messages reaching Arena's ordinary streaming Responses path.
`tests/test_backend_transport_runtime.py` checks that failed streaming HTTP bodies
survive socket cleanup, nested provider errors become readable messages, and an
empty body retains the HTTP error fallback across compatible backends.

These isolated tests never launch Shortcuts.

For PCC first-use setup, also run `tests/test_pcc_shortcut_setup.py` and
`tests/test_startup_model_manager.py`. Mock native discovery/import and isolate
runtime paths. Cover explicit setup intent, unchanged installed shortcuts,
ambiguous names, missing bundled files, import errors, pending UI status and
interactive versus noninteractive startup. Preview opening is not installation
or readiness; the ordinary start must still recheck installation.

For PCC observation boundaries, include `tests/test_backend_fabric.py` alongside
`tests/test_apple_pcc_backend.py`: cold and warm passive snapshots must never
contact Shortcuts or query native PCC metadata. Explicit discovery/start refreshes
installation evidence; cached projections retain the original observation time,
cannot mutate the owner's cache, and must not preserve success after a failed
explicit refresh.

Cover automatic Pro preference,
one Cloud fallback on a confirmed Pro access/availability error, explicit model
overrides without fallback, and rejection of refusal/unknown-error/timeout fallback.
Also cover
installation versus access, missing/ambiguous shortcuts, blank input, private
per-request staging and cleanup, operator-credential stripping, fresh UTF-8 output,
failed/blocked output, one shared timeout budget across both attempts, and no loops.
Cover real image-file staging, ordered message/attachment binding, malformed
base64/transport and remote input rejection, unchanged multi-frame bytes, native
image-error propagation, exact Pro/Cloud image digests, cleanup on every outcome,
ordinary vision dispatch, and conservative metadata for old text-only adapters.
Authorized live probes use harmless text and synthetic images in temporary files, retain CLI status
and actual returned output, and distinguish account errors from installation.
Also cover full policy and message preservation, strict buffered stream completion,
unchanged single-user text for direct chat/Arena, UTF-8, unsupported inputs/controls,
separately scoped SDK metadata, port isolation,
owned-process startup/cleanup/stop (including macOS framework Python re-exec),
normal catalog/card/tab identity and existing preferred-II selection. Authorized
browser checks use an isolated control plane and temporary registry/response state.
A shortcut round trip alone does not establish workflow conformance or content quality.

Run the isolated backend/transport, frontend identity and lifecycle slices:

    .venv/bin/python -m pytest tests/test_apple_fm_backend.py tests/test_frontend_apple_fm.py tests/test_backend_transport_runtime.py tests/test_backend_fabric.py tests/test_stack_shutdown.py -q

For default-model metadata discovery, include `tests/test_apple_fm_metadata.py`
and `tests/test_startup_model_manager.py`. Verify sourced host-default metadata,
known/future variants, positive context validation, cache reuse, missing SDK/tool,
older OS, unavailable model, malformed output and timeout fallbacks. HTTP identity
and readiness must stay independent. A native metadata check may run only the
Swift helper without generation; record its execution environment because a
restricted sandbox can return Core 3 with zero context instead of usable facts.

For AFM streaming, `tests/test_apple_fm_backend.py -k stream` verifies terminal
markers, failure/partial handling and UTF-8 decoding independent of HTTP's default
text encoding. Keep non-ASCII punctuation and names intact in Arena and direct chat.

For Apple OCR/barcode changes, include `tests/test_apple_fm_image_tools.py`,
`tests/test_session_controls.py`, and the Apple image-mode cases in
`tests/test_infer_api.py` / `tests/test_responses_api.py`. Verify native transcript
call/result linkage, exact tool text, original versus re-encoded image digests,
empty detections, skipped/mismatched calls, private staging cleanup and bounded
process failure. Use synthetic OCR/QR/blank images for live CLI/browser checks in
disposable state. Check canonical receipt persistence, not model prose alone.

Broaden to existing Ollama/MLX/llama.cpp manager tests, startup, session controls,
chat/infer APIs, shared frontend, runtime hygiene and fake-backend conformance
when those owners change. Live tests require explicit lifecycle authority and a
disposable checkout/state root. Never use production registry/artifact paths.
Browser acceptance includes two-instance creation, exact selection, streaming,
stop-one/survivor, reload, prerequisite errors and failed startup. Report actual
interpretive-inference context failures separately from successful direct chat;
do not shorten policy or substitute a provider to turn the check green. Detailed
observations and limits are in [Apple AI](APPLE_FOUNDATION_MODELS.md).

For image transport changes, include `tests/test_infer_api.py` and the vision/image
attachment cases in `tests/test_responses_api.py`. Verify internal image-part
aliases normalize to inline `image_url` parts without changing image bytes or
history order, the exact selected instance receives them, PDF pages use that
backend, and malformed/unsupported parts fail visibly. Browser acceptance must
include an attached synthetic image and canonical response evidence. AFM 3 model
research does not prove public audio access: keep TTS/STT unsupported unless its
actual transport and the existing audio evidence contracts are validated.

`tests/test_image_input_formats.py` covers raw image media types and uploaded
JPEG/PNG bytes through chat and vision analysis to the selected Apple transport.
Include uppercase and misleading filename extensions, explicit data URLs,
unchanged prompts and saved input digests. These offline checks use synthetic
fixtures and a fake completion backend; they do not measure model accuracy or
prove that a particular live backend decodes every image format.
