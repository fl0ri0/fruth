# Lighthouse Audio Roundtrip

**Status:** verified Fruth reference run  
**Run and review date:** 2026-09-18  
**Response:** `resp_1789746906910_471a87424e06e`  
**Final frame:** `resp_1789746906910_471a87424e06e:frame-2`

## Request

```text
Write a short two-sentence English field note about fog surrounding a coastal lighthouse. Create one local WAV audio artifact that reads the complete note in a calm, natural voice. Then transcribe that generated audio back into text. Return the original note, the audio, and the transcription together.
```

## Result

The response contains the original note, one generated WAV, and the transcription
of that exact WAV.

Original note:

> Thick, grey fog clings heavily to the jagged rocks around the lighthouse base. The rhythmic pulse of the beacon barely pierces through the dense, damp haze.

Returned transcription:

> Thick gray fog clings heavily to the jagged rocks around the lighthouse base. The rhythmic pulse of the beacon barely pierces through the dense, damp haze.

- [Play or inspect the generated WAV](artifacts/audio/narration.wav)
- [Read the saved transcription](artifacts/transcripts/transcript.md)

## Roundtrip evidence

The STT branch used `mlx-community/whisper-large-v3-mlx`. Its recorded audio-input receipt binds
the consumer to the generated TTS artifact; the lexical fidelity check returned
`TTS_STT_SEMANTIC_MATCH`. The transcript spells “grey” as “gray” and changes punctuation,
so it is a semantic match under the recorded policy, not a verbatim match.

```json
{
  "audio_reference_input_evidence": {
    "artifact_id": "audio_79c365e8706cd9789a126849",
    "artifact_ref": "artifact:audio_79c365e8706cd9789a126849",
    "authority": "canonical_direct_audio_dependency",
    "branch_id": "branch-text_to_speech-1",
    "file_sha256": "0f34fa4d8620d3ec0d47be0007c6c670f3cc92b606ccbf9d80311990163b6cfe",
    "obligation_id": "obligation-phase-2",
    "path": "canonical-artifact:20260918T155626Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
    "phase_id": "phase-2",
    "provider_input_sha256": "0f34fa4d8620d3ec0d47be0007c6c670f3cc92b606ccbf9d80311990163b6cfe",
    "source_response_id": "resp_1789746906910_471a87424e06e",
    "status": "verified"
  },
  "tts_stt_semantic_evidence": {
    "authority": "runtime_deterministic_verification",
    "consumer_branch_id": "branch-speech_to_text-1",
    "consumer_phase_id": "phase-3",
    "detected_lang_code": "en",
    "expected_lang_code": "english",
    "kind": "fruth.tts_stt_semantic_evidence",
    "metrics": {
      "exact_match": false,
      "negation_consistent": true,
      "normalized_source": "thick grey fog clings heavily to the jagged rocks around the lighthouse base the rhythmic pulse of the beacon barely pierces through the dense damp haze",
      "normalized_transcript": "thick gray fog clings heavily to the jagged rocks around the lighthouse base the rhythmic pulse of the beacon barely pierces through the dense damp haze",
      "overlap_token_count": 25,
      "semantic_match": true,
      "sequence_ratio": 0.993421,
      "source_negation_count": 0,
      "source_token_count": 26,
      "token_f1": 0.961538,
      "token_precision": 0.961538,
      "token_recall": 0.961538,
      "transcript_negation_count": 0,
      "transcript_token_count": 26
    },
    "policy_id": "tts_stt_lexical_fidelity_v1",
    "producer_branch_id": "branch-text_to_speech-1",
    "producer_phase_id": "phase-2",
    "reason_code": "TTS_STT_SEMANTIC_MATCH",
    "semantic_match": true,
    "source_sha256": "c32d815e23f5498a7cd7135bbac55303649bc6f1034a7f37c7428fbf4c53a9cc",
    "status": "matched",
    "thresholds": {
      "min_sequence_ratio": 0.6,
      "min_source_tokens_for_full_policy": 4,
      "min_token_precision": 0.65,
      "min_token_recall": 0.85,
      "short_min_sequence_ratio": 0.86,
      "short_min_token_f1": 0.8
    },
    "transcript_sha256": "d0351dd8c6f2f2d50c33082376d62ca7aeb912337a713ab7bd99fe79f71d4a5a",
    "transcript_text": "Thick gray fog clings heavily to the jagged rocks around the lighthouse base. The rhythmic pulse of the beacon barely pierces through the dense, damp haze.",
    "version": 1
  }
}
```

## Audio evidence

The recorded TTS executor was `mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16`. The exact backend prompt
was bound to this WAV by the source digest. The runtime recorded
`single_sequence` generation, `344` maximum audio tokens,
and no generation-limit exhaustion.

| Recorded measurement | Value |
| --- | --- |
| WAV format | 24000 Hz, 1 channel, PCM 16-bit |
| Duration | 8.32 s |
| Active signal | 7.5 s |
| Total silence | 0.82 s |
| Longest internal silence | 0.7 s |
| Trailing silence | 0.12 s |

```json
{
  "kind": "fruth.tts_audio_integrity_evidence",
  "authority": "runtime_deterministic_audio_verification",
  "status": "passed",
  "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
  "source_digest_match": true,
  "source_sha256": "c32d815e23f5498a7cd7135bbac55303649bc6f1034a7f37c7428fbf4c53a9cc",
  "artifact_sha256": "0f34fa4d8620d3ec0d47be0007c6c670f3cc92b606ccbf9d80311990163b6cfe",
  "artifact_size_bytes": 399404,
  "materialization_eligible": true
}
```

These are the run's recorded physical-integrity and source-binding checks.
Publication did not add a new listening test or speech-recognition pass.

## Runtime truth and monitor snapshot

| Evidence | Verified state |
| --- | --- |
| Response lifecycle | `completed`, terminal |
| Late fill | `completed`; zero failed or pending branches |
| Final materialization contract | `fulfilled` |
| Graph Closure | `fulfilled`; no open continuation or actionable repair |
| Surface state | `fulfilled` |
| Saved artifact count | 2 |
| Independent monitor | `clean` for this exact final frame |
| Missing files / SHA mismatches / HTML or CSS issues | zero |

The monitor snapshot was recorded at `2026-09-18T16:03:02.136849Z`. Publication
review rechecked the source files and recorded hashes, as well as existing bundle
hashes and relative links where present. The exporter independently verified the
indexed frame, its terminal state, matching monitor evidence and exact prompt.

## Why this is a reference

This run demonstrates how a generated audio artifact becomes the exact input of a later transcription branch, with digest-bound source and transcript fidelity evidence.

It is one observed Fruth execution of this prompt. Broader conformance and model
quality claims require their own evidence.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
