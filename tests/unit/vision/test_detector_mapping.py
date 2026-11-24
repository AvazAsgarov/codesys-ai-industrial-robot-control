"""Detector labels -> PLC classes; models that are missing are reported with the fix."""

from pathlib import Path

import pytest

from airc.twin.catalogue import PartCatalogue
from airc.vision.detector import LabelMap, ModelsMissingError, OpenVinoDetector


def test_label_map_prompt_and_coco() -> None:
    cat = PartCatalogue.load()
    prompts = LabelMap.for_prompts(cat)
    coco = LabelMap.for_coco(cat)
    for cls, part in enumerate(cat.classes):
        assert prompts.cls(part.prompt) == cls
        if part.coco is not None:
            assert coco.cls(part.coco) == cls
    assert prompts.cls("banana") is None
    assert coco.cls("person") is None


def test_missing_models_message(tmp_path: Path) -> None:
    with pytest.raises(ModelsMissingError, match="airc vision export"):
        OpenVinoDetector(tmp_path / "nothing_here", LabelMap({}))
