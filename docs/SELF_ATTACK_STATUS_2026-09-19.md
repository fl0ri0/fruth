# Fruth Self-Attack status — 2026-09-19

The full Fruth `0.1.2` campaign completed with **PASS** for deterministic/fake
conformance, the representative live gate, and full live conformance. It started
on September 18 and finished on September 19, 2026.

This is a dated public summary of that campaign's recorded evidence. Its verdict
applies to the tested source and scope; it does not certify later runtime changes
or every model, backend, prompt, and control combination.

## Verdicts and coverage

| Scope | Verdict | Complete profiles | Complete cases |
| --- | --- | ---: | ---: |
| Deterministic/fake conformance | PASS | 38/38 | 380/380 |
| Full live conformance | PASS | 17/17 | 170/170 |

The representative live gate also passed using the same live observations; it
was not an additional campaign. All five owner-test groups passed in both stages.
There were no deterministic invariant findings, incomplete case observations,
manual-review entries, or new regressions. No live budget was exhausted, and no
additional profile attempts were needed.

| Authority boundary | Fake captures | Live captures | Findings | Incomplete cases |
| --- | ---: | ---: | ---: | ---: |
| Commitment and closure | 76/76 | 34/34 | 0 | 0 |
| Aspiration and promotion | 76/76 | 34/34 | 0 | 0 |
| Repair/rebase and anchored intent | 76/76 | 34/34 | 0 | 0 |
| Late Fill and exact evidence/source binding | 76/76 | 34/34 | 0 | 0 |
| Lenses/attention and graph scope | 76/76 | 34/34 | 0 | 0 |

The default `self-attack-v1` corpus contains ten cases: a root and follow-up for
each boundary. Seed `0` selected every reviewed finite control value plus four
seeded mixed profiles. This was the full default matrix, not an exhaustive test
of all combinations. The 24 inventory-only controls were recorded as exclusions,
not counted as exercised controls. Environment controls were swept only in the
isolated fake stage; live profiles changed request controls.

## Campaign identity and execution

- Local run identity: `full-conformance-20260918`.
- Fake run ID: `73f497d58aaf45b7af5d310a82c44581`.
- Live run ID: `9541de3c154f4f86a08d02504f0241c0`.
- Controller start: `2026-09-18T17:12:28.017380Z`.
- Controller completion: `2026-09-19T01:21:39.092067Z`; exit code `0`.
- The live stage used this campaign's own passing fake evidence. Earlier
  campaigns were not reused as its fake gate or counted toward its coverage.

The command used was:

```sh
./fruth self-attack --detach --live-after-fake --live-profile-limit 17 --live-main-budget 43200 --output state/self_attack/full-conformance-20260918
```

The fake sweep used two isolated workers. The live main allowance was 43,200
seconds, with the existing 1,200-second sequence ceiling, 900-second confirmation
allowance, 300-second additional replay ceiling, and four additional profile
attempts available. No limits, evidence requirements, or assertions were relaxed
during the campaign to obtain a passing result.

For a fresh execution, use a new output directory and the commands and
prerequisites in [Self-Attack conformance](SELF_ATTACK.md). Live execution requires
an already running control plane and suitable ready capabilities; the harness
does not start models. Model prose does not determine conformance verdicts.

## Source and evidence provenance

Both native run manifests record this source digest:

```text
8512aa03e3527ca5d4020cf8db308cfa5d73686c094dc40c8a51655e39546119
```

The completion inspection matched both manifests to the recorded corpus,
profiles, seed, and source identity. All 311 separately recorded source, policy,
configuration, and test file hashes still matched at that inspection. Subsequent
publication preparation adds this summary, documentation links, and packaging
coverage; it does not change the runtime or harness represented by the native
source digest.

These SHA-256 values identify the retained native evidence under the run identity
above. They are provenance identifiers, not links to files shipped in the source
release:

| Retained record | SHA-256 |
| --- | --- |
| `completion.json` | `feedecdf2128fbe45982b41a8a376324f68e717db8b608a225749ed001cbc657` |
| `run.json` | `41cd6a92ace2761a35a005fb5c8977de314a0a339209b483eadd8bfc04cb1152` |
| `report.md` | `4191b87867b3500e0442427959efc1b58ae48f2f65dbd13de288825467d29f14` |
| `results.json` | `5046c8fbfe2537916400fc131d185fc44a30d89b8a432e9204cfe7023842c19d` |
| `live/run.json` | `72ccffdd01cf6e24848b390168641c079b5a9ee218417a1a09b28f82bd2b9cbc` |
| `live/report.md` | `08c5e20beb1ffe19b10a713b59c8c9bf7fdec2a88c345fe653640c0f2d2a7e50` |
| `live/results.json` | `3b2b2e0e12d451979450272516998a123acac34485f4715dced73ac3ccea3683` |

## Interpretation and publication boundary

PASS means the harness found the required observations and no deterministic
invariant violations within this scope. A truthful blocked obligation can pass
conformance; these counts do not mean every requested artifact was fulfilled.
The result is not a guarantee of factual accuracy, perceptual media quality, or
success on arbitrary future requests. Fake providers establish deterministic
runtime evidence; the live results record a separate observation of local
interpretive inference and execution.

The public source selection includes this summary, the harness, its tests, and
the compact reproducible corpora. Raw captures, audio and other retained artifact
bytes, response ledgers, worker runtimes, logs, learning state, and large forensic
corpora remain local and excluded. The summary and hashes alone cannot reproduce
a forensic recheck of the original captures. See [Release Scope](RELEASE_SCOPE.md#source-selection-and-checksums).
