# System Design: `codesys-ai-industrial-robot-control`

| | |
|---|---|
| **Status** | Draft for approval |
| **Date** | 2026-11-23 |
| **Repository** | `github.com/AvazAsgarov/codesys-ai-industrial-robot-control` (public) |
| **Local path** | `C:\dev\codesys-ai-industrial-robot-control` (outside OneDrive) |
| **Language** | Everything in English (code, comments, docs, paper, HMI) |

---

## 1. Intent

University final project for the topic *"Industrial Robot Control System: a PLC controls the movement of a robot arm, with sensors for arm position and the objects it manipulates, and motors that move the arm."*

The owner wants it to be far beyond a minimal answer to that brief. It should look and behave like a real industrial system, be clean enough to publish publicly as a portfolio repo, and be backed by an IEEE-style paper and a live demo. The instructor must find nothing to criticise.

**What the system does, in one sentence:** an AI-driven robotic sorting and quality-inspection work cell. Parts arrive on a moving conveyor, a camera identifies each one, an AI decision model judges its quality, and a 6-axis robot arm controlled by a CODESYS PLC picks it from the moving belt. Good parts are sorted **by type** into one bin per type. Defective parts go to Rework or Scrap, and uncertain ones go to Quarantine (owner decision: sort by type **and** quality).

### 1.1 Success criteria

1. A live end-to-end demo: CODESYS PLC + MuJoCo digital twin + vision + THX-02 + HMI, running on the owner's laptop.
2. The PLC program reads like professional industrial code: object-oriented Structured Text, PackML, alarms, interlocks, recipes.
3. The HMI looks like a modern high-performance (ISA-101) operator interface, not a student mock-up.
4. Measured results (accuracy, throughput, latency) that go into the paper as real numbers.
5. A repository a stranger can clone, understand from the README, and run by following the docs.
6. An IEEE-format LaTeX paper and a presentation deck with a demo video.

### 1.2 Goals

- Real motion control: SoftMotion axis group with 6-axis kinematics, linear and PTP moves, picking from a moving conveyor (conveyor tracking).
- Real AI in the loop: a pretrained YOLO26/YOLOE-26 detector, with no retraining by default, plus the THX-02 decision model.
- Hierarchical control architecture with clear real-time boundaries: hard real-time PLC → near-real-time vision → supervisory AI.
- A digital twin that makes the system demonstrable without hardware.
- Reproducible, tested, documented.

### 1.3 Non-goals

- Real hardware, a real safety PLC or certified functional safety. Safety logic is modelled, not certified.
- Training or fine-tuning a detector. This is a fallback only, see §6.3.
- A separate web dashboard. The HMI is CODESYS Visualization.
- Docker. CODESYS Control Win cannot run in a container, and the laptop has limited disk.
- Running the robot from a vision-language-action model. Closed models such as Helix-02 are not available, and open ones need a GPU.

### 1.4 Anti-goals (failure even if it "works")

- Monolithic `PLC_PRG` spaghetti, magic numbers, or copy-pasted logic.
- A demo that only works with hand-tuned luck. Every number in the paper must come from a reproducible script.
- AI that is decorative. Every AI output must change what the robot physically does, and must have a measured accuracy.
- A safety bug: the robot moving while the E-stop or door interlock is active, or any unhandled fault leaving the arm in motion.
- A repo with binaries-only PLC code that nobody can review on GitHub.

---

## 2. Constraints

| Constraint | Consequence |
|---|---|
| Laptop: Intel Core Ultra 7 255U, Intel iGPU + NPU, **no NVIDIA GPU**, 16 GB RAM | CPU/OpenVINO inference only; THX-02 via hosted API; MuJoCo (CPU) instead of Isaac Sim |
| Disk: C: being freed (≥ 20 GB target) | No Docker Desktop; uv for Python; MiKTeX or TeX Live basic, not the full distribution |
| CODESYS V3.5 SP22 Patch 4 + SoftMotion 4.20, Visualization, OPC UA Server, Scripting; **no licence** | Control Win runs in demo mode and stops after ~2 h, then is restarted; acceptable for development and demo |
| CODESYS Control Win on Windows is not hard real-time | Task cycles of 2–10 ms are fine for simulation; documented as a limitation |
| THX-02 hosted API: free, no key, **60 decisions/min per IP**, images allowed (≤ 4, body < 8 MB) | Max ~1 decision/s; needs a timeout and a fallback path |
| Public repo, Ultralytics is AGPL-3.0 | Repo licence **AGPL-3.0** |
| No Claude co-author lines in commits, PRs or docs | Owner's explicit rule |

