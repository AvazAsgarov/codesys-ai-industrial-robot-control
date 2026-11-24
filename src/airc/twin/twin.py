"""The digital twin at run time: servo joints, belt transport, sensors, suction and bins.

One :meth:`Twin.step` is one bridge cycle (20 ms): the joint setpoints are interpolated linearly
over the physics substeps (2 ms), parts lying on the belt are carried by the belt's position change
(so the twin's parts and the PLC's part tracking use the same belt position), then the sensors are
evaluated. Parts come from a pre-built pool per class; spawning moves a parked body onto the belt.
"""

import math
from dataclasses import dataclass

import mujoco
import numpy as np
from numpy.typing import NDArray

from airc.twin.cell import CellGeometry
from airc.twin.config import TwinConfig
from airc.twin.kinematics import TOOL_FROM_FLANGE
from airc.twin.scene import MM, PART_GROUP, PartSlot, build_mjcf, part_slots

FloatArray = NDArray[np.float64]
BELT_JUMP_M = 0.2  # a larger belt position change in one cycle is a PLC restart, not motion
SETTLED_SPEED = 0.05  # m/s: a part slower than this counts as resting
STACK_ALLOWANCE_M = 0.08  # a part resting this far above a bin's rim lies on other parts in it
RESTING_TOL_M = 0.005  # a part this close to the belt surface lies on it
CUP_PENETRATION_M = 0.002  # the cup may press this far into the part top and still grip


@dataclass(frozen=True)
class PartSpec:
    """A part to spawn: class index, pose on the belt (belt frame, mm and degrees)."""

    cls: int
    y_mm: float
    theta_deg: float
    x_mm: float | None = None  # default: just inside the infeed


@dataclass(frozen=True)
class PartTruth:
    """Ground truth of one spawned part (belt frame for x/y, world z)."""

    pid: int
    cls: int
    x_mm: float
    y_mm: float
    z_mm: float
    theta_deg: float
    on_belt: bool
    held: bool
    in_bin: int | None


@dataclass(frozen=True)
class TwinState:
    """Sensor and drive values after a step."""

    joint_pos_rad: FloatArray
    joint_torque_nm: FloatArray
    pe1: bool
    pe2: bool
    vacuum_ok: bool
    bin_counts: tuple[int, ...]
    bin_full: tuple[bool, ...]


@dataclass
class _Active:
    pid: int
    slot: int
    in_bin: int | None = None


def _quat_z(theta_rad: float) -> FloatArray:
    return np.array([math.cos(theta_rad / 2), 0.0, 0.0, math.sin(theta_rad / 2)])


