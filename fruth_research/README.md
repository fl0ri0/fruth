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

Clean/full/forget/reset preserve Research. Archive uses verified copy and space
preflight while leaving the active Research tree intact. Sharing flags remain
curation metadata, never publication permission.
