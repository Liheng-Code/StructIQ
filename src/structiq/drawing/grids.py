"""Extract structural gridlines (and their labels) from a DXF drawing.

Pipeline: collect orthogonal lines on grid layers -> group them into plans
(one cluster per drawn plan) -> attach grid labels found as block attributes
(e.g. block ``COLUNM AXIS`` with attribute ``AXIS`` = ``A``) -> report.

Only DXF is read (DWG is converted first, see ``convert.py``). Coordinates are
the drawing's own units (millimetres for the test drawing); nothing is rescaled.

Usage::

    python -m structiq.drawing.grids drawing.dxf [grid-layer-output.dxf]
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

DEFAULT_LAYER_PATTERN = r"GRID"  # matches GRID, N- GRID, A-GRID LINE, GRID-144...
DEFAULT_TAG_PATTERN = r"AXIS|GRID"  # attribute tags that carry a grid label
ORTHO_TOL = 1.0  # a line is orthogonal if its off-axis extent is below this
MERGE_TOL = 1.0  # lines closer than this are the same gridline
CLUSTER_MARGIN = 500.0  # lines this close belong to the same plan
LABEL_REACH = 4000.0  # max distance from a label to the end of its line
LABEL_ALIGN = 600.0  # max sideways offset of a label from its line


@dataclass
class GridLine:
    direction: str  # "V" = vertical (constant x), "H" = horizontal (constant y)
    position: float  # x for V, y for H
    start: float  # extent along the line (low end)
    end: float  # extent along the line (high end)
    layer: str
    labels: list[str] = field(default_factory=list)

    @property
    def label(self) -> str | None:
        return Counter(self.labels).most_common(1)[0][0] if self.labels else None


@dataclass
class GridCluster:
    index: int
    bbox: tuple[float, float, float, float]  # xmin, ymin, xmax, ymax
    vertical: list[GridLine]
    horizontal: list[GridLine]
    warnings: list[str] = field(default_factory=list)

    @staticmethod
    def spacings(lines: list[GridLine]) -> list[float]:
        pos = [ln.position for ln in lines]
        return [round(b - a, 1) for a, b in zip(pos, pos[1:])]


@dataclass
class GridResult:
    clusters: list[GridCluster]
    unmatched_labels: list[tuple[str, float, float]]


def _collect_lines(msp, layer_re) -> list[GridLine]:
    out: list[GridLine] = []
    for e in msp.query("LINE"):
        if not layer_re.search(e.dxf.layer):
            continue
        s, t = e.dxf.start, e.dxf.end
        if abs(s.x - t.x) <= ORTHO_TOL and abs(s.y - t.y) > ORTHO_TOL:
            out.append(GridLine("V", (s.x + t.x) / 2, min(s.y, t.y), max(s.y, t.y), e.dxf.layer))
        elif abs(s.y - t.y) <= ORTHO_TOL and abs(s.x - t.x) > ORTHO_TOL:
            out.append(GridLine("H", (s.y + t.y) / 2, min(s.x, t.x), max(s.x, t.x), e.dxf.layer))
    return out


def _bbox(line: GridLine) -> tuple[float, float, float, float]:
    if line.direction == "V":
        return (line.position, line.start, line.position, line.end)
    return (line.start, line.position, line.end, line.position)


def _touch(a, b, margin: float) -> bool:
    return not (
        a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1]
    )


def _cluster(lines: list[GridLine]) -> list[list[GridLine]]:
    parent = list(range(len(lines)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = [_bbox(ln) for ln in lines]
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            if _touch(boxes[i], boxes[j], CLUSTER_MARGIN):
                parent[find(i)] = find(j)
    groups: dict[int, list[GridLine]] = {}
    for i, ln in enumerate(lines):
        groups.setdefault(find(i), []).append(ln)
    return list(groups.values())


def _merge(lines: list[GridLine]) -> list[GridLine]:
    """Merge collinear duplicates (same direction and position within MERGE_TOL)."""
    merged: list[GridLine] = []
    for ln in sorted(lines, key=lambda x: (x.direction, x.position)):
        last = merged[-1] if merged else None
        if last and last.direction == ln.direction and abs(last.position - ln.position) <= MERGE_TOL:
            last.start, last.end = min(last.start, ln.start), max(last.end, ln.end)
        else:
            merged.append(GridLine(ln.direction, ln.position, ln.start, ln.end, ln.layer))
    return merged


def _collect_labels(msp, tag_re) -> list[tuple[str, float, float]]:
    out = []
    for ins in msp.query("INSERT"):
        for att in ins.attribs:
            text = att.dxf.text.strip()
            if text and tag_re.search(att.dxf.tag):
                p = att.dxf.insert
                out.append((text, p.x, p.y))
                break
    return out


def _score(label, line: GridLine) -> float | None:
    """Distance score if the label sits at an end of the line, else None."""
    _, x, y = label
    across, along = (x, y) if line.direction == "V" else (y, x)
    side = abs(across - line.position)
    beyond = max(line.start - along, along - line.end, 0.0)
    if side > LABEL_ALIGN or beyond > LABEL_REACH:
        return None
    return side + beyond


def extract_grids(
    doc,
    layer_pattern: str = DEFAULT_LAYER_PATTERN,
    tag_pattern: str = DEFAULT_TAG_PATTERN,
) -> GridResult:
    msp = doc.modelspace()
    raw = _collect_lines(msp, re.compile(layer_pattern, re.I))
    clusters: list[GridCluster] = []
    for group in _cluster(raw):
        lines = _merge(group)
        v = sorted((ln for ln in lines if ln.direction == "V"), key=lambda x: x.position)
        h = sorted((ln for ln in lines if ln.direction == "H"), key=lambda x: x.position)
        xs = [ln.position for ln in v] + [ln.start for ln in h] + [ln.end for ln in h]
        ys = [ln.position for ln in h] + [ln.start for ln in v] + [ln.end for ln in v]
        clusters.append(GridCluster(0, (min(xs), min(ys), max(xs), max(ys)), v, h))
    clusters.sort(key=lambda c: (round(c.bbox[1], -3), c.bbox[0]))
    for i, c in enumerate(clusters, 1):
        c.index = i

    labels = _collect_labels(msp, re.compile(tag_pattern, re.I))
    all_lines = [(c, ln) for c in clusters for ln in c.vertical + c.horizontal]
    unmatched = []
    for lab in labels:
        best = None
        for _, ln in all_lines:
            s = _score(lab, ln)
            if s is not None and (best is None or s < best[0]):
                best = (s, ln)
        if best:
            best[1].labels.append(lab[0])
        else:
            unmatched.append(lab)

    for c in clusters:
        for ln in c.vertical + c.horizontal:
            name = f"{'vertical' if ln.direction == 'V' else 'horizontal'} line at {ln.position:.0f}"
            if not ln.labels:
                c.warnings.append(f"{name}: no label found")
            elif len(set(ln.labels)) > 1:
                c.warnings.append(f"{name}: conflicting labels {sorted(set(ln.labels))}")
        for lines in (c.vertical, c.horizontal):
            names = [ln.label for ln in lines if ln.label]
            for dup in {n for n in names if names.count(n) > 1}:
                c.warnings.append(f"label {dup!r} used by more than one line")
    return GridResult(clusters, unmatched)


def format_report(result: GridResult, unit: str = "mm", source: str | None = None) -> str:
    out = ["DRAFT: generated by StructIQ, for engineer review. Not approved."]
    if source:
        out.append(f"Source drawing: {source}")
    out.append(f"Plans with gridlines found: {len(result.clusters)}")
    for c in result.clusters:
        out.append(
            f"\nPlan {c.index}: {len(c.vertical)} vertical x {len(c.horizontal)} horizontal"
            f"  (x {c.bbox[0]:.0f}..{c.bbox[2]:.0f}, y {c.bbox[1]:.0f}..{c.bbox[3]:.0f})"
        )
        for title, lines in (("Vertical  ", c.vertical), ("Horizontal", c.horizontal)):
            items = ", ".join(f"{ln.label or '?'}@{ln.position:.0f}" for ln in lines)
            out.append(f"  {title}: {items}")
            out.append(f"  {'':10}  spacing ({unit}): {c.spacings(lines)}")
        for w in c.warnings:
            out.append(f"  ! {w}")
    if result.unmatched_labels:
        out.append(f"\nLabels not matched to any gridline: {len(result.unmatched_labels)}")
        for text, x, y in result.unmatched_labels[:20]:
            out.append(f"  {text!r} at ({x:.0f}, {y:.0f})")
    return "\n".join(out)


def write_grid_dxf(result: GridResult, path: str | Path, text_height: float = 350.0) -> Path:
    """Write a new DXF with only the structural grid (layers S-GRID, S-GRID-TXT)."""
    doc = ezdxf.new("R2018", setup=True)
    doc.units = 4  # millimetres
    doc.layers.add("S-GRID", color=1, linetype="CENTER")
    doc.layers.add("S-GRID-TXT", color=2)
    msp = doc.modelspace()
    for c in result.clusters:
        for ln in c.vertical + c.horizontal:
            if ln.direction == "V":
                a, b = (ln.position, ln.start), (ln.position, ln.end)
                tp = (ln.position, ln.end + text_height)
            else:
                a, b = (ln.start, ln.position), (ln.end, ln.position)
                tp = (ln.start - 2 * text_height, ln.position)
            msp.add_line(a, b, dxfattribs={"layer": "S-GRID"})
            if ln.label:
                msp.add_text(
                    ln.label, height=text_height, dxfattribs={"layer": "S-GRID-TXT", "insert": tp}
                )
    out = Path(path)
    doc.saveas(out)
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2, 3):
        print(
            "Usage: python -m structiq.drawing.grids <drawing.dxf> "
            "[grid-output.dxf] [source name for the report]"
        )
        return 2
    result = extract_grids(ezdxf.readfile(args[0]))
    report = format_report(result, source=args[2] if len(args) == 3 else Path(args[0]).name)
    print(report)
    if len(args) >= 2:
        dxf = write_grid_dxf(result, args[1])
        txt = dxf.with_name(f"{dxf.stem}-report.txt")
        txt.write_text(report + "\n", encoding="utf-8")
        print(f"\nWrote {dxf}\nWrote {txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
