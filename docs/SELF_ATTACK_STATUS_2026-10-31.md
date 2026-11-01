# Fruth validation status — October 31, 2026

This report separates completed, source-bound observations from release-package
validation. The 0.1.9 changes build on the bounded semantic-core and Hypothesis
work shipped in 0.1.8; they do not claim a new universal proof or a new live matrix.

## Changes and observed validation since 0.1.8

- Responsibility extraction separates preparation, evidence, Closure,
  materialization, continuation, durable commit and operator projections behind
  existing contracts. Its final recorded source passed 380 offline cases in 38
  profiles, 198 owner checks and the matching source/evidence checker.
- Process startup/cleanup ownership, Whisper request admission and Python
  bootstrap checks received bounded regressions. Codex route documentation now
  states the actual boundary; selected inputs do not imply strict read confinement.
- Native PDF preparation runs in owned bounded child processes. The later macOS
  temporary-path correction passed 120 focused/API tests plus four subtests and
  88 native tests. It preserves strict workspace identity and cleanup checks.
- PDF continuation now keeps generated OCR output separate from selected edit
  authority and preserves the phase of an existing repair branch. The corrected
  source passed 1,539 distinct tests and 604 subtests, with matching dependency
  evidence and no recorded isolation violations.
- Two user-run PDF requests on October 31 were independently checked through
  canonical frames, Ledger readback and exact saved Markdown. Both completed
  with fulfilled Closure and no pending Late Fill: a three-page mixed document
  and a four-page scanned document. A page-local prose inconsistency remains a
  model-quality limitation, separate from successful processing and persistence.
- The operator reports successful Flux 3 generation in both the direct tab and
  Fruth using MLX-VLM 0.7.11 and the native prompt upsampler. This is a targeted
  observation, not an independently inspected image conformance campaign.

The refactoring gate used selected source-map digest
e7fad1f96e08ddab38f81214521b2e5038032a68564f93d72f67245a432eaff4.
The later PDF continuation checks used
4cd314073c1616cf47858558149d3acb59227eb87e05b9b27dc7c29777953e24.
These identities precede 0.1.9 release metadata. The package's
validation/receipt.json and validation/constraints.txt record the exact source,
environment and successful maintained jobs used for release validation. The full
offline gate and source/evidence checker have separate retained completion
receipts; neither historical results nor this prose substitutes for those checks.

## Inherited 0.1.8 investigation and live evidence

The results below keep their original revisions and dates. No full local, AFM or
PCC live matrix was repeated for the responsibility/PDF changes.

## Investigation and resulting guarantees

Bounded Hypothesis studies, deterministic counterexamples and native-owner
replays examined meaning preservation through saved-file consumption and
readback, request intake, content-evidence coverage, review cancellation and
conditional continuation. Separate finite dependency studies examined which
formal constraints follow from others. These approaches answer different
questions and their case counts are not interchangeable.

Independent requirements, exact physical bytes and source/target identities were
used to distinguish successful execution from unsupported completion claims.
The round led to explicit content-review duties, strict review-reference checks,
preserved caller authority/policy, fresh control-time Closure accounting and
bounded continuation of independently owed work. Later source follow-ups corrected
scoped output exclusions, filename intake, terminal-link applicability, exact-target
syntax repair and complete delivery of separate image reports.

The completed studies have declared finite domains and controlled provider output.
They do not establish a universal semantic verifier, general model comprehension,
unconditional progress or a minimal set of implementation requirements. Local
formal derivations did not justify deleting substantive runtime safeguards.
Maintained regression tests and the [testing protocol](TESTING_PROTOCOL.md)
provide the executable validation routes; generated research campaigns remain
explicit opt-ins.

## Recorded results

| Evidence | Result | Scope |
| --- | --- | --- |
| Final reference-fix regression selection, October 28 | 1,995 tests and 898 subtests passed; zero isolation violations | Common recorded source for all three reference corrections |
| Reference-fix offline gate, October 28 | 380/380 cases, 38 profiles; 198 owner checks in five groups; no findings/incompletes | Corrected runtime; source/evidence checker accepted |
| Local live matrix, October 26–27 | Original 169 PASS/1 INCOMPLETE; linked two-case recovery 2/2 PASS | Missing audio-binding cell has passing recovery evidence on the same recorded source |
| AFM live matrix, October 27 | Original 167 PASS/3 INCOMPLETE; linked recovery 4/4 PASS | Three missing cells have passing recovery evidence on the same recorded source |
| PCC Cloud, October 26 and28 | First 100/100 PASS; remaining 70/70 PASS | All 170 distinct case positions covered across two documented source epochs |
| Targeted local references, October 29 | Image reports and JSON/read/HTML both completed | Corrected source; three report contributions and both file content reviews verified |
| PCC Cloud Pro | Untested | No Cloud Pro conformance claim |

The local audio mismatch was correctly rejected. AFM initially recorded an audio
mismatch and a provider safety refusal with its blocked dependent case; the
selected retries passed without changing the source or weakening checks. These
observations do not establish the cause of the provider refusal or a first-attempt
success rate. Native subset verdicts remain INCOMPLETE for the whole matrix even
when every selected case passes. No combined native full-matrix verdict was
computed for the local/AFM recovery sets in this round.

