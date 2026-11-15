"""Read the beam arrangement out of a sample structural drawing set (PDF).

The sample (a Revit export) draws every beam as two dotted brown lines (its faces) with a
tag (RCB1, PTB1...) on it, gridlines as teal dash-dot lines, and a framing schedule table
(Level, Mark, Type "RCB1-(400x500)mm", Fck). This module measures, per floor sheet:

* the gridlines (teal runs) and their labels (bubbles), which calibrate sheet mm to real mm
  (A-B = 4000 and B-C = 7000 in this building) and give grid-frame coordinates
  (X from gridline A, Y from gridline 01, both in real mm);
* the beams: pairs of parallel brown runs a beam-width apart with a tag between them;
* the framing schedule (mark to size, Fck);
* the slab thickness tags.

Output is a JSON of *observations*, the evidence behind the written beam rules. It is derived
from client project data, so keep it out of git (store it beside the project).

Usage::

    python -m structiq.framing.learn "<sample.pdf>" "<observations.json>"
"""

from __future__ import annotations

import collections
import json
import re
import sys
from dataclasses import asdict, dataclass, field

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)

K = 25.4 / 72  # PDF points to mm
BROWN = "#804000"
TEAL = "#408080"
PLAN_MAX_X = 210.0  # mm: the floor plan sits left of this; sections are to its right
PLAN_MAX_Y = 250.0  # mm: the schedule table and notes are below this
TAG_REACH = 6.0  # mm of sheet: a tag may sit this far beside the beam face
GRID_SPACING = {"AB": 4000.0, "BC": 7000.0}  # real mm, this building
MIN_BEAM_WIDTH, MAX_BEAM_WIDTH = 150.0, 3000.0  # real mm
MIN_RUN = 8.0  # mm of sheet: shorter brown runs are noise
MERGE_GAP = 2.0  # mm of sheet: collinear beam pieces closer than this are one beam
TAG_RE = re.compile(r"^(RCB|PTB|PBT|SB|RECL|RCL)\d*[a-z]?$")
TYPE_RE = re.compile(r"-\((\d+)x(\d+)\)mm")
ROW_RE = re.compile(r"(\S+)\s+(\S+)\s+\S+-\((\d+)x(\d+)\)mm\s+(C\d+/\d+)")
SLAB_RE = re.compile(r"^(\d+)\s*mm$")


@dataclass
class Beam:
    mark: str | None
    orientation: str  # "V" runs along Y (01 to 04), "H" runs along X (A to C)
    centre: float  # real mm: X (V beams) or Y (H beams) in the grid frame
    width: float  # real mm
    start: float  # real mm along the beam
    end: float
    size: str | None = None  # "400x500" from the schedule


@dataclass
class Sheet:
    page: int
    name: str
    scale: float | None = None  # real mm per mm of sheet
    grid_x: dict[str, float] = field(default_factory=dict)  # label -> real X (A = 0)
    grid_y: dict[str, float] = field(default_factory=dict)  # label -> real Y (01 = 0)
    schedule: dict[str, dict] = field(default_factory=dict)  # mark -> {w, d, fck, level}
    slab_mm: list[int] = field(default_factory=list)
    beams: list[Beam] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _tp(page, p):
    q = pymupdf.Point(p) * page.rotation_matrix
    return q.x * K, q.y * K


def _box(page, rect):
    r = pymupdf.Rect(rect) * page.rotation_matrix
    r.normalize()
    return r.x0 * K, r.y0 * K, r.x1 * K, r.y1 * K


def _hex(color):
    return None if color is None else "#%02x%02x%02x" % tuple(round(v * 255) for v in color)


def _runs(page, colour: str):
    """Collinear straight strokes of one colour merged into runs.

    Returns ({y: [(x0, x1)]} for horizontal runs, {x: [(y0, y1)]} for vertical runs).
    """
    horizontal, vertical = collections.defaultdict(list), collections.defaultdict(list)
    for d in page.get_drawings():
        if _hex(d.get("color")) != colour:
            continue
        for item in d["items"]:
            if item[0] != "l":
                continue
            (x0, y0), (x1, y1) = _tp(page, item[1]), _tp(page, item[2])
            if abs(y1 - y0) < 0.05 and abs(x1 - x0) > 0.2:
                horizontal[round((y0 + y1) / 2, 1)].append(tuple(sorted((x0, x1))))
            elif abs(x1 - x0) < 0.05 and abs(y1 - y0) > 0.2:
                vertical[round((x0 + x1) / 2, 1)].append(tuple(sorted((y0, y1))))

    def merge(table, gap):
        out = {}
        for pos, spans in table.items():
            spans.sort()
            merged = [list(spans[0])]
            for a, b in spans[1:]:
                if a <= merged[-1][1] + gap:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            out[pos] = [tuple(m) for m in merged]
        return out

    return merge(horizontal, 1.2), merge(vertical, 1.2)


