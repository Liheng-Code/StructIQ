"""Split a combined DXF into one file per drawing (floor plan, section, elevation...).

The manual way is: copy the file, delete everything that is not the drawing, purge, save. This does the same:

1. ``find_views`` finds the separate drawings in model space: entities that lie close together form a view; very large entities
   (long stray lines) are ignored so they do not join everything into one view. Each view gets its title from the drawing's own text.
2. ``export_window`` builds a new clean DXF from the entities fully inside one view's window, with only the blocks, layers and
   linetypes they use. Entities that cross the window edge are dropped and counted, never moved.

The source is never modified. A DWG is converted to DXF first (``structiq.drawing.convert``). Output is DXF; use
``structiq.tools.autocad`` to turn it into a DWG with AutoCAD's own PURGE.

    python -m structiq.drawing.split scan "<file.dwg|.dxf>" [--preview views.png]
    python -m structiq.drawing.split export "<file.dwg|.dxf>" --view 3 --out "<file.dxf>"
"""

from __future__ import annotations

import argparse
import collections
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox, zoom
from ezdxf.addons.importer import Importer

Box = tuple[float, float, float, float]  # x0, y0, x1, y1

TITLE_RE = re.compile(r"floor plan|\bplan\b|section\s+[a-z]\s*-\s*[a-z]|elevation|layout|roof|terrace", re.I)
KEEP_BLOCKS = ("*Model_Space", "*Paper_Space", "_")  # "_" = the arrowhead blocks that dimension styles point to
KEEP_LINETYPES = {"CONTINUOUS", "BYLAYER", "BYBLOCK"}
KEEP_LAYERS = {"0", "Defpoints"}


@dataclass
class View:
    id: int
    box: Box
    count: int
    labels: list[str] = field(default_factory=list)

    @property
    def title(self) -> str | None:
        return self.labels[0] if self.labels else None

    @property
    def size(self) -> tuple[float, float]:
        return self.box[2] - self.box[0], self.box[3] - self.box[1]


@dataclass
class SplitReport:
    window: Box
    kept: int = 0
    dropped_outside: int = 0
    dropped_crossing: int = 0
    dropped_unmeasurable: int = 0
    blocks_removed: int = 0
    layers_removed: int = 0
    linetypes_removed: int = 0
    size_before: int = 0
    size_after: int = 0

    def summary(self) -> str:
        return (
            f"kept {self.kept} entities; dropped {self.dropped_outside} outside, {self.dropped_crossing} crossing the edge, "
            f"{self.dropped_unmeasurable} without a size; purged {self.blocks_removed} blocks, {self.layers_removed} layers, "
            f"{self.linetypes_removed} linetypes; file {self.size_before // 1024} KB -> {self.size_after // 1024} KB"
        )


# ------------------------------------------------------------------ reading
def _plain(e: Any) -> str:
    try:
        text = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
    except Exception:  # noqa: BLE001  (a damaged text entity is skipped, not fatal)
        return ""
    return " ".join(str(text).split())


def _boxes(msp: Any) -> list[tuple[Box, Any]]:
    out: list[tuple[Box, Any]] = []
    for e in msp:
        b = bbox.extents([e], fast=True)
        if b.has_data:
            out.append(((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y), e))
    return out


def _robust_span(boxes: list[tuple[Box, Any]]) -> float:
    """Span of the entity centres between the 1st and 99th percentile, so a few stray objects do not count."""
    xs = sorted((b[0] + b[2]) / 2 for b, _ in boxes)
    ys = sorted((b[1] + b[3]) / 2 for b, _ in boxes)
    if not xs:
        return 0.0
    lo, hi = int(len(xs) * 0.01), max(int(len(xs) * 0.99) - 1, 0)
    return float(max(xs[hi] - xs[lo], ys[hi] - ys[lo]))


