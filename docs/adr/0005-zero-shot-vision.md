# 5. Zero-shot detection with YOLO26 / YOLOE-26 on OpenVINO

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

Parts must be identified and located on the belt. The owner prefers not to train a detector;
the laptop has no NVIDIA GPU.

## Decision

Use pretrained Ultralytics YOLOE-26 (text-prompted, open-vocabulary segmentation) and YOLO26
(COCO) as a comparison, exported to OpenVINO and run on CPU (iGPU optional). Pose is derived
from the segmentation mask. Accuracy is measured against the simulator's exact ground truth.

Fallback: if zero-shot mAP@0.5 on the final part set stays below 0.80 after prompt tuning,
change the part set or fine-tune on auto-labelled synthetic data, and report it in the paper.

## Consequences

- No training compute or labelling effort.
- The repository is licensed AGPL-3.0 to match Ultralytics.
- Part types are chosen from textured scanned objects (Google Scanned Objects, CC BY 4.0) that
  text prompts can name.
