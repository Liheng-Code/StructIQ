"""Detect MEP shafts and similar openings from their text labels.

The architect labels shafts with text (MEP, PLUMBING, SHAFT, DUCT, RISER, VOID);
the shaft boundary is not drawn as one shape. So for each label the enclosing
cell is found by casting four rays from the label to the nearest wall or column
(see ``walls.py`` / ``columns.py``). Only a cell closed on all four sides, with
every side at most ``MAX_RAY`` mm away, counts as bounded; otherwise the label is
reported alone with its position and no size. Labels that contain ROOM (for example
MEP ROOM) are listed as rooms, not as openings.

Whether the opening is drawn in the slab is not guessed: the report says if the
cell centre lies inside the slab outline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from structiq.drawing import columns, grids, slabs, template, walls

LABEL_PATTERN = r"\b(MEP|PLUMBING|SHAFT|DUCT|RISER|VOID)\b"
MAX_RAY = 8000.0  # mm: farthest wall a ray may hit
LARGE = 6000.0  # mm: a "shaft" bigger than this probably leaked through a wall gap
PLAN_MARGIN = 3000.0  # mm


@dataclass
class Opening:
    plan: int
    label: str
    kind: str  # "shaft" | "room"
    x: float  # label position
    y: float
    rect: tuple[float, float, float, float] | None  # xmin, ymin, xmax, ymax of the cell
    near_ref: str
    inside_slab: bool | None

    @property
    def bounded(self) -> bool:
        return self.rect is not None

    @property
    def size(self) -> tuple[float, float] | None:
        r = self.rect
        return (r[2] - r[0], r[3] - r[1]) if r else None

    @property
    def large(self) -> bool:
        s = self.size
        return bool(s and max(s) > LARGE)


@dataclass
class OpeningResult:
    openings: list[Opening]
    outside_plans: int = 0


def _enclose(px: float, py: float, boxes) -> tuple[float, float, float, float] | None:
    left = max((b[2] for b in boxes if b[1] <= py <= b[3] and b[2] <= px), default=None)
    right = min((b[0] for b in boxes if b[1] <= py <= b[3] and b[0] >= px), default=None)
    down = max((b[3] for b in boxes if b[0] <= px <= b[2] and b[3] <= py), default=None)
    up = min((b[1] for b in boxes if b[0] <= px <= b[2] and b[1] >= py), default=None)
    if None in (left, right, down, up):
        return None
    if min(px - left, right - px, py - down, up - py) < 0:
        return None
    if max(px - left, right - px, py - down, up - py) > MAX_RAY:
        return None
    return (left, down, right, up)


def extract_openings(
    doc,
    grid_result: grids.GridResult,
    wall_result: walls.WallResult,
    col_result: columns.ColumnResult,
    slab_result: slabs.SlabResult | None = None,
) -> OpeningResult:
    label_re = re.compile(LABEL_PATTERN, re.I)
    result = OpeningResult([])
    for e in doc.modelspace():
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue
        text = (e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()).strip()
        if not label_re.search(text):
            continue
        px, py = e.dxf.insert.x, e.dxf.insert.y
        plan = next(
            (
                c
                for c in grid_result.clusters
                if c.bbox[0] - PLAN_MARGIN <= px <= c.bbox[2] + PLAN_MARGIN
                and c.bbox[1] - PLAN_MARGIN <= py <= c.bbox[3] + PLAN_MARGIN
            ),
            None,
        )
        if plan is None:
            result.outside_plans += 1
            continue
        boxes = [(w.x0, w.y0, w.x1, w.y1) for w in wall_result.walls if w.plan == plan.index]
        boxes += [
            (c.x - c.width / 2, c.y - c.height / 2, c.x + c.width / 2, c.y + c.height / 2)
            for c in col_result.columns
            if c.plan == plan.index
        ]
        rect = _enclose(px, py, boxes)
        cx, cy = ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2) if rect else (px, py)
        inside = None
        if slab_result is not None:
            outline = next((s for s in slab_result.slabs if s.plan == plan.index and s.closed), None)
            if outline is not None:
                inside = slabs.point_in_polygon(cx, cy, outline.points)
        v = min(plan.vertical, key=lambda ln: abs(ln.position - cx), default=None)
        h = min(plan.horizontal, key=lambda ln: abs(ln.position - cy), default=None)
        ref = f"{(v.label or '?') if v else '?'}{(h.label or '?') if h else '?'}"
        result.openings.append(
            Opening(
                plan.index,
                " ".join(text.split()),
                "room" if re.search(r"ROOM", text, re.I) else "shaft",
                px,
                py,
                rect,
                ref,
                inside,
            )
        )
    result.openings.sort(key=lambda o: (o.plan, o.y, o.x))
    return result


def format_openings_report(result: OpeningResult) -> str:
    out = ["OPENINGS (MEP shafts found from text labels; confirm against the drawing)"]
    plans = sorted({o.plan for o in result.openings})
    for p in plans:
        out.append(f"\nPlan {p}:")
        in_plan = [o for o in result.openings if o.plan == p]
        cells = [tuple(round(v) for v in o.rect) for o in in_plan if o.rect]
        for o in in_plan:
            if o.bounded:
                w, h = o.size
                flags = []
                if cells.count(tuple(round(v) for v in o.rect)) > 1:
                    flags.append("shares its cell with another label: boundary probably wrong")
                if o.large:
                    flags.append("LARGE: the cell may have leaked through a wall gap")
                if o.kind == "shaft" and o.inside_slab:
                    flags.append("inside the slab outline, no void drawn: confirm the opening")
                note = ("  ! " + "; ".join(flags)) if flags else ""
                area = w * h / 1e6
                out.append(
                    f"  {o.kind:<5} {o.label!r}: {w:.0f} x {h:.0f} mm ({area:.2f} m2), near {o.near_ref}{note}"
                )
            else:
                out.append(
                    f"  {o.kind:<5} {o.label!r}: label only at ({o.x:.0f}, {o.y:.0f}), near "
                    f"{o.near_ref}; no closed wall boundary found, size unknown"
                )
    if not result.openings:
        out.append("\nNo MEP/shaft labels found.")
    if result.outside_plans:
        out.append(f"\nShaft labels outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def add_openings(doc, result: OpeningResult, text_height=None) -> None:
    """Bounded shaft cells on S-OPEN with a dashed green X (S-OPEN-X); rooms on S-OPEN-ROOM
    (no X, they are not openings); label-only on S-OPEN-CHECK.

    ``text_height(plan)`` gives the label height (Arial, STIQ-TEXT); default 150 mm.
    """
    template.define_styles(doc)
    msp = doc.modelspace()
    for o in result.openings:
        if o.rect:
            x0, y0, x1, y1 = o.rect
            layer = "S-OPEN" if o.kind == "shaft" else "S-OPEN-ROOM"
            msp.add_lwpolyline(
                [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer}
            )
            if o.kind == "shaft":
                msp.add_line((x0, y0), (x1, y1), dxfattribs={"layer": "S-OPEN-X"})
                msp.add_line((x0, y1), (x1, y0), dxfattribs={"layer": "S-OPEN-X"})
        else:
            msp.add_circle((o.x, o.y), 200, dxfattribs={"layer": "S-OPEN-CHECK"})
        msp.add_text(
            o.label,
            height=text_height(o.plan) if text_height else 150,
            dxfattribs={"layer": "S-OPEN-TXT", "insert": (o.x, o.y), "style": "STIQ-TEXT"},
        )
