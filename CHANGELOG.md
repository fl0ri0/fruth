# Changelog

Fruth changes are recorded here. The original Ollmo release history is retained
below.

## [0.1.9] - 2026-11-01

Separate runtime responsibilities while preserving Fruth's accepted-work,
evidence and durable-response contracts. Harden process lifecycle and PDF
continuation, and carry exact validation dependencies with the source package.

### Runtime ownership and continuation

- Extract focused owners for request preparation, evidence, Closure,
  materialization, continuation, frame construction, durable commit and operator
  projections. Retain public compatibility surfaces, persisted formats and
  existing authority and evidence gates.
- Keep newly produced PDF/OCR text separate from selected-predecessor edit
  authority when rebuilding work. Existing selected-file edits and accepted
  file-output obligations remain supported.
- Preserve an existing repair branch's phase and execution binding when its
  terminal projection is rebuilt. Fresh or expanded work retains its own identity;
  stale-result rejection remains enforced.

### Lifecycle, input handling and installation

- Make startup and cleanup act on verified owned processes, preserving unrelated
  listeners and reused process identities.
- Enforce Whisper request admission before transcription dispatch.
- Isolate PDF extraction/rendering in owned, bounded processes with explicit
  capacity, cancellation and cleanup outcomes. Resolve macOS temporary-directory
  aliases before strict child workspace validation, preventing false cleanup
  failures from retaining the preparation slot.
- Correct Python bootstrap and interpreter/dependency checks. Record the actual
  validated dependency closure, source identities and execution evidence in the
  portable validation/ receipt and constraints pair.

### Compatibility and documentation

- Document the supported MLX-VLM Flux 3 loader and its native prompt-upsample
  checkpoint, without bundling model weights or backend environments.
- Clarify the optional Codex route's real read-access boundary, installation and
  observable response contracts. Keep internal research and migration proposals
  outside the public package.
- Update release metadata, the landing page and the single current validation
  report. Preserve the five existing reference packages and historical live
  campaign identities. See [validation status](docs/SELF_ATTACK_STATUS_2026-10-31.md)
  for tested scope and the distinction between durable completion and model accuracy.

## [0.1.8] - 2026-10-29

Turn the completed bounded Hypothesis and semantic-core investigation round into
stronger runtime contracts: preserve requested meaning across handoffs, retain
caller authority through repair and recovery, and require current evidence before
closing owed work. The experimental `0.x` support scope remains unchanged.

### Property-based investigation and resulting hardening

- Extend bounded Hypothesis and deterministic adversarial studies across request
  intake, saved-file consumption, persistence/readback, semantic reviews,
  cancellation and continuation. Independent requirements and physical bytes
  supply the oracles; controlled providers exercise real runtime owners. Retain
  counterexamples and promote corrected behavior into maintained regressions.
- Preserve requested JSON content, exact named outputs, saved-read dependencies
  and consumer requirements through supported intake and preparation. Recognize
  affirmative bare-filename commands and scoped exclusions without admitting
  provider-proposed extras or weakening explicit output bans.
- Require current, bound content reviews for newly admitted named text producer
  → saved read → consumer workflows. File existence, valid syntax and an exact
  read receipt no longer discharge those accepted content duties on their own.
  Missing or failed reviews leave the response visibly unresolved.
- Validate review evidence references against the exact review packet and
  required criteria. Preserve the reference policy through canonical request
  persistence and recovery; reject missing, foreign or stale review evidence.
- Preserve accepted caller context through control operations and publish a
  fresh Closure assessment after a winning control. Accepted sibling reviews
  remain covered; delayed results from cancelled work remain rejected.
- Continue independently owed, admitted review work after a control conflict
  through the existing bounded handoff. Preserve promotion, canonical requests,
  exact dependency aliases and evidence-only quoted review context without
  replaying the root request or bypassing cancellation/current-frame checks.
- Require terminal links only where accepted consumer contracts actually owe
  them. Independent mixed outputs and ordinary saved-data consumers no longer
  inherit an unrelated link requirement; genuinely missing links remain open.
- Complete the bounded dependency study and source-level follow-ups. Local
  derivations and repeated formal constraints do not justify deleting substantive
  runtime requirements. Safety checks, reviewer accuracy and progress remain
  distinct claims; finite study coverage is not a universal proof.

### Reference workflow corrections

