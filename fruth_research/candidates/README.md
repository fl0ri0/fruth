# Research candidate queue

Successful eval persistence in `fruth_services/self_learning.py` synchronizes the
existing extractor's JSONL into this queue. No extractor or rematerializer runs
here. `canonically reconstructible != adjudicated != Gold`.

Candidate identity is `research-` plus SHA-256 of the exact source `case_id`.
Different source ids remain different candidates even when prompts match. Each row
has a source id, content-addressed source generation, first/last seen generation,
current source record digest, exact eval-row byte binding, available response/frame
annotations, a bounded prompt preview (500 characters, length/hash/truncation flag),
source tags and historical annotations. Canonical bindings are explicitly
unverified; a Ledger path existing does not establish response membership.
Missing prompt or frame information stays absent/unverified.

`review.disposition` is one of `unreviewed`, `promoted`, `deferred`, `rejected`,
`superseded`. Gold ids, notes and the reviewed source digest survive synchronization.
`review_source_changed` flags source content that differs from the reviewed record.
`source_versions` retains up to 32 distinct record versions; reaching the named
limit fails synchronization visibly without dropping history. Reappearance updates
current bindings; disappearance preserves the candidate and its review. Historical
versions are metadata, not retained raw evidence. Explicit review updates through
`fruth_services.research_candidates.set_review` preserve prior review objects in
`review_history`; they do not create, relabel or remove Gold cases.

The JSONL is the atomic primary queue. A nonblocking file lock serializes writers;
a busy queue fails secondary sync so it cannot indefinitely delay learning. The
manifest is an atomic derived count/digest summary. If its write fails after the
queue commits, resync rebuilds it. Compare `candidates_sha256` before relying on a
manifest. Malformed queues, unsafe symlinks, duplicate source ids or changed source
bytes fail visibly. Learning remains committed when secondary sync fails.

From the repository root:

```sh
.venv/bin/python fruth_research/candidates/sync.py
.venv/bin/python fruth_research/candidates/sync.py --refresh-availability
```

`--root` selects an explicit topology. `--source` selects an existing eval JSONL
inside that root. Automatic sync only uses the conventional
`<root>/state/self_learning/eval_cases.jsonl` destination; custom persistence paths
require this explicit CLI. Read-only extraction and report-only persistence do not
sync. No candidate data flows into learning acceptance, execution, repair or Closure.

The Fruth queue starts empty. `./fruth start` initializes missing stores
automatically and preserves existing candidates and reviews. Once local learning is
persisted, the ordinary integration synchronizes candidate metadata. Use
`--refresh-availability` when no eval ledger exists; ordinary sync requires its
explicit source.

Clean/full/forget/reset preserve this directory, including review history and
nested cache files. Archive takes one verified copy of the whole Research tree.
After raw evidence deletion, refresh availability: `provenance_available` means
only the listed paths/digests exist, `provenance_partial` means some do, and
`source_missing` means none do. Changed exact source bytes also count as missing.
These statuses are observations at the last refresh, not continuing monitoring.
No raw candidate evidence is copied and no provenance is invented after reset.

Everything is internal research. `external_share_status` is retained on updates;
new candidates default to `review_required`. Retention confers no export rights.

For the next step, use the maintained [evidence review commands](../README.md#review-new-evidence).
Sync does not perform adjudication or create Gold. Explicit reviewed cases can be
added through [Gold curation](../gold-core/README.md#add-reviewed-cases); only their
linked candidate source versions receive promoted dispositions.
