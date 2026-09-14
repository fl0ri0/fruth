# Self-Attack status — 2026-09-14

The September 14 full campaign ended **FULL_CONFORMANCE_FAIL**. The subsequent
investigation fixed the shared cause of its three failing cases and recorded
**ALL_FRAME_FINDINGS_RESOLVED**, supported by deterministic regressions, three
targeted live confirmations and two staged audio-repair variants. A new full
campaign has not been run after those fixes, so no new full-system PASS is claimed.

This public summary combines the retained campaign and resolution evidence. It
does not rewrite either historical record. Earlier September 6 evidence recorded
fake PASS, representative live-gate PASS and full-live INCOMPLETE.

## Original campaign

Run identity: `full-conformance-post-hardening-20260914-fresh-suite`.
The campaign ran on September 14 from 04:46:08 to 11:48:13 UTC and exited 1.

| Scope or observation | Recorded result |
| --- | --- |
| Deterministic/fake conformance | PASS; 38 profiles, no invariant findings |
| Full live campaign | FAIL; all 17 profiles and 170 planned cases started and accounted for |
| Live case outcomes | 167 PASS, 3 FAIL |
| Planned follow-ups | 85/85 started and passed |
| Invariant findings | Eight observations across the three failing cases |
| Missing scenario witness | One `exact_source_binding` witness in the original live evidence |
| Readiness / other HTTP timeouts | 0 / 0 |

All three failures came from the `evidence-root` case in the Late Fill / source
binding boundary: speak a sentence and transcribe the audio actually generated.
The oracle observed different `/response_frame` bodies under the same frozen
frame identity (`frozen_frame_mutated`, signature `00128a9655c1c841d1dc`).

| Profile | Selected setting | Finding observations | Later disposition |
| --- | --- | ---: | --- |
| `8d81c46fcf0a` | `ghost_mode=improviser` | 4 | Resolved for the tested runtime |
| `385d7c0ad2cd` | `developer_flags.planner_timeout_ms=7200000` | 2 | Resolved for the tested runtime |
| `4ff7c83732d9` | `developer_flags.accepted_learning_authority=preferred` | 2 | Resolved for the tested runtime |

These settings identify the observed cases; they were not established as direct
causes of the defect. A truthful blocked audio obligation is not itself a
conformance failure.

## Cause and fix

The retained Ledger records and canonical loader reconstructed the original
frozen bodies. Later detailed lookup could instead return an expanded live
representation under the same frame ID. TTS semantic regeneration exposed the
window between durable checkpoint readback and publication of the live result.

The investigation classified the cause as **OBSERVER_SNAPSHOT_BUG** in server
lookup, with regeneration a **CONTRIBUTING_TRIGGER**. The evidence supports an
inconsistent projection; it does not prove an in-place durable Ledger mutation.
A continuous historical filesystem write audit was not available.

The fix in `ollmo_webserver.py` binds the detailed lookup's frozen frame and
durability envelope to the already-loaded canonical durable body when both frame
ID and sequence match. Live progress remains outside that frozen body. The fix
adds no extra read and changes neither the invariant oracle, semantic thresholds,
repair budget nor VoiceDesign behavior.

## Evidence after the fix

| Validation scope | Result and limit |
| --- | --- |
| Deterministic reproduction | Pre-fix reproduction triggered the historical signature; six profile × accepted/exhausted repair variants passed after the fix |
| Bounded regressions | 610 tests and 45 subtests passed; no source drift recorded |
| Exact targeted fake cases | 3/3 PASS; source and provider-artifact binding exercised, no findings or missing evidence |
| Targeted live confirmations | 3/3 PASS; fulfilled, source binding exercised, no findings or missing evidence |
| Staged bad A → good B | PASS; exactly one repair, verified B becomes authoritative, final obligation fulfilled |
| Staged bad A → bad B | Policy PASS; exactly one repair, exhausted budget, obligation unfulfilled and Closure blocked, no third attempt |

The live confirmations all passed on the first audio attempt; they did not
naturally exercise regeneration. The two staged tests separately replayed fixed,
digest-bound recordings and transcripts through the actual finalizer, successor
parent checks, Ledger recovery, checkpoint, lookup, semantic verifier and Closure
owners. Both passed, retained rejected audio as audit evidence, kept frozen
predecessors stable and made duplicate callbacks inert. They used no new random
generation or production RNG restoration.

The retained resolution completion records **ALL_FRAME_FINDINGS_RESOLVED** at
12:57:37 UTC on September 14. All eight historical observations have individual
resolved dispositions. This result applies to the identified issue and tested
runtime, not every subsequent source revision or the complete profile/case suite.

## Remaining limits

The original campaign remains failed and its missing witness remains part of
that historical record. Targeted confirmations supply new evidence for the three
cases; they do not retroactively turn the 170-case campaign into a PASS.

The existing lexical audio verifier is also not an exact acoustic-word guarantee.
In one original case it rejected “The night house is quiet.” but accepted
“The Benna Lighthouse is quiet.” for “The lighthouse is quiet.” The retained user
listening observation disputed exact fidelity. Thresholds were not changed by the
frame fix; exact speech fidelity and semantic-policy redesign remain separate.

Later upload validation passed 768 tests and 21 subtests in an isolated copy with
network blocked; one module skipped because curated Research assets are excluded.
That is additional regression evidence, not a fresh Self-Attack campaign. A new
full campaign would be needed to establish a new full-system verdict. See
[Self-Attack](SELF_ATTACK.md) for scope and verdict definitions.

## Evidence provenance and publication boundary

The following retained records under the run identity above were read to prepare
this summary. Their SHA-256 identities distinguish the original result from the
later resolution. They are provenance identifiers, not links to shipped files.

| Retained record | SHA-256 |
| --- | --- |
| `final-report.md` | `2a13435161b2b3a54cb2c39a3ab9b343e1c2f140b2ca3a308f9d745a0d3dcbd9` |
| `suite/completion.json` | `dfd9a09a00dd39a7cc0ccf00918ddfec9bfe9836b69d439be197c9e9358e1224` |
| `frame-finding-resolution/report.md` | `fa53ceb55c6364d5481c82f902eabcbcaeddf831bd0eee40f2a458af675c1a02` |
| `frame-finding-resolution/resolution-completion.json` | `fa522ec6b431f651eb6a4e20d80881f78b3e46d3a4003ee351b775874304916b` |

Raw captures, audio, ledgers, logs, local Research trees and forensic evidence
remain excluded from the public upload. Preparing this report launched no live
requests or conformance campaign and rewrote no historical evidence.
