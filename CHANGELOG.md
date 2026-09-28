# Changelog

Fruth changes are recorded here. The original Ollmo release history is retained
below.

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
  [dated results](docs/SELF_ATTACK_STATUS_2026-09-27.md); neither native verdict is
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
  170 live cases. See the [dated report](docs/SELF_ATTACK_STATUS_2026-09-19.md)
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
