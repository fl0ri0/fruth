# Fruth source packaging scope

This document defines the contents and support boundaries of the Fruth `0.1.3`
source package. See the [installation guide](../README.md#install-and-start)
for setup and [known limitations](KNOWN_LIMITATIONS.md) for current constraints.

## Added in 0.1.3

This package adds the following to the published 0.1.2 baseline:

- [Apple AI](APPLE_FOUNDATION_MODELS.md), the fourth local backend, with `fm serve`
  text generation, image analysis, streaming and instance management.
- Optional [Apple PCC](../fruth_integrations/shortcuts/README.md) text/image
  execution through user-installed Shortcuts and a locally managed loopback
  adapter. Requests send selected inputs to Apple; local readiness does not
  establish cloud access or remaining quota.
- Bounded provider failover, saved-artifact follow-up/reference fixes and scoped
  local AFM context, preserving existing request and evidence gates.
- Native macOS PDFKit/CoreGraphics rendering through PyObjC, with pypdf text
  extraction and the existing OCR/vision routes. Each incoming PDF is processed
  afresh; explicit history retrieval remains available. Page coverage and model
  transcription accuracy remain separate guarantees.
- Reusable offline Research evidence review and explicit Gold curation, including
  retained validation and recoverable publication of reviewed cases.

See the [changelog](../CHANGELOG.md) and the dated
[AFM/PCC conformance observations](SELF_ATTACK_STATUS_2026-09-27.md). AFM's correct
mismatch rejections and PCC's quota-limited coverage retain their native
INCOMPLETE verdicts. Those runs predate the latest failover, Research and PDF
changes; they do not establish full conformance of the complete 0.1.3 source.
Release preparation validates the selected source package separately; building
it does not publish it or change those historical verdicts.

## What 0.1.3 Provides

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
  metadata, and research-contact paths maintained by `@fl0ri0`. Public issues,
  pull requests, support, and review are not currently promised.

Existing capabilities remain available unless they would make installation,
security, or response truth materially unsafe. Optional backends and
modalities remain experimental.

## Source selection and checksums

`scripts/build_release_archive.py` owns the current source allowlist and verifier.
`PUBLIC_DOCS` includes the normative contracts, `SELF_ATTACK.md`, the dated
[September 19 conformance summary](SELF_ATTACK_STATUS_2026-09-19.md) and
[September 25–27 Apple results](SELF_ATTACK_STATUS_2026-09-27.md), causal
telemetry and state-flow diagnostics. The dated summary records the tested
source and scope; packaging it does not establish a new conformance result.
`PUBLIC_CONFIG_PATHS` includes exactly `config/self_attack_corpus.json` and
`config/graph_rebase_shadow_corpus.json` as compact reproducible inputs. Harness
and test code are included through the normal source-tree rules. Raw captures,
production ledgers, local forensic corpora and generated `state/` are excluded;
running conformance creates new local evidence.

`PUBLIC_INTEGRATION_DOC_PATHS` includes the exact PCC setup guide at
`fruth_integrations/shortcuts/README.md`. The bridge's Python sources are selected
through the normal integration source rules; unrelated integration notes are not
included. The user creates or installs the two named Shortcuts as documented.

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

## Supported Environment

The primary tested environment is a recent macOS release on Apple Silicon
with Python 3.11 or newer. Individual local capabilities additionally require
their own backend and model packages. Other operating systems and processor
architectures are not part of the 0.1.3 support promise.

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
- only the prompt, context promoted by Fruth for the current turn, and files or
  Fruth artifacts explicitly selected for that turn are included; unrelated
  files and conversation artifacts are not added automatically;
- recognized images use Codex's native image-input path, while other selected
  regular files are copied into a temporary working directory configured
  read-only for that Codex run;
- one request accepts at most 5 files, up to 100 MiB per file and 250 MiB in
  total; URLs, folders, and symbolic links are rejected;
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

Direct provider API-key management and external providers beyond the documented
ChatGPT and Apple PCC integrations are not part of 0.1.3.

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
