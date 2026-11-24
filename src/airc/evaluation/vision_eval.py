"""Zero-shot detector benchmark (``airc eval vision``, plan Task 7).

A detector runs on every labelled frame of a rendered dataset (the window around PE1 that the
vision worker uses). Detection quality is AP@0.5 per class, mAP and precision/recall at a
confidence threshold; pose quality is measured for the confident detections that match a part
(same class, IoU >= 0.5), with the same pixel -> belt conversion as the vision worker and a
theta error that respects each class's rotational symmetry; latency is the detector call alone.
"""

import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from airc.evaluation.dataset import LabelledFrame, SceneInfo
from airc.evaluation.metrics import (
    Box,
    Truth,
    angle_error_deg,
    iou,
    mean_ap,
    per_class_stats,
    percentile_summary,
    position_error_mm,
)
from airc.evaluation.metrics import Detection as Scored
from airc.twin.catalogue import PartCatalogue
from airc.twin.config import TwinConfig
from airc.vision.detector import Detection, Detector, LabelMap, ModelsMissingError, Rotated
from airc.vision.service import belt_pose

CONF = 0.25  # precision, recall and pose are counted at this confidence
IOU = 0.5
DETECTORS = ("yoloe-visual", "yoloe", "yolo26", "oracle")


def _fbox(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    return float(box[0]), float(box[1]), float(box[2]), float(box[3])


class OracleDetector:
    """Returns the true masks of the frame last shown with :meth:`see` (the pose ceiling)."""

    name = "oracle"

    def __init__(self) -> None:
        """Start without a frame."""
        self._frame: LabelledFrame | None = None

    def see(self, frame: LabelledFrame) -> None:
        """The frame whose truth the next :meth:`detect` returns."""
        self._frame = frame

    def detect(self, rgb: Any) -> list[Detection]:  # noqa: ANN401 - the image is not used
        """The labelled parts as detections with confidence 1."""
        del rgb
        if self._frame is None:
            return []
        return [Detection("truth", p.cls, 1.0, _fbox(p.box), p.mask) for p in self._frame.parts]


def _model_names(model_dir: Path) -> set[str]:
    meta: Any = yaml.safe_load((model_dir / "metadata.yaml").read_text(encoding="utf-8"))
    return {str(n) for n in dict(meta.get("names", {})).values()}


def make_detector(  # noqa: PLR0913 - keyword options
    kind: str,
    tag: str,
    cfg: TwinConfig,
    *,
    prompts: Sequence[str] | None = None,
    device: str = "intel:cpu",
    quarter_turns: int = 0,
) -> Detector:
    """A detector for the classes of ``cfg`` (catalogue parts).

    Args:
        kind: ``yoloe-visual`` (visual prompts made from reference renders, the cell's
            detector), ``yoloe`` (text prompts), ``yolo26`` (COCO names) or ``oracle``
            (true masks).
        tag: Text prompt set of the exported YOLOE model (``classes``, ``candidates``, or a
            tuning tag); ignored by the other detectors.
        cfg: Twin configuration whose classes are catalogue parts.
        prompts: YOLOE prompt per class (default: the catalogue's).
        device: OpenVINO device.
        quarter_turns: Show the detector the window turned this many quarter turns
            counter-clockwise (1: far end of the belt at the top, parts upright).

    Raises:
        ModelsMissingError: If the exported model is not on this machine.
        ValueError: If two classes share a prompt or the model lacks a class's prompt.
    """
    if kind == "oracle":
        return OracleDetector()
    from airc.vision import models  # noqa: PLC0415 - optional dependency group `vision`
    from airc.vision.detector import OpenVinoDetector  # noqa: PLC0415

    catalogue = PartCatalogue.load().with_classes([c.name for c in cfg.parts.classes])
    if kind == "yolo26":
        labels = LabelMap({p.coco: i for i, p in enumerate(catalogue.classes) if p.coco})
        return Rotated(OpenVinoDetector(models.coco_dir(), labels, device=device), quarter_turns)
    if kind == "yoloe-visual":  # the cell's detector: classes named by their slug
        tag, texts = "visual", [p.slug for p in catalogue.classes]
    elif kind == "yoloe":
        texts = list(prompts) if prompts is not None else [p.prompt for p in catalogue.classes]
    else:
        msg = f"unknown detector {kind!r} (one of {', '.join(DETECTORS)})"
        raise ValueError(msg)
    if len(set(texts)) != len(texts):
        msg = f"two classes share a prompt ({texts}): YOLOE cannot tell them apart"
        raise ValueError(msg)
    model_dir = models.yoloe_dir(tag)
    if not (model_dir / "metadata.yaml").is_file():
        msg = f"no exported model in {model_dir}: run `airc vision export --prompts {tag}` first"
        raise ModelsMissingError(msg)
    missing = set(texts) - _model_names(model_dir)
    if missing:
        msg = f"{model_dir.name} was exported without the prompts {sorted(missing)}"
        raise ValueError(msg)
    labels = LabelMap({t: i for i, t in enumerate(texts)})
    return Rotated(OpenVinoDetector(model_dir, labels, device=device), quarter_turns)


def match_frame(
    detections: Sequence[Detection],
    truths: Sequence[tuple[int, tuple[float, float, float, float]]],
    conf: float = CONF,
    iou_threshold: float = IOU,
) -> dict[int, int]:
    """Detection index -> truth index for one frame (greedy, most confident first).

    Only detections of a part class at or above ``conf`` take part; each truth is matched at
    most once, to the unused truth of the same class with the highest IoU >= ``iou_threshold``.
    """
    order = sorted(
        (i for i, d in enumerate(detections) if d.cls is not None and d.confidence >= conf),
        key=lambda i: -detections[i].confidence,
    )
    used: set[int] = set()
    out: dict[int, int] = {}
    for i in order:
        det = detections[i]
        best, best_iou = -1, iou_threshold
        for j, (cls, box) in enumerate(truths):
            if j in used or cls != det.cls:
                continue
            overlap = iou(Box(*det.box_xyxy), Box(*box))
            if overlap >= best_iou:
                best, best_iou = j, overlap
        if best >= 0:
            used.add(best)
            out[i] = best
    return out


def _clean(value: Any) -> Any:  # noqa: ANN401 - JSON tree
    """NaN -> None and rounding, so the result is valid, readable JSON."""
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 4)
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