---

## 3. Approaches considered

The owner handed the "how" to the builder. These are the main forks and the calls made.

### 3.1 Simulation / digital twin

| Option | Trade-off | Call |
|---|---|---|
| **MuJoCo** (Python) | Fast on CPU, accurate contacts, offscreen camera rendering, MJCF is plain text | **Chosen** |
| PyBullet | Similar, but older, weaker rendering, maintenance has slowed | Rejected |
| Webots / CoppeliaSim | Full GUI simulators, heavier, harder to script and version | Rejected |
| Isaac Sim | Photorealistic, but needs an NVIDIA GPU | Impossible |
| CODESYS 3D visu only | No physics and no camera images, so there's nothing to run vision on | Rejected |

### 3.2 PLC ↔ Python link

| Option | Trade-off | Call |
|---|---|---|
| **OPC UA** (CODESYS server + `asyncua` client) | Industry standard, typed structured tags, subscriptions, looks right in the paper | **Chosen** |
| Modbus TCP | Simple but flat registers, no structs, old-fashioned | Rejected |
| Shared memory / UDP | Fastest but non-standard and fragile | Rejected |

### 3.3 Robot kinematics

| Option | Trade-off | Call |
|---|---|---|
| **SoftMotion SM3_Robotics axis group + built-in 6-DOF articulated kinematics** | Real industrial motion stack: path planning, blending, conveyor tracking, jog, limits | **Chosen** |
| Own inverse kinematics in ST | Instructive but re-implements what SoftMotion does better; risky | Rejected |

The robot arm is a **generic 6-axis arm with a spherical wrist** (like typical industrial robots), modelled by the project in MJCF with link lengths **identical** to the CODESYS kinematics parameters. No vendor robot model or branding is used.

### 3.4 Vision

