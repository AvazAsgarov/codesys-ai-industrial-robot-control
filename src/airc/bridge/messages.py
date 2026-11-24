"""Values exchanged with the PLC each bridge cycle (units as in the PLC: mm, degrees)."""

from dataclasses import dataclass, field
from enum import IntEnum

Six = tuple[float, float, float, float, float, float]


class PackMLCommand(IntEnum):
    """``E_PackMLCommand`` of the PLC."""

    NONE = 0
    RESET = 1
    START = 2
    STOP = 3
    HOLD = 4
    UNHOLD = 5
    SUSPEND = 6
    UNSUSPEND = 7
    ABORT = 8
    CLEAR = 9
    COMPLETE = 10


class PackMLState(IntEnum):
    """``E_PackMLState`` of the PLC (ISA-TR88 numbering)."""

    UNDEFINED = 0
    CLEARING = 1
    STOPPED = 2
    STARTING = 3
    IDLE = 4
    SUSPENDED = 5
    EXECUTE = 6
    STOPPING = 7
    ABORTING = 8
    ABORTED = 9
    HOLDING = 10
    HELD = 11
    UNHOLDING = 12
    SUSPENDING = 13
    UNSUSPENDING = 14
    RESETTING = 15
    COMPLETING = 16
    COMPLETE = 17


class Quality(IntEnum):
    """``E_Quality`` of the PLC (spec section 6.3)."""

    UNKNOWN = 0
    OK = 1
    REWORK = 2
    SCRAP = 3


class DecisionSource(IntEnum):
    """``E_DecisionSource`` of the PLC: where a part's quality decision came from."""

    NONE = 0
    AI = 1
    FALLBACK = 2


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
class DecisionMsg:
    """Quality decision (``GVL_Bridge.stDecision``, ``ST_DecisionMsg``): a new one has a new seq.

    The PLC marks every decision message it accepts as ``E_DecisionSource.Ai``; its own
    deadline produces the fallback.
    """

    seq: int
    part_id: int
    quality: Quality
    quality_prob: float
    ident_reliable: bool


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
    # A decision service is configured: the PLC waits for ``stDecision`` up to its deadline.
    # FALSE: the PLC decides each part by its rule as soon as vision has identified it.
    decision_active: bool = False


@dataclass(frozen=True)
class PlcDiagnostics:
    """Alarm and sequence state of the cell (``PRG_Main.fbCell``), read on demand."""

    newest_alarm: int
    error_active: bool
    critical_active: bool
    pick_step: int
    worst_joint: int
    following_error_deg: Six
