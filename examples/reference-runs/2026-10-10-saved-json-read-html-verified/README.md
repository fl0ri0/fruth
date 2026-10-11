# Saved JSON → actual read → derived HTML

**Status:** verified Fruth reference run  
**Run and review date:** 2026-10-10  
**Response:** `resp_1791661769853_751c21357a7928`  
**Final frame:** `resp_1791661769853_751c21357a7928:frame-2`

## Request

```text
Save a read-check.json with values [42,96]. Then read the actually saved read-check.json again. Create read-check.html from the read data with a table containing both values and their sum. Use self-contained HTML with embedded CSS and no external resources. Return exactly these two files.
```

## Result

Exactly two files were saved. The JSON contains `[42, 96]`; the derived HTML displays both values and their sum, `138`. The consumer read is bound to the saved JSON bytes and producer identity, and the resulting HTML has its own checked digest.

## Saved-file consumption evidence

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
    "path": "canonical-artifact:20261010T195252Z_chat_text_artifact_gemma4_26b_read-check.html",
    "sha256": "029e2fee54dcbc9b87f332c3ea956cb3f8c731211cc1fa3f720c7843ab7918d7",
    "size_bytes": 1815
  },
  "read": {
    "artifact_id": "text_cbcc1e77dd448dfadfdf9d84",
    "artifact_ref": "artifact:text_cbcc1e77dd448dfadfdf9d84",
    "branch_id": "branch-text_artifact-2",
    "consumer_branch_id": "branch-text_artifact-1",
    "consumer_phase_id": "phase-2",
    "encoding": "utf-8",
    "path": "canonical-artifact:20261010T195122Z_chat_text_artifact_gemma4_26b_read-check.json",
    "phase_id": "phase-3",
    "producer_branch_id": "branch-text_artifact-2",
    "producer_phase_id": "phase-3",
    "response_id": "resp_1791661769853_751c21357a7928",
    "sha256": "0c2d338502a3b8b106815e34004c2234f3b5eb1defa649f737e3dbc4a69ebf4f",
    "size_bytes": 9,
    "source_response_id": "resp_1791661769853_751c21357a7928",
    "utf8_base64": "WzQyLCA5Nl0K"
  },
  "status": "consumed"
}
```

## Portable result

- [Open the portable HTML result](bundle/index.html)
- [Bundle manifest](bundle/manifest.json)

## Runtime truth and monitor

The final response is terminal and completed. Late Fill, the materialization contract, Closure and surface state are fulfilled, with no pending or failed branches. The independent monitor reports `clean` for this exact final frame; no missing files, hash mismatches or HTML/CSS issues were reported.

The monitor report was recorded at `2026-10-10T20:21:12.076759Z` after execution, during backlog reconciliation. Source artifacts were rechecked during this export.

Monitor phase timings are diagnostic observations, not a benchmark. Backfilled event-window fields can include another response’s activity (the Echoes image-wave end is later than its own terminal output); these phase-duration fields are retained as observed but are not used to admit a reference or compare performance.

## Scope

This is one recorded local execution of the exact prompt. It supplements the dated conformance results; it does not establish a general success rate or a new AFM/PCC verdict. The original response frame and runtime artifacts remain authoritative.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
