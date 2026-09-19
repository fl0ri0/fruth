# Gold Core — Fruth curation and validation

Fruth starts with an empty Gold corpus. Normal startup initializes its empty
manifest and preserves existing cases and reviews. The [schema](schema.json),
validator, evidence resolver and synthetic tests are included. Old curated cases
and their retained evidence are not part of this fresh installation.

## Sources and curation

The preferred source model is:

```text
canonical response/frame history
  -> candidate from existing self-learning eval machinery
  -> attach invariant/defect/adjudication evidence
  -> curate the bounded research case
```

Selection favors explicit intent, exact identity, retained evidence, clear scope,
adjudicated behavior and distinct boundaries. Cases with missing response bindings,
unclear fulfillment, unverified provider fidelity or unresolved causes are deferred.
Every case’s `contract.scope` and `adjudication.limitations` restrict its claims.
Candidate bindings are not adjudicated Gold cases.

## Outcome labels and failures

`expected_outcome`, `historical_result`, `case_role`, `reproducibility`,
`evidence_quality` and `adjudication.status` describe separate dimensions. A
historical Closure label is recorded separately from the curated expected outcome.
An `invariant_preserved` case can establish saved-byte consistency or scope without
certifying every part of the original request. `complete` means complete for the
specific direct probe, not full end-to-end system coverage.

A **correct negative** preserves truth when fulfillment is unavailable. Bad audio
A followed by bad B, exactly one repair and blocked Closure is policy-correct;
the obligation remains unfulfilled. A **defect regression** records historical
wrong behavior and a distinct correct contract, causal classification, fix and
corrected evidence. Infrastructure
failure is separately labeled: unwanted ENOSPC can coexist with correct refusal
of false Index authority. Failures expose boundaries that successes alone miss.

## Provenance and authority

Each reference names a `root_kind` (`state` or `artifacts`), a relative path,
purpose and SHA-256. Campaign/response/frame ids and existing eval ids are retained
where applicable. A Ledger or eval JSONL row additionally names its exact byte
offset and length; its digest covers those raw bytes, including newline. Appending
later rows does not invalidate that binding. Compaction or rewriting does; use a
retained matching epoch rather than silently rebinding it.

Canonical CAS references also retain the runtime's `canonical_sha256`, which hashes
bytes with trailing newlines removed. The ordinary `sha256` hashes the exact file.
Effective sidecars follow the exact parent lineage through existing owner logic.
Recorded JSON-pointer assertions bind decisive ids, states and verdicts to evidence.
Source hashes already retained in diagnostic/source evidence remain in those files.

All references continue to support live checkout validation. Resolution order is:
explicit `--evidence-root` values (checkout default), the sibling
`retained-evidence/gold-core-v0` store, then explicit `--archive-root` values.
`--retained-only` explicitly selects a historical audit using only retained bytes
and cannot be combined with live/archive roots. This is useful after an eval
ledger is rewritten for a new learning generation. A default live check still
fails on a changed historical binding. The first existing source must match its digest; corruption never falls through.
There is no archive discovery, fuzzy matching or semantic rebinding. An incomplete
or corrupt retained manifest fails, as does a manifest-promised missing file.

The retained manifest records original root/path, exact digest, original whole-file
digest, selected offset/length, retained path/digest, canonical digest where present,
case ids and purposes. A sliced Ledger row retains its exact raw bytes, including
newline; JSON assertions still run against those bytes. Whole-file dependencies
remain whole even when large. Original case references and curated labels are
unchanged. Absolute paths inside historical evidence are unchanged and do not
become resolver authority. Upstream replay dependencies beyond a case's enumerated
references may still be missing; retention does not promise a runnable environment.

Raw evidence remains authoritative within its owner contract: frames and Closure
for owed/fulfilled work, saved files for bytes, artifact records for identities,
and adjudication for defects and expected behavior. Curated metadata is neither a
replacement truth store nor permission to mutate or execute runtime state.

## Validation

From the checkout, use the existing Python environment:

```sh
.venv/bin/python fruth_research/gold-core/validate.py
.venv/bin/python fruth_research/gold-core/test_validate.py
```

An empty corpus deliberately does not pass Gold validation. Startup reports
`not_run_empty`; it does not claim adjudicated or validated cases. The synthetic
tests exercise validator mechanics using temporary evidence.

`--corpus` selects a separate corpus copy; `--retained-store` selects its exact
store. `--archive-root /path/to/actual/snapshot` adds an explicit final fallback.
Use `evidence.py` to inventory dependencies; `evidence.py --materialize` performs
space/source preflight, copies and verifies exact selected bytes, detects source
movement and publishes a complete store. It refuses to overwrite an existing
store. A failed copy keeps a clearly named partial directory for diagnosis.

Clean/full/forget/reset preserve Gold and retained evidence. Learning changes only
the sibling candidate queue; Gold membership, outcomes and classifications require
explicit curation. After reset, validate a populated corpus and refresh candidate provenance
with `../candidates/sync.py --refresh-availability`. This does not run workloads.

The validator checks the JSON Schema subset used here, unique ids, labels,
reference paths/digests, recorded facts, semantic duplicate keys, defect/negative
rules and manifest counts. Unsupported schema keywords fail closed. It uses the
Python standard library; no dependency was added. It does not run historical
cases, call providers, regenerate artifacts, verify current Epoch authority or
independently prove natural-language judgments. Tests use temporary evidence.

Semantic deduplication uses intent/obligation shape + sorted boundaries + expected
outcome + trajectory role. Prompt equality is not the dedup key. Any deliberate
same-key exception requires an explicit rationale on every affected case. Reused local ids must be disambiguated by exact evidence roots.

## Research use, bias and sharing

Intended uses: regression/evaluation design, behavioral analysis, systems research,
and a future separately reviewed dataset export. Not intended: treating historical
behavior as automatically correct, replacing raw evidence, or training without
separate review. There is no eval runner or export pipeline in v0.

Document selection bias and coverage for each curated population. Semantic
deduplication removes repeated coverage; case counts do not estimate incident
frequency or provider reliability.

Deterministic means fixed owner/fixture inputs; retained replay fixes provider
outputs, not production RNG. Stochastic runs are observations, and historical-only
cases do not promise replay in the current environment. Later runtime changes do not retroactively update labels.

Sharing flags are curation metadata only. Raw references can contain personal
context, local paths, provider/machine ids and source/media with uncleared rights.
Review selected metadata and evidence before any separately authorized export;
retention itself does not supply rights clearance or publication permission.
