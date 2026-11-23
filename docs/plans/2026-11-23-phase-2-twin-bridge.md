# Phase 2 — Digital Twin and OPC UA Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parts flow on a MuJoCo conveyor and the robot, driven by the CODESYS soft-PLC over OPC UA, picks them and sorts them into bins by a fixed rule (class → type bin), end to end on one laptop.

**Architecture:** The PLC application from Phase 1 runs on **CODESYS Control Win V3 x64** started as a console process (no admin rights needed) and deployed headlessly by a CODESYS script. A Python process (`airc run`) hosts the twin and the bridge in one asyncio loop: every 20 ms the bridge reads PLC setpoints over OPC UA, the twin steps physics 10 × 2 ms with simulated servo joints, and the bridge writes back joint feedback, sensors and (in P2) ground-truth "vision" messages. The PLC stays master of motion; the twin is master of physical objects (spec §4.2).

**Tech Stack:** CODESYS V3.5 SP22 P4 + Control Win V3 x64 (demo mode, ~2 h per start), CODESYS IronPython scripting, Python 3.12, `mujoco` 4.0.1, `asyncua` 2.1.0, `numpy`, `pydantic`, pytest, ruff, pyright strict.

**Spec:** `docs/specs/2026-11-23-system-design.md` (§3.1, §3.2, §4.1–§4.3, §8, §10, §12, §15 P2). ADR 0002, 0003, 0004.

## Spike results (done before writing this plan, 2026-11-23)

