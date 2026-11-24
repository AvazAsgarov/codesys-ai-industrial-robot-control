"""Fetch and prepare the scanned parts of ``config/parts.yaml`` into ``assets/objects/<slug>/``.

Run: ``python tools/uv_run.py --group assets python tools/fetch_objects.py [slug ...]``
(default: every candidate). Each part gets:

- ``model.obj``: the scan in its resting pose and scale, in metres, with texture coordinates.
  The origin is the centroid of the part's top view (what the camera sees) in X/Y and the
  middle of its height in Z, so the twin's body position is the pose vision reports.
- ``texture.png``: the scan's texture, at most 1024 px.
- ``meta.json``: size, grip height (top surface above the belt at the origin), source.
- ``LICENSE.txt``: CC BY 4.0 attribution (Google Scanned Objects), and what was changed.

The zip of every candidate is checked against the SHA-256 in ``parts.yaml``.
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

REPO = Path(__file__).resolve().parents[1]
CATALOGUE = REPO / "config" / "parts.yaml"
OUT = REPO / "assets" / "objects"
TEXTURE_MAX_PX = 1024
GRID_MM = 1.0  # raster for the top-view centroid
DEGENERATE = 1e-14  # a triangle with less area than this (in m^2 scale) is skipped
LICENSE = """{fuel_name} from Google Scanned Objects (Google Research), CC BY 4.0
https://creativecommons.org/licenses/by/4.0/ - source: {url}
Changes: placed in its resting pose (rotation {rotate_deg} deg), scaled by {scale}, re-centred,
texture resized to at most {px} px.
"""


@dataclass(frozen=True)
class Prepared:
    """A part ready for the twin: vertices (m), faces, texture coordinates and measurements."""

    vertices: np.ndarray
    faces: np.ndarray
    uv: np.ndarray | None
    size_mm: tuple[float, float, float]
    grip_height_mm: float


def rotation_xyz(deg: tuple[float, float, float]) -> np.ndarray:
    """Rotation matrix for X, then Y, then Z rotations (degrees, fixed axes)."""
    rx, ry, rz = np.radians(deg)
    cx, sx, cy, sy, cz, sz = np.cos(rx), np.sin(rx), np.cos(ry), np.sin(ry), np.cos(rz), np.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mz @ my @ mx


def top_view_centroid(vertices: np.ndarray, faces: np.ndarray) -> tuple[float, float]:
    """Area centroid (x, y) of the part's silhouette seen from above, by rasterising faces."""
    step = GRID_MM / 1000.0
    lo = vertices[:, :2].min(axis=0)
    hi = vertices[:, :2].max(axis=0)
    nx, ny = (np.ceil((hi - lo) / step).astype(int) + 1).tolist()
    covered = np.zeros((nx, ny), dtype=bool)
    gx = lo[0] + step * np.arange(nx)
    gy = lo[1] + step * np.arange(ny)
    for tri in vertices[faces][:, :, :2]:
        (x0, y0), (x1, y1), (x2, y2) = tri
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < DEGENERATE:
            continue
        i0, i1 = np.searchsorted(gx, [tri[:, 0].min(), tri[:, 0].max()])
        j0, j1 = np.searchsorted(gy, [tri[:, 1].min(), tri[:, 1].max()])
        if i0 >= i1 or j0 >= j1:
            continue
        px, py = np.meshgrid(gx[i0:i1], gy[j0:j1], indexing="ij")
        a = ((y1 - y2) * (px - x2) + (x2 - x1) * (py - y2)) / den
        b = ((y2 - y0) * (px - x2) + (x0 - x2) * (py - y2)) / den
        inside = (a >= 0) & (b >= 0) & (a + b <= 1)
        covered[i0:i1, j0:j1] |= inside
    ii, jj = np.nonzero(covered)
    return float(gx[ii].mean()), float(gy[jj].mean())


def surface_height_at_origin(vertices: np.ndarray, faces: np.ndarray) -> float:
    """Highest z where the vertical line through (0, 0) meets the mesh (m)."""
    best = -np.inf
    for tri in vertices[faces]:
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < DEGENERATE:
            continue
        a = ((y1 - y2) * (0 - x2) + (x2 - x1) * (0 - y2)) / den
        b = ((y2 - y0) * (0 - x2) + (x0 - x2) * (0 - y2)) / den
        c = 1 - a - b
        if a >= 0 and b >= 0 and c >= 0:
            best = max(best, a * z0 + b * z1 + c * z2)
    if best == -np.inf:
        msg = "the part has no surface above its top-view centroid (hollow in the middle)"
        raise ValueError(msg)
    return float(best)


