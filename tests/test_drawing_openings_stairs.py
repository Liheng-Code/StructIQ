import ezdxf

from structiq.drawing import columns, grids, layout, openings, slabs, stairs, walls


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _base_doc():
    """Grid A,B,C x 1,2 (x 0/4000/11000, y 0/7000), mm units, slab covering everything."""
    doc = ezdxf.new("R2018")
    doc.units = 4
    doc.layers.add("GRID")
    doc.layers.add("SLAB")
    msp = doc.modelspace()
    ax = doc.blocks.new("AXIS BUBBLE")
    ax.add_attdef("AXIS", insert=(0, 0), height=250)
    for x, name in zip([0, 4000, 11000], "ABC"):
        msp.add_line((x, -2000), (x, 9000), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (x, 9500)).add_auto_attribs({"AXIS": name})
    for y, name in zip([0, 7000], "12"):
        msp.add_line((-2000, y), (13000, y), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (-2500, y)).add_auto_attribs({"AXIS": name})
    msp.add_lwpolyline(_rect(-500, -500, 11500, 7500), close=True, dxfattribs={"layer": "SLAB"})
    return doc


def _stair_block(doc, name="STAIRBLK", flights=2, treads=12, with_text=True):
    blk = doc.blocks.new(name)
    for f in range(flights):
        x0 = f * 1300  # 1000 wide flights, 300 gap
        for i in range(treads):
            blk.add_lwpolyline(
                _rect(x0, i * 280, x0 + 1000, (i + 1) * 280),
                close=True,
                dxfattribs={"layer": "STAIR-LAYER"},
            )
    blk.add_lwpolyline([(0, -500), (2300, -500)], dxfattribs={"layer": "STAIR-LAYER"})  # landing edge
    if with_text:
        blk.add_mtext("UP")
    return blk


def _pipeline(doc):
    g = grids.extract_grids(doc)
    s = slabs.extract_slabs(doc, g)
    return g, s


def test_two_flight_stair_detected():
    doc = _base_doc()
    _stair_block(doc)
    doc.modelspace().add_blockref("STAIRBLK", (1000, 2000), dxfattribs={"layer": "0"})
    g, s = _pipeline(doc)
    r = stairs.extract_stairs(doc, g, s)
    (st,) = r.stairs
    assert len(st.flights) == 2 and all(f.treads == 12 for f in st.flights)
    assert all(round(f.width) == 1000 and round(f.depth) == 280 for f in st.flights)
    # footprint: 2300 wide, treads 3360 + 500 landing edge below
    assert round(st.footprint[2] - st.footprint[0]) == 2300
    assert round(st.footprint[3] - st.footprint[1]) == 3860
    assert st.bay == ("A-B", "1-2")
    assert st.inside_slab is True


def test_slightly_skewed_tread_rectangles_still_count():
    doc = _base_doc()
    blk = doc.blocks.new("DRIFT")
    for i in range(8):  # corners drift by 0.14 mm like the architect's copy-pasted stair
        y = i * 280
        blk.add_lwpolyline(
            [(0, y + 0.06), (1000, y + 0.2), (1000, y + 280.2), (0, y + 280.06)], close=True
        )
    doc.modelspace().add_blockref("DRIFT", (1000, 2000))
    g, s = _pipeline(doc)
    (st,) = stairs.extract_stairs(doc, g, s).stairs
    assert st.flights[0].treads == 8


def test_rotated_stair_found_in_wcs():
    doc = _base_doc()
    _stair_block(doc)
    doc.modelspace().add_blockref(
        "STAIRBLK", (6000, 2000), dxfattribs={"layer": "0", "rotation": 90}
    )
    g, s = _pipeline(doc)
    (st,) = stairs.extract_stairs(doc, g, s).stairs
    assert {f.orientation for f in st.flights} == {"H"}
    assert all(f.treads == 12 for f in st.flights)


