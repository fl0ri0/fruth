# Echoes of the Pass

**Status:** verified Fruth reference run  
**Run date:** 2026-10-18; export verified 2026-10-21  
**Response:** `resp_1792349272560_7cc71d82684358`  
**Final frame:** `resp_1792349272560_7cc71d82684358:frame-3`

## Request

```text
Create a quiet local exhibition website for a fictional alpine sound archive called Echoes of the Pass.

Create index.html and styles.css, exactly two atmospheric mountain images, and one English WAV narration. The narration must say exactly: “Above the tree line, wind and stone preserve the memory of every season.”

Use one image as the hero and the other in a listening section. Include a working audio player for the narration. Save everything as one complete local bundle with correct relative links and no external assets.
```

## Result

Five requested artifacts were saved: HTML, CSS, two generated mountain
images and one WAV narration. Final materialization and Closure are fulfilled.
The portable bundle resolves the local CSS, image and audio links.

This is the later completed run after the continuation corrections. Earlier
attempts are retained separately and are not relabelled as successful.

## Saved artifacts

- [HTML artifact](bundle/index.html)
- [CSS artifact](bundle/assets/css/styles.css)
- [PNG artifact](bundle/assets/images/image-01.png)
- [PNG artifact](bundle/assets/images/image-02.png)
- [WAV artifact](bundle/assets/audio/narration.wav)

## Portable result

- [Open the portable HTML result](bundle/index.html)
- [Bundle manifest](bundle/manifest.json)

## Recorded binding and integrity evidence

These records bind the accepted inputs and saved bytes. Physical audio
integrity and source binding alone do not certify every spoken word;
Lighthouse additionally records the transcript comparison.

```json
{
  "tts_audio_integrity_evidence": [
    {
      "active_rms_threshold": 0.010026,
      "active_window_count": 47,
      "artifact_path": "canonical-artifact:20261018T185306Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
      "artifact_sha256": "ffc37147a0359bdcb6912602a8001354f0860bfca07b3607d8e2ff23714934a7",
      "artifact_size_bytes": 249644,
      "authority": "runtime_deterministic_audio_verification",
      "channel_count": 1,
      "compression_type": "NONE",
      "container": "wav",
      "declared_source_sha256": "241c60649dd168bec6393acb6a523957af920fa4157b32ae581333d4ca9ba574",
      "effective_active_seconds": 4.7,
      "encoding": "pcm_s16le",
      "frame_count": 124800,
      "generation_limit_evidence": {
        "audio_tokens_per_second": 12.5,
        "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
        "completion_signal": "not_exposed_by_backend",
        "expected_limit_duration_seconds": 20.48,
        "expected_limit_frame_count": 491520,
        "frame_delta_from_limit": -366720,
        "generation_limit_reached": false,
        "generation_scope": "single_sequence",
        "inferred_audio_tokens": 65,
        "kind": "fruth.tts_generation_limit_evidence",
        "max_tokens": 256,
        "model_family": "qwen3_tts",
        "observed_duration_seconds": 5.2,
        "observed_frame_count": 124800,
        "policy_id": "qwen3_tts_generation_limit_exhaustion_v1",
        "reason_code": "TTS_AUDIO_GENERATION_LIMIT_NOT_REACHED",
        "samples_per_audio_token": 1920,
        "status": "passed",
        "tts_model_type": "voice_design",
        "version": 1
      },
      "kind": "fruth.tts_audio_integrity_evidence",
      "leading_silence_seconds": 0.0,
      "longest_internal_silence_seconds": 0.3,
      "materialization_eligible": true,
      "minimum_expected_active_seconds": 2.6,
      "model_family": "qwen3_tts",
      "nominal_duration_seconds": 5.2,
      "peak_window_rms": 0.200522,
      "policy_id": "tts_wav_signal_completeness_v2",
      "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
      "sample_rate_hz": 24000,
      "sample_width_bytes": 2,
      "silence_ratio": 0.096154,
      "silence_seconds": 0.5,
      "source_character_count": 72,
      "source_digest_match": true,
      "source_sha256": "241c60649dd168bec6393acb6a523957af920fa4157b32ae581333d4ca9ba574",
      "source_word_count": 13,
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
      "trailing_silence_ratio": 0.019231,
      "trailing_silence_seconds": 0.1,
      "tts_model_type": "voice_design",
      "version": 1,
      "window_count": 52
    }
  ],
  "generation_limit_evidence": [
    {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 20.48,
      "expected_limit_frame_count": 491520,
      "frame_delta_from_limit": -366720,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 65,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 256,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 5.2,
      "observed_frame_count": 124800,
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
      "phase_id": "phase-4",
      "policy_id": "tts_stt_lexical_fidelity_v1",
      "source_authority": "final_infer_prompt",
      "tts_source_text": "Above the tree line, wind and stone preserve the memory of every season.",
      "tts_source_text_sha256": "241c60649dd168bec6393acb6a523957af920fa4157b32ae581333d4ca9ba574",
      "tts_source_text_source": "inference_final_spoken_prompt",
      "version": 1
    }
  ]
}
```

## Runtime truth and scope

The final frame is completed, with fulfilled materialization and Closure and no
pending or failed branches. Its exact-frame monitor verdict is `clean`, recorded
at `2026-10-18T18:58:17.571656Z`. Saved bytes and package checksums were
rechecked during export; the original frame and monitor record remain unchanged.

This run followed the October 18 Echoes continuation corrections.
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
