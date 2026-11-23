---
name: mujoco-twin
description: Use when building or changing the MuJoCo digital twin of the cell (MJCF robot, conveyor, parts, suction gripper, photo-eyes, bins, cameras), its sensors and actuators, scenario configs, or its synchronisation with the PLC through the OPC UA bridge.
---

# MuJoCo twin (this project)

Design: spec §8, §4.2; ADR 0002.

## Conventions

- SI units everywhere (m, kg, s, rad). Z up. World origin at the robot base.
- MJCF lives in `assets/mjcf/`; names follow `<part>_<role>` (`belt_surface`, `pe1_site`, `cam_overhead`).
- Joint servos are position actuators with explicit `kp`, damping, armature, `forcerange`
  (torque limit) and gear. Never teleport joints.
- Suction gripper: an equality (weld) constraint, active only when vacuum is on and the cup touches a part.
- Photo-eyes: ray or site sensors. Bins: occupancy from contacts. All are booleans to the PLC.
- Belt: kinematic surface velocity taken from the PLC conveyor axis.
- Physics step 2 ms; overhead camera rendered offscreen at about 15 Hz; a showcase camera for the demo video.

## Sync rules

- The PLC is master of setpoints; the twin is master of physical state and measured joint values.
- Exchange every 20 ms through the bridge; never block the physics loop on I/O.
- Scenario YAML (`config/scenarios/`) fixes seed, spawn rate, part mix, defect rate and injected faults.

Extended in phase P2.
