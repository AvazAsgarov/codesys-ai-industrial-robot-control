# Phase 3 — Vision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The robot picks parts at the positions a camera-based, zero-shot detector reports (YOLOE-26 with text prompts, YOLO26 as the COCO baseline, both on OpenVINO), on scanned real-world objects, and the detection, pose and calibration metrics are recorded as reproducible results.

**Architecture:** The twin gets an overhead inspection camera at the PE1 photo-eye and textured scanned parts (Google Scanned Objects). When the PLC requests a capture, the runner snapshots the scene and hands it to a **vision worker thread**. The thread owns the MuJoCo offscreen renderer and the OpenVINO detector, so neither ever blocks the 20 ms bridge cycle. The worker renders the frame, detects and segments the parts, and turns the mask of the captured part into (x, y, θ) on the belt through the calibrated camera model. It returns a `VisionMsg` that the runner writes to the PLC as soon as it is ready. The ground-truth oracle stays as a selectable mode (`--vision oracle`) and as the reference for every metric. A seeded benchmark renders labelled frames from the same twin and scores the detectors against exact ground truth.

**Tech Stack:** `mujoco` 4.0.1 (offscreen `Renderer`, segmentation rendering), `ultralytics` 8.4.x (YOLOE-26 / YOLO26, used for prompt setting, export and inference), `openvino` 2026.4, `opencv-python` (calibration), `trimesh` + `fast-simplification` (asset preparation only), Python 3.12, pytest, ruff, pyright strict.

**Spec:** `docs/specs/2026-11-23-system-design.md` (§3.4, §4.1, §4.3 steps 2–4, §6.1–§6.3, §8, §12, §15 P3). ADR 0002, 0005.

## Spike results (2026-11-24, before writing this plan)

| Question | Result |
|---|---|
| Offscreen rendering on this laptop | `mujoco.Renderer(model, 720, 1280)` works on Windows: 0.5 s to create the GL context, **~20 ms per 1280×720 RGB frame**; segmentation rendering gives per-pixel geom ids. The model needs `<visual><global offwidth="1280" offheight="720"/>`. A frame costs a whole bridge cycle, so rendering must not run in the bridge loop. |
| Scanned objects | Gazebo Fuel serves all 1033 Google Scanned Objects (CC BY 4.0) as zips (`fuel.gazebosim.org/1.0/GoogleResearch/models/<name>/1/<name>.zip`, 3–6 MB): OBJ mesh (8–32 k faces, metres) + one PNG texture. MuJoCo loads them with their textures directly. |
| Candidate sizes | Android figure 66×46×81 mm, Ecoforms cup Ø100×72, gaming mouse 123×175×40 (cable included), mugs 137–166 mm wide (too wide for the 160 mm bins), cereal bowl Ø170 (too wide). |
| YOLOE-26 text prompts → OpenVINO | `YOLOE("yoloe-26s-seg.pt").set_classes([...])` then `export(format="openvino")`: the class names are **kept** in the exported model (40 MB). Loaded with `YOLO(path, task="segment")`, it returns boxes and masks. |
| Zero-shot quality (1 top-down frame) | YOLOE-26s, prompts "toy figure / cup / computer mouse": mouse 0.53, cup 0.25, figure 0.12 — all found, but with **low confidence**. YOLO26s-seg (COCO): mouse 0.89; figure → "orange", cup seen from above → "frisbee". A straight top-down view hides what makes objects recognizable. |
| Latency | YOLOE-26s OpenVINO FP32, 640 px, CPU, laptop under load: **~300 ms** per frame. PE1 → PE2 is 750 mm ≈ 7.8 s at 96 mm/s, so latency is not a throughput problem; it is still measured and reported (CPU vs iGPU, FP32 vs FP16). |
| Install | `torch` 2.15 CPU + `ultralytics` 8.4.218 + `openvino` 2026.4.1 install on Windows/Python 3.12 (~1.5 GB). C: has 28 GB free. |

## Decisions taken by the builder (owner may overrule at review)

