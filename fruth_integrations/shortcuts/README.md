# Apple PCC through Shortcuts

This opt-in text and image bridge runs user-installed Apple Shortcuts. It automatically
prefers Cloud Pro and uses Cloud when Pro is unavailable; users need not choose
a tier. **Apple PCC** appears in Models and the startup model list. Start its
instance, then select it using the existing preferred interpretive inference
controls. The backend key is `apple_pcc`, the model key is `auto`, and instances
use `apple_pcc:auto:<port>`. A Python function and command line expose the same
automatic selection. The local `apple_fm:system` backend remains separate.

Apple documents both Cloud and Cloud Pro as
[Private Cloud Compute models in Shortcuts](https://support.apple.com/guide/shortcuts-mac/use-apple-intelligence-in-shortcuts-mchl91750563/mac).
Cloud Pro has extended context, but Shortcuts exposes no exact context size,
model revision or remaining-quota API. Optional macOS 27 Swift discovery queries
`PrivateCloudComputeLanguageModel().contextSize`: this Mac reported **32,768**.
That observation is stored under `backend_metadata.sdk_model`, explicitly scoped
to the SDK default, not the executing Shortcuts tier. Exact Shortcuts context and
variant fields remain unknown. The SDK exposes no PCC variant name or Pro selector.
Language, region, system version, account
access and Apple's usage limits can affect availability.

### Direct terminal access

The installed `fm` CLI accepts only `system`; `fm available --model pcc` is
rejected. The public Swift PCC API is a separate possible transport, but Apple
requires its [managed PCC entitlement](https://developer.apple.com/documentation/foundationmodels/privatecloudcomputelanguagemodel).
A real standalone Swift generation probe on 2026-09-21 terminated with
`Missing entitlement: com.apple.developer.private-cloud-compute`, without a
generated answer. An earlier successful SDK context-size observation does not
grant generation access. The installed public SDK also has no explicit Cloud
Pro selector, so it cannot promise the bridge's Pro-first selection contract.
No direct SDK transport is enabled; Shortcuts remains the working path here.

The existing terminal command invokes one shortcut, waits for its result and
returns control to Fruth. Fruth validates that result and supplies the next
branch-local task and required dependency evidence on the next call. Intermediate
workflow phases remain Fruth state; they do not require a persistent Shortcuts
conversation. Changing transport alone would not establish better model output.

## Use as a Fruth instance

Starting Apple PCC launches only Fruth's loopback adapter on ports 11651–11700;
stopping it stops that owned process, not Apple's services. The card identifies
cloud processing. Sending a turn sends its task, applicable instructions, attached images and selected context to
Apple. Catalog/status observations never generate text or establish account access.

PCC uses the normal Fruth request, handoff, review, promotion and closure paths.
Routing and inference-owned execution receive the **full `FRUTH_INFERENCE.md`**;
the compact local AFM policy does not apply. The adapter preserves ordered system/user/assistant messages in an explicit
text envelope. Image parts are bound to numbered image files supplied alongside
that envelope as Shortcut Input; image bytes are not converted to prompt text. This is role framing, not a native system-message API. Output
correctness and policy compliance still require Fruth's ordinary validation.
The transport envelope does not assign a Fruth role. For interpretive inference,
the existing policy owner supplies the Fruth role and current planning/execution/
review instructions. A direct single-instance tab remains ordinary chat, with
its own supplied messages and no automatic Fruth policy or role.
Embedded requests and schema examples remain context, not replacement tasks.
Inference-owned preparation uses the existing focused task/reference framing
also used for local AFM: the model prepares the current phase's content, while
Fruth executes the later media and file branches. PCC's role instructions state
that Shortcuts transports the model exchange; Fruth performs the downstream branches.
This framing does not apply to direct single-instance chat.

This integration supports **chat and image analysis**, including reading visible
text (model-based OCR), image comparison and document-page analysis through
Fruth's existing PDF path. It advertises no audio input/output, image generation,
native OCR/barcode tools, tool calling, constrained JSON, sampling or output-token controls. Streaming
compatibility delivers the completed answer after Shortcuts finishes; it does not
stream provider tokens. Per-call `pcc_execution` records the shortcut target,
fallback attempts, exact text input digest and ordered image byte digests. A shortcut's configured tier is not a
cryptographically attested model identity.

## Set up the shortcuts

On a compatible Mac with Apple Intelligence, import the provided shortcuts or
create them using the recipe below. A shortcut's presence in the library does
not prove access to its model; availability depends on the options and account
access provided by Apple on that Mac.

### Import

In [current repository builds](https://github.com/fl0ri0/fruth/archive/refs/heads/main.zip),
choose **Set up** on the Apple PCC Models card, or select PCC
in the interactive startup list when it says **setup required**. Fruth checks
the installed names and opens only missing bundled shortcuts on the Mac running
Fruth. Review and click **Add Shortcut** in Apple's import previews. In the web
UI, refresh Models and select Start; in the terminal, press Enter after adding
them. Startup checks installation again before launching the adapter.

Opening a preview does not install a shortcut or establish cloud access. Existing
shortcuts are left alone; duplicate names require manual resolution. Background
status, routing and ordinary model requests never open import previews.
Noninteractive startup skips setup and reports how to complete it in Models.
If using Fruth remotely, complete the native import on its host Mac.

To import manually:

Open [Fruth PCC.shortcut](Fruth%20PCC.shortcut) and
[Fruth PCC Pro.shortcut](Fruth%20PCC%20Pro.shortcut) in the Shortcuts app, review
their actions, then add them. Keep the exact names shown below. If either name
already exists, inspect the existing shortcut first and avoid adding duplicates.

The original 0.1.3 source archive predates these exports and assisted setup.
For that archive, import manually using
the companion `fruth-pcc-shortcuts.zip` from the
[0.1.3 release](https://github.com/fl0ri0/fruth/releases/tag/v0.1.3).
Current repository downloads and subsequent source builds include both files
in this directory. Import remains an explicit user step; Fruth does not install
or replace shortcuts automatically.

### Manual recipe

Only create the model choices exposed by your system:

| Bridge selection | Exact shortcut name | Use Model selection |
| --- | --- | --- |
| `cloud` | `Fruth PCC` | **Cloud** |
| `cloud-pro` | `Fruth PCC Pro` | **Cloud Pro** |

For each shortcut:

1. Add **Use Model** and choose the matching model explicitly.
2. In its prompt field, insert the **Shortcut Input** variable. Do not type the
   words “Shortcut Input” as literal prompt text. The whole prompt is this variable.
3. Expand the action, set **Output → Text**, and turn **Follow Up** off.
4. Add **Stop and Output**, using the **Response** variable from Use Model.
   Leave its “If there's nowhere to output” option at **Do Nothing**.
5. If the input configuration offers “If there's no input,” choose **Stop and
   Respond**, with `BLOCKED: Fruth PCC requires task text as Shortcut Input.`

The input variable receives the UTF-8 text file and any attached image files
passed by the bridge. Keep its type automatic so images remain image content. Do not add a fixed prompt, clipboard input, interactive question, local
model fallback, ChatGPT action or shell action. The bridge sends exactly the
caller's task text and supplied images; the low-level bridge does not inject a
policy or fetch image URLs or model-specified paths. Fruth's ordinary policy owner supplies the policy before the instance
adapter serializes messages.

A single direct user text message passes through unchanged, including in Arena.
When system instructions, conversation history or images are present, the adapter
retains the ordered message envelope and image bindings. Inference-owned requests
therefore keep their full policy and scoped roles. Per-call evidence distinguishes
`plain_user_text`, `text_role_envelope` and `text_role_envelope_with_image_files`.

The installed shortcuts are user-managed. Verify the model setting in the editor
after editing or importing one: the CLI cannot attest that a shortcut still uses
Cloud or Cloud Pro. Keep exactly one shortcut per name to avoid ambiguous dispatch.

## Run from the checkout

List installed choices without sending a cloud request:

```sh
.venv/bin/python -m fruth_integrations.shortcuts.pcc list
```

Create a UTF-8 text file containing the task, then run:

```sh
.venv/bin/python -m fruth_integrations.shortcuts.pcc run \
  --input /absolute/path/task.txt --timeout 120
```

For image questions, add `--image /absolute/path/image.png`; repeat `--image`
to supply multiple images in order. This sends the task text and those images to
Apple's PCC service. The default `--model auto`
tries Pro first. If its shortcut is missing or ambiguous, or Apple returns a
recognized native Pro access, availability or usage-limit error, the bridge uses
Cloud once with the same task text and exact image bytes. No extra generation probe or permanent
eligibility cache is used, so access changes are recognized on the next request.
`--model cloud` and `--model cloud-pro` remain optional diagnostic overrides;
explicit choices do not fall back.

The command prints JSON. `status=completed` includes the returned `output` and
means the shortcut finished with a fresh, nonempty UTF-8 output file. It does not
prove the generated answer is correct or that a Fruth workflow is fulfilled.
Errors exit nonzero and preserve the CLI diagnostic. Missing/ambiguous shortcuts,
CLI connectivity errors, model/account errors, blank output and timeouts stay
distinct. Text starting with `BLOCKED:` is returned as blocked, without output.
`model` identifies the actual final target and `attempts` preserves diagnostics
for both tiers when fallback occurs, without duplicating generated text.

Listing reports installation separately from `access=unknown`. It does not
silently run a model or infer eligibility from an Apple subscription. Execution
is the access check for that particular request. On the test Mac, Cloud Pro's
native error specifically required signing in with an **iCloud+ account**; auto
selection recorded that reason and successfully used Cloud without user input.
Shortcuts provides localized stderr rather than structured eligibility codes.
Known English/German errors are recognized; unknown errors, refusals/guardrails,
invalid output and uncertain timeouts remain failures instead of triggering a
second-model request. If both tiers fail, both failures remain visible.

The native CLI offers no per-call option to suppress error notifications. A Pro
access failure can therefore display a Shortcuts error banner before Cloud
succeeds. Disabling Finder's desktop notifications and sound did not suppress
this banner on the tested macOS 27 system. Do not present that setting as a fix.
Automatic selection retries Pro on each new call so changed account access is
recognized immediately; it can therefore repeat the banner while Pro is unavailable.
Bridge diagnostics retain the actual error and Cloud fallback regardless of the UI.

Python callers can use:

```python
from fruth_integrations.shortcuts.pcc import run_pcc_text

result = run_pcc_text(task_text, timeout_sec=120)
# Optional images are ordered inline base64 data URLs, never filesystem paths.
result = run_pcc_text(task_text, images=[image_data_url], timeout_sec=120)
```

`PCC_SHORTCUT_TIMEOUT_SEC` defaults to 120 seconds and `--timeout`/`timeout_sec`
sets the budget shared by listing and both tier attempts. The subprocess is killed/reaped
on timeout; cancellation of Apple's system-side work is unverified. The bridge
removes its private temporary text, image and output files when the call ends. It rejects
blank task text before starting Shortcuts, never reuses an old output path, and
does not treat stdout or partial output from a failed invocation as a result.

Native token streaming, token usage, native roles, tool calls, TTS/STT, parallel
throughput and unattended/locked-screen execution have not been established. Access through a restricted application sandbox may fail
with “Couldn't communicate with a helper application”; this does not establish
that the selected cloud model is unavailable.

## Images, OCR and scanner boundaries

No additional Shortcut action or permission was needed for image analysis on the
test Mac. Both shortcuts continue to use **Use Model → Text → Stop and Output**.
The CLI accepts the prompt file and real image files as multiple `--input-path`
arguments. Updated instances advertise `chat` and `vision_analysis`; restart old
PCC instances to load the adapter and publish those capabilities. An old running
text-only adapter is not upgraded by a passive metadata read.

Image inputs use ordinary Fruth attachments and vision branches. The adapter
decodes inline base64 and forwards the original image bytes to Use Model. The
declared image MIME type supplies the temporary filename extension; image formats
and frames are interpreted by Apple. There is no additional image library or
PCC format/frame gate. Native image errors remain failed calls. Use Fruth's existing
PDF page handling when individual document pages need separate analysis.
Its existing `PCC_MAX_REQUEST_BYTES` memory budget is 8 MiB; excess input fails
explicitly, without truncating policy or images. Only inline image data URLs are
accepted over HTTP/Python. The CLI's explicit `--image` file inputs are encoded
before entering that same boundary. No remote image fetch or filesystem lookup
is performed from model content. `pcc_execution.image_inputs` binds each supplied
file by ordered index, temporary attachment name, byte count and SHA-256, including
both Pro and Cloud attempts. Fruth's normal `vision_input_evidence` and dependency
checks remain authoritative for its image review branches.

Use a normal image question such as “Transcribe all visible text exactly” for
OCR. This is model output, without the deterministic scanner guarantees or native
`fm respond --tool` controls of the local Apple AI backend. A synthetic QR probe
returned an incorrect URL rather than its encoded payload, so PCC is **not
advertised as a barcode/QR decoder**. Native local OCR/barcode tools remain
separate capabilities. Structured text can be requested normally; Shortcuts'
response formats do not establish a constrained JSON or native tool-call API.

Apple documents [photo inputs to Use Model](https://support.apple.com/guide/shortcuts-mac/use-apple-intelligence-in-shortcuts-mchl91750563/mac)
and [multiple CLI input files](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac).

## Validation and distribution

On macOS 27.0 on 2026-09-21:

- After removing the extra PCC image checks and Pillow, full Fruth vision passed
  again (2.189s), as did ordered PNG/JPEG description and exact OCR (2.487s), with
  unchanged image digests.
- Arena's osmosis prompt failed inside the message wrapper but succeeded as plain
  text. With the single-user passthrough, PCC and local AFM both completed the
  original prompt in the actual Arena UI with canonical saved frames. Native
  failures now retain their error message through streaming socket cleanup.
- The updated adapter passed a full Fruth vision response with canonical saved
  state and the exact supplied image digest (2.632s including Pro fallback).
- Two ordered PNG/JPEG attachments passed image description and exact OCR in
  2.615s. The QR model decode probe failed and is retained as failed.
- These synthetic checks do not replace the user's complete animal workflow.

- Cloud passed three fresh CLI round trips, including the finished Python bridge.
  Generation command durations were approximately 1.38–2.26 seconds.
- One probe returned clean JSON, preserved `Zürich — grüezi`, and calculated
  `1250 + 2750` as `4000`. This is a bounded transport check, not a quality score.
- Cloud Pro was configured but returned Apple's iCloud+ sign-in error. No Pro
  generation succeeded on this account.
- Calling the bare Shortcuts CLI without input hung for 120 seconds despite the
  input policy. Use the bridge's mandatory file input and blank-input guard.
- Automatic selection was tested live: Pro returned its account error in 0.136
  seconds, then Cloud returned the exact fresh test marker in 1.273 seconds.
- The 38 isolated tests in `tests/test_pcc_shortcut_bridge.py` passed without
  invoking real Shortcuts or accessing production Fruth state.

Detailed local probe records are retained in the development checkout and are
not included in the source distribution. The public
[September 25–27 conformance report](../../docs/SELF_ATTACK_STATUS_2026-09-27.md)
records the later integration campaign, evidence identities and quota-limited
coverage without converting its INCOMPLETE verdict into a pass.

The September 21 export attempt reported an iCloud sign-in error, while ordinary
Cloud execution succeeded. The original 0.1.3 source archive therefore shipped the
bridge and manual recipe without exported shortcuts. The companion download
and later repository addition provide the files separately from that archive.
Apple's [CLI guide](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac)
describes invocation, input/output files and signing for redistribution.

For maintainers exporting replacements, use **File → Export → For: Anyone**.
Apple validates a copy through iCloud for public sharing. If export reports that
you must sign into iCloud even though the Mac is signed in, check both
**Shortcuts → Settings → General → iCloud Sync** and
**System Settings → iCloud → See All → Shortcuts**. In the distribution check,
the app setting was on but the system setting was off; enabling system access
resolved the export error. That setting also enables library syncing across
devices. The provided files were exported for Anyone, their two-action workflows
were inspected, and both opened in Shortcuts' import preview without installing
duplicates. Import acceptance does not establish access to Apple's model tiers.

## Usage limits observed during conformance

The September 26–27, 2026 campaign recorded 140 successful Cloud executions
across 127 suite requests before the next request received Apple's error:
“You have reached the usage limit for this model. Please try again later.”
This is an observed campaign count, not a published fixed quota. Earlier usage,
request size and provider accounting are not established by that count.
The same error was subsequently visible in direct Shortcuts execution and a
single-instance Fruth chat. Starting a new chat did not restore access.

The available error did not specify a reset time. Fruth must preserve this
provider failure rather than claim completion. Cloud Pro access fallback does
not bypass the final Cloud tier's quota. See the
[dated conformance results](../../docs/SELF_ATTACK_STATUS_2026-09-27.md) for the
successful scope and untested cases.
