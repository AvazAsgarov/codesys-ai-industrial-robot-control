# Verification and validation (Phase 6)

What was checked on the final build, how, and with what result. Every number comes from a run
on this laptop (Core Ultra 7 255U, 16 GB, no GPU; CODESYS V3.5 SP22 Patch 4) or from CI.

## 1. PLC logic in the CODESYS simulation

78 test cases in 12 files (`tests/plc/*.json`), run with the CODESYS simulation (real compiler,
real SoftMotion libraries), each file in its own simulation session:

| File | Cases | Result |
|---|---|---|
| `types` | 1 | pass |
| `motion_smoke` | 1 | pass |
| `recipes` | 2 | pass |
| `alarms` | 7 | pass |
| `equipment` | 6 | pass |
| `joint_monitor` | 10 | pass |
| `motion` | 8 | pass |
| `packml` | 8 | pass |
| `tracking` | 12 | pass |
| `pick` | 7 | pass |
| `cell` | 9 | pass |
| `hmi` | 7 | pass |
| **Total** | **78** | **78 / 78** |

Full run of the 77 cases on the Phase 5 build (about 28 minutes), then `hmi` (7/7, one new
case) and `cell` (9/9) again after the review fixes to the operator panel.

## 2. Python: unit and integration tests

`pytest` (with ruff, ruff format and pyright) on every pull request, on Ubuntu and Windows
runners. Rendering tests need an OpenGL context, which hosted runners lack: CI sets
`AIRC_SKIP_RENDER=1` and they run locally. The bridge loop is tested against a mock PLC
(`tests/integration/`): cycle timing, reconnect, capture answering, vision and decision workers
that never block the 20 ms cycle, video recorder.

## 3. End to end on the soft-PLC

`pytest -m codesys` drives CODESYS Control Win V3 x64 (the deployed application) with the twin
over OPC UA, starting the cell as an operator would (Clear, Reset, Start):

| Test | Scenario | Result |
|---|---|---|
| `test_e2e_sorts_by_class` | 300 s, ground-truth vision | pass: 30 spawned, 29 placed (11/8/10), 0 wrong, 0 missed, 0 lost; longest gap 34 ms |
| `test_e2e_faults_abort_and_recover` | E-stop, full bin, lost bridge, door open | pass: aborted (E-stop, 6 s), suspended (bin full, 16 s, resumed by itself), aborted (bridge lost, 6 s), aborted (door, 9 s), each recovered; 0 lost, 0 reconnects; the part on the cup at an abort went to Quarantine as designed |
| `test_e2e_picks_at_vision_positions` | 300 s, camera + YOLOE | pass: 30 captured, 30 valid answers, 28 placed (11/8/9), 0 wrong, 0 missed, 0 lost; position error \|dx\|+\|dy\| 2.2 mm mean; vision answer 561 ms mean; longest gap 312 ms |

## 4. Live operation from the HMI

Started with Reset and Start on the native CODESYS visualization (WebVisu):

| Run | Vision | Captured | Sorted | Wrong / missed / lost | Bridge cycle | Longest gap |
|---|---|---|---|---|---|---|
| 20 min | YOLOE | 87 | 78 (30/23/25) | 0 / 0 / 0 | 8.1 ms mean, 13.0 ms p95 | 256 ms |
| 6 min, recorded | YOLOE | 34 | 28 | 0 / 0 / 0 | 6.3 ms mean, 10.1 ms p95 | 199 ms |
| 2.5 min, Phase 4 bridge | YOLOE | 14 | 11 | 0 / 0 / 0 | 8.0 ms mean, 11.2 ms p95 | 200 ms |

Runs end on a timer, so the remaining captured parts were still on the belt or on their way to
a bin. In the 20-minute run bin A reached its capacity of 30 and the cell suspended, as designed.
The PLC's bridge watchdog is 500 ms; no run lost the bridge.

## 5. Vision benchmark

`airc eval vision --seed 301 --frames 500` (951 rendered parts, exact ground truth):
YOLOE visual prompts mAP@0.5 0.997, position error 2.0 mm mean / 3.1 mm p95, box orientation
1.0° p95; text prompts 0.138; YOLO26 COCO 0.058 (`docs/architecture/vision.md`).

## 6. Reviews

Each phase ended with an independent review of the whole branch; findings were fixed test-first
or recorded. Phase 5: no high-severity findings; the mode selector, the vision warm-up and the
test harness's decision flag were fixed.

## Found in this phase

- The end-to-end tests built the twin with the Phase 2 placeholder parts while the PLC picks at
  the scanned products' heights since Phase 3, so every grip failed ("vacuum not reached"). The
  live runs were not affected (`airc run` loads the scenario's parts). Fixed: the tests load the
  scenario's parts like the CLI.
- `airc plc start` keeps the runtime's process id per checkout, so a second checkout (a git
  worktree) started a second CODESYS Control next to the first; the two competed for the OPC UA
  port and a run lost its connection. Fixed: `start` adopts a runtime that is already running.
- Only the speed override was gated by user group (the HMI tool keeps access rights per card,
  not per button), and the demo build has no visualization accounts; the gate was removed and
  ADR 0010 states that the PLC protects the machine.

## Limits

- Simulation only: no real robot, camera or field bus. The vision results hold for rendered
  images; transfer to a real camera is not shown.
- THX-02 was not run live (no API key on this machine); its request format is checked against
  one recorded call.
- The soft-PLC runs under the CODESYS demo licence (stops after about 2 hours).
