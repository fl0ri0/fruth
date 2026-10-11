# Evening Rain

**Status:** verified Fruth reference run  
**Run and review date:** 2026-10-10  
**Response:** `resp_1791660884493_83a505967037c`  
**Final frame:** `resp_1791660884493_83a505967037c:frame-2`

## Request

```text
Write a short three-sentence English reflection about evening rain. Then create exactly one local audio artifact that reads the complete reflection aloud in a calm, natural voice. Return the written reflection and the finished audio together.
```

## Result

The written reflection was supplied in full to the audio branch:

> The evening rain descends in a soft, rhythmic pattern against the windowpane. Each drop carries the scent of damp earth and quieted streets. In this gentle deluge, the world seems to settle into a peaceful, contemplative slumber.

[Listen to the saved narration](artifacts/audio/narration.wav)

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
    "tts_source_text": "The evening rain descends in a soft, rhythmic pattern against the windowpane. Each drop carries the scent of damp earth and quieted streets. In this gentle deluge, the world seems to settle into a peaceful, contemplative slumber.",
    "tts_source_text_sha256": "3b58e612a845625d6ab2f22f88b6c874794086a53499a9a82c4d034963c7b958",
    "tts_source_text_source": "inference_final_spoken_prompt",
    "version": 1
  },
  "tts_audio_integrity_evidence": {
    "active_rms_threshold": 0.011927,
    "active_window_count": 131,
    "artifact_path": "canonical-artifact:20261010T193558Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
    "artifact_sha256": "6b53d56ebc5150881635c45ffebdd4cc728cf1cadc105f70ad72258f8a3898cf",
    "artifact_size_bytes": 852524,
    "authority": "runtime_deterministic_audio_verification",
    "channel_count": 1,
    "compression_type": "NONE",
    "container": "wav",
    "declared_source_sha256": "3b58e612a845625d6ab2f22f88b6c874794086a53499a9a82c4d034963c7b958",
    "effective_active_seconds": 13.1,
    "encoding": "pcm_s16le",
    "frame_count": 426240,
    "generation_limit_evidence": {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 35.76,
      "expected_limit_frame_count": 858240,
      "frame_delta_from_limit": -432000,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 222,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 447,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 17.76,
      "observed_frame_count": 426240,
      "policy_id": "qwen3_tts_generation_limit_exhaustion_v1",
      "reason_code": "TTS_AUDIO_GENERATION_LIMIT_NOT_REACHED",
      "samples_per_audio_token": 1920,
      "status": "passed",
      "tts_model_type": "voice_design",
      "version": 1
    },
    "kind": "fruth.tts_audio_integrity_evidence",
    "leading_silence_seconds": 0.0,
    "longest_internal_silence_seconds": 1.2,
    "materialization_eligible": true,
    "minimum_expected_active_seconds": 7.4,
    "model_family": "qwen3_tts",
    "nominal_duration_seconds": 17.76,
    "peak_window_rms": 0.238541,
    "policy_id": "tts_wav_signal_completeness_v2",
    "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
    "sample_rate_hz": 24000,
    "sample_width_bytes": 2,
    "silence_ratio": 0.262387,
    "silence_seconds": 4.66,
    "source_character_count": 229,
    "source_digest_match": true,
    "source_sha256": "3b58e612a845625d6ab2f22f88b6c874794086a53499a9a82c4d034963c7b958",
    "source_word_count": 37,
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
    "trailing_silence_ratio": 0.009009,
    "trailing_silence_seconds": 0.16,
    "tts_model_type": "voice_design",
    "version": 1,
    "window_count": 178
  }
}
```

## Runtime truth and monitor

The final response is terminal and completed. Late Fill, the materialization contract, Closure and surface state are fulfilled, with no pending or failed branches. The independent monitor reports `clean` for this exact final frame; no missing files, hash mismatches or HTML/CSS issues were reported.

The monitor report was recorded at `2026-10-10T20:20:16.935758Z` after execution, during backlog reconciliation. Source artifacts were rechecked during this export.

Monitor phase timings are diagnostic observations, not a benchmark. Backfilled event-window fields can include another response’s activity (the Echoes image-wave end is later than its own terminal output); these phase-duration fields are retained as observed but are not used to admit a reference or compare performance.

## Scope

This is one recorded local execution of the exact prompt. It supplements the dated conformance results; it does not establish a general success rate or a new AFM/PCC verdict. The original response frame and runtime artifacts remain authoritative.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
