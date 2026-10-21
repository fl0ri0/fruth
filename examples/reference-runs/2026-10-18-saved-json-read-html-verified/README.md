# Saved JSON → actual read → derived HTML

**Status:** verified Fruth reference run  
**Run date:** 2026-10-18; export verified 2026-10-21  
**Response:** `resp_1792350516834_3dfaa65a1700f8`  
**Final frame:** `resp_1792350516834_3dfaa65a1700f8:frame-2`

## Request

```text
Save a read-check.json with values [17, 144]. Then read the actually saved read-check.json again. Create read-check.html from the read data with a table containing both values and their sum. Use self-contained HTML with embedded CSS and no external resources. Return exactly these two files.
```

## Result

Exactly two requested files were saved. The JSON contains `[17, 144]`;
the HTML table contains both values and their sum, `161`. The actual saved
JSON read and HTML output are bound to the consumer by the retained evidence.

## Saved artifacts

- [JSON artifact](bundle/assets/files/file-01.json)
- [HTML artifact](bundle/index.html)

## Portable result

- [Open the portable HTML result](bundle/index.html)
- [Bundle manifest](bundle/manifest.json)

## Recorded binding and integrity evidence

These records establish input/output binding; semantic accuracy remains
a separate question.

```json
{
  "saved_file_read_evidence": [
    {
      "artifact_id": "text_7ba2e93fd348e829239ad3ff",
      "artifact_ref": "artifact:text_7ba2e93fd348e829239ad3ff",
      "branch_id": "branch-text_artifact-2",
      "consumer_branch_id": "branch-text_artifact-1",
      "consumer_phase_id": "phase-2",
      "encoding": "utf-8",
      "path": "canonical-artifact:20261018T191030Z_chat_text_artifact_gemma4_26b_read-check.json",
      "phase_id": "phase-3",
      "producer_branch_id": "branch-text_artifact-2",
      "producer_phase_id": "phase-3",
      "response_id": "resp_1792350516834_3dfaa65a1700f8",
      "sha256": "01b1bf6853392c0268490288dbffae8681d960b8d00bd32a4cadf12f25fab5e0",
      "size_bytes": 10,
      "source_response_id": "resp_1792350516834_3dfaa65a1700f8",
      "utf8_base64": "WzE3LCAxNDRdCg=="
    }
  ],
  "saved_file_consumption_evidence": [
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
      "input_sha256": "c0573bc34aa146a1ad2bf500765163ae5864f160760c48f9162852a25be19e05",
      "output": {
        "path": "canonical-artifact:20261018T191156Z_chat_text_artifact_gemma4_26b_read-check.html",
        "sha256": "7433cf22fae86f944baf90bf679ff3e36a989dd46f8d535e207a4ac87f6145f4",
        "size_bytes": 2087
      },
      "read": {
        "artifact_id": "text_7ba2e93fd348e829239ad3ff",
        "artifact_ref": "artifact:text_7ba2e93fd348e829239ad3ff",
        "branch_id": "branch-text_artifact-2",
        "consumer_branch_id": "branch-text_artifact-1",
        "consumer_phase_id": "phase-2",
        "encoding": "utf-8",
        "path": "canonical-artifact:20261018T191030Z_chat_text_artifact_gemma4_26b_read-check.json",
        "phase_id": "phase-3",
        "producer_branch_id": "branch-text_artifact-2",
        "producer_phase_id": "phase-3",
        "response_id": "resp_1792350516834_3dfaa65a1700f8",
        "sha256": "01b1bf6853392c0268490288dbffae8681d960b8d00bd32a4cadf12f25fab5e0",
        "size_bytes": 10,
        "source_response_id": "resp_1792350516834_3dfaa65a1700f8",
        "utf8_base64": "WzE3LCAxNDRdCg=="
      },
      "status": "consumed"
    }
  ]
}
```

## Runtime truth and scope

The final frame is completed, with fulfilled materialization and Closure and no
pending or failed branches. Its exact-frame monitor verdict is `clean`, recorded
at `2026-10-18T19:13:10.672317Z`. Saved bytes and package checksums were
rechecked during export; the original frame and monitor record remain unchanged.

This run followed the October 18 Echoes continuation corrections.
All five October 18 references therefore do not share one identical source
revision. They also precede the October 19 image idle-residency fix.

This is one recorded local workflow. It does not establish a general success
rate, a controlled performance comparison, or an AFM/PCC verdict. No inference
or new content generation was performed for this export.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