1. **Parts are chosen by measurement, not by taste.** The candidates are a shortlist of about 8 scanned objects. They must fit the cell: footprint ≤ 120 mm, height 30–90 mm, and a flat or gently curved top that the Ø40 mm cup can grip. They must also be nameable by a prompt, and preferably be COCO classes. The final three are the ones with the best zero-shot mAP@0.5 on a **tuning** seed. The paper reports their numbers on a separate **test** seed. This is the spec's fallback rule (§6.3), applied up front.
2. **The camera looks obliquely, not straight down.** It is tilted 30–40° from the vertical, looking along the belt at PE1. The spike showed that a top-down view hides the features detectors know. The exact tilt is chosen on the tuning seed, with the candidate views {0°, 25°, 40°}. Pose stays exact: the camera model intersects the pixel ray with the plane of the part's top. Its height comes from the class, from the catalogue.
3. **Scanned meshes are committed, decimated.** They are cut to ≤ 5 000 faces with a ≤ 1024 px texture (~0.5–1.5 MB per part), with attribution in `THIRD_PARTY.md`. CC BY 4.0 allows this with attribution, and "decimated" counts as the indicated change. This lets CI and a fresh clone run the twin without a download. Model **weights are not committed**: `airc vision export` downloads and exports them into the git-ignored `models/`.
4. **Ultralytics, torch and OpenVINO are an optional dependency group, `vision`.** `uv sync` gives the twin/bridge/PLC stack. `uv sync --group vision` adds detection. CI installs only the default group and tests the vision code against a fake detector. The real-model tests are marked `vision` and run locally. `opencv-python` becomes a core dependency, because calibration and pose tests run in CI.
5. **Quality defects are Phase 4.** P3 renders only defect-free parts. The defect texturing (spec §6.3) is built where THX-02 consumes it.
6. **Parts with no valid detection are not picked.** The vision message says `xValid := FALSE`. The PLC still routes them to Quarantine by `F_SelectBin`, but the pick height now depends on the class. A part without a class has no known height, so the PLC skips the pick, raises `VisionMissing` (Warning, already defined) and lets the part run off the belt end into a new **reject chute** in the twin. The chute is counted, and reported as "unidentified". Low-confidence parts *do* have a class, so they are still picked into Quarantine.

## Global Constraints

- Conventions of `docs/conventions.md` and spec §11: pyright **strict** on `src/airc`, ruff, Google docstrings, no blocking calls in the asyncio loop. Configuration lives only in `config/*.yaml`.
- **The bridge cycle is never blocked by vision.** Rendering and inference run in one dedicated worker thread, which owns the GL context and the OpenVINO model. The runner only snapshots, submits and polls.
- Units at the PLC boundary are unchanged: belt frame in mm and degrees, and `ST_VisionMsg` keeps its layout. Pick height comes from `GVL_CellGeometry.PART_HEIGHTS[class]`, not from vision.
- Every number in the paper comes from a script with a seed: `airc eval vision` and `airc calibrate` write `experiments/results/*.json`. Tuning and test seeds are disjoint.
- Licences: Ultralytics AGPL-3.0 (the repo is AGPL-3.0 already). Google Scanned Objects CC BY 4.0, with every used object named in `THIRD_PARTY.md` and `assets/objects/<slug>/LICENSE.txt`.
- No large binaries in git. Meshes are ≤ 2 MB per part after decimation. Weights, exported models and rendered datasets are git-ignored.
- Commits use Conventional Commits with no AI attribution. Work goes on branch `phase/3-vision`, as one PR, squash-merged after CI is green. The release is tagged `v0.4.0`.

## Review Focus

