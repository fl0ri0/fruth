# Lighthouse Audio Roundtrip

**Status:** verified Fruth reference run  
**Run and review date:** 2026-10-10  
**Response:** `resp_1791661038279_0aaf0718e7e63`  
**Final frame:** `resp_1791661038279_0aaf0718e7e63:frame-2`

## Request

```text
Write a short two-sentence English field note about fog surrounding a coastal lighthouse. Create one local WAV audio artifact that reads the complete note in a calm, natural voice. Then transcribe that generated audio back into text. Return the original note, the audio, and the transcription together.
```

## Result

Original field note:

> A heavy, salt-damp fog has settled around the base of the coastal lighthouse. The beam struggles to penetrate the thick, grey shroud, casting only a faint, rhythmic pulse into the gloom.

Recorded transcription:

> A heavy, salt-damp fog has settled around the base of the coastal lighthouse. The beam struggles to penetrate the thick, gray shroud, casting only a faint, rhythmic pulse into the gloom.

The lexical-fidelity policy accepted the roundtrip. It is not a byte-identical transcript: the original uses “grey” and the transcription “gray”. The consumer received the exact generated WAV, bound by producer identity and file digest.

- [Saved audio](artifacts/audio/narration.wav)
- [Saved text](artifacts/transcripts/transcript.md)

### Roundtrip evidence

```json
{
  "audio_input": {
    "artifact_id": "audio_a63fb83ff1f4d8c4c75214f3",
    "artifact_ref": "artifact:audio_a63fb83ff1f4d8c4c75214f3",
    "authority": "canonical_direct_audio_dependency",
    "branch_id": "branch-text_to_speech-1",
    "file_sha256": "482ca8cc807d7896ce5901051a0842666616a2e895be57a38474c2247fb98f37",
    "obligation_id": "obligation-phase-2",
    "path": "canonical-artifact:20261010T193827Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
    "phase_id": "phase-2",
    "provider_input_sha256": "482ca8cc807d7896ce5901051a0842666616a2e895be57a38474c2247fb98f37",
    "source_response_id": "resp_1791661038279_0aaf0718e7e63",
    "status": "verified"
  },
  "semantic_match": {
    "authority": "runtime_deterministic_verification",
    "consumer_branch_id": "branch-speech_to_text-1",
    "consumer_phase_id": "phase-3",
    "detected_lang_code": "en",
    "expected_lang_code": "english",
    "kind": "fruth.tts_stt_semantic_evidence",
    "metrics": {
      "exact_match": false,
      "negation_consistent": true,
      "normalized_source": "a heavy salt damp fog has settled around the base of the coastal lighthouse the beam struggles to penetrate the thick grey shroud casting only a faint rhythmic pulse into the gloom",
      "normalized_transcript": "a heavy salt damp fog has settled around the base of the coastal lighthouse the beam struggles to penetrate the thick gray shroud casting only a faint rhythmic pulse into the gloom",
      "overlap_token_count": 31,
      "semantic_match": true,
      "sequence_ratio": 0.994444,
      "source_negation_count": 0,
      "source_token_count": 32,
      "token_f1": 0.96875,
      "token_precision": 0.96875,
      "token_recall": 0.96875,
      "transcript_negation_count": 0,
      "transcript_token_count": 32
    },
    "policy_id": "tts_stt_lexical_fidelity_v1",
    "producer_branch_id": "branch-text_to_speech-1",
    "producer_phase_id": "phase-2",
    "reason_code": "TTS_STT_SEMANTIC_MATCH",
    "semantic_match": true,
    "source_sha256": "e0045a28414b5a6a56e9f4599d3cf28eb142f72819a6b65abae156e9a9f2e7ad",
    "status": "matched",
    "thresholds": {
      "min_sequence_ratio": 0.6,
      "min_source_tokens_for_full_policy": 4,
      "min_token_precision": 0.65,
      "min_token_recall": 0.85,
      "short_min_sequence_ratio": 0.86,
      "short_min_token_f1": 0.8
    },
    "transcript_sha256": "e62018fcabaae11329ad6a1d59b592e9a8223136fee6c667b6b6f04565f3ea45",
    "transcript_text": "A heavy, salt-damp fog has settled around the base of the coastal lighthouse. The beam struggles to penetrate the thick, gray shroud, casting only a faint, rhythmic pulse into the gloom.",
    "version": 1
  }
}
```

## Audio source and integrity

The recorded exact backend text and deterministic physical WAV checks were rechecked against the saved bytes. Physical integrity and source binding alone do not certify every spoken word; the Lighthouse case adds its explicit STT fidelity evidence.

