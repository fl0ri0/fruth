# Apple backend conformance — September 25–27, 2026

These are dated observations of local AFM and Apple PCC integration, not a
claim that every model answer is correct or that all intended coverage passed.
Both campaigns completed their controllers with native INCOMPLETE verdicts
(exit 2). Original results have not been rewritten.

| Scope | AFM, September 25–26 | PCC, September 26–27 |
| --- | ---: | ---: |
| Offline gate | 380/380 passed, 38 profiles | 380/380 passed, 38 profiles |
| Live profiles returned | 17/17 | 17/17 |
| Live cases passed | 168 | 126 |
| Live cases incomplete | 2 | 44 |
| Invariant findings | 0 | 0 |
| Total elapsed | 13h 39m 22s | 13h 14m 14s |

Both used seed 0 and the full 17-profile, 170-case live matrix, following their
own passing offline gate and all five owner-test groups. The main live budget
was 24 hours, separate from the offline gate; each dependency sequence retained
its 1,200-second ceiling. This is bounded coverage, not an exhaustive proof.

## AFM interpretation

All 170 cases executed and were graded. Two audio-root cases correctly rejected
an audio/transcript mismatch: Guard PASS, successful handoff coverage INCOMPLETE.
The other 168 cases passed, including all 17 audio evidence follow-ups. The
rejection is intended behavior; successful handoff was not exercised in those
two cases. The run supports working AFM integration without converting those
coverage gaps into observed successful handoffs.

## PCC interpretation

The run recorded 140 successful Cloud executions across 127 suite requests,
including 13 additional image-inspection calls. Sampled serving evidence records
Cloud Pro access rejection followed by successful Cloud fallback; this campaign
must not be described as Cloud Pro conformance. Counts are observations, not
Apple's published quota or a complete account-level usage total.

At approximately 00:52 Europe/Zurich on September 27, the next suite request
received Apple's explicit model usage-limit error. All 21 subsequent affected
root cases contain that error; their 21 dependent follow-ups were blocked.
That accounts for 42 incomplete cases, including all 40 cases in the final four
profiles. The remaining two incomplete cases were one correctly rejected
mismatch and one audio follow-up not started before its sequence budget expired.
The report's missing-closure label describes absent execution evidence; retained
failed payloads establish the provider usage limit as the cause of the late
cluster. There is no successful execution evidence for unstarted follow-ups.

The main sweep did not exhaust its 24-hour allowance. Successful PCC execution
is demonstrated within the observed scope; quota-blocked cases remain untested.
The runtime uses other selected backends for capabilities such as image and
audio generation, so these are Fruth integration tests with the named primary
inference backend, not claims that AFM/PCC produced every media artifact.

## Performance and limits

Readiness-check timeouts persisted between cases. The event-tail optimization
fixed a different preflight cost; it did not eliminate readiness scans or the
whole-file response-index publication cost. Concurrent work on another account
was reported during the PCC run, but its contribution to timing was not measured.
These campaigns are not controlled performance benchmarks. Zero invariant
findings does not establish factual accuracy of all explanation text.

## Retained evidence identity

The following identifiers refer to local retained evidence, not files shipped
with the source distribution. Each verdict applies to its recorded source.

### `full-conformance-afm-20260925-r2`

- Live run ID: `2116e0bbab0e4cebb9d313ddb8c321a4`.
- Source digest: `0e1c238726ec54659da7761f6e3c571270f171185f5df248f2e530a7cacf81d0`.
- Controller finished: `2026-09-26T07:52:05.350550Z`; exit `2`.

| Record | SHA-256 |
| --- | --- |
| `completion.json` | `a815761928d1710b4574ae726fa32b436d4546ec14ad1d4df081859353c8c672` |
| `run.json` | `2c7947226849cd10d8afeb68eafeb21a6333a8e18efdcc9df47b04374aa0a655` |
| `report.md` | `445b42aeda9a387c665a9ea594e00d827a3726d6e31a7979639314c5c05e4feb` |
| `live/run.json` | `a7dfd2fcafa3e06df48b3ae4899e58c946fa77b3dba4a326770106f54be8128f` |
| `live/report.md` | `bfb3f5ea6bc8852e04bca20d9be54f967a4282aa4add74ca4be87e36534a1def` |
| `live/results.json` | `74e77b76fd73080b774f66abb00e8c4b4e1a4a91afe8b10e5ff6ca26798a7ba4` |

### `full-conformance-pcc-20260926`

- Live run ID: `e5a197e625314d13bb4b51475ab83299`.
- Source digest: `0e1c238726ec54659da7761f6e3c571270f171185f5df248f2e530a7cacf81d0`.
- Controller finished: `2026-09-27T00:00:29.343845Z`; exit `2`.

| Record | SHA-256 |
| --- | --- |
| `completion.json` | `a1abb73a941cb3b2cdfda10ccbfa2475be78987fb54fba6a8a1f018c10d24cb1` |
| `run.json` | `bcff4de3c111f41490706ccaad57d93de138c64a5fd285183a6a825ee0067fb4` |
| `report.md` | `445b42aeda9a387c665a9ea594e00d827a3726d6e31a7979639314c5c05e4feb` |
| `live/run.json` | `8e1eddaca18591cfbf27199a2f99d92a8f2b4b825e5c7ddea89c6d923ee9e97d` |
| `live/report.md` | `a40be5dce8cdc49f543b4abd2199cbdcb8a9eb00f6009956a4f7c3f619815c5e` |
| `live/results.json` | `4fbc63d632e7a489271b967f83f329a6e582c0731bb5d24906e7ebb144fb213e` |