- Preserve the saved-read and content contract during exact-target HTML syntax
  repair. Bind the source read, target snapshot, defect and prepared input; retain
  fresh output evidence and require a current consumer review. Verify an already
  saved repair instead of rewriting its bytes after capturing their digest.
- Deliver all accepted individual image reports for supported separate-inspection
  requests through an explicit identity-bound join. Reject omitted, duplicate or
  substituted contributions and check the final rendered answer. Distinct
  comparison and transformation requests retain their own execution paths.
- Present each content review's accepted local duties and criteria before shared
  context, and identify sibling duties by their accepted branch contracts.
  Negative reviews still block completion; improved live reviewer reliability is
  not inferred from offline fixtures.

### Apple compatibility and validation

- Restore PCC Pro → Cloud fallback for the observed opaque Shortcuts error when
  current native diagnostics tie the owned request to the explicit Pro-access
  rejection. Keep unrelated, stale or ambiguous errors from authorizing fallback.
- Recognize the updated Foundation Models CLI system-model availability output
  after the operator has accepted Apple's terms, preserving explicit readiness
  and license failures.
- Complete the matching 38-profile / 380-case offline gate and 198 owner checks,
  followed by the source/evidence checker. Record local, AFM and PCC live windows
  and targeted recovery with their actual source identities and original verdicts.
- Refresh the two affected reference packages from October 29; retain the three
  October 27 audio/site examples. Saved files, read chains, individual reviews and
  canonical completion are verified. See the [current validation status](docs/SELF_ATTACK_STATUS_2026-10-31.md)
  for coverage, source chronology and limitations.

## [0.1.7] - 2026-10-21

Strengthen durable continuation and evidence preservation, widen local image and
embedding support, and make validation and storage workflows easier to reproduce.
The experimental `0.x` support scope remains unchanged.

### Corrected and hardened

- Preserve accepted result content and digests during later terminal file repair,
  while refreshing current artifacts and new repair results. Keep replaced repair
  contracts as explicit supersession history instead of leaving them executable
  after their replacement completes. Retain publication and exact-target checks.
- Preserve terminal Closure repair and partial-rebase execution identities when
  rebuilding Late Fill state. An admitted repair worker can enter running state
  without rejecting its own execution; stale execution checks remain enforced.
- Make `archive --full` exclude raw self-attack campaigns from copying and space
  preflight, then delete only local run directories after successful archive and
  retention checks. Preserve external campaign stores, existing archives, links,
  helpers, learning and storage-location configuration. Plain archive can omit
  the copy without deleting runs via `--exclude-self-attack`. Record the scope
  and cleanup policy in the manifest. Full archive also rotates the three monitor
  history files so the new runtime epoch starts with fresh monitor state.
- Preserve accepted image and sibling evidence through explicit Late Fill retry.
  Bind generated-image inspections to exact saved inputs, reject text-only
  dispatch and generation refusals, and allow one compatible alternate vision
  instance after a transient backend failure. Share the existing two-attempt
  limit with answer-evidence recovery. Reconsider only previously accepted
  dependent work blocked by that prerequisite, clear stale inline-output errors
  after accepted completion, and retain original failure provenance and frozen
  parent frames.
- Extend embedding helpers to model- and adapter-qualified image/audio inputs,
  preserving text-only backends. Explicit current-turn media can supply bounded,
  digest-labelled advisory similarities; unsupported inputs remain visible and
  media scores do not inherit deterministic text routing thresholds. Recognize
  native image checkpoint `config.json` model declarations so manual downloads
  receive the installed loader's specific compatibility result.
- Keep Ollama download errors readable by removing terminal controls and manifest
  spinner frames before returning diagnostics to the browser and runtime event log.
  Preserve the actual error text and CLI exit status without automatic retry.
- Release unused MLX image allocator buffers and idle image model weights after
  generation/edit requests, retaining completed output and lazily reloading for
  the next request. Coordinate cleanup with in-flight requests and preserve
  unrelated model groups.
- Discover MLX image capabilities through the installed native loader and local
  checkpoint metadata instead of a model-name allowlist. Keep incomplete/unknown
  checkpoints unavailable with a reason; distinguish generation from editing,
  expose native sampling defaults and enforce loader-specific step minima.
  Include Z-Image through this shared discovery path.