def test_too_few_treads_or_skewed_rotation_not_a_stair():
    doc = _base_doc()
    _stair_block(doc, "SHORT", flights=1, treads=3)
    doc.modelspace().add_blockref("SHORT", (1000, 2000))
    _stair_block(doc, "SKEW")
    doc.modelspace().add_blockref("SKEW", (6000, 2000), dxfattribs={"rotation": 30})
    g, s = _pipeline(doc)
    r = stairs.extract_stairs(doc, g, s)
    assert r.stairs == [] and r.skewed_blocks == 1


def _wall(x0, y0, x1, y1):
    return walls.Wall(
        1, "H" if x1 - x0 >= y1 - y0 else "V", x0, y0, x1, y1,
        min(x1 - x0, y1 - y0), max(x1 - x0, y1 - y0), "WALL", "brick", None,
    )


def _openings(doc, wall_list):
    g, s = _pipeline(doc)
    cols = columns.ColumnResult([], {}, 0)
    return openings.extract_openings(doc, g, walls.WallResult(wall_list), cols, s)


def _box_walls(x0, y0, x1, y1, t=120):
    """Four wall boxes whose inner faces form the cell x0..x1 x y0..y1."""
    return [
        _wall(x0 - t, y0 - t, x1 + t, y0),  # bottom
        _wall(x0 - t, y1, x1 + t, y1 + t),  # top
        _wall(x0 - t, y0, x0, y1),  # left
        _wall(x1, y0, x1 + t, y1),  # right
    ]


def test_bounded_shaft_gets_size_and_slab_flag():
    doc = _base_doc()
    doc.modelspace().add_mtext("MEP", dxfattribs={"insert": (2000, 3500), "attachment_point": 5})
    r = _openings(doc, _box_walls(1000, 3000, 3000, 4000))
    (o,) = r.openings
    assert o.kind == "shaft" and o.bounded
    assert (round(o.size[0]), round(o.size[1])) == (2000, 1000)
    assert o.inside_slab is True and o.near_ref in {"A1", "B1", "A2", "B2"}
    assert "no void drawn" in openings.format_openings_report(r)


def test_two_labels_in_one_cell_are_flagged():
    doc = _base_doc()
    msp = doc.modelspace()
    msp.add_mtext("MEP", dxfattribs={"insert": (1800, 3500), "attachment_point": 5})
    msp.add_mtext("PLUMBING", dxfattribs={"insert": (2200, 3500), "attachment_point": 5})
    r = _openings(doc, _box_walls(1000, 3000, 3000, 4000))
    assert "shares its cell" in openings.format_openings_report(r)


def test_unbounded_label_reported_without_size():
    doc = _base_doc()
    doc.modelspace().add_mtext("PLUMBING", dxfattribs={"insert": (2000, 3500)})
    r = _openings(doc, [])
    (o,) = r.openings
    assert not o.bounded and o.size is None
    assert "label only" in openings.format_openings_report(r)


def test_room_label_is_a_room_not_an_opening():
    doc = _base_doc()
    doc.modelspace().add_mtext("MEP ROOM", dxfattribs={"insert": (2000, 3500), "attachment_point": 5})
    r = _openings(doc, _box_walls(1000, 3000, 3000, 4000))
    (o,) = r.openings
    assert o.kind == "room"
    assert "no void drawn" not in openings.format_openings_report(r)


def test_layout_writes_stair_and_opening_layers(tmp_path):
    doc = _base_doc()
    _stair_block(doc)
    doc.modelspace().add_blockref("STAIRBLK", (1000, 2000), dxfattribs={"layer": "0"})
    doc.modelspace().add_mtext("MEP", dxfattribs={"insert": (8000, 3500)})
    lay = layout.extract_layout(doc)
    out = layout.write_layout(lay, tmp_path / "layout.dxf")
    names = {la.dxf.name for la in ezdxf.readfile(out).layers}
    assert {"S-STAIR", "S-OPEN-CHECK", "S-SLAB-EDGE"} <= names
    text = layout.format_layout_report(lay, source="test.dwg")
    assert "STAIRS" in text and "OPENINGS" in text
