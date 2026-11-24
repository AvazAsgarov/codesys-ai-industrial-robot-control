# 9. YOLOE visual prompts from rendered reference views

- **Status:** Accepted (supersedes the text-prompt part of ADR 0005)
- **Date:** 2026-11-25

## Context

ADR 0005 chose zero-shot YOLOE-26 with text prompts and set a fallback: if mAP@0.5 on the final
part set stays below 0.80, change the part set or adapt the detector. The part set is three
scanned products (Google Scanned Objects): `probiotic_box`, `vitamin_jar`, `coffee_can`.

On the rendered benchmark (seed 301, 500 frames, 951 parts, the inspection camera at 25° tilt):

| Detector | Prompts | mAP@0.5 |
|---|---|---|
| YOLO26s-seg (COCO classes) | box / bottle / can mapped to COCO | 0.058 |
| YOLOE-26s-seg | text: box, bottle, can | 0.138 |
| YOLOE-26s-seg | text, image rotated 90° | 0.566 |
| YOLOE-26s-seg | **visual prompts** | **0.997** |

Text prompts are weak on these renders (best tuned text setup on the tuning seed: 0.9998 at 40°
tilt with the image turned and the prompts carton / bottle / coffee can, but that needs a
different camera and part set): the products seen from above do not look like the average
"bottle" or "can" in the text embedding space. The owner ruled out fine-tuning.

## Decision

Use YOLOE **visual prompts**: render six seeded reference scenes of the twin (every class once
per scene, random lighting), give YOLOE the box of each example, average the visual prompt
embeddings per class and fold them into the network with `set_classes`, then export to OpenVINO
(`airc vision export --prompts visual`). Nothing is trained; the reference scenes are generated
from the twin, so a new part type needs only its mesh.

Text prompts and YOLO26 COCO stay as baselines in the benchmark (`airc eval vision`).

## Consequences

- The fallback of ADR 0005 is not needed: mAP@0.5 0.997 against the 0.80 threshold
  (AP box 1.000, jar 0.997, can 0.993).
- Position error 2.0 mm mean (p95 3.1 mm) on the belt plane, from the mask centroid and the
  calibrated camera; well inside the suction cup's tolerance.
- Box orientation 1.0° p95 from a rectangle fit on the belt plane; about 3 % of the nearly square
  boxes come out 90° off (the suction cup does not need the orientation to pick).
- Detection runs at about 170 ms per frame on the laptop CPU, off the bridge cycle (vision
  worker thread), so the 20 ms bridge loop is not affected.
- The reference views come from the same renderer as the test frames: the result shows that the
  pipeline works without training, not that it transfers to real camera images. The paper states
  this limit.
