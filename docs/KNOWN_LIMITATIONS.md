# Known Limitations in Fruth 0.1.3

This list records current limits of the 0.1.3 source package.
It is not a roadmap or a general backlog.

## Platform and Packaging

- The primary tested platform is macOS on Apple Silicon. Windows, Linux, and
  Intel Mac behavior is not guaranteed for 0.1.3.
- Distribution is a source archive. It is not a signed or notarized macOS app,
  a container image, or a package-manager release.
- Backend packages and model weights are not bundled. A capability can be
  listed but remain unavailable until its local backend and model are
  installed.
- PDF page rendering for local OCR/vision requires macOS and the Quartz Python
  binding from `requirements.txt`. Other platforms retain text-layer extraction
  with `pypdf`, but have no supported local page renderer. A text layer alone
  cannot cover scanned pages or text embedded in images. File-aware external
  agent routes receive the original PDF under their existing sharing controls.
- Rendering and OCR are separate: a successfully rendered page is not proof of
  recognized text. Page limits and OCR failures remain visible in counts and
  warnings; password-locked or unreadable PDFs fail explicitly. Python environments
  that sandbox access to macOS application frameworks may prevent PDFKit from
  initializing; native rendering tests need access to those system services.
- The bundled Fruth skill is Codex-specific in 0.1.3 and must be copied into
  the user's Codex skills directory manually; marketplace/plugin distribution
  and other agent integrations are outside this release.
- The dashboard currently requests Google Fonts, Axios, and Font Awesome from
  external CDNs when opened with network access. The architecture diagram also
  requests JetBrains Mono from Google Fonts. The standalone `site/` landing
  page uses bundled local assets and does not make those requests.

## Runtime

- Fruth is intended for local, single-user operation. Remote exposure and
  multi-user isolation are not supported.
- Flask remains the current control-plane implementation.
- Optional models and modalities can be unavailable or degraded. This is
  acceptable only when status and recovery evidence remain truthful.
- Model output quality and latency are provider-dependent and are not
  deterministic.
- Ordinary finalizer Artifact Registry/frame-persistence errors are currently
  logged and swallowed. A successful HTTP response, completed lifecycle or
  in-memory frame alone does not prove durable commit. Inspect matching durable
  frame/CAS and saved artifact evidence; Readiness retention is secondary and
  cannot repair this guarantee. See the
  [finalization boundary](RESPONSES_CONTRACT.md#finalization-and-durable-completion).

## Apple AI and Apple PCC

- Local Apple AI requires a compatible Mac, available Apple Intelligence and
  the installed `fm` command. Language, region and system configuration affect
  availability; Fruth does not download or enable the Apple system model.
- Apple PCC requires the user-installed Shortcuts in the
  [PCC setup guide](../fruth_integrations/shortcuts/README.md). Its loopback adapter
  can be running while cloud access is unavailable or usage-limited. Fruth has
  no authoritative remaining-quota or reset-time API.
- The dated AFM/PCC campaigns retain their INCOMPLETE coverage verdicts. They
  predate later 0.1.3 changes; see the
  [Apple conformance observations](SELF_ATTACK_STATUS_2026-09-27.md).
- PDF page dispatch and model transcription quality are separate. The observed
  four-page AFM response contained reading errors despite complete page coverage.
  Native OCR tool receipts establish execution/source binding, not perfect text
  recognition. Model safety refusals remain failures without an OCR bypass.
- Automatic provider failover is bounded and respects input compatibility,
  explicit targets/locks and refusal/evidence gates. It does not promise recovery
  from every failure or switch producers after streamed content has begun.

## Optional ChatGPT Route

- The ChatGPT execution route uses Codex, is optional and cloud-based, and must
  be explicitly enabled. It accepts a prompt plus files or Fruth artifacts
  explicitly selected for the current turn. Referential turns may also include
  context promoted by Fruth's context gate, but the provider response is text
  only.
- Fruth can reuse authentication owned by the ChatGPT app or Codex CLI, but it
  cannot guarantee that the app's internal executable location will remain
  unchanged. Discovery fails closed and then tries the documented fallback.
- Automatic model selection means the invoked Codex executable chooses its
  current default. Fruth neither receives the exact GPT variant nor mirrors
  the model selected in an already open ChatGPT conversation. Model prose is
  not authoritative identity evidence.
- The dashboard's ChatGPT tab is an external conversation target. It has no
  local lifecycle controls and is intentionally excluded from Start, Stop,
  Pull, Delete, and Arena.
- Direct ChatGPT tab turns are ephemeral and independent. Displayed history is
  retained for inspection. For referential turns, Fruth may promote bounded
  relevant context into the current request, but it does not resume a hidden
  provider session or resend the entire conversation automatically.
- Recognized images are attached through Codex's native image-input path.
  Other selected regular files are only made available inside a temporary
  working directory configured read-only for the Codex run. Acceptance does
  not guarantee that every document, audio, binary, or other file format can be
  interpreted semantically by the selected model and its available tools.
- The fixed request limits are 5 files, 100 MiB per file, and 250 MiB in total.
  URLs, folders, and symbolic links are not accepted.
- Direct API-key management remains outside this optional route's 0.1.3 contract.
  Apple PCC is a separate integration with its own availability and sharing rules.

## Compatibility

- No compatibility is promised for private, saved, or historical builds that
  predate 0.1.0.
- Public `0.x` interfaces may evolve as the runtime contracts mature.

See [Release Scope](RELEASE_SCOPE.md) for the supported 0.1.3 release boundary.
