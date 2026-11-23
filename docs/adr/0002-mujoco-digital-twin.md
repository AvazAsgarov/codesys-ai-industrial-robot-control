# 2. MuJoCo as the digital twin

- **Status:** Accepted
- **Date:** 2026-11-23

## Context

There is no hardware. The cell must be demonstrable with a moving robot, a conveyor, physical
parts, a suction gripper, sensors and a camera image for the vision pipeline. The laptop has no
NVIDIA GPU (Intel Core Ultra 7 255U, 16 GB RAM).

## Decision

Use MuJoCo (Python bindings) for the digital twin. The scene is described in MJCF (plain XML,
versionable). The robot joints are simulated servo motors (PD control with inertia, damping and
torque limits) that track PLC setpoints and report encoder position, velocity and torque back.
The overhead camera is rendered offscreen.

Rejected: PyBullet (weaker rendering, slowing maintenance), Webots/CoppeliaSim (heavy GUI
simulators, harder to script and version), Isaac Sim (needs an NVIDIA GPU), CODESYS 3D
visualization alone (no physics, no camera images).

## Consequences

- Runs on CPU; physics at 2 ms steps, rendering at about 15 Hz.
- Rendered images are not photoreal, so zero-shot detection accuracy must be measured (ADR 0005).
- The servo loop lives in the twin, as it would in a real drive; the PLC supervises it.