class Twin:
    """MuJoCo model of the cell plus the bookkeeping of parts, suction and bins."""

    def __init__(
        self,
        cfg: TwinConfig | None = None,
        geo: CellGeometry | None = None,
        bin_capacity: int | None = None,
    ) -> None:
        """Build the model.

        Args:
            cfg: Twin configuration (default: ``config/twin.yaml``).
            geo: Cell geometry (default: from the PLC sources).
            bin_capacity: Override of ``cfg.bins.capacity``.
        """
        self.cfg = cfg if cfg is not None else TwinConfig.load()
        self.geo = geo if geo is not None else CellGeometry.from_plc_sources()
        self.model = mujoco.MjModel.from_xml_string(build_mjcf(self.geo, self.cfg))
        self.data = mujoco.MjData(self.model)
        self.capacity = bin_capacity if bin_capacity is not None else self.cfg.bins.capacity
        self._slots: list[PartSlot] = part_slots(self.cfg)
        m = self.model
        self._qadr = [int(m.jnt_qposadr[m.joint(f"j{i + 1}").id]) for i in range(6)]
        self._dadr = [int(m.jnt_dofadr[m.joint(f"j{i + 1}").id]) for i in range(6)]
        self._body = [m.body(s.body).id for s in self._slots]
        self._free_q = [int(m.jnt_qposadr[m.body_jntadr[b]]) for b in self._body]
        self._free_v = [int(m.jnt_dofadr[m.body_jntadr[b]]) for b in self._body]
        self._weld_eq = [m.equality(s.weld).id for s in self._slots]
        self._tool = m.body("link6").id
        self._tcp = m.site("tcp").id
        self._kv_over_kp = np.array(self.cfg.servo.kv) / np.array(self.cfg.servo.kp)
        self._nsub = max(1, round(self.cfg.bridge_period_s / self.cfg.physics_timestep_s))
        self._active: dict[int, _Active] = {}
        self._next_pid = 1
        self._held: int | None = None
        self._grip_blocked = False
        self._last_sp: FloatArray | None = None
        self._last_belt: float | None = None
        self._bin_counts = [0] * len(self.geo.bin_drop_xy)
        self._pe = (False, False)
        mujoco.mj_forward(self.model, self.data)

    # --- geometry helpers ------------------------------------------------------------------------
    @property
    def belt_top_m(self) -> float:
        """Z of the belt surface (m)."""
        return self.geo.belt_surface_z * MM

    def _height(self, slot: int) -> float:
        return self.cfg.parts.classes[self._slots[slot].cls].height_mm * MM

    def _part_pos(self, slot: int) -> FloatArray:
        return self.data.xpos[self._body[slot]].copy()

    def _on_belt(self, a: _Active) -> bool:
        if self._held == a.pid:
            return False
        x, y, z = self._part_pos(a.slot)
        half_w = self.cfg.belt.width_mm * MM / 2
        x0 = self.geo.belt_origin_x * MM
        on_xy = (
            x0 <= x <= x0 + self.cfg.belt.length_mm * MM
            and abs(y - self.geo.belt_origin_y * MM) <= half_w
        )
        resting = abs(z - (self.belt_top_m + self._height(a.slot) / 2)) < RESTING_TOL_M
        return on_xy and resting

    # --- parts ----------------------------------------------------------------------------------
    def _free_slot(self, cls: int) -> int:
        used = {a.slot for a in self._active.values()}
        for i, slot in enumerate(self._slots):
            if slot.cls == cls and i not in used:
                return i
        # pool exhausted: recycle the oldest part that is in a bin or fell off the belt
        for pid in sorted(self._active):
            a = self._active[pid]
            if self._slots[a.slot].cls != cls or pid == self._held:
                continue
            if a.in_bin is not None or self._part_pos(a.slot)[2] < self.belt_top_m - 0.1:
                self._park(a.slot)
                del self._active[pid]
                return a.slot
        msg = f"no free part of class {cls} (pool of {self.cfg.parts.pool_per_class})"
        raise RuntimeError(msg)

    def _park(self, slot: int) -> None:
        self._place(slot, np.array(self._slots[slot].park_xyz), 0.0)

    def _place(self, slot: int, pos: FloatArray, theta_rad: float) -> None:
        q, v = self._free_q[slot], self._free_v[slot]
        self.data.qpos[q : q + 3] = pos
        self.data.qpos[q + 3 : q + 7] = _quat_z(theta_rad)
        self.data.qvel[v : v + 6] = 0.0
        mujoco.mj_forward(self.model, self.data)

    def _add(self, cls: int, pos: FloatArray, theta_deg: float) -> int:
        slot = self._free_slot(cls)
        pid = self._next_pid
        self._next_pid += 1
        self._active[pid] = _Active(pid, slot)
        self._place(slot, pos, math.radians(theta_deg))
        return pid

    def spawn(self, spec: PartSpec) -> int:
        """Put a part on the belt; returns its twin id."""
        part = self.cfg.parts.classes[spec.cls]
        x_mm = spec.x_mm if spec.x_mm is not None else part.length_mm / 2 + 5.0
        pos = np.array(
            [
                (self.geo.belt_origin_x + x_mm) * MM,
                (self.geo.belt_origin_y + spec.y_mm) * MM,
                self.belt_top_m + part.height_mm * MM / 2 + 0.0005,
            ]
        )
        return self._add(spec.cls, pos, spec.theta_deg)

    def drop_into_bin(self, spec: PartSpec, bin_index: int) -> int:
        """Drop a part into a bin from just above it (tests and scenarios)."""
        bx, by = self.geo.bin_drop_xy[bin_index]
        z = self.cfg.bins.size_mm[2] * MM + 0.03
        return self._add(spec.cls, np.array([bx * MM, by * MM, z]), spec.theta_deg)

    def place_part_at(self, pid: int, x_mm: float, y_mm: float, z_mm: float) -> None:
        """Test helper: move a part (upright, at rest) to belt-frame x/y and world z (mm)."""
        a = self._active[pid]
        pos = np.array(
            [
                (self.geo.belt_origin_x + x_mm) * MM,
                (self.geo.belt_origin_y + y_mm) * MM,
                z_mm * MM,
            ]
        )
        self._place(a.slot, pos, 0.0)

    def part(self, pid: int) -> PartTruth:
        """Ground truth of a spawned part."""
        a = self._active[pid]
        pos = self._part_pos(a.slot)
        quat = self.data.xquat[self._body[a.slot]]
        theta = math.degrees(
            math.atan2(
                2 * (quat[0] * quat[3] + quat[1] * quat[2]),
                1 - 2 * (quat[2] ** 2 + quat[3] ** 2),
            )
        )
        return PartTruth(
            pid=pid,
            cls=self._slots[a.slot].cls,
            x_mm=pos[0] / MM - self.geo.belt_origin_x,
            y_mm=pos[1] / MM - self.geo.belt_origin_y,
            z_mm=pos[2] / MM,
            theta_deg=theta,
            on_belt=self._on_belt(a),
            held=self._held == pid,
            in_bin=a.in_bin,
        )

    def parts(self) -> list[PartTruth]:
        """Ground truth of every spawned part."""
        return [self.part(pid) for pid in sorted(self._active)]

    # --- robot ----------------------------------------------------------------------------------
    def joint_positions_rad(self) -> FloatArray:
        """Measured joint positions J1..J6 (rad)."""
        return np.array([self.data.qpos[a] for a in self._qadr])

    def set_joint_positions(self, q_rad: FloatArray) -> None:
        """Teleport the arm to joint positions J1..J6 (rad), at rest, and hold them."""
        for i, adr in enumerate(self._qadr):
            self.data.qpos[adr] = q_rad[i]
            self.data.qvel[self._dadr[i]] = 0.0
        self.data.ctrl[:6] = q_rad
        self._last_sp = np.asarray(q_rad, dtype=np.float64).copy()
        mujoco.mj_forward(self.model, self.data)

    def joint_damping(self, joint: int) -> float:
        """Damping of a joint (index 0..5)."""
        return float(self.model.dof_damping[self._dadr[joint]])

    def set_joint_damping(self, joint: int, damping: float) -> None:
        """Change the damping of a joint (index 0..5); a huge value blocks the joint."""
        self.model.dof_damping[self._dadr[joint]] = damping

    def tool_rotation(self) -> FloatArray:
        """Rotation of the tool frame (Z = approach direction), as the PLC's MCS orientation."""
        flange = self.data.site_xmat[self._tcp].reshape(3, 3)
        return flange @ TOOL_FROM_FLANGE

    def tcp_position_m(self) -> FloatArray:
        """World position of the suction cup tip (m)."""
        return self.data.site_xpos[self._tcp].copy()

    def place_part_under_cup(self, pid: int, gap_mm: float) -> None:
        """Test helper: move a part (upright) so its top is ``gap_mm`` below the cup tip."""
        a = self._active[pid]
        tcp = self.tcp_position_m()
        pos = np.array([tcp[0], tcp[1], tcp[2] - gap_mm * MM - self._height(a.slot) / 2])
        self._place(a.slot, pos, 0.0)

    # --- suction --------------------------------------------------------------------------------
    def _grip_candidate(self) -> int | None:
        tcp = self.tcp_position_m()
        for pid, a in self._active.items():
            part = self.cfg.parts.classes[self._slots[a.slot].cls]
            pos = self._part_pos(a.slot)
            gap = tcp[2] - (pos[2] + self._height(a.slot) / 2)
            reach = min(part.size_mm[:2] if part.shape == "box" else part.size_mm[:1]) * MM / 2
            if (
                -CUP_PENETRATION_M <= gap <= self.cfg.suction.max_gap_mm * MM
                and np.hypot(tcp[0] - pos[0], tcp[1] - pos[1]) <= reach
            ):
                return pid
        return None

    def _weld(self, pid: int) -> None:
        a = self._active[pid]
        eq = self._weld_eq[a.slot]
        p1, p2 = self.data.xpos[self._tool], self.data.xpos[self._body[a.slot]]
        r1 = self.data.xmat[self._tool].reshape(3, 3)
        q1_inv = np.zeros(4)
        mujoco.mju_negQuat(q1_inv, self.data.xquat[self._tool])
        rel_q = np.zeros(4)
        mujoco.mju_mulQuat(rel_q, q1_inv, self.data.xquat[self._body[a.slot]])
        self.model.eq_data[eq, 0:3] = 0.0
        self.model.eq_data[eq, 3:6] = r1.T @ (p2 - p1)
        self.model.eq_data[eq, 6:10] = rel_q
        self.model.eq_data[eq, 10] = 1.0
        self.data.eq_active[eq] = 1
        self._held = pid

    def _release(self) -> None:
        if self._held is not None and self._held in self._active:
            self.data.eq_active[self._weld_eq[self._active[self._held].slot]] = 0
        self._held = None

    def drop_part(self, block_grip: bool = True) -> None:
        """Fault: the gripped part falls; while ``block_grip`` the cup cannot grip again."""
        self._release()
        self._grip_blocked = block_grip

    def allow_grip(self) -> None:
        """End of a drop fault: the cup can grip again."""
        self._grip_blocked = False

    def _update_suction(self, vacuum_on: bool) -> None:
        if not vacuum_on:
            self._release()
        elif self._held is None and not self._grip_blocked:
            pid = self._grip_candidate()
            if pid is not None:
                self._weld(pid)

    # --- sensors --------------------------------------------------------------------------------
    def _beam(self, belt_x_mm: float) -> bool:
        half_w = self.cfg.belt.width_mm * MM / 2
        start = np.array(
            [
                (self.geo.belt_origin_x + belt_x_mm) * MM,
                self.geo.belt_origin_y * MM - half_w - 0.02,
                self.belt_top_m + self.cfg.photo_eye_height_mm * MM,
            ]
        )
        groups = np.zeros(6, dtype=np.uint8)
        groups[PART_GROUP] = 1
        geom = np.zeros(1, dtype=np.int32)
        dist = mujoco.mj_ray(
            self.model, self.data, start, np.array([0.0, 1.0, 0.0]), groups, 1, -1, geom
        )
        return 0.0 <= dist <= 2 * half_w + 0.04

    def _update_bins(self) -> None:
        w, d, h = (v * MM for v in self.cfg.bins.size_mm)
        for a in self._active.values():
            if a.in_bin is not None or a.pid == self._held:
                continue
            x, y, z = self._part_pos(a.slot)
            v = self.data.qvel[self._free_v[a.slot] : self._free_v[a.slot] + 3]
            if float(np.linalg.norm(v)) > SETTLED_SPEED or z > h + STACK_ALLOWANCE_M:
                continue
            for i, (bx, by) in enumerate(self.geo.bin_drop_xy):
                if abs(x - bx * MM) <= w / 2 and abs(y - by * MM) <= d / 2:
                    a.in_bin = i
                    self._bin_counts[i] += 1
                    break

    def empty_bin(self, index: int) -> None:
        """Operator empties a bin: its count restarts at zero."""
        self._bin_counts[index] = 0

    # --- stepping -------------------------------------------------------------------------------
    def step(
        self,
        sp_rad: FloatArray,
        belt_pos_m: float,
        belt_vel_m_s: float,
        vacuum_on: bool,
    ) -> TwinState:
        """Advance one bridge cycle.

        Args:
            sp_rad: Joint setpoints J1..J6 (rad) for the end of the cycle.
            belt_pos_m: Conveyor axis position (m).
            belt_vel_m_s: Conveyor velocity (m/s).
            vacuum_on: Vacuum valve command.

        Returns:
            The state after the cycle.
        """
        target = np.asarray(sp_rad, dtype=np.float64)
        start = self._last_sp if self._last_sp is not None else target
        delta = 0.0 if self._last_belt is None else belt_pos_m - self._last_belt
        if abs(delta) > BELT_JUMP_M:
            delta = 0.0
        self._last_sp, self._last_belt = target, belt_pos_m
        carried = [a.slot for a in self._active.values() if self._on_belt(a)]
        self._update_suction(vacuum_on)
        # velocity feed-forward: the actuator force is kp (q* - q) + kv (dq* - dq)
        feed_forward = self._kv_over_kp * (target - start) / self.cfg.bridge_period_s
        for k in range(1, self._nsub + 1):
            self.data.ctrl[:6] = start + (target - start) * (k / self._nsub) + feed_forward
            for slot in carried:
                # carried by position only: the belt's own motion is the PLC's axis position
                q, v = self._free_q[slot], self._free_v[slot]
                self.data.qpos[q] += delta / self._nsub
                self.data.qvel[v] = 0.0
            mujoco.mj_step(self.model, self.data)
        # mj_step leaves positions of the pre-integration state: recompute them for the sensors
        mujoco.mj_forward(self.model, self.data)
        self._update_bins()
        return self.state()

    def state(self) -> TwinState:
        """Current sensor and drive values."""
        return TwinState(
            joint_pos_rad=self.joint_positions_rad(),
            joint_torque_nm=self.data.actuator_force[:6].copy(),
            pe1=self._beam(self.geo.pe1_x),
            pe2=self._beam(self.geo.pe2_x),
            vacuum_ok=self._held is not None,
            bin_counts=tuple(self._bin_counts),
            bin_full=tuple(c >= self.capacity for c in self._bin_counts),
        )
