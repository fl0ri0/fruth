# Fruth Reference Runs

These five selected workflows were executed by Fruth on **October 27 and29, 2026**.
Each package preserves the actual prompt, completed final frame, matching clean
monitor record, saved artifacts and checksums. These are human-facing examples,
separate from test fixtures, evaluation corpora and self-learning state.

## Curated examples

1. [Echoes of the Pass](reference-runs/2026-10-27-echoes-of-the-pass/README.md) —
   HTML/CSS, two generated mountain images and English WAV narration, with an
   openable local bundle and verified relative links.
2. [Evening Rain](reference-runs/2026-10-27-evening-rain/README.md) — a three-sentence
   reflection and one WAV, with exact TTS source binding and audio integrity evidence.
3. [Lighthouse Audio Roundtrip](reference-runs/2026-10-27-lighthouse-audio-roundtrip/README.md)
   — a two-sentence note, generated WAV and transcription of that audio. The
   transcript matches the spoken source after lexical normalization.
4. [Funny Animal Selfies](reference-runs/2026-10-29-funny-animal-selfies/README.md)
   — three images, three individual image analyses and their complete combined report.
5. [Saved JSON → actual read → derived HTML](reference-runs/2026-10-29-saved-json-read-html-verified/README.md)
   — `read-check.json` with values **17,142**; `read-check.html` contains both
   values and sum **159**, with embedded CSS. Saved-file readback, both content
   reviews and final Closure are verified.

## Package contents and scope

Each package includes its README, exact prompt, copied artifacts, sanitized
response projection, independent monitor snapshot and checksum manifest. Echoes
and Saved JSON include portable bundles; open `bundle/index.html` for those
results. Canonical HTML under `artifacts/` retains its original runtime-relative
asset paths. Media was copied without regeneration.

The existing `scripts/export_reference_run.py` admits the exact final frame,
Closure, materialization, monitor identity, artifact bytes and applicable bundle
links. All five packages and their 13 saved artifact files were verified during
this refresh. Original runtime evidence remains authoritative; model-authored
visual descriptions remain interpretations.

The Echoes portable export was corrected on October 30 after a CSS image reference
retained its old filename during export. Its canonical artifacts and execution
evidence are unchanged. The exporter now rewrites supported references in all
bundle files and checks the actual exported dependencies before recording success;
a prior manifest's link status alone is insufficient. This is a static check of
the existing bundle owner's supported HTML, CSS, JavaScript and JSON references,
not browser execution or validation of dynamically constructed URLs.

The October 29 saved-file and image-report packages now also include
`evidence_bindings` in `response.json` (projection refreshed October 30):

- `semantic_reviews` identifies the saved review generation and instruction
  digest, its source artifact version, and the recorded Closure acceptance.
- `saved_file_reads` links producer bytes to the consumer artifact. At export,
  the recorded read bytes are compared with the published source. The consumer
  input digest is retained as recorded, without claiming to recompute that input.
- `image_reports` links each image digest to its individual saved report and its
  exact contribution in the delivered text.

This is a small allowlisted projection of saved evidence, with package-relative
paths. It excludes raw frames, model instructions and internal derivations.
`availability: not_recorded` means the selected family has no record in the
exported source; it does not establish whether that activity was required or
performed. Older packages without this optional section remain valid.

The portable verifier checks artifact versions, report digests and report placement.
It cannot authenticate the omitted runtime records or independently establish
that a model's interpretation is correct. Recorded review acceptance and physical
file checks remain distinct. Use `python scripts/export_reference_run.py
--verify-only examples/reference-runs/<package>` to check a package locally.

These are selected successful outcomes, not a first-attempt success-rate estimate
or a controlled performance comparison. The three audio/site examples retain
October 27 executions. The image-report and saved-file examples were refreshed
on October 29 after their respective runtime corrections; earlier attempts remain
retained privately. Model-authored descriptions are copied unchanged.

The [current validation status](../docs/SELF_ATTACK_STATUS_2026-10-31.md)
records the bounded property-based investigation round, matching offline gate and
source-bound local, AFM and PCC results. Reference success supplements conformance;
it does not replace the full matrix. See the [Self-Attack guide](../docs/SELF_ATTACK.md)
and [testing protocol](../docs/TESTING_PROTOCOL.md) for scope.