class Scorer:
    """Accumulates one detector's answers over labelled frames and scores them."""

    def __init__(self, name: str, conf: float = CONF, iou_threshold: float = IOU) -> None:
        """Start empty.

        Args:
            name: Detector name for the record.
            conf: Confidence for precision, recall and the pose errors.
            iou_threshold: IoU for a detection to match a part.
        """
        self.name = name
        self.conf = conf
        self.iou = iou_threshold
        self._scored: list[Scored] = []
        self._truths: list[Truth] = []
        self._latencies: list[float] = []
        self._pos: list[float] = []
        self._theta: list[float] = []
        self._frames = 0
        self._scene: SceneInfo | None = None

    def add(self, frame: LabelledFrame, dets: Sequence[Detection], latency_ms: float) -> None:
        """Score the detections of one frame."""
        scene = self._scene = frame.scene
        self._frames += 1
        self._latencies.append(latency_ms)
        boxes = [(p.cls, _fbox(p.box)) for p in frame.parts]
        self._truths += [Truth(frame.index, cls, Box(*box)) for cls, box in boxes]
        self._scored += [
            Scored(frame.index, d.cls, d.confidence, Box(*d.box_xyxy))
            for d in dets
            if d.cls is not None
        ]
        for i, j in match_frame(dets, boxes, self.conf, self.iou).items():
            part = frame.parts[j]
            pose = belt_pose(dets[i], scene.roi, scene.camera, scene.geo, scene.classes)
            self._pos.append(position_error_mm((pose.x_mm, pose.y_mm), (part.x_mm, part.y_mm)))
            symmetry = scene.symmetry[part.cls]
            if symmetry != 0:  # a round part has no orientation to get wrong
                self._theta.append(angle_error_deg(pose.theta_deg, part.theta_deg, symmetry))

    def result(self) -> dict[str, Any]:
        """The result record (JSON-ready; NaN written as null).

        Raises:
            ValueError: If no frame was added.
        """
        scene = self._scene
        if scene is None:
            msg = "no frames to evaluate"
            raise ValueError(msg)
        classes = list(range(len(scene.slugs)))
        stats = per_class_stats(self._scored, self._truths, classes, self.iou, self.conf)
        result: dict[str, Any] = {
            "detector": self.name,
            "tilt": scene.tilt_deg,
            "classes": list(scene.slugs),
            "prompts": list(scene.prompts),
            "frames": self._frames,
            "parts": len(self._truths),
            "conf": self.conf,
            "iou": self.iou,
            "mAP50": mean_ap(stats),
            "per_class": {
                scene.slugs[c]: {
                    "P": s.precision,
                    "R": s.recall,
                    "AP50": s.ap50,
                    "n_truth": s.n_truth,
                    "n_det": s.n_det,
                }
                for c, s in stats.items()
            },
            "pose_mm": percentile_summary(self._pos),
            "theta_deg": percentile_summary(self._theta),
            "latency_ms": percentile_summary(self._latencies),
        }
        return _clean(result)


def evaluate(
    detector: Detector,
    frames: Iterable[LabelledFrame],
    frame_hook: Callable[[LabelledFrame], None] | None = None,
    conf: float = CONF,
    iou_threshold: float = IOU,
) -> dict[str, Any]:
    """Run ``detector`` on every frame and score it against the truth.

    Args:
        detector: The detector (its first call is a warm-up and is not timed).
        frames: The labelled frames (e.g. :func:`airc.evaluation.dataset.render_dataset`).
        frame_hook: Called with each frame before the detector (the oracle's :meth:`see`).
        conf: Confidence for precision, recall and the pose errors.
        iou_threshold: IoU for a detection to match a part.

    Returns:
        The result record of :meth:`Scorer.result`.
    """
    scorer = Scorer(detector.name, conf, iou_threshold)
    warm = False
    for frame in frames:
        if frame_hook is not None:
            frame_hook(frame)
        if not warm:
            detector.detect(frame.rgb)  # warm-up (model compilation, caches)
            warm = True
        t0 = time.perf_counter()
        dets = detector.detect(frame.rgb)
        scorer.add(frame, dets, (time.perf_counter() - t0) * 1000.0)
    return scorer.result()
