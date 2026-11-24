"""Rule baseline (spec 7.3) and the decision result's PLC message."""

from airc.bridge.messages import DecisionMsg, DecisionSource, Quality
from airc.decision.fallback import fallback_decision
from airc.decision.result import Decision


def test_fallback_is_quality_ok_with_source_fallback():
    d = fallback_decision(17, reason="deadline", latency_ms=2500.0)
    assert d.part_id == 17
    assert d.quality is Quality.OK
    assert d.source is DecisionSource.FALLBACK
    assert d.quality_prob == 0.0  # no AI probability behind it
    assert d.ident_reliable is True  # the PLC's confidence threshold still quarantines
    assert d.reason == "deadline"
    assert d.latency_ms == 2500.0


def test_decision_to_msg_matches_st_decision_msg():
    d = Decision(
        part_id=5,
        quality=Quality.SCRAP,
        quality_prob=0.83,
        ident_reliable=False,
        source=DecisionSource.AI,
        latency_ms=640.0,
    )
    msg = d.to_msg(seq=12)
    assert msg == DecisionMsg(
        seq=12, part_id=5, quality=Quality.SCRAP, quality_prob=0.83, ident_reliable=False
    )
    assert int(msg.quality) == 3  # E_Quality.Scrap