- Add an instance-bound image adapter for qualified local MLX-VLM image models
  alongside existing Ollama image execution. Separate image discovery/startup
  from chat/vision, retain exact reference bytes for editing, and validate PNG
  results and controls before artifact persistence. Preserve image execution
  evidence through provenance and canonical responses; distinguish requested
  seeds from provider-reported seeds. Add Pillow decoding with MIT-CMU notices.
- Allow qualified MLX image models through the frontend Start button's shared
  lifecycle gate, matching terminal startup. Keep snapshot/package qualification
  and explicit start-source checks.
- Expose optional diffusion Steps in supported MLX image session controls for
  generation and reference editing. Preserve native defaults when blank, reject
  invalid/unsupported values, and retain requested/sent steps in image evidence.
- Complete backend-neutral text-embedding helper integration: supported MLX
  encoders use their embedding server, llama.cpp embedding instances report
  vector output, and automatic selection no longer favors Ollama. Preserve
  explicit helper preferences and existing routing thresholds. Reject malformed
  or inconsistent vector batches and discard stale hints after helper failure.
- Preserve previously accepted sibling results when cancelling, waiving or
  superseding pending Late Fill work, including immediate durable recovery.
- Serialize control and worker publication per response within one server process.
  Recheck frame, execution and target identities through publication so stale
  results cannot undo acknowledged controls. Stale control admission returns 409;
  a fresh request with no controllable target retains 404.
- Allow one guarded handoff of exact admitted, never-submitted pending work after
  a control conflict, using the existing scheduler and original live worker
  context. Preserve accepted siblings, cancellations, local contracts and
  dependencies. Failed qualification or scheduling consumes the attempt;
  passive recovery and pending-only retry do not gain execution authority.

### Testing and maintainability