1. **Two parts in the frame at capture** (pitch jitter, or a part still in view from the last capture). Expected: the detection whose belt position, rewound by the belt travel since the capture, is closest to PE1 answers this capture. The other part is ignored, never merged. Test: `test_capture_picks_the_part_at_pe1` (Task 5).
2. **No detection, or detector exception / overload.** Expected: `VisionMsg(valid=False)` within the deadline. The runner keeps cycling, and the PLC does not pick the part (decision 6) and counts it as unidentified. A crashed worker restarts itself with a logged error. Tests: `test_no_detection_gives_invalid_message`, `test_worker_survives_detector_error` (Task 5), PLC `unidentified_part_not_picked` (Task 6).
3. **Inference slower than the part's travel to PE2.** Expected: a result that arrives after the part entered the pick window is still written; the PLC's `VisionMissing` timeout decides. Results are never applied to the wrong part id. Test: `test_late_result_keeps_its_part_id` (Task 5).
4. **Rotationally symmetric parts** (cup seen from above). Expected: the θ error uses each class's symmetry order from `config/parts.yaml`, so a 180°-symmetric part is not scored 180° wrong. Test: `test_theta_error_respects_symmetry` (Task 7).
5. **Part near the belt edge or partly out of the frame.** Expected: the camera's field of view covers the belt width plus the largest part at PE1. A mask touching the image border is reported with lower confidence, not with a biased centroid. Tests: `test_frame_covers_belt_at_pe1` (Task 2), `test_border_mask_flagged` (Task 4).

## Fixed values (P3)

| Item | Value |
|---|---|
| Inspection camera | 1280×720, `fovy` from the tuning step (start 45°), above belt X = PE1, looking along +X tilted by the tuned angle; name `cam_inspect` |
| Capture image to detector | full frame letterboxed to 640 px (Ultralytics default) |
| Detectors | `yoloe-26s-seg` with text prompts (primary), `yolo26s-seg` COCO (baseline); FP32 and FP16 OpenVINO; device CPU and GPU (iGPU) measured |
| Confidence threshold | detector 0.10 (keep low, rank by confidence); PLC Quarantine threshold stays `rConfidenceThreshold` 0.6 (recipe) |
| Domain randomisation (seeded) | light direction ±30°, intensity ×[0.6, 1.4], belt colour ±10 % value, Gaussian noise σ 2/255, blur σ ∈ [0, 0.8] px |
| Benchmark size | tuning seed 300: 200 frames; test seed 301: 500 frames; 1–3 parts per frame, uniform over classes |
| Calibration | 9×6 checkerboard, 25 mm squares, 15 poses on the belt; reprojection error, focal error %, camera position error mm, orientation error ° vs MJCF truth |
| Part heights (PLC) | `GVL_CellGeometry.PART_HEIGHTS[0..2]` = `top_height_mm` of the three classes in `config/parts.yaml` (top of the part above the belt, as it rests); a unit test keeps both equal |

---

### Task 1: Scanned part catalogue

**Files:**
- Create: `config/parts.yaml`, `tools/fetch_objects.py`, `assets/objects/<slug>/{model.obj,texture.png,LICENSE.txt,meta.json}` (generated, committed), `tests/unit/twin/test_parts_catalogue.py`
- Modify: `src/airc/twin/config.py` (`PartClass` → mesh-based), `src/airc/twin/scene.py` (mesh assets, materials), `config/twin.yaml` (parts section points to `parts.yaml`), `THIRD_PARTY.md`, `pyproject.toml` (group `assets`: `trimesh`, `fast-simplification`)

**Interfaces:**
- Produces: `config/parts.yaml` with `candidates: [{slug, fuel_name, prompt, coco_name?, symmetry: 1|2|4|0 (0 = round), rest: upright|inverted}]` and `classes: [slug, slug, slug]` (the chosen three; class index = PLC `usiClass`).
- Produces: `PartCatalogue.load() -> PartCatalogue` with `classes: list[PartModel]`. Each `PartModel` has `slug, prompt, coco_name, symmetry, mesh_path, texture_path, size_mm (x, y, z as resting), top_height_mm`.
- Produces: `tools/fetch_objects.py <slug>...`: downloads from Fuel and checks the zip's SHA-256 against `parts.yaml`. It decimates to ≤ 5 000 faces, rescales the texture to ≤ 1024 px, re-centres the mesh (origin at the footprint centre, z = 0 at the resting bottom) and writes `meta.json` (extents, faces, source URL, licence).

