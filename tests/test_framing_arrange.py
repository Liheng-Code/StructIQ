import ezdxf
import pytest

from structiq.drawing import layout
from structiq.framing import arrange, rules

RULES = {
    "status": "approved",
    "frame": {"column_lines": ["A", "C"]},
    "slab": {"thickness_floor": 150, "thickness_roof": 120, "max_clear_span": 3500},
    "concrete": {"beam": "C30/37", "column": "C35/45"},
    "pt_bands": {
        "width_by_line": {"1": 2400, "2": 2400, "3": 2400, "4": 2600},
        "depth": 500,
        "mark_by_width": {2400: "PTB1", 2600: "PTB3"},
        "line_tolerance": 1500,
    },
    "beams": {
        "edge": {"mark": "RCB1", "width": 400, "depth": 500},
        "interior": {"mark": "RCB3", "width": 300, "depth": 500},
        "stair_edge": {"mark": "RCB5", "width": 200, "depth": 500},
        "trimmer": {"mark": "RCB6", "width": 200, "depth": 400},
        "curb": {"mark": "RCB8", "width": 200, "depth": 600},
    },
    "interior_beams": {"direction": "along_y", "placement": "max_span_first_then_equal", "min_segment": 1000},
    "openings": {
        "stair": {"edge_beam": "stair_edge", "end_beam": "interior"},
        "shaft": {"trimmers": False},
        "lift_core": {"beams": False},
    },
    "cantilever_edge": {"beam": "stair_edge", "min_overhang": 300},
    "tolerances": {"position_match": 150},
}


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _doc(slab=True, stair=False, lift=False):
    """Grid A, B, C = 0, 4000, 11000 and 1..4 = 0, 5100, 12800, 20500; columns on A and C."""
    doc = ezdxf.new("R2018")
    doc.units = 4
    for name in ("GRID", "SLAB"):
        doc.layers.add(name)
    msp = doc.modelspace()
    ax = doc.blocks.new("AXIS BUBBLE")
    ax.add_attdef("AXIS", insert=(0, 0), height=250)
    xs, ys = [0, 4000, 11000], [0, 5100, 12800, 20500]
    for x, name in zip(xs, "ABC"):
        msp.add_line((x, -3000), (x, 23500), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (x, 24000)).add_auto_attribs({"AXIS": name})
    for y, name in zip(ys, "1234"):
        msp.add_line((-3000, y), (14000, y), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (-3500, y)).add_auto_attribs({"AXIS": name})
    col = doc.blocks.new("COLBLK")
    col.add_lwpolyline(_rect(-250, -300, 250, 300), close=True)
    col.add_hatch(color=7).paths.add_polyline_path(_rect(-250, -300, 250, 300), is_closed=True)
    for x in (0, 11000):
        for y in ys:
            msp.add_blockref("COLBLK", (x, y))
    if slab:
        msp.add_lwpolyline(_rect(-700, -500, 11700, 21800), close=True, dxfattribs={"layer": "SLAB"})
    if stair:  # 2300 x 3600 stair void on line A, between lines 2 and 3 (y 5350..8950)
        blk = doc.blocks.new("STAIRBLK")
        for f in range(2):
            for i in range(12):
                blk.add_lwpolyline(
                    _rect(f * 1300, i * 280, f * 1300 + 1000, (i + 1) * 280), close=True,
                    dxfattribs={"layer": "STAIR"},
                )
        msp.add_blockref("STAIRBLK", (-100, 5350), dxfattribs={"layer": "0"})
    if lift:
        car = doc.blocks.new("CAR")
        car.add_line((0, 0), (500, 500), dxfattribs={"layer": "X-ELEVATOR"})
        lb = doc.blocks.new("LIFTBLK")
        lb.add_blockref("CAR", (800, 800))
        core = [
            (0, 2210), (0, 0), (2200, 0), (2200, 575), (2000, 575), (2000, 200),
            (200, 200), (200, 2010), (2000, 2010), (2000, 1615), (2200, 1615), (2200, 2210),
        ]
        lb.add_lwpolyline(core, close=True, dxfattribs={"layer": "N- WALL HATCH BRICK"})
        msp.add_blockref("LIFTBLK", (-200, 10540))  # core y 10540..12750 on line A
    return doc


def _arrange(doc):
    return layout.extract_layout(doc), rules.from_dict(RULES)


def _v(result, role=None, plan=1):
    return [b for b in result.beams if b.plan == plan and b.orientation == "V" and (role is None or b.role == role)]


def test_rules_must_be_approved():
    with pytest.raises(rules.RulesNotApprovedError):
        rules.from_dict({**RULES, "status": "draft"})
    assert rules.from_dict({**RULES, "status": "draft"}, allow_draft=True).max_clear_span == 3500


def test_interior_beams_first_at_the_span_limit_then_equal():
    xs = arrange._interior_positions(0, 11000, 400, 300, 3500)
    assert xs == pytest.approx([3850.0, 7400.0])  # the sample has 3850 and 7360