- Record source-bound 170-case live coverage for local models, AFM and PCC Cloud,
  supported by matching 380-case offline gates. Refresh the five public reference
  packages from the October 18 runs. The
  [October 21 results](docs/SELF_ATTACK_STATUS_2026-10-31.md#historical-results) records source
  identities, PCC window/retry coverage and validation limits.
- Replace the obsolete urllib3 1.x constraint with urllib3 2.x (`>=2,<3`).
  Document the OpenSSL requirement and separate main/backend environment updates.
- Add optional `state/storage_locations.json` for independent archive and
  Self-Attack write targets and multiple read locations. Keep existing defaults,
  preserve configuration during cleanup, reject unavailable selected destinations,
  and provide `fruth storage` discovery for manually relocated evidence. External
  archive moves verify copied bytes before removing each source; historical
  receipts remain unchanged.
- Add deterministic conservation, overlap and continuation regressions, independent
  fault-sensitivity controls and bounded Hypothesis studies using real runtime
  owners with synthetic providers.
- Separate complete trace generation from side-effecting persistence scenarios,
  seal inputs before execution and count actual starts/transitions independently.
- Add bounded persistence-fault and fresh-process recovery studies covering
  selected writer interruptions, partial tails, unavailable Index data and missing
  authoritative evidence. Distinguish readable historical work from write
  confirmation and execution permission.
- Separate ordinary regressions from opt-in research campaigns and historical
  diagnostics while keeping deterministic controls in mixed study modules.
  Package a portable pre-import guarded runner with fresh-process purity routes,
  exclusive evidence, exact cold-child admission/reaping and bounded detached
  supervision. Integrate bounded shell, Node, Python CLI and owned native-process
  routes with exact admission, containment, deadlines and reaping receipts.
  Correct restart-fixture probe instrumentation and add an exhausted-wait control.
- Clarify the public semantic-core overview: required meaning, operation contracts
  and evidence for the exact subject, version and scope, including coverage across
  handoffs and recovery. This summarizes engineering obligations without claiming
  a minimal or complete axiom system.

## [0.1.6] - 2026-10-11

Hardening and validation since 0.1.5: strengthen caller authority, accepted file
bindings, saved evidence and successor lineage. The experimental `0.x` support
scope remains unchanged.

### Corrected and hardened

- Enforce trusted Host/Origin and explicit action declarations before local API
  effects. Reject invalid preference request encodings instead of silently
  resetting preferences; update the browser and supported clients accordingly.
- Preserve the actual caller's intent separately from planner-prepared execution
  text through graph rebuilding, dispatch, writing, frames and recovery.
- Preserve explicit output filenames, extensions, targets and counts through
  structured extraction. Validate accepted bindings before writes and require
  matching physical file identity and digest for fulfillment and canonical reuse.
- Preserve conflicting saved-result evidence through canonicalization/recovery;
  prevent duplicate evidence order from hiding a conflict. Keep successor work
  independent of incidental diagnostic text, preserve saved bindings on repeated
  completion, and require each image successor's own qualified result while
  retaining earlier artifact identities.
- Keep truth-guard text corrections consistent across public outputs, frozen
  frames and retrieval without replacing independent or artifact-backed content.
  Classify control JSON by keys and explicit envelope structure; preserve ordinary
  field-name mentions, documentation examples and fenced data followed by prose.
- Attribute monitor phase timings to the actual response or its branch records.
  Withhold uncorrelated times, retain separate wave spans and flag contradictory
  timing evidence without changing artifact/Closure verdicts or historical reports.
- Archive legacy root-level outputs before cleanup, verify protected copies before
  moving runtime/history, preserve learning/reset archives during cache sweeps,
  and distinguish planned, missing-target and failed-retention outcomes.
- Serve the fixed Axios 1.20.0 browser dependency locally with its license and
  provenance. Fonts and icons remain separate external dashboard dependencies.

### Testing and maintainability

- Exercise accepted file bindings, returned evidence, graph successors and artifact
  lineage with bounded Hypothesis property and stateful campaigns. Retain reduced
  counterexamples, independent reference models, positive controls and deterministic
  regressions. Findings drove the evidence and successor corrections above;
  these families do not constitute an exhaustive state-space or liveness proof.
- Extract the initial Late Fill eligibility decision into a private helper while
  preserving ordered state updates and the existing scheduling/execution owners.
- Add bounded PCC conformance windows, structured quota stopping, resume and
  compatible evidence composition. Provider quota-stop behavior still needs live
  validation; Cloud and Cloud Pro evidence remain distinct.
- Replace public test-guide links to private plans with self-contained operational
  guidance, and check Markdown links against files actually selected for release.

### Recorded validation and examples

- Record the October 10 complete local and AFM live matrices: 170/170 cases each
  on their recorded source. Subsequent response corrections have separate offline
  validation; later source changes do not relabel those historical results.
- Refresh all five public reference packages with October 10 executions, saved
  artifacts, exact-frame monitor evidence and checksums. Their retained historical
  phase timings carry the documented attribution limitation. See the
  [validation report](docs/SELF_ATTACK_STATUS_2026-10-31.md#historical-results) for scope and chronology.
- Clarify collaboration guidance: the maintainer is open to contributions and
  learning the review process, with limited capacity and no guaranteed turnaround.

## [0.1.5] - 2026-10-05

Maintenance release for branch progress and additive dependency validation.
The experimental `0.x` support scope remains unchanged.

- Prevent an unavailable image branch from repeatedly suppressing independent
  executable work. Select ready work before availability rechecks, then recheck
  the oldest due waits while preserving dependency and resource guards.
- Use the same availability selection for execution and next-wave state
  publication. Preserve branch identity, cancellation, evidence gates and named
  retry budgets.
- Reject additive dependency repairs with unresolved or ambiguous identities,
  self-dependencies or cycles, including invalid combinations of otherwise local
  additions. Revalidate the candidate graph when applying an accepted repair.
- Add regressions for dependency validation, competing availability waits,
  independent branch progress and preserved dependency/resource constraints.
- Clarify the semantic-core overview and the existing scheduling contracts.

## [0.1.4] - 2026-10-01

Includes both signed PCC shortcut exports in the source archive and makes SQLite
the standard response Index. The experimental `0.x` support scope remains unchanged.

- Bundle `Fruth PCC.shortcut` and `Fruth PCC Pro.shortcut` with their bridge and
  setup helper in the complete source tarball.
- Offer PCC first-use setup from Models and the interactive startup selector.
  Open missing bundled shortcuts for the user's Add Shortcut confirmation,
  preserve existing installations, and recheck installation before starting PCC.
- Replace whole-JSON response-index publication with transactional per-response
  SQLite updates. Preserve canonical Ledger history, frozen frame lineage,
  snapshots, evidence, validation and recovery. JSON remains inactive backup or
  migration input, or explicit current-history rollback/export; normal runtime
  maintains one SQLite Index.
- Add explicit migration, reconstruction and current-history rollback/export
  tooling, including complete-map authentication and Ledger coverage checks.
  New roots initialize through the frame writer; passive reads create no storage
  and never migrate or silently reactivate JSON.
- Preserve frame-relative evidence paths when verifying relocated SQLite
  histories, including archive/restore and migration fixtures.
- Keep archive, cleanup and reviewed-learning retention aware of the selected
  SQLite generation and protected Index files. Report protected-output conflicts
  explicitly in the learning evaluation CLI.
- Correct persistence documentation: unconfirmed frame writes block delivery
  with an explicit storage failure; confirmed Ledger commits remain committed
  when derived Index publication fails.
- Preserve the verified map identity in state-flow diagnostics for SQLite
  lookups, using the existing authenticated root without another map scan.

## [0.1.3] - 2026-09-28

Adds local Apple Foundation Models and optional Apple PCC integration, native
macOS PDF processing, follow-up/fallback fixes and reusable Research curation.
The experimental `0.x` support scope remains unchanged.

- Recover automatic chat and file/vision provider failures through the configured
  fallback and compatible running alternatives, with recorded, bounded attempts.
  Preserve accepted work, explicit targets/locks, refusal and evidence gates;
  never switch producers after streaming begins.
- Add Apple PCC chat and image analysis through user-installed Shortcuts, with
  preferred interpretive inference selection, Cloud Pro-to-Cloud access fallback,
  and recorded input/tier evidence. Apple's usage limits remain provider limits.
- Preserve saved image/audio artifacts on state-explanation follow-ups, instead
  of repeating generation or transcription; carry selected response and multiple
  artifact references into follow-up context.
- Keep registered dependency identities when selecting public artifacts, so an
  older linked file cannot reappear beside its authoritative current replacement.
- Scope AFM conversation context to the current request and relevant references;
  ordinary saved-artifact explanations no longer automatically require additional
  semantic reviews. Explicit review contracts and evidence checks remain active.
- Read recent events from the end of the event log; compact response-index writes
  and avoid unnecessary parent-ledger scans when a verified current index proves
  a new response absent. The index still uses whole-file publication.
- Record the September 25–27 AFM and PCC conformance observations, including
  correct mismatch rejections and PCC quota-limited coverage. See the
  [dated results](docs/SELF_ATTACK_STATUS_2026-10-31.md#historical-results); neither native verdict is
  restated as a full pass.
- Replace optional PyMuPDF and the first-page `sips` fallback with native macOS
  PDFKit/CoreGraphics rendering through PyObjC. Preserve selected page order,
  full page counts, crop/rotation geometry and rendering limits; retain pypdf
  for text-layer extraction. No cross-platform renderer is added.
- Process incoming PDFs afresh while keeping explicit history retrieval. Route
  rendered pages through the selected OCR/vision path, including Apple single
  tabs; preserve page/coverage diagnostics on failures and correct image MIME
  labels without changing source bytes. Successful page dispatch does not prove
  transcription accuracy; see [Apple PDF observations](docs/APPLE_FOUNDATION_MODELS.md).
- Add reusable offline Research evidence audit, response inspection and explicit
  Gold curation commands, with exact bindings, retained validation and recoverable
  publication. Curated private cases and evidence remain excluded from source
  packages; candidate availability does not establish correctness.
- Show Apple PCC separately from on-device Apple AI in the architecture diagram,
  with its local bridge and cloud execution boundary; refresh architecture and
  source-scope documentation.
- Add Apple FM as the fourth local backend through the installed macOS `fm serve`
  command: text chat, image analysis, streaming, multiple instances, exact targeting and owned
  process start/stop. The UI backend label is Apple AI; API identity remains `system`.
- Reserve 50 ports after llama.cpp (default 11601–11650), with existing registry,
  status, Responses, artifact and closure owners. Local AFM needs no model download
  or SDK inference dependency. Apple PCC is a separate optional backend.
  See [Apple AI](docs/APPLE_FOUNDATION_MODELS.md).
- Preserve inline image bytes and message order in Apple FM requests; route image
  and scanned-PDF analysis through the selected backend. AFM 3 speech remains
  unavailable through the installed public transport.
- Keep ordinary image descriptions in the vision answer instead of inventing
  duplicate analysis and text branches. Explicit dependent tasks and saved-file
  requests retain their graph contracts.
- Send the explicitly authored common plus current-role policy projection to
  the executing local AFM backend. Other backends, including PCC, retain the full
  ordinary inference policy. Preserve source digests, current inputs, accepted
  branch contracts and runtime validation gates.
- Update the landing page, backend inventory and source-package documentation.

## [0.1.2] - 2026-09-19

Continues Ollmo 0.1.1 under the Fruth name, with legacy-input cleanup and
migration fixes. The existing engine and experimental `0.x` support scope are
carried forward.

- Rename the project, Python packages, CLI and project configuration to Fruth;
  describe the former Ghost responsibility as interpretive inference.
- Use the canonical `semantic_role_ids` list for explicit role selection; remove
  the former public `ghost_mode` aliases. Preserve internal intent orientations,
  role sets, precedence and advisory authority.
- Set the web/API default to port 5011, preserving backend ports 11434–11600 and
  the existing startup, shutdown, restart, discovery and recovery workflow.
- Package maintained Research code and initialize missing empty stores during
  normal startup. Keep accumulated Research data and accepted learning separate.
- Normalize working-frame role summaries through the canonical request owner,
  including malformed inputs, deduplication and metadata precedence.
- Require contract-specific evidence before skipping already-completed-looking
  branches, including reads of saved files used by later outputs.
- Add one bounded retry for failed vision-analysis evidence when a compatible
  alternative is available, preserving the original branch and source binding.
- Reconcile accepted media and file outputs before final link repair and Closure;
  prefer exact verified producer paths to avoid unintended extra artifacts.
- Update project documentation, citation concepts, copyright attribution and the
  architecture diagram's persistence, observation and rebase authority boundaries.
- Replace migrated examples with five recorded Fruth reference runs, retaining
  their response, monitor, artifact and checksum evidence.
- Record the 18–19 September full conformance pass: 380 deterministic cases and
  170 live cases. See the [dated report](docs/SELF_ATTACK_STATUS_2026-10-31.md#historical-results)
  for tested scope and limitations.

## [0.1.1] - 2026-09-12

Stabilization and evidence hardening since the August 1, 2026 public release.
This patch release retains the existing local-first product and experimental
`0.x` support scope. See [installation](README.md#install-and-start) and
[known limitations](docs/KNOWN_LIMITATIONS.md) for current usage guidance.

### Fixed and hardened

- Preserve exact requested file identities, counts and producer/consumer
  dependencies through graph rebuilds, repair and category-scoped deferral.
- Preserve explicitly reserved image candidates across punctuation and scoped
  pronoun/ordinal references without promoting neighboring artifact categories.
- Bind saved-file consumers to the actual saved bytes, paths, identities and
  digests; keep missing or changed evidence visible as incomplete work.
- Tighten artifact authority, multi-file HTML/CSS/image binding, target-specific
  repair, canonical outputs and openable bundle validation.
- Improve counted image prompts and retries, TTS source/completeness checks,
  bounded generation recovery and direct TTS-to-STT dependency evidence.
- Harden durable frame/Index/Epoch handling and Readiness retention; reduce
  repeated preparation/hydration while retaining current integrity checks.
- Improve semantic-review publication, late-fill continuation, retained context,
  MLX reasoning controls, audio transport and accepted-learning eval refresh.

### Added

- Deterministic/fake Self-Attack conformance, explicit live coverage scopes,
  resumable captures and two compact reproducible corpora.
- Causal, transition and state-flow diagnostics; extracted Late Fill telemetry
  ownership and bounded epoch-mismatch diagnostics.
- Five curated, self-contained reference-run packages, with saved artifacts,
  sanitized response/monitor evidence, verified bundles where applicable and
  checksum manifests.

### Documentation and distribution

- Audited current response, artifact, Closure, durability, lookup and authority
  contracts; preserved dated evidence and corrected misleading completion claims.
- Updated public guidance and companion-skill contracts; documented output
  rendering boundaries and the experimental support scope.
- Extended the source allowlist for public diagnostics, Self-Attack and references;
  exclude Finder metadata and keep SHA manifests specific to built archives.

## [0.1.0] - 2026-08-01

Initial public release of Ollmo.

- Local-first AI runtime substrate and control plane for Ollama, MLX, and
  llama.cpp, with an optional explicitly enabled ChatGPT provider.
- Canonical Responses, Ghost routing, work graphs, materialized artifacts,
  continuable runtime state, and evidence-gated closure.
- Local model and media workbench, Codex companion skill, static project site,
  reproducible release archive, and Apache-2.0 project licensing.
