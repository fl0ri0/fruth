# Fruth source packaging scope

This document defines the current source selection and support boundaries.
This scope applies to Fruth `0.1.9`. The [changelog](../CHANGELOG.md) and
[October 31 status](SELF_ATTACK_STATUS_2026-10-31.md) describe its changes and
source-bound validation evidence. See the [installation guide](../README.md#install-and-start)
for setup and [known limitations](KNOWN_LIMITATIONS.md) for current constraints.
The reference selection contains three October 27 workflows and two October 29
workflows. Existing published archives and their original evidence remain unchanged.

## Included capabilities

The source package includes:

- Transactional SQLite response indexing with authenticated completeness and
  Ledger coverage, explicit migration/reconstruction and current-history
  rollback/export. The append-only Ledger remains canonical durable history.
- [Apple AI](APPLE_FOUNDATION_MODELS.md), the fourth local backend, with `fm serve`
  text generation, image analysis, streaming and instance management.
- Optional [Apple PCC](../fruth_integrations/shortcuts/README.md) text/image
  execution through user-installed Shortcuts and a locally managed loopback
  adapter. Requests send selected inputs to Apple; local readiness does not
  establish cloud access or remaining quota. Both signed shortcut exports and
  assisted first-use setup are bundled in the source archive.
- Bounded provider failover, saved-artifact follow-up/reference fixes and scoped
  local AFM context, preserving existing request and evidence gates.
- Native macOS PDFKit/CoreGraphics rendering through PyObjC, with pypdf text
  extraction and the existing OCR/vision routes. Each incoming PDF is processed
  afresh; explicit history retrieval remains available. Page coverage and model
  transcription accuracy remain separate guarantees.
- Reusable offline Research evidence review and explicit Gold curation, including
  retained validation and recoverable publication of reviewed cases.

See the [changelog](../CHANGELOG.md) and
[October 31 validation status](SELF_ATTACK_STATUS_2026-10-31.md) for source-bound
evidence. Responsibility extraction and process/PDF corrections have their own
offline and targeted checks. Earlier local, AFM and PCC campaigns retain their
source identities and recovery history. They do not become complete live tests
of later changes. PCC Cloud Pro remains untested.
Release preparation checks the selected source package separately; a local build
does not publish it or alter historical verdicts.

## Supported surfaces

- A local Flask control plane and browser interface.
- A standalone static repository landing page, packaged with all of its local
  CSS, JavaScript, font, and font-license dependencies. The live local root
  remains the dashboard; `/site/` provides the canonical local preview of the
  self-contained `site/` publication directory. Its contents can be placed at
  the root of a dedicated Pages branch and activated manually; the release
  includes no publication workflow.
- Local model discovery and lifecycle support for the backends already
  implemented by Fruth, including Ollama, MLX, llama.cpp and Apple AI paths,
  plus a locally managed bridge for optional Apple PCC cloud execution.
- The canonical `/api/responses` and `/v1/responses` execution surfaces.
- Interpretive inference routing, durable response frames, runtime status, history, and
  materialized artifact tracking.
- Truthful response state: `outputs`, artifacts, response frames, lifecycle,
  closure, and late-fill state are authoritative; model prose is not proof of
  success.
- A bundled, Codex-specific Fruth skill for inspecting local runtime truth,
  choosing safe request paths, and using canonical responses and artifacts.
  Skill installation is manual and does not start Fruth or enable cloud use.
- An optional, explicitly enabled ChatGPT route through Codex that accepts a
  prompt, bounded context promoted for the current turn, and local files or
  Fruth artifacts explicitly selected for that turn, then returns text. Fruth reuses a login owned by the ChatGPT app
  or a separately installed Codex CLI without reading, copying, or storing that
  login. The dashboard exposes ChatGPT as an external cloud target and interpretive inference
  preference, never as a local running instance.
- A reproducible, allowlist-based source archive with a SHA-256 manifest.
- Five explicitly curated, self-contained reference-run packages with copied
  public artifacts, sanitized final-response and monitor evidence, and package
  checksums. Production response ledgers, monitor ledgers, runtime state, and
  unrelated generated artifacts remain excluded from the source release.
- Apache License 2.0 coverage for Fruth's own code and project documentation,
  with separate notices for third-party components, machine-readable citation
  metadata, and research-contact paths maintained by `@fl0ri0`. Collaboration is
  welcome within the maintainer's learning process and available capacity;
  responses, reviews, merges, and ongoing support cannot be guaranteed. See
  [participation guidance](../CONTRIBUTING.md).

Existing capabilities remain available unless they would make installation,
security, or response truth materially unsafe. Optional backends and
modalities remain experimental.

## Source selection and checksums

`scripts/build_release_archive.py` owns the current source allowlist and verifier.
`RELEASE_BROWSER_DEPENDENCY_FILES` requires the fixed local Axios browser build,
source map, MIT license and provenance under `static/vendor/axios-1.20.0/` for new
builds. Verification retains compatibility with complete historical CDN-based
dashboards, but rejects partial bundles or a local dashboard missing the bundle.
This is current source selection, not a claim that this addition shipped in
previously published 0.1.5 archives. Google Fonts and Font Awesome remain remote
dashboard dependencies; see [third-party notices](../THIRD_PARTY_NOTICES.md).

`PUBLIC_DOCS` includes the normative contracts, `SELF_ATTACK.md`, the single
current [October 31 validation status](SELF_ATTACK_STATUS_2026-10-31.md), causal
telemetry and state-flow diagnostics. Earlier summaries and reference selections
are retained privately; the current report preserves their historical verdicts.
The dated summary records the tested
source and scope; packaging it does not establish a new conformance result.
`PUBLIC_CONFIG_PATHS` includes exactly `config/self_attack_corpus.json` and
`config/graph_rebase_shadow_corpus.json` as compact reproducible inputs. The first is the default Self-Attack corpus;
the second supports the documented opt-in graph-rebase diagnostic command.
Their corpus identifiers are independent of the software release version. Harness
and test code are included through the normal source-tree rules. Raw captures,
production ledgers, local forensic corpora and generated `state/` are excluded;
running conformance creates new local evidence.

The three reference replay fixtures use synthetic, portable paths. Review
instruction and generation bindings are regenerated consistently after path
normalization; original artifact bytes, content digests and verdicts are retained.
These public derivatives support regression replay without exporting operator
home/cache paths. Original live captures remain private.

`PUBLIC_INTEGRATION_DOC_PATHS` includes the exact PCC setup guide at
`fruth_integrations/shortcuts/README.md`. The bridge's Python sources are selected
through the normal integration source rules; unrelated integration notes are not
included. `PUBLIC_SHORTCUT_PATHS` selects exactly `Fruth PCC.shortcut` and
`Fruth PCC Pro.shortcut` from that directory. Both exports are required for new
builds; unrelated shortcut exports are excluded. Archive verification accepts
older releases with neither file, but rejects a partial pair or an unlisted
`.shortcut` file. Packaging checks establish inclusion and byte integrity, not
Apple signature validity or workflow behavior.

Users import the bundled shortcuts explicitly as documented in the setup guide.

The four exact companion-skill files are `skills/fruth/SKILL.md`,
`skills/fruth/NOTICE`, `skills/fruth/agents/openai.yaml` and
`skills/fruth/references/fruth-contract.md`. Other skills are excluded. Some skill
engineering/monitoring references describe development-checkout resources:
`AGENTS.md`, `plans/` and `skills/fruth-run-monitor/` are not shipped. Public
operation uses the bundled contracts and `FRUTH_FOR_AGENTS.md`; missing optional
development resources are not a reason to infer runtime authority.

Development plans, exploratory notes and raw generated validation reports are
excluded. Reviewed public summaries are included only through the explicit
allowlist. The canonical monitor is `scripts/fruth_run_monitor.py`.

`MANIFEST.sha256` covers every staged regular release file except itself,
including the generated empty `model_ports.json`. The verifier checks the exact
file set and every digest, as well as archive-path/type/size and public-scope
constraints. The manifest cannot contain the final archive's own digest; the
builder reports that SHA-256 separately. Deterministic staging/archive metadata
makes unchanged selected inputs reproducible. This is content-integrity and
packaging evidence, not a signed release or proof of runtime conformance. The
builder performs no upload; publication gates and external publication remain
separate actions.

## Exact validation environment records

Validation can opt into `scripts/run_tests.py --record-validation` as
described in [the testing protocol](TESTING_PROTOCOL.md#validation-dependency-records).
`scripts/validation_record.py` exports a pair from completed, successful runner
jobs: `validation/constraints.txt` and `validation/receipt.json`. These are the
only allowed public files in `validation/`. They are optional for source builds;
a partial pair or a pair for different source is rejected. Historical archives
without either file retain their original verification behavior. No record is
backfilled for 0.1.8: today's audit/installations are not its validation environment.
The 0.1.9 package includes the pair captured from its completed release-validation
jobs; its receipt identifies the exact source and executed scope.

The constraints pin the active declared dependency closure, not every installed
package. `pytest`, `hypothesis` and `pyyaml` roots are classified as validation;
other declared roots are runtime. Shared transitives retain both roles. This is
recordkeeping, not a requirements split or dependency cleanup. The original
requirements ranges and Hypothesis pin remain the installation contract.
Original direct/metadata edge markers, their evaluation and exact versions are
retained in the receipt. Packaging tools (`pip`, `setuptools`, `wheel`) are
identified separately; incidental packages contribute only a count and metadata
digest, never new constraints. This records metadata, not a byte audit of every
installed package or its import resolution.

The receipt contains Python implementation/version, executable digest, ABI/cache
tag, marker environment (OS/architecture included), TLS identity, packaging tools,
requirements digest, closure identity and exact selected tests/outcomes/JUnit
counts. Source identity is SHA-256 of the sorted JSON relative-path/digest map
using the runner's existing encoding. It covers every release-selected input
except the generated pair, `MANIFEST.sha256` and generated empty
`model_ports.json`. The ordinary release manifest still covers the pair. Thus
generating a receipt does not change the source identity it describes; changing
code, tests, public documentation or requirements does. Private plans are absent.

These are three distinct evidence levels:

- **Environment inventory:** a current metadata observation; no earlier test
  result is attached by inference.
- **Matching validated environment:** the actual test workers captured matching
  before/after inventories, and export checked their frozen source, configuration,
  selections, results, JUnit and completion evidence. This establishes only the
  listed checks, including visible skips; it is not a full release verdict.
- **Known installation-artifact provenance:** requires genuine contemporaneous
  install/download evidence bound to that environment. The current exporter
  explicitly records this as unavailable. It does not accept a generic pip report
  as proof, recover original wheel hashes from installed metadata, or substitute
  newly downloaded same-version wheels. Keep any genuine installation evidence
  privately for review; raw reports/URLs are not public release inputs.

The pair proves consistency of retained records, not authenticity or a signature.
Before/after observations do not defeat a concurrent change-and-restore of an
environment, native-library changes, or hostile test code. Hold the chosen
environment stable during validation. Missing artifact provenance means neither
byte-identical nor offline reconstruction is claimed. Version constraints alone
do not establish wheel availability, native ABI compatibility or capability tests.
Different Python minors, platforms and architectures require their own validation;
the pair describes one target and pins carry that target's minor/platform markers.
The strict environment check also compares patch/TLS/OS and incidental metadata.

For a separately prepared compatible environment, apply constraints explicitly:

```sh
python -m pip install -r requirements.txt -c validation/constraints.txt
python -B scripts/validation_record.py verify --source . --record validation --environment
```

Constraints do not install packages by themselves, and off-target markers may
leave pins inactive. Never treat such an installation as a match without checking
the receipt. Matching versions may still differ in metadata/tool identities;
bootstrap tool versions are recorded, not automatically installed by constraints.
Normal startup and installation do not consume the pair. See the primary
[packaging marker API](https://packaging.pypa.io/en/stable/markers.html) and
[pip repeatable-install guidance](https://pip.pypa.io/en/stable/topics/repeatable-installs/).

## Supported Environment

The primary tested environment is a recent macOS release on Apple Silicon
with Python 3.11 or newer. Individual local capabilities additionally require
their own backend and model packages. Other operating systems and processor
architectures are not part of the 0.1.9 support promise.

Fruth is intended for local, single-user use and binds its web control plane
to `127.0.0.1` by default. Remote and multi-user deployment are outside this
release scope.

## Local-First and Optional Cloud Use

Local execution is the default product posture. Apple PCC is an optional cloud
backend reached through user-installed Shortcuts; selected task text, images and
context leave the device for Apple. Availability and usage limits are checked
per call; starting its local adapter does not establish cloud access. See the
[PCC guide](../fruth_integrations/shortcuts/README.md).

ChatGPT is a separate optional cloud path:

- it must be explicitly enabled before Fruth can route a prompt or selected
  files to it;
- Fruth explicitly supplies the current prompt, promoted context, and selected
  files or Fruth artifacts; staging bounds this handoff, not all downstream reads;
- recognized images use Codex's native image-input path, while other selected
  regular files are copied under neutral names into a temporary working directory
  with byte counts and digests recorded. The requested read-only command sandbox
  restricts writes without establishing selected-file-only read access;
- one request accepts at most 5 files, up to 100 MiB per file and 250 MiB in
  total; URLs, folders, and direct leaf symbolic links are rejected. Regular files
  reached through symlinked parent directories are accepted;
- the route returns text, and acceptance of a regular file does not guarantee
  semantic interpretation of every format;
- the ChatGPT app's bundled Codex executable is preferred, with a separately
  installed `codex` executable as fallback;
- Fruth does not select a fixed cloud model and does not promise to mirror the
  model selected in an open ChatGPT conversation;
- the exact GPT variant is not exposed to Fruth, and model self-description is
  not runtime identity proof;
- the prompt, promoted context, and selected file bytes sent through this route
  leave the machine and are processed by OpenAI under the user's existing
  account and applicable terms;
- direct dashboard turns are ephemeral and independent; Fruth can promote
  bounded relevant context for a referential turn, but no provider session is
  silently resumed.

Downstream client loading and enabled tools have their own access boundaries.
Offline synthetic checks demonstrated broader local reads, but no actual
unselected-data disclosure to the provider was demonstrated. See
[SECURITY.md](../SECURITY.md#chatgpt-through-codex-and-cloud-processing).

Direct provider API-key management and external providers beyond the documented
ChatGPT and Apple PCC integrations are not part of 0.1.9.

## Compatibility

Saved and historical builds that were never publicly released do not create a
compatibility obligation. Public contracts introduced in the `0.x` series
will be changed deliberately and documented, but may still evolve.

## Research packaging

The current `RESEARCH_SOURCE_FILES` allowlist includes Research initialization,
status, candidate synchronization, offline evidence audit/inspection, explicit
Gold curation, schema/validator/evidence resolver, documentation and synthetic
tests. Accumulated candidates, Gold cases, retained evidence, review reports,
curation receipts and generated manifests are excluded. Fruth startup creates
missing empty stores automatically and preserves existing Research data.
No Research absence is treated as an optional test skip.
