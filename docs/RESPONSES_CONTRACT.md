# Responses Contract

This document names the response-state fields that are part of Fruth's runtime truth contract. It is intentionally narrower than general product docs: it describes what callers and UI code may rely on.

## OpenAI-shaped compatibility boundary

Fruth exposes `/api/responses` and `/v1/responses` through its local response
handler. This is a supported local contract with an OpenAI-shaped text
compatibility surface, not complete OpenAI Responses protocol support or a direct
call to OpenAI's hosted API. `fruth_services/responses.py` owns the text adapter.

HTTP callers must follow the [local caller admission contract](HTTP_API_BOUNDARY.md):
mutations and explicit-refresh GETs require `X-Fruth-Action: 1`; configured Host
and exact browser Origin are checked. This covers JSON, multipart, streaming,
`/v1` and local-provider aliases. The marker is a browser safeguard, not native
process authentication or an operator credential.

- Text normalization accepts `prompt`, string `input`, and text message content.
  Role-bearing message items currently preserve their role when explicitly typed
  as `{"type": "message", "role": "developer", "content": "..."}`. The standard
  role/content form without `type` is not faithfully normalized: it can become
  user content. This is a known compatibility limitation, not a desired change
  in instruction authority.
- A complete function/custom-tool round trip, `function_call_output` handling,
  OpenAI Conversations resources and `previous_response_id` semantics are not
  implemented by this adapter. Unsupported input may be ignored rather than
  rejected. Do not infer support from an endpoint name or backend feature flag.
- Local `conversation_id`, response frames and Late Fill retain Fruth semantics.
  Canonical `outputs` and lifecycle/closure truth are distinct from compatibility
  `output`, `output_text` and `status`. The text-output builder's zero token usage
  values are placeholders, not measured zero consumption.

Fixing role handling, rejecting unsupported items, changing completion/usage
semantics or extending tool/provider compatibility requires a separate code and
contract change. Client integrations must validate the subset they actually use.

## Retrieval for clients

`GET /api/responses/<id>` (also `/v1/responses/<id>`) returns a bounded UI view by
default. Poll an existing response with `?view=status` for compact lifecycle and
Late Fill observation; `compact=true` and the compact/observer view aliases also
select that surface. Explicit `?view=full`, `?view=raw` or `?view=truth` retrieves
full response truth when `compact` is not enabled. `?view=debug` remains bounded.
Fetch exact details or artifact content when needed, not the entire response on
every poll. Pending work is observed under the same response id, never restarted
by posting its prompt again. The detailed projection rules below remain binding.

Compatibility `output_text` may mirror a downstream canonical output. Rebuilding
the display from compact slots must not assign that text to the preparation slot
when an existing completed output already binds it to another owner. Slot-local
text, matching canonical outputs and branch fill results remain independent
evidence; equal wording alone does not collapse separately owned outputs. This
holds without hydrating the omitted role/dependency sidecars.

## Response Frame

Explicit inline/embedded implementation formats (for example embedded CSS or
inline JavaScript) do not request additional file artifacts. An explicitly named
separate stylesheet or script remains a separate output request.

Local page-image inference requires visual asset cues outside quoted data.
Generic version/variant nouns alone do not supply those cues; rendering a JSON
version field in HTML does not request an image. Explicit image work retains its
own admission and dependency requirements.

An affirmative file-creation header also governs adjacent named file
specifications (for example, “Create two files. note.txt must contain notes.
status.json must contain data.”). This is file authority, not JSON response
formatting. Quoted examples, source/reference descriptions, negation and an
intervening independent instruction do not acquire that authority. Affirmative
named commands such as “Create note.txt. Create status.json.” also retain their
file duties when followed by “Do not create other files”; a generic file noun
is not required in each creation command. Recognition uses the existing local
polarity and literal boundaries and does not grant execution permission.

Materialization deferral is category-scoped. The compatibility field
`prompt_intent.explicit_defer_materialization` records the presence of a defer
instruction; it is not by itself a global stop. `materialization_defer_scope`
retains global materialization, generic file, and canonical text-extension scope.
Image/audio decisions retain their existing category fields. An exclusion of SVG
or audio cannot stop unrelated requested text files or remove saved-file dependency
edges. Matching deferred file obligations retain their identities and unresolved
Closure checks; they are not silently waived or fulfilled. Older graphs without
scoped evidence retain their compatibility interpretation until rebuilt.

A relative generic-file exclusion (“do not create other/additional/extra files”)
keeps `files=true` with an optional `file_exceptions` version 1 record. Fresh
caller analysis resolves that record from recognized affirmative media counts
and exact text-file requests. It is an eligibility ceiling, not output admission:
planner/provider text cannot add targets or counts, and branch-local payload,
reservation, dependency and current execution checks still apply. Explicit
category/format deferral and a separate blanket file ban take precedence. With
no recognized permitted outputs, the exclusion permits none. Named text requests
use the existing file-intake grammar, including explicit file-creation headers.
Older readers conservatively honor `files=true`; newer readers do not infer
missing or unknown-version exceptions from historical effective prompts. Existing
frames are not migrated or rewritten. Recovery uses their recorded scope; a new
caller request can establish fresh scope after an older false block.

Accepted current-turn file promises remain in `request_phase_graph.intent_obligations`
when a later detector, planner, or response graph contains fewer requests. Graph
rebuilding retains their exact file and branch/phase/dependency identities from
the same-prompt runtime graph; newer explicit waiver/supersession records remain
visible. A smaller derived set is not a release. The composed Closure owner uses
the existing terminal saved-file evidence check for accepted named obligations;
counting other text artifacts cannot fulfill a missing filename/type. This does
not add general semantic or literal-content validation for plain text files.

A request to read a saved file and derive a named output from those read bytes
is stronger than a dependency on preparation text. For a unique newly requested
text producer and named text consumer, the bounded grammar builds
`artifact_request.saved_file_dependency` (version 1), with exact producer and
consumer branch/phase ids, output requests and a consumer-local instruction.
The consumer depends on the producer phase. Both branches are excluded from
text-artifact coalescing. Planner deferral retains their file contracts; graph
rebuilding reuses the same exact file owners and branch/phase identities. Ambiguous or unsupported recognized dependencies keep
`branch_contract_error=saved_file_dependency_unbound`; existing files and model
claims cannot discharge that gate.

The supported grammar is deliberately limited to separate clauses (sentence,
semicolon or newline boundaries): an earlier `save/store/write/create` or
`speichere/schreibe` clause with the producer filename; `read/reread/re-read` or
`lies/lese` with a saved/stored/persisted or gespeichert/gesichert cue; then
`create/generate/write/build` or `erstelle/erzeuge/generiere/schreibe`, a named
consumer, and `from/using/based on` read/data/file cues or `daraus/aus den
(gelesenen/eingelesenen)` cues. A named read or format cue must match the
producer; an unnamed read must be unambiguous. Negated clauses do not grant
execution authority. Trailing consumer constraints and standalone prior
self-contained/embedded/external-resource constraint clauses are retained,
without replaying the producer task or root prompt. Later independent action
clauses, structured joins, retained inputs, binary inputs and external executor
consumers are outside this positive path. This is not general natural-language
file-execution support. `Create a new file named data.json ... and save it`
is supported by the named `create` clause; this does not add general pronoun
resolution or new file-executor verbs.

Late Fill captures `saved_file_output_snapshot` after the producer's actual
materializer returns a saved file, then binds it through the existing canonical
artifact identity owner. The dependency owner uses the existing authorized
saved-artifact path resolver, opens a stable regular file, and reads at most
90,000 bytes (the existing complete revision-input bound). Inputs and observed
outputs must be nonempty valid UTF-8; no truncation, replacement decoding or
fallback data is allowed. The SHA-256 is computed from the same bytes as the
input, which are stored losslessly as `utf8_base64` in
`execution_contract.saved_file_read_evidence`. This avoids whitespace changes
by generic contract normalization. Typed `input_refs` retain the exact artifact,
response, producer, consumer, path and digest binding.

Immediately before internal chat invocation, Late Fill revalidates the saved
version and input binding. The prepared prompt must equal the bounded
bytes-derived prompt; a changed/truncated prompt fails rather than bypassing
normal preparation limits. Only the consumer's one output request is admitted.
A successful invocation with a saved, correctly targeted output records
`saved_file_consumption_evidence` with the contract, captured read, submitted
input digest and output snapshot. This is runtime handoff evidence, not a
model's assertion or a general guarantee of semantic output quality. The
isolated positive test independently computes its output from that submitted
input.

New caller captures opt into `content_requirement_policy=named_saved_text_v1`.
The policy applies only when this existing unambiguous named text producer →
saved read → named text consumer path is admitted. The graph and each existing
artifact request retain separate producer and consumer `content_requirements`:
stable branch/phase and requirement identities, exact accepted clause text, its
SHA-256, and one review criterion per group. This does not parse arbitrary prose
into a general semantic verifier. Other responses do not acquire this review gate.

Technical snapshot, source binding, syntax and saved-output checks retain their
existing meanings. They cannot discharge these content groups. Closure requires
an accepted current branch semantic review (or an already-authorized applicable
waiver/supersession) before marking the groups covered. Missing or inconsistent
accounting on a newly governed request remains explicitly unresolved, even if
all artifact checks pass. Unverified content is not thereby incorrect.

The existing branch-review owner prepares the exact requirements and actual
saved output content; the consumer packet also includes its bound saved source.
Coverage requires complete content within the existing 16,000-byte semantic
artifact excerpt budget, including requirement metadata. Truncated or omitted
content and a digest alone are insufficient. Late Fill preserves this packet
through dependency gathering and verifies its instruction digest before dispatch.
Acceptance joins settled branch identity with the actual accepted fill result,
current generation binding, and the existing strict verdict/criterion contract.
Changed requirements, source or output invalidate the prior review. A completed
summary or queued instruction alone is not accepted review evidence.