def _cluster(values, tol=0.6):
    out = []
    for v in sorted(values):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(c) / len(c) for c in out]


def _text(page):
    """Text spans as (text, font, size, x0, y0, x1, y1) in sheet mm."""
    spans = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                if s["text"].strip():
                    x0, y0, x1, y1 = _box(page, s["bbox"])
                    spans.append((s["text"].strip(), s["font"], s["size"], x0, y0, x1, y1))
    return spans


def _sheet_name(spans) -> str:
    parts = [s[0] for s in spans if 114 <= s[3] <= 235 and 8 <= s[4] <= 13 and s[1].startswith("Arial")]
    return " ".join(parts)


def _schedule(page, level_hint=None):
    """Framing schedule rows: mark -> {w, d, fck, level}."""
    # cells come out of the PDF one per text object, so search the running text for
    # "<level> <mark> <type>-(WxD)mm <fck>" instead of rebuilding table lines
    rows = {}
    for m in ROW_RE.finditer(page.get_text("text")):
        level, mark, w, d, fck = m.groups()
        rows.setdefault(mark, {"w": int(w), "d": int(d), "fck": fck, "level": level})
    return rows


def read_sheet(doc, page_no: int) -> Sheet:
    page = doc[page_no - 1]
    spans = _text(page)
    sheet = Sheet(page_no, _sheet_name(spans))
    horizontal, vertical = _runs(page, TEAL)

    # gridlines: long teal runs in the plan area
    vx = _cluster([x for x, runs in vertical.items() if x < PLAN_MAX_X and any(b - a >= 100 for a, b in runs)])
    hy = _cluster([y for y, runs in horizontal.items() if any(b - a >= 80 and a < PLAN_MAX_X for a, b in runs)])
    letters = {  # bubbles may be at the top or the bottom of the plan, never in the title band
        t: (x0 + x1) / 2
        for t, f, sz, x0, y0, x1, y1 in spans
        if t in ("A", "B", "C") and 27 < y0 < 285 and x1 < PLAN_MAX_X
    }
    numbers = {t: (y0 + y1) / 2 for t, f, sz, x0, y0, x1, y1 in spans if re.fullmatch(r"0[1-4]", t) and x0 < 30}
    gx, gy = {}, {}
    for label, pos in letters.items():
        nearest = min(vx, key=lambda v: abs(v - pos), default=None)
        if nearest is not None and abs(nearest - pos) < 4:
            gx[label] = nearest
    for label, pos in numbers.items():
        nearest = min(hy, key=lambda v: abs(v - pos), default=None)
        if nearest is not None and abs(nearest - pos) < 4:
            gy[label] = nearest
    if not {"A", "B", "C"} <= set(gx) or "01" not in gy:
        sheet.warnings.append("gridlines or bubbles not found; sheet skipped")
        return sheet

    s1 = GRID_SPACING["AB"] / (gx["B"] - gx["A"])
    s2 = GRID_SPACING["BC"] / (gx["C"] - gx["B"])
    if abs(s1 - s2) / s1 > 0.02:
        sheet.warnings.append(f"scale check failed (A-B gives {s1:.1f}, B-C gives {s2:.1f}); sheet skipped")
        return sheet
    scale = (s1 + s2) / 2
    sheet.scale = round(scale, 2)
    sheet.grid_x = {k: round((v - gx["A"]) * scale) for k, v in sorted(gx.items())}
    sheet.grid_y = {k: round((gy["01"] - v) * scale) for k, v in sorted(gy.items())}

    sheet.schedule = _schedule(page)
    sheet.slab_mm = sorted({int(m.group(1)) for t, *_ in spans if (m := SLAB_RE.match(t))})

    # beams: parallel brown runs a beam width apart, with a tag beside or on them. Tags in the
    # schedule table below the plan are not beam tags.
    tags = [
        ((x0 + x1) / 2, (y0 + y1) / 2, t)
        for t, f, sz, x0, y0, x1, y1 in spans
        if TAG_RE.match(t) and y1 < PLAN_MAX_Y and x1 < PLAN_MAX_X + 20
    ]
    h_runs, v_runs = _runs(page, BROWN)
    bands = []  # (orientation, centre_sheet, width_sheet, start, end)
    for orientation, table in (("V", v_runs), ("H", h_runs)):
        positions = sorted(p for p, runs in table.items() if any(b - a >= MIN_RUN for a, b in runs))
        for i, p in enumerate(positions):
            for q in positions[i + 1 :]:
                width = (q - p) * scale
                if width > MAX_BEAM_WIDTH:
                    break
                if width < MIN_BEAM_WIDTH:
                    continue
                for a0, a1 in table[p]:
                    for b0, b1 in table[q]:
                        start, end = max(a0, b0), min(a1, b1)
                        if end - start >= MIN_RUN and (p + q) / 2 < PLAN_MAX_X + 20:
                            bands.append((orientation, (p + q) / 2, q - p, start, end))

    # each tag labels the nearest band it sits beside or on (tags are drawn next to the beam)
    marks: dict[int, str] = {}
    for tx, ty, text in tags:
        best = None
        for i, (orientation, centre, width, start, end) in enumerate(bands):
            across, along = (tx, ty) if orientation == "V" else (ty, tx)
            reach = width / 2 + TAG_REACH
            if abs(across - centre) <= reach and start - 0.6 <= along <= end + 0.6:
                gap = abs(across - centre)
                if best is None or gap < best[0]:
                    best = (gap, i)
        if best is not None:
            marks.setdefault(best[1], text)

    # a tagged piece also names the untagged collinear pieces of the same beam (same width)
    for i, (orientation, centre, width, start, end) in enumerate(bands):
        if i in marks:
            continue
        for j, mark in list(marks.items()):
            o2, c2, w2, s2, e2 = bands[j]
            if o2 == orientation and abs(c2 - centre) < 0.8 and abs(w2 - width) < 0.8:
                marks[i] = mark
                break

    found = []
    for i, (o, c, w, s, e) in enumerate(bands):
        if i not in marks:
            continue
        row = sheet.schedule.get(marks[i])
        # a real beam is as wide as its schedule size; pairs of unrelated lines are not
        if row and abs(w * scale - row["w"]) > max(40.0, 0.1 * row["w"]):
            continue
        found.append([o, c, w, s, e, marks[i]])

    # merge collinear pieces of the same beam
    found.sort(key=lambda b: (b[0], round(b[1], 0), b[5], b[3]))
    merged = []
    for b in found:
        if (
            merged
            and merged[-1][0] == b[0]
            and merged[-1][5] == b[5]
            and abs(merged[-1][1] - b[1]) < 0.8
            and b[3] <= merged[-1][4] + MERGE_GAP
        ):
            merged[-1][4] = max(merged[-1][4], b[4])
        else:
            merged.append(list(b))

    for orientation, centre, width, start, end, mark in merged:
        if orientation == "V":
            c = (centre - gx["A"]) * scale
            a0, a1 = (gy["01"] - end) * scale, (gy["01"] - start) * scale
        else:
            c = (gy["01"] - centre) * scale
            a0, a1 = (start - gx["A"]) * scale, (end - gx["A"]) * scale
        row = sheet.schedule.get(mark)
        sheet.beams.append(
            Beam(
                mark,
                orientation,
                round(c),
                round(width * scale / 10) * 10,
                round(min(a0, a1)),
                round(max(a0, a1)),
                f"{row['w']}x{row['d']}" if row else None,
            )
        )
    sheet.beams.sort(key=lambda b: (b.orientation, b.centre, b.start))
    return sheet


