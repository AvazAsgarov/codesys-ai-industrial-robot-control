"""The scanned part catalogue (``config/parts.yaml`` + ``assets/objects/<slug>/``).

The candidates are the shortlist of scanned objects; ``classes`` are the three sorted part types
in PLC class order. Sizes and grip heights come from each part's ``meta.json``, written by
``tools/fetch_objects.py``.
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from airc.common.config import default_config_path


class PartModel(BaseModel):
    """One scanned part: prompts for the detectors, files and measurements."""

    model_config = ConfigDict(frozen=True)

    slug: str
    prompt: str
    coco: str | None
    symmetry: int  # rotational symmetry about the vertical (1 none, 2 = 180 deg, 0 round)
    mesh_path: Path
    texture_path: Path
    size_mm: tuple[float, float, float]  # x, y, z as it rests (z = height)
    grip_height_mm: float  # top surface above the belt at the part's origin (the cup's target)


class PartCatalogue(BaseModel):
    """The shortlist (as prepared on this machine) and the three sorted classes."""

    model_config = ConfigDict(frozen=True)

    candidates: tuple[PartModel, ...]
    classes: tuple[PartModel, ...]

    @classmethod
    def load(cls, path: Path | None = None, assets: Path | None = None) -> "PartCatalogue":
        """Load ``config/parts.yaml`` and the prepared assets (default: the repository's).

        Raises:
            FileNotFoundError: If a candidate was not prepared (run tools/fetch_objects.py).
        """
        file = path if path is not None else default_config_path().parent / "parts.yaml"
        root = assets if assets is not None else file.resolve().parents[1] / "assets" / "objects"
        raw: Any = yaml.safe_load(file.read_text(encoding="utf-8"))
        chosen: list[str] = list(raw["classes"])
        parts: dict[str, PartModel] = {}
        for entry in raw["candidates"]:
            folder = root / entry["slug"]
            meta_file = folder / "meta.json"
            if not meta_file.is_file():
                if entry["slug"] not in chosen:
                    continue  # a candidate not prepared on this machine (only the classes are kept)
                msg = f"{meta_file} missing: run python tools/fetch_objects.py {entry['slug']}"
                raise FileNotFoundError(msg)
            meta: Any = json.loads(meta_file.read_text(encoding="utf-8"))
            parts[entry["slug"]] = PartModel(
                slug=entry["slug"],
                prompt=entry["prompt"],
                coco=entry.get("coco"),
                symmetry=int(entry["symmetry"]),
                mesh_path=folder / "model.obj",
                texture_path=folder / "texture.png",
                size_mm=tuple(meta["size_mm"]),
                grip_height_mm=float(meta["grip_height_mm"]),
            )
        return cls(
            candidates=tuple(parts.values()),
            classes=tuple(parts[slug] for slug in chosen),
        )

    def with_classes(self, slugs: Sequence[str]) -> "PartCatalogue":
        """The same shortlist with other candidates as the sorted classes (in this order).

        Raises:
            KeyError: If a slug is not a prepared candidate.
        """
        by_slug = {p.slug: p for p in self.candidates}
        missing = [s for s in slugs if s not in by_slug]
        if missing:
            msg = f"not prepared candidates: {', '.join(missing)}"
            raise KeyError(msg)
        return self.model_copy(update={"classes": tuple(by_slug[s] for s in slugs)})
