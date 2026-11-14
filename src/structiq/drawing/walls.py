"""Detect wall segments in a DXF plan and relate them to the gridlines.

In the test drawing each wall segment is an anonymous block (``*U...``) placed
on a wall layer, so the *layer* is meaningful but the block name is not:

* **Block walls**: an INSERT on a layer matching ``WALL_LAYER_PATTERN`` whose
  bounding box is wall-shaped (thickness ``MIN_THICK``..``MAX_THICK`` mm, length
  at least ``MIN_ASPECT`` x thickness).
* **Direct walls**: closed 4-vertex rectangular polylines on a wall layer.
  Other polylines on wall layers are counted, not extracted.

Wall kind comes from the layer name: ``brick`` (infill), ``structural``
(layer name contains STRUCT) or ``other``. Walls are axis-aligned boxes; a
rotated block that is not a multiple of 90 degrees is flagged because its
bounding box overstates the wall.

Objects on a ``STRUCT`` layer that are too small to be walls are reported so
the engineer can check them; nothing is silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezdxf import bbox

from structiq.drawing import grids

WALL_LAYER_PATTERN = r"WALL"
MIN_THICK = 50.0  # mm
MAX_THICK = 600.0  # mm
MIN_ASPECT = 2.0
ON_GRID_TOL = 150.0  # mm
PLAN_MARGIN = 3000.0  # mm


@dataclass
class Wall:
    plan: int
    orientation: str  # "H" runs along x, "V" runs along y
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float
    length: float
    layer: str
    kind: str  # "brick" | "structural" | "other"
    grid_line: str | None  # label of the gridline it lies on, if any
    skewed: bool = False

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2


@dataclass
class WallResult:
    walls: list[Wall]
    non_rectangular: int = 0  # wall-layer polylines that are not simple rectangles
    not_wall_shaped: int = 0  # wall-layer blocks inside plans that are too thick/short (L, T...)
    rejected_structural: list[tuple[int | None, str, float, float]] = field(default_factory=list)
    outside_plans: int = 0


def _kind(layer: str) -> str:
    up = layer.upper()
    if "STRUCT" in up:
        return "structural"
    if "BRICK" in up:
        return "brick"
    return "other"


def _plan_for(grid_result: grids.GridResult, cx: float, cy: float):
    return next(
        (
            c
            for c in grid_result.clusters
            if c.bbox[0] - PLAN_MARGIN <= cx <= c.bbox[2] + PLAN_MARGIN
            and c.bbox[1] - PLAN_MARGIN <= cy <= c.bbox[3] + PLAN_MARGIN
        ),
        None,
    )


def extract_walls(doc, grid_result: grids.GridResult) -> WallResult:
    layer_re = re.compile(WALL_LAYER_PATTERN, re.I)
    msp = doc.modelspace()
    result = WallResult([])
    seen: set[tuple[int, int, int, int]] = set()

    for e in msp:
        if not layer_re.search(e.dxf.layer):
            continue
        t = e.dxftype()
        if t not in ("INSERT", "LWPOLYLINE"):
            continue
        if t == "LWPOLYLINE" and not (e.closed and len(e) == 4):
            result.non_rectangular += 1
            continue
        ext = bbox.extents([e])
        if not ext.has_data:
            continue
        w, h = ext.size.x, ext.size.y
        thick, length = min(w, h), max(w, h)
        plan = _plan_for(grid_result, ext.center.x, ext.center.y)
        wall_like = MIN_THICK <= thick <= MAX_THICK and length >= MIN_ASPECT * thick
        if not wall_like:
            if "STRUCT" in e.dxf.layer.upper():
                result.rejected_structural.append(
                    (plan.index if plan else None, e.dxf.layer, round(w), round(h))
                )
            elif plan is not None:
                result.not_wall_shaped += 1
            continue
        key = (round(ext.extmin.x), round(ext.extmin.y), round(ext.extmax.x), round(ext.extmax.y))
        if key in seen:
            continue
        seen.add(key)
        if plan is None:
            result.outside_plans += 1
            continue

        orientation = "H" if w >= h else "V"
        lines = plan.horizontal if orientation == "H" else plan.vertical
        axis = ext.center.y if orientation == "H" else ext.center.x
        near = min(lines, key=lambda ln: abs(ln.position - axis)) if lines else None
        on_grid = near is not None and abs(near.position - axis) <= ON_GRID_TOL
        rot = abs(e.dxf.rotation) % 90 if t == "INSERT" else 0.0
        result.walls.append(
            Wall(
                plan.index,
                orientation,
                ext.extmin.x,
                ext.extmin.y,
                ext.extmax.x,
                ext.extmax.y,
                thick,
                length,
                e.dxf.layer,
                _kind(e.dxf.layer),
                (near.label or "?") if on_grid else None,
                skewed=min(rot, 90 - rot) > 1.0,
            )
        )
    result.walls.sort(key=lambda x: (x.plan, x.orientation, x.centre[1], x.centre[0]))
    return result


def format_walls_report(result: WallResult) -> str:
    out = ["WALLS (detected from wall-layer blocks and rectangles; confirm against the drawing)"]
    plans = sorted({w.plan for w in result.walls})
    for p in plans:
        ws = [w for w in result.walls if w.plan == p]
        total = sum(w.length for w in ws) / 1000
        out.append(f"\nPlan {p}: {len(ws)} wall segments, total length {total:.1f} m")
        by_kind: dict[tuple[str, int], list[Wall]] = {}
        for w in ws:
            by_kind.setdefault((w.kind, round(w.thickness)), []).append(w)
        for (kind, thick), group in sorted(by_kind.items()):
            length = sum(w.length for w in group) / 1000
            out.append(f"  {kind:<10} {thick:>4} mm thick: {len(group):>3} segments, {length:.1f} m")
        on: dict[tuple[str, str], list[Wall]] = {}
        for w in ws:
            if w.grid_line is not None:
                on.setdefault((w.orientation, w.grid_line), []).append(w)
        if on:
            parts = [f"{name} x{len(g)}" for (_, name), g in sorted(on.items())]
            out.append(f"  On a gridline: {', '.join(parts)}")
        out.append(f"  Off gridlines: {sum(1 for w in ws if w.grid_line is None)} segments")
        skew = [w for w in ws if w.skewed]
        if skew:
            out.append(f"  ! {len(skew)} segment(s) rotated off 90 degrees: sizes are approximate")
        if not any(w.kind == "structural" for w in ws):
            out.append("  No structural (RC) walls identified on a structural-wall layer.")
    if result.rejected_structural:
        out.append(
            f"\n! {len(result.rejected_structural)} object(s) on a STRUCT wall layer are too small "
            "to be walls (not extracted); check them:"
        )
        for plan, layer, w, h in result.rejected_structural[:12]:
            out.append(f"  plan {plan}: {layer!r} {w} x {h} mm")
    if result.not_wall_shaped:
        out.append(
            f"\n! {result.not_wall_shaped} wall-layer block(s) inside plans are not wall-shaped "
            f"(thickness outside {MIN_THICK:.0f}-{MAX_THICK:.0f} mm or too short, e.g. L/T walls); "
            "not extracted."
        )
    if result.non_rectangular:
        out.append(
            f"\n! {result.non_rectangular} wall-layer polyline(s) are not simple rectangles "
            "(not extracted)."
        )
    if result.outside_plans:
        out.append(f"\nWall objects outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def add_walls(doc, result: WallResult) -> None:
    """Add wall rectangles on S-WALL (structural), S-WALL-INFILL (brick) or S-WALL-CHECK."""
    layers = {
        "structural": ("S-WALL", 5),
        "brick": ("S-WALL-INFILL", 8),
        "other": ("S-WALL-CHECK", 6),
    }
    for name, color in layers.values():
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for w in result.walls:
        pts = [(w.x0, w.y0), (w.x1, w.y0), (w.x1, w.y1), (w.x0, w.y1)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layers[w.kind][0]})
