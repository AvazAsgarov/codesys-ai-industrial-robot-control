"""MJCF of the cell, generated from the PLC geometry and ``config/twin.yaml``.

World frame = robot base frame of the PLC (Z up), in metres. The arm is a generic 6-axis arm with a
spherical wrist. At all joints zero the upper arm points up (+Z) and the forearm and tool point
forward (+X), as in CODESYS; the joint directions are those measured against CODESYS
(``airc.twin.kinematics.JOINT_AXES``).

Collision groups (contype/conaffinity bits): environment 1, parts 2, suction cup 4. The arm's links
are visual only; parts collide with the environment, each other and the cup.
"""

from dataclasses import dataclass

import numpy as np

from airc.twin.cell import CellGeometry
from airc.twin.config import PartClass, TwinConfig
from airc.twin.kinematics import JOINT_AXES

MM = 0.001
FLOOR_Z = -0.8  # the belt and the bins stand on frames; the floor is 0.8 m below their tops
PART_GROUP = 3


@dataclass(frozen=True)
class PartSlot:
    """A pre-built part body in the model (parked until spawned)."""

    body: str
    weld: str
    cls: int
    park_xyz: tuple[float, float, float]


def part_slots(cfg: TwinConfig) -> list[PartSlot]:
    """All part bodies of the pool, in model order."""
    slots: list[PartSlot] = []
    for cls, part in enumerate(cfg.parts.classes):
        for k in range(cfg.parts.pool_per_class):
            park = (3.0 + 0.15 * k, 3.0 + 0.3 * cls, FLOOR_Z + part.height_mm * MM / 2)
            slots.append(PartSlot(f"part_{cls}_{k}", f"suck_{cls}_{k}", cls, park))
    return slots


def _f(*values: float) -> str:
    return " ".join(f"{v:.6g}" for v in values)


def _robot(geo: CellGeometry, cfg: TwinConfig) -> str:
    a1, d1, a2 = geo.robot_a1 * MM, geo.robot_d1 * MM, geo.robot_a2 * MM
    a3, d3, d4, d6 = geo.robot_a3 * MM, geo.robot_d3 * MM, geo.robot_d4 * MM, geo.robot_d6 * MM
    cup_r = cfg.suction.cup_radius_mm * MM
    s = cfg.servo

    def joint(i: int) -> str:
        axis = " ".join(str(v) for v in JOINT_AXES[i])
        lo, hi = s.range_deg[i]
        return (
            f'<joint name="j{i + 1}" axis="{axis}" range="{_f(lo, hi)}" limited="true" '
            f'damping="{s.friction[i]:g}" armature="{s.armature[i]:g}"/>'
        )

    return f"""
    <body name="base">
      <geom type="cylinder" size="0.15 0.2" pos="0 0 -0.2" class="link"/>
      <body name="link1" gravcomp="1">
        {joint(0)}
        <geom type="capsule" fromto="{_f(0, 0, 0.05, 0, 0, d1)}" size="0.08" class="link"/>
        <geom type="capsule" fromto="{_f(0, 0, d1, a1, 0, d1)}" size="0.07" class="link"/>
        <body name="link2" pos="{_f(a1, 0, d1)}" gravcomp="1">
          {joint(1)}
          <geom type="capsule" fromto="{_f(0, 0, 0, 0, 0, a2)}" size="0.06" class="link"/>
          <body name="link3" pos="{_f(0, 0, a2)}" gravcomp="1">
            {joint(2)}
            <geom type="capsule" fromto="{_f(0, 0, 0, 0, 0, a3)}" size="0.055" class="link"/>
            <body name="link4" pos="{_f(0, d3, a3)}" gravcomp="1">
              {joint(3)}
              <geom type="capsule" fromto="{_f(0, 0, 0, d4, 0, 0)}" size="0.045" class="link"/>
              <body name="link5" pos="{_f(d4, 0, 0)}" gravcomp="1">
                {joint(4)}
                <geom type="sphere" size="0.045" class="link"/>
                <body name="link6" gravcomp="1">
                  {joint(5)}
                  <geom type="capsule" fromto="{_f(0, 0, 0, d6 - 0.012, 0, 0)}" size="0.025"
                        class="link"/>
                  <geom name="cup" type="cylinder" fromto="{_f(d6 - 0.012, 0, 0, d6, 0, 0)}"
                        size="{cup_r:.6g}" contype="4" conaffinity="2" rgba="0.1 0.1 0.1 1"
                        mass="0.05"/>
                  <site name="tcp" pos="{_f(d6, 0, 0)}" size="0.005"/>
                </body>
              </body>
            </body>
          </body>
        </body>
      </body>
    </body>"""