```json
{
  "tts_semantic_source": {
    "authority": "runtime_exact_backend_prompt",
    "branch_id": "branch-text_to_speech-1",
    "kind": "fruth.tts_semantic_source",
    "lang_code": "english",
    "phase_id": "phase-2",
    "policy_id": "tts_stt_lexical_fidelity_v1",
    "source_authority": "final_infer_prompt",
    "tts_source_text": "A heavy, salt-damp fog has settled around the base of the coastal lighthouse. The beam struggles to penetrate the thick, grey shroud, casting only a faint, rhythmic pulse into the gloom.",
    "tts_source_text_sha256": "e0045a28414b5a6a56e9f4599d3cf28eb142f72819a6b65abae156e9a9f2e7ad",
    "tts_source_text_source": "inference_final_spoken_prompt",
    "version": 1
  },
  "tts_audio_integrity_evidence": {
    "active_rms_threshold": 0.010054,
    "active_window_count": 100,
    "artifact_path": "canonical-artifact:20261010T193827Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
    "artifact_sha256": "482ca8cc807d7896ce5901051a0842666616a2e895be57a38474c2247fb98f37",
    "artifact_size_bytes": 579884,
    "authority": "runtime_deterministic_audio_verification",
    "channel_count": 1,
    "compression_type": "NONE",
    "container": "wav",
    "declared_source_sha256": "e0045a28414b5a6a56e9f4599d3cf28eb142f72819a6b65abae156e9a9f2e7ad",
    "effective_active_seconds": 10.0,
    "encoding": "pcm_s16le",
    "frame_count": 289920,
    "generation_limit_evidence": {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 32.0,
      "expected_limit_frame_count": 768000,
      "frame_delta_from_limit": -478080,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 151,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 400,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 12.08,
      "observed_frame_count": 289920,
      "policy_id": "qwen3_tts_generation_limit_exhaustion_v1",
      "reason_code": "TTS_AUDIO_GENERATION_LIMIT_NOT_REACHED",
      "samples_per_audio_token": 1920,
      "status": "passed",
      "tts_model_type": "voice_design",
      "version": 1
    },
    "kind": "fruth.tts_audio_integrity_evidence",
    "leading_silence_seconds": 0.0,
    "longest_internal_silence_seconds": 0.7,
    "materialization_eligible": true,
    "minimum_expected_active_seconds": 6.4,
    "model_family": "qwen3_tts",
    "nominal_duration_seconds": 12.08,
    "peak_window_rms": 0.201071,
    "policy_id": "tts_wav_signal_completeness_v2",
    "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
    "sample_rate_hz": 24000,
    "sample_width_bytes": 2,
    "silence_ratio": 0.172185,
    "silence_seconds": 2.08,
    "source_character_count": 186,
    "source_digest_match": true,
    "source_sha256": "e0045a28414b5a6a56e9f4599d3cf28eb142f72819a6b65abae156e9a9f2e7ad",
    "source_word_count": 32,
    "status": "passed",
    "thresholds": {
      "absolute_active_rms": 0.0015,
      "max_sentence_chunk_internal_silence_seconds": 3.0,
      "max_trailing_silence_ratio": 0.65,
      "max_trailing_silence_seconds": 4.0,
      "max_trailing_to_active_ratio": 2.5,
      "max_words_per_second": 5.0,
      "min_expected_active_seconds": 0.25,
      "relative_active_rms": 0.05,
      "window_seconds": 0.1
    },
    "trailing_silence_ratio": 0.014901,
    "trailing_silence_seconds": 0.18,
    "tts_model_type": "voice_design",
    "version": 1,
    "window_count": 121
  }
}
```

## Runtime truth and monitor

The final response is terminal and completed. Late Fill, the materialization contract, Closure and surface state are fulfilled, with no pending or failed branches. The independent monitor reports `clean` for this exact final frame; no missing files, hash mismatches or HTML/CSS issues were reported.

The monitor report was recorded at `2026-10-10T20:20:33.981333Z` after execution, during backlog reconciliation. Source artifacts were rechecked during this export.

Monitor phase timings are diagnostic observations, not a benchmark. Backfilled event-window fields can include another response’s activity (the Echoes image-wave end is later than its own terminal output); these phase-duration fields are retained as observed but are not used to admit a reference or compare performance.

## Scope

This is one recorded local execution of the exact prompt. It supplements the dated conformance results; it does not establish a general success rate or a new AFM/PCC verdict. The original response frame and runtime artifacts remain authoritative.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
