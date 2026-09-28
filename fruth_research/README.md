# Fruth Research

Research preserves candidate metadata, explicit review dispositions, curated Gold
cases and selected evidence independently of runtime cleanup. It grants no
execution, learning-acceptance, repair or closure authority.

```text
canonical response/frame history
  -> existing self_learning extraction / merge / persistence
  -> Research candidate metadata sync
  -> explicit adjudication, semantic dedup and Gold curation
  -> selected Gold provenance retention
```

Research is part of Fruth. `./fruth start` initializes missing stores automatically
with zero candidates, zero Gold cases and no retained historical evidence. Existing
queues, reviews and Gold data remain unchanged on startup.

The passive `/api/research` surface reports these counts and their limited
authority. Initialization preserves existing queues, reviews and Gold manifests.
It never extracts old frames, invokes a model, downloads data or activates learning.

[Candidates](candidates/README.md) synchronize from explicit local learning
persistence. [Gold](gold-core/README.md) keeps a schema, validator and evidence
resolver; case selection remains explicit. Source-release packages include this
maintained functionality and focused synthetic tests, without accumulated stores.

## Review new evidence

From the checkout root, after the ordinary learning merge/candidate sync:

```sh
.venv/bin/python fruth_research/review.py audit --output fruth_research/reviews/audit-2026-09-27.json
.venv/bin/python fruth_research/review.py inspect --audit fruth_research/reviews/audit-2026-09-27.json --response-id RESPONSE_ID --output fruth_research/reviews/response-review.json
```

Use a new output filename for each audit/inspection. `--root /path/to/checkout`
before the subcommand selects another explicit topology. Audit scans the ledger
once and records exact row coordinates; inspection reads only the selected
response lineage, checks its hashes and uses the existing response-frame owner
to reconstruct its saved state. Neither command submits requests or changes
candidate reviews, Gold or runtime state. The CLI blocks network/subprocess calls
and writes outside its output directory.

Audit checks exact eval annotations and response membership. It does not rederive
extractor labels, inspect all candidate sidecars, or infer correctness from a
historical `completed`/`fulfilled` label. Missing current-ledger membership can
mean preserved historical evidence, rather than a failed response. Inspection
reports absent/corrupt sidecars and artifact digest evidence separately; an absent
producer digest is not a proven digest mismatch.

A curator then reviews the request, canonical evidence and outcome, identifies a
distinct contract, and writes a case using [the Gold schema](gold-core/schema.json).
Use [additive curation](gold-core/README.md#add-reviewed-cases) to validate and retain
those explicitly reviewed cases. This is the reusable replacement for the old
date-specific review scripts. It does not automatically turn every candidate into
Gold or use a model to adjudicate the queue. Generated reports and curation receipts
are private Research data and are excluded from source releases.

Clean/full/forget/reset preserve Research. Archive uses verified copy and space
preflight while leaving the active Research tree intact. Sharing flags remain
curation metadata, never publication permission.
