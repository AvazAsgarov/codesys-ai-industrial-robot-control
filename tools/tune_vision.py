"""Tune the zero-shot vision on the tuning seed (plan Task 7, step 3).

Run: ``python tools/uv_run.py --group vision --group assets python tools/tune_vision.py``

Grid: camera tilt x class triple (one box, one jar, the coffee can) x YOLOE prompt wording x
image orientation (the window as the camera sees it, or turned a quarter counter-clockwise so
the far end of the belt is at the top). Every configuration is scored with the same metrics as
``airc eval vision`` on the same seeded frames.

One YOLOE-26 model is exported with every prompt wording; a prompt triple is scored by keeping
only the detections of its three prompts (the network scores each prompt on its own, so this is
what a model exported with just those prompts reports, up to its top-k limit). The best
configuration is then re-run with a model exported with exactly its three prompts to confirm.

Writes ``experiments/results/vision_tuning.json``.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path
from typing import Any

from airc.evaluation.dataset import render_dataset
from airc.evaluation.vision_eval import Scorer, evaluate, make_detector
from airc.twin.config import TwinConfig
from airc.vision import models
from airc.vision.detector import (
    Detection,
    Detector,
    LabelMap,
    OpenVinoDetector,
    Rotated,
    suppress_overlaps,
)

BOXES = ["probiotic_box", "candy_box", "ink_cartridge"]
JARS = ["vitamin_jar", "glucosamine_jar"]
CANS = ["coffee_can"]
BOX_PROMPTS = ["box", "cardboard box", "carton", "package"]
JAR_PROMPTS = ["bottle", "jar", "pill bottle"]
CAN_PROMPTS = ["can", "tin can", "coffee can"]
VARIANTS_TAG = "variants"
TUNED_TAG = "tuned"


def _relabel(dets: list[Detection], prompts: tuple[str, ...]) -> list[Detection]:
    """The detections a model with only ``prompts`` would report, with their class index."""
    index = {p: i for i, p in enumerate(prompts)}
    return [
        Detection(d.label, index[d.label], d.confidence, d.box_xyxy, d.mask)
        for d in dets
        if d.label in index
    ]


def _variants_model() -> Path:
    all_prompts = [*BOX_PROMPTS, *JAR_PROMPTS, *CAN_PROMPTS]
    path = models.yoloe_dir(VARIANTS_TAG)
    if not (path / "metadata.yaml").is_file():
        models.export_yoloe(all_prompts, VARIANTS_TAG)
    return path


def _row(res: dict[str, Any], turns: int) -> dict[str, Any]:
    return {"quarter_turns": turns, **res}


def _summary(row: dict[str, Any]) -> str:
    per = ", ".join(f"{k} {v['AP50']}" for k, v in row["per_class"].items())
    return (
        f"tilt {row['tilt']:>4} turns {row['quarter_turns']} {row['prompts']}: "
        f"mAP {row['mAP50']} ({per})"
    )


def main() -> None:
    """Run the grid and write the results."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--seed", type=int, default=300)
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--tilts", default="25,40,55")
    ap.add_argument("--turns", default="0,1", help="quarter turns of the window to try")
    ap.add_argument("--out", type=Path, default=Path("experiments/results/vision_tuning.json"))
    args = ap.parse_args()
    tilts = [float(t) for t in args.tilts.split(",")]
    turn_options = [int(k) for k in args.turns.split(",")]
    prompt_sets = list(itertools.product(BOX_PROMPTS, JAR_PROMPTS, CAN_PROMPTS))
    raw: Detector = OpenVinoDetector(_variants_model(), LabelMap(), one_label_per_object=False)
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for tilt, triple in itertools.product(tilts, itertools.product(BOXES, JARS, CANS)):
        base = TwinConfig.load(parts="catalogue", classes=list(triple)).with_camera_tilt(tilt)
        detectors = {k: Rotated(raw, k) for k in turn_options}
        scorers = {(k, ps): Scorer(detectors[k].name) for k in turn_options for ps in prompt_sets}
        warm = False
        for frame in render_dataset(args.seed, args.frames, base):
            for k, det in detectors.items():
                if not warm:
                    det.detect(frame.rgb)
                t0 = time.perf_counter()
                found = det.detect(frame.rgb)
                ms = (time.perf_counter() - t0) * 1000.0
                for ps in prompt_sets:
                    scorers[k, ps].add(frame, suppress_overlaps(_relabel(found, ps)), ms)
            warm = True
        best = None
        for (k, ps), scorer in scorers.items():
            row = _row({**scorer.result(), "prompts": list(ps)}, k)
            rows.append(row)
            if best is None or (row["mAP50"] or 0.0) > (best["mAP50"] or 0.0):
                best = row
        assert best is not None
        print(
            f"[{time.perf_counter() - started:6.0f} s] {triple}: best {_summary(best)}", flush=True
        )
    rows.sort(key=lambda r: -(r["mAP50"] or 0.0))
    top = rows[0]
    confirm = _confirm(top, args.seed, args.frames)
    record = {
        "command": "python tools/tune_vision.py "
        f"--seed {args.seed} --frames {args.frames} --tilts {args.tilts} --turns {args.turns}",
        "seed": args.seed,
        "frames": args.frames,
        "device": "intel:cpu",
        "camera": "exact",
        "method": (
            "one YOLOE-26s export with every prompt wording; a prompt triple keeps only the "
            "detections of its prompts; the best configuration is confirmed with a model "
            "exported with exactly its three prompts"
        ),
        "grid": {
            "tilts": tilts,
            "quarter_turns": turn_options,
            "boxes": BOXES,
            "jars": JARS,
            "cans": CANS,
            "box_prompts": BOX_PROMPTS,
            "jar_prompts": JAR_PROMPTS,
            "can_prompts": CAN_PROMPTS,
        },
        "best": top,
        "best_confirmed": confirm,
        "configurations": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8")
    for row in rows[:5]:
        print(_summary(row))
    print(f"confirmed with an export of {top['prompts']}: mAP {confirm['mAP50']} -> {args.out}")


def _confirm(top: dict[str, Any], seed: int, frames: int) -> dict[str, Any]:
    """Re-run the best configuration with a model exported with exactly its three prompts."""
    models.export_yoloe(top["prompts"], TUNED_TAG)
    cfg = TwinConfig.load(parts="catalogue", classes=top["classes"]).with_camera_tilt(top["tilt"])
    det = make_detector(
        "yoloe", TUNED_TAG, cfg, prompts=top["prompts"], quarter_turns=top["quarter_turns"]
    )
    res = evaluate(det, render_dataset(seed, frames, cfg))
    return _row({**res, "prompts": top["prompts"]}, top["quarter_turns"])


if __name__ == "__main__":
    main()
