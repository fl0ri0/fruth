# Echoes of the Pass

**Status:** verified Fruth reference run  
**Run and review date:** 2026-10-10  
**Response:** `resp_1791660495291_eee430ac1667a`  
**Final frame:** `resp_1791660495291_eee430ac1667a:frame-2`

## Request

```text
Create a quiet local exhibition website for a fictional alpine sound archive called Echoes of the Pass.

Create index.html and styles.css, exactly two atmospheric mountain images, and one English WAV narration. The narration must say exactly: “Above the tree line, wind and stone preserve the memory of every season.”

Use one image as the hero and the other in a listening section. Include a working audio player for the narration. Save everything as one complete local bundle with correct relative links and no external assets.
```

## Result

Five requested artifacts were saved: HTML, CSS, two mountain images and one English WAV narration. The portable bundle resolves its local CSS, image and audio links.


## Audio source and integrity

The recorded exact backend text and deterministic physical WAV checks were rechecked against the saved bytes. Physical integrity and source binding alone do not certify every spoken word; the Lighthouse case adds its explicit STT fidelity evidence.

```json
{
  "tts_semantic_source": {
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
  },
  "tts_audio_integrity_evidence": {
    "active_rms_threshold": 0.010131,
    "active_window_count": 44,
    "artifact_path": "canonical-artifact:20261010T193021Z_audio_mlx-community_Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16.wav",
    "artifact_sha256": "e5ef3e9c01c38c3fbfe8cb128172c59758ea300d53ee6e0e9489e75f10fd3511",
    "artifact_size_bytes": 238124,
    "authority": "runtime_deterministic_audio_verification",
    "channel_count": 1,
    "compression_type": "NONE",
    "container": "wav",
    "declared_source_sha256": "241c60649dd168bec6393acb6a523957af920fa4157b32ae581333d4ca9ba574",
    "effective_active_seconds": 4.4,
    "encoding": "pcm_s16le",
    "frame_count": 119040,
    "generation_limit_evidence": {
      "audio_tokens_per_second": 12.5,
      "budget_policy_id": "qwen3_tts_adaptive_audio_tokens_v2",
      "completion_signal": "not_exposed_by_backend",
      "expected_limit_duration_seconds": 20.48,
      "expected_limit_frame_count": 491520,
      "frame_delta_from_limit": -372480,
      "generation_limit_reached": false,
      "generation_scope": "single_sequence",
      "inferred_audio_tokens": 62,
      "kind": "fruth.tts_generation_limit_evidence",
      "max_tokens": 256,
      "model_family": "qwen3_tts",
      "observed_duration_seconds": 4.96,
      "observed_frame_count": 119040,
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
    "nominal_duration_seconds": 4.96,
    "peak_window_rms": 0.202611,
    "policy_id": "tts_wav_signal_completeness_v2",
    "reason_code": "TTS_AUDIO_INTEGRITY_PASSED",
    "sample_rate_hz": 24000,
    "sample_width_bytes": 2,
    "silence_ratio": 0.112903,
    "silence_seconds": 0.56,
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
    "trailing_silence_ratio": 0.032258,
    "trailing_silence_seconds": 0.16,
    "tts_model_type": "voice_design",
    "version": 1,
    "window_count": 50
  }
}
```

## Portable result

- [Open the portable HTML result](bundle/index.html)
- [Bundle manifest](bundle/manifest.json)

## Runtime truth and monitor

The final response is terminal and completed. Late Fill, the materialization contract, Closure and surface state are fulfilled, with no pending or failed branches. The independent monitor reports `clean` for this exact final frame; no missing files, hash mismatches or HTML/CSS issues were reported.

The monitor report was recorded at `2026-10-10T20:14:45.673332Z` after execution, during backlog reconciliation. Source artifacts were rechecked during this export.

Monitor phase timings are diagnostic observations, not a benchmark. Backfilled event-window fields can include another response’s activity (the Echoes image-wave end is later than its own terminal output); these phase-duration fields are retained as observed but are not used to admit a reference or compare performance.

## Scope

This is one recorded local execution of the exact prompt. It supplements the dated conformance results; it does not establish a general success rate or a new AFM/PCC verdict. The original response frame and runtime artifacts remain authoritative.

## Publication Package

This directory is a sanitized, immutable publication copy of the reviewed run. It does not replace the original response frame or runtime artifacts.

- [Exact reviewed prompt](prompt.txt)
- [Sanitized final response truth](response.json)
- [Sanitized independent monitor snapshot](monitor-report.json)
- [Package checksums and provenance](manifest.json)
