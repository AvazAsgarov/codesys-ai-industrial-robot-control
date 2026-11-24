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


class Detector(Protocol):
    """Anything that finds parts in an RGB image."""

    name: str

    def detect(self, rgb: NDArray[np.uint8]) -> list[Detection]:
        """Detections in the image, best first."""
        ...


class OpenVinoDetector:
    """An Ultralytics segmentation model exported to OpenVINO."""

    def __init__(
        self,
        model_dir: Path,
        labels: LabelMap,
        device: str = "intel:cpu",
        conf: float = 0.10,
        imgsz: int = 640,
    ) -> None:
        """Load the model.

        Args:
            model_dir: The ``*_openvino_model`` directory written by ``airc vision export``.
            labels: Detector label -> PLC class.
            device: OpenVINO device (``intel:cpu``, ``intel:gpu``).
            conf: Minimum confidence of a detection.
            imgsz: Network input size.

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
        return out