PCC's failed intervening attempts are retained separately. The later correction
restored Pro-to-Cloud fallback for the observed generic Shortcuts error using
request-correlated native access-rejection evidence. The remaining 70 passed after
that correction and the AFM discovery compatibility fix. This is 170 passing case
positions across source versions, not a uniform-current-source 170-case pass.
Case counts are not provider request counts or evidence of Apple's quota policy.

Conformance PASS concerns the checked runtime contracts: a truthful blocked
response can satisfy a safety check. It does not guarantee every answer's
usefulness or factual accuracy. The [conformance guide](SELF_ATTACK.md) explains
matrix scope, budgets and native verdicts.

## Source chronology

The local/AFM campaigns, their targeted recoveries and PCC's first 100 used runtime
digest `98d1aa9848accab876f346d61d16f6775fb22b6f9647f236b11ecc867c571dba`.
PCC's remaining 70 used `10998e803511812bddea3b1f6699ed510aefb6005d37c60957910164b73b181b`
after the Apple compatibility corrections.

The later reference corrections passed the offline gate with runtime digest
`06476d5e6a07f55b422b2635e7fc87c5a92a50168b9fbcc1e570dfcdddc38fb2`
and selected 579-file source map
`7450fec4356222e4dff973d0edca590dfcb3972066b8658867712f0953addb26`.
The checker verified exact source/corpus/profile/evidence bindings and hashed
27,242 retained evidence files. Release metadata, documentation and public-example
exports were prepared afterward; original tested-source hashes remain unchanged.
Portable replay fixtures were derived during packaging and checked separately;
original witnesses remain retained.
No full live matrix was repeated after the reference corrections.

The normal local configuration used Gemma4:26b preferred interpretive inference
with MLX Gemma E4B fallback. AFM and PCC used their respective two-instance Apple
configurations without an explicit interpretive fallback. Image/audio/embedding
helpers were separately supplied by MLX Z-Image, Qwen3TTS, Whisper and Ollama
EmbeddingGemma2. PCC Cloud did not itself generate the image or audio artifacts.

## Current reference examples

[Five public packages](../examples/README.md) preserve exact prompts, final frames,
matching monitor records and verified saved artifacts. Echoes, Evening Rain and
Lighthouse retain their October 27 executions. The image-review and saved-file
packages now use October 29 executions.

The latter image run delivers all three bound analysis contributions exactly once;
model descriptions remain interpretations. The file run saves `[17,142]`, reads
those actual bytes, and produces a self-contained HTML table with sum 159. Both
producer and consumer reviews are accepted and canonical recovered Closure has
no unresolved content duties. This run did not need syntax repair; the repair
path has separate offline dispatch/persistence acceptance evidence.

## Evidence identities

These names identify retained operator evidence, not files shipped in the source
archive. Hashes bind observations without implying third-party replication.

| Evidence | Run ID | Results SHA-256 |
| --- | --- | --- |
| `full-conformance-local-20261026/live` | `95aa5e40e3d14892ba041e654cdea6ed` | `69b0c47220cf62e54a7d1e1b0aa1f84ee06f618a5739f497d8ec6cbdb1798a70` |
| `local-evidence-recovery-20261027/live` | `f0988d1afa6e46508a4b4dd201387a98` | `b13f8df94b76feaac07996139a94c79f177a8603256aef8d3e0d5f485150145c` |
| `full-conformance-afm-20261027/live` | `5af0d249e47345239da9f34e244a7a34` | `5f31d91f222b3aa3ec90c8856eae370852259c2dbece2406909e3be31aa4bfb7` |
| `afm-recovery-20261027/live` | `e528dfa9833f4e8fbf78a94223e6b965` | `578bc37b35dafa9b064f8bde44bf6f5b8f1b3f1e77a425fbb66244a2526c6ff6` |
| `full-conformance-pcc-20261026/window-01` | `c84021496ea044569334182094d64272` | `884a9a30aa48fe662203783b2b788761c89a74ab3899e9985cde855af43cf2d8` |
| `full-conformance-pcc-20261026/window-02-r4` | `a97b5d2750604ff18aed3f045f85a763` | `78c458cf6274265003e8e6fe36b2dcbfb8a425a8da0566481b35c9f1253dbe90` |
| `offline-reference-improvements-20261028T210940Z` | `3c5fa6d3f6664dde88980048199dafa0` | `1966cdddf2efa05d5fcbcfe95f1b17de417238536607bab2ba045364304926d6` |

## Historical results

This is the single current public status report. Previous published releases keep
their original reports and evidence scope; private original copies are retained.

- September 19: complete deterministic 380-case and live 170-case passes.
- September 25–27: AFM 168 PASS/2 INCOMPLETE; PCC 126 PASS/44 INCOMPLETE, both with
  zero invariant findings. Audio rejections and provider limits left gaps.
- October 10: local and AFM each 170/170 before subsequent response corrections;
  those changes had separate affected suites and offline gates.
- October 18–21, supporting 0.1.7: local 170/170, AFM 170/170 after image idle-residency
  correction, and a source-compatible derived PCC Cloud 170/170 result including
  an audio retry. Five October 18 references were selected for that release.
- October 27's earlier curated image and saved-file examples are replaced in the
  current publication selection. Original failed attempts and successful retries
  remain retained; no historical outcome is rewritten.

Release/package checks are separate from runtime conformance and are recorded
with the prepared archive. Building a package does not publish it or certify
unexecuted live behavior. See [release scope](RELEASE_SCOPE.md).
