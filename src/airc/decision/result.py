"""The decision service's answer about one part."""

from dataclasses import dataclass

from airc.bridge.messages import DecisionMsg, DecisionSource, Quality


@dataclass(frozen=True)
class Decision:
    """Quality decision for one part, as the PLC needs it plus its provenance.

    ``source`` mirrors ``E_DecisionSource``. ``ST_DecisionMsg`` has no source field: the PLC
    marks every decision message it accepts as ``Ai`` and produces ``Fallback`` itself when its
    deadline passes. A caller that wants the PLC to see the fallback as such should therefore
    not write a ``FALLBACK`` decision; writing it gives the same bin (quality ok, class bin).
    """

    part_id: int
    quality: Quality
    quality_prob: float
    ident_reliable: bool
    source: DecisionSource
    latency_ms: float
    reason: str | None = None  # why the fallback was used
    model: str | None = None

    def to_msg(self, seq: int) -> DecisionMsg:
        """The ``ST_DecisionMsg`` for this decision with sequence number ``seq``."""
        return DecisionMsg(
            seq=seq,
            part_id=self.part_id,
            quality=self.quality,
            quality_prob=self.quality_prob,
            ident_reliable=self.ident_reliable,
        )