def prepare(
    vertices: np.ndarray,
    faces: np.ndarray,
    uv: np.ndarray | None,
    rotate_deg: tuple[float, float, float],
    scale: float,
) -> Prepared:
    """Turn a scan (metres) into the resting, scaled, re-centred part."""
    v = (vertices @ rotation_xyz(rotate_deg).T) * scale
    zmin, zmax = v[:, 2].min(), v[:, 2].max()
    v[:, 2] -= (zmin + zmax) / 2
    cx, cy = top_view_centroid(v, faces)
    v[:, 0] -= cx
    v[:, 1] -= cy
    size = tuple(float(s) for s in (v.max(axis=0) - v.min(axis=0)) * 1000.0)
    grip = (surface_height_at_origin(v, faces) - v[:, 2].min()) * 1000.0
    return Prepared(v, faces, uv, (size[0], size[1], size[2]), grip)


def write_obj(path: Path, part: Prepared) -> None:
    """Write vertices (6 decimals), texture coordinates and faces as OBJ."""
    lines = [f"v {x:.6f} {y:.6f} {z:.6f}" for x, y, z in part.vertices]
    if part.uv is not None:
        lines += [f"vt {u:.6f} {v:.6f}" for u, v in part.uv]
        lines += [f"f {a + 1}/{a + 1} {b + 1}/{b + 1} {c + 1}/{c + 1}" for a, b, c in part.faces]
    else:
        lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in part.faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fetch(entry: dict[str, Any], url_template: str) -> None:
    """Download, check, prepare and write one candidate."""
    import trimesh  # noqa: PLC0415 - asset tools only (dependency group "assets")
    from PIL import Image  # noqa: PLC0415
    from trimesh.resolvers import ZipResolver  # noqa: PLC0415

    name = entry["fuel_name"]
    url = url_template.format(name=name)
    data = urllib.request.urlopen(url, timeout=120).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry["sha256"]:
        msg = f"{name}: SHA-256 {digest} does not match parts.yaml"
        raise ValueError(msg)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        obj = z.read("meshes/model.obj")
        mtl = z.read("meshes/model.mtl")
        png = z.read("materials/textures/texture.png")
    resolver = ZipResolver(io.BytesIO(data))  # pyright: ignore[reportArgumentType] - accepts a zip file object
    del mtl
    mesh: Any = trimesh.load(
        io.BytesIO(obj), file_type="obj", force="mesh", resolver=resolver, process=False
    )
    uv = getattr(mesh.visual, "uv", None)
    part = prepare(
        np.asarray(mesh.vertices, dtype=np.float64),
        np.asarray(mesh.faces, dtype=np.int64),
        None if uv is None else np.asarray(uv, dtype=np.float64),
        tuple(entry["rotate_deg"]),
        float(entry["scale"]),
    )
    out = OUT / entry["slug"]
    out.mkdir(parents=True, exist_ok=True)
    write_obj(out / "model.obj", part)
    image = Image.open(io.BytesIO(png)).convert("RGB")
    image.thumbnail((TEXTURE_MAX_PX, TEXTURE_MAX_PX))
    image.save(out / "texture.png", optimize=True)
    meta = {
        "slug": entry["slug"],
        "source": url,
        "sha256": digest,
        "licence": "CC BY 4.0",
        "rotate_deg": entry["rotate_deg"],
        "scale": entry["scale"],
        "size_mm": [round(s, 2) for s in part.size_mm],
        "grip_height_mm": round(part.grip_height_mm, 2),
        "faces": len(part.faces),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    (out / "LICENSE.txt").write_text(
        LICENSE.format(
            fuel_name=name,
            url=url,
            rotate_deg=entry["rotate_deg"],
            scale=entry["scale"],
            px=TEXTURE_MAX_PX,
        ),
        encoding="utf-8",
    )
    print(f"{entry['slug']}: size {meta['size_mm']} mm, grip {meta['grip_height_mm']} mm")


def main(slugs: list[str]) -> None:
    """Fetch the named candidates (all if none named)."""
    cat = yaml.safe_load(CATALOGUE.read_text(encoding="utf-8"))
    for entry in cat["candidates"]:
        if not slugs or entry["slug"] in slugs:
            fetch(entry, cat["fuel_url"])


if __name__ == "__main__":
    main(sys.argv[1:])