- [ ] **Step 1 (RED):** `test_catalogue_parts_fit_the_cell` (footprint ≤ 120 mm, height 30–90 mm, every class has a prompt), `test_mesh_part_rests_on_belt` (spawn each class, step 1 s: z settles within 2 mm of `top_height_mm`, no tunnelling), `test_mesh_part_grippable` (the cup 3 mm above the top welds the part for every class), `test_mesh_files_small` (each ≤ 2 MB). FAIL.
- [ ] **Step 2:** Shortlist of about 8 candidates in `parts.yaml`, run `fetch_objects.py`. The collision geometry is MuJoCo's convex hull of the decimated mesh. The visual geometry is the textured mesh. Inverted cups get `rest: inverted`. PASS. Existing twin tests stay green, with placeholder heights replaced by catalogue heights.
- [ ] **Step 3:** Commit `feat(twin): scanned part catalogue from Google Scanned Objects`.

### Task 2: Inspection camera and renderer

**Files:**
- Create: `src/airc/vision/{__init__,camera,render}.py`, `tests/unit/vision/test_camera.py`, `tests/unit/vision/test_render.py`
- Modify: `src/airc/twin/scene.py` (inspection camera, a `cam_showcase` camera for the demo video (spec §8), offscreen buffer, named lights for randomisation), `config/cell.yaml` (camera block), `.github/workflows/ci.yml` (Ubuntu: `apt-get install libosmesa6`, `MUJOCO_GL=osmesa`)

**Interfaces:**
- Produces: `CameraModel` (frozen dataclass) with `K: 3×3`, `R_wc: 3×3`, `t_wc: 3`, `width`, `height`; `CameraModel.from_mujoco(model, data, name) -> CameraModel`; `project(p_world_m) -> (u, v)`; `ray(u, v) -> (origin, direction)`; `pixel_to_belt(u, v, z_top_mm, geo) -> (x_mm, y_mm)` (belt frame).
- Produces: `FrameRenderer(model, width, height)` with `render(data, randomise: Randomisation | None) -> Frame`. `Frame` carries `rgb: uint8[H,W,3]` and `seg: int32[H,W]` (MuJoCo object id per pixel). It must be used from one thread only.
- Produces: `Randomisation.draw(rng) -> Randomisation` (light, belt tint, noise, blur), applied without changing the physics.

