"""Export of the detectors to OpenVINO (``airc vision export``).

Weights are downloaded by Ultralytics into ``models/`` (git-ignored); their SHA-256 is recorded
in ``assets/models/manifest.yaml`` so a result can be traced to the exact weights. YOLOE-26 is
exported with its text prompts set: the prompts are folded into the exported network.
"""

import hashlib
import importlib
import json
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from airc.common.config import default_config_path

YOLOE_WEIGHTS = "yoloe-26s-seg.pt"
COCO_WEIGHTS = "yolo26s-seg.pt"
Precision = Literal["fp32", "fp16"]


def repo_root() -> Path:
    """The repository (parent of ``config/``)."""
    return default_config_path().parent.parent


def models_dir() -> Path:
    """Where weights and exported models live (git-ignored)."""
    return repo_root() / "models"


def yoloe_dir(tag: str, precision: Precision = "fp32") -> Path:
    """Exported YOLOE-26 with the prompt set ``tag``."""
    return models_dir() / f"yoloe-26s-seg-{tag}-{precision}_openvino_model"


def coco_dir(precision: Precision = "fp32") -> Path:
    """Exported YOLO26 (COCO)."""
    return models_dir() / f"yolo26s-seg-{precision}_openvino_model"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(weights: Path, exported: Path, prompts: Sequence[str] | None) -> None:
    manifest = repo_root() / "assets" / "models" / "manifest.json"
    data: dict[str, Any] = (
        json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}
    )
    data[exported.name] = {
        "weights": weights.name,
        "weights_sha256": _sha256(weights),
        "prompts": list(prompts) if prompts is not None else None,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _export(model: Any, target: Path, precision: Precision) -> Path:  # noqa: ANN401 - Ultralytics model
    produced = Path(model.export(format="openvino", half=precision == "fp16", imgsz=640))
    if target.exists():
        shutil.rmtree(target)
    shutil.move(str(produced), str(target))
    return target


def export_yoloe(prompts: Sequence[str], tag: str, precision: Precision = "fp32") -> Path:
    """Export YOLOE-26-S (segmentation) with the given text prompts to OpenVINO."""
    ultralytics: Any = importlib.import_module("ultralytics")
    models_dir().mkdir(exist_ok=True)
    weights = models_dir() / YOLOE_WEIGHTS
    model = ultralytics.YOLOE(str(weights))
    model.set_classes(list(prompts))
    target = _export(model, yoloe_dir(tag, precision), precision)
    _record(weights, target, prompts)
    return target


def export_coco(precision: Precision = "fp32") -> Path:
    """Export YOLO26-S (segmentation, COCO classes) to OpenVINO."""
    ultralytics: Any = importlib.import_module("ultralytics")
    models_dir().mkdir(exist_ok=True)
    weights = models_dir() / COCO_WEIGHTS
    model = ultralytics.YOLO(str(weights))
    target = _export(model, coco_dir(precision), precision)
    _record(weights, target, None)
    return target