| Option | Trade-off | Call |
|---|---|---|
| **Pretrained YOLO26 + YOLOE-26 (text-prompted, open vocabulary), zero-shot, OpenVINO** | No training; open-vocabulary prompts cover any part name; accuracy is measured against simulator ground truth | **Chosen** (owner's preference) |
| Fine-tune YOLO26 on synthetic data | Higher accuracy on renders, but costs time and compute | **Fallback only** if zero-shot accuracy is too low (§6.3) |

### 3.5 Decision layer

| Option | Trade-off | Call |
|---|---|---|
| **THX-02 hosted API** (`api.hal-x.ai/v1/decide`) | Fast (~0.1 s model time, ~0.8 s round trip measured), image input, no local RAM/disk cost | **Chosen** (owner approved the external API) |
| THX-02 local (9 GB BF16) | Offline, but heavy on 16 GB RAM next to CODESYS and MuJoCo; seconds per call on CPU | Optional mode, not default |
| Rule-based only | Deterministic but not AI | Kept as the **fallback and baseline** for comparison |

---

## 4. System architecture

### 4.1 Layers and timing

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │ L3  Supervisory AI        THX-02 decision service (hosted API)        │  ~0.2–2 s, async
 ├──────────────────────────────────────────────────────────────────────┤
 │ L2  Perception            Vision service: camera → YOLO26/YOLOE-26     │  ~20–100 ms
 │                           (OpenVINO) → part pose on belt               │
 ├──────────────────────────────────────────────────────────────────────┤
 │ L1  Integration           OPC UA bridge (asyncua), tag map, watchdog  │  20 ms cycle
 ├──────────────────────────────────────────────────────────────────────┤
 │ L0  Control (hard RT)     CODESYS Control Win: PackML, SoftMotion,     │  2 ms motion,
 │                           conveyor tracking, alarms, interlocks        │  10 ms logic
 ├──────────────────────────────────────────────────────────────────────┤
 │ Plant                     MuJoCo digital twin: robot, conveyor,        │  physics 2 ms,
 │                           camera, sensors, gripper, bins               │  render 15 Hz
 └──────────────────────────────────────────────────────────────────────┘
 HMI: CODESYS Visualization (TargetVisu + WebVisu), reads L0 directly.
```

**Rule:** a slower layer never blocks a faster one. The PLC never waits on vision or AI. If a decision arrives late, the PLC applies the fallback policy (§7.3).

### 4.2 Who is master of what

| Quantity | Master | Followers |
|---|---|---|
| Joint positions, TCP pose, conveyor position | **PLC** (SoftMotion virtual drives) | Twin mirrors them kinematically |
| Physical object state (parts on belt, in gripper, in bins) | **Twin** (physics) | PLC learns via simulated sensors |
| Sensor signals (photo-eyes, vacuum OK, bin full, door, E-stop button) | **Twin** (or HMI for operator buttons) | PLC |
| Part identity, class, quality, destination | **Vision + THX-02** → written into the PLC part queue | PLC owns the queue once written |

The robot axes are SoftMotion **virtual drives** (`SM_Drive_Virtual`) that generate the motion setpoints. *(Builder's call, made to answer the brief's "sensors for arm position" and "motors that move the arm" honestly.)* The twin does **not** simply copy them:

- Each joint in MuJoCo is a **simulated servo motor**: a PD position controller with inertia, damping, torque limit and gear ratio. It tracks the PLC setpoint and has real dynamics: lag, overshoot, and stalling when blocked.
- The twin reports **measured joint encoder positions, velocities and motor torque/current** back to the PLC every bridge cycle (`GVL_Bridge.stRobotFeedback`).
- The PLC compares setpoint against measured position in `FB_JointMonitor`: following-error supervision with warning/error thresholds, torque-limit and stall detection, and an encoder plausibility check. This is the PLC's "arm position sensor" layer, and it drives real alarms (§5.4).
- The 20 ms OPC UA link cannot close a 2 ms servo loop, so the servo loop lives in the twin (as it would live in a real servo drive). The PLC does trajectory generation and supervision, as a real robot controller does over a fieldbus drive.

### 4.3 Part lifecycle (sequence)

1. The twin spawns a part upstream (random type, pose and defect state from the scenario config).
2. Part crosses **photo-eye PE1** → the PLC latches the conveyor position, assigns a `PartId` and asks the bridge for an image (`xCaptureRequest`, `udiPartId`, `lrBeltPosAtCapture`).
3. The bridge renders the camera frame. The vision service detects the part and returns class, confidence, bounding box, mask and orientation, and converts pixels to belt coordinates using the calibrated camera model.
4. The bridge writes the vision result into the PLC part queue (`ST_PartRecord`) and sends the crop + metadata to THX-02 **asynchronously**.
5. THX-02 returns quality (`ok`/`rework`/`scrap`) and destination with probabilities. The bridge writes them into the same record, plus a `eDecisionSource` (AI or FALLBACK).
6. The PLC schedules the pick when the part enters the robot's tracking window. `MC_TrackConveyorBelt` (or equivalent) synchronises the TCP to the belt, then the robot approaches, applies vacuum, lifts and places in the bin.
7. The twin confirms placement (bin sensors). The PLC updates counters, OEE and the log. The bridge records ground truth vs. decisions for evaluation.

The camera-to-pick distance and belt speed are chosen so that **THX-02 has at least 3 s** before the pick window opens (recipe parameter).

---

## 5. PLC design (CODESYS)

### 5.1 Devices and tasks

| Item | Setting |
|---|---|
| Device | CODESYS Control Win V3 x64 |
| `MotionTask` | 2 ms, highest priority: SoftMotion bus cycle, axis group, conveyor tracking |
| `MainTask` | 10 ms: PackML, equipment logic, part tracking, alarms |
| `CommTask` | 50 ms: OPC UA tag packing, watchdog, statistics |
| `VisuTask` | 100 ms: visualization |
| OPC UA | Symbol configuration with OPC UA, exposing only `GVL_Bridge` and `GVL_Hmi` structures (read/write rights per variable) |

### 5.2 Program organisation (application folders)

```
Application
├── 00_Config        GVL_Config, GVL_Constants, parameter lists, recipe definitions
├── 01_Types         E_*, ST_*, aliases (E_PackMLState, E_PackMLMode, ST_PartRecord, ST_Pose6D …)
├── 02_Interfaces    I_Equipment, I_Resettable, I_AlarmSource, I_Station …
├── 10_Framework     FB_PackMLStateMachine, FB_AlarmManagerAdapter, FB_EventLogger,
│                    FB_RingBuffer, FB_Statistics (OEE)
├── 20_Equipment     FB_Robot (axis group wrapper), FB_Conveyor, FB_VacuumGripper,
│                    FB_PhotoEye, FB_Bin, FB_SafetyMonitor, FB_CameraTrigger
├── 30_Process       FB_PartTracker (queue), FB_PickScheduler, FB_SortingCell (top-level unit),
│                    FB_RecipeManager
├── 40_Comm          GVL_Bridge, GVL_Hmi, FB_BridgeWatchdog, FB_DecisionIntake
├── 50_Programs      PRG_Main, PRG_Motion, PRG_Comm (thin: instantiate and call)
└── 90_Tests         TEST_* programs/FBs for simulation-based unit tests
```

Every equipment FB implements `I_Equipment` (`Enable`, `Reset`, `Stop`, `Abort`, properties `State`, `HasError`, `ErrorId`). `FB_SortingCell` owns all equipment and maps PackML commands to it.

### 5.3 PackML (ISA-TR88.00.02)

- **States:** all 17 standard states (Stopped, Starting, Idle, Suspending, Suspended, Unsuspending, Execute, Stopping, Aborting, Aborted, Holding, Held, Unholding, Completing, Complete, Resetting, Clearing).
- **Modes:** `Production`, `Maintenance` (slow speed, single cycle, no AI), `Manual` (jog in joint/world coordinates, door open allowed at reduced speed, i.e. modelled T1 behaviour).
- **PackTags (subset):** `Command.CntrlCmd`, `Command.UnitMode`, `Command.MachSpeed`, `Status.StateCurrent`, `Status.UnitModeCurrent`, `Status.CurMachSpeed`, `Admin.ProdProcessedCount`, `Admin.ProdDefectiveCount`, `Admin.Alarm[]`, `Admin.StopReason`.
- Suspended = starved (no parts) or blocked (target bin full). Held = operator hold. Aborted = E-stop or critical fault.

### 5.4 Alarms and interlocks

- CODESYS **AlarmManager** with classes `Critical` (→ Abort), `Error` (→ Stop), `Warning` (no state change), `Info`.
- Initial alarm list (extended during build): joint following error (setpoint vs. twin encoder), motor torque limit / stall, encoder implausible; E-stop pressed; safety door open in Production; axis group error (with SoftMotion error ID); following error / joint limit; vacuum lost during transfer; part missed (left the tracking window); bin full; vision timeout; THX-02 timeout/fallback used (warning); OPC UA bridge heartbeat lost (critical: robot stops); low AI confidence (warning).
- Interlocks: no motion unless group powered AND no critical alarm AND (door closed OR Manual mode at reduced speed); gripper cannot release outside a bin zone except on abort; conveyor stops if robot reports blocked.
- Bridge watchdog: the bridge toggles a heartbeat every cycle; if the PLC sees no change for 500 ms it raises a critical alarm and the cell aborts.

### 5.5 Recipes

CODESYS Recipe Management: belt speed, pick height, approach/retreat offsets, max TCP velocity/acceleration, confidence threshold, THX-02 deadline, class→bin mapping, fallback policy. Two shipped recipes: `Standard` and `HighSpeed`.

### 5.6 Source control of the PLC project

- `plc/RobotCell.project` (binary) is committed for convenience.
- The **source of truth for review** is the text export in `plc/src/` (one file per POU/GVL/DUT, via the CODESYS MCP toolkit `export_sources` / CODESYS scripting). It is regenerated before every commit that touches the PLC.
- `plc/scripts/` holds CODESYS IronPython scripts for export, import and headless build.

---

## 6. Vision design

### 6.1 Camera

- Fixed overhead RGB camera above the belt, upstream of the robot, 1280×720, MuJoCo offscreen renderer.
- Intrinsics and extrinsics are known from the MJCF. A checkerboard calibration routine is still implemented and compared against ground truth. This is a small paper result on calibration error.
- Domain realism: textured scanned objects, randomised lighting, mild noise and blur.

### 6.2 Detection pipeline

1. **Detector:** YOLOE-26 (segmentation variant) with **text prompts** for the part catalogue, plus YOLO26 (COCO) as a comparison. Both are exported to OpenVINO and run on CPU (iGPU tested as an option).
2. **Pose:** the centroid and principal orientation from the segmentation mask (min-area rectangle / PCA) → (x, y, θ) on the belt plane via the camera model.
3. **Output record:** class, confidence, bbox, θ, belt coordinates, crop image, inference time.

### 6.3 Parts and evaluation

- **Part catalogue:** 3 sortable object types (plus optional distractor objects for robustness tests) taken from **Google Scanned Objects** (CC BY 4.0, attributed in `THIRD_PARTY.md`), chosen to be (a) graspable by suction, and (b) nameable by text prompts. Final selection at build time; prefer types that also exist in COCO so YOLO26 can serve as a baseline.
- **Defects:** procedurally applied texture defects (cracks, stains, missing print, colour shift) and geometric defects (scaled or chipped variant) on a configurable share of parts. Ground truth is stored per part.
- **Ground-truth quality labels** *(builder's call, owner may change)*:

  | Defect | Ground-truth disposition | Reason |
  |---|---|---|
  | None | `ok` | |
  | Stain / dirt | `rework` | Cosmetic, cleanable |
  | Missing or smeared print/label | `rework` | Can be relabelled |
  | Colour shift | `rework` | Cosmetic |
  | Crack | `scrap` | Structural |
  | Chipped / broken piece | `scrap` | Structural |
  | Wrong size (scaled variant) | `scrap` | Out of tolerance |

  Defect severity is randomised so that some cases are genuinely ambiguous. That way the AI-vs-rules comparison is not trivial.
- **Metrics:** precision, recall and mAP@0.5 per class against simulator ground truth, plus pose error (mm, degrees) and latency.
- **Fallback rule:** if zero-shot mAP@0.5 < 0.80 on the final part set after prompt tuning, either swap the part set to better-detected objects or fine-tune on auto-labelled synthetic data. Either choice must be reported honestly in the paper.

---

## 7. AI decision layer (THX-02)

### 7.1 Role

THX-02 is a **supervisory decision model**, not a detector and not a controller. It never commands motion. It fills decision fields in the part record that the PLC then acts on within its own safety envelope.

### 7.2 Decisions

| Decision | THX-02 question type | Inputs | Effect |
|---|---|---|---|
| **Quality disposition** | `choice`: ok / rework / scrap | Part crop image + YOLO class & confidence | Selects OK bin, rework bin, or scrap bin |
| **Uncertainty check** | `noul`: "Is the identification reliable?" | Crop + detector output | If "no" with high probability, route to quarantine bin |
| **Alarm triage (advisory)** | `choice` over root-cause categories + `score` severity | Active alarms, recent events, axis and part states (JSON) | Shown on the HMI as an operator recommendation only |

**Bin selection** (in the PLC, `FB_SortingLogic`): quarantine if the uncertainty check fails or detector confidence < threshold → else `scrap` / `rework` per the quality decision → else the **type bin** for the detected class (recipe class→bin mapping). So the detector's class and THX-02's decision both physically change where each part goes.

**One API request per part** carries both part questions (the API accepts several typed questions per request). That keeps the load at 1 req/part, so ≤ 50 parts/min stays within the free-tier limit. Alarm triage is called only on demand (alarm selected on the HMI) and is rate-limited separately. *(Builder's call.)*

Probabilities and the chosen option are logged for every call.

### 7.3 Robustness

- Per-part deadline (recipe, default 2.5 s); timeout → fallback.
- **Fallback policy (rule-based baseline):** class → bin by mapping; low confidence → quarantine. `eDecisionSource = FALLBACK`, warning alarm.
- Rate limiting on the client side (≤ 50 req/min, below the 60/min free-tier limit) with `429`/`Retry-After` handling.
- The client supports `mode: api | local | off`. `local` uses the `thx02[local]` package and is optional.

### 7.4 Evaluation

- Quality decision accuracy, precision/recall on defects, and a confusion matrix vs. ground truth.
- **Ablation:** rule-based only vs. YOLO + THX-02, measured on the same seeded scenario.
- Latency distribution and fallback rate.
- **Reproducibility** *(builder's call)*: every THX-02 request and response is recorded (JSONL with model name, timestamp, latency, payload hash) together with the scenario seed. Paper numbers are computed from these recordings by a script, so they can be recomputed without calling the API. A `replay` mode feeds recorded decisions back into a run. The paper states the API date range and that the hosted model is not version-pinned.
- Evaluation runs are split into batches that fit inside the ~2 h CODESYS demo window and are resumable by seed.

---

## 8. Digital twin (MuJoCo)

- **Scene:** floor, safety fence + door, belt conveyor (kinematic surface velocity from the PLC conveyor axis), 6-axis arm with suction gripper, 4 **6 bins**: one per good part type (3 types, `Type A/B/C` named after the final catalogue) + Rework + Scrap + Quarantine, all inside the arm's reach envelope, photo-eyes PE1 (camera trigger) and PE2 (pick window entry), overhead camera, a second "showcase" camera for demo video.
- **Gripper:** suction modelled as a weld/equality constraint that activates when vacuum is on and a part is in contact under the cup. Vacuum-OK is a sensor back to the PLC.
- **Sensors to PLC:** photo-eyes, vacuum OK, bin occupancy/full, door closed, E-stop button (also operable from the HMI and the twin viewer).
- **Scenario config (YAML):** spawn rate, part mix, defect rate, random seed, belt speed override for tests, fault injection (drop part, block bin, lose bridge, slow AI).
- **Viewer:** MuJoCo native viewer for development; recorded showcase camera for the demo video.

---

## 9. HMI design (CODESYS Visualization)

### 9.1 Design language

- **ISA-101 high-performance HMI:** neutral grey background, colour reserved for abnormal states and alarms, analog values shown with context (ranges, targets), minimal decoration, consistent navigation.
- Alarm colours per ISA-18.2 priority (critical, high, medium, low), never used for anything else.
- One typeface, defined text-size scale and spacing grid; custom SVG symbol set for robot, conveyor, bins, gripper, camera.
- Resolution 1920×1080, also served as WebVisu.
- The `impeccable` and `taste-skill` skills are used to critique mock-ups before they are built.

### 9.2 Screens

| # | Screen | Content |
|---|---|---|
| 1 | **Overview** | Cell mimic (belt, robot, bins, parts in flight), PackML state & mode, start/stop/reset/hold, throughput, OEE, active alarm banner |
| 2 | **Robot** | Joint positions vs. limits, TCP pose, 3D path (`VisuElem3DPath`), speed override, jog panel (Manual mode only), axis errors |
| 3 | **Vision & AI** | Last N parts: class, confidence, quality decision with probabilities, decision source, latency; detection overlay (bounding box drawn on the camera view) |
| 4 | **Alarms** | AlarmManager table with acknowledge, history, filter; THX-02 triage advice for the selected alarm |
| 5 | **Trends** | Cycle time, throughput, AI latency, decision confidence, joint torque proxy |
| 6 | **Recipes** | Recipe select, edit (role-gated), load/save |
| 7 | **Production** | Counters per bin, defect rate, OEE breakdown (availability, performance, quality), shift reset |
| 8 | **System** | Bridge/OPC UA health, task cycle times, user login (Operator / Maintenance / Engineer via VisuUserMgmt), language-ready texts |

Showing the live camera image inside CODESYS Visualization must be verified at build time. Option A: an image element refreshed from a file the bridge writes. Option B: a WebBrowser element (TargetVisu) pointing to an MJPEG endpoint served by the bridge. If neither is reliable, the screen shows the overlay with vector graphics only and the image appears in the twin viewer. **Builder's call after a short spike.**

---

## 10. Repository layout

```
codesys-ai-industrial-robot-control/
├── .claude/
│   └── skills/                     project skills (see §13)
├── .github/
│   ├── workflows/ci.yml            ruff, pyright, pytest, LaTeX build
│   ├── ISSUE_TEMPLATE/
│   └── pull_request_template.md
├── config/
│   ├── cell.yaml                   geometry, camera, timing, endpoints
│   ├── parts.yaml                  part catalogue, prompts, bin mapping
│   ├── scenarios/                  seeded demo & evaluation scenarios
│   └── opcua_tags.yaml             single source for tag names (PLC ↔ Python)
├── docs/
│   ├── architecture/               architecture.md + diagrams/*.drawio (+ exported svg)
│   ├── adr/                        architecture decision records (0001-…)
│   ├── specs/                      this design + later specs
│   ├── plans/                      implementation plans per phase
│   ├── hmi/                        design system, screen specs, mock-ups
│   ├── user-guide/                 install, run, operate, troubleshoot
│   └── conventions.md              naming & style rules (§11)
├── plc/
│   ├── RobotCell.project           CODESYS project (binary)
│   ├── src/                        text export of every POU/DUT/GVL (reviewable)
│   ├── visu/                       exported HMI symbols / images
│   └── scripts/                    CODESYS IronPython: export, import, build
├── src/
│   └── airc/                       Python package ("AI Industrial Robot Control")
│       ├── bridge/                 OPC UA client, tag map, heartbeat, part-record I/O
│       ├── twin/                   MuJoCo scene builder, sensors, gripper, scenarios
│       ├── vision/                 camera, detectors, pose, calibration
│       ├── decision/               THX-02 client, prompts, fallback policy, rate limiter
│       ├── evaluation/             ground-truth logging, metrics, report generation
│       ├── common/                 config, logging, types, timing utils
│       └── cli.py                  `airc run`, `airc eval`, `airc calibrate`, …
├── assets/
│   ├── mjcf/                       robot, conveyor, cell (MJCF xml)
│   ├── objects/                    scanned object meshes & textures (+ licences)
│   └── models/                     model download manifest (weights not committed)
├── tests/
│   ├── unit/                       pure Python tests
│   ├── integration/                twin + bridge + mocked PLC
│   └── plc/                        PLC simulation test scripts (run locally)
├── experiments/
│   ├── runs/                       evaluation outputs (gitignored except summaries)
│   └── results/                    CSV/JSON summaries used by the paper
├── paper/
│   ├── main.tex                    IEEEtran conference format
│   ├── sections/                   one .tex per section
│   ├── figures/
│   └── references.bib
├── presentation/                   slide deck source + exported PDF
├── media/                          README GIF, screenshots, demo video link
├── .editorconfig  .gitattributes  .gitignore  .pre-commit-config.yaml
├── CLAUDE.md                       instructions for AI-assisted work in this repo
├── CHANGELOG.md  LICENSE (AGPL-3.0)  THIRD_PARTY.md  README.md
└── pyproject.toml  uv.lock
```

---

## 11. Conventions

### 11.1 CODESYS / IEC 61131-3

| Element | Rule | Example |
|---|---|---|
| Function block | `FB_` + PascalCase | `FB_VacuumGripper` |
| Function | `F_` | `F_DegToRad` |
| Program | `PRG_` | `PRG_Main` |
| Interface | `I_` | `I_Equipment` |
| Struct | `ST_` | `ST_PartRecord` |
| Enum | `E_` (values PascalCase) | `E_PackMLState.Execute` |
| Union / Alias | `U_` / `T_` | `T_PartId` |
| GVL | `GVL_` | `GVL_Bridge` |
| Method / Property | PascalCase verb / noun | `Reset()`, `IsReady` |
| Variables | CODESYS type prefixes, camelCase after prefix | `xEnable` BOOL, `iCount` INT, `udiPartId` UDINT, `rSpeed` REAL, `lrPos` LREAL, `sName` STRING, `tTimeout` TIME, `eState` enum, `stPart` struct, `fbRobot` FB instance, `itfAxis` interface, `aBins` array, `pData` pointer |
| Constants | `UPPER_SNAKE` in `GVL_Constants` | `MAX_PARTS_IN_QUEUE` |
| Language | Structured Text everywhere; SFC allowed for the pick sequence if it reads better | |
| Rules | No logic in `PRG_*` beyond instantiation and calls; no magic numbers; every FB has a header comment (purpose, inputs, outputs, states); `{attribute 'qualified_only'}` on GVLs and enums | |

### 11.2 Python

- Python 3.12, uv, `src/` layout, package `airc`.
- PEP 8 via **ruff** (lint + format), **pyright** strict on `airc`, type hints everywhere, dataclasses/pydantic for messages.
- Modules `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE`.
- asyncio for bridge and I/O; no blocking calls in the bridge loop.
- Configuration only from `config/*.yaml` (+ environment variables for secrets); no hard-coded IPs or paths.

### 11.3 Git and files

- Branches: `main` (always working), `phase/<n>-<topic>`, `feat/…`, `fix/…`, `docs/…`.
- Commits: Conventional Commits (`feat(plc): add vacuum gripper FB`). **No AI co-author trailers.**
- Each phase merges via a PR with a short description and checklist.
- Files and folders: `kebab-case` for docs and folders, except where a tool requires otherwise (Python modules, CODESYS objects).
- Large binaries (weights, videos) are never committed; they are downloaded by script or linked.

---

## 12. Testing and verification

| Level | What | Where it runs |
|---|---|---|
| Python unit | Tag map, pose math, calibration, rate limiter, fallback policy, THX-02 client (mocked HTTP) | Local + CI |
| Twin | Scene loads, kinematics match PLC parameters (FK comparison), sensors fire correctly | Local + CI (headless MuJoCo) |
| PLC unit | Each equipment FB and the PackML machine tested in CODESYS simulation via scripted force/cycle/read | Local (needs CODESYS) |
| Integration | PLC + bridge + twin, scripted scenario, assertions on counts/alarms | Local |
| Fault injection | E-stop mid-move, door open, vacuum loss, bridge loss, AI timeout, bin full | Local, results logged |
| Evaluation | Seeded scenarios, N ≥ 500 parts per configuration, metrics → `experiments/results/` | Local |

CI (GitHub Actions) covers everything that does not need CODESYS: lint, type check, unit and twin tests, paper build.

**KPIs reported in the paper:** pick success rate, sorting accuracy, throughput (parts/min), mean/95th-percentile cycle time, detection mAP and pose error, THX-02 decision accuracy vs. rule baseline, end-to-end latency, fallback rate, fault recovery times, OEE.

---

## 13. Tooling and project skills

- Installed: superpowers (workflow), pyright-lsp, drawio-skill (diagrams), scientific-writing + citation-management (paper), CODESYS MCP toolkit (edit/compile/simulate/export/HMI).
- **Project skills** written in Phase 0 under `.claude/skills/`:
  - `codesys-st-conventions`: §11.1 rules, FB template, export workflow.
  - `softmotion-robotics`: axis group setup, kinematics parameters, move/tracking FB patterns, error handling.
  - `isa101-hmi`: palette, typography, symbol rules, screen templates.
  - `mujoco-twin`: MJCF conventions, sensor/gripper patterns, sync with the bridge.
  - `ieee-paper`: IEEEtran structure, figure/table style, build command, result-number sourcing rule.

---

## 14. Deliverables

1. Public GitHub repo with README (GIF demo, architecture diagram, quick start), docs, CI badge.
2. CODESYS project + text sources.
3. Python services package.
4. IEEE-format paper (PDF + LaTeX source), ~6–8 pages, with a Related Work section covering VLA models (Helix-02, OpenVLA, π0), world models (V-JEPA 2), decision models (THX-02) and open-vocabulary detection (YOLOE).
5. Presentation deck + 2–3 min demo video.

---

## 15. Phases and exit criteria

| Phase | Scope | Done when |
|---|---|---|
| **P0 Foundation** | Local folder, git, public repo, layout §10, conventions, CLAUDE.md, project skills, uv env, CI, empty CODESYS project compiles, LaTeX toolchain | CI green; empty project compiles; owner reviews the repo skeleton |
| **P1 PLC core** | Types, interfaces, PackML, equipment FBs, SoftMotion axis group with 6-DOF kinematics + conveyor axis, alarms, interlocks, recipes, PLC unit tests | Robot executes a scripted pick-and-place cycle in CODESYS simulation; all PLC tests pass |
| **P2 Digital twin + bridge** | MJCF cell, sensors, gripper, OPC UA bridge, sync, scenarios | Parts flow on the belt and the robot (driven by the PLC) picks with fixed rule-based sorting |
| **P3 Vision** | Camera, YOLO26/YOLOE-26 via OpenVINO, pose, calibration, zero-shot benchmark | Robot picks parts at the positions vision reports; detection metrics recorded |
| **P4 Decision layer** | THX-02 client, quality and routing decisions, fallback, alarm triage | Live decisions drive the bins; ablation numbers recorded |
| **P5 HMI** | Design system, 8 screens, user roles, alarm and trend views | Owner approves the HMI from screenshots and a live run |
| **P6 V&V** | Integration + fault-injection tests, full evaluation runs | All KPIs in `experiments/results/`; no open critical bugs |
| **P7 Deliverables** | README, diagrams, paper, slides, demo video | Paper PDF builds in CI; repo polished; owner signs off |

Every phase follows: plan → build with tests → review → owner check → merge.

**No fixed deadline was set** (owner: not a concern). Priority rule if time ever gets short: keep a working end-to-end slice first (P1 → P4 with minimal HMI), then deepen. Cut in this order: local THX-02 mode → calibration study → alarm triage → Trends/System screens. Never cut: safety logic, tests, measured results.

**Course requirements (from the owner):** the only hard requirement is an IEEE-style paper written in LaTeX. Structured Text is acceptable. The repo may be public from P0.

---

## 16. Left to the builder

- Exact SoftMotion FB names and kinematics parameters; verify with `get_signature` against SM3_Robotics / SM3_Transformation 4.20.
- Link lengths and joint limits of the generic arm, as long as they match the PLC kinematics.
- Final part catalogue and text prompts within the §6.3 criteria.
- Exact OPC UA structure layout, within `config/opcua_tags.yaml` as the single source of truth.
- The live-camera-on-HMI method (§9.2).
- Exact recipe defaults, belt geometry and speeds, within the timing rule in §4.3.

## 17. Open items for the owner

- Paper metadata (authors, university, faculty, course, instructor): needed in P7, not before.

## 18. Decisions log

| Decision | By | Date |
|---|---|---|
| Sort by part type **and** quality (6 bins) | Owner | 2026-11-23 |
| Zero-shot vision, no retraining by default | Owner | 2026-11-23 |
| THX-02 via hosted API | Owner | 2026-11-23 |
| CODESYS Visualization as the HMI; everything in English; public repo | Owner | 2026-11-23 |
| Simulated servo joints with encoder/torque feedback and PLC supervision | Builder | 2026-11-23 |
| One THX-02 request per part; record/replay for reproducible results | Builder | 2026-11-23 |
| Defect → rework/scrap ground-truth mapping (§6.3) | Builder | 2026-11-23 |
| MuJoCo, OPC UA, SoftMotion kinematics, AGPL-3.0, uv (no Docker) | Builder | 2026-11-23 |
