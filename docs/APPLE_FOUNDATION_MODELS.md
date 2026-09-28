# Apple Foundation Models

Fruth supports local text generation and image analysis through the installed `fm serve` CLI as the
`apple_fm` backend. The UI calls the backend **Apple AI** and uses Apple's observed
model display name, falling back to **AFM** when metadata is unavailable.
Its required API model is still `system`. Startup and the Models panel also show
the Mac's default AFM variant and context size when the optional native metadata
query succeeds. This sourced host observation is separate from exact-server
identity. A local directory name does not identify a serving model.
Each instance has its own process, loopback port, log and registry identity.
Apple's underlying model resources may be shared; multiple servers do not prove
parallel model execution or greater throughput.

## Setup and UI use

Use a compatible Mac with Apple Intelligence and a macOS installation supplying
`fm`. Check the installed transport before starting an instance:

```bash
fm serve --help
fm license --status
fm available --model system
```

Fruth checks these prerequisites and shows a disabled Apple AI card with the
reason when they are missing. Review Apple's license yourself if needed. Fruth
never accepts licenses, downloads Apple models, enables Apple Intelligence, or
starts/stops Apple's system services. Other backends remain usable without `fm`.
No Python Foundation Models SDK dependency is required.

In the existing Models panel, press the model card's play button under Apple AI. Press it again for
another instance. Each appears separately, for example **AFM 3 Core Advanced · 11601** and
**AFM 3 Core Advanced · 11602** when that variant is observed. Card titles use catalog
metadata; tabs prefer their instance's recorded observation and use catalog metadata
when the older instance has none. Missing or unavailable metadata falls back to
**AFM**. Select a tab to chat with that exact instance. Its stop button
stops only that registered server. Refresh/reload reconciles the same registry and
cached status used by other backends. Unsupported download/remove actions are
not offered for Apple's system model.

The Fruth tab can select Apple AI in interpretive inference preferences. Those
preferences select a model/backend pool; individual model tabs select exact
instances. Apple AI uses the same interpretation, branch handoff, saved-artifact
and response-frame pipeline as the other backends.

Shared processing extracts the accepted branch payload before a TTS handoff and
rebinds generated links to saved artifacts. Markdown narration headings, including
`narration_script` and a narration filename with fenced text, supply only their
spoken body. That text is not proof of generated audio. Multiple narration choices
still require branch selection; missing HTML image elements require content repair
because link rebinding can only repair links that exist.

Attach an image with the composer's **+** controls in an Apple AI conversation,
then ask about its contents. Apple AI also participates in Fruth's ordinary
`vision_analysis` routing and image-evidence paths. PDF attachments in both direct
chat tabs and vision routes use the existing PDFKit/CoreGraphics renderer. Each
selected page reaches the same Apple AI instance as an image; mixed PDFs do not
silently lose their scanned content to text-layer extraction. `pdf_prefer_text`
explicitly requests the existing text layer for ordinary image analysis/chat.
Page caps retain the full document count and a coverage warning. Restart existing Apple AI instances after updating
Fruth so their registered capability metadata includes vision.
The terminal startup catalog uses the observed default model's display name (or
**AFM** when unavailable) under **Apple AI**, with **Chat + Vision**.
When AFM cannot start, the terminal prints the prerequisite failure reason before
the selector instead of silently omitting it. It remains outside the selectable
list until `fm available --model system` reports availability. The selector is a
snapshot; rerun startup discovery after Apple reports the model ready, or refresh
the Models catalog in an already-running Fruth server.

### Default-model metadata

On macOS 27 or newer, model discovery runs the bundled read-only Swift helper
through `xcrun swift`. It reads
[`SystemLanguageModel.default.variant`](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/variant-swift.property),
the variant's `displayName`, and
[`contextSize`](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/contextsize).
The macOS 27 SDK is optional; missing tools, older SDKs, unavailable models,
invalid results and timeouts leave normal `fm` readiness unchanged. The helper
creates no inference session and performs no generation or asset installation.

`backend_metadata.system_model` records `source`, `scope=host_default_model`,
`observed_at`, `os_version`, status, display name, variant identifier and positive
context size. Startup stores this observation alongside the new instance's
existing HTTP metadata. Catalog discovery includes the same source information.
The probe is cached once per Fruth process, including failures; restarting Fruth
rechecks it. Passive status reads and inference never invoke the helper. Its
20-second timeout is `APPLE_FM_METADATA_TIMEOUT_SEC`. Swift's standard SDK module
cache is reused across launches; Fruth does not persist a separate model-metadata
cache. Existing model-server processes can remain running.

