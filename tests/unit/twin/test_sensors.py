"""Photo-eyes and bins of the twin."""

from itertools import pairwise

import numpy as np

from airc.twin.twin import PartSpec, Twin

HOME_RAD = np.radians([0.0, -30.0, 60.0, 0.0, 60.0, 0.0])


def _run(twin: Twin, belt_mm: float, steps: int, v_mm_s: float = 100.0) -> list[bool]:
    edges: list[bool] = []
    pos = belt_mm
    for _ in range(steps):
        pos += v_mm_s * 0.02
        edges.append(twin.step(HOME_RAD, pos / 1000.0, v_mm_s / 1000.0, False).pe1)
    return edges


def _rising_edges(signal: list[bool]) -> int:
    return sum(1 for a, b in pairwise(signal) if b and not a)


def test_pe1_sees_a_passing_part() -> None:
    twin = Twin()
    twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=200.0))
    signal = _run(twin, 0.0, 100)  # 200 mm of travel past PE1 at 300 mm
    assert _rising_edges(signal) == 1
    assert not signal[-1]


def test_close_parts_give_two_pe1_edges() -> None:
    twin = Twin()
    # Type A boxes are 60 mm long: 80 mm pitch leaves a 20 mm gap
    twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=200.0))
    twin.spawn(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0, x_mm=120.0))
    signal = _run(twin, 0.0, 150)
    assert _rising_edges(signal) == 2


def test_part_falls_into_bin_and_counts() -> None:
    twin = Twin()
    pid = twin.drop_into_bin(PartSpec(cls=1, y_mm=0.0, theta_deg=0.0), bin_index=1)
    state = twin.state()
    for _ in range(50):
        state = twin.step(HOME_RAD, 0.0, 0.0, False)
    assert twin.part(pid).in_bin == 1
    assert state.bin_counts[1] == 1
    assert state.bin_counts[0] == 0


def test_bin_full_at_capacity() -> None:
    twin = Twin(bin_capacity=2)
    twin.drop_into_bin(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0), bin_index=4)
    twin.drop_into_bin(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0), bin_index=4)
    state = twin.state()
    for _ in range(60):
        state = twin.step(HOME_RAD, 0.0, 0.0, False)
    assert state.bin_full[4]
    assert not state.bin_full[0]


def test_part_resting_on_another_in_the_bin_counts() -> None:
    twin = Twin()
    twin.drop_into_bin(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0), bin_index=0)
    state = twin.state()
    for _ in range(40):
        state = twin.step(HOME_RAD, 0.0, 0.0, False)
    pid = twin.drop_into_bin(PartSpec(cls=0, y_mm=0.0, theta_deg=0.0), bin_index=0)
    # put the second part right on top of the first one's footprint, above the bin's rim
    first = twin.parts()[0]
    twin.place_part_at(pid, first.x_mm, first.y_mm, z_mm=twin.cfg.bins.size_mm[2] + 30.0)
    for _ in range(40):
        state = twin.step(HOME_RAD, 0.0, 0.0, False)
    assert twin.part(pid).in_bin == 0
    assert state.bin_counts[0] == 2
