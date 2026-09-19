# Saved JSON → actual read → derived HTML

**Status:** verified Fruth reference run  
**Run and review date:** 2026-09-18  
**Response:** `resp_1789748256967_fcaea6cbf63d38`  
**Final frame:** `resp_1789748256967_fcaea6cbf63d38:frame-2`

## Request

```text
Save a read-check.json with values [42,96]. Then read the actually saved read-check.json again. Create read-check.html from the read data with a table containing both values and their sum. Use self-contained HTML with embedded CSS and no external resources. Return exactly these two files.
```

## Result

The saved `read-check.json` contains only the requested values:

```json
[42, 96]
```

The consumer read those saved bytes and produced self-contained HTML containing
`42`, `96`, and their sum, `138`. The two requested files are the complete artifact
set; the sum is derived in the HTML and is not added to the source JSON.

- [Read the saved JSON](bundle/assets/files/file-01.json)
- [Open the derived HTML table](bundle/index.html)
- [Inspect the portable bundle manifest](bundle/manifest.json)

## Saved-file consumption evidence

The runtime captured the source bytes, their digest and exact producer identity,
then bound that evidence to the HTML consumer and the saved output digest. The
read-only artifact-contract verifier accepted the current files against this
record. Phase identifiers are graph identities: the verified dependency here is
producer `phase-3` → consumer `phase-2`.

```json
{
  "contract": {
    "consumer_branch_id": "branch-text_artifact-1",
    "consumer_instruction": "Create read-check.html from the read data with a table containing both values and their sum. Use self-contained HTML with embedded CSS and no external resources. Return exactly these two files.",
    "consumer_phase_id": "phase-2",
    "consumer_request": {
      "extension": "html",
      "source_name": "read-check"
    },
    "kind": "fruth.saved_file_dependency",
    "producer_branch_id": "branch-text_artifact-2",
    "producer_phase_id": "phase-3",
    "producer_request": {
      "extension": "json",
      "source_name": "read-check"
    },
    "version": 1
  },
  "input_sha256": "183a837aab2d5e5b0a7efbc937af2625ed2a778a4e33f9e23ae4b9ea125d90ac",
  "output": {
    "path": "canonical-artifact:20260918T162018Z_chat_text_artifact_gemma4_26b_read-check.html",
    "sha256": "94dca090157c0d2d345ab326d5054781e7092864a84a3129d0f71c12484f3a5b",
    "size_bytes": 1220
  },
  "read": {
    "artifact_id": "text_7065146270a39644e11b6631",
    "artifact_ref": "artifact:text_7065146270a39644e11b6631",
    "branch_id": "branch-text_artifact-2",
    "consumer_branch_id": "branch-text_artifact-1",
    "consumer_phase_id": "phase-2",
    "encoding": "utf-8",
    "path": "canonical-artifact:20260918T161934Z_chat_text_artifact_gemma4_26b_read-check.json",
    "phase_id": "phase-3",
    "producer_branch_id": "branch-text_artifact-2",
    "producer_phase_id": "phase-3",
    "response_id": "resp_1789748256967_fcaea6cbf63d38",
    "sha256": "0c2d338502a3b8b106815e34004c2234f3b5eb1defa649f737e3dbc4a69ebf4f",
    "size_bytes": 9,
    "source_response_id": "resp_1789748256967_fcaea6cbf63d38",
    "utf8_base64": "WzQyLCA5Nl0K"
  },
  "status": "consumed"
}
```

Both artifact branches record `gemma4:26b` as their executor. The HTML embeds its
CSS and has no external resource dependency. Publication preserves the result's
original bytes and appearance.

## Runtime truth and monitor snapshot

| Evidence | Verified state |
| --- | --- |
| Response lifecycle | `completed`, terminal |
| Late fill | `completed`; zero failed or pending branches |
| Final materialization contract | `fulfilled` |
| Graph Closure | `fulfilled`; no open continuation or actionable repair |
| Surface state | `fulfilled` |
| Saved artifact count | 2 |
| Independent monitor | `clean` for this exact final frame |
| Missing files / SHA mismatches / HTML or CSS issues | zero |

The monitor snapshot was recorded at `2026-09-18T16:22:09.814993Z`. Publication
review rechecked the source files and recorded hashes, as well as existing bundle
hashes and relative links where present. The exporter independently verified the
indexed frame, its terminal state, matching monitor evidence and exact prompt.

## Why this is a reference

This run demonstrates how a later artifact is derived from the actual saved producer bytes, with matching read, input and output evidence before closure.

It is one observed Fruth execution of this prompt. Broader conformance and model
quality claims require their own evidence.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
