"""Compare StructIQ's beam arrangement with the engineer's design (the answer key).

The answer key is ``beam-observations.json`` from ``learn.py`` (the sample structural set),
whose beams are in the grid frame (X from gridline A, Y from gridline 01, real mm). StructIQ's
beams are converted to the same frame per plan. A sample beam counts as matched where one of
ours has the same orientation, a centre within ``position_match`` and overlaps along its length;
the score is matched length over sample length. PT bands are matched separately (centre and
mark width), since StructIQ marks them without designing them.

Because plan numbers are not floors, every plan is compared with every sample floor sheet and
the best match shows which floor a plan is.

Usage::

    python -m structiq.framing.compare "<converted.dxf>" "<observations.json>" [--plans 3,4,5,6]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf

from structiq.drawing import layout as drawing_layout
from structiq.drawing.pipeline import read_brain
from structiq.framing.rules import load_rules

PT_PREFIXES = ("PTB", "PBT")
RC_PREFIX = "RCB"


@dataclass
class Match:
    plan: int
    page: int
    sheet_name: str
    observed_len: float = 0.0
    matched_len: float = 0.0
    extra_len: float = 0.0
    pt_observed: int = 0
    pt_matched: int = 0
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.matched_len / self.observed_len if self.observed_len else 0.0


def _union_length(spans) -> float:
    total, last = 0.0, None
    for s, e in sorted(spans):
        if last is None or s > last:
            total += e - s
            last = e
        elif e > last:
            total += e - last
            last = e
    return total


def _covered(start, end, spans) -> float:
    """Length of [start, end] covered by ``spans``."""
    clipped = [(max(start, s), min(end, e)) for s, e in spans if min(end, e) > max(start, s)]
    return _union_length(clipped)


def ours_in_grid_frame(layout, plan: int):
    """StructIQ's beams and bands of ``plan`` as dicts in the grid frame (X from A, Y from 01)."""
    cluster = next(c for c in layout.grid.clusters if c.index == plan)
    xa = min(ln.position for ln in cluster.vertical)
    ys = sorted(cluster.horizontal, key=lambda ln: ln.position)
    y1 = next((ln.position for ln in ys if (ln.label or "").lstrip("0") == "1"), ys[0].position)
    beams = []
    for b in layout.beams.beams:
        if b.plan != plan:
            continue
        origin = xa if b.orientation == "V" else y1
        along = y1 if b.orientation == "V" else xa
        beams.append(
            {"mark": b.mark, "orientation": b.orientation, "centre": b.centre - origin,
             "start": b.start - along, "end": b.end - along, "width": b.width}
        )
    bands = [
        {"mark": b.mark, "centre": b.y - y1, "width": b.width, "x0": b.x0 - xa, "x1": b.x1 - xa}
        for b in layout.beams.bands
        if b.plan == plan
    ]
    return beams, bands


def compare_plan(layout, plan: int, sheet: dict, tol: float) -> Match:
    beams, bands = ours_in_grid_frame(layout, plan)
    m = Match(plan, sheet["page"], sheet["name"])
    observed = [b for b in sheet["beams"] if (b["mark"] or "").startswith(RC_PREFIX)]
    for o in observed:
        length = o["end"] - o["start"]
        spans = [
            (b["start"], b["end"])
            for b in beams
            if b["orientation"] == o["orientation"] and abs(b["centre"] - o["centre"]) <= tol
        ]
        got = _covered(o["start"], o["end"], spans)
        m.observed_len += length
        m.matched_len += got
        if length - got > 300:
            axis = "X" if o["orientation"] == "V" else "Y"
            m.missing.append(
                f"{o['mark']} {axis}={o['centre']:.0f} {o['start']:.0f}..{o['end']:.0f} "
                f"({length - got:.0f} mm not covered)"
            )
    for b in beams:
        spans = [
            (o["start"], o["end"])
            for o in observed
            if o["orientation"] == b["orientation"] and abs(b["centre"] - o["centre"]) <= tol
        ]
        free = (b["end"] - b["start"]) - _covered(b["start"], b["end"], spans)
        m.extra_len += max(free, 0.0)
        if free > 300:
            axis = "X" if b["orientation"] == "V" else "Y"
            m.extra.append(
                f"{b['mark']} {axis}={b['centre']:.0f} {b['start']:.0f}..{b['end']:.0f} "
                f"({free:.0f} mm not in the sample)"
            )
    pts = [b for b in sheet["beams"] if (b["mark"] or "").startswith(PT_PREFIXES)]
    seen = {(round(b["centre"] / 100), b["width"]) for b in pts}
    m.pt_observed = len({round(b["centre"] / 100) for b in pts})
    for band in bands:
        if any(abs(band["centre"] - b["centre"]) <= tol * 4 and abs(band["width"] - b["width"]) <= 100 for b in pts):
            m.pt_matched += 1
    _ = seen
    return m


def format_matrix(matches: list[Match]) -> str:
    out = ["plan -> sample sheet: matched RC beam length (sample length, extra length of ours), PT bands"]
    plans = sorted({m.plan for m in matches})
    for p in plans:
        row = sorted((m for m in matches if m.plan == p), key=lambda m: -m.score)
        out.append(f"\nPlan {p}:")
        for m in row[:4]:
            out.append(
                f"  vs page {m.page:>2} {m.sheet_name[:34]:<34} {m.score * 100:5.1f}% of {m.observed_len / 1000:5.1f} m"
                f"   extra {m.extra_len / 1000:4.1f} m   PT {m.pt_matched}/{m.pt_observed}"
            )
    return "\n".join(out)


def format_detail(m: Match) -> str:
    out = [f"\nDetail: plan {m.plan} against page {m.page} ({m.sheet_name})"]
    out.append(f"  matched {m.score * 100:.1f}% of {m.observed_len / 1000:.1f} m; extra {m.extra_len / 1000:.1f} m of ours")
    out.append("  Sample beams not covered by StructIQ:")
    out += [f"    {s}" for s in m.missing[:25]] or ["    none"]
    out.append("  StructIQ beams not in the sample:")
    out += [f"    {s}" for s in m.extra[:25]] or ["    none"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)
    p = argparse.ArgumentParser(prog="python -m structiq.framing.compare")
    p.add_argument("drawing", help="converted architect DXF")
    p.add_argument("observations", help="beam-observations.json from framing.learn")
    p.add_argument("--plans", help="comma separated plan numbers (default: all arranged)")
    p.add_argument("--detail", help='"plan=page", e.g. 3=9, prints the differences for that pair')
    ns = p.parse_args(sys.argv[1:] if argv is None else argv)

    brain, _ = read_brain()
    rules = load_rules(brain)
    lay = drawing_layout.extract_layout(ezdxf.readfile(ns.drawing), beam_rules=rules)
    sheets = [s for s in json.loads(Path(ns.observations).read_text("utf-8")) if s.get("scale") and s["beams"]]
    plans = [int(x) for x in ns.plans.split(",")] if ns.plans else lay.beams.arranged
    matches = [compare_plan(lay, pl, s, rules.position_match) for pl in plans for s in sheets]
    print(format_matrix(matches))
    if ns.detail:
        pl, pg = (int(x) for x in ns.detail.split("="))
        pick = next((m for m in matches if m.plan == pl and m.page == pg), None)
        print(format_detail(pick) if pick else f"\nno comparison for plan {pl} against page {pg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