def test_pt_bands_on_lines_with_columns_inside_the_slab():
    lay, r = _arrange(_doc())
    res = arrange.arrange_beams(lay, r)
    assert [(b.line, b.mark, b.width) for b in res.bands] == [
        ("1", "PTB1", 2400), ("2", "PTB1", 2400), ("3", "PTB1", 2400), ("4", "PTB3", 2600),
    ]


def test_edge_and_interior_beams_run_between_band_faces():
    lay, r = _arrange(_doc())
    res = arrange.arrange_beams(lay, r)
    edge_a = sorted((b.start, b.end) for b in _v(res, "edge") if b.centre == 0)
    # between band faces: 1200..3900, 6300..11600, 14000..19200 (band 04 is 2600 wide)
    assert edge_a == [(1200.0, 3900.0), (6300.0, 11600.0), (14000.0, 19200.0)]
    interior = sorted({round(b.centre) for b in _v(res, "interior")})
    assert interior == [3850, 7400]
    # RCB5 is the balcony edge beam: the test slab overhangs the column lines by 700
    assert {b.mark for b in res.beams} == {"RCB1", "RCB3", "RCB5"}


def test_balcony_edge_beam_only_where_the_slab_extends_far_enough():
    lay, r = _arrange(_doc())  # slab -700..11700: 700 past A (west) and 700 past C (east)
    res = arrange.arrange_beams(lay, r)
    cant = [b for b in res.beams if b.role == "cantilever_edge"]
    # 700 > 300 on both sides: RCB5 with the outer face on the slab edge, between band faces
    assert sorted({round(b.centre) for b in cant}) == [-600, 11600]
    assert {b.mark for b in cant} == {"RCB5"}
    # a slab that overhangs only 200 gets none
    doc = _doc()
    for e in list(doc.modelspace().query("LWPOLYLINE[layer=='SLAB']")):
        doc.modelspace().delete_entity(e)
    doc.modelspace().add_lwpolyline(_rect(-200, -500, 11200, 21800), close=True, dxfattribs={"layer": "SLAB"})
    lay2, r2 = _arrange(doc)
    assert [b for b in arrange.arrange_beams(lay2, r2).beams if b.role == "cantilever_edge"] == []


def test_no_slab_outline_means_no_beams_and_a_flag():
    lay, r = _arrange(_doc(slab=False))
    res = arrange.arrange_beams(lay, r)
    assert res.beams == [] and res.arranged == []
    assert "no slab outline" in res.flags[1][0]


def test_stair_cuts_the_edge_beam_and_gets_its_own_trimmers():
    lay, r = _arrange(_doc(stair=True, lift=True))
    res = arrange.arrange_beams(lay, r)
    # edge beam on line A is gone between the bands where the stair and the lift stand
    edge_a = sorted((b.start, b.end) for b in _v(res, "edge") if b.centre == 0)
    assert edge_a == [(1200.0, 3900.0), (14000.0, 19200.0)]
    # the stair edge beam sits on the stair's west edge (X=-100), splits at the end beam
    west = sorted((b.start, b.end) for b in _v(res, "stair_edge"))
    assert all(b.centre == -100 for b in _v(res, "stair_edge"))
    assert west[0][0] == 5350
    assert west[-1][1] == 10540  # runs on to the lift core
    # the end beam closes the north side of the stair out to the first interior beam
    (end,) = [b for b in res.beams if b.role == "stair_end"]
    assert end.orientation == "H" and end.centre == pytest.approx(8710, abs=1)  # 5350 + 12 x 280
    assert end.end == pytest.approx(3850 - 150)
    # and the interior beam is cut where it lands
    cut = sorted((b.start, b.end) for b in _v(res, "interior") if round(b.centre) == 3850)
    assert any(abs(e - (end.centre - 150)) < 2 for s, e in cut)


def test_band_is_cut_short_by_the_stair_and_the_lift():
    lay, r = _arrange(_doc(stair=True, lift=True))
    res = arrange.arrange_beams(lay, r)
    band2 = next(b for b in res.bands if b.line == "2")
    band3 = next(b for b in res.bands if b.line == "3")
    assert band2.x0 == pytest.approx(2200, abs=2)  # stair east edge (-100 + 2300 wide)
    assert band3.x0 == pytest.approx(2000, abs=2)  # lift core east face
    assert any("cut short" in f for f in res.flags[1])


def test_schedule_lists_each_mark_once():
    lay, r = _arrange(_doc(stair=True, lift=True))
    rows = arrange.arrange_beams(lay, r).schedule(1)
    marks = [m for m, _, _ in rows]
    assert marks == sorted(set(marks)) and {"RCB1", "RCB3", "RCB5", "PTB1", "PTB3"} <= set(marks)
    assert ("RCB1", "RCB1-(400x500)mm", "C30/37") in rows