| Question | Result |
|---|---|
| Can the soft-PLC run without admin rights? | Yes: `CODESYSControlService.exe -d` runs as a console app; data and config in `%APPDATA%\CODESYS\CODESYSControlWinV3x64\<id>\`. The Windows service cannot be started without admin. |
| Headless deploy? | Yes, IronPython via `CODESYS.exe --noUI --runscript`: add gateway `Gateway-1` (localhost:1217) → `set_gateway_and_ip_address(gw, "127.0.0.1")` → `set_credentials_for_initial_user` → `login(OnlineChangeOption.Never, True)` → `start()` → `create_boot_application()`. ~3 min per run (CODESYS start-up). |
| OPC UA exposure | `create_symbol_config(False, True, Guid.Empty)` + `{attribute 'symbol' := 'readwrite'}` on `GVL_Bridge`. Nodes: `ns=4;s=|var|CODESYS Control Win V3 x64.Application.GVL_Bridge.<var>`; struct members (`…stCapture.udiSeq`) and array elements (`…aJointPosFb[2]`) are addressable; LREAL arrays read/write as `Double[]`. |
| OPC UA login | The runtime offers **no** identity token by default (no server certificate → no secure endpoint; plaintext endpoint without tokens). With `[CmpUserMgr] SECURITY.UserMgmtAllowAnonymous=YES` the plaintext endpoint offers an Anonymous token and read/write works. |
| Bridge cycle cost | Batched read (5 nodes) + write (2 nodes): mean 1.5 ms, p95 2.0 ms, max 3.3 ms → a 20 ms cycle is comfortable. |
| Packages | `mujoco` 4.0.1 and `asyncua` 2.1.0 install from wheels on Windows / Python 3.12. |

The spike's runtime was stopped afterwards and its config restored, because it listened on the LAN (4840, 11740) with anonymous access.

## Decision for the owner (before Task 1)

**OPC UA security mode.** Option A is my recommendation.

- **A — Anonymous, plaintext, localhost only.** The project's runtime config enables anonymous login and binds OPC UA and the PLC programming port to the loopback adapter only (Task 1 must prove that nothing listens on the LAN; if binding cannot be restricted, fall back to B). Fully scriptable, zero manual steps. Honest in the paper as "lab setup, single host".
- **B — Signed & encrypted with a user.** Matches industrial practice (spec §5.4 spirit). Needs a one-time manual step in the CODESYS IDE (*Device → Security settings*: create the OPC UA server certificate), then the bridge connects with `Basic256Sha256` + the runtime test user from `.env`. Costs ~10 minutes of clicking once per machine, and the client certificate must be trusted on the PLC once.

## Global Constraints

- Conventions of `docs/conventions.md` (ST §1, Python §2): Hungarian ST names, `qualified_only`, thin `PRG_*`; Python `src/airc`, ruff, **pyright strict**, Google docstrings, type hints everywhere, no blocking calls in the asyncio loop.
- Configuration only from `config/*.yaml` (+ `.env` for credentials); **`config/opcua_tags.yaml` is the single source of tag names** (spec §10, §16). No hard-coded IPs/paths in code.
- Units: PLC mm / ° ; Python converts at the bridge boundary to SI (m, rad) for MuJoCo. Robot base frame = MuJoCo world frame.
- Timing (spec §4.1): bridge cycle **20 ms**, physics timestep **2 ms**, PLC MainTask 4 ms. A slow layer never blocks a fast one.
- Kinematics in MJCF **identical** to `GVL_CellGeometry.ROBOT_*` (a1 50, d1 400, a2 450, a3 50, d3 0, d4 450, d6 120 mm); generic arm, no vendor branding (spec §3.3).
- Everything that needs CODESYS runs locally; CI runs ruff, pyright, unit tests, headless twin tests and bridge tests against an in-process asyncua server.
- Commits: Conventional Commits, no AI attribution. Branch `phase/2-twin-bridge`, one PR, squash merge after CI is green.
- Demo licence: the runtime stops after ~2 h; `airc plc start` restarts it.

## Fixed values (P2)

| Item | Value |
|---|---|
| Joint servo (MuJoCo `position` actuator + damping) | kp 2000 Nm/rad (J1–J3), 400 (J4–J6); damping 60 / 10; torque limit 300 / 60 Nm; armature 0.1 / 0.02 |
| Belt | 2100 mm long, 300 mm wide, top at Z 0, infeed at `BELT_ORIGIN` (−1500, −550) |
| Photo-eyes | beam across the belt at belt-frame X 300 (PE1) and 1050 (PE2), 20 mm above the belt |
| Parts (P2 placeholders) | Type A box 60×60×40 mm red, Type B cylinder Ø60×40 mm blue, Type C box 80×40×40 mm green; 0.15 kg; µ 0.8 |
| Suction | weld equality to the touching part when vacuum on and the cup is within 5 mm of the part top; `xVacuumOk` = weld active |
| Bins | 6 open boxes 160×160×120 mm under `BIN_DROP[*]` X/Y, top at Z 120; full at 10 parts (scenario value) |
| Spawning | scenario `config/scenarios/p2_demo.yaml`: seed 42, interval 6 s ± 1 s, mix A/B/C ⅓ each, Y offset ±50 mm, θ ±30° |
| Feedback latency compensation | PLC keeps 128 setpoint samples (512 ms); twin echoes the setpoint sequence number its feedback belongs to |

## Review Focus

1. **Bridge dies or is killed during a move.** Expected: PLC `BridgeLost` (Critical) within `tFeedbackTimeout` → Aborting → Aborted, robot stopped, vacuum kept; restarting the bridge + Clear + Reset resumes. Test `bridge_loss_aborts_cell` (Task 7).
2. **PLC application restarted or re-downloaded while the bridge is connected** (node ids stay, values reset). Expected: the bridge reconnects with backoff and re-sends `xTwinActive`; no crash, no stale-sequence messages applied twice. Test `test_reconnects_after_server_restart` (Task 5).
3. **Two parts close together** (spawn gap smaller than a part). Expected: two PE1 edges → two captures → two records; the twin never merges them. Test `test_close_parts_give_two_pe1_edges` (Task 3).
4. **Belt stopped by the PLC** (Stopped, Suspended, Aborted). Expected: parts on the belt stand still (no drift), spawning pauses, photo-eye states stay valid. Test `test_parts_stop_with_belt` (Task 3).
5. **Joint feedback lags at full speed.** Expected: no `FollowingErrorWarn/Fault` in a normal cycle thanks to sequence-matched comparison; a blocked joint still faults. Tests `lagged_feedback_no_fault`, `blocked_joint_faults` (Task 4) and the integration run (Task 7).

---

### Task 1: Soft-PLC runtime and headless deploy

**Files:**
- Create: `plc/scripts/deploy_runtime.py` (IronPython), `src/airc/plc/runtime.py`, `src/airc/plc/__init__.py`, `config/runtime.yaml`
- Modify: `src/airc/cli.py` (`airc plc start|deploy|stop|status`), `plc/scripts/README.md`, `docs/adr/0008-softplc-runtime-and-opcua-security.md` (new), `.env.example`
- Test: `tests/unit/test_runtime_config.py`

**Interfaces:**
- Produces: `airc plc start` (console runtime, waits for port 11740, returns PID file `.airc/runtime.pid`), `airc plc deploy` (runs `deploy_runtime.py` on a temp copy of `plc/RobotCell.project`; login, start, boot application), `airc plc stop`, `airc plc status` (PID alive, OPC UA endpoint reachable, app state).
- Produces: `apply_runtime_settings(cfg_path: Path, settings: RuntimeSettings) -> bool` — idempotent edit of the user-level `CODESYSControl.cfg`, keeps a `.orig` backup once; returns True when changed.

- [ ] **Step 1 (RED):** `test_apply_runtime_settings_is_idempotent` (adds keys once, second call returns False, unrelated lines untouched, comment lines kept); `test_backup_written_once`. Run `uv run pytest tests/unit/test_runtime_config.py` → FAIL (module missing).
- [ ] **Step 2:** Implement `RuntimeSettings` (pydantic, from `config/runtime.yaml`: executable path, data dir glob, settings per section) and `apply_runtime_settings`. Option A settings: `[CmpUserMgr] SECURITY.UserMgmtAllowAnonymous=YES`, `[CmpOPCUAServer] NetworkAdapter=<loopback>` + `UseLoopback=1`, `[CmpBlkDrvTcp]` loopback-only, `[CmpWebServer] LocalAddress=127.0.0.1`. Pytest → PASS.
- [ ] **Step 3: Prove localhost-only.** `airc plc start`; `Get-NetTCPConnection -State Listen -OwningProcess <pid>` shows **only 127.0.0.1** for 4840 and 11740 (and 8080 if present). If any LAN address remains, ledger a ruling and switch to Option B.
- [ ] **Step 4:** `deploy_runtime.py` from the spike (gateway, address, credentials from `.env`, symbol configuration created once and committed in the project, login/start/boot app); logs to `plc/scripts/deploy_runtime.log` (gitignored). `airc plc deploy` → app state `run`; `airc plc status` reads `GVL_Bridge.eState` over OPC UA = 2 (Stopped).
- [ ] **Step 5:** ADR 0008 (console runtime, headless deploy, security option chosen and why, demo licence). Commit `feat(plc): run and deploy the soft-PLC headlessly`.

### Task 2: Tag map and OPC UA bridge client

**Files:**
- Create: `config/opcua_tags.yaml`, `src/airc/bridge/{__init__,tags,client,messages}.py`
- Modify: PLC `GVL_Bridge` (`{attribute 'symbol' := 'readwrite'}`; new `xTwinActive`, `udiSetpointSeq`, `udiFeedbackForSeq`), `pyproject.toml` (add `asyncua>=2.1,<3`, `numpy>=2`)
- Test: `tests/unit/test_tags.py`, `tests/integration/test_bridge_client.py` (in-process asyncua `Server` that mirrors the tag map)

**Interfaces:**
- Produces: `TagMap.load(path: Path) -> TagMap` with `node_id(name: str) -> str`; names are the GVL variable paths (`GVL_Bridge.aJointPosSp`, `GVL_Bridge.stVision.udiSeq`, …); prefix `ns=4;s=|var|CODESYS Control Win V3 x64.Application.` from the YAML.
- Produces: `PlcOutputs` (dataclass: `joint_sp_deg: tuple[float, ...6]`, `setpoint_seq: int`, `belt_pos_mm`, `belt_vel_mm_s`, `vacuum_on: bool`, `capture: CaptureMsg`, `state: int`, `mode: int`) and `PlcInputs` (heartbeat, twin_active, joint_fb_deg, joint_torque_nm, feedback_seq, feedback_for_seq, pe1, pe2, vacuum_ok, bin_full[6], door_closed, estop_ok, vision: VisionMsg | None).
- Produces: `class BridgeClient` with `async connect() -> None`, `async read_outputs() -> PlcOutputs`, `async write_inputs(inp: PlcInputs) -> None` (one batched `write_values`; struct messages written member by member, `udiSeq` **last**), `async close()`. Reconnect with exponential backoff 0.5 → 8 s.

- [ ] **Step 1 (RED):** `test_tag_map_has_every_gvl_bridge_var` (parses `plc/src/Comm/GVL_Bridge.st`, every variable has a tag); `test_unknown_tag_raises`. FAIL.
- [ ] **Step 2:** YAML + `TagMap`. PASS.
- [ ] **Step 3 (RED):** integration tests against the in-process server: `test_round_trip_outputs_and_inputs`, `test_vision_seq_written_last` (server-side write log order), `test_reconnects_after_server_restart`. FAIL.
- [ ] **Step 4:** `BridgeClient`. PASS. Then against the real runtime (`airc plc deploy` first): `uv run python -m airc.bridge.probe` prints state and a 200-cycle timing, p95 < 5 ms.
- [ ] **Step 5:** PLC side: add the three new `GVL_Bridge` variables; compile 0/0; export. Commit `feat(bridge): OPC UA tag map and client`.

### Task 3: MuJoCo cell scene and sensors

**Files:**
- Create: `src/airc/twin/{__init__,scene,robot,cell,parts,sensors,gripper}.py`, `config/twin.yaml`, `config/scenarios/p2_demo.yaml`
- Test: `tests/unit/twin/test_scene.py`, `test_sensors.py`, `test_gripper.py`

**Interfaces:**
- Produces: `build_scene(cell: CellConfig, twin: TwinConfig) -> mujoco.MjModel` (MJCF generated in Python from the same numbers as `GVL_CellGeometry`; written to `assets/mjcf/cell.generated.xml` for inspection, gitignored); joint names `j1…j6`, sites `tcp`, `pe1`, `pe2`, bodies `bin_<name>`.
- Produces: `class Twin` with `step(sp_rad: np.ndarray, belt_pos_m: float, belt_vel_m_s: float, vacuum_on: bool, dt: float = 0.02) -> TwinState` (10 substeps, setpoint linearly interpolated, parts on the belt carried kinematically by Δ belt position), `spawn(part: PartSpec) -> int`, `state() -> TwinState` (joint pos/torque, pe1/pe2, vacuum_ok, bin counts/full, parts with ground truth).

- [ ] **Step 1 (RED):** `test_scene_loads_and_has_six_joints`, `test_part_on_belt_moves_with_belt_delta` (Δ belt 100 mm → part X +0.100 m ± 1 mm), `test_parts_stop_with_belt`, `test_close_parts_give_two_pe1_edges` (gap 20 mm at 100 mm/s), `test_suction_welds_only_when_close` (cup 3 mm above → weld; 10 mm → none), `test_part_falls_into_bin_and_counts`, `test_bin_full_at_capacity`. FAIL.
- [ ] **Step 2:** Implement. PASS (headless, no rendering). CI runs these on Ubuntu and Windows.
- [ ] **Step 3:** Commit `feat(twin): MuJoCo cell with conveyor, sensors, suction and bins`.

### Task 4: Servo joints, kinematics match and latency-compensated supervision

**Files:**
- Create: `tests/fixtures/fk_reference.json` (generated), `tests/plc/fk_reference.json` (PLC harness spec), PLC `Tests/PRG_TestFk`
- Modify: `src/airc/twin/robot.py`; PLC `FB_JointMonitor` (setpoint history ring of 128 samples keyed by `udiSetpointSeq`; compare feedback with the setpoint of `udiFeedbackForSeq`), `FB_SortingCell` (loopback := NOT latched `xTwinActive`; watchdog enabled when twin active), `tests/plc/joint_monitor.json`
- Test: `tests/unit/twin/test_kinematics.py`, `tests/unit/twin/test_servo.py`

**Interfaces:**
- Consumes: `Twin` (Task 3), PLC kinematics.
- Produces: FK fixture `[{"acs_deg": [6], "mcs": {"x","y","z","a","b","c"}}]` × 12 poses (home, ready, 6 bin drops, 4 random within limits), read from CODESYS simulation via `PRG_TestFk` (`MC_GroupReadActualPosition` in MCS after `MC_MoveDirectAbsolute`).

- [ ] **Step 1 (RED):** PLC: `joint_monitor.json` new cases `lagged_feedback_no_fault` (feedback = setpoint of 10 samples earlier, `udiFeedbackForSeq` matches → no warn) and `blocked_joint_faults` (feedback frozen while setpoints move → fault). FAIL in sim.
- [ ] **Step 2:** PLC changes; compile 0/0; all `tests/plc` specs pass (one file per quiet sim session); export.
- [ ] **Step 3 (RED):** `test_fk_matches_plc` (MuJoCo `tcp` site vs fixture: ≤ 0.5 mm, ≤ 0.1°), `test_servo_tracks_ramp` (ramp 90°/s: steady lag ≤ 2°, no overshoot > 0.5°), `test_blocked_joint_stalls_at_torque_limit`. FAIL.
- [ ] **Step 4:** Robot MJCF joint axes/zero offsets chosen to match the fixture; servo gains from *Fixed values*. PASS. Commit `feat(twin): servo joints matching the PLC kinematics`.

### Task 5: Twin–bridge runner (`airc run`)

**Files:**
- Create: `src/airc/runner.py`, `src/airc/bridge/oracle.py`
- Modify: `src/airc/cli.py` (`airc run --scenario <path> [--duration s] [--viewer]`)
- Test: `tests/integration/test_runner_mock_plc.py`

**Interfaces:**
- Consumes: `BridgeClient`, `Twin`, scenario config.
- Produces: `async run(scenario: Scenario, client: BridgeClient, twin: Twin, stop: asyncio.Event) -> RunReport` — 20 ms cycle paced on the monotonic clock (overruns counted, never skipped silently); heartbeat toggles each cycle; `xTwinActive` TRUE after the first successful write.
- Produces: `GroundTruthOracle.on_capture(capture: CaptureMsg, twin: TwinState) -> VisionMsg` — P2 stand-in for vision: the part nearest PE1 at the capture, its true class and pose in the belt frame; **no decision message** (the PLC applies its fallback rule = class bin, source *Fallback*). `RunReport`: parts spawned/placed per bin, wrong-bin count, missed, overruns, cycle-time stats.

- [ ] **Step 1 (RED):** with the in-process mock server playing a scripted PLC: `test_heartbeat_toggles_every_cycle`, `test_capture_answered_with_ground_truth_once` (same `udiSeq` twice → one vision message), `test_cycle_overrun_counted`. FAIL.
- [ ] **Step 2:** Implement. PASS. `--viewer` opens the MuJoCo passive viewer in a thread (development only).
- [ ] **Step 3:** Commit `feat: twin-bridge runner with ground-truth stand-in for vision`.

### Task 6: Scenario and fault injection

**Files:**
- Create: `src/airc/twin/scenario.py`
- Modify: `config/scenarios/p2_demo.yaml`, add `config/scenarios/p2_faults.yaml`
- Test: `tests/unit/twin/test_scenario.py`

**Interfaces:**
- Produces: `Scenario` (pydantic): `seed`, `spawn: {interval_s, jitter_s, mix, y_offset_mm, theta_deg}`, `bin_capacity`, `faults: list[Fault]` with `Fault = {at_s, kind: "estop" | "door_open" | "drop_part" | "block_bin" | "lose_bridge" | "block_joint", duration_s, target?}`; `Scenario.load(path) -> Scenario`; `SpawnSchedule(scenario).due(t_s) -> list[PartSpec]` deterministic per seed.

- [ ] **Step 1 (RED):** `test_same_seed_same_parts`, `test_faults_fire_once_at_time`, `test_invalid_fault_kind_rejected`. FAIL.
- [ ] **Step 2:** Implement; runner applies faults (E-stop/door → PLC inputs; drop_part → weld off; lose_bridge → stop writing for `duration_s`; block_joint → huge damping on that joint). PASS. Commit `feat(twin): seeded scenarios and fault injection`.

### Task 7: End-to-end runs, docs and exit test

**Files:**
- Create: `tests/integration/test_e2e_local.py` (marked `@pytest.mark.codesys`, skipped in CI), `docs/architecture/twin-bridge.md`, `.claude/skills/mujoco-twin/SKILL.md` (update)
- Modify: `tests/plc/cell.json` (case `bridge_loss_aborts_cell` via harness-simulated heartbeat stop), README status, CHANGELOG `[0.3.0]`, `config/cell.yaml`

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1 (RED):** `test_e2e_sorts_by_class` — `airc plc start` + `deploy`, Reset/Start through OPC UA (`GVL_Hmi` gets the symbol pragma read-only except `eCommand`), `airc run --scenario p2_demo --duration 300`: assert ≥ 40 parts spawned, **placed ≥ 95 %**, **wrong bin = 0**, no Critical/Error alarm, bridge overruns < 1 %. `test_e2e_faults` with `p2_faults.yaml`: E-stop mid-transfer → Aborted with part held → Clear/Reset/Start → part in Quarantine; lose_bridge 1 s → Aborted; recovery works. FAIL before integration fixes.
- [ ] **Step 2:** Fix what the runs reveal (each fix with its unit/PLC test first). PASS twice in a row.
- [ ] **Step 3:** PLC spec `bridge_loss_aborts_cell` passes in sim; full `tests/plc` regression passes.
- [ ] **Step 4:** Docs (architecture, timing diagram, how to run), record a 30 s showcase clip with the viewer for the README (not committed if > 5 MB; link instead). Commit, PR "Phase 2: digital twin and OPC UA bridge", CI green, squash merge, tag `v0.3.0`.

## Exit criteria (spec §15 P2)

Parts flow on the belt; the robot, driven by the PLC over OPC UA, picks them and places them by class (fixed rule) — proven by `test_e2e_sorts_by_class` on the owner's laptop, with unit, twin and bridge tests green in CI.
