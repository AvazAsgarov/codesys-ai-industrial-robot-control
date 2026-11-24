# Vision benchmark (Phase 3, Task 7)

All numbers come from the JSON files next to this one, produced by `airc eval vision` and
`tools/tune_vision.py`.

**Setup.** Frames are rendered from the twin (`airc.evaluation.dataset.render_dataset`). Each
frame has 1-3 non-overlapping parts of the three classes (probiotic_box, vitamin_jar,
coffee_can) near PE1: x = PE1 +-150 mm, y +-80 mm, any yaw. The images use seeded lighting,
noise and blur, and the camera is tilted 25 deg (`config/twin.yaml`). The detector sees the
640 x 640 window around PE1 that the vision worker uses. Ground truth (masks, boxes, belt
poses) is exact. A detection matches a part when it has the same class and box IoU >= 0.5.
P/R and the pose errors use confidence >= 0.25. Pose goes through the worker's own
pixel -> belt conversion (`service.belt_pose`) with the exact camera, and the theta error
respects each part's symmetry: boxes are scored mod 180 deg; the jar and the can are round
and not scored. Latency is the detector call alone (CPU, OpenVINO FP32, Intel Core Ultra 7
255U, laptop under normal load).

## Test seed 301, 500 frames (951 parts: 284 box, 358 jar, 309 can)

| Detector | mAP@0.5 | AP box / jar / can | P / R box | P / R jar | P / R can | pos mm mean / p95 | theta deg mean / p95 (box) | latency ms p50 / p95 |
|---|---|---|---|---|---|---|---|---|
| **yoloe-visual** (cell) | **0.997** | 1.000 / 0.997 / 0.993 | 1.00 / 1.00 | 0.99 / 1.00 | 1.00 / 0.99 | 1.99 / 3.09 | 3.18 / 1.04 | 166 / 194 |
| yoloe text box/bottle/can | 0.138 | 0.331 / 0.083 / 0.000 | 1.00 / 0.04 | - / 0.00 | - / 0.00 | 2.22 / 4.16 | 0.72 / 1.67 | 166 / 194 |
| yoloe text, window turned 90 deg | 0.566 | 0.419 / 0.554 / 0.725 | 1.00 / 0.04 | 0.86 / 0.37 | 1.00 / 0.16 | 2.09 / 2.81 | 0.47 / 0.95 | 176 / 203 |
| yolo26 COCO (only "bottle") | 0.058 | 0.000 / 0.174 / 0.000 | - / 0.00 | 0.45 / 0.18 | - / 0.00 | 1.97 / 2.46 | - | 176 / 211 |
| oracle (true masks) | 1.000 | 1 / 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 | 1.82 / 3.19 | 0.48 / 0.74 | - |

Files: `vision_yoloe-visual_301.json`, `vision_yoloe-text_301.json`,
`vision_yoloe-text-rot90_301.json`, `vision_yolo26_301.json`, `vision_oracle_301.json`.

- With visual prompts, YOLOE-26s passes the plan's gate (mAP@0.5 >= 0.80) without training.
- Position error is the geometry, not the detector. Even the true masks give 1.8 mm mean,
  because the centroid of a tilted view is not the centroid of the footprint. YOLOE's masks
  add about 0.2 mm (max 5.0 mm).
- Theta of the box: the median error is 0.46 deg and the p95 is 1.04 deg. About 3 % of the
  boxes (max 89.6 deg) are reported 90 deg off. The box is almost square (104 x 118 mm), and
  with an imperfect mask the side test sometimes picks the wrong side. With true masks this
  never happens (max 0.76 deg).
- Text prompts are weak, and YOLO26 COCO has no box or can class. Both stay as baselines.

## Tuning seed 300 (text prompts), `vision_tuning.json`

The grid covers tilt {25, 40, 55} deg x 6 class triples (one box of probiotic_box / candy_box /
ink_cartridge, one jar of vitamin_jar / glucosamine_jar, and coffee_can) x 36 prompt wordings
(box: box / cardboard box / carton / package; jar: bottle / jar / pill bottle; can: can /
tin can / coffee can) x window orientation (as seen, or turned a quarter counter-clockwise).
That is 1296 configurations of 60 frames each (kept short; text prompts are the baseline). An
earlier run of 200 frames, cut short after five triples at 25 deg, picked the same best
wording and orientation for each of those triples. One YOLOE export holds every wording, and each triple keeps only its
own labels. The best configuration was confirmed with an export of exactly its three prompts
(mAP 0.9998 both ways).

| # | Tilt | Turned | Classes | Prompts | mAP | AP box / jar / can | pos mm | theta deg | ms p50 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 40 | yes | candy_box, vitamin_jar, coffee_can | carton, bottle, coffee can | 1.000 | 1.000 / 1.000 / 1.000 | 2.84 | 0.61 | 210 |
| 2 | 40 | yes | candy_box, glucosamine_jar, coffee_can | carton, bottle, coffee can | 0.992 | 1.000 / 0.976 / 0.999 | 3.00 | 0.62 | 186 |
| 3 | 55 | yes | candy_box, vitamin_jar, coffee_can | carton, bottle, coffee can | 0.975 | 1.000 / 0.977 / 0.947 | 5.25 | 1.59 | 258 |
| 4 | 55 | yes | candy_box, glucosamine_jar, coffee_can | carton, bottle, coffee can | 0.974 | 1.000 / 0.975 / 0.947 | 5.64 | 2.44 | 225 |
| 5 | 55 | yes | ink_cartridge, glucosamine_jar, coffee_can | box, bottle, coffee can | 0.973 | 0.941 / 0.979 / 1.000 | 5.81 | 10.34 | 220 |

- **Window orientation matters most for text prompts.** The camera looks down the belt with
  +X to the image right, so upright parts lie on their sides in the image. Turning the window
  so the far end of the belt is at the top raises the best mAP at every tilt: 0.61 -> 0.82 at
  25 deg, 0.60 -> 1.00 at 40 deg, 0.46 -> 0.97 at 55 deg.
- **Prompt wording helps clearly.** "coffee can" beats "can" and "carton" beats "box". With
  the current wording box / bottle / can, the window turned, the mAP averaged over the six
  triples is 0.30 / 0.46 / 0.54 at 25 / 40 / 55 deg.
- With text prompts the candy box is the easiest box (AP 1.0). The probiotic box and the ink
  cartridge stay at 0.3-0.9.
- A steeper tilt (55 deg) costs position accuracy: 5-6 mm mean instead of 2-3 mm.

## Recommendation

Keep the current configuration: YOLOE-26s with visual prompts, tilt 25 deg, classes
probiotic_box / vitamin_jar / coffee_can, and the window as seen. It reaches mAP 0.997 on the
test seed with 2 mm position error, so neither the tilt nor the classes need to change. The
visual prompts were made from 25 deg renders and were not re-measured at other tilts. If the
text-prompt baseline is to be shown at its best, use tilt 40 deg, the window turned, candy_box
for the box, and the prompts carton / bottle / coffee can. That is a tuning-seed result, not
measured on seed 301.
