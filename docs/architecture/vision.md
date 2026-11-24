# Vision (Phase 3)

The PLC asks for a picture when a part passes photo-eye PE1; the vision service answers with the
part's class and its pose on the belt. The answer goes back over the OPC UA bridge
(`GVL_Bridge.stVision`) and the PLC's part tracker attaches it to the part record. A part without
a valid answer is never picked (`FB_PartTracker.NextPickable`): it runs to the end of the belt
and is counted as missed, and the PLC raises `VisionMissing`.

```
 PLC                                Runner (20 ms bridge cycle)          Vision worker thread
 PE1 edge -> stCapture (part id, ──► snapshot of the twin state  ──────► render cam_inspect
             belt position)          (qpos, mocap; a few hundred floats)   (1280x720, MuJoCo)
                                                                          ROI 640x640 at PE1
 stVision (class, x, y, theta, ◄── written when the answer is ready ◄──── YOLOE-26s-seg (OpenVINO)
           confidence, valid)         (the loop never waits for it)        mask -> centroid, axis
                                                                          pixel -> belt (camera
                                                                          model, part height)
```

## Parts

Three scanned products from Google Scanned Objects (CC BY 4.0, see `THIRD_PARTY.md`), chosen to be
told apart from above: `probiotic_box` (class 0), `vitamin_jar` (1), `coffee_can` (2). Their
meshes and textures are in `assets/objects/`; `config/parts.yaml` lists them, and the PLC's pick
height per class is `GVL_CellGeometry.PART_HEIGHTS`.

## Camera and calibration

`cam_inspect` looks at the belt at PE1 from 750 mm, tilted 25° (1280x720, 45° vertical field of
view). The pixel-to-belt mapping uses a pinhole model whose intrinsics and pose come from a
checkerboard calibration in the twin (`airc calibrate`, OpenCV `calibrateCamera` + `solvePnP`,
15 seeded board poses): 0.06 px RMS reprojection error, focal length within 0.02 %, camera
position within 1.2 mm and 0.09°. The result is `config/calibration/cam_inspect.json`; without it
the service falls back to the exact model from MuJoCo.

## Detector

YOLOE-26s-seg with **visual prompts** (ADR 0009): six seeded reference renders of the three
products give one embedding per class, folded into the network and exported to OpenVINO
(`airc vision export --prompts visual`). Nothing is trained. The detector sees a 640x640 window
around PE1 at native resolution (the part is about 150 px wide there).

From the chosen detection's mask: centroid -> belt x/y at the part's top height; a
minimum-area rectangle of the mask outline on the belt plane -> orientation (the side that is the
part's x axis is chosen from the class size, allowing for the side faces the tilted camera sees);
when two labels overlap (IoU >= 0.7) only the more confident one is kept; the belt travel since
the capture is subtracted, so the pose refers to the capture instant the PLC tracks.

## Benchmark

`airc eval vision --seed 301 --frames 500` renders frames with 1-3 parts near PE1, random
lighting, and scores against the simulator's exact ground truth (parts and masks):

| Detector | mAP@0.5 | Position error mean / p95 | Latency mean (CPU) |
|---|---|---|---|
| YOLOE-26s-seg, visual prompts | 0.997 | 2.0 / 3.1 mm | 166 ms (p50) |
| YOLOE-26s-seg, text prompts | 0.138 | 2.2 / 4.2 mm | 166 ms |
| YOLOE-26s-seg, text prompts, image turned 90° | 0.566 | 2.1 / 2.8 mm | 176 ms |
| YOLO26s-seg, COCO classes | 0.058 | 2.0 mm mean | 176 ms |
| Oracle (true masks) | 1.000 | 1.8 / 3.2 mm | - |

Box orientation error: 1.0° p95 (oracle masks 0.7°). The position error is geometric: even the
true masks give 1.8 mm, because the centre of a tilted view is not the centre of the footprint.
Results: `experiments/results/vision_*_301.json`, summary `vision_summary.md`. Tuning used
another seed (300); seed 301 was run once for the final numbers.

## Running it

```powershell
python tools/uv_run.py --group vision airc vision export --prompts visual   # once (~1 min)
python tools/uv_run.py --group vision airc run --vision yoloe               # soft-PLC running
```

`--vision oracle` answers from the simulator's ground truth instead (Phase 2 behaviour).