def _belt(geo: CellGeometry, cfg: TwinConfig) -> str:
    length, width, thick = (
        cfg.belt.length_mm * MM,
        cfg.belt.width_mm * MM,
        cfg.belt.thickness_mm * MM,
    )
    cx = geo.belt_origin_x * MM + length / 2
    cy = geo.belt_origin_y * MM
    top = geo.belt_surface_z * MM
    return (
        f'<geom name="belt" type="box" size="{_f(length / 2, width / 2, thick / 2)}" '
        f'pos="{_f(cx, cy, top - thick / 2)}" class="env" rgba="0.2 0.2 0.22 1"/>'
    )


def _cameras(geo: CellGeometry, cfg: TwinConfig) -> str:
    """``cam_inspect`` over photo-eye PE1 (tilted to look down the belt) and ``cam_showcase``."""
    c = cfg.camera
    tilt = np.radians(c.tilt_deg)
    target = np.array([geo.belt_origin_x + geo.pe1_x, geo.belt_origin_y, geo.belt_surface_z]) * MM
    view = np.array([np.sin(tilt), 0.0, -np.cos(tilt)])  # down the belt and down
    pos = target - view * c.distance_mm * MM
    right = np.array([np.cos(tilt), 0.0, np.sin(tilt)])  # image right: belt +X
    up = np.array([0.0, 1.0, 0.0])  # image up: belt +Y
    showcase = target + np.array([0.9, -1.6, 1.1])
    return (
        f'<camera name="cam_inspect" pos="{_f(*pos)}" xyaxes="{_f(*right, *up)}" '
        f'fovy="{c.fovy_deg:g}"/>\n    '
        f'<camera name="cam_showcase" pos="{_f(*showcase)}" mode="targetbody" '
        f'target="link1" fovy="50"/>'
    )


def _bins(geo: CellGeometry, cfg: TwinConfig) -> str:
    w, d, h = (v * MM for v in cfg.bins.size_mm)
    t = cfg.bins.wall_mm * MM
    out: list[str] = []
    for i, (x_mm, y_mm) in enumerate(geo.bin_drop_xy):
        x, y = x_mm * MM, y_mm * MM
        walls = [
            (x, y, -t / 2, w / 2 + t, d / 2 + t, t / 2),  # bottom, top surface at z = 0
            (x - w / 2 - t / 2, y, h / 2, t / 2, d / 2 + t, h / 2),
            (x + w / 2 + t / 2, y, h / 2, t / 2, d / 2 + t, h / 2),
            (x, y - d / 2 - t / 2, h / 2, w / 2, t / 2, h / 2),
            (x, y + d / 2 + t / 2, h / 2, w / 2, t / 2, h / 2),
        ]
        for k, (px, py, pz, sx, sy, sz) in enumerate(walls):
            out.append(
                f'<geom name="bin{i}_{k}" type="box" size="{_f(sx, sy, sz)}" '
                f'pos="{_f(px, py, pz)}" class="env" rgba="0.55 0.55 0.58 1"/>'
            )
    return "\n    ".join(out)


