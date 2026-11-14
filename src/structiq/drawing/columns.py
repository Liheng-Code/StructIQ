"""Detect column positions in a DXF plan and relate them to the gridlines.

How columns are recognised (architect drawings rarely use a clean column layer):

* **Block columns**: an INSERT whose block holds only simple geometry (lines,
  polylines, hatch/solid) including a *solid* hatch, and whose bounding box is
  column-sized (``MIN_DIM``..``MAX_DIM`` mm, aspect ratio <= ``MAX_ASPECT``).
  Block names are ignored (they are meaningless in the test drawing).
* **Direct columns**: closed rectangular polylines or solid hatches placed
  directly on a layer whose name matches ``COLUMN_LAYER_PATTERN``.

Every column is related to the nearest gridlines of its plan and reported as
``on grid`` (centre within ``ON_GRID_TOL`` of both lines) or ``off grid`` with
its offsets. Nothing is guessed: unlabeled or off-grid items are flagged.

Usage::

    python -m structiq.drawing.columns drawing.dxf [layout-output.dxf] [source name]
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import bbox

from structiq.drawing import grids, template

COLUMN_LAYER_PATTERN = r"COL"
MIN_DIM = 150.0  # mm
MAX_DIM = 1500.0  # mm
MAX_ASPECT = 6.0
ON_GRID_TOL = 150.0  # mm
PLAN_MARGIN = 3000.0  # mm around a plan's gridlines that still belongs to the plan
_SIMPLE_TYPES = {"HATCH", "SOLID", "LWPOLYLINE", "POLYLINE", "LINE"}


@dataclass
class Column:
    x: float
    y: float
    width: float
    height: float
    layer: str
    block: str | None
    plan: int
    grid_ref: str  # e.g. "C2"
    dx: float  # offset of centre from the nearest vertical gridline
    dy: float  # offset of centre from the nearest horizontal gridline
    on_grid: bool


@dataclass
class ColumnResult:
    columns: list[Column]
    missing: dict[int, list[str]]  # plan index -> grid intersections with no column
    outside_plans: int


def _is_solid_hatch(e) -> bool:
    return e.dxftype() == "SOLID" or (e.dxftype() == "HATCH" and e.dxf.solid_fill == 1)


def _column_block(block) -> bool:
    ents = list(block)
    if not 1 <= len(ents) <= 12:
        return False
    if not {e.dxftype() for e in ents} <= _SIMPLE_TYPES:
        return False
    return any(_is_solid_hatch(e) for e in ents)


def _size_ok(ext) -> bool:
    w, h = ext.size.x, ext.size.y
    if not (MIN_DIM <= w <= MAX_DIM and MIN_DIM <= h <= MAX_DIM):
        return False
    return max(w, h) / min(w, h) <= MAX_ASPECT


def _candidates(doc, layer_re):
    """Yield (entity, extents, block name or None) for column-like objects."""
    msp = doc.modelspace()
    block_ok: dict[str, bool] = {}
    for e in msp.query("INSERT"):
        name = e.dxf.name
        if name not in block_ok:
            block_ok[name] = _column_block(doc.blocks.get(name))
        if not block_ok[name]:
            continue
        ext = bbox.extents([e])
        if ext.has_data and _size_ok(ext):
            yield e, ext, name
    for e in msp:
        if not layer_re.search(e.dxf.layer):
            continue
        t = e.dxftype()
        direct = (t == "LWPOLYLINE" and e.closed and len(e) == 4) or (
            t == "HATCH" and e.dxf.solid_fill == 1
        )
        if not direct:
            continue
        ext = bbox.extents([e])
        if ext.has_data and _size_ok(ext):
            yield e, ext, None


def _ref(v: grids.GridLine, h: grids.GridLine) -> str:
    a, b = v.label or "?", h.label or "?"
    return f"{a}{b}" if not a.isdigit() or b.isdigit() else f"{b}{a}"


def extract_columns(doc, grid_result: grids.GridResult) -> ColumnResult:
    layer_re = re.compile(COLUMN_LAYER_PATTERN, re.I)
    columns: list[Column] = []
    outside = 0
    seen: set[tuple[int, int]] = set()
    for e, ext, name in _candidates(doc, layer_re):
        cx, cy = ext.center.x, ext.center.y
        key = (round(cx), round(cy))
        if key in seen:
            continue
        seen.add(key)
        plan = next(
            (
                c
                for c in grid_result.clusters
                if c.bbox[0] - PLAN_MARGIN <= cx <= c.bbox[2] + PLAN_MARGIN
                and c.bbox[1] - PLAN_MARGIN <= cy <= c.bbox[3] + PLAN_MARGIN
                and c.vertical
                and c.horizontal
            ),
            None,
        )
        if plan is None:
            outside += 1
            continue
        v = min(plan.vertical, key=lambda ln: abs(ln.position - cx))
        h = min(plan.horizontal, key=lambda ln: abs(ln.position - cy))
        dx, dy = cx - v.position, cy - h.position
        columns.append(
            Column(
                cx,
                cy,
                ext.size.x,
                ext.size.y,
                e.dxf.layer,
                name,
                plan.index,
                _ref(v, h),
                dx,
                dy,
                abs(dx) <= ON_GRID_TOL and abs(dy) <= ON_GRID_TOL,
            )
        )
    columns.sort(key=lambda c: (c.plan, c.y, c.x))

    missing: dict[int, list[str]] = {}
    for plan in grid_result.clusters:
        have = {c.grid_ref for c in columns if c.plan == plan.index and c.on_grid}
        missing[plan.index] = [
            _ref(v, h) for v in plan.vertical for h in plan.horizontal if _ref(v, h) not in have
        ]
    return ColumnResult(columns, missing, outside)


def format_columns_report(result: ColumnResult) -> str:
    out = ["COLUMNS (detected from block/hatch geometry; confirm against the drawing)"]
    for plan in sorted({c.plan for c in result.columns} | set(result.missing)):
        cols = [c for c in result.columns if c.plan == plan]
        on = [c for c in cols if c.on_grid]
        off = [c for c in cols if not c.on_grid]
        out.append(f"\nPlan {plan}: {len(cols)} columns ({len(on)} on grid, {len(off)} off grid)")
        for c in on:
            out.append(f"  {c.grid_ref:<4} {c.width:.0f} x {c.height:.0f}  [{c.block}]")
        for c in off:
            out.append(
                f"  ! off grid near {c.grid_ref}: offset ({c.dx:+.0f}, {c.dy:+.0f})"
                f"  {c.width:.0f} x {c.height:.0f}  [{c.block or c.layer}]"
            )
        if result.missing.get(plan):
            out.append(f"  Grid intersections with no column: {', '.join(result.missing[plan])}")
    if result.outside_plans:
        out.append(f"\nColumn-like objects outside any plan (not listed): {result.outside_plans}")
    return "\n".join(out)


def write_layout_dxf(
    grid_result: grids.GridResult,
    col_result: ColumnResult,
    path: str | Path,
) -> Path:
    """Write grid + columns on structural layers (S-GRID, S-GRID-TXT, S-COLS, S-COLS-TXT)."""
    doc = grids.build_grid_doc(grid_result)
    add_columns(doc, col_result)
    out = Path(path)
    doc.saveas(out)
    return out


def add_columns(doc, col_result: ColumnResult) -> None:
    """Add the S-COLS / S-COLS-TXT layers and column shapes to ``doc``."""
    template.define_styles(doc)  # no-op when the layers already exist
    msp = doc.modelspace()
    for c in col_result.columns:
        x0, x1 = c.x - c.width / 2, c.x + c.width / 2
        y0, y1 = c.y - c.height / 2, c.y + c.height / 2
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "S-COLS"})
        hatch = msp.add_hatch(color=256, dxfattribs={"layer": "S-COLS-HATCH"})
        hatch.paths.add_polyline_path(pts, is_closed=True)
        msp.add_text(
            c.grid_ref if c.on_grid else f"{c.grid_ref}?",
            height=200,
            dxfattribs={"layer": "S-COLS-TXT", "insert": (x1 + 100, y1 + 100)},
        )


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)  # ezdxf logs a line per unsupported object copy
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2, 3):
        print(
            "Usage: python -m structiq.drawing.columns <drawing.dxf> "
            "[layout-output.dxf] [source name for the report]"
        )
        return 2
    doc = ezdxf.readfile(args[0])
    g = grids.extract_grids(doc)
    c = extract_columns(doc, g)
    source = args[2] if len(args) == 3 else Path(args[0]).name
    report = grids.format_report(g, source=source) + "\n\n" + format_columns_report(c)
    print(report)
    if len(args) >= 2:
        dxf = write_layout_dxf(g, c, args[1])
        txt = dxf.with_name(f"{dxf.stem}-report.txt")
        txt.write_text(report + "\n", encoding="utf-8")
        print(f"\nWrote {dxf}\nWrote {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
