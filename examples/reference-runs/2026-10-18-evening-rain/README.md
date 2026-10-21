# Evening Rain

**Status:** verified Fruth reference run  
**Run date:** 2026-10-18; export verified 2026-10-21  
**Response:** `resp_1792342940935_63e5a8351b76`  
**Final frame:** `resp_1792342940935_63e5a8351b76:frame-2`

## Request

```text
Write a short three-sentence English reflection about evening rain. Then create exactly one local audio artifact that reads the complete reflection aloud in a calm, natural voice. Return the written reflection and the finished audio together.
```

## Written source

The soft pitter-patter of raindrops against the windowpane signals the day's gentle end. A cool, damp mist settles over the streets, washing away the heat of the afternoon. In the quiet rhythm of the falling rain, the world seems to find a moment of profound peace.

## Saved artifacts

- [WAV artifact](artifacts/audio/narration.wav)

## Recorded binding and integrity evidence

These records bind the accepted inputs and saved bytes. Physical audio
integrity and source binding alone do not certify every spoken word;
Lighthouse additionally records the transcript comparison.

```json
{
  "tts_audio_integrity_evidence": [
    {
      "active_rms_threshold": 0.008772,
      "active_window_count": 177,
      "artifact_path": "canonical-artifact:20261018T170339Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
      "artifact_sha256": "8a61ccf6bcc6f800b92b77d4be5f41d5869e4077b7f50faf2617c945d4efafc6",
      "artifact_size_bytes": 1294124,
      "authority": "runtime_deterministic_audio_verification",
      "channel_count": 1,
      "compression_type": "NONE",
      "container": "wav",
      "declared_source_sha256": "7ef84ddd2dc01d1186f5ec128b41a343232d7dd4430b530ae6c9687d497e1286",
      "effective_active_seconds": 17.7,
      "encoding": "pcm_s16le",
      "frame_count": 647040,
      "generation_limit_evidence": {
        "audio_tokens_per_second": 12.5,
        "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
        "completion_signal": "not_exposed_by_backend",
        "expected_limit_duration_seconds": 43.28,
        "expected_limit_frame_count": 1038720,
        "frame_delta_from_limit": -391680,
        "generation_limit_reached": false,
        "generation_scope": "single_sequence",
        "inferred_audio_tokens": 337,
        "kind": "fruth.tts_generation_limit_evidence",
        "max_tokens": 541,
        "model_family": "qwen3_tts",
        "observed_duration_seconds": 26.96,
        "observed_frame_count": 647040,
        "policy_id": "qwen3_tts_generation_limit_exhaustion_v1",
        "reason_code": "TTS_AUDIO_GENERATION_LIMIT_NOT_REACHED",
        "samples_per_audio_token": 1920,
        "status": "passed",
        "tts_model_type": "voice_design",
        "version": 1
      },
      "kind": "fruth.tts_audio_integrity_evidence",
      "leading_silence_seconds": 0.0,
      "longest_internal_silence_seconds": 2.3,
      "materialization_eligible": true,
      "minimum_expected_active_seconds": 9.4,
      "model_family": "qwen3_tts",
      "nominal_duration_seconds": 26.96,
      "peak_window_rms": 0.175432,
      "policy_id": "tts_wav_signal_completeness_v2",
      "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
      "sample_rate_hz": 24000,
      "sample_width_bytes": 2,
      "silence_ratio": 0.343472,
      "silence_seconds": 9.26,
      "source_character_count": 265,
      "source_digest_match": true,
      "source_sha256": "7ef84ddd2dc01d1186f5ec128b41a343232d7dd4430b530ae6c9687d497e1286",
      "source_word_count": 47,
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
      "trailing_silence_ratio": 0.017062,
      "trailing_silence_seconds": 0.46,
      "tts_model_type": "voice_design",
      "version": 1,
      "window_count": 270
    }
  ],
  "generation_limit_evidence": [
    {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 43.28,
      "expected_limit_frame_count": 1038720,
      "frame_delta_from_limit": -391680,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 337,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 541,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 26.96,
      "observed_frame_count": 647040,
      "policy_id": "qwen3_tts_generation_limit_exhaustion_v1",
      "reason_code": "TTS_AUDIO_GENERATION_LIMIT_NOT_REACHED",
      "samples_per_audio_token": 1920,
      "status": "passed",
      "tts_model_type": "voice_design",
      "version": 1
    }
  ],
  "tts_semantic_source": [
    {
      "authority": "runtime_exact_backend_prompt",
      "branch_id": "branch-text_to_speech-1",
      "kind": "fruth.tts_semantic_source",
      "lang_code": "english",
      "phase_id": "phase-2",
      "policy_id": "tts_stt_lexical_fidelity_v1",
      "source_authority": "final_infer_prompt",
      "tts_source_text": "The soft pitter-patter of raindrops against the windowpane signals the day's gentle end. A cool, damp mist settles over the streets, washing away the heat of the afternoon. In the quiet rhythm of the falling rain, the world seems to find a moment of profound peace.",
      "tts_source_text_sha256": "7ef84ddd2dc01d1186f5ec128b41a343232d7dd4430b530ae6c9687d497e1286",
      "tts_source_text_source": "inference_final_spoken_prompt",
      "version": 1
    }
  ]
}
```

## Runtime truth and scope

The final frame is completed, with fulfilled materialization and Closure and no
pending or failed branches. Its exact-frame monitor verdict is `clean`, recorded
at `2026-10-18T17:07:09.974080Z`. Saved bytes and package checksums were
rechecked during export; the original frame and monitor record remain unchanged.

This run preceded the October 18 Echoes continuation corrections.
All five October 18 references therefore do not share one identical source
revision. They also precede the October 19 image idle-residency fix.

This is one recorded local workflow. It does not establish a general success
rate, a controlled performance comparison, or an AFM/PCC verdict. No inference
or new content generation was performed for this export.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
