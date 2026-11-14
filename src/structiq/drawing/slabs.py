"""Detect slab outlines in a DXF plan.

Slab outline = polyline on a layer matching ``SLAB_LAYER_PATTERN``. It counts as
closed when the DXF flag is set or its last vertex meets its first (within
``CLOSE_TOL`` mm); an outline that is neither is reported as open, not repaired.
Circles on the slab layer are listed as features to review (round openings,
curved edges or something else); StructIQ does not guess which.

Area is reported only when the drawing units are millimetres.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezdxf import bbox

from structiq.drawing import grids

SLAB_LAYER_PATTERN = r"SLAB"
CLOSE_TOL = 1.0  # mm
PLAN_MARGIN = 3000.0  # mm
MM_UNITS = 4  # $INSUNITS value for millimetres


@dataclass
class Slab:
    plan: int
    points: list[tuple[float, float]]
    closed: bool  # flag set or end meets start
    orthogonal: bool
    has_bulges: bool
    area_m2: float | None
    bbox: tuple[float, float, float, float]
    covers: list[str]  # grid intersections inside the outline


@dataclass
class SlabFeature:
    plan: int
    kind: str  # "circle"
    x: float
    y: float
    radius: float
    near_ref: str


@dataclass
class SlabResult:
    slabs: list[Slab]
    features: list[SlabFeature]
    plans_without_slab: list[int]
    outside_plans: int = 0
    warnings: list[str] = field(default_factory=list)


def _shoelace(pts: list[tuple[float, float]]) -> float:
    s = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def _inside(px: float, py: float, pts: list[tuple[float, float]]) -> bool:
    inside = False
    j = len(pts) - 1
    for i, (xi, yi) in enumerate(pts):
        xj, yj = pts[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


point_in_polygon = _inside  # public alias used by stairs/openings


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


def _ref(plan: grids.GridCluster, x: float, y: float) -> str:
    v = min(plan.vertical, key=lambda ln: abs(ln.position - x), default=None)
    h = min(plan.horizontal, key=lambda ln: abs(ln.position - y), default=None)
    return f"{v.label or '?' if v else '?'}{h.label or '?' if h else '?'}"


def extract_slabs(doc, grid_result: grids.GridResult) -> SlabResult:
    layer_re = re.compile(SLAB_LAYER_PATTERN, re.I)
    mm = doc.header.get("$INSUNITS") == MM_UNITS
    result = SlabResult([], [], [])
    for e in doc.modelspace():
        if not layer_re.search(e.dxf.layer):
            continue
        t = e.dxftype()
        ext = bbox.extents([e])
        if not ext.has_data or t not in ("LWPOLYLINE", "CIRCLE"):
            continue
        plan = _plan_for(grid_result, ext.center.x, ext.center.y)
        if plan is None:
            result.outside_plans += 1
            continue
        if t == "CIRCLE":
            c = e.dxf.center
            result.features.append(
                SlabFeature(plan.index, "circle", c.x, c.y, e.dxf.radius, _ref(plan, c.x, c.y))
            )
            continue

        pts = [(x, y) for x, y in e.get_points("xy")]
        has_bulges = any(b for (b,) in e.get_points("b"))
        met = len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) <= CLOSE_TOL and abs(pts[0][1] - pts[-1][1]) <= CLOSE_TOL
        if met:
            pts = pts[:-1]
        closed = bool(e.closed) or met
        orth = all(
            abs(a[0] - b[0]) <= CLOSE_TOL or abs(a[1] - b[1]) <= CLOSE_TOL
            for a, b in zip(pts, pts[1:] + pts[:1])
        )
        area = _shoelace(pts) / 1e6 if (closed and mm) else None
        covers = [
            _ref_pair(v, h)
            for v in plan.vertical
            for h in plan.horizontal
            if closed and _inside(v.position, h.position, pts)
        ]
        result.slabs.append(
            Slab(
                plan.index,
                pts,
                closed,
                orth,
                has_bulges,
                area,
                (ext.extmin.x, ext.extmin.y, ext.extmax.x, ext.extmax.y),
                covers,
            )
        )
    result.slabs.sort(key=lambda s: s.plan)
    with_slab = {s.plan for s in result.slabs}
    result.plans_without_slab = [c.index for c in grid_result.clusters if c.index not in with_slab]
    return result


def _ref_pair(v: grids.GridLine, h: grids.GridLine) -> str:
    return f"{v.label or '?'}{h.label or '?'}"


def format_slabs_report(result: SlabResult, grid_result: grids.GridResult) -> str:
    out = ["SLABS (outline polylines on the slab layer; confirm against the drawing)"]
    total = {c.index: len(c.vertical) * len(c.horizontal) for c in grid_result.clusters}
    for s in result.slabs:
        area = f"{s.area_m2:.1f} m2" if s.area_m2 is not None else "area n/a"
        shape = "orthogonal" if s.orthogonal else "has diagonal edges"
        state = "closed" if s.closed else "OPEN outline (ends do not meet)"
        out.append(f"\nPlan {s.plan}: {len(s.points)} vertices, {area}, {shape}, {state}")
        out.append(
            f"  bbox x {s.bbox[0]:.0f}..{s.bbox[2]:.0f}, y {s.bbox[1]:.0f}..{s.bbox[3]:.0f}"
        )
        if s.closed:
            out.append(
                f"  Covers {len(s.covers)} of {total.get(s.plan, 0)} grid intersections"
                + (f": {', '.join(s.covers)}" if s.covers else "")
            )
        if s.has_bulges:
            out.append("  ! outline has curved segments; vertices only, curves not followed")
        if not s.closed:
            out.append("  ! open outline: area and coverage not computed")
    if result.plans_without_slab:
        out.append(
            "\n! No slab outline found for plan(s): "
            + ", ".join(str(p) for p in result.plans_without_slab)
        )
    if result.features:
        out.append("\nCircles on the slab layer (round openings or curved edges? please review):")
        for f in result.features:
            out.append(
                f"  plan {f.plan}: circle r={f.radius:.0f} mm at ({f.x:.0f}, {f.y:.0f}), near {f.near_ref}"
            )
    if result.outside_plans:
        out.append(f"\nSlab-layer objects outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def add_slabs(doc, result: SlabResult) -> None:
    """Add outlines on S-SLAB-EDGE; open outlines and circles go to S-SLAB-CHECK."""
    for name, color in (("S-SLAB-EDGE", 4), ("S-SLAB-CHECK", 6), ("S-SLAB-TXT", 2)):
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for s in result.slabs:
        layer = "S-SLAB-EDGE" if s.closed else "S-SLAB-CHECK"
        msp.add_lwpolyline(s.points, close=s.closed, dxfattribs={"layer": layer})
        if s.closed:
            cx = sum(p[0] for p in s.points) / len(s.points)
            cy = sum(p[1] for p in s.points) / len(s.points)
            label = f"SLAB {s.area_m2:.1f} m2" if s.area_m2 is not None else "SLAB"
            msp.add_text(label, height=300, dxfattribs={"layer": "S-SLAB-TXT", "insert": (cx, cy)})
    for f in result.features:
        msp.add_circle((f.x, f.y), f.radius, dxfattribs={"layer": "S-SLAB-CHECK"})