def read_set(path: str, pages: list[int] | None = None) -> list[Sheet]:
    doc = pymupdf.open(path)
    return [read_sheet(doc, n) for n in pages or range(1, doc.page_count + 1)]


def summary(sheets: list[Sheet]) -> str:
    out = []
    for s in sheets:
        if not s.scale:
            out.append(f"\n== page {s.page}: {s.name or '(no name)'}  SKIPPED: {'; '.join(s.warnings)}")
            continue
        out.append(f"\n== page {s.page}: {s.name or '(no name)'}  scale 1:{s.scale / 1.0:.0f}")
        out.append(f"   grid X (from A): {s.grid_x}   grid Y (from 01): {s.grid_y}")
        out.append(f"   slab thickness tags: {s.slab_mm} mm")
        out.append("   schedule: " + ", ".join(f"{m} {r['w']}x{r['d']} {r['fck']}" for m, r in s.schedule.items()))
        for b in s.beams:
            axis = "X" if b.orientation == "V" else "Y"
            out.append(
                f"   {b.mark or '?':<6} {b.orientation} at {axis}={b.centre:>6} width {b.width:>5}"
                f" from {b.start:>6} to {b.end:>6} (len {b.end - b.start:>5}) size {b.size}"
            )
        for w in s.warnings:
            out.append(f"   ! {w}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print('Usage: python -m structiq.framing.learn "<sample.pdf>" ["<observations.json>"]')
        return 2
    sheets = read_set(args[0])
    print(summary(sheets))
    if len(args) == 2:
        with open(args[1], "w", encoding="utf-8") as fh:
            json.dump([asdict(s) for s in sheets], fh, indent=1)
        print(f"\nWrote {args[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
