"""Values exchanged with the PLC each bridge cycle (units as in the PLC: mm, degrees)."""

from dataclasses import dataclass, field

Six = tuple[float, float, float, float, float, float]
ZERO6: Six = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class CaptureMsg:
    """Capture request (``GVL_Bridge.stCapture``): a new request has a new ``seq``."""

    seq: int = 0
    part_id: int = 0
    belt_pos_mm: float = 0.0


@dataclass(frozen=True)
class VisionMsg:
    """Vision result (``GVL_Bridge.stVision``); class index as in ``GVL_Params.aClassToBin``."""

    seq: int
    part_id: int
    valid: bool
    cls: int
    confidence: float
    x_mm: float
    y_mm: float
    theta_deg: float


@dataclass(frozen=True)
class PlcOutputs:
    """What the bridge reads from the PLC every cycle."""

    joint_sp_deg: Six = ZERO6
    setpoint_seq: int = 0
    belt_pos_mm: float = 0.0
    belt_vel_mm_s: float = 0.0
    vacuum_on: bool = False
    capture: CaptureMsg = field(default_factory=CaptureMsg)
    state: int = 0
    mode: int = 0


@dataclass(frozen=True)
class PlcInputs:
    """What the bridge writes to the PLC every cycle (messages are written separately)."""

    heartbeat: bool
    twin_active: bool
    joint_fb_deg: Six
    joint_torque_nm: Six
    feedback_seq: int
    feedback_for_seq: int
    pe1: bool
    pe2: bool
    vacuum_ok: bool
    bin_full: tuple[bool, bool, bool, bool, bool, bool]
    door_closed: bool
    estop_ok: bool
