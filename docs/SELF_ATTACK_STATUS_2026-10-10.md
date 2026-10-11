# Fruth validation status — October 10, 2026

The October 10 validation sequence includes complete local and AFM conformance,
the response-correction offline gate, and five fresh local reference workflows.
The later monitor/classifier closeout is recorded separately below.
These are separate, source-bound observations; they do not constitute a new PCC
pass or a new released version.

## Recorded results

| Evidence | Result | Tested scope |
| --- | --- | --- |
| Local live conformance | PASS, 170/170 cases, 17 profiles | Complete intended live matrix on the pre-correction runtime |
| AFM live conformance | PASS, 170/170 cases, 17 profiles | Complete intended live matrix on the same pre-correction runtime |
| Response-correction affected suites | 1,248 tests and 473 subtests passed | Corrected response semantics, canonical output, frame/recovery and API paths, including retained reproductions |
| Corrected-source offline fake gate | PASS, 380/380 cases, 38 profiles; 198 owner checks | Deterministic runtime conformance; matching-source checker passed |
| Refreshed local reference workflows | 5/5 admitted; exact-frame monitor verdicts clean | The five original reference prompts, executed anew after the response-correction runtime reload and before the later closeout |
| Later closeout focused suites | 132 passed, one expected development-shim skip | Truth-guard boundaries, monitor attribution, reference export and public release selection |
| Later closeout affected suites | 1,226 tests and 473 subtests passed | Response semantics, frames, Responses API and retained R1/R2 reproductions |
| Later closeout full offline gate | PASS, 380/380 cases, 38 profiles; 198 owner checks | Fresh matching deterministic matrix and source/evidence checker; zero isolation violations |
| PCC | No new campaign in this validation round | Historical quota-limited coverage remains separate |

Both complete live matrices recorded zero invariant findings and zero incomplete
observations. A conformance PASS is a verdict about the checked runtime contracts;
an honestly unresolved or blocked response may satisfy those contracts. It is not
a claim that every request produced a satisfactory answer.

The live campaigns prompted a separate review of unresolved responses. Two
reproduced defects were corrected: truth-guard text could be lost through output
projection/recovery, and ordinary JSON content mentioning internal field names
could be misclassified as a control envelope. The subsequent affected tests and
fake gate cover those corrections. The five new references add real local
workflow evidence. The complete local/AFM live matrices were not rerun afterward.

The later closeout narrows control-JSON false positives, defines a sole `response`
wrapper, adds secondary-identity/type controls, and corrects monitor timing
attribution across overlapping responses. Its affected offline tests and complete
matching gate/checker passed. It does not rewrite the five reference
packages or their historical monitor records.

## Five refreshed references

The [reference index](../examples/README.md) links the dated, self-contained
packages, each with the exact prompt, final frame identity, saved artifacts,
independent monitor snapshot and checksums:

- **Echoes of the Pass:** HTML/CSS, exactly two images, exact narration source,
  physical WAV integrity and a portable bundle with resolved local links.
- **Evening Rain:** the complete written reflection bound to one generated WAV,
  with source/file digests and physical integrity checks.
- **Lighthouse Audio Roundtrip:** the generated WAV bound to the STT consumer,
  with accepted lexical fidelity. The transcript uses “gray” where the original
  uses “grey”; it is a semantic match, not byte-identical text.
- **Funny Animal Selfies:** three distinct images and three separate vision
  consumers, each bound to the actual supplied image digest, followed by the
  recorded combined inspection.
- **Saved JSON → actual read → derived HTML:** exactly two files, `[42, 96]`
  and a table including `138`, with verified saved-input consumption and output
  identities/digests.

The operator reports first-submission success for all five. Five curated outcomes
do not establish a general success rate. Model-authored visual descriptions remain
interpretations even when the consumed image identity is verified.

The monitor was disabled during the large conformance campaigns, so reference
reports were appended afterward. All five match their exact final frames and
report no missing files, hash mismatches or HTML/CSS issues. Some retained
event-window phase times include other responses' activity; those fields are not
used for reference admission or performance comparisons. This observation does
not change the canonical frame, artifact or Closure results.

