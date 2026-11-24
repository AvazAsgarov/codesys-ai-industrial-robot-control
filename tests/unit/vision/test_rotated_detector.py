"""A detector that sees the image turned by quarter turns and answers in the original image."""

import numpy as np
from numpy.typing import NDArray

from airc.vision.detector import Detection, Rotated, suppress_overlaps


class _MarkFinder:
    """Detects the bright pixels; remembers the image it was given."""

    name = "marks"

    def __init__(self) -> None:
        self.seen: NDArray[np.uint8] | None = None

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        self.seen = rgb
        mask = rgb[:, :, 0] > 0
        vs, us = np.nonzero(mask)
        box = (float(us.min()), float(vs.min()), float(us.max() + 1), float(vs.max() + 1))
        return [Detection("mark", 0, 0.5, box, mask)]


def test_rotated_detector_answers_in_the_original_image() -> None:
    img = np.zeros((40, 60, 3), dtype=np.uint8)
    img[5:10, 40:58] = 255  # near the right edge: the top after a counter-clockwise turn
    inner = _MarkFinder()
    det = Rotated(inner, quarter_turns=1)
    [found] = det.detect(img)
    assert inner.seen is not None
    assert inner.seen.shape == (60, 40, 3)
    assert inner.seen[:20, :, 0].any()  # the mark is in the upper part of what the model saw
    assert np.array_equal(found.mask, img[:, :, 0] > 0)
    assert found.box_xyxy == (40.0, 5.0, 58.0, 10.0)
    assert det.name == "marks-rot90"


def test_zero_turns_is_the_detector_itself() -> None:
    inner = _MarkFinder()
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[2:4, 2:5] = 9
    assert Rotated(inner, quarter_turns=0).detect(img)[0].box_xyxy == (2.0, 2.0, 5.0, 4.0)


def test_every_turn_maps_the_box_back() -> None:
    img = np.zeros((40, 60, 3), dtype=np.uint8)
    img[5:10, 40:58] = 255
    for k in (1, 2, 3, -1):
        [found] = Rotated(_MarkFinder(), quarter_turns=k).detect(img)
        assert found.box_xyxy == (40.0, 5.0, 58.0, 10.0), k
        assert np.array_equal(found.mask, img[:, :, 0] > 0)


def test_overlapping_labels_of_one_object_keep_the_most_confident() -> None:
    m = np.zeros((4, 4), dtype=bool)
    dets = [
        Detection("can", 2, 0.9, (10.0, 10.0, 50.0, 50.0), m),
        Detection("jar", 1, 0.7, (11.0, 10.0, 50.0, 51.0), m),  # the same object, other label
        Detection("jar", 1, 0.6, (60.0, 10.0, 90.0, 50.0), m),  # another object
        Detection("box", 0, 0.5, (30.0, 10.0, 70.0, 50.0), m),  # touching, not the same object
    ]
    kept = suppress_overlaps(dets)
    assert [d.confidence for d in kept] == [0.9, 0.6, 0.5]
