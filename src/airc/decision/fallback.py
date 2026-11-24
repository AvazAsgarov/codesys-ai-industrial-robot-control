"""Rule-based fallback and baseline (spec 7.3).

Without an AI answer the part is treated as quality ok, so the PLC sorts it by class
(``aClassToBin``) and still quarantines it when the detector's confidence is below the recipe
threshold (``F_SelectBin``). The same rule is the "rule-based only" arm of the ablation (7.4).
"""

from airc.bridge.messages import DecisionSource, Quality
from airc.decision.result import Decision


def fallback_decision(part_id: int, *, reason: str, latency_ms: float = 0.0) -> Decision:
    """The rule-baseline decision for a part THX-02 did not answer.

    Args:
        part_id: The PLC's part id.
        reason: Why there is no AI answer (``deadline``, ``rate_limited``, ``mode off``, ...).
        latency_ms: Time spent before falling back.

    Returns:
        Quality ok, no probability, identification not challenged, source ``FALLBACK``.
    """
    return Decision(
        part_id=part_id,
        quality=Quality.OK,
        quality_prob=0.0,
        ident_reliable=True,
        source=DecisionSource.FALLBACK,
        latency_ms=latency_ms,
        reason=reason,
    )