## Source and evidence identities

The two full live matrices used runtime digest
`343952298e4ae9cd2ae8e43938290ce3473e2e8833d79d5f2676f9f66bb29f9d`.
Their run IDs and result-file SHA-256 values are:

| Campaign | Run ID | Results SHA-256 |
| --- | --- | --- |
| Local | `b7648fd0f0a44a9c9cb8afb9986bfcb5` | `b814101a4430961a6dc6b8ec6e2c5fe612f0a1b67a2ab3ba25baea38fbe85e2a` |
| AFM | `ac12a00a305444e3810e43500731706a` | `877974346d8929143ceca6286e78db9e73f875440a07deae5e5d0913389dd3a7` |

The first response-correction runtime and its fake gate use runtime digest
`9578aa317d40457f660f14a1ec223a460b153b17ffea32b865bbde3df941b1b4`.
The fake run ID is `46eddf9b10a94a1b9c13e49a9d869cb4`; its full source digest is
`da1bdf720b86bea179ca059e1aed26159822a905e07a10f87efe2e27ea78ed7c`.
The affected-test source map is
`b37658a9a74dbb5b56097b2396e1444146610e3e5ce4726f00f5d53efa6647df`.
Documentation, reference packages and release selection were updated afterward;
those changes do not replace the recorded tested-source identities.

The later closeout gate is run `123c60b02d1846f783f358db45a1f089`, completed
at `2026-10-10T21:55:04Z`. Its runtime digest is
`e6771e5dd7f0dd9127d060c95c3e005ba47a2ac5bee85776d3260bf8e1a234be`,
diagnostic digest
`7819af8a1254d6857a56fb3c1667ff9733aeb48393100b341bb48a08b244570f`,
and full native source digest
`836ffd89e5fb130eca6a3ff7ec5400c46515b81d4c14b8f1a0943398abe9385d`.
Final editorial status/changelog updates followed the immutable tested source;
runtime, policy, test and monitor code remained identical. New monitor reports
use attributable timing evidence; historical reports retain their recorded data.

During the reference refresh, the serving process was observed to have started
at 21:27:16 Europe/Zurich, after that correction, from the reviewed checkout.
The runtime input hashes observed then match that gate and predate startup.
The five references began between
21:28 and 21:49. This is process/startup/source provenance, not introspection of
loaded Python memory. Each reference package separately binds its original final
frame record and independent monitor record by hash.

Historical reports and original failure evidence remain retained. The bounded
offline correction's earlier harness-denied and interrupted attempts are preserved
separately from its successful final runs. Final affected validation and the fresh
gate/checker recorded zero isolation violations.

## Limits

- The full local and AFM live matrices both passed before the two subsequent
  response corrections. Those corrections passed the affected tests and a fresh
  full offline gate; five local reference workflows then passed on the corrected
  runtime. The full local and AFM live matrices were not repeated after the
  corrections.
- The five references confirm those concrete workflows. The broader profile and
  case coverage comes from the recorded conformance campaigns above.
- The later monitor/classifier closeout has separate offline validation. The
  serving runtime was not restarted and no new local, AFM or PCC inference ran
  for that closeout; earlier live/reference results retain their tested source.
- No new PCC campaign ran in this round; its historical quota-limited coverage
  remains separate from the completed local and AFM campaigns.
- Discarded provider text is not exhaustively retained. This limits exact replay
  of some historical rejected answers, without requiring every rejected candidate
  to become durable ledger content.
- No performance improvement is quantified by these reports. No new inference,
  runtime restart, model change or release publication was performed while
  reviewing and exporting the already completed runs.

The [September 19 report](SELF_ATTACK_STATUS_2026-09-19.md) and
[September 25–27 Apple report](SELF_ATTACK_STATUS_2026-09-27.md) retain their
original source-bound results. Packaging checks and a release decision remain
separate from runtime conformance.
