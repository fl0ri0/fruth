# Fruth Reference Runs

These five examples were executed by Fruth on 2026-09-18. Each package preserves
the actual prompt, result and evidence from its recorded run. They are
human-facing examples, distinct from test fixtures, evaluation corpora and
self-learning state.

A reference run is admitted only when its final response frame, Closure state,
materialization contract, saved artifacts and applicable bundle checks agree.
Media-specific integrity and consumption evidence supplements that runtime truth.

## Curated examples

1. [Echoes of the Pass](reference-runs/2026-09-18-echoes-of-the-pass/README.md) — a
   local exhibition website with two generated mountain images, one English WAV
   narration, HTML, CSS, working relative media links and an openable bundle.
2. [Evening Rain](reference-runs/2026-09-18-evening-rain/README.md) — a newly written
   three-sentence reflection passed to one VoiceDesign audio branch, with verified
   source binding and physical audio integrity.
3. [Lighthouse Audio Roundtrip](reference-runs/2026-09-18-lighthouse-audio-roundtrip/README.md)
   — an original field note, generated WAV and transcription of that exact audio,
   with recorded roundtrip fidelity evidence.
4. [Funny Animal Selfies](reference-runs/2026-09-18-funny-animal-selfies/README.md) —
   three distinct generated images, each inspected by its own vision branch,
   followed by one combined report and digest-bound image-consumption evidence.
5. [Saved JSON → actual read → derived HTML](reference-runs/2026-09-18-saved-json-read-html-verified/README.md)
   — exactly two requested files: JSON containing `[42, 96]` and a self-contained
   HTML table showing those values and `138`. The saved JSON read is bound to the
   consumer and output by recorded identities and digests.

## Package contents

Each directory contains a README, the exact prompt, copied public artifacts, a
sanitized final-response projection, an independent monitor snapshot and a
checksum manifest. Echoes of the Pass and Saved JSON also include portable local
bundles. For the exhibition website, open its `bundle/index.html`; the canonical
HTML copy under `artifacts/` retains the original runtime-relative asset paths.

The packages were gathered with `scripts/export_reference_run.py`. Publication
checks revalidated the final-frame identity, matching monitor evidence, prompt,
source files, package checksums and local bundle links. The canonical response
frames and original saved artifacts remain authoritative. Media was copied from
the recorded runs without regeneration.

These examples establish the recorded outcomes of five prompts. See
[Self-Attack conformance](../docs/SELF_ATTACK.md) and the
[testing protocol](../docs/TESTING_PROTOCOL.md) for coverage definitions and
broader validation requirements.
