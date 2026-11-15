"""Detect lift shafts and their RC core walls.

In the test drawing a lift is one block that holds the lift car symbol (a nested
insert whose geometry sits on an ELEVATOR layer) and the core wall outline. The
architect draws the core on *brick* wall layers, so the wall layer says nothing
about concrete: the lift itself is what marks it as an RC core.

* **Lift**: an INSERT whose block, at any nesting depth up to ``MAX_DEPTH``, holds
  entities on a layer matching ``LIFT_LAYER_PATTERN``.
* **Core wall**: the smallest closed polyline with at least 8 vertices on a wall
  layer in that block, taken as the wall *body* (the larger outline just outside it
  is the finishes). The clear shaft is the box formed by the inner corners of that
  polygon; the wall thickness is the gap between the two.

The core wall is drawn as an RC wall (S-WALL), the clear shaft as an opening
(S-OPEN) labelled LIFT. Whether a slab void is drawn at the shaft is not guessed:
the report says if the shaft centre lies inside the slab outline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ezdxf.math import Vec3

from structiq.drawing import grids, slabs, template

LIFT_LAYER_PATTERN = r"ELEVATOR|LIFT"
WALL_LAYER_PATTERN = r"WALL"
MAX_DEPTH = 3
MIN_CORE_VERTICES = 8
PLAN_MARGIN = 3000.0  # mm
EDGE_TOL = 1.0  # mm


@dataclass
class Lift:
    plan: int
    block: str
    core: list[tuple[float, float]]  # RC core wall outline (wall body)
    outer: tuple[float, float, float, float]  # bounding box of the core
    cavity: tuple[float, float, float, float] | None  # clear shaft
    thickness: float | None  # core wall thickness
    near_ref: str  # nearest grid intersection, e.g. "A3"
    bay: tuple[str, str] | None
    inside_slab: bool | None  # None = the plan has no slab outline
    doors: list[tuple[float, float, float, float]] = field(default_factory=list)  # gaps in the core


@dataclass
class LiftResult:
    lifts: list[Lift]
    outside_plans: int = 0
    without_core: int = 0  # lift cars found without a recognisable core wall outline


def _has_lift_layer(doc, block, rx, depth=0) -> bool:
    for e in block:
        if rx.search(e.dxf.layer):
            return True
        if e.dxftype() == "INSERT" and depth < MAX_DEPTH:
            inner = doc.blocks.get(e.dxf.name)
            if inner is not None and _has_lift_layer(doc, inner, rx, depth + 1):
                return True
    return False


def _cavity(points):
    """Clear shaft box and wall thickness from an orthogonal core outline, else (None, None)."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    inner = [
        p
        for p in points
        if abs(p[0] - x0) > EDGE_TOL
        and abs(p[0] - x1) > EDGE_TOL
        and abs(p[1] - y0) > EDGE_TOL
        and abs(p[1] - y1) > EDGE_TOL
    ]
    if len(inner) < 3:
        return None, None
    cx0, cx1 = min(p[0] for p in inner), max(p[0] for p in inner)
    cy0, cy1 = min(p[1] for p in inner), max(p[1] for p in inner)
    gaps = sorted([cx0 - x0, x1 - cx1, cy0 - y0, y1 - cy1])
    thickness = (gaps[1] + gaps[2]) / 2  # median of the four sides
    return (cx0, cy0, cx1, cy1), thickness


def _doors(points):
    """Gaps in the core wall: the box between each pair of jamb edges.

    A jamb edge joins a vertex on the outline's outer box to an inner vertex. In outline
    order a gap is a "boundary -> inner" edge followed later by an "inner -> boundary"
    edge; the four points of such a pair bound the gap.
    """
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    def on_outer(p):
        return any(abs(p[0] - v) <= EDGE_TOL for v in (x0, x1)) or any(
            abs(p[1] - v) <= EDGE_TOL for v in (y0, y1)
        )

    n = len(points)
    flags = [on_outer(p) for p in points]
    doors = []
    if all(flags) or not any(flags):
        return doors
    for i in range(n):
        if flags[i] and not flags[(i + 1) % n]:  # boundary -> inner: a jamb starts a gap
            j = (i + 1) % n
            while not flags[(j + 1) % n]:  # walk the run of inner vertices to its last one
                j = (j + 1) % n
            pts = [points[i], points[(i + 1) % n], points[j], points[(j + 1) % n]]
            gx, gy = [p[0] for p in pts], [p[1] for p in pts]
            doors.append((min(gx), min(gy), max(gx), max(gy)))
    return doors


