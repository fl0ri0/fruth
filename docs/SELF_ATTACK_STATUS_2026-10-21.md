# Fruth validation status — October 21, 2026

**Local, AFM and PCC Cloud each have complete 170-case live coverage.**
The five October 18 [reference workflows](../examples/README.md) also have
completed final frames and clean, matching monitor records. This is validation
of the post-0.1.6 checkout; it does not publish or certify a new release archive.

## Recorded results

| Evidence | Result | Tested scope |
| --- | --- | --- |
| Local, October 18–19 | PASS, 170/170 cases, 17 profiles; zero incomplete/findings | Local model mix, before the image idle-residency fix |
| AFM r3, October 19 | PASS, 170/170 cases, 17 profiles; zero incomplete/findings | Local Apple system model, after the image idle-residency fix |
| PCC Cloud, October 19–21 | Derived PASS, 170/170 unique cells, 17 profiles; zero remaining gaps/conflicts | Compatible bounded windows, including the successful audio retry |
| Local offline gate | PASS, 380/380 cases, 38 profiles, 198 owner checks in five groups | Matching local source; source checker passed |
| AFM/PCC offline gate | PASS, 380/380 cases, 38 profiles, 198 owner checks in five groups | Matching corrected source; source checker passed; PCC reused this verified gate |
| October 18 references | 5/5 admitted; 13 saved artifacts verified | Exact prompts, final frames, monitor identities, artifact digests and applicable bundle links |
| PCC Cloud Pro | Untested, 0/170 | No Cloud Pro conformance claim |

A conformance PASS concerns the checked runtime contracts. An honestly blocked
or unresolved answer can satisfy those contracts; PASS does not certify every
model answer's usefulness or factual accuracy. The live matrix covers five
boundaries: commitment/closure, aspiration/promotion, anchored repair/rebase,
Late Fill source binding, and attention/graph scope. Finite coverage is not a
general proof of rule independence, concurrency or progress.

## PCC windows and retry

The first allocation dispatched 100 cases: **99 PASS and one INCOMPLETE**, with
zero findings. Profile `5331e9ce7633`, case `evidence-root`, correctly rejected
an audio/transcript mismatch (`audio_transcript_mismatch_rejected`, Guard PASS).
That preserved the safety contract but left successful exact-source handoff
coverage unexercised.

After the operator's pause, the second allocation executed the remaining 70
cells plus a fresh two-case producer/follow-up retry: **72/72 PASS**, zero
incomplete cases and zero findings. Both native window records retain their
INCOMPLETE whole-matrix verdicts and exit 2 because each is a partial selection.
Their compatible combined evidence establishes **PCC Cloud 170/170 PASS**.
The native offline combiner performed **162 comparisons with zero conflicts
and zero comparison gaps**, checking source, configuration and actual serving
tier. It made no provider requests and did not rewrite the first audio rejection.

There were 172 dispatched case attempts for 170 unique matrix cells. Case counts
are not Apple request counts. No provider quota stop was recorded in these two
allocations; neither their size nor the pause establishes Apple's quota or reset
schedule. The observed tier was Cloud, not Cloud Pro.

## Models and source chronology

The normal local campaign used Ollama `gemma4:26b` as preferred interpretive
inference, with MLX `gemma-4-E4B-it-qat-8bit` fallback and `ornith-1.5:9b`
available. AFM used two `apple_fm/system` instances; PCC used two
`apple_pcc/auto` instances. AFM and PCC had no explicit interpretive fallback.
All three configurations included MLX Z-Image Turbo, Qwen3 TTS, Whisper large-v3
and Ollama EmbeddingGemma 2. These are integrated Fruth workflows; AFM/PCC did
not themselves generate all image or audio artifacts.

The local pass preceded the October 19 correction that releases idle MLX image
model weights after requests and reloads them for the next request. AFM r3 and
both PCC windows tested the corrected source with the matching offline gate.
The correction did not lower resolution or diffusion steps. Earlier AFM
memory-pressure failures and the subsequent complete pass remain distinct
observations; this was not a controlled experiment attributing every earlier
failure to one cause.

