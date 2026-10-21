# Fruth Reference Runs

These five workflows were executed by Fruth on **October 18, 2026** and exported
from their existing evidence on October 21. Each package contains the actual
prompt, completed final frame, matching clean monitor record, saved artifacts and
checksums. These are human-facing examples, separate from test fixtures,
evaluation corpora and self-learning state.

## Curated examples

1. [Echoes of the Pass](reference-runs/2026-10-18-echoes-of-the-pass/README.md) —
   HTML/CSS, two generated mountain images, one English WAV narration and an
   openable local bundle with verified relative links and fulfilled Closure.
2. [Evening Rain](reference-runs/2026-10-18-evening-rain/README.md) — a written
   three-sentence reflection and one WAV, with exact TTS source binding and
   physical audio integrity evidence.
3. [Lighthouse Audio Roundtrip](reference-runs/2026-10-18-lighthouse-audio-roundtrip/README.md)
   — a two-sentence note, generated WAV and transcription of that audio. The
   transcript matches after lexical normalization, with a punctuation difference.
4. [Funny Animal Selfies](reference-runs/2026-10-18-funny-animal-selfies/README.md)
   — three generated images and three separate vision consumers, each bound to
   the actual supplied image digest, followed by the recorded combined inspection.
5. [Saved JSON → actual read → derived HTML](reference-runs/2026-10-18-saved-json-read-html-verified/README.md)
   — exactly two files: JSON with `[17, 144]` and a self-contained HTML table with
   both values and `161`. Saved-input consumption and output digests are recorded.

## Package contents and scope

Each package includes its README, exact prompt, copied artifacts, sanitized
response projection, independent monitor snapshot and checksum manifest. Echoes
and Saved JSON also include portable bundles; open `bundle/index.html` for those
results. Canonical HTML under `artifacts/` retains its original runtime-relative
asset paths. Media was copied without regeneration.

The existing `scripts/export_reference_run.py` admits the exact final frame,
Closure, materialization, monitor identity, artifact bytes and applicable bundle
links. The original runtime evidence remains authoritative. The 13 saved artifact
files and all five packages were verified during this refresh. Model-authored
visual descriptions remain interpretations even when image consumption is proven.

Evening Rain and Lighthouse preceded the October 18 Echoes continuation fixes;
the other three runs followed them. All five precede the October 19 image
idle-residency fix. Earlier Echoes attempts and the previous public reference
packages remain historical evidence; these five selected outcomes do not establish
a first-attempt success rate or a controlled performance comparison.

See the [October 21 validation status](../docs/SELF_ATTACK_STATUS_2026-10-21.md)
for the complete local, AFM and PCC Cloud campaigns and their source identities.
Reference success supplements conformance; it does not replace the full matrix.
The [Self-Attack guide](../docs/SELF_ATTACK.md) and
[testing protocol](../docs/TESTING_PROTOCOL.md) define broader validation scope.
