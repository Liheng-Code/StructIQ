"""Full structural layout from an architect DXF: grid, columns, walls, slabs.

Writes one DXF with all structural layers plus a DRAFT text report.

Usage::

    python -m structiq.drawing.layout drawing.dxf [layout-output.dxf] [source name]
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path

import ezdxf

from structiq.drawing import columns, grids, slabs, walls


@dataclass
class Layout:
    grid: grids.GridResult
    columns: columns.ColumnResult
    walls: walls.WallResult
    slabs: slabs.SlabResult


def extract_layout(doc) -> Layout:
    g = grids.extract_grids(doc)
    return Layout(
        g,
        columns.extract_columns(doc, g),
        walls.extract_walls(doc, g),
        slabs.extract_slabs(doc, g),
    )


def format_layout_report(layout: Layout, source: str | None = None) -> str:
    return "\n\n".join(
        [
            grids.format_report(layout.grid, source=source),
            columns.format_columns_report(layout.columns),
            walls.format_walls_report(layout.walls),
            slabs.format_slabs_report(layout.slabs, layout.grid),
        ]
    )


def write_layout(layout: Layout, path: str | Path) -> Path:
    doc = grids.build_grid_doc(layout.grid)
    columns.add_columns(doc, layout.columns)
    walls.add_walls(doc, layout.walls)
    slabs.add_slabs(doc, layout.slabs)
    out = Path(path)
    doc.saveas(out)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)  # ezdxf logs a line per unsupported object copy
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2, 3):
        print(
            "Usage: python -m structiq.drawing.layout <drawing.dxf> "
            "[layout-output.dxf] [source name for the report]"
        )
        return 2
    layout = extract_layout(ezdxf.readfile(args[0]))
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