def find_views(
    doc: Any,
    *,
    gap: float | None = None,
    max_entity: float | None = None,
    min_entities: int = 40,
    within: Box | None = None,
) -> list[View]:
    """The separate drawings in model space, ordered top to bottom then left to right (ids start at 1).

    ``within`` looks only inside one box (for example one sheet that holds several drawings)."""
    msp = doc.modelspace()
    boxes = _boxes(msp)
    if within is not None:
        wx0, wy0, wx1, wy1 = within
        boxes = [(b, e) for b, e in boxes if b[0] >= wx0 and b[1] >= wy0 and b[2] <= wx1 and b[3] <= wy1]
        span = float(max(wx1 - wx0, wy1 - wy0))
    else:
        span = _robust_span(boxes)
    if span <= 0:
        return []
    max_entity = max_entity if max_entity is not None else (0.5 if within is not None else 0.10) * span
    gap = gap if gap is not None else 0.002 * span
    items = [(b, e) for b, e in boxes if max(b[2] - b[0], b[3] - b[1]) <= max_entity]

    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = max(gap, span / 2000)
    grid: dict[tuple[int, int], list[int]] = collections.defaultdict(list)
    for i, (b, _) in enumerate(items):
        for cx in range(int((b[0] - gap) // cell), int((b[2] + gap) // cell) + 1):
            for cy in range(int((b[1] - gap) // cell), int((b[3] + gap) // cell) + 1):
                grid[(cx, cy)].append(i)
    for members in grid.values():
        for a in members:
            ax0, ay0, ax1, ay1 = items[a][0]
            for c in members:
                if c <= a:
                    continue
                bx0, by0, bx1, by1 = items[c][0]
                if ax0 - gap <= bx1 and bx0 - gap <= ax1 and ay0 - gap <= by1 and by0 - gap <= ay1:
                    ra, rc = find(a), find(c)
                    if ra != rc:
                        parent[ra] = rc

    groups: dict[int, list[int]] = collections.defaultdict(list)
    for i in range(len(items)):
        groups[find(i)].append(i)

    raw: list[tuple[Box, int]] = []
    for idx in groups.values():
        if len(idx) < min_entities:
            continue
        box = (
            min(items[i][0][0] for i in idx),
            min(items[i][0][1] for i in idx),
            max(items[i][0][2] for i in idx),
            max(items[i][0][3] for i in idx),
        )
        raw.append((box, len(idx)))
    if raw:
        heights = sorted(r[0][3] - r[0][1] for r in raw)
        row_h = max(0.75 * heights[len(heights) // 2], 1.0)  # views whose centres are within a row height are in one row
        raw.sort(key=lambda r: (-round((r[0][1] + r[0][3]) / 2 / row_h), r[0][0]))

    texts = [
        (e.dxf.insert, float(e.dxf.char_height if e.dxftype() == "MTEXT" else e.dxf.height), _plain(e))
        for _, e in items
        if e.dxftype() in ("TEXT", "MTEXT")
    ]
    found_by_view: dict[int, list[tuple[float, str, float, float]]] = collections.defaultdict(list)
    for p, h, text in texts:
        if not text or len(text) > 60 or not TITLE_RE.search(text):
            continue
        # the view the text lies in, else the nearest one when it sits just outside (a title under a drawing)
        best, best_d = -1, None
        for n, (box, _) in enumerate(raw):
            dx = max(box[0] - p.x, 0.0, p.x - box[2])
            dy = max(box[1] - p.y, 0.0, p.y - box[3])
            d = (dx * dx + dy * dy) ** 0.5
            if best_d is None or d < best_d:
                best, best_d = n, d
        if best >= 0 and best_d is not None and best_d <= max(10 * h, 0.001 * span):
            found_by_view[best].append((h, text, float(p.x), float(p.y)))
    views = []
    for n, (box, count) in enumerate(raw):
        found = sorted(found_by_view[n], key=lambda r: -r[0])
        labels: list[str] = []
        for _, text, px, py in found:
            if text not in labels:
                labels.append(text)
            # the window must include the title even when it sits just outside the drawing's lines
            box = (min(box[0], px), min(box[1], py - 2 * found[0][0]), max(box[2], px), max(box[3], py + 2 * found[0][0]))
        views.append(View(n + 1, box, count, labels[:6]))
    return views


# ------------------------------------------------------------------ purge
def _entity_layers_and_blocks(entities: Any, layers: set[str], blocks: set[str], linetypes: set[str]) -> None:
    for e in entities:
        layers.add(e.dxf.get("layer", "0"))
        lt = e.dxf.get("linetype")
        if lt:
            linetypes.add(lt.upper())
        if e.dxftype() == "INSERT":
            blocks.add(e.dxf.name)
        elif e.dxftype() == "DIMENSION" and e.dxf.get("geometry"):
            blocks.add(e.dxf.geometry)


def purge_unused(doc: Any) -> tuple[int, int, int]:
    """Remove blocks, layers and linetypes nothing uses. Returns the three counts removed."""
    used_layers: set[str] = set(KEEP_LAYERS)
    used_blocks: set[str] = set()
    used_lt: set[str] = set(KEEP_LINETYPES)
    clayer = doc.header.get("$CLAYER")
    if clayer:
        used_layers.add(clayer)
    for layout in doc.layouts:
        _entity_layers_and_blocks(layout, used_layers, used_blocks, used_lt)
    todo = list(used_blocks)
    done: set[str] = set()
    while todo:
        name = todo.pop()
        if name in done or name not in doc.blocks:
            continue
        done.add(name)
        found: set[str] = set()
        _entity_layers_and_blocks(doc.blocks.get(name), used_layers, found, used_lt)
        todo += [b for b in found if b not in done]
        used_blocks |= found

    blocks_removed = 0
    for blk in list(doc.blocks):
        if blk.name.startswith(KEEP_BLOCKS) or blk.name in used_blocks:
            continue
        doc.blocks.delete_block(blk.name, safe=False)
        blocks_removed += 1
    layers_removed = 0
    for layer in list(doc.layers):
        if layer.dxf.name not in used_layers:
            used_lt.add(layer.dxf.linetype.upper())
    for layer in list(doc.layers):
        if layer.dxf.name not in used_layers:
            doc.layers.remove(layer.dxf.name)
            layers_removed += 1
    for layer in doc.layers:
        used_lt.add(layer.dxf.linetype.upper())
    linetypes_removed = 0
    for lt in list(doc.linetypes):
        if lt.dxf.name.upper() not in used_lt:
            doc.linetypes.remove(lt.dxf.name)
            linetypes_removed += 1
    return blocks_removed, layers_removed, linetypes_removed


# ------------------------------------------------------------------ export
def export_window(src: str | Path, window: Box, out: str | Path, *, margin: float = 0.0) -> SplitReport:
    """Copy what lies fully inside ``window`` (grown by ``margin``) into a fresh, clean DXF and save it to ``out``.

    The new file is built from scratch, so it carries only the kept entities and the layers, blocks, styles and linetypes they use.
    Nothing is carried over from the source's object tables: a DXF converted from DWG holds half-written objects that make
    AutoCAD reject a copy of it. ``src`` is not changed.
    """
    src, out = Path(src), Path(out)
    if out.resolve() == src.resolve():
        raise ValueError("the output must be a different file from the source")
    source = ezdxf.readfile(src)
    x0, y0, x1, y1 = window[0] - margin, window[1] - margin, window[2] + margin, window[3] + margin
    report = SplitReport(window=(x0, y0, x1, y1), size_before=src.stat().st_size)
    keep = []
    for e in source.modelspace():
        b = bbox.extents([e], fast=True)
        if not b.has_data:
            report.dropped_unmeasurable += 1
            continue
        ex0, ey0, ex1, ey1 = b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y
        if ex0 >= x0 and ey0 >= y0 and ex1 <= x1 and ey1 <= y1:
            keep.append(e)
        elif ex1 < x0 or ex0 > x1 or ey1 < y0 or ey0 > y1:
            report.dropped_outside += 1
        else:
            report.dropped_crossing += 1
    report.kept = len(keep)

    doc = ezdxf.new("R2018", setup=True)
    doc.units = source.units
    ezdxf_log = logging.getLogger("ezdxf")
    previous = ezdxf_log.level
    ezdxf_log.setLevel(logging.ERROR)  # the importer logs one line per object type it cannot copy
    try:
        importer = Importer(source, doc)
        importer.import_entities(keep, doc.modelspace())
        importer.finalize()
    finally:
        ezdxf_log.setLevel(previous)
    report.blocks_removed = max(len(source.blocks) - len(doc.blocks), 0)
    report.layers_removed = max(len(source.layers) - len(doc.layers), 0)
    report.linetypes_removed = max(len(source.linetypes) - len(doc.linetypes), 0)
    purge_unused(doc)  # the importer may bring a resource that ended up unused
    if report.kept:
        zoom.extents(doc.modelspace(), factor=1.05)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    try:
        doc.saveas(tmp)
        tmp.replace(out)  # a failed save never leaves a broken file under the real name
    finally:
        tmp.unlink(missing_ok=True)
    report.size_after = out.stat().st_size
    return report


# ------------------------------------------------------------------ preview and CLI
def preview(views: list[View], path: str | Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 9))
    for v in views:
        x0, y0, x1, y1 = v.box
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, linewidth=1.2))
        label = f"{v.id}: {v.title or '?'}"
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, ha="center", va="center", fontsize=8)
    if views:
        ax.set_xlim(min(v.box[0] for v in views), max(v.box[2] for v in views))
        ax.set_ylim(min(v.box[1] for v in views), max(v.box[3] for v in views))
    ax.set_aspect("equal")
    ax.set_title("Detected drawings (view number: title found in the drawing)")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return Path(path)


def load_dxf(path: str | Path) -> Path:
    """The DXF to read: a DWG is converted into the local cache first."""
    p = Path(path)
    if p.suffix.lower() == ".dwg":
        from structiq.drawing import convert

        return convert.dwg_to_dxf(p)
    if p.suffix.lower() != ".dxf":
        raise ValueError(f"expected a .dwg or .dxf file: {p}")
    return p


def format_views(views: list[View]) -> str:
    lines = [f"{len(views)} drawing(s) found (ordered top to bottom, then left to right)"]
    for v in views:
        w, h = v.size
        lines.append(f"  {v.id:>2}  {w / 1000:7.1f} x {h / 1000:6.1f} m  {v.count:>5} entities  {v.title or '(no title found)'}")
        extra = [x for x in v.labels[1:] if x != v.title]
        if extra:
            lines.append(f"        also: {'; '.join(extra)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)
    ap = argparse.ArgumentParser(prog="python -m structiq.drawing.split")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="list the drawings found in a combined file")
    s.add_argument("file")
    s.add_argument("--preview", help="write a picture of the detected drawings (PNG)")
    s.add_argument("--min-entities", type=int, default=40)
    e = sub.add_parser("export", help="write one detected drawing to its own DXF")
    e.add_argument("file")
    e.add_argument("--view", type=int, required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--margin", type=float, default=0.0)
    e.add_argument("--min-entities", type=int, default=40)
    for q in (s, e):
        q.add_argument("--within", type=int, help="look inside this view number only (a sheet that holds several drawings)")
        q.add_argument("--gap", type=float, help="drawing units: entities closer than this belong together")
        q.add_argument("--max-entity", type=float, help="drawing units: larger entities are ignored (they would join the drawings)")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)

    dxf = load_dxf(ns.file)
    doc = ezdxf.readfile(dxf)
    within = None
    if ns.within:
        top = next((v for v in find_views(doc, min_entities=ns.min_entities, max_entity=ns.max_entity) if v.id == ns.within), None)
        if top is None:
            print(f"no view {ns.within} in the first scan", file=sys.stderr)
            return 1
        within = top.box
    views = find_views(doc, min_entities=ns.min_entities, within=within, gap=ns.gap, max_entity=ns.max_entity)
    if ns.cmd == "scan":
        print(format_views(views))
        if ns.preview:
            print(f"preview: {preview(views, ns.preview)}")
        return 0
    view = next((v for v in views if v.id == ns.view), None)
    if view is None:
        print(f"no view {ns.view}; run 'scan' first", file=sys.stderr)
        return 1
    report = export_window(dxf, view.box, ns.out, margin=ns.margin)
    print(f"wrote {ns.out}\n{report.summary()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
