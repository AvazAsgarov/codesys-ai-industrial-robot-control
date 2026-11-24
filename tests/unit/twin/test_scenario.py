"""Seeded scenarios: part supply and fault timeline."""

import pydantic
import pytest

from airc.twin.scenario import FaultTimeline, Scenario, SpawnSchedule

BASE = {"name": "t", "seed": 7, "spawn": {"pitch_mm": 100, "jitter_mm": 30, "y_offset_mm": 40}}


def _parts(seed: int) -> list[tuple[int, float, float]]:
    schedule = SpawnSchedule(Scenario.model_validate({**BASE, "seed": seed}))
    out: list[tuple[int, float, float]] = []
    for pos in range(0, 3000, 20):
        out += [(p.cls, p.y_mm, p.theta_deg) for p in schedule.due(float(pos))]
    return out


def test_same_seed_same_parts() -> None:
    first, again, other = _parts(7), _parts(7), _parts(8)
    assert len(first) >= 25
    assert first == again
    assert first != other


def test_no_parts_while_the_belt_stands() -> None:
    schedule = SpawnSchedule(Scenario.model_validate(BASE))
    schedule.due(500.0)
    assert schedule.due(500.0) == []


def test_faults_fire_once_at_time() -> None:
    scenario = Scenario.model_validate(
        {
            **BASE,
            "faults": [
                {"at_s": 1.0, "kind": "estop", "duration_s": 0.5},
                {"at_s": 2.0, "kind": "block_bin", "duration_s": 1.0, "target": 3},
            ],
        }
    )
    timeline = FaultTimeline(scenario)
    seen: list[tuple[float, str, bool]] = []
    for k in range(200):  # 4 s in 20 ms steps
        t = k * 0.02
        seen += [(round(t, 2), e.fault.kind, e.start) for e in timeline.events(t)]
    assert seen == [
        (1.0, "estop", True),
        (1.5, "estop", False),
        (2.0, "block_bin", True),
        (3.0, "block_bin", False),
    ]


def test_invalid_fault_kind_rejected() -> None:
    with pytest.raises(pydantic.ValidationError):
        Scenario.model_validate({**BASE, "faults": [{"at_s": 1.0, "kind": "meteor"}]})


def test_targeted_fault_needs_a_target() -> None:
    with pytest.raises(pydantic.ValidationError, match="target"):
        Scenario.model_validate({**BASE, "faults": [{"at_s": 1.0, "kind": "block_joint"}]})


def test_spawning_resumes_after_belt_position_reset() -> None:
    # a PLC restart or re-download sets the conveyor position back to 0
    schedule = SpawnSchedule(Scenario.model_validate({**BASE, "spawn": {"pitch_mm": 100}}))
    for pos in range(0, 5001, 20):
        schedule.due(float(pos))
    assert schedule.due(0.0) == []
    spawned = [p for pos in range(20, 201, 20) for p in schedule.due(float(pos))]
    assert len(spawned) >= 1  # within about one pitch, not after 5 m of travel