Branch review instructions lead with the reviewed branch's accepted output,
content duties and complete semantic criteria. The packet's
`accepted_branch_scope` attributes sibling duties to their own branch/phase
identities as context, using accepted contracts rather than filenames or reviewer
prose. Applicable shared constraints remain attached to the reviewed branch.
Stable logical duty fields keep reviewer admission/completion bookkeeping from
changing the generation by itself; actual evidence and contract changes retain
the existing invalidation rules. Context labels do not expand valid evidence
references. Negative, uncertain and incomplete verdicts retain their blocking
meaning even when saved files independently look correct. This presentation
change does not establish live reviewer soundness.

New caller captures additionally record
`content_review_reference_policy=packet_exact_v1`. Only the named saved-text
content-review path uses this rule. Its runtime-owned packet includes
`evidence_reference_catalog.allowed_refs`: exact, unambiguous aliases of the
supplied branch/phase, complete saved output, bound complete source, and accepted
requirements. Artifact refs, paths/names and supplied source artifact IDs retain
their existing spellings; no registry lookup or inferred alias expands the set.
The instruction states these forms explicitly, and the catalog/instruction are
part of the existing generation digest. The review binding records
`evidence_reference_policy=packet_exact_v1` without changing its existing policy
identifier or the verdict schema version.

Every verdict-level reference and every reference on a passed required criterion
must resolve within that exact packet. Required criteria need nonempty refs.
Ordering and duplicates are allowed. Exact strings and `ref`, `id` or
`name` envelopes are supported in arrays when all identity fields resolve to the
same evidence; a criterion may also use a single exact
string. Surrounding whitespace retains existing normalization. Unknown, mistyped,
ambiguous, stale, malformed or out-of-scope refs reject the entire review for
completion, including mixed valid/invalid lists. No fuzzy matching, citation
repair or accepted-subset fallback occurs. Original returned text and reference
declarations remain available, with per-entry rejection locations and reasons.
The accepted request retains this policy independently of downstream graph and
result metadata, so missing review labels cannot downgrade governed work. Missing
or inconsistent required evidence remains unresolved. Correct technical artifacts
stay available; existing manual-review/recovery authority and budgets still apply.

Canonical request frames preserve the explicitly captured
`content_review_reference_policy` through persistence and caller-intent restoration.
An absent historical request policy remains absent; restoration does not infer it
from graph metadata, model output, successful results or current defaults.
Supported Late Fill controls restore their finalizer request from the current
canonical frame inside the existing response mutation boundary. A missing or
plain top-level request projection therefore cannot erase captured provenance,
original caller scope, separate preparation text or saved policy identities.
Bounded observation projections and claimed provenance in plain mappings cannot
override that canonical source. If the canonical request or original-intent
evidence is unavailable, it stays unavailable; controls neither backfill older
frames nor gain root-reconstruction or scheduling authority.

Restored pre-reference-policy requests and frozen reviews retain their original
interpretation, including historical nonempty-reference acceptance. This rule
does not recertify past completion. Exact reference validity establishes evidence
membership only; a false positive with legitimate refs remains an A2 reviewer-
soundness limitation.

Review execution uses existing Closure promotion, routing and attempt budgets.
Unavailable capacity or insufficient packet coverage leaves verification work
unresolved for attention, without availability polling or regenerating good
artifacts. Covered branch criteria do not independently create a duplicate global
review; other whole-turn review signals retain their authority.

Closure and its compact surface retain `completion_basis`,
`content_coverage_status`, `content_requirement_count`,
`unresolved_content_requirement_count`, and `correctness_basis`. Canonical frames
retain the full groups, bindings and verdicts through ordinary CAS persistence;
compact views may omit detail but retain this accounting. A bound positive review
can be wrong: `completion_basis=bound_semantic_review` explicitly depends on
reviewer soundness and is not independent proof of correctness. No new waiver,
parallel store, compatibility-key replacement or saved-file dependency version
change is introduced. Restoring a historical frozen request does not add this
admission policy or rewrite its prior completion decision; absence there means
this coverage was not recorded.

Early existing-file fulfilment, missing-result fallback, Closure, and terminal
branch reconciliation use the same strict saved-file evidence validator:
exact producer and consumer records, artifact identities, captured-byte digest,
input digest, saved output and current versions must agree. Missing, malformed,
unauthorized, ambiguous, changed or misbound evidence remains unmet. Identical
bytes at another artifact identity are not aliases. Evidence is preserved by
ordinary response-frame storage and read-only hydration; no historical frame
is migrated or retroactively credited with a read.

After a producer's exact snapshot, artifact identity and current bytes pass
validation, its named-file closure check stays bound to that verified path.
Earlier streamed drafts with the same logical filename cannot make that binding
ambiguous or substitute for it. Any explicit contracted target must agree;
filename, extension and saved-content syntax checks still apply. Work without
an exact proven producer binding retains the ordinary ambiguity checks.

An early saved file does not discharge a producer or consumer branch without
that branch's required snapshot or consumption evidence. Missing evidence keeps
the branch eligible for its normal dependency-gated execution. Reusing a proven
result preserves its complete evidence record; ordinary file reuse and its
existing syntax-repair rules remain available for branches without a saved-read
contract.

When Closure repair projection changes the executable branch identity, its
promoted contract retains the originating identities and records an
`execution_binding` with the exact contract, branch and phase ids. Terminal
settlement checks that binding and the target artifact identity, and retains
the binding in resolved-contract evidence. Legacy contracts without this field
keep the existing exact-identity comparison; observation does not retrofit
bindings or rewrite historical frames.

`response_frame` is the frozen response snapshot. It is immutable once written. Late fill and recovery do not edit an old frame; they produce successor lookup payloads and, outside tests, successor frame ledger entries.

For direct image analysis, `runtime.vision_input_evidence` retains the runtime
dispatch receipt (source image SHA-256, byte size and exact instance). A current
vision phase can complete from generated text plus this matching receipt;
provider prose or a missing/mismatched receipt alone cannot establish image input.

Important surfaces:

- `response_frame.request`: the request snapshot used for replay/audit.
- New runtime-captured requests retain original caller intent and native output
  scope here, with `intent_source = runtime_caller_capture_v1`. A different
  `execution_prompt` is preparation for the authorized backend, not another
  instruction or output grant. Caller/model fields with these names cannot
  supply the runtime's private in-process capture. Canonical recovery restores
  that distinction; ordinary public `prompt`/`input` precedence is unchanged.
- `response_frame.planning.artifact_flow.work_tree`: internal work truth.
- `response_frame.planning.artifact_flow.output_slots`: slot projection from the work tree.
- `response_frame.output.outputs`: canonical public output projection.

Frame ledger rules:

- The first persisted frame for a response id is `frame_relation.kind = initial`.
- A later persisted state for the same response id is a typed successor frame with `parent_response_id`, `parent_frame_id`, and `parent_frame_sequence`. Ordinary continuation normally uses `frame_relation.kind = late_fill_successor`. Bounded graph relations are not interchangeable: `graph_patch_reopen_successor` is executable only after exact terminal-owner revalidation; `graph_patch_terminal_review` is audit-only; `graph_rebase_stage_successor` is durable audit-only; and `graph_rebase_partial_successor` is executable only for the exact registry-trusted, gate-approved branch-local continuation. Full, staged-only, stale, widened, untrusted, or gate-blocked rebase records remain non-executable.
- Every appended frame for the same response id must have a unique monotonic `frame_sequence` and matching `frame_id` such as `resp_x:frame-1`, `resp_x:frame-2`, `resp_x:frame-3`. If a live payload still carries stale successor metadata, persistence rewrites the append metadata so the new ledger fact links to the latest prior frame instead of reusing an old frame id.
- Successor frames are new audit facts. They do not mutate the original frame and must be distinguishable during replay.
- Late Fill producer/consumer result truth is also typed. A TTS producer records the exact final backend prompt and SHA-256 as `tts_semantic_source`, and every produced PCM WAV receives deterministic `tts_audio_integrity_evidence` bound to that source and file. HTTP 200, a readable WAV header, or non-zero file size is transport/artifact-existence truth only. Audio fulfillment additionally requires sufficient effective active-signal duration for the source and acceptable silence/trailing-padding ratios. Failed or unavailable integrity keeps the physical file and registry record as diagnostic evidence, marks it non-materializable, blocks the audio obligation, and requests branch repair. Its directly dependent STT consumer records `tts_stt_semantic_evidence` against that one bound source. Missing, drifted, ambiguous, or mismatching evidence blocks fulfillment with dependency-chain repair even if an audio artifact and transcript exist; expected source text is never supplied to STT.
- `runtime.tts_semantic_regeneration` is additive attempt evidence for the named one-regeneration TTS policy. Each producer entry binds `failed_attempt_id`, a distinct `attempt_id`, `repairs_attempt`, consumed budget, original failed result/verdict, replacement result and verification outcome. The same branch/phase remains the original obligation; the repair execution/artifact identities are distinct. Failed original media is withdrawn from current public outputs but retained in audit evidence. Only a replacement accepted by the unchanged verifier may satisfy the audio obligation. A consumed entry is persisted and read back through the existing frame/CAS mechanism before invocation; restart never treats an uncertain in-flight attempt as a fresh budget. Readback must prove the exact appended frame and equality of the complete reservation in the frame owner’s canonical durable representation, including zero remaining budget and attempt/artifact lineage; omitted empty metadata is compared using that same established serialization. No old frame or historical suite result is rewritten.
- `response_frame.current_state` is the compact current lookup snapshot captured inside that frame. It is recovery data for `/api/responses/<id>`, not permission to rewrite the frozen frame.
- Persisted ledger rows are compact audit facts. Large internal snapshots such as full `runtime`, `working_frame`, request-phase graphs, context candidates, planner diagnostics, bulky semantic-review state, work trees, large request inputs, and oversized planning contracts may be moved into sidecar JSON files under `state/response_frames/snapshots/`. Sidecars are content-addressed by SHA-256, so separate semantic refs such as `runtime` and `current_state.runtime`, `planning.request_phase_graph` and `planning.artifact_flow.request_phase_graph`, or repeated work-tree projections may point at the same physical file when their payloads are byte-identical. Large nested runtime/working-frame subtrees are split into their own `*_snapshot_ref` entries rather than summarized; the parent snapshot keeps the ref structure, and the child sidecar keeps the full raw subtree. The ledger keeps machine-readable `*_snapshot_ref` / `external_snapshots` entries with path, SHA-256 digest, byte size, and JSON path. This preserves truth without duplicating multi-megabyte internal state in every successor row.
- Successor ledger rows delta-log external snapshots against their parent frame. `external_snapshots.items` on a persisted successor contains only new or changed refs for that row; unchanged parent refs are listed under `external_snapshots.inheritance` and omitted from the row-local `items`. Recovery/replay merges the parent manifest before returning the current response view. When a recovered frame exposes both effective and row-local truth, `external_snapshots.items` is the effective merged manifest and `external_snapshots.delta_items` is the successor row's own diff.
- Sidecar snapshots may themselves be compact CAS manifests. Large worthwhile child fields such as request-phase graph nodes/edges, context candidates, decision/semantic contracts, graph-closure reviews, dependency evidence, branch/result collections, and work-tree structures can be replaced inside the sidecar by child `*_snapshot_ref` entries when they exceed the split threshold. This is ref-splitting, not summarization: child sidecars keep the full content, and snapshot readers expand those refs for replay/recovery.
- Recursive child splitting reuses the parent's private media-normalized JSON subtree within that snapshot write. Independent snapshot writes normalize their inputs anew. Every child still receives its own path/lineage metadata, content hash, and current sidecar-byte verification. Within one compaction, recursive child writes may reuse immutable normalized/serialized bytes only after comparing the exact freshly split input and normalization policy and rechecking the same private frame, sequence, storage directory, ledger, and index bindings. Root snapshots still normalize/serialize independently. Changed or unprovable bindings, new inputs, and exhausted preparation memory use the full transformation path. This preparation reuse does not cache file integrity or change publication ordering.
- Within one compaction, pure JSON byte-size preparation may also reuse exact typed, ordered private input bytes under the same frame/storage/policy/worker binding and a separate 8 MiB memory budget. This reuses only the size calculation: split eligibility, JSON path, depth, sibling reservations, ref budgets, media normalization and current CAS verification still execute. Unknown inputs or exhausted memory take the full preparation path.
- `working_frame` ledger sidecars are logic-only vessels. They keep small orchestration state such as `status`, pending ids, closure/loop state, and compact route/request summaries inline, while graph, contract, prompt, input, context-candidate, and artifact-flow bodies are represented by child `*_snapshot_ref` entries. The child sidecars remain full diagnostic truth.
- `outputs[]` and `output_slots[]` are handle projections. They keep `artifact_ref`, slot/status/type/order, and compact recovery fields, but must not inline artifact dossiers, prompts, provenance, metadata, `image_state`, paths, or nested `artifacts[]` once an artifact ref exists. Full artifact identity, provenance, metadata, and enrichments live in the artifact dossier snapshot and registry.
- Diagnostic snapshot hashes exclude volatile timestamp keys such as `created_at`, `updated_at`, `started_at`, and `completed_at` for graph/contract/context/work-tree sidecars. Those timestamps are bookkeeping metadata, not diagnostic content identity; frame/index metadata remains the operational time source, while the snapshot hash represents stable diagnostic content.
- Persisted frames use one selected derived SQLite Index generation for current-state recovery. New roots initialize it through the frame writer; existing JSON histories require explicit lossless migration before ordinary writes. Passive reads never create or migrate storage. `current_index.<generation>.sqlite3` is selected through `current_index.active.json`; JSON remains inactive backup/migration input or explicit current-history rollback/export for older code. The compact JSONL Ledger remains durable recovery truth. JSON v2 binds the complete map to EOF/count/map digest. SQLite uses a complete authenticated AVL root and a small independent metadata seal bound to exact physical Ledger identity, EOF, count and ordered row-hash coverage. A scoped inclusion/absence proof validates the exact requested ID and cannot enumerate or prove another ID absent. Entry-local sizes remain historical append facts; decoded rows still validate exact response/frame identity and SQLite source-row bytes. Legacy, incomplete, stale, malformed, corrupt, replaced or unpublished coverage cannot establish lookup authority by assumption. Canonical recovery retains its Ledger fallback and returns the latest valid frame or truthful not-found/corrupt-Ledger state.
- Within an explicit legacy JSON export publication, a freshly coverage-verified map may supply private normalized siblings to the updated map; the complete updated map is hashed and published. SQLite publication updates one entry and its AVL ancestors transactionally after Ledger fsync, then atomically seals the new coverage checkpoint. It does not rewrite a JSON mirror. Normal SQLite persistence retains exact parent CAS and frozen successor lineage; rollback/export preserves current canonical history for older code. Interruption between Ledger commit, DB commit and selector publication leaves uncertain coverage; reconstruction uses committed canonical rows without duplicating them or executing work.
- Complete epoch verification reuses its already verified map digest for the private rebound copy only when every entry's ledger path and name remain exactly unchanged. Any changed binding, including equivalent path spelling, gets a newly computed digest. The full ledger scan, final physical ledger/index checks, and subsequent selection, hydration and registry binding checks still execute; no verification result is cached across calls.
- A complete legacy v1 map gains JSON-v2 coverage through the explicit operator command `.venv/bin/python scripts/attest_response_frame_index.py`. Use `--check-only` first. It streams the physical Ledger, verifies the exact response set/latest coordinates, preserves entries/manifests and atomically adds only coverage fields. Explicit SQLite migration applies that legacy preflight plus canonical reconstruction/tree verification; passive reads never migrate. Active SQLite attestation performs complete Epoch verification without rewriting the generation. Malformed rows, mismatches or moving evidence reject.

Wire projection and canonical truth are deliberately separate:

- Successful non-streaming `POST` responses and `GET` views `default`, `ui`, `status`, and `debug` are byte-budgeted public projections. The final serialized outer envelope is at most 8 MiB, including retry/control/status wrappers; each serialized Responses-style SSE event is held to the same ceiling. The normal indexed POST/default/UI/status projection does not hydrate sidecars. Bounded debug reads may hydrate selected Closure/rebase observation sidecars; exceptional ledger recovery may reconstruct canonical state before projecting a bounded result.
- Public compaction is byte-based, not a fixed character or item-count cut. Ordinary 5,000-character text and collections of 65 tiny records remain intact when they fit the budget. Bulky strings at or above 256 KiB and collections at or above 1 MiB may instead expose a bounded preview plus exact length/count, byte size, SHA-256, and an adjacent content-addressed `*_snapshot_ref` for the complete value.
- `view=full`, `view=raw`, and `view=truth` are exact canonical reads. They may exceed the public wire budget because they recursively restore the complete content-addressed sidecar graph. Every authoritative ref is recursively validated for its declared CAS identity and content before it is exposed; a missing, malformed, or corrupt ref fails closed with HTTP 409 instead of returning partial canonical truth.

This is truth by reference, not semantic summarization. The public wire may carry handles, previews, counts, and digests, while exact bytes remain recoverable from the referenced CAS graph without semantic loss.

`GET /api/responses/<id>` returns the current UI response view by default. It may come from live lookup state or, after lookup TTL expiry/restart, from the latest valid persisted frame for that response id, but the default projection must stay frontend-safe: lifecycle/status truth, output handles, artifact cards, display text, and compact late fill state are included; raw `response_frame`, `runtime`, `working_frame`, work-tree, graph diagnostics, and large repair/debug payloads are not. Recovered default views still carry compact recovery provenance through status fields such as `status_lookup`, `frame_id`, `frame_sequence`, and `state_version`. When no usable live record exists, missing or corrupt durable truth produces a not-found or corrupt-ledger error. An existing live record can still supply a bounded fallback; that does not establish durable recovery or permit invented fulfillment.

