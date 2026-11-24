"""Phase 2 stand-in for the vision service: answers capture requests from the twin's ground truth.

The PLC captures a part when it breaks photo-eye PE1 and records the conveyor position at that
moment. The answer must give the part's belt-frame pose *at capture* (the PLC adds the belt travel
since then), so the oracle takes the part whose position, rewound by that travel, is closest to
PE1. No quality decision is sent in Phase 2: the PLC applies its fallback rule (class bin).
"""

from airc.bridge.messages import CaptureMsg, VisionMsg
from airc.twin.twin import PartTruth

MAX_DISTANCE_MM = 150.0  # a part farther from PE1 than this cannot be the captured one
GROUND_TRUTH_CONFIDENCE = 1.0


class GroundTruthOracle:
    """Turns capture requests into vision messages from simulator ground truth."""

    def __init__(self, pe1_x_mm: float) -> None:
        """Create the oracle for photo-eye PE1 at ``pe1_x_mm`` (belt frame)."""
        self._pe1 = pe1_x_mm
        self._seq = 0

    def on_capture(
        self, capture: CaptureMsg, parts: list[PartTruth], belt_pos_mm: float
    ) -> VisionMsg:
        """Answer one capture request.

        Args:
            capture: The PLC's request (part id and conveyor position at the trigger).
            parts: Ground truth of the twin's parts now.
            belt_pos_mm: Conveyor position now.

        Returns:
            The vision message; ``valid`` is False if no part was near PE1 at capture.
        """
        travel = belt_pos_mm - capture.belt_pos_mm
        self._seq += 1
        best: tuple[float, PartTruth, float] | None = None
        for part in parts:
            if not part.on_belt:
                continue
            x_at_capture = part.x_mm - travel
            distance = abs(x_at_capture - self._pe1)
            if distance <= MAX_DISTANCE_MM and (best is None or distance < best[0]):
                best = (distance, part, x_at_capture)
        if best is None:
            return VisionMsg(self._seq, capture.part_id, False, 0, 0.0, 0.0, 0.0, 0.0)
        _, part, x = best
        return VisionMsg(
            seq=self._seq,
            part_id=capture.part_id,
            valid=True,
            cls=part.cls,
            confidence=GROUND_TRUTH_CONFIDENCE,
            x_mm=x,
            y_mm=part.y_mm,
            theta_deg=part.theta_deg,
        )
