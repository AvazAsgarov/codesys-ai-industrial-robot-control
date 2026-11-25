# Running the demo

A 10-minute live demonstration of the cell: CODESYS soft-PLC with the operator HMI, the MuJoCo
digital twin and camera-based picking with YOLOE. Everything runs on this laptop; nothing is
reachable from the network.

## Before the demo (once, about 5 minutes)

```powershell
copy .env.example .env                                                      # test credentials for the local soft-PLC
python tools/uv_run.py --group vision airc vision export --prompts visual   # detector to OpenVINO (~1 min)
python tools/uv_run.py airc plc start                                       # CODESYS Control Win (soft-PLC)
python tools/uv_run.py airc plc deploy                                      # download the PLC application (~3 min)
```

The soft-PLC runs in demo mode for about 2 hours; after that, `airc plc start` again.

## The demo

1. **Start the twin** (with the 3D view):

   ```powershell
   python tools/uv_run.py --group vision airc run --vision yoloe --viewer --duration 900
   ```

2. **Open the operator HMI** in a browser: <http://127.0.0.1:8081/webvisu.htm>
   (native CODESYS visualization, served by the soft-PLC).
3. On the HMI press **Reset** (state goes Stopped → Idle), then **Start** (Starting → Execute;
   the robot homes and goes to its ready pose, the belt starts).
4. Parts arrive on the belt. At photo-eye PE1 the PLC asks the camera; YOLOE answers with the
   class and position; the robot picks the moving part and drops it into its bin. The bin bars
   on the Overview count up; the Robot page shows joint positions, following errors and the last
   vision answer.
5. **Show a fault:** the fault scenario injects an E-stop, a full bin, a lost bridge and an open
   door: `airc run --vision yoloe --scenario config/scenarios/p2_faults.yaml --viewer`. The cell
   aborts (E-stop, door, bridge) or suspends (full bin); the alarm lamps light on the Alarms page.
   Recover from the HMI: **Acknowledge**, **Clear** (Alarms page), **Reset**, **Start**.
6. **Manual mode:** Stop, select **Manual**, Reset, Start; the jog buttons on the Robot page move
   single joints (only in Manual and Execute, `Jog permitted` lamp).

## Recording a video instead

```powershell
python tools/uv_run.py --group vision airc run --vision yoloe --duration 300 --record experiments/demo/demo.mp4
```

Then press Reset and Start on the HMI; the video shows the showcase camera with time, PLC state
and placed parts.

## What to point out (PLC course)

- IEC 61131-3 Structured Text, object-oriented: function blocks with methods and properties,
  interfaces (`I_AlarmSink`), enums, structs; thin programs (`PRG_Main`).
- PackML (ISA-TR88.00.02) state machine with modes Production / Maintenance / Manual.
- CODESYS SoftMotion: a 6-axis kinematic group, conveyor tracking, `MC_` motion blocks.
- Alarm handling after ISA-18.2 (priorities P1-P3, acknowledge, newest alarm in the top bar).
- Watchdogs: bridge heartbeat (500 ms), joint following-error monitor, stale feedback.
- ISA-101 HMI: grey screens, colour only for abnormal states, role-gated commands.
- Tests: 70+ PLC test cases run in the CODESYS simulation (`tests/plc/*.json`) plus end-to-end
  tests on the real soft-PLC.