Non-streaming `POST /api/responses` and `POST /v1/responses` attempt canonical frame persistence before serializing the response. Unconfirmed `not_committed`/`uncertain` outcomes return an explicit storage failure (503, or 507 for a reported full disk) with a frame-bound `persistence` receipt. A confirmed Ledger commit survives failed Index publication and remains recoverable from the Ledger. Their normal wire result is projected from the current indexed compact ledger row: public lifecycle/status, output handles, output slots/branches, artifact handles, display text, frame identity, and the effective content-addressed snapshot-ref manifest remain available, while hydrated `runtime`, `working_frame`, and repeated full-frame bodies are not copied onto the wire. This projection is read-only and performs no sidecar hydration. If the durable row is not yet available, a bounded in-memory fallback keeps small compatibility payloads inline and replaces large internal bodies with clearly audit-only digest identities; the fallback retains the persistence outcome and does not confirm durability or claim replay authority. Explicit canonical reads remain available through the truth views below. See the [finalization boundary](#finalization-and-durable-completion) for failure, stream and recovery semantics.

`GET /api/responses/<id>?view=status` returns the compact observer view for an existing response. It is for polling and UI state updates, not artifact copying. It exposes canonical lifecycle truth, open late fill branch state, compact surface/recovery state, and a `state_version` that changes when the observable response state changes. Clients should poll this compact view while work is open, fetch the default UI view only when `state_version` changes or artifact/detail handles are needed, and never start a duplicate `/api/responses` request just to check whether the original work finished. File contents for copy/open/show-all actions should be resolved from artifact entries and targeted artifact endpoints, not by pulling raw response-frame debug truth.

`GET /api/responses/<id>?view=debug` returns a bounded developer observation. It combines the indexed compact frame and all effective snapshot refs with only the selected graph-rebase, Closure, scope-ladder, and candidate-review evidence needed by rollout diagnostics. It does not hydrate unrelated work trees, artifact bodies, graph nodes, or recursive diagnostic children. `?view=full`, `?view=raw`, and `?view=truth` remain the explicit canonical diagnostic lookup and recursively hydrate expanded response frames, runtime graphs, working frames, closure reviews, repair feedback, and other large truth payloads. UI code must not use any of these developer/operator views for normal rendering or reconciliation; exact CAS/replay/operator clients must use `truth` or `raw`, not bounded `debug`.

When present, `status_lookup` is a compact status companion inside the response lookup payload. It should carry the same lifecycle/status semantics used by the compact observer so clients can render state without inferring from assistant prose, stale slots, or compatibility `status`.

`fruthctl` makes the wire/truth split explicit. `send ... --json` performs one bounded `POST /api/responses` and prints that public wire result. `send ... --truth-json` performs the bounded POST, then reads the same response id through exact `view=truth` and emits a normalized canonical summary. `responses get <response_id> --json` returns the raw canonical truth-view payload, while `--truth-json` emits its normalized summary. `--json` and `--truth-json` are mutually exclusive for each command.

Artifact registry split:

- Response frames carry output refs and compact artifact dossiers for replay/recovery.
- Output registration consumes the attached current response frame's accepted
  `artifacts.output` identities, including an empty accepted set. Earlier
  top-level projections and last-saved-path shortcuts cannot replace that set or
  mint replacement refs. Without an attached frame, explicit artifact records
  take precedence over compatibility shortcuts for the same saved path/type.
- `state/artifact_registry.jsonl` is the durable lookup surface for concrete artifacts across modalities. New output artifacts from `artifacts[]`, `saved_text_path`, `saved_text_artifacts`, `saved_audio_path`, and `saved_image_path` are persisted with `roles = ["output"]`, `artifact_ref`, path, type, provenance, metadata, and linked response ids. True external user inputs are persisted with `roles = ["input"]`.
- Reused Fruth artifacts are references, not new inputs. Route reuse, selected reference artifacts, artifact bindings, and registry-known paths must carry stable refs/bindings and must not be re-materialized as fresh `input_artifacts`.
- In the UI, **Reference Reply** selects the public reply text and its referenceable canonical artifacts together, including replies containing only artifacts. Multiple public text outputs remain in order; internal diagnostics and non-public work do not become reply content. Individual artifact selections accumulate, repeated selection of the same identity is idempotent, and selecting another reply preserves already-selected files. The current selected message and every selected artifact travel in `reference_artifacts` through preview, JSON/SSE, multipart and request snapshots.
- Selected references retain `artifact_ref`, `artifact_id`, `source_response_id` and available branch/phase/slot/obligation identities. These are lookup addresses; client text or metadata does not prove a binding. The existing canonical source/artifact verification remains authoritative. A source supplied by an artifact is preserved when it differs from the containing reply. Selection is conversation-scoped, and removal or clearing changes only the selected context.
- Explicit selected reply text is preserved in full at intake, including beyond 12,000 characters; the generic artifact-content preview limit is not applied to that message. Normal provider context and request limits still apply. Referencing a reply or file does not grant permission to repeat its original work or generate replacement artifacts.
- Modality-specific provenance wins over generic output provenance. For example, generated-image provenance remains attached to the image artifact and generic output registration may add lookup metadata or linked responses without downgrading that provenance.

Response artifact bundle operations fail closed on incomplete wire projections. A previewed, truncated, or emergency handle set is not enough to choose bundle contents: bundle creation resolves and recursively hydrates the exact CAS-backed response truth first. Missing, malformed, or corrupt refs return HTTP 409 instead of producing a silently incomplete bundle.

Artifact fulfillment rules:

- Canonical Late Fill image selection qualifies candidates against the exact
  accepted result and its response/source, branch, phase, obligation, producer,
  artifact identity and saved path before binding, ref lookup or fallback.
  Matching labels, an explicit slot ref, physical existence and equal bytes do
  not replace accepted-result evidence. Missing or competing accepted identities
  keep the image output unresolved. Rejected candidates remain dossier diagnostics,
  including conflicting claims under an accepted ref, and cannot become public
  fulfillment during repeated finalization or recovery. Existing verified reuse,
  physical path aliases, direct outputs and other modality owners retain their
  existing gates; this is not a global cross-response artifact prohibition.
  A compact lookup uses accepted result evidence in its same frozen frame when
  the bounded status overlay omits it; compact ledger results retain artifact and
  source identities. A completed-branch summary cannot override an execution
  result's rejection. Older unbound/batch completed projections retain their
  established compatibility contract. Physical availability stays with its
  existing validation owner; this pure projection check does not stat files.
  Qualification uses the frame owner's image type aliases and output-type-only
  records too; an alternate image spelling cannot bypass accepted evidence.
- Model prose, Markdown code blocks, prompt lists, or chat text are evidence, not fulfilled file artifacts. They fulfill a requested file only when runtime materializes the file and records it in output slots, `outputs`, `artifacts`, response-frame truth, or artifact registry truth.
- A prompt for an image is not the image artifact. A script for audio is not the audio artifact. HTML/CSS prose is not a saved page unless materialized as files.
- Linked artifact sets close only when concrete saved files point to their concrete saved dependencies. Placeholder names, guessed paths, stale paths, wrong relative links, or missing CSS/image references are open artifact-binding problems.
- A page background color does not imply a hero/background image placement requirement. Hero placement checks distinguish image-specific request language from color styling; existing hero regions and ordinary concrete image links retain their binding checks. A correctly linked HTML image does not require a duplicate CSS image reference merely because the stylesheet sets a background color.
- Template-style asset variables such as `IMG_PATH_1`, `IMAGE_URL_2`, or `ASSET_REF_3` are linked-artifact placeholders. When concrete artifacts already exist, terminal rebind should replace those variables with correct relative artifact links before closure instead of regenerating duplicate assets.
- When concrete artifacts exist but are not linked, recovery should prefer deterministic rebind or bounded repair against existing artifacts before declaring failure or creating duplicate page files.
- If the user requested an exact artifact count, a smaller count remains incomplete unless Closure records an explicit waiver or supersession.

Generated-image `image_state_enrichment` is optional artifact evidence, not the image artifact itself and not proof of artifact closure. `status=pending_existing` means another background worker already owns the same image path; `status=skipped` should carry a reason such as `downstream_vision_analysis` or `required_artifact_closure_priority` when enrichment was intentionally suppressed to avoid duplicate or lower-priority analysis.

Status semantics:

- Top-level `status` is compatibility-facing OpenAI-style state. It may remain `completed` once the first answer is returned.
- `lifecycle_state` is canonical for continuation, late fill, and branch truth.
- First-party runtime and UI code must not treat `status = completed` as terminal when `lifecycle_state` indicates active continuation. Active continuation is explicit, not prefix-based: `late_fill_pending` and `late_fill_running` keep polling/execution active.
- Actionable repair/control states such as `blocked`, `repair_needed`, `late_fill_repair_needed`, `repair_branch_contract`, `repair_dependency_chain`, and `rebuild_from_promoted_obligations` are diagnostic/control states. They must not show running/queued spinners unless a separate active execution state is present.
- Terminal or frozen states such as `late_fill_failed`, `late_fill_completed`, `completed`, `failed`, `cancelled`, `waived`, `superseded`, `skipped`, and `frozen` are non-polling. Failed late fill may still expose recovery candidates or failed branch diagnostics, but it is not an open continuation.
- Responses expose `canonical_status_field = "lifecycle_state"` and a machine-readable `status_semantics` object. When compatibility status and canonical lifecycle split, `status_compatibility = true`.

Example compatibility split:

    {
      "status": "completed",
      "lifecycle_state": "late_fill_running",
      "canonical_status_field": "lifecycle_state",
      "status_compatibility": true,
      "status_semantics": {
        "compatibility_status": "completed",
        "canonical_lifecycle_state": "late_fill_running",
        "canonical_status_field": "lifecycle_state",
        "status_compatibility": true,
        "has_open_continuation": true,
        "has_actionable_repair": false,
        "is_terminal": false,
        "terminal": false
      }
    }

Blocked naming note: runtime uses plain `blocked` as the canonical lifecycle value for blocked late fill/current-state lookup. Older docs or compatibility payloads may say `late_fill_blocked`; clients should treat that as a compatibility alias for blocked repair/control truth, not as active late fill execution.

## Finalization and durable completion

Semantic completion, durable persistence and response delivery are distinct
boundaries. Closure compares saved outputs and exact dependency evidence with
the preserved original obligations. It may repeat during reconciliation and
repair. A frozen frame can record fulfilled, pending, blocked or failed work.

Before terminal link repair, Runtime prepares an eligibility view from accepted
current Late Fill results, artifact identities and output slots using the same
preparation as frame construction. This view is local to link repair; it does not
publish outputs, freeze or persist a frame. It repeats after deterministic
saved-file repairs, before the final link and Closure checks. An earlier pending
output projection cannot hide newly
accepted media, and an older fulfilled frame cannot override a current rejected
or empty public output set. Existing dependency selection, unique public-media
fallback and ambiguity checks still govern rebinding; saved bytes alone do not
publish failed or cancelled work.

The finalizer in `fruth_webserver.py` constructs the frame and reconciles public
artifact identities, then attempts Artifact Registry persistence from that
frame's accepted output set. The frame writer in
`fruth_services/response_frames.py` prepares and verifies CAS sidecars, appends
and flushes/fsyncs the Ledger row under the append lock, then atomically publishes
the derived Index. Parent compare-and-swap checks remain mandatory where the
successor path requires them. These stores are not one atomic transaction: an
Index failure can occur after the Ledger row is durable, and canonical recovery
must retain its ledger fallback.

After a confirmed Ledger commit, the finalizer may retain a relevant
settled graph-rebase Readiness observation. This pass remains synchronous before
finalizer return, but is after canonical durable persistence. A concurrent lookup
can therefore see the durable terminal successor before Readiness or the finalizer
finishes. Readiness failure is secondary evidence failure: it neither rolls back
the frame nor grants or removes semantic completion. Its diagnostics and final
completion timings do not retroactively rewrite the persisted frame.

The native writer reports an additive, frame-bound `persistence` receipt to the
finalizer. It is delivery metadata, outside the frozen frame: a row cannot attest
its own subsequent fsync or Index publication. Its `status` distinguishes
`not_committed` (no row append began), `uncertain` (append/flush/fsync did not
return a confirmed outcome), and `committed` (Ledger flush/fsync and any new
Ledger/parent-directory names were confirmed). `index_status` separately reports
`published`, `failed`, or `not_attempted`; `artifact_registry` separately reports
its publication outcome. A confirmed Ledger row with failed Index publication
retains its exact frame identity and normal read-side Ledger fallback. Do not
append the same work again to repair its Index.

Unconfirmed persistence raises a typed finalizer error. The HTTP response is
507 for a reported full disk, otherwise 503, with
`error.code=response_persistence_failed`, `retryable=false` and
`recovery_action=inspect_response_persistence`. The live outer response becomes
`incomplete`/`blocked`; its candidate frozen frame, semantic Closure and existing
outputs remain available for inspection. Status, UI, debug and full lookup retain
that storage outcome. Streams emit `response.failed`, and Late Fill stops without
classifying storage failure as a model failure or scheduling a branch retry.
Explicit branch retry also rejects an unresolved storage outcome. Passive lookup
does not erase uncertainty merely because bytes are readable from the OS cache.
An operator must inspect the exact frame/Ledger and restore storage before
continuing; repeating the original inference request is not storage recovery.
Parent-CAS mismatches keep their existing rejection semantics.

Before append, the writer rejects an unterminated final Ledger record with
`response_frame_ledger_unterminated_tail`. This includes valid JSON missing its
physical newline: no new record may be concatenated onto it. Existing bytes and
the Index remain untouched. This is a controlled stop, not an automatic repair:
preserve the original Ledger/tail and recover a validated copy under explicit
operator authority before further writes. Read-only lookup never truncates,
quarantines, rewrites or repairs historical state.

Older recovered frames and non-persisting projections may have no write receipt.
Neither receipt absence, HTTP success, `persist_effective`, a frame-shaped object
nor lifecycle alone proves a fresh commit. Durable-completion claims still need
the matching Ledger/frame identity, valid referenced CAS and saved artifact
evidence. Storage confirmation does not establish semantic fulfillment.

Readiness's Epoch is a verified source binding, not an execution epoch or an
incrementing permission token. The verifier binds the physical Ledger/Index,
complete map, latest frame identities and source-row digests. Selection,
hydration and registry append still check current bindings. Relocated archived
epochs may contribute verified evidence through explicit retention/sync; they
cannot authorize current execution. The evidence registry and trusted operator
registry are different stores with different authority.

On a pre-append physical epoch mismatch, `readiness_epoch_moved` includes bounded
`epoch_retention` diagnostics: expected/observed Ledger and Index device, inode,
size in bytes, and mtime/ctime in nanoseconds, plus every changed-field reason.
Paths and available frame/verified-epoch identities are metadata only; oversized
identity/path values are omitted explicitly. The retained Index entry is labeled
`verified_index_entry`, never presented as a fresh current entry. Current byte
equality and mutation attribution remain `unknown` without bound evidence.
The existing error log carries the detail, with best-effort causal telemetry and
observer process-boot identity when available. The guard reuses its stat captures;
after a Ledger mismatch it also captures the otherwise short-circuited Index stat.
It performs no diagnostic content reads or hashes. Diagnostic failure preserves
the same rejection, and successful retention emits no mismatch diagnostic.

A private, single-use Readiness observation may avoid a second JSON hydration
only after rechecking the same response/frame/map/epoch, physical files, indexed
row bytes and every consumed sidecar's current bytes and integrity. A changed,
missing, corrupt, relocated, consumed or untrusted candidate takes the normal
loader or fails its existing gate. This receipt is never persisted or exposed as
public authority, and registry validation/deduplication still runs.

## Request Phase Graph

`runtime.request_phase_graph` is the request obligation graph. Its user intent is anchored by interpretive inference and the current turn, but its state may be refined before freeze from runtime evidence.

Graph refinement is allowed only when it continues the same request intent. It must not invent a new task because an older turn or generic history mentioned an artifact.

Runtime captures the actual request after permitted canonical predecessor/input
promotion and before planner rewriting. Graph rebuilding, artifact requests and
text writing use this captured current intent and accepted explicit scope;
backend execution still receives the prepared payload. A scalar planner prompt
cannot create an extra file, change an output count, waive owed work or broaden
source delegation. Later branches retain their own accepted payload and output
contract rather than replaying the root request.

Additive refinement diagnostics:

    {
      "graph_refinements": [
        {
          "source": "assistant_output_claim",
          "capability": "text_to_speech",
          "reason": "assistant_output_explicitly_claimed_pending_materialization"
        }
      ],
      "prompt_intent": {
        "refined_from_output_claim": true
      }
    }

When this happens, synthesized branch records may carry:

    {
      "branch_id": "branch-text_to_speech-1",
      "capability": "text_to_speech",
      "source": "assistant_output_claim_refinement",
      "refinement_source": "assistant_output_claim"
    }

This is a closure-safety mechanism for an already-promoted current-turn obligation. A pending/queued assistant claim can expose an underrepresented branch, but the claim alone cannot promote a reserved, negated or merely inferred modality. Runtime still validates authority and materialization before treating the obligation as fulfilled.

## Candidate Graph And Promotion Review

`candidate_graph` is the visible possibility layer. It may contain outputs, workload tasks, context/reference/memory candidates, evidence candidates, repair candidates, continuations, learning hints, and rejected proposals.

`promotion_review` is the boundary that turns a candidate into a promoted contract or leaves it reserved, omitted, waived, rejected, or stale. Only promoted contracts are owed work. Reserved or candidate-only items are state, not pending failures.

Additive repair rejects reservation/deferral only from structured disposition
records bound to the proposed work's exact branch/phase, obligation/contract or
candidate/promotion identity. Explicit phase/branch aliases and candidate-to-contract
links preserve that binding. Diagnostic prose, scope labels, field names and
unrelated disposition records cannot reserve an already accepted duty. This
inspection grants no promotion or application authority.

The canonical lifecycle is:

    possibility -> relevance -> promoted contract -> runtime work -> review -> freeze

When a candidate is promoted into executable work, the runtime should also carry the branch-scale workload task truth where available:

    {
      "task_id": "task-phase-2",
      "branch_id": "branch-image_generation-1",
      "capability": "image_generation",
      "input_refs": [{"kind": "phase_output", "ref": "phase-1"}],
      "output_contract": {
        "output_type": "image",
        "required": true,
        "status": "planned"
      },
      "lifecycle": {
        "policy": "prepare_execute_verify_freeze",
        "recursive": true,
        "scope": "branch_local",
        "cycle": [
          "prepare",
          "gather_evidence",
          "execute",
          "verify",
          "repair_or_freeze"
        ],
        "stages": [
          {"stage": "prepare", "status": "pending"},
          {"stage": "execute", "status": "pending"},
          {"stage": "verify", "status": "pending"},
          {"stage": "freeze", "status": "pending"}
        ]
      }
    }

The `stages` array remains compatibility state. The `cycle` field is the general branch-scale workload contract: every subtask can prepare focused inputs, gather dependency evidence, execute, verify against its output contract and review criteria, then either repair or freeze. `decomposition_level` is descriptive graph depth and is not a fixed small execution cap.

## Late Fill

`late_fill` records continuation of obligations already present in the request phase graph. It must not create a new user intent.

State rebuilds carry accepted results and the admitted execution envelope through
pending, running and terminal checkpoints. This includes terminal Closure repair
and partial-rebase identities as well as graph-patch successor identity. Carrying
an envelope does not admit new work or bypass the current-frame, execution and
branch-control checks. A completed terminal repair handoff must not dispatch again
when its branch completion evidence is recovered.
One terminal or cancelled member does not complete another exact admitted pending
member of that execution. An explicitly activated handoff may continue the latter
through the normal gates. Foreign/unbound work and stale pending copies of an
already terminal branch do not reopen the execution.

Terminal repair projection retains promotion on a new matching output obligation
only when the promoted runtime repair contract, its exact execution binding and
the accepted additive patch agree. The obligation retains the repair-contract and
graph-review identities. Required/pending labels, missing proof, foreign identities
and provider claims do not supply promotion; existing historical obligations are
not backfilled by projection or passive recovery.

Terminal materialization refreshes current artifact/output projections and new
results. Previously accepted `fill_results` retain their original content,
digests and execution identities even when a later authorized repair replaces
the same file. History does not become a new submission or confer execution
authority; current repair results still pass the publication target checks.

If terminal Closure replaces a repair's executable branch with a bounded
materialization branch, the exact replaced contract is retained in the repair
loop's `superseded_contracts`, with its replacement identity. It is no longer
counted as another executable duty. This records a transfer, not fulfillment:
the replacement must pass graph admission, execution and Closure. Unrelated
contracts sharing a target remain separate obligations.

Historical frames without `request.intent_source` remain readable audit truth.
Their saved effective prompt is not evidence of original caller authority. Retry
may continue an existing accepted branch under its exact local contract and
dependency gates, but cannot reconstruct new root obligations or fall back to
that prompt when local work is missing. A persisted legacy root payload may still
be hashed solely to reject root replay in the existing operator-authorized partial
rebase guard; it is never promoted to intent. Successors retain missing evidence,
and passive recovery does not rewrite old frames. This compatibility rule does
not retroactively certify the admission of historical obligations.

Late fill executes branch-local contracts. The focused prompt or payload for a branch can come from `content_payload`, `artifact_prompt`, `stage_direction`, dependency artifacts, artifact dossiers, prior branch outputs, vision evidence, transcript evidence, or other promoted input refs. It should not fall back to the full original multi-step prompt when a branch-local task is available.

Core fields:

- `status`: `pending`, `running`, `completed`, `partial_failed`, `failed`, or `skipped`.
- `pending_branches[]`: branch obligations that can still be materialized.
- `completed_branches[]`: branch obligations with runtime evidence.
- `failed_branches[]`: branch obligations that failed with structured diagnostic truth.
- `fill_results[]`: successful materialization attempts.
- `error`: display-safe aggregate error text when the overall late fill failed or partially failed.
- `skip_kind`, `skip_reason`, `skip_source`: present when `status == "skipped"` so "no work needed" is not confused with a failed or suppressed continuation.
- `recovery_candidates[]`: branch-local recovery options discovered by failure analysis. Candidates are inert unless explicitly promoted.
- `auto_recovery_enabled`: currently `false` for generic recovery candidates. This does not disable separately Closure-promoted auto-executable repairs or the named bounded image, TTS and vision recovery policies; their exact contracts and gates still decide scheduling.
- `repair_action` / `repair_actions`: optional Closure Repair classification for the active gap or pending repair branches.

The initial pruning pass delegates each decision to the private
`LateFillRuntimeOwner._initial_late_fill_branch_eligibility` helper. It receives
the ordered branch's current payload/gap, existing Late Fill evidence, current
terminal ids and legacy terminal capabilities, the original pending sequence's
capability counts, and the existing capability-gap builder. Its internal result
is `excluded` for missing capability or already-accounted terminal state,
`fulfilled` for qualifying evidence with at most one pending branch of that
capability, or `pending` otherwise. Required text, images and other capabilities
retain their existing evidence owners. Gap/evidence evaluation still occurs
before the duplicate guard. The caller records fulfillment immediately so later
decisions see that update, then retains the surviving records in order. These
internal decisions add no public fields or authority; dependency batches and
active selection continue to own scheduling and resource/availability policy.

Image pruning uses canonical saved evidence for the exact accepted branch, with
matching phase/obligation identities when declared and current artifact authority.
An earlier image or a shared capability alone cannot fulfill another image duty.
Equal bytes do not make two duties the same; independently owed operations retain
their local instructions and result bindings. Existing qualifying evidence may
still skip execution. Earlier `fill_results` remain available through subsequent
execution and already-fulfilled/no-work states, finalization and durable recovery.

For an exact graph-patch successor execution, an accepted terminal callback retains
its complete result envelope, branch/output bindings, canonical saved evidence and
error provenance. Repeated status-only, partial, empty or conflicting callbacks
cannot erase or replace those facts, including through result-field projection,
frame construction and recovery. `updated_at`, `timing` and `scheduling_policy`
may receive operational enrichment. Changed parent, graph or scheduled-scope
identities cannot replace that execution. A different execution can become current
only after the existing successor admission/version/acceptance gates publish its
exact execution record; old/foreign callbacks cannot select it. Fresh authorized
repair remains possible, with the earlier frozen frame and execution retained.

UI surfaces should treat `pending_branches`, `active_branches`, `completed_branches`, `failed_branches`, and `fill_results` as branch-state truth before older slot projections. Slots are still useful for layout and artifact identity, but a stale pending slot must not keep showing queued when the matching branch is completed or blocked.

Branch control, retry publication and worker checkpoints share a response-scoped
mutation boundary in `ResponsesRuntimeOwner`. Prepared worker results remain
candidates until publication rechecks the current frame id/sequence, execution
binding and target disposition under that boundary. It stays held through frame
commit and live publication. Current live controls within the same frame are
carried into the candidate before result revalidation, preserving normal sibling
cancellation processing. A changed durable version rejects the candidate.
A stale worker rejects its candidate with `stale_result_rejected`
diagnostics; saved physical artifacts remain inspectable but are not accepted
outputs. A control whose admitted target changed returns HTTP 409 with
`response_mutation_conflict`; a fresh control with no pending/active target still
returns 404. HTTP 200 cancellation cannot be replaced by that stale worker.

After those checks, a control restores the request from the current canonical
frame, applies the exact disposition and rebuilds Closure with the ordinary
assessment owner before freezing its successor. Checks, coverage, counts,
semantic-review/repair diagnostics and the corresponding surface projections
describe the same accepted evidence. An accepted sibling review remains covered;
disposing a separate review task supplies no review evidence or disposition of
its underlying content requirement. Assessment failure prevents that control
publication. This assessment does not invoke a model, materialize repairs or
activate continuation. Historical missing caller authority/policy remains absent,
and passive reads return the saved assessment without refreshing it.

A legitimately scheduled, still-live worker may then attempt one guarded handoff
through the existing Late Fill release-then-schedule seam. This continues its
existing admitted execution; it does not admit work or mint an execution key.
The private invocation context retains the original promoted scope, exact local
contracts/request, submitted IDs and consumed one-attempt allowance. Only a newer
committed exact user-control frame with unchanged execution, graph, unaffected
contracts and accepted evidence qualifies. The rejected result is never accepted.
An accepted sibling S remains accepted; cancelled T remains cancelled; independent
still-pending P may run only if it was never submitted in this invocation chain.

The child revalidates after winning the existing claim, at entry, before dispatch
and at acceptance. Scope is a dispatch filter; other pending obligations remain
visible. Local instructions and accepted dependency bindings remain exact. Missing
local/dependency evidence blocks progress; a direct local prompt does not waive a
declared dependency. No root/assistant fallback or first-pending dependency bypass
is allowed in guarded mode. Evidence types without a qualifying existing owner
predicate remain pending. In particular, the materialization predicate used here
qualifies image and required text artifacts; it does not establish audio-producer
dependency integrity. Existing normal execution and failed retry remain unchanged.

The allowance is spent on qualification, including denial or unsuccessful
scheduling. Duplicate submission/entry is inert, a losing claimant releases
nothing, submission failure releases its own claim, and a successfully started
child exclusively owns cleanup even if later tracing fails. A second conflict
stops the child. Cancellation after logical dispatch cannot recall physical
provider work, but still prevents stale acceptance. Passive reads and recovery
never schedule; process-context loss ends this permission. Pending-only retry
still returns 409. There is no durable resume queue, new endpoint or UI action.
Existing availability polling remains conditional on finite provider/capacity and
scheduling assumptions, with no new total waiting deadline.

C9 captures the exact frame's canonical request at admission and compares it with
the current exact frame's canonical request. It retains full equality, including
caller policy, provenance and unknown fields. Live/wire request carriers do not
replace that source. Re-freezing an already compacted request preview preserves
its original omission audit when no further projection occurs; new detail still
passes through the existing compaction owner. This preserves audit provenance
without excluding preview fields from the continuation comparison.

For a guarded child, a dependency branch alias resolves only through one current
accepted graph phase and its exact completed branch identity. Ambiguous aliases,
conflicting completion identities and unpromoted candidates do not make work
ready. Ordinary scheduling retains its existing wave ordering.

An exact accepted branch semantic review may quote original intent as bounded
review evidence. Runtime verifies its promoted repair and accepted graph patch,
local execution contract, instruction/generation binding and freshly derived
Closure evidence before allowing that exact instruction through the root-replay
guard. Review labels and self-consistent hashes alone are insufficient. The
exception applies only to the instruction's prompt/content carriers, never to
other root-bearing fields, widened execution scope or partial/rebase successors.
It creates no continuation permission and changes no result-acceptance gate.

This boundary coordinates threads of one control-plane process, including its
claimed worker and progress callbacks. It does not serialize independent
responses or claim support for multiple control-plane processes writing the same
response. Provider calls and terminal materialization run outside it. The lock
registry is held only to retain/release a response lock, never while waiting.
Acquisition order is response mutation, then short lookup/stream or existing
artifact/frame storage operations, then the frame writer's SQLite lock. Worker
claim acquisition/release remains separate; no provider wait, join, or lock
acquisition from an already-held lookup/claim/storage lock is allowed. Existing
append locks and exact successor parent CAS remain independent requirements.

Availability selection happens inside the dependency-ready batch, before resource
priorities. Work without a recorded availability wait is considered first; if
only waits remain, the oldest due `next_check_epoch` group is considered first.
The selected group still passes through the existing image/helper resource guards.
`scheduling_policy.availability_selection` may report `ready_before_wait_rechecks`
or `oldest_due_waits`, with `availability_deferred_branch_count` for candidates
outside that group. These are scheduling diagnostics, not new execution authority.
Current dispatch and next-wave `active_branches` use the same selection rule;
waiting obligations remain pending with their exact identities and attempt counts.

Failed branch shape:

    {
      "branch_id": "branch-image_generation-2",
      "phase_id": "phase-3",
      "capability": "image_generation",
      "output_type": "image",
      "status": "failed",
      "error": {
        "code": "INSTANCE_UNAVAILABLE",
        "message": "image backend unavailable",
        "stage": "execute_prepared_branch",
        "retryable": true,
        "exception_type": "RuntimeError"
      },
      "attempt": {
        "stage": "execute_prepared_branch",
        "capability": "image_generation",
        "instance_id": "flux-2",
        "backend": "ollama",
        "model": "x/flux2-klein:latest"
      },
      "recovery_context": {
        "can_retry": true,
        "retry_scope": "same_branch",
        "suggested_action": "retry_excluding_instance",
        "preserve_intent": true,
        "exclude_instance_ids": ["flux-2"]
      },
      "recovery_state": {
        "kind": "fruth.late_fill_recovery_state",
        "status": "candidate",
        "trigger": "late_fill_failure",
        "branch_id": "branch-image_generation-2",
        "capability": "image_generation",
        "promotion_required": true,
        "auto_execute": false,
        "preserve_intent": true,
        "retry_scope": "same_branch",
        "suggested_action": "retry_excluding_instance",
        "failed_instance_id": "flux-2",
        "exclude_instance_ids": ["flux-2"]
      }
    }

Allowed `recovery_context.suggested_action` values are:

- `manual_review`
- `start_compatible_instance`
- `retry_excluding_instance`
- `retry_same_branch`
- `repair_dependency_chain`
- `rebind_dependency_evidence`
- `repair_branch_contract`
- `rebuild_from_promoted_obligations`
- `semantic_review`

`repair_dependency_chain` means the failed branch is missing an input artifact from an upstream phase, so repeating the same branch would repeat the graph error. The next recovery step must repair or promote the dependency chain before the branch is executable again.

`rebind_dependency_evidence` means the dependency artifact or evidence already exists in runtime truth but is not bound to the blocked branch. The next recovery step should bind the existing evidence to the branch-local contract instead of regenerating or asking for the same input again.

`repair_branch_contract` means the branch is under-specified or failed contract validation before it can safely execute. `rebuild_from_promoted_obligations` means closure review found that the graph planned too little work for the current intent, so the workload/obligation layer needs repair before execution. Repair-created pending branches should preserve `execution_contract`, `workload_task_ref`, `output_obligation_ref`, `input_refs`, `review_criteria`, and `output_contract` where available.

`semantic_review` means the output exists but qualitative review criteria remain unverified by deterministic runtime truth. Today this is advisory review work unless promotion policy explicitly turns it into an executable verifier branch.

Closure repair feedback may include:

    {
      "repair_loop": {
        "kind": "fruth.repair_loop",
        "status": "candidate",
        "authority": "runtime_review_promoted",
        "auto_execute": false,
        "repair_work_available": true,
        "round": 1,
        "max_rounds_policy": "bounded_runtime_repair_policy",
        "next_actions": ["repair_dependency_chain"],
        "requires_promotion": true
      }
    }

This candidate loop frame is not an autonomous retry. It tells clients and repair policy where the next bounded repair round would start. When Closure promotes a concrete executable repair contract, `repair_loop.auto_execute` may become `true`; that means the promoted repair branch is schedulable through late fill and may remain open until its bounded automatic repair budget is exhausted. The default budget is controlled by non-UI policy `FRUTH_AUTO_EXECUTABLE_REPAIR_MAX_ATTEMPTS`, and branch/repair-contract metadata such as `auto_executable_repair_max_attempts` can provide a more specific budget within the safe cap.

Late fill gates repair branches before backend execution. A `repair_dependency_chain` or `rebind_dependency_evidence` branch without dependency artifacts or prior branch evidence becomes a blocked failed branch with `DEPENDENCY_CHAIN_REPAIR_REQUIRED`. A `repair_branch_contract` branch without a bounded `execution_contract` becomes a blocked failed branch with `BRANCH_CONTRACT_REPAIR_REQUIRED`. These blocks apply to target materialization, not to the whole repair loop. Response frames should surface `materialization_blocked`, `blocked_scope`, `blocked_prerequisite`, `repair_work_available`, `repair_work_policy`, and `needs_external_input` so clients know whether Fruth can still repair the missing prerequisite locally. When the required dependency evidence or execution contract is present, the corresponding block flag is resolved and the bounded branch can run. These are repair states, not backend retries.

## Output Slots And Outputs

The admitted delivery-only per-image inspection family carries
`structured_output_contract.mode=separate_image_reports_v1` on its final text
branch. Its required bindings name each accepted analysis branch/phase and image
producer branch/phase. Runtime deterministically delivers those existing public
reports in source order, with one contribution per source. It revalidates image
identity/bytes, the existing vision input receipt and report digest at preparation,
dispatch and Closure. `report_delivery_evidence` persists these bindings; public
text must equal the complete rendered contributions. Missing, duplicate, foreign
or substituted contributions leave Closure open even if synthesis text exists.

Admission is conservative: an explicit separate visible-image inspection clause
with no additional terminal transformation receives this delivery contract.
Comparison, summary, translation and other distinct writing duties retain their
execution contracts. Existing frozen contracts remain readable without adding
new historical duties. Delivery coverage does not certify visual-description
truth or explain an earlier live model's omission.

Slots are presentation truth tied to work truth. They should stay compact and reference branch-local diagnostic truth instead of duplicating it.

Canonical output rules:

- Work-tree output nodes are the internal source of output slots when a runtime-owned `planning.artifact_flow.work_tree` is present.
- Slot/work-tree/promoted-obligation outputs are canonical public truth and should carry `source = promoted_output_slot` plus `compatibility_derived = false`.
- Fallback outputs assembled from `output_text`, `content_payload`, or stray artifacts are compatibility projections only. They should carry `source = compatibility_derived` plus `compatibility_derived = true`.
- Runtime consumers must not treat compatibility-derived outputs as proof that a promoted obligation was fulfilled. Use output slots, work-tree nodes, branch state, artifact refs, and closure/recovery state for that decision.

When a truth guard rewrites or annotates an unsupported artifact claim, the
correction must survive canonical output selection, frame persistence and
retrieval. Optional `runtime.truth_guard.text_projection` binds that correction
to its output identity and the source/corrected text hashes. Only stale mirrors
of that output are corrected; independent branches, artifact-backed content and
later results keep their own values. This projection grants no execution or
fulfillment authority and does not rewrite historical frozen frames.

Work-tree ownership rules:

- Runtime-owned work trees are authoritative when present and response frames snapshot them. They are marked with `work_tree_source = "runtime_owned"`, `authoritative = true`, and `compatibility_derived = false`.
- `output_slots` are derived from that work tree; they should not silently replace it with prose, legacy `outputs`, or artifact fallbacks.
- For legacy payloads without a runtime-owned work tree, the frame planner may still build a `derived_planning_snapshot` for compatibility. That fallback is marked `authoritative = false` and `compatibility_derived = true`; it is not deeper truth than an explicit runtime work tree.

Blocked slot shape:

    {
      "slot_id": "output-phase-3",
      "branch_id": "branch-image_generation-2",
      "phase_id": "phase-3",
      "type": "image",
      "status": "blocked",
      "blocked_reason": "image backend unavailable",
      "error_ref": {
        "branch_id": "branch-image_generation-2",
        "code": "INSTANCE_UNAVAILABLE",
        "stage": "execute_prepared_branch"
      },
      "recovery_context": {
        "can_retry": true,
        "retry_scope": "same_branch",
        "suggested_action": "retry_excluding_instance",
        "preserve_intent": true,
        "exclude_instance_ids": ["flux-2"]
      },
      "recovery_state": {
        "kind": "fruth.late_fill_recovery_state",
        "status": "candidate",
        "trigger": "late_fill_failure",
        "branch_id": "branch-image_generation-2",
        "capability": "image_generation",
        "promotion_required": true,
        "auto_execute": false,
        "preserve_intent": true,
        "retry_scope": "same_branch",
        "suggested_action": "retry_excluding_instance",
        "failed_instance_id": "flux-2",
        "exclude_instance_ids": ["flux-2"]
      }
    }

Top-level `outputs[]`, `output_slots[]`, and `output_branches[]` should preserve `blocked_reason`, `error_ref`, compact `recovery_context`, and compact `recovery_state` so UI and API consumers can render status and offer explicit recovery.

## Text Artifact Payloads

Text/file artifacts are materialized outputs. Before either direct Responses or
selected-file/internal Infer persists provider-derived text, the shared phase
acceptance owner must accept its substantive payload. For example:

    {
      "output_obligations": [
        {
          "type": "artifact",
          "name": "README.md",
          "mime_type": "text/markdown",
          "content_payload": "# Local Canvas\n\n..."
        }
      ]
    }

One safe substantive `content_payload` may be unwrapped and materialized under
the accepted output contract. A control envelope containing only `content`, or
multiple competing payloads, remains repairable and causes no output writes.
The lower-level extractor's ability to parse a wrapper is not phase acceptance.

Valid JSON is classified by its envelope keys: mentioning an internal field name
inside ordinary JSON content does not make it control data. An object whose sole
key is `response` and whose value is another object transparently wraps that
envelope; arbitrary named children such as `example` remain ordinary data.
Actual control envelopes, including escaped keys, retain the substantive-payload
checks above. For incomplete JSON-like text, a control name must occur in object
key position to trigger the guard; quoted values and ordinary bracketed prose
are not control keys. This permits ordinary fenced JSON followed by prose while
keeping malformed/truncated control-key objects repairable. Acceptance as phase
text grants no execution or fulfillment authority, and is not JSON syntax validation.

Provider filename, MIME type, fence language and target claims cannot override
an explicitly accepted logical filename, extension, target or output count.
Explicit `.txt` remains `.txt`. Only an admitted generic save with unspecified
name/format and no target permits bounded format derivation. Generated storage
prefixes and collision suffixes preserve the existing logical naming convention.

Required-file fulfillment checks the physical saved path and logical identity
against the accepted branch/output contract, including when no target path was
supplied. Conflicting returned metadata or output digest evidence cannot make a
different readable file fulfill that contract or qualify for canonical reuse.
The root Responses saved-result handoff validates every relevant returned
declaration against the caller/source contract captured before execution, before
canonical artifacts can discard name, extension, target or output-digest claims.
`text_artifact_saved_evidence` retains the accepted contract, raw declarations
and rejection error through artifact registration, physical metadata refresh,
frame persistence and canonical recovery. Input-attachment digests remain
separate from output-record digest evidence. Rejected files remain inspectable
diagnostics while the original obligation stays unresolved.

Canonical reuse reconciles same-output declarations before ranking or deduplication.
A clean duplicate cannot hide a contradiction in either record order. Existing
response, frame, provenance and branch identities distinguish unrelated historical
or reference evidence; differing aliases or declared digests alone do not create
a new output version. A canonical reuse projection is an alias, not a fresh write.
Fresh validated work may resolve the duty through the existing write, revision,
dependency and repair gates while retaining the earlier rejection as diagnostic
evidence. Physical bytes matching the request do not silently clear a rejected
declaration.

Exact target revisions still require their current-branch write proof; saved-file
consumers still require the bound producer/read identities and digests. Neither
text claiming a save nor an existing wrong file is completion evidence.

A saved-read consumer's one bounded syntax repair preserves its original
`saved_file_dependency` and content requirements. The separate version-1
`artifact_request.saved_file_syntax_repair` binds the original logical consumer
to exactly the rejected physical target, complete target snapshot, file identity
and deterministic defects. Preparation combines that packet with a fresh verified
read of the unchanged producer. Dispatch rechecks source identities/version,
target bytes/identity/defects, exact prepared prompt and authorized output request.
The combined prompt uses the existing 90,000-byte saved-input bound, without
truncation. The repair grants no sibling-target authority.

Repaired consumption records the repair packet and new input/output digests;
ordinary consumption evidence cannot certify that replacement. The logical
consumer contract remains authoritative, and changed output needs a current
consumer content review before Closure can complete. Recovery preserves this
evidence through the existing canonical frame and artifact owners.

Terminal link applicability is consumer-specific. The existing
`local_visual_asset_binding` and `shared_css_binding` contracts identify owed
producer links through the consumer's branch/phase and declared source identities.
A required link stays open when omitted entirely, or when its saved producer is
missing, foreign, unpublished or ambiguously bound. A response-wide rebind candidate
pool, a file extension, an ordering edge or shared preparation does not create a
link duty. In particular, `saved_file_read_required` proves consumption of saved
data; it does not require a backlink to that data file.

Actual saved local references retain their existence and binding checks. Owed
links resolve from the bound consumer through its saved linked dependencies;
disconnected sibling content cannot satisfy them. A stylesheet carrying the
page's visual cohort may use that same page's links only when the page actually
links the stylesheet and owes the same producers. A JSON image-path manifest
remains its own consumer. Terminal validation uses the private current accepted
output projection also used by rebinding; normal finalization still owns public
handles and frozen frame lineage. These are derived checks over existing records,
with no persisted-format change or reconstruction of missing historical authority.

Ambiguous deictic requests such as "make this HTML" need a selected source, current payload, or explicit reference before persistence.

A bare pronoun in a later sentence may refer to one explicitly named text
artifact requested earlier in the current turn, for example "Create styles.css.
Use it for the page background." During preparation, this binding requires the
matching required text-artifact successor in the resolved current phase graph;
an absent, reserved, disconnected or differently named target does not supply
the source. A declaration derived from missing external input does not ground
that input. This is an input binding, not evidence that the file exists.

Final materialization includes open canonical image/audio output obligations as
well as text artifacts. Pending, blocked or failed media cannot be omitted merely
because its closure check uses `final_output` without repeating `requires_artifact`.
Fulfilled, waived and superseded obligations remain closed; references in HTML
and successfully saved CSS cannot fulfill a missing media obligation.

## Artifact Dossiers And Evidence

Artifact continuity is centered on durable identity, not copied paths. `artifact_dossiers` are keyed by `artifact_ref` and gather identity, provenance, metadata, enrichments, linked response/message ids, and availability.

An accepted branch image carries its identity and producer bindings into later
frames and durable reloads. When its saved path also appears in the response's
last-saved-image shortcut, canonical construction uses the accepted branch record;
it does not mint a competing unbound identity from that shortcut. This preserves
the same artifact even when a compact top-level projection omits it. The rule
does not confer authority on a supplied reference or equate different artifacts
with equal bytes. Existing binding, provenance, alias and conflict checks still
govern acceptance, and a new accepted generation keeps its own identity.

Public linked-dependency selection uses the exact registered file identity before
falling back to a derived basename, consistently with bundle selection. A current
authoritative replacement wins over an older linked copy of the same logical
file; conflicting strongest identities remain unresolved.

Explicit selected-file collections retain every valid reference, in order,
including producer response/branch/phase provenance and supplied file digests.
Repeated intake normalization must not reduce the collection to the last file.
The interpretive inference layer receives a bounded path/type view of the complete collection; that view is
not artifact authority. Message merging must distinguish different attachment
collections even when their text envelopes are identical.

Each single-file consumer uses its explicit execution-contract artifact ref or
already-bound path. Without an exact binding, only one capability-compatible
reference is unambiguous; collection order cannot choose among sibling files.
Preserving n files does not create n obligations, but existing authorized
consumers must retain access to each required input. Named predecessor edits
still use their existing exact authorization filter.

A carried predecessor **message bundle** is a different source claim from an
explicit file collection. To ground source-sensitive truth-guard checks, its
conversation, response/message identity, canonical message content and every
claimed artifact must pass the existing predecessor proof. Normalization keeping
all references does not confer that authority. A failed bundle proof excludes the
claimed message and files from the guard's private source view; it does not mutate
the request or reject independent explicit file selections. If the requested
transformation then lacks a grounded source, the existing output guard returns
`runtime.truth_guard.status = clarification_required`. This is an output-guard
projection, not a requirement that every earlier intake rejection create a
`runtime` object.

For retained audio consumed by STT, the last input boundary verifies the selected
Registry identity, the current source response artifact and producer provenance,
and the source-bound digest against both the current saved file and the private
copy actually sent to Whisper. Registered aliases retain canonical authority;
unregistered refs, retargeted paths, missing/conflicting source evidence and
changed bytes fail before Whisper. Direct uploads and same-response producer
dependencies retain their existing paths. A direct same-response TTS dependency
uses the completed producer's canonical fill-result identity before final
publication. Late Fill preserves that artifact record ahead of saved-path
shortcuts, selects by the consumer's accepted phase/artifact dependency, and
passes a private immutable binding to internal infer. Request JSON cannot create
this binding. Infer checks the exact ref/id/source/producer/path and physical
verification digest against the source and its actual private input copy. This
does not publish early or relax retained Registry verification. This binding check changes neither
transcription nor TTS/STT semantic comparison.

The infer response exposes `audio_reference_input_evidence` for this check. The
current canonical Responses projection retains it on direct TTS→STT Late Fill
results as a provider-copy identity witness. Retained-reference results do not
currently persist that additional field;
a canonical response alone therefore is not a retained provider-copy digest
witness. Do not infer that telemetry from a successful transcript or Closure.

Late branches should use existing dossier evidence when it satisfies the promoted branch contract. Examples:

- a visual review can use generated-image enrichment or promoted vision-analysis evidence
- an audio confirmation can use generated-audio identity plus transcript evidence
- a source edit can use the selected text/document artifact as active reference truth

If the dossier evidence is missing, stale, or insufficient, the runtime may promote a new evidence branch. It should not silently pretend the evidence already exists.

## Explicit Recovery

Dedicated Apple OCR/barcode requests preserve
`runtime.apple_fm_image_tool_evidence` alongside `runtime.vision_input_evidence`.
The tool receipt records a validated native call/result pair, exact result
text/digest, source image digest and transcript attachment digest. Its transport is
`fm.respond` with `execution_scope=local_cli_session`; it does not prove the
selected HTTP server received the image. Apple may re-encode images, so original
and transcript byte identities remain distinct. A real empty tool result is
reported as no detections; model-only prose cannot establish tool execution.

Generated-image vision analysis also has a bounded automatic evidence recovery.
`vision_input_evidence` records the SHA-256, byte count and instance at actual
image dispatch; Late Fill binds it to the response, branch and phase. For a
unique completed direct image producer, Runtime verifies that receipt against
the saved image. A rejected path-only or missing-input answer then becomes
`VISION_DEPENDENCY_EVIDENCE_REJECTED`, eligible for one alternate-instance attempt
under `vision_bounded_evidence_recovery_v1` (two total attempts maximum).

The same branch and exact image remain owed. The failed instance stays excluded,
and the retry uses only available compatible capacity. Missing, changed,
unbound or ambiguous input remains dependency repair; PDFs and text-only input
do not enter this policy. Cancellation, waiver, optional/deferred work and
automatic-follow-up opt-outs remain authoritative. The retry undergoes the same
evidence check and Closure; exhaustion does not publish rejected text as success.
Both the original rejected answer and dispatch proof survive normalization and
frame storage in `recovery_attempt.prior_vision_evidence_failure`, while a second
rejection retains its own error evidence. Existing frames without dispatch proof
are not retroactively made retryable.

For transient backend failures of these same direct-image branches,
`vision_bounded_backend_recovery_v1` permits one available alternate instance.
Runtime first binds the prepared input to its accepted producer, exact saved
path, digest, response, branch, phase and dependencies. This is preparation
evidence, not a claim that the failed provider inspected the image. Typed timeout,
unavailability, and HTTP 408/429/500/502/503/504 failures qualify; invalid requests
do not. The original failure and binding remain in
`recovery_attempt.prior_vision_backend_failure`. Backend and answer-evidence
recovery share the same two-attempt ceiling; switching failure classes cannot
reset it. Successful dispatch must return a matching native image receipt.
An explicit generation refusal is not an image inspection; these deterministic
rejection checks do not certify the semantic accuracy of an accepted description.

Explicit recovery is user-triggered and branch-scoped. It preserves accepted
sibling results and the original request intent. The retry wave may also include
existing dependent branches that never dispatched because this prerequisite
failed at the dependency gate. Their original identities and edges must still
match the accepted graph; cancellation, external-input requirements and opt-outs
remain binding. Normal dependency gates decide when they can execute. Completed
inline results clear stale retry errors only for their exact output slots; saved
file obligations retain their separate artifact-evidence requirements. Historical
frames remain unchanged, and evidence lost by an older retry is not reconstructed
by this correction.

The failure side exposes `recovery_state.status == "candidate"`. The retry endpoint
promotes the selected candidate into `recovery_state.status == "attempting"` and
records a `recovery_attempt`. Related branches admitted to the bounded retry wave
retain their own recovery records. This is preparation for operational recovery,
not general automatic recovery.

Endpoint:

    POST /api/responses/<response_id>/late_fill/retry

Request:

    {
      "branch_id": "branch-image_generation-2",
      "exclude_instance_ids": ["flux-2"]
    }

Retry state:

    {
      "recovery_state": {
        "kind": "fruth.late_fill_recovery_state",
        "status": "attempting",
        "trigger": "explicit_retry_endpoint",
        "branch_id": "branch-image_generation-2",
        "capability": "image_generation",
        "promotion_required": false,
        "auto_execute": false
      },
      "recovery_attempt": {
        "kind": "fruth.late_fill_recovery_attempt",
        "trigger": "explicit_retry_endpoint",
        "branch_id": "branch-image_generation-2",
        "capability": "image_generation",
        "preserve_intent": true,
        "auto_execute": false,
        "failed_instance_id": "flux-2",
        "excluded_instance_ids": ["flux-2"]
      }
    }

Behavior:

- rejects missing, unknown, or non-retryable branches
- moves the selected failed branch back to `pending_branches[]`
- keeps completed branches and artifacts intact
- carries `failed_instance_id` and `excluded_instance_ids` into late fill route resolution
- returns the current canonical lookup payload and lets the existing lookup poller observe completion or failure

## Control Gating

Required session controls are hard requirements only after Fruth has applied safe defaults and prompt-derived hints.

Safe defaults:

- `reasoning_effort` uses the actual local target model's advertised default when omitted; explicit Off remains Off, and unsupported non-Off values are rejected.
- `tts_voice` may use `default_first_option` when a backend exposes a speaker list.
- generic `tts_instruct` may default to `Use a natural, conversational voice.` for text-to-speech when no stricter voice description is present.

Hard blocks:

- explicit custom voice or speaker requirements without a valid default remain `missing_session_controls`.
- controls without a safe default or prompt-derived value remain blocking.