def extract_lifts(
    doc,
    grid_result: grids.GridResult,
    slab_result: slabs.SlabResult | None = None,
    lift_layer_pattern: str | None = None,
) -> LiftResult:
    lift_re = re.compile(lift_layer_pattern or LIFT_LAYER_PATTERN, re.I)
    wall_re = re.compile(WALL_LAYER_PATTERN, re.I)
    result = LiftResult([])
    is_lift: dict[str, bool] = {}
    for e in doc.modelspace().query("INSERT"):
        name = e.dxf.name
        block = doc.blocks.get(name)
        if name not in is_lift:
            is_lift[name] = block is not None and _has_lift_layer(doc, block, lift_re)
        if not is_lift[name]:
            continue

        m = e.matrix44()
        candidates = []
        for x in block:
            if (
                x.dxftype() == "LWPOLYLINE"
                and x.closed
                and len(x) >= MIN_CORE_VERTICES
                and wall_re.search(x.dxf.layer)
            ):
                pts = []
                for p in x.get_points("xy"):
                    q = m.transform(Vec3(p[0], p[1], 0))
                    pts.append((q.x, q.y))
                area = slabs._shoelace(pts)
                candidates.append((area, pts))
        if not candidates:
            result.without_core += 1
            continue
        _, core = min(candidates, key=lambda c: c[0])
        xs, ys = [p[0] for p in core], [p[1] for p in core]
        outer = (min(xs), min(ys), max(xs), max(ys))
        cavity, thickness = _cavity(core)

        cx, cy = ((outer[0] + outer[2]) / 2, (outer[1] + outer[3]) / 2)
        if cavity:
            cx, cy = (cavity[0] + cavity[2]) / 2, (cavity[1] + cavity[3]) / 2
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
            slab = next((s for s in slab_result.slabs if s.plan == plan.index and s.closed), None)
            if slab is not None:
                inside = slabs.point_in_polygon(cx, cy, slab.points)
        v = min(plan.vertical, key=lambda ln: abs(ln.position - cx), default=None)
        h = min(plan.horizontal, key=lambda ln: abs(ln.position - cy), default=None)
        ref = f"{(v.label or '?') if v else '?'}{(h.label or '?') if h else '?'}"
        result.lifts.append(
            Lift(
                plan.index,
                name,
                core,
                outer,
                cavity,
                thickness,
                ref,
                grids.grid_bay(plan, cx, cy),
                inside,
                doors=_doors(core),
            )
        )
    result.lifts.sort(key=lambda lift: (lift.plan, lift.outer[0], lift.outer[1]))
    return result


def format_lifts_report(result: LiftResult) -> str:
    out = [
        "LIFTS (lift car symbol found; the core wall is drawn as an RC wall. "
        "Confirm against the drawing)"
    ]
    for lift in result.lifts:
        w, h = lift.outer[2] - lift.outer[0], lift.outer[3] - lift.outer[1]
        bay = f"bay {lift.bay[0]} / {lift.bay[1]}" if lift.bay else "outside the grid bays"
        out.append(f"\nPlan {lift.plan}: lift core at {lift.near_ref} ({bay}), outer {w:.0f} x {h:.0f} mm")
        if lift.cavity:
            cw, ch = lift.cavity[2] - lift.cavity[0], lift.cavity[3] - lift.cavity[1]
            out.append(
                f"  core wall {lift.thickness:.0f} mm thick; clear shaft {cw:.0f} x {ch:.0f} mm "
                f"({cw * ch / 1e6:.2f} m2)"
            )
        else:
            out.append("  ! core outline is not a simple box: thickness and clear shaft not computed")
        for door in lift.doors:
            width = max(door[2] - door[0], door[3] - door[1])
            out.append(f"  door opening {width:.0f} mm wide in the core wall (drawn with an X)")
        if lift.inside_slab is None:
            out.append("  Slab: this plan has no slab outline to compare with.")
        elif lift.inside_slab:
            out.append("  ! Shaft is inside the slab outline: no void is drawn. Confirm the opening.")
        else:
            out.append("  Shaft is outside the slab outline.")
    if not result.lifts:
        out.append("\nNo lift detected (no block with an ELEVATOR/LIFT layer inside a plan). Confirm.")
    else:
        out.append(
            "\nNote: the core is taken from the wall body outline in the lift block; the larger "
            "outline just outside it (finishes) is ignored."
        )
    if result.without_core:
        out.append(f"\n! {result.without_core} lift block(s) have no core wall outline (not drawn).")
    if result.outside_plans:
        out.append(f"\nLift blocks outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def add_lifts(doc, result: LiftResult, text_height=None) -> None:
    """Draw lift cores as in the sample structural drawing.

    Core wall outline on S-WALL with a solid grey fill on S-WALL-HATCH; the clear shaft on
    S-OPEN with a dashed green X (S-OPEN-X); each door gap in the core also gets an X;
    label LIFT on S-OPEN-TXT.
    """
    template.define_styles(doc)
    msp = doc.modelspace()

    def cross(x0, y0, x1, y1):
        msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "S-OPEN-X"})
        msp.add_line((x0, y1), (x1, y0), dxfattribs={"layer": "S-OPEN-X"})

    for lift in result.lifts:
        msp.add_lwpolyline(lift.core, close=True, dxfattribs={"layer": "S-WALL"})
        hatch = msp.add_hatch(color=256, dxfattribs={"layer": "S-WALL-HATCH"})
        hatch.paths.add_polyline_path(lift.core, is_closed=True)
        for door in lift.doors:
            cross(*door)
        if lift.cavity:
            x0, y0, x1, y1 = lift.cavity
            msp.add_lwpolyline(
                [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "S-OPEN"}
            )
            cross(x0, y0, x1, y1)
            msp.add_text(
                "LIFT",
                height=text_height(lift.plan) if text_height else 250,
                dxfattribs={
                    "layer": "S-OPEN-TXT",
                    "insert": ((x0 + x1) / 2, (y0 + y1) / 2),
                    "style": "STIQ-TEXT",
                },
            )
