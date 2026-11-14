"""Detect stairs in a DXF plan from stacks of tread rectangles.

In the test drawing a stair is one block holding closed rectangular polylines
(one per tread) stacked at a pitch equal to the tread depth, one stack per
flight, on stair layers *inside the block* while the INSERT itself sits on layer
``0``. So stairs are recognised by geometry, not by names or layers:

* a flight = at least ``MIN_TREADS`` identical axis-aligned rectangles
  (depth ``DEPTH_RANGE`` mm, width ``WIDTH_RANGE`` mm) touching end to end;
* a stair = every flight found in one block insert, plus the other geometry on the
  same layers as the treads (landings, walls of the stair) for its footprint.

Blocks rotated off a multiple of 90 degrees are skipped and counted, because the
detection works on axis-aligned boxes.

Whether a slab opening is drawn at the stair is not guessed: the report states if
the stair centre lies inside the slab outline (so the outline has no void there).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ezdxf.math import Vec3

from structiq.drawing import grids, slabs

MIN_TREADS = 5
DEPTH_RANGE = (150.0, 400.0)  # tread depth, mm
WIDTH_RANGE = (600.0, 2500.0)  # flight width, mm
PITCH_TOL = 3.0  # mm
PLAN_MARGIN = 3000.0  # mm


@dataclass
class Flight:
    orientation: str  # "V": treads stacked along y; "H": stacked along x
    treads: int
    width: float
    depth: float
    bbox: tuple[float, float, float, float]


@dataclass
class Stair:
    plan: int
    block: str
    flights: list[Flight]
    footprint: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax
    bay: tuple[str, str] | None
    inside_slab: bool | None  # None = the plan has no slab outline


@dataclass
class StairResult:
    stairs: list[Stair]
    skewed_blocks: int = 0
    outside_plans: int = 0


RECT_TOL = 1.0  # mm: drawn rectangles are often off by a fraction of a millimetre


def _rect_of(points):
    """Axis-aligned rectangle from 4 points (corners may drift by RECT_TOL), else None."""
    xs = sorted(p[0] for p in points)
    ys = sorted(p[1] for p in points)
    for v in (xs, ys):
        if v[1] - v[0] > RECT_TOL or v[3] - v[2] > RECT_TOL or v[2] - v[1] <= RECT_TOL:
            return None
    return ((xs[0] + xs[1]) / 2, (ys[0] + ys[1]) / 2, (xs[2] + xs[3]) / 2, (ys[2] + ys[3]) / 2)


def _block_geometry(block):
    """Rect polylines (block coords, with layer) and all line/polyline points by layer."""
    rects, pts_by_layer = [], defaultdict(list)
    for e in block:
        t = e.dxftype()
        if t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            pts_by_layer[e.dxf.layer].extend(pts)
            if e.closed and len(pts) == 4 and (r := _rect_of(pts)):
                rects.append((*r, e.dxf.layer))
        elif t == "LINE":
            pts_by_layer[e.dxf.layer].extend(
                [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
            )
    return rects, pts_by_layer


def _detect_flights(rects):
    """rects: [(x0, y0, x1, y1, layer)] in WCS. Returns [(Flight, layers)]."""
    unique = {}
    for x0, y0, x1, y1, layer in rects:
        unique.setdefault((round(x0), round(y0), round(x1), round(y1)), (x0, y0, x1, y1, set()))[
            4
        ].add(layer)
    found = []
    for orient in ("V", "H"):
        groups = defaultdict(list)
        for x0, y0, x1, y1, layers in unique.values():
            w, h = x1 - x0, y1 - y0
            width, depth = (w, h) if orient == "V" else (h, w)
            if not (DEPTH_RANGE[0] <= depth <= DEPTH_RANGE[1] and WIDTH_RANGE[0] <= width <= WIDTH_RANGE[1]):
                continue
            key = (round(x0) if orient == "V" else round(y0), round(width), round(depth))
            groups[key].append((x0, y0, x1, y1, layers))
        for (_, width, depth), items in groups.items():
            idx = 1 if orient == "V" else 0
            items.sort(key=lambda r: r[idx])
            run = [items[0]]
            for item in items[1:] + [None]:
                if item is not None and abs(item[idx] - run[-1][idx] - depth) <= PITCH_TOL:
                    run.append(item)
                    continue
                if len(run) >= MIN_TREADS:
                    bb = (
                        min(r[0] for r in run),
                        min(r[1] for r in run),
                        max(r[2] for r in run),
                        max(r[3] for r in run),
                    )
                    layers = set().union(*(r[4] for r in run))
                    found.append((Flight(orient, len(run), float(width), float(depth), bb), layers))
                run = [item] if item is not None else []
    return found


def extract_stairs(doc, grid_result: grids.GridResult, slab_result: slabs.SlabResult | None = None):
    msp = doc.modelspace()
    result = StairResult([])
    cache: dict[str, tuple] = {}
    for e in msp.query("INSERT"):
        name = e.dxf.name
        if name not in cache:
            cache[name] = _block_geometry(doc.blocks.get(name))
        rects, pts_by_layer = cache[name]
        if len(rects) < MIN_TREADS:
            continue
        if abs(e.dxf.rotation) % 90 > 1.0 and 90 - abs(e.dxf.rotation) % 90 > 1.0:
            result.skewed_blocks += 1
            continue
        m = e.matrix44()

        def to_wcs(x, y, m=m):
            p = m.transform(Vec3(x, y, 0))
            return p.x, p.y

        wcs = []
        for x0, y0, x1, y1, layer in rects:
            a, b = to_wcs(x0, y0), to_wcs(x1, y1)
            wcs.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), layer))
        detected = _detect_flights(wcs)
        if not detected:
            continue
        flights = sorted((f for f, _ in detected), key=lambda f: (f.bbox[0], f.bbox[1]))
        layers = set().union(*(ls for _, ls in detected))
        xs = [f.bbox[0] for f in flights] + [f.bbox[2] for f in flights]
        ys = [f.bbox[1] for f in flights] + [f.bbox[3] for f in flights]
        for layer in layers:
            for px, py in pts_by_layer.get(layer, []):
                wx, wy = to_wcs(px, py)
                xs.append(wx)
                ys.append(wy)
        foot = (min(xs), min(ys), max(xs), max(ys))
        cx, cy = (foot[0] + foot[2]) / 2, (foot[1] + foot[3]) / 2
        plan = next(
            (
                c
                for c in grid_result.clusters
                if c.bbox[0] - PLAN_MARGIN <= cx <= c.bbox[2] + PLAN_MARGIN
                and c.bbox[1] - PLAN_MARGIN <= cy <= c.bbox[3] + PLAN_MARGIN
            ),
            None,
        )
        if plan is None:
            result.outside_plans += 1
            continue
        inside = None
        if slab_result is not None:
            outline = next((s for s in slab_result.slabs if s.plan == plan.index and s.closed), None)
            if outline is not None:
                inside = slabs.point_in_polygon(cx, cy, outline.points)
        result.stairs.append(
            Stair(plan.index, name, flights, foot, grids.grid_bay(plan, cx, cy), inside)
        )

    result.stairs.sort(key=lambda s: (s.plan, s.footprint[0], s.footprint[1]))
    return result


def format_stairs_report(result: StairResult) -> str:
    out = ["STAIRS (detected from stacked tread rectangles; confirm against the drawing)"]
    for s in result.stairs:
        w, h = s.footprint[2] - s.footprint[0], s.footprint[3] - s.footprint[1]
        bay = f"bay {s.bay[0]} / {s.bay[1]}" if s.bay else "outside the grid bays"
        out.append(f"\nPlan {s.plan}: {len(s.flights)} flight(s), footprint {w:.0f} x {h:.0f} mm, {bay}")
        for i, f in enumerate(s.flights, 1):
            out.append(
                f"  flight {i}: {f.treads} treads, {f.depth:.0f} mm deep, {f.width:.0f} mm wide, "
                f"runs along {'y' if f.orientation == 'V' else 'x'}"
            )
        if s.inside_slab is None:
            out.append("  Slab: this plan has no slab outline to compare with.")
        elif s.inside_slab:
            out.append("  ! Stair centre is inside the slab outline: no void is drawn. Confirm the opening.")
        else:
            out.append("  Stair centre is outside the slab outline.")
    if not result.stairs:
        out.append("\nNo stairs detected.")
    if result.skewed_blocks:
        out.append(f"\n! {result.skewed_blocks} block(s) rotated off 90 degrees were skipped.")
    if result.outside_plans:
        out.append(f"\nStair-like blocks outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def add_stairs(doc, result: StairResult, text_height=None) -> None:
    """Add flights and footprints on S-STAIR, labels on S-STAIR-TXT.

    ``text_height(plan)`` gives the label height (Arial, STIQ-TEXT); default 250 mm.
    """
    for name, color in (("S-STAIR", 150), ("S-STAIR-TXT", 2)):
        if name not in doc.layers:
            doc.layers.add(name, color=color)
    msp = doc.modelspace()
    for s in result.stairs:
        x0, y0, x1, y1 = s.footprint
        msp.add_lwpolyline(
            [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "S-STAIR"}
        )
        for f in s.flights:
            a, b, c, d = f.bbox
            msp.add_lwpolyline(
                [(a, b), (c, b), (c, d), (a, d)], close=True, dxfattribs={"layer": "S-STAIR"}
            )
        msp.add_text(
            f"STAIR {len(s.flights)}F x {s.flights[0].treads}T",
            height=text_height(s.plan) if text_height else 250,
            dxfattribs={"layer": "S-STAIR-TXT", "insert": (x0, y1 + 150), "style": "STIQ-TEXT"},
        )
