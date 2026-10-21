# Funny Animal Selfies

**Status:** verified Fruth reference run  
**Run date:** 2026-10-18; export verified 2026-10-21  
**Response:** `resp_1792349890648_bcedf37220fd08`  
**Final frame:** `resp_1792349890648_bcedf37220fd08:frame-2`

## Request

```text
Create a playful series of exactly three funny animal selfies. Choose the animals, settings, poses, and visual style yourself, but make the three images clearly distinct. Then inspect each generated image separately and briefly describe only what is actually visible, including any accidental readable text or obvious visual defect.
```

## Recorded image inspection

**Branch 1 (capybara):** A capybara floats face-up in a steaming pool or hot spring, head and upper body above the surface. Wet brown fur, large dark snout with pinkish nose, small rounded ears, dark eyes, and whiskers are visible. Its front limbs rest on the water. A single orange slice sits cut-face-up on its head. Steam rises from the water; the background is blurred tropical greenery with rocks along the edge and soft bokeh highlights.

**Branch 2 (raccoon):** A raccoon with grey and black fur stands in a dimly lit kitchen, holding a slice of pepperoni pizza in its paws. Background shows cabinets, a refrigerator, and a window. No readable text or obvious defects visible.

**Branch 3 (giraffe):** A close-up, wide-angle giraffe wearing large pink heart-shaped sunglasses with purple-tinted lenses, centered in the foreground. Background is a dry golden savanna under a clear blue sky, with scattered acacia trees and small distant animals on the plains. No readable text or obvious defects visible.

Each of the three vision consumers records the exact supplied image digest.
The descriptions above are model interpretations, not independent human
verification of every visible detail.

## Saved artifacts

- [PNG artifact](artifacts/images/image-01.png)
- [PNG artifact](artifacts/images/image-02.png)
- [PNG artifact](artifacts/images/image-03.png)

## Recorded binding and integrity evidence

These records establish input/output binding; semantic accuracy remains
a separate question.

```json
{
  "vision_input_evidence": [
    {
      "authority": "runtime_vision_image_dispatch",
      "branch_id": "branch-vision_analysis-1",
      "image_sha256": "ed4d6b00b3bcbcd142a5b9949cfb9013d2086554a531dfe9e3e8d6ab1d05b8bd",
      "instance_id": "ornith-1.5:9b-1",
      "kind": "fruth.vision_input_evidence",
      "phase_id": "phase-5",
      "response_id": "resp_1792349890648_bcedf37220fd08",
      "size_bytes": 1252133,
      "status": "supplied",
      "version": 1
    },
    {
      "authority": "runtime_vision_image_dispatch",
      "branch_id": "branch-vision_analysis-2",
      "image_sha256": "13a41144c2b339c2ae7088e011a488b0ef01d877b9a49d0487fa2a401f3fc562",
      "instance_id": "mlx-community__gemma-4-E4B-it-qat-8bit-mlx-11501",
      "kind": "fruth.vision_input_evidence",
      "phase_id": "phase-6",
      "response_id": "resp_1792349890648_bcedf37220fd08",
      "size_bytes": 369282,
      "status": "supplied",
      "version": 1
    },
    {
      "authority": "runtime_vision_image_dispatch",
      "branch_id": "branch-vision_analysis-3",
      "image_sha256": "bf1ccf7e143a650c9dabe0535a7705b7c8553f7bc6b9325da3a77e1fdf106889",
      "instance_id": "gemma4:26b-1",
      "kind": "fruth.vision_input_evidence",
      "phase_id": "phase-7",
      "response_id": "resp_1792349890648_bcedf37220fd08",
      "size_bytes": 1462653,
      "status": "supplied",
      "version": 1
    }
  ]
}
```

## Runtime truth and scope

The final frame is completed, with fulfilled materialization and Closure and no
pending or failed branches. Its exact-frame monitor verdict is `clean`, recorded
at `2026-10-18T19:08:20.353536Z`. Saved bytes and package checksums were
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
