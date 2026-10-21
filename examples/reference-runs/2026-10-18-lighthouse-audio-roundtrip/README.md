# Lighthouse Audio Roundtrip

**Status:** verified Fruth reference run  
**Run date:** 2026-10-18; export verified 2026-10-21  
**Response:** `resp_1792343088298_ddd4978b607ad`  
**Final frame:** `resp_1792343088298_ddd4978b607ad:frame-2`

## Request

```text
Write a short two-sentence English field note about fog surrounding a coastal lighthouse. Create one local WAV audio artifact that reads the complete note in a calm, natural voice. Then transcribe that generated audio back into text. Return the original note, the audio, and the transcription together.
```

## Written source

A dense, salt-scented fog clings heavily to the base of the lighthouse. The rhythmic beam struggles to pierce through the thick, white shroud.

## Transcription

A dense, salt-scented fog clings heavily to the base of the lighthouse. The rhythmic beam struggles to pierce through the thick white shroud.

The recorded lexical comparison matches after normalization; the written
texts differ in punctuation. The generated WAV is bound to the STT consumer.

## Saved artifacts

- [WAV artifact](artifacts/audio/narration.wav)
- [MD artifact](artifacts/transcripts/transcript.md)

## Recorded binding and integrity evidence

These records bind the accepted inputs and saved bytes. Physical audio
integrity and source binding alone do not certify every spoken word;
Lighthouse additionally records the transcript comparison.

```json
{
  "tts_audio_integrity_evidence": [
    {
      "active_rms_threshold": 0.010632,
      "active_window_count": 81,
      "artifact_path": "canonical-artifact:20261018T170600Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
      "artifact_sha256": "c08bb767857842da78d12a57e2aa8c2a6e0d95c5d38acfafe698f1833b14343c",
      "artifact_size_bytes": 445484,
      "authority": "runtime_deterministic_audio_verification",
      "channel_count": 1,
      "compression_type": "NONE",
      "container": "wav",
      "declared_source_sha256": "412e9d112d4a13cba04ed9f5fa4f5b47bc6c880d9c3cd9ab7bf1dad59962f689",
      "effective_active_seconds": 8.1,
      "encoding": "pcm_s16le",
      "frame_count": 222720,
      "generation_limit_evidence": {
        "audio_tokens_per_second": 12.5,
        "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
        "completion_signal": "not_exposed_by_backend",
        "expected_limit_duration_seconds": 26.0,
        "expected_limit_frame_count": 624000,
        "frame_delta_from_limit": -401280,
        "generation_limit_reached": false,
        "generation_scope": "single_sequence",
        "inferred_audio_tokens": 116,
        "kind": "fruth.tts_generation_limit_evidence",
        "max_tokens": 325,
        "model_family": "qwen3_tts",
        "observed_duration_seconds": 9.28,
        "observed_frame_count": 222720,
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
      "minimum_expected_active_seconds": 4.8,
      "model_family": "qwen3_tts",
      "nominal_duration_seconds": 9.28,
      "peak_window_rms": 0.212634,
      "policy_id": "tts_wav_signal_completeness_v2",
      "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
      "sample_rate_hz": 24000,
      "sample_width_bytes": 2,
      "silence_ratio": 0.127155,
      "silence_seconds": 1.18,
      "source_character_count": 142,
      "source_digest_match": true,
      "source_sha256": "412e9d112d4a13cba04ed9f5fa4f5b47bc6c880d9c3cd9ab7bf1dad59962f689",
      "source_word_count": 24,
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
      "trailing_silence_ratio": 0.019397,
      "trailing_silence_seconds": 0.18,
      "tts_model_type": "voice_design",
      "version": 1,
      "window_count": 93
    }
  ],
  "generation_limit_evidence": [
    {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 26.0,
      "expected_limit_frame_count": 624000,
      "frame_delta_from_limit": -401280,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 116,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 325,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 9.28,
      "observed_frame_count": 222720,
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
      "tts_source_text": "A dense, salt-scented fog clings heavily to the base of the lighthouse. The rhythmic beam struggles to pierce through the thick, white shroud.",
      "tts_source_text_sha256": "412e9d112d4a13cba04ed9f5fa4f5b47bc6c880d9c3cd9ab7bf1dad59962f689",
      "tts_source_text_source": "inference_final_spoken_prompt",
      "version": 1
    }
  ],
  "tts_stt_semantic_evidence": [
    {
      "authority": "runtime_deterministic_verification",
      "consumer_branch_id": "branch-speech_to_text-1",
      "consumer_phase_id": "phase-3",
      "detected_lang_code": "en",
      "expected_lang_code": "english",
      "kind": "fruth.tts_stt_semantic_evidence",
      "metrics": {
        "exact_match": true,
        "negation_consistent": true,
        "normalized_source": "a dense salt scented fog clings heavily to the base of the lighthouse the rhythmic beam struggles to pierce through the thick white shroud",
        "normalized_transcript": "a dense salt scented fog clings heavily to the base of the lighthouse the rhythmic beam struggles to pierce through the thick white shroud",
        "overlap_token_count": 24,
        "semantic_match": true,
        "sequence_ratio": 1.0,
        "source_negation_count": 0,
        "source_token_count": 24,
        "token_f1": 1.0,
        "token_precision": 1.0,
        "token_recall": 1.0,
        "transcript_negation_count": 0,
        "transcript_token_count": 24
      },
      "policy_id": "tts_stt_lexical_fidelity_v1",
      "producer_branch_id": "branch-text_to_speech-1",
      "producer_phase_id": "phase-2",
      "reason_code": "TTS_STT_SEMANTIC_MATCH",
      "semantic_match": true,
      "source_sha256": "412e9d112d4a13cba04ed9f5fa4f5b47bc6c880d9c3cd9ab7bf1dad59962f689",
      "status": "matched",
      "thresholds": {
        "min_sequence_ratio": 0.6,
        "min_source_tokens_for_full_policy": 4,
        "min_token_precision": 0.65,
        "min_token_recall": 0.85,
        "short_min_sequence_ratio": 0.86,
        "short_min_token_f1": 0.8
      },
      "transcript_sha256": "8b4e40fc2d930b5ba7ed7831cd4996a72eb056ad328d19d46f50a10a68815635",
      "transcript_text": "A dense, salt-scented fog clings heavily to the base of the lighthouse. The rhythmic beam struggles to pierce through the thick white shroud.",
      "version": 1
    }
  ]
}
```

## Runtime truth and scope

The final frame is completed, with fulfilled materialization and Closure and no
pending or failed branches. Its exact-frame monitor verdict is `clean`, recorded
at `2026-10-18T17:07:15.800638Z`. Saved bytes and package checksums were
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
