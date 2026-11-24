"""Zero-shot detectors on OpenVINO (spec §6.2): YOLOE-26 with text prompts, YOLO26 (COCO).

Both are Ultralytics models exported to OpenVINO by ``airc vision export``. Ultralytics (and
torch) are imported only when a detector is created: they belong to the optional dependency
group ``vision``, and everything else (CI included) runs without them.
"""

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from airc.twin.catalogue import PartCatalogue

MASK_THRESHOLD = 0.5  # mask probability -> pixel belongs to the object
SAME_OBJECT_IOU = 0.7  # two detections overlapping this much are one object with two labels


class ModelsMissingError(FileNotFoundError):
    """An exported detector is not on this machine."""


@dataclass(frozen=True)
class LabelMap:
    """Detector label -> PLC part class (labels that are not parts map to ``None``)."""

    classes: Mapping[str, int] = field(default_factory=dict[str, int])

    @classmethod
    def for_prompts(cls, catalogue: PartCatalogue) -> "LabelMap":
        """YOLOE-26: the text prompt of each class."""
        return cls({p.prompt: i for i, p in enumerate(catalogue.classes)})

    @classmethod
    def for_slugs(cls, catalogue: PartCatalogue) -> "LabelMap":
        """YOLOE-26 with visual prompts: the classes are named by their catalogue slug."""
        return cls({p.slug: i for i, p in enumerate(catalogue.classes)})

    @classmethod
    def for_coco(cls, catalogue: PartCatalogue) -> "LabelMap":
        """YOLO26 (COCO): the COCO name of each class that has one."""
        return cls({p.coco: i for i, p in enumerate(catalogue.classes) if p.coco is not None})

    def cls(self, label: str) -> int | None:
        """PLC class of a detector label."""
        return self.classes.get(label)


@dataclass(frozen=True)
class Detection:
    """One detected object in an image."""

    label: str
    cls: int | None  # PLC class (None: a known object that is not a part)
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    mask: NDArray[np.bool_]  # image-sized


def _box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    iw = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def suppress_overlaps(
    detections: list[Detection], iou_threshold: float = SAME_OBJECT_IOU
) -> list[Detection]:
    """One label per object: the most confident of detections that overlap (any labels).

    The network suppresses duplicates per label only, so an object that looks like two classes
    would otherwise be reported twice (box IoU >= ``iou_threshold``: the same object).
    """
    kept: list[Detection] = []
    for det in sorted(detections, key=lambda d: d.confidence, reverse=True):
        if all(_box_iou(det.box_xyxy, k.box_xyxy) < iou_threshold for k in kept):
            kept.append(det)
    return kept


class Detector(Protocol):
    """Anything that finds parts in an RGB image."""

    name: str

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        """Detections in the image, best first."""
        ...


class OpenVinoDetector:
    """An Ultralytics segmentation model exported to OpenVINO."""

    def __init__(  # noqa: PLR0913 - keyword options
        self,
        model_dir: Path,
        labels: LabelMap,
        *,
        device: str = "intel:cpu",
        conf: float = 0.10,
        imgsz: int = 640,
        one_label_per_object: bool = True,
    ) -> None:
        """Load the model.

        Args:
            model_dir: The ``*_openvino_model`` directory written by ``airc vision export``.
            labels: Detector label -> PLC class.
            device: OpenVINO device (``intel:cpu``, ``intel:gpu``).
            conf: Minimum confidence of a detection.
            imgsz: Network input size.
            one_label_per_object: Keep only the most confident label of an object
                (:func:`suppress_overlaps`).

        Raises:
            ModelsMissingError: If the model directory does not exist.
        """
        if not (model_dir / "metadata.yaml").is_file():
            msg = f"no exported model in {model_dir}: run `airc vision export` first"
            raise ModelsMissingError(msg)
        ultralytics: Any = importlib.import_module("ultralytics")  # optional group `vision`

        self.name = model_dir.name.removesuffix("_openvino_model")
        self._model: Any = ultralytics.YOLO(str(model_dir), task="segment")
        self._labels = labels
        self._device = device
        self._conf = conf
        self._imgsz = imgsz
        self._one_label = one_label_per_object

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        """Detections in the image (masks at image resolution), best first."""
        results: Any = self._model.predict(
            np.ascontiguousarray(rgb[:, :, ::-1]),  # Ultralytics expects BGR arrays
            conf=self._conf,
            imgsz=self._imgsz,
            device=self._device,
            retina_masks=True,
            verbose=False,
        )
        res = results[0]
        if res.boxes is None or len(res.boxes) == 0:
            return []
        names: dict[int, str] = res.names
        boxes = res.boxes.xyxy.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()
        labels = res.boxes.cls.cpu().numpy().astype(int)
        masks = (
            res.masks.data.cpu().numpy() > MASK_THRESHOLD
            if res.masks is not None
            else np.zeros((len(boxes), *rgb.shape[:2]), dtype=bool)
        )
        out: list[Detection] = []
        for box, conf, label, mask in zip(boxes, confs, labels, masks, strict=True):
            name = names[int(label)]
            out.append(
                Detection(
                    label=name,
                    cls=self._labels.cls(name),
                    confidence=float(conf),
                    box_xyxy=(float(box[0]), float(box[1]), float(box[2]), float(box[3])),
                    mask=mask.astype(bool),
                )
            )
        out.sort(key=lambda d: d.confidence, reverse=True)
        return suppress_overlaps(out) if self._one_label else out


class Rotated:
    """A detector that is shown the image turned by quarter turns (counter-clockwise).

    The tilted inspection camera looks along the belt with the belt's +X to the image right, so
    an upright part leans sideways in the image; turned once counter-clockwise, the far end of
    the belt is at the top and parts stand upright as in everyday photos. Masks and boxes are
    turned back: the answer is in the original image.
    """

    def __init__(self, detector: Detector, quarter_turns: int = 1) -> None:
        """Wrap ``detector``; ``quarter_turns`` counter-clockwise (negative: clockwise)."""
        self._inner = detector
        self._k = quarter_turns % 4
        self.name = detector.name if self._k == 0 else f"{detector.name}-rot{90 * self._k}"

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        """Detections in the original (unturned) image, best first."""
        if self._k == 0:
            return self._inner.detect(rgb)
        turned = np.ascontiguousarray(np.rot90(rgb, self._k))
        out: list[Detection] = []
        for det in self._inner.detect(turned):
            mask = np.ascontiguousarray(np.rot90(det.mask, -self._k))
            box = det.box_xyxy
            h = turned.shape[0]
            for _ in range(self._k):  # undo one counter-clockwise turn: (x, y) <- (h - y', x')
                box = (h - box[3], box[0], h - box[1], box[2])
                h = turned.shape[1] if h == turned.shape[0] else turned.shape[0]
            out.append(Detection(det.label, det.cls, det.confidence, box, mask))
        return out