A native query on the test Mac on 2026-09-20 reported **AFM 3 Core Advanced**
(`coreAdvanced3`) with **8,192 tokens**. Under a restricted shell sandbox the same
API returned Core 3 with zero context. Fruth retains that incomplete payload as
diagnostic evidence and displays unknown metadata, rather than accepting it as a
usable model identity or zero-token limit. Future variants preserve Apple's
display name and use the identifier `unknown`.

The HTTP adapter still sends `system`; `/v1/models` does not identify its specific
variant. Consequently the host query does not set the server's `model_variant`
or `context_size`, select a variant, or alter inference policy/budgets.

Ordinary backends receive the complete `FRUTH_INFERENCE.md`. Apple AI receives
the expanded common block and current role block from
[`fruth_inference/policies/apple_fm.md`](../fruth_inference/policies/apple_fm.md).
The projection restores more semantic orientation, review distinctions and
phase/evidence duties than the earlier shared 1,232-token estimate. Its execution
policy is about 2,500 estimated tokens before task instructions and context;
estimates are not Apple tokenizer measurements or a context-limit assertion.
Only the actual executing backend selects this projection. Unmarked custom
policy files retain their complete content.

AFM preparation receives a `fruth_bounded_task` and `fruth_promoted_context`, using
the same task/reference distinction as the ChatGPT provider handoff. It writes
the current text payload; the larger workflow remains reference intent and
constraints. Later media production, saved-file reads, inspections and closure
remain Fruth runtime work. The ChatGPT-specific recursion marker is not attached
to AFM. These instructions do not relax evidence gates or prove the model will
follow them. Branch contracts and inputs remain intact; missing/malformed compact
policy fails visibly. Two instances do not pool their context windows.

## Lifecycle and ports

The default AFM range is **11601–11650**, exactly 50 consecutive ports immediately
after llama.cpp's configured maximum. `APPLE_FM_START_PORT` is derived from
`LLAMA_CPP_PORT_MAX`; the existing Ollama/MLX/llama.cpp ranges are unchanged.
Allocation uses the existing free-port helper, registry reservations, and shared
start lock. No separate port-reservation store is introduced.

A registered identity is `apple_fm:system:11601`; its API `request_model` remains
`system`. Logs use `logs/apple_fm_system_<port>.log` and the existing log hygiene.
Startup checks that the owned process holds its listener and that `/health` and
`/v1/models` identify an available `system` model. Failed startup terminates/reaps
only its owned child and removes its own failed registration.

Stop verifies the process birth time and complete launch command before signaling
it. A stale or unverified PID fails visibly. Stack shutdown uses the same AFM
ownership checks, excludes AFM from generic PID/port fallback, and preserves the
registry/status/logs if an AFM stop fails. It never sweeps the AFM range to kill
unregistered listeners. Missing exact request targets return an error.

## Identity, provenance and capabilities

| Fact | Server transport observation |
| --- | --- |
| Backend | `apple_fm`, installed `fm serve` |
| API model | `system` |
| UI labels | Apple AI backend; observed default-model name on cards and instance tabs, with AFM fallback and per-tab port |
| Server variant / exact revision / context size | Not reported by HTTP; separate host-default variant/context observation when available |
| Variant selection | Not exposed |
| Input/output | Text and image input; text output, including incremental streaming |
| Roles | `system`, `user`, `assistant` |
| Controls | `temperature`, `top_p`; explicit output limit maps to `max_completion_tokens` |
| General tool calling, audio, reasoning effort | Not supported by the HTTP adapter; dedicated image tools use the CLI below |

Image requests use inline `image_url` data URLs. Fruth converts its internal
`input_text`/`input_image` parts to the server's `text`/`image_url` wire format,
preserving image bytes, order and user-message history. Remote image URLs and
unsupported content parts fail explicitly. Raw uploaded images receive a media
type based on their byte signature: JPEG stays `image/jpeg`, while rendered PDF
pages stay PNG. Recognized GIF, WebP, BMP and TIFF signatures are also preserved;
this transport label does not guarantee that every backend decodes every format
or every frame. Explicit image data URLs retain their supplied media type and
bytes. No image conversion is performed by this request builder.

