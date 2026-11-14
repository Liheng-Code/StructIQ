"""Propose the beam arrangement of a floor from the approved rules.

Pure geometry on what Drawing Intelligence already extracted (gridlines, columns, slab
outline, stair footprints, lift cores, shaft cells). Coordinates are model mm; a beam
running along Y (01 to 04) is ``orientation="V"`` at ``centre`` = X, one running along X
is ``"H"`` at ``centre`` = Y; ``start``/``end`` are along the beam.

The rules (learned from the sample design, see ``rules.py`` and Core Brain
``04-beam-arrangement.md``):

1. PT bands on the transverse gridlines that carry a column and sit inside the slab; marked
   only (mark, width), cut short where a stair or lift sits in the way.
2. Edge beams on the column lines, interior beams in between so that no clear slab span
   exceeds the limit (the first one at the limit from the first edge beam, the rest equal),
   all running between the faces of consecutive PT bands.
3. Where a stair or lift opening crosses a beam line, that stretch is dropped; the stair
   gets an edge beam along its west edge (continuing to the lift core) and an end beam
   across its north end out to the first interior beam. Lift cores are walls: no beams.

Sizes are the engineer's preliminary sizes, not a calculation. Everything unusual becomes a
flag, never a silent choice.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from structiq.framing.rules import BeamRules

COLUMN_TOL = 150.0  # mm: a column belongs to a gridline within this
STAIR_EDGE_REACH = 300.0  # mm: an edge beam this close to the stair's west edge is replaced


@dataclass
class Beam:
    plan: int
    role: str  # edge | interior | stair_edge | stair_end
    mark: str
    width: float
    depth: float
    orientation: str  # "V" along Y, "H" along X
    centre: float  # model X for V, model Y for H
    start: float
    end: float

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass
class Band:
    plan: int
    line: str
    mark: str
    width: float
    depth: float
    y: float  # model Y of the band centre line
    x0: float
    x1: float


@dataclass
class BeamResult:
    beams: list[Beam] = field(default_factory=list)
    bands: list[Band] = field(default_factory=list)
    flags: dict[int, list[str]] = field(default_factory=dict)
    arranged: list[int] = field(default_factory=list)
    fck: str = "C30/37"

    def schedule(self, plan: int) -> list[tuple[str, str, str]]:
        """(mark, type, Fck) rows for the plan, one per mark."""
        rows: dict[str, tuple[str, str, str]] = {}
        for b in self.beams:
            if b.plan == plan:
                rows.setdefault(b.mark, (b.mark, f"{b.mark}-({b.width:.0f}x{b.depth:.0f})mm", self.fck))
        for band in self.bands:
            if band.plan == plan:
                rows.setdefault(
                    band.mark,
                    (band.mark, f"{band.mark}-({band.width:.0f}x{band.depth:.0f})mm", self.fck),
                )
        return sorted(rows.values())


def _subtract(intervals, a, b):
    out = []
    for s, e in intervals:
        if b <= s or a >= e:
            out.append((s, e))
            continue
        if s < a:
            out.append((s, a))
        if e > b:
            out.append((b, e))
    return out


def _interior_positions(xa: float, xc: float, edge_w: float, int_w: float, max_span: float):
    """X of the interior beams: first at the span limit from the edge, the rest equal."""
    clear_total = (xc - xa) - edge_w
    n = 0
    while (clear_total - n * int_w) / (n + 1) > max_span:
        n += 1
    if n == 0:
        return []
    first = xa + edge_w / 2 + max_span + int_w / 2
    xs = [first]
    if n > 1:
        east_face = first + int_w / 2
        remaining = (xc - edge_w / 2) - east_face
        panel = (remaining - (n - 1) * int_w) / n
        for k in range(n - 1):
            xs.append(east_face + panel + int_w / 2 + k * (panel + int_w))
    return xs


def arrange_beams(layout, rules: BeamRules) -> BeamResult:
    """Arrange beams on every plan that has a slab outline and two column lines."""
    res = BeamResult(fck=rules.fck_beam)
    for c in layout.grid.clusters:
        flags = res.flags.setdefault(c.index, [])
        slab = next((s for s in layout.slabs.slabs if s.plan == c.index and s.closed), None)
        if slab is None:
            flags.append("no slab outline for this plan: beams not arranged")
            continue
        col_lines = sorted(
            (ln for ln in c.vertical if ln.label in rules.column_lines), key=lambda ln: ln.position
        )
        if len(col_lines) < 2:
            flags.append("fewer than two column lines found: beams not arranged")
            continue
        xa, xc = col_lines[0].position, col_lines[-1].position
        columns = [col for col in layout.columns.columns if col.plan == c.index]
        sx0, sy0, sx1, sy1 = slab.bbox

        # openings that block beams: (x0, y0, x1, y1, kind)
        stairs = [s for s in layout.stairs.stairs if s.plan == c.index]
        lifts = [lift for lift in layout.lifts.lifts if lift.plan == c.index]
        shafts = [o for o in layout.openings.openings if o.plan == c.index and o.rect and o.kind == "shaft"]
        boxes = (
            [(*s.footprint, "stair") for s in stairs]
            + [(*lift.outer, "lift") for lift in lifts]
            + [(*o.rect, "shaft") for o in shafts]
        )

        # 1. PT bands
        bands: list[Band] = []
        for ln in c.horizontal:
            width = rules.band_width(ln.label or "")
            if width is None:
                continue
            if not any(abs(col.y - ln.position) <= COLUMN_TOL for col in columns):
                continue
            tol = rules.band_line_tolerance
            if not (sy0 - tol <= ln.position <= sy1 + tol):
                continue
            x0, x1 = xa, xc
            mid = (xa + xc) / 2
            for bx0, by0, bx1, by1, kind in boxes:
                if kind == "shaft" or by1 <= ln.position - width / 2 or by0 >= ln.position + width / 2:
                    continue
                if bx1 <= xa or bx0 >= xc:
                    continue
                if (bx0 + bx1) / 2 < mid:
                    x0 = max(x0, bx1)
                else:
                    x1 = min(x1, bx0)
                flags.append(
                    f"PT band on line {ln.label} is cut short by a {kind} opening "
                    f"(X {bx0:.0f}..{bx1:.0f})"
                )
            bands.append(Band(c.index, ln.label or "?", rules.band_mark(width), width, rules.band_depth, ln.position, x0, x1))
        bands.sort(key=lambda b: b.y)
        if len(bands) < 2:
            flags.append("fewer than two PT bands inside the slab: RC beams not arranged")
            res.bands.extend(bands)
            continue
        res.bands.extend(bands)

        # 2. along-Y beam lines between band faces
        edge = rules.sizes["edge"]
        interior = rules.sizes["interior"]
        lines = [(ln.position, "edge", edge) for ln in col_lines]
        xs_int = _interior_positions(xa, xc, edge.width, interior.width, rules.max_clear_span)
        lines += [(x, "interior", interior) for x in xs_int]
        spans = [
            (a.y + a.width / 2, b.y - b.width / 2) for a, b in zip(bands, bands[1:])
        ]
        beams: list[Beam] = []
        for x, role, size in sorted(lines):
            intervals = [(s, e) for s, e in spans if e - s > 0]
            for bx0, by0, bx1, by1, kind in boxes:
                if bx1 > x - size.width / 2 and bx0 < x + size.width / 2:
                    intervals = _subtract(intervals, by0, by1)
            for s, e in intervals:
                if e - s >= rules.min_segment:
                    beams.append(Beam(c.index, role, size.mark, size.width, size.depth, "V", x, s, e))
            if role == "edge" and any(
                bx1 > x - size.width / 2 and bx0 < x + size.width / 2 for bx0, _, bx1, _, _ in boxes
            ):
                flags.append(
                    f"edge beam on column line at X={x:.0f} is interrupted by an opening; "
                    "its stretch is covered by the stair edge beam or the lift core"
                )

        # balcony edge beam where the slab extends past a column line
        if rules.cantilever_role:
            size = rules.sizes[rules.cantilever_role]
            for overhang, x in ((xa - sx0, sx0 + size.width / 2), (sx1 - xc, sx1 - size.width / 2)):
                if overhang <= rules.cantilever_min_overhang:
                    continue
                intervals = list(spans)
                for bx0, by0, bx1, by1, kind in boxes:
                    if bx1 > x - size.width / 2 and bx0 < x + size.width / 2:
                        intervals = _subtract(intervals, by0, by1)
                for s, e in intervals:
                    if e - s >= rules.min_segment:
                        beams.append(
                            Beam(c.index, "cantilever_edge", size.mark, size.width, size.depth, "V", x, s, e)
                        )

        # 3. stair trimmers
        edge_size = rules.sizes[rules.stair_edge_role]
        end_size = rules.sizes[rules.stair_end_role]
        for sx_0, sy_0, sx_1, sy_1 in [s.footprint for s in stairs]:
            # the stair edge beam runs on to the lift core when the core stands on the same line
            ends = [
                lift.outer[1]
                for lift in lifts
                if lift.outer[0] <= sx_0 <= lift.outer[2] and lift.outer[1] >= sy_1 - 1.0
            ]
            y_end = min(ends) if ends else sy_1
            west = Beam(c.index, "stair_edge", edge_size.mark, edge_size.width, edge_size.depth, "V", sx_0, sy_0, y_end)
            # the end beam runs out to the west face of the first interior line east of the stair
            east_x = min((x for x in xs_int if x > sx_1), default=None)
            if east_x is not None:
                stop = east_x - interior.width / 2
            else:
                stop = sx_1
            end = Beam(
                c.index, "stair_end", end_size.mark, end_size.width, end_size.depth, "H",
                sy_1, sx_0 + edge_size.width / 2, stop,
            )
            # the stair edge beam takes over this stretch of the edge line beside it
            kept = []
            for b in beams:
                if b.orientation == "V" and b.role == "edge" and abs(b.centre - sx_0) <= STAIR_EDGE_REACH:
                    for s, e in _subtract([(b.start, b.end)], sy_0, y_end):
                        if e - s >= rules.min_segment:
                            kept.append(replace(b, start=s, end=e))
                else:
                    kept.append(b)
            beams = kept
            # the end beam cuts the stair edge beam and the interior beam it lands on
            for b in [west]:
                pieces = _subtract([(b.start, b.end)], sy_1 - end_size.width / 2, sy_1 + end_size.width / 2)
                for s, e in pieces:
                    if e - s >= rules.min_segment:
                        beams.append(Beam(b.plan, b.role, b.mark, b.width, b.depth, b.orientation, b.centre, s, e))
            beams.append(end)
            if east_x is not None:
                cut = []
                for b in beams:
                    if b.orientation == "V" and b.role == "interior" and abs(b.centre - east_x) < 1.0:
                        for s, e in _subtract([(b.start, b.end)], sy_1 - end_size.width / 2, sy_1 + end_size.width / 2):
                            if e - s >= rules.min_segment:
                                cut.append(Beam(b.plan, b.role, b.mark, b.width, b.depth, "V", b.centre, s, e))
                    else:
                        cut.append(b)
                beams = cut
        for lift in lifts:
            if not lift.cavity:
                flags.append("lift core outline is not a simple box: check the beams around it")

        # panel check: clear gap between neighbouring along-Y beam lines
        line_x = sorted((x, size.width) for x, _, size in lines)
        for (x0, w0), (x1, w1) in zip(line_x, line_x[1:]):
            clear = (x1 - w1 / 2) - (x0 + w0 / 2)
            if clear > rules.max_clear_span + 1.0:
                flags.append(f"slab panel between X={x0:.0f} and X={x1:.0f} is {clear:.0f} clear, over the limit")

        beams.sort(key=lambda b: (b.orientation, b.centre, b.start))
        res.beams.extend(beams)
        res.arranged.append(c.index)
    return res


def format_beams_report(result: BeamResult, plan_names: dict[int, str] | None = None) -> str:
    names = plan_names or {}
    out = [
        "BEAMS (preliminary arrangement from the engineer's rules; sizes are not a calculation. "
        "Confirm against the drawing)"
    ]
    plans = sorted(set(result.flags) | set(result.arranged))
    for p in plans:
        label = names.get(p)
        title = f"Plan {p}" + (f" ({label})" if label else "")
        beams = [b for b in result.beams if b.plan == p]
        bands = [b for b in result.bands if b.plan == p]
        if p in result.arranged:
            roles = {}
            for b in beams:
                roles.setdefault((b.role, b.mark, b.width, b.depth), []).append(b)
            out.append(
                f"\n{title}: {len(beams)} RC beam piece(s), {len(bands)} PT band(s) "
                f"({sum(b.length for b in beams) / 1000:.1f} m of RC beam)"
            )
            for (role, mark, w, d), group in sorted(roles.items()):
                out.append(
                    f"  {role:<10} {mark} {w:.0f}x{d:.0f}: {len(group)} piece(s), "
                    f"{sum(b.length for b in group) / 1000:.1f} m"
                )
            for band in bands:
                out.append(
                    f"  PT band    {band.mark} {band.width:.0f}x{band.depth:.0f} on line {band.line} "
                    f"(marked only, not designed)"
                )
        else:
            out.append(f"\n{title}: not arranged")
        for f in result.flags.get(p, []):
            out.append(f"  ! {f}")
    out.append("\nBeam rules: Core Brain beam-rules.yaml (approved). PT bands are not designed here.")
    return "\n".join(out)
