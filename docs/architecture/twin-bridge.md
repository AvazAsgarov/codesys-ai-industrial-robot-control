# Digital twin and OPC UA bridge (Phase 2)

The PLC application of Phase 1 runs on a real CODESYS runtime and drives a MuJoCo model of the
cell over OPC UA. The PLC stays master of motion; the twin is master of physical objects
(spec §4.2).

```
 CODESYS Control Win V3 x64 (soft-PLC, 4 ms MainTask)          Python: airc run (one process)
 ┌──────────────────────────────┐   OPC UA, 127.0.0.1:4840   ┌──────────────────────────────┐
 │ GVL_Bridge  setpoints, belt, │ ── read every 20 ms ─────► │ Runner (20 ms cycle)          │
 │             vacuum, capture  │                            │  ├ Twin.step: 10 x 2 ms       │
 │             state            │ ◄── write every 20 ms ──── │  │   servo joints, belt carry, │
 │ GVL_Bridge  joint feedback,  │                            │  │   suction, photo-eyes, bins │
 │             sensors, vision  │                            │  ├ SpawnSchedule (by belt mm) │
 │ GVL_Hmi     commands         │ ◄── tests / HMI ────────── │  ├ GroundTruthOracle (vision) │
 └──────────────────────────────┘                            │  └ FaultTimeline              │
                                                             └──────────────────────────────┘
```

## Running it

```powershell
python tools/uv_run.py airc plc start      # soft-PLC as a console process (ADR 0008)
python tools/uv_run.py airc plc deploy     # headless download of plc/RobotCell.project (~3 min)
python tools/uv_run.py airc run --viewer   # twin + bridge, scenario config/scenarios/p2_demo.yaml
```

Start production from the HMI (Phase 5) or over OPC UA (`GVL_Hmi.eCommand`: Reset, then Start);
the end-to-end test does that: `python tools/uv_run.py pytest -m codesys -s`.

## One bridge cycle (20 ms)

1. Read the PLC outputs: joint setpoints and their sample number (`udiSetpointSeq`), conveyor
   position and velocity, vacuum valve, capture request, PackML state. The previous cycle's inputs
   are written in the same round trip.
2. Step the twin ten times 2 ms: each joint is a simulated servo drive (PD with velocity
   feed-forward, torque limit, rotor inertia), the setpoint is interpolated over the cycle. Parts
   lying on the belt move with the PLC's conveyor position, so the twin's parts and the PLC's part
   tracking use the same belt.
3. Spawn the parts due by belt travel (seeded, one every `pitch_mm` of belt movement).
4. Answer a new capture request: Phase 2 has no camera yet, so the ground-truth oracle reports the
   captured part's class and its pose at the moment of capture. No quality decision is sent: the
   PLC's fallback rule sorts by class.
5. Prepare the inputs: measured joint positions and torques with the setpoint sample they answer
   (`udiFeedbackForSeq`), photo-eyes, vacuum switch, bin-full signals, door and E-stop, heartbeat.

## Timing and supervision

| Item | Value |
|---|---|
| Bridge cycle | 20 ms; one OPC UA round trip (read + previous write), about 2–3 ms on loopback |
| Twin step | 10 × 2 ms physics, about 2.5 ms of CPU |
| Joint supervision | `FB_JointMonitor` compares feedback with the setpoint *sample it answers* (128 samples of history), so transport delay is not following error; a blocked joint still faults |
| Watchdogs | heartbeat (`FB_BridgeWatchdog`) and feedback freshness (`tFeedbackTimeout`), 500 ms |
| Windows pacing | asyncio's clock ticks every 15.6 ms on Windows; the runner uses an event loop on `time.perf_counter`, 1 ms system timer resolution and above-normal priority |

## Kinematics

The arm in MuJoCo is built from `GVL_CellGeometry` (the PLC is the single source of geometry). Joint
directions and the orientation convention were measured against CODESYS SoftMotion: J1 about +Z,
J2 and J3 about −Y, J4 about +X, J5 about +Y, J6 about +X; MCS angles A/B/C are Z-Y-Z Euler angles
of the tool frame (Z = approach). Eleven reference poses captured from CODESYS
(`tests/fixtures/fk_reference.json`) match within 0.5 mm and 0.1°.

## Faults

`config/scenarios/p2_faults.yaml` injects an E-stop, a full bin, a lost bridge and an opened door;
a scenario can also drop the gripped part or block a joint. Each fault has a start time and a
duration; recovery (Clear, Reset, Start) is the operator's. `test_e2e_faults_abort_and_recover`
runs this scenario on the soft-PLC and plays the operator through OPC UA.

Resetting forgets the tracked parts: in Stopped the PLC does not supervise the belt (the bridge
watchdog is off and parts may be removed by hand), so production restarts from an empty, known
belt. Parts left on the belt run off its end; the operator clears the belt before Reset.