Live PNG tests verified one image
and a two-image streamed comparison. The model described the visible shapes and
colors correctly; this is a bounded functional check, not a general accuracy score.
Direct browser chat and a routed image request were checked against canonical
response evidence. Fruth persists the image-dispatch digest and exact instance
in the runtime snapshot so a completed vision phase can satisfy its text output.

Generated-image follow-ups use the shared one-image task prompt, including the
accepted visual criteria and bound artifact reference. A paired check on two
retained conformance images found that the earlier authority/override wording
triggered Apple guardrail errors while concrete task wording completed on both
AFM instances. This changes the handoff wording, not Apple's guardrails, Fruth's
evidence checks, or retry authority. Provider refusals remain failed work; this
bounded check does not establish general visual accuracy.

Apple documents [multimodal image analysis](https://developer.apple.com/documentation/foundationmodels/analyzing-images-with-multimodal-prompting),
including two image attachments in one prompt and analysis of document images.
This establishes image-input support, not direct parsing of arbitrary PDF files
or unlimited document coverage. Fruth renders selected PDF pages and sends them
sequentially as independent image requests to the selected instance. The direct
tab adds no per-page branches or frame instructions; it joins labelled page
answers after generation. The original user prompt and full document page count
accompany each page, within the existing page and timeout limits.

Apple's [guardrails check model input and output](https://developer.apple.com/documentation/foundationmodels/improving-the-safety-of-generative-model-output).
A guardrail error is not evidence of a multi-page or rendering limitation, nor
does it identify the precise triggering input or output. Model-based PDF failures
report the failing page and preserve the count of earlier successful pages in
the canonical failed response and PDF history. They stop without retrying,
switching to OCR, or reporting partial work as a complete document. Native OCR
tool success and successful model-based image analysis are separate outcomes.

A bounded local comparison on 2026-09-27 reproduced a mixed-document guardrail
failure with a single page, with a simpler image prompt, with explicit page
scope, and with both page images in one request. Fresh `fm respond` and direct
FoundationModels API sessions also rejected the same page with default
guardrails and no OCR tools, while a previously successful JPEG still completed
on the same server. The native API reported `May contain unsafe content` with
no further metadata. These observations rule out Fruth's file/page counting or
frame assembly as the cause of that failure; they do not identify its content
trigger or establish a general PDF limitation. No speculative prompt change,
OCR substitution or guardrail relaxation was applied.

A subsequent user-authorized four-page comparison on the same day showed that
prompt wording also matters: the unchanged handwritten page was rejected with
the general whole-document transcription prompt but accepted with the earlier
handwriting-specific prompt. A concrete per-page transcription prompt then
completed all four pages, including the exact letter image rejected in the
earlier mixed-document test. This validates sequential page handoff, not accurate
transcription: visual review found substantial recognition errors and omissions,
including an incorrect date and location. The precise guardrail trigger remains
unknown; neither a World-Sim prompt-injection diagnosis nor reliable verbatim
transcription follows from these tests. Fruth continues to preserve the user's
prompt without automatic rewriting or refusal retries.

### OCR and barcode / QR tools

Apple AI's **Session Controls → Image Mode** offers **Read text (OCR)** and
**Read barcodes / QR codes** when the installed `fm respond --help` advertises
the corresponding tools. Attach an image or PDF and send the request. **Image analysis**
keeps the ordinary model-based description path. Reload Fruth's webserver and
browser after updating; existing model servers can remain running.

The same explicit modes are available through `/api/infer` and `/api/responses`:

```bash
curl http://127.0.0.1:5011/api/responses \
  -F instance_id=apple_fm:system:11601 \
  -F ocr_mode=apple_barcode \
  -F 'input=Read the barcode in this image.' \
  -F file=@/absolute/path/code.png
```

Use `ocr_mode=apple_ocr` for OCR or `auto` for ordinary image analysis. Both Apple
chat and vision instances expose these controls, including in routing metadata.
These are explicit recognition operations: they return the native tool's text
or barcode records, without model rewriting, translation, summarization or URL
navigation. A detected URL is data. PDFs are rendered natively, then passed to
the same tool one page at a time, including PDFs with existing text layers.
Explicit OCR/barcode selection therefore requires rendering even when
`pdf_prefer_text` is set. Results keep their original page numbers, and a failed
page reports an error with receipts for earlier successful pages.

These modes run a fresh, bounded local `fm respond --tool ocr` or `--tool barcode`
session. They do not send tool calls to the selected instance's HTTP port, and
do not expose arbitrary tool registration. The selected Fruth instance remains
the request target; execution provenance explicitly records `fm.respond` and
`local_cli_session`. The call has its own context, uses only the supplied image
and fixed tool instructions, and does not consume the conversation as an OCR
instruction. Chat sampling controls apply to normal chat/image analysis only.

Fruth requires the saved native transcript to contain the expected tool call,
the exact image label and a matching tool result. It returns that result rather
than the model's final prose. An empty result reports no detections; missing,
repeated, mismatched or failed calls are errors. No automatic retry or model-only
fallback is used. The request's inference timeout bounds a single-image child
process; `pdf_page_timeout_sec` bounds each PDF page's child process.
A timeout kills/reaps that CLI child, without signaling model servers or Apple's
system services. Private image/transcript staging is removed after the call.

Canonical responses retain `runtime.apple_fm_image_tool_evidence`: tool name,
call ID, exact tool-result text/digest, input-image digest and transcript attachment
digest. Apple may re-encode the image; the receipt records both byte identities
and `image_reencoded`. Reported asset IDs are preserved without inferring a model
variant. The image dispatch receipt also identifies this CLI transport.

For PDFs, the same canonical evidence field contains a
`fruth.apple_fm_pdf_tool_evidence` aggregate with the original PDF's SHA-256,
full document page count and an ordered `pages` list. Each entry retains its
one-based `page_index` and the native tool's existing image `evidence`. The
renderer supplies pixels; only the native tool transcript establishes OCR or
barcode detections. An empty, verified result counts as processed and explicitly
reports no detections for that page.

A separate closure limitation was observed with the prompt “Transcribe every
page in order”: prompt-only intent analysis classifies it as speech-to-text even
with a screenshot and explicit Apple OCR. A verified OCR result can therefore
coexist with an unrelated pending speech branch (`lifecycle_state=repair_needed`).
The PDF handoff correction does not change that intent/closure behavior; native
recognition evidence alone is not proof of complete request closure.

Initial native probes showed that AFM can skip a tool or invent the attachment
label. Fixed instructions succeeded on the synthetic OCR/QR/blank fixtures;
verification still rejects those failure modes instead of reporting success.

## AFM 3 speech capability versus public access

Apple's [third-generation model report](https://machinelearning.apple.com/research/introducing-third-generation-of-apple-foundation-models)
confirms Core Advanced 3 powers expressive TTS and improved dictation. This model
capability does not establish an accessible speech transport: the installed
`fm serve` returns 404 for `/v1/audio/speech` and `/v1/audio/transcriptions`, and
the inspected Foundation Models SDK exposes no audio input/output API.

An [Apple staff reply](https://developer.apple.com/forums/thread/834149) states
that no new public speech-generation API specific to that model was released.
Apple's [SpeechAnalyzer sample](https://developer.apple.com/documentation/Speech/bringing-advanced-speech-to-text-capabilities-to-your-app)
uses the separate Speech framework; its public API does not establish that a
transcription uses Core Advanced 3. Fruth therefore does not advertise AFM TTS/STT
or substitute older Speech/AVFoundation services under the Apple AI identity.

The [Python SDK](https://apple.github.io/python-apple-fm-sdk/) wraps the same Swift
framework. Its current public [attachment API](https://apple.github.io/python-apple-fm-sdk/api/attachment.html)
supports images, and its [session API](https://apple.github.io/python-apple-fm-sdk/api/session.html)
returns text or structured values. The inspected Python interface has no AFM
audio attachment, speech synthesis or transcription methods. Switching this
backend to the Python SDK would not unlock AFM 3 audio.

## Server metadata

Per-instance metadata records the exact health/models URLs, observation time,
transport-contract observation date and raw reported model entry. Unknown future
fields are retained as reported data without guessing their semantics. `/v1/models`
provided `id`, `object`, `owned_by`, and a `created` value that changed with server
startup; it is not an exact model revision.

A separate native observation supplied for this Mac reported `coreAdvanced3`,
“AFM 3 Core Advanced”, and 8192 tokens on September 20, 2026. That observation is
**not attributed to an `fm serve` instance**. Neither 8192 nor a variant/version
number is hardcoded as a backend property.

## Transport behavior and limits

The installed CLI uses `/v1/chat/completions`. It is a tested subset of that
protocol, not a claim of full OpenAI compatibility. Tests observed incremental
HTTP deltas, a `stop` finish reason and `[DONE]`. The adapter requires both terminal
markers and nonempty text. Malformed events, explicit errors/refusals, missing
markers and incomplete finish reasons fail; partial text cannot fulfill an output.
Results use the existing Fruth output/frame/closure owners.

System instructions and supplied assistant/user history were accepted. A following
request without that history did not remember the prior test secret. Fruth remains
responsible for explicitly supplying each conversation's relevant history.

The server recognizes `temperature` and `top_p`; valid values succeeded and invalid
strings failed. `max_tokens` was ignored by this CLI, so Fruth maps an explicit
limit to `max_completion_tokens`. A limit of one shortened output, but the server
still returned `finish_reason=stop` and counted two completion tokens. That marker
cannot prove semantic completeness or an exact one-token visible answer.

Nonstream responses reported prompt/completion/total token counts, retained in the
raw completion result where the caller accepts it. Streaming usage was not
reported. Fruth's compatibility zero usage counters on those streaming responses
are not measured token counts. No token-counting SDK is added.

Server HTTP errors preserve their diagnostic message through Fruth. Oversized
inputs can still exceed the model's context: scope selection does not enlarge it.
A separate oversized raw prompt returned a guardrail error, so not every large-input
error can be classified as context overflow. Refusals are errors when the transport
identifies them; ordinary model refusal prose has no separate reliable signal.

Closing the upstream stream releases its HTTP connection. It does not establish
that Apple's inference stopped. Fruth's existing response worker can continue
when a browser disconnects, and reconnect/retrieval observes that response. No
Apple system service is stopped as a cancellation mechanism. Timeout, disconnection,
model failure and successful completion remain distinct.

## Reference boundaries and verified environment

Observed on macOS **27.0 (26A428)** with the active macOS SDK **27.0**, using
`/usr/bin/fm`. This CLI does not expose `--version`. Its help offered host, port and
socket binding and only the model `system`; no variant selection option was
present. The project virtual environment had no `apple-fm-sdk` installed.

Apple's [SystemLanguageModel](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel),
[variant](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/variant-swift.property),
and [Variant](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/variant-swift.struct)
references distinguish model availability and variant information, including
`core3`, `coreAdvanced3` and display names. They do not establish what this CLI
server exposes. The read-only framework property is not a server selection knob.

[LanguageModelSession](https://developer.apple.com/documentation/foundationmodels/languagemodelsession),
[content generation](https://developer.apple.com/documentation/foundationmodels/generating-content-and-performing-tasks-with-foundation-models),
[contextSize](https://developer.apple.com/documentation/foundationmodels/systemlanguagemodel/contextsize),
and [context management](https://developer.apple.com/documentation/foundationmodels/managing-the-context-window)
cover framework sessions and context. Framework streaming snapshots must not be
mistaken for this CLI's observed incremental HTTP deltas.

The official [Python SDK documentation](https://apple.github.io/python-apple-fm-sdk/)
and [repository](https://github.com/apple/python-apple-fm-sdk) are supplemental
references for model availability, sessions, generation options and errors.
Their examples and APIs are not an installed CLI capability guarantee. In
particular, generation-control examples must be checked against the corresponding
constructor/method signature. No Python or Swift inference path was introduced.

[Private Cloud Compute](https://developer.apple.com/documentation/foundationmodels/adding-server-side-intelligence-with-private-cloud-compute)
is separate from the local `apple_fm:system` integration, which has no automatic
cloud fallback. An explicit [Shortcuts text bridge](../fruth_integrations/shortcuts/README.md)
now prefers Cloud Pro automatically and uses Cloud on a confirmed Pro
availability/access error. This was verified on the test Mac: Pro returned an
iCloud+ sign-in requirement and Cloud completed the request. The **Apple PCC**
card registers a normal `apple_pcc:auto:<port>` text instance and is eligible for
the existing preferred-II controls. Inference-owned calls receive the full
canonical policy and scoped Fruth roles; direct chat gets neither automatically.
The compact local AFM policy does not apply. An optional native PCC SDK observation reported
32,768 context tokens; the exact Shortcuts tier's limit and variant remain
unreported. See the bridge guide for role framing, lifecycle and cloud boundaries.

See the [testing protocol](TESTING_PROTOCOL.md#apple-foundation-models-backend)
for repeatable validation. Browser checks exercised two instances, interpretive
text, JSON-to-HTML branch handoff, actual saved-file reads and a committed successor
frame. These establish transport and runtime integration; generated content still
needs verification against the request, as it does with every backend.