def _part_assets(cfg: TwinConfig) -> str:
    """Meshes, textures and materials of the scanned part classes."""
    out: list[str] = []
    for cls, part in enumerate(cfg.parts.classes):
        if part.shape == "mesh":
            out.append(f'<mesh name="part_mesh_{cls}" file="{part.mesh_file}"/>')
            out.append(f'<texture name="part_tex_{cls}" type="2d" file="{part.texture_file}"/>')
            out.append(f'<material name="part_mat_{cls}" texture="part_tex_{cls}"/>')
    return "\n    ".join(out)


def _part_geom(cls: int, part: PartClass, friction: float) -> str:
    common = (
        f'contype="2" conaffinity="7" group="{PART_GROUP}" friction="{friction:g} 0.005 0.0001"'
    )
    if part.shape == "mesh":  # collides as the convex hull of the scan
        return f'<geom type="mesh" mesh="part_mesh_{cls}" material="part_mat_{cls}" {common}/>'
    common += f' rgba="{_f(*part.rgba)}"'
    if part.shape == "box":
        sx, sy, sz = (v * MM / 2 for v in part.size_mm)
        return f'<geom type="box" size="{_f(sx, sy, sz)}" {common}/>'
    radius, height = part.size_mm[0] * MM / 2, part.size_mm[1] * MM / 2
    return f'<geom type="cylinder" size="{_f(radius, height)}" {common}/>'


def _parts(cfg: TwinConfig) -> tuple[str, str]:
    bodies: list[str] = []
    welds: list[str] = []
    for slot in part_slots(cfg):
        part = cfg.parts.classes[slot.cls]
        bodies.append(
            f'<body name="{slot.body}" pos="{_f(*slot.park_xyz)}"><freejoint/>'
            f"{_part_geom(slot.cls, part, cfg.parts.friction)}"
            f'<inertial pos="0 0 0" mass="{cfg.parts.mass_kg:g}" '
            f'diaginertia="{_f(1e-4, 1e-4, 1e-4)}"/></body>'
        )
        welds.append(f'<weld name="{slot.weld}" body1="link6" body2="{slot.body}" active="false"/>')
    return "\n    ".join(bodies), "\n    ".join(welds)


def build_mjcf(geo: CellGeometry, cfg: TwinConfig) -> str:
    """Return the cell as an MJCF document."""
    s = cfg.servo
    actuators = "\n    ".join(
        f'<position name="a{i + 1}" joint="j{i + 1}" kp="{s.kp[i]:g}" kv="{s.kv[i]:g}" '
        f'forcelimited="true" '
        f'forcerange="{_f(-s.torque_limit[i], s.torque_limit[i])}" '
        f'ctrllimited="false"/>'
        for i in range(6)
    )
    part_bodies, welds = _parts(cfg)
    return f"""<mujoco model="sorting_cell">
  <compiler angle="degree" autolimits="true"/>
  <asset>
    {_part_assets(cfg)}
  </asset>
  <option timestep="{cfg.physics_timestep_s:g}" gravity="0 0 -9.81" integrator="implicitfast"/>
  <visual>
    <global offwidth="1920" offheight="1080"/>
  </visual>
  <default>
    <default class="link">
      <geom contype="0" conaffinity="0" rgba="0.92 0.55 0.1 1" density="2700"/>
    </default>
    <default class="env">
      <geom contype="1" conaffinity="2" friction="0.8 0.005 0.0001"/>
    </default>
  </default>
  <worldbody>
    <light pos="0 0 3" dir="0 0 -1" directional="true"/>
    <geom name="floor" type="plane" size="6 6 0.1" pos="{_f(0, 0, FLOOR_Z)}" class="env"
          rgba="0.75 0.75 0.75 1"/>
    {_belt(geo, cfg)}
    {_cameras(geo, cfg)}
    {_bins(geo, cfg)}
    {_robot(geo, cfg)}
    {part_bodies}
  </worldbody>
  <equality>
    {welds}
  </equality>
  <actuator>
    {actuators}
  </actuator>
</mujoco>
"""
