# Saved JSON → actual read → derived HTML

**Run date:** 2026-10-29; export checked 2026-10-29  
**Response:** `resp_1793252268413_53d21e0320fb7`  
**Final frame:** `resp_1793252268413_53d21e0320fb7:frame-3`

## Request

```text
Save a read-check.json with values [17, 142]. Then read the actually saved read-check.json again. Create read-check.html from the read data with a table containing both values and their sum. Use self-contained HTML with embedded CSS and no external resources. Return exactly these two files.
```

## Result

The actually saved JSON contains [17,142]. The derived HTML table contains both values and sum159, with embedded CSS and no external resources. The saved-read chain and output digests match; both branch content reviews passed.

Saved Closure and materialization are fulfilled; no failed or pending work remains. The independent monitor report matches this final frame.

## Saved artifacts

- [20261029T053945Z_chat_text_artifact_gemma4_26b_read-check.json](bundle/assets/files/file-01.json)
- [20261029T054024Z_chat_text_artifact_gemma4_26b_read-check.html](bundle/index.html)

## Portable result

- [Open the portable result](bundle/index.html)
- [Bundle manifest](bundle/manifest.json)

## Scope

This is one observed local-model execution, not a first-attempt reliability estimate or a full conformance matrix. Artifacts and model reports are copied unchanged. No inference or media generation was performed for this export.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