- [ ] **Step 1 (RED):** `test_projection_round_trip` (world point → pixel → ray hits the point within 0.1 mm), `test_pixel_to_belt_matches_ground_truth` (the rendered mask centroid of a part on the belt maps to its true x/y within 2 mm at 0° tilt, for a top point), `test_frame_covers_belt_at_pe1` (both belt edges ±150 mm and a 120 mm part at PE1 lie inside the frame for the configured tilt), `test_render_shapes_and_segmentation` (each spawned part's id appears in `seg`). FAIL.
- [ ] **Step 2:** Implement. Rendering tests are marked `render`. CI runs them on Ubuntu with OSMesa. On Windows CI they skip only if no GL context can be made, with the reason in the skip message. PASS.
- [ ] **Step 3:** Commit `feat(vision): inspection camera model and offscreen renderer`.

### Task 3: Camera calibration (`airc calibrate`)

**Files:**
- Create: `src/airc/vision/calibration.py`, `tests/unit/vision/test_calibration.py`
- Modify: `src/airc/twin/scene.py` (optional checkerboard body, parked off-belt), `src/airc/cli.py`

**Interfaces:**
- Produces: `calibrate(frames: list[Frame], board: Checkerboard) -> Calibration` (OpenCV `findChessboardCorners`, `cornerSubPix`, `calibrateCamera`, then `solvePnP` of a board flat on the belt for the extrinsics). `compare(cal, truth: CameraModel) -> CalibrationReport` (RMS reprojection px, fx/fy error %, principal point px, camera position mm, orientation °).
- Produces: `airc calibrate --poses 15 --seed 7` → `experiments/results/calibration.json` (study) and `config/calibration/cam_inspect.yaml` (the calibrated K, R, t that the vision service uses, spec §4.3 step 3). `CameraModel.load_calibrated(path)`.

- [ ] **Step 1 (RED):** `test_calibration_recovers_intrinsics_from_synthetic_corners` (corners projected with a known K + noise σ 0.2 px → fx within 0.5 %), `test_report_against_truth` (renders 15 board poses: RMS < 0.5 px, position error < 5 mm). FAIL.
- [ ] **Step 2:** Implement. PASS. Run once and commit the result JSON (calibration study, spec §6.1).
- [ ] **Step 3:** Commit `feat(vision): checkerboard calibration compared with ground truth`.

### Task 4: Detectors on OpenVINO and mask pose

**Files:**
- Create: `src/airc/vision/{detector,pose,models}.py`, `assets/models/manifest.yaml`, `tests/unit/vision/test_pose.py`, `tests/unit/vision/test_detector_mapping.py`, `tests/vision/test_openvino_models.py` (marker `vision`)
- Modify: `pyproject.toml` (group `vision`: `ultralytics>=8.4,<9`, `openvino>=2026.4`, `torch` CPU index; marker `vision`; core `opencv-python`), `src/airc/cli.py` (`airc vision export`), `.gitignore` (`models/`)

**Interfaces:**
- Produces: `Detection` (frozen): `label: str, confidence: float, box_xyxy, mask: bool[H,W], touches_border: bool`. `Detector` protocol: `detect(rgb) -> list[Detection]`, `name: str`.
- Produces: `OpenVinoDetector(model_dir: Path, device: "CPU" | "GPU", label_map: dict[str, int]) -> Detector`. It is the only module that imports `ultralytics`, imported lazily. Missing models raise `ModelsMissingError("run: airc vision export")`.
- Produces: `airc vision export [--precision fp32|fp16]`. It builds `models/yoloe-26s-seg-parts_openvino_model` (prompts from `parts.yaml`) and `models/yolo26s-seg_openvino_model`. File names and SHA-256 of the source weights are recorded in `assets/models/manifest.yaml`.
- Produces: `mask_pose(mask) -> MaskPose(u, v, theta_deg, area_px)`: centroid plus principal axis (PCA of the mask pixels), θ in (−90, 90].

- [ ] **Step 1 (RED):** `test_mask_pose_of_rotated_rectangle` (θ within 1°, centroid within 0.5 px), `test_mask_pose_round_is_stable` (a disc gives any θ, flagged `symmetric`), `test_border_mask_flagged`, `test_label_map_prompt_and_coco` (prompt label → class, COCO label → class, unknown → ignored), `test_missing_models_message`. FAIL.
- [ ] **Step 2:** Implement. Local only: `test_openvino_models_keep_prompt_classes`, and `test_detects_each_class_in_a_rendered_frame` (one class at a time at PE1, confidence > 0.1). PASS (CI: the unit tests; local: also `-m vision`).
- [ ] **Step 3:** Commit `feat(vision): YOLOE-26 and YOLO26 on OpenVINO with mask pose`.

### Task 5: Vision service in the loop

**Files:**
- Create: `src/airc/vision/service.py`, `tests/unit/vision/test_service.py`, `tests/integration/test_runner_vision.py`
- Modify: `src/airc/runner.py` (`vision` mode: `oracle | yoloe | yolo26`; snapshot + submit on capture, poll each cycle), `src/airc/cli.py` (`airc run --vision ...`), `src/airc/bridge/oracle.py` (shared "part at PE1" selection), `config/cell.yaml` (vision block: mode, device, deadline)

**Interfaces:**
- Consumes: `CameraModel` (the **calibrated** model from Task 3 by default; `vision.camera_model: calibrated | truth` in `cell.yaml`, so pose error includes calibration error as on a real cell), `FrameRenderer`, `Detector`, `mask_pose`, `PartCatalogue` (heights).
- Produces: `VisionWorker(twin_model, detector, camera, catalogue)`: a thread with `submit(job: CaptureJob) -> None` and `poll() -> list[VisionResult]`. It is non-blocking, and the thread owns the renderer. `CaptureJob` holds `capture: CaptureMsg, qpos/qvel snapshot (np copies), belt_pos_mm at render`. `VisionResult` holds `msg: VisionMsg, latency_ms, detections, crop: uint8[h,w,3]` (the part's box with 10 % margin, the image THX-02 receives in Phase 4; spec §6.2 output record) and `truth: PartTruth | None` (for logging).
- Produces: `select_capture_detection(detections, poses_mm, pe1_x, travel_mm) -> index | None`. It applies the same rule as the oracle: closest to PE1 after rewinding by belt travel, within 150 mm.
- Produces: a per-capture JSONL log `experiments/runs/<run-id>/vision.jsonl`, with the truth vs the reported class and pose for every capture.

- [ ] **Step 1 (RED):** `test_capture_picks_the_part_at_pe1` (two parts in view → the one at PE1), `test_no_detection_gives_invalid_message`, `test_worker_survives_detector_error` (the fake detector raises once → invalid message, the next capture works), `test_late_result_keeps_its_part_id` (a slow fake detector, two captures → results carry their own ids), `test_runner_cycle_not_blocked_by_vision` (fake detector sleeps 300 ms; the bridge max gap stays < 60 ms against the fake PLC). FAIL.
- [ ] **Step 2:** Implement. The physics snapshot is `qpos`/`qvel`/`mocap` copies, re-applied to a worker-owned `MjData` with `mj_forward`. PASS.
- [ ] **Step 3:** Commit `feat(vision): vision worker answers PLC captures without blocking the bridge`.

### Task 6: PLC per-class pick height and unidentified parts

**Files:**
- Modify (PLC): `GVL_CellGeometry` (`PART_HEIGHTS : ARRAY[0..2] OF LREAL`, values from `parts.yaml`; `PART_HEIGHT` removed), `FB_PickSequence` (heights by class), `FB_PartTracker` / scheduling (a record with `NOT xVisionValid` is not scheduled for a pick, and raises `VisionMissing`). Heights are part of the cell's geometry, like the bin poses, not recipe values.
- Modify: `tests/plc/generators/cell.py` (+ `pick.json` if affected), twin: reject chute at the belt end (counts parts), `RunReport.unidentified`
- Test: PLC specs, `tests/unit/twin/test_sensors.py`, `tests/unit/twin/test_parts_catalogue.py::test_plc_part_heights_match_catalogue` (parses `GVL_CellGeometry.st` as the twin already does, so the PLC and `parts.yaml` cannot drift)

**Interfaces:**
- Produces: PLC pick Z = `PART_HEIGHTS[usiClass]` ± the recipe approach/depth; `F_SelectBin` is unchanged.

- [ ] **Step 1 (RED):** PLC `pick_height_follows_class` (inject class 2 with height H → the descent target Z = H − lrPickDepth), `unidentified_part_not_picked` (vision `xValid` FALSE → no pick, `VisionMissing` Warning, the cell stays in Execute). Twin `test_part_off_belt_end_lands_in_reject_chute`. FAIL.
- [ ] **Step 2:** Implement. Compile 0/0. Run all `tests/plc` specs touching the changed FBs (pick, cell, tracking), and the full cell spec. Export sources. PASS.
- [ ] **Step 3:** Commit `feat(plc): pick height per part class; unidentified parts are not picked`.

### Task 7: Zero-shot benchmark, prompt tuning and part selection (`airc eval vision`)

**Files:**
- Create: `src/airc/evaluation/{__init__,dataset,metrics,vision_eval}.py`, `tests/unit/evaluation/test_metrics.py`, `experiments/results/vision_*.json` + `vision_summary.md` (committed)
- Modify: `src/airc/cli.py` (`airc eval vision --detector yoloe|yolo26 --seed N --frames N [--tilt deg] [--prompts file]`), `config/parts.yaml` (final `classes`, tuned prompts, chosen tilt), `config/cell.yaml`

**Interfaces:**
- Produces: `render_dataset(seed, frames, catalogue, tilt) -> Iterator[LabelledFrame]` (ground-truth boxes and masks from the segmentation render; parts placed as the spawner places them, plus 0–2 extra parts in view).
- Produces: `average_precision(dets, truths, iou=0.5) -> float` (all-point interpolation, as COCO/Ultralytics), `per_class_pr(...)`, `pose_errors(...)` (mm and symmetry-aware °), and the latency p50/p95.
- Produces: `vision_<detector>_<seed>.json` with `{detector, device, precision, tilt, prompts, frames, mAP50, per_class: {P, R, AP50}, pose_mm: {mean, p95}, theta_deg: {mean, p95}, latency_ms: {p50, p95}}`.

- [ ] **Step 1 (RED):** `test_ap_perfect_detections_is_one`, `test_ap_hand_computed_case` (3 truths, 4 detections → AP from a worked example in the test), `test_theta_error_respects_symmetry`, `test_dataset_same_seed_same_frames`. FAIL.
- [ ] **Step 2:** Implement. PASS.
- [ ] **Step 3 (tuning, seed 300):** For each candidate, prompt variant (≤ 3 per candidate) and tilt {0, 25, 40}°, run YOLOE-26s. Choose the tilt and the three classes with the best mAP@0.5 that fit decision 1. Write `parts.yaml` `classes` and prompts. Ledger every choice as a ruling, with the numbers.
- [ ] **Step 4 (test, seed 301, 500 frames):** YOLOE-26s and YOLO26s-seg baseline; CPU FP32, CPU FP16, GPU FP16. Results JSON + `vision_summary.md`. **Gate:** YOLOE mAP@0.5 ≥ 0.80. If it is below after tuning, apply the spec's fallback (swap the weakest class for the next candidate and re-run). Fine-tuning stays out of scope unless swapping cannot reach 0.80; that would stop for the owner.
- [ ] **Step 5:** Commit `feat(eval): zero-shot vision benchmark and part selection`.

### Task 8: End-to-end with vision, docs and exit test

**Files:**
- Create: `config/scenarios/p3_vision.yaml` (catalogue mix, pitch 1000 mm, seed 44), `docs/architecture/vision.md`, `docs/adr/0009-vision-pipeline.md` (camera placement, worker thread, assets, catalogue selection), `.claude/skills/mujoco-twin/SKILL.md` (camera/renderer section)
- Modify: `tests/integration/test_e2e_local.py` (`test_e2e_picks_at_vision_positions`), README (vision quick start, results table), CHANGELOG `[0.4.0]`, versions → 0.4.0 (pyproject, `airc.__version__`, `cell.yaml`, PLC `PROJECT_VERSION`), `THIRD_PARTY.md`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1 (RED):** `test_e2e_picks_at_vision_positions`: soft-PLC + twin + YOLOE vision, `p3_vision` for 300 s. Asserts: the cell stays in Execute; **every pick grips** (no `VacuumNoGrip`); `lost == 0`; placed + unidentified + still-on-belt = spawned; the share of parts in their true class bin ≥ measured per-class recall − 5 %. The vision JSONL shows pose error p95 < 10 mm. FAIL before integration fixes.
- [ ] **Step 2:** Fix what the run reveals, each fix with its test first. PASS twice in a row. The Phase 2 e2e tests (oracle mode) still pass.
- [ ] **Step 3:** Docs, ADR 0009, README results table from `experiments/results/`, a short showcase clip (link, not committed if > 5 MB). PR "Phase 3: vision", CI green, squash merge, tag `v0.4.0`.

## Exit criteria (spec §15 P3)

The robot picks parts at the positions vision reports, and the detection metrics are recorded. This is proven by `test_e2e_picks_at_vision_positions` on the owner's laptop and by `experiments/results/vision_*.json`: per-class P/R/AP@0.5, pose error and latency for YOLOE-26 and the YOLO26 baseline on the test seed, plus the calibration study. Unit, vision-mapping, camera and metric tests are green in CI.
