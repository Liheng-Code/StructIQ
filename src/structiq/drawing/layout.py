"""Full structural layout from an architect DXF.

Grid, columns, walls, slabs, openings (MEP shafts) and stairs in one DXF on
structural layers, plus a DRAFT text report. When sheet fields are given, each plan
is also placed on its own A3 sheet from the StructIQ template (title block filled,
viewport at a fitted scale, grid labels drawn as scaled bubbles).

Usage::

    python -m structiq.drawing.layout drawing.dxf [layout-output.dxf] [source name]
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf import zoom

from structiq.drawing import columns, grids, openings, slabs, stairs, template, walls

EXTENT_MARGIN = 2000.0  # mm around a plan: room for the grid bubbles beyond the line ends


@dataclass
class Layout:
    grid: grids.GridResult
    columns: columns.ColumnResult
    walls: walls.WallResult
    slabs: slabs.SlabResult
    openings: openings.OpeningResult
    stairs: stairs.StairResult


@dataclass
class PlanSheet:
    plan: int
    name: str  # layout (tab) name, e.g. "A3-PLAN-1"
    extent: tuple[float, float, float, float]  # model-space box shown on the sheet
    scale: int  # viewport scale 1:scale

    @property
    def size_m(self) -> tuple[float, float]:
        return (self.extent[2] - self.extent[0]) / 1000, (self.extent[3] - self.extent[1]) / 1000

    @property
    def centre(self) -> tuple[float, float]:
        return (self.extent[0] + self.extent[2]) / 2, (self.extent[1] + self.extent[3]) / 2


def extract_layout(doc, rc_layer_pattern: str | None = None) -> Layout:
    g = grids.extract_grids(doc)
    cols = columns.extract_columns(doc, g)
    wls = walls.extract_walls(doc, g, rc_layer_pattern)
    slb = slabs.extract_slabs(doc, g)
    return Layout(
        g,
        cols,
        wls,
        slb,
        openings.extract_openings(doc, g, wls, cols, slb),
        stairs.extract_stairs(doc, g, slb),
    )


def plan_sheets(layout: Layout) -> list[PlanSheet]:
    """One A3 sheet per plan: extent of everything drawn for it, plus a fitted scale."""
    sheets = []
    for c in layout.grid.clusters:
        x0, y0, x1, y1 = c.bbox
        boxes = [s.bbox for s in layout.slabs.slabs if s.plan == c.index]
        boxes += [s.footprint for s in layout.stairs.stairs if s.plan == c.index]
        boxes += [o.rect for o in layout.openings.openings if o.plan == c.index and o.rect]
        for bx0, by0, bx1, by1 in boxes:
            x0, y0, x1, y1 = min(x0, bx0), min(y0, by0), max(x1, bx1), max(y1, by1)
        m = EXTENT_MARGIN
        extent = (x0 - m, y0 - m, x1 + m, y1 + m)
        scale = template.fit_scale(extent[2] - extent[0], extent[3] - extent[1])
        sheets.append(PlanSheet(c.index, f"A3-PLAN-{c.index}", extent, scale))
    return sheets


def format_sheets_report(sheets: list[PlanSheet]) -> str:
    out = [
        "SHEETS (one A3 sheet per plan; plan numbers follow the order found, bottom to top "
        "then left to right, and are not floor levels)"
    ]
    for s in sheets:
        w, h = s.size_m
        out.append(f"  {s.name}: plan {s.plan}, scale 1:{s.scale}, area shown {w:.1f} x {h:.1f} m")
    out.append(
        "  Title block: stage DRAFT FOR REVIEW; drawing numbers and client are left blank "
        "for the engineer."
    )
    return "\n".join(out)


def format_layout_report(
    layout: Layout,
    source: str | None = None,
    brain_version: str | None = None,
    sheets: list[PlanSheet] | None = None,
) -> str:
    parts = [
        grids.format_report(layout.grid, source=source),
        columns.format_columns_report(layout.columns),
        walls.format_walls_report(layout.walls),
        slabs.format_slabs_report(layout.slabs, layout.grid),
        openings.format_openings_report(layout.openings),
        stairs.format_stairs_report(layout.stairs),
    ]
    if sheets:
        parts.append(format_sheets_report(sheets))
    text = "\n\n".join(parts)
    if brain_version:
        first, rest = text.split("\n", 1)
        text = f"{first}\nCore Brain version: {brain_version}\n{rest}"
    return text


def _add_bubbles(doc, layout: Layout, sheets: list[PlanSheet]) -> None:
    """Grid labels as STIQ-GRID-BUBBLE blocks scaled to print at 5.0 mm on each sheet."""
    msp = doc.modelspace()
    for sheet in sheets:
        s = sheet.scale
        cluster = next(c for c in layout.grid.clusters if c.index == sheet.plan)
        places = [
            ((ln.position, ln.end + 3.0 * s), ln.label) for ln in cluster.vertical  # top end
        ] + [
            ((ln.start - 3.0 * s, ln.position), ln.label) for ln in cluster.horizontal  # left end
        ]
        for pos, label in places:
            if not label:
                continue
            ref = msp.add_blockref(
                "STIQ-GRID-BUBBLE",
                pos,
                dxfattribs={"xscale": s, "yscale": s, "zscale": s, "layer": "S-GRID-BUBBLE"},
            )
            ref.add_auto_attribs({"GRID": label})


def write_layout(
    layout: Layout,
    path: str | Path,
    sheet_fields: dict[str, str] | None = None,
    sheets: list[PlanSheet] | None = None,
) -> Path:
    """Write the layout DXF. With ``sheet_fields`` each plan also gets an A3 sheet."""
    with_sheets = sheet_fields is not None
    doc = grids.build_grid_doc(layout.grid, labels="none" if with_sheets else "text")
    columns.add_columns(doc, layout.columns)
    walls.add_walls(doc, layout.walls)
    slabs.add_slabs(doc, layout.slabs)
    openings.add_openings(doc, layout.openings)
    stairs.add_stairs(doc, layout.stairs)
    if with_sheets:
        sheets = sheets if sheets is not None else plan_sheets(layout)
        template.add_sheet_blocks(doc)
        _add_bubbles(doc, layout, sheets)
        for sheet in sheets:
            fields = dict(sheet_fields)
            fields["DRAWING_NAME"] = f"STRUCTURAL LAYOUT PLAN {sheet.plan}"
            fields["SCALE"] = f"1 : {sheet.scale}"
            template.add_sheet(
                doc,
                sheet.name,
                fields,
                sheet.centre,
                sheet.scale,
                extent=(sheet.extent[2] - sheet.extent[0], sheet.extent[3] - sheet.extent[1]),
            )
        if "Layout1" in doc.layouts:
            doc.layouts.delete("Layout1")
        if sheets:
            template.open_on_sheet(doc, sheets[0].name)  # open on the first sheet, not Model
    zoom.extents(doc.modelspace(), factor=1.05)  # Model tab: show all plans, not an empty area
    out = Path(path)
    doc.saveas(out)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)  # ezdxf logs a line per unsupported object copy
    parser = argparse.ArgumentParser(prog="python -m structiq.drawing.layout")
    parser.add_argument("drawing", help="converted DXF to read")
    parser.add_argument("output", nargs="?", help="layout DXF to write (a report is written beside it)")
    parser.add_argument("source", nargs="?", help="source drawing name for the report")
    parser.add_argument(
        "--rc-layers", help="regex for layer names that hold RC walls (default: STRUCT|RC|SHEAR...)"
    )
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    args = [a for a in (ns.drawing, ns.output, ns.source) if a is not None]
    layout = extract_layout(ezdxf.readfile(args[0]), ns.rc_layers)
    report = format_layout_report(layout, source=args[2] if len(args) == 3 else Path(args[0]).name)
    print(report)
    if len(args) >= 2:
        dxf = write_layout(layout, args[1])
        txt = dxf.with_name(f"{dxf.stem}-report.txt")
        txt.write_text(report + "\n", encoding="utf-8")
        print(f"\nWrote {dxf}\nWrote {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