The five references were executed on October 18. Evening Rain and Lighthouse
preceded that day's Echoes continuation corrections; the latest Echoes, Selfies
and saved-file runs followed them. Each public package preserves its actual
prompt and result. The saved-file case now uses `[17, 144]` and sum `161`.
Lighthouse's transcript matches after lexical normalization, with a punctuation
difference. Selfies has three digest-bound image inspections; model descriptions
remain interpretations. Earlier Echoes attempts are not relabelled as successes.

These curated outcomes do not measure a first-attempt success rate. Recorded
timings are individual observations, not controlled performance comparisons.
The documentation refresh copied and verified existing results without inference,
runtime restart, model changes or publication.

## Evidence identities

Campaign names below identify retained local evidence; raw campaigns and
production ledgers are not part of the public source package. SHA-256 values
bind each recorded result, without implying independent third-party replication.

| Campaign / evidence | Run ID | Results SHA-256 |
| --- | --- | --- |
| `full-conformance-local-20261018/live` | `0b65f8f5751a448b9875f6f6a3085807` | `de767d70296b87cbb099e586b26d61f86590ebb998c85ed8e214b990c7f7f01d` |
| `full-conformance-local-20261018/offline` | `aecbaa27832c429c94af5e81bab80de8` | `c0f631345b600824955a5883651e6a7690e75dba91d7fcccf2a6c30a8dd53380` |
| `full-conformance-afm-20261019-r3/live` | `bbbd1a0a8a4c4d78a290ea6e6e3ffebe` | `08ac780cce24f756dc20fa9bc6e11f89d83ab9c1cae90cdae04bdd393e6b3ec5` |
| `full-conformance-afm-20261019-r3/offline` | `1e4d019375ba41c784ec2720321ca6a7` | `5521138d811818c79aef4fe0fc8e35541b5acb146eec0b9086e641ca43174b9f` |
| `full-conformance-pcc-20261019/window-01` | `771c1c344f5e4bf0aea38fdf16f1b597` | `c8860adf3fafd623d5393e38686c8e85cafb5870136968f841954927b22d2922` |
| `full-conformance-pcc-20261019/window-02-with-audio-retry` | `13047ced12004413b41ba87d3e6d01ac` | `6ea1e8ea2f906df327aaa1f15d7e46faa5c856bfb2ea0113c7ffc3388ca37f91` |
| `full-conformance-pcc-20261019/combined-20261021` | Derived 2026-10-21T07:21:33Z | `408c7240f1354344b09cef0fb860d1ac556db1d1a45a07b1311e71965777509a` |

The local runtime digest is
`45b397b47a58cf46b09e935455f17d5e75766ed99d285197275fe252684c3896`;
its full native source digest is
`8ab3334ef2fe53e182c80b6081c76274b33484b4d443d8ac293688d38831dcae`.
AFM r3 and PCC share runtime digest
`d7159d68cfb0512d398ed1684c936c4febcaf204564833b1b7b424e01c9a14e5`
and full native source digest
`99b34fc84858aec10149b8d5d270c1a078c92d03cbeb44d9a7d1bcbb312936d1`.
The shared diagnostic digest is
`43d6207c57d2ffb941b9b108492bee837886d34aa7e1dda74bc2ae8054cd2b55`.
All 552 files in the AFM/PCC frozen source map matched the working checkout
before this editorial refresh. Documentation, public examples and packaging
selection are prepared afterward; recorded tested-source identities stay intact.

## Historical results

This is the single current public status report. Earlier dated summaries and
reference packages are retained privately with their original bytes; previously
published releases are unchanged. Historical results keep their original scope:

- **September 19:** complete deterministic 380-case and live 170-case passes.
- **September 25–27:** AFM 168 PASS / 2 INCOMPLETE; PCC 126 PASS / 44 INCOMPLETE.
  Both recorded zero invariant findings and native INCOMPLETE. Correct audio
  rejections and PCC usage limits left gaps; Cloud Pro was not demonstrated.
- **October 10:** local and AFM each passed 170/170 before the subsequent
  response corrections. Those corrections and the later monitor/classifier
  closeout had separate passing affected suites and 380-case offline gates.
  The five October 10 references remain evidence of their own executions.
  No new PCC campaign belonged to that round.

See [Self-Attack conformance](SELF_ATTACK.md) for coverage and bounded-window
semantics, and [source packaging scope](RELEASE_SCOPE.md) for what is distributed.
Release/package validation remains separate from these runtime observations.
