import ezdxf

from structiq.drawing import grids, layout, slabs, walls


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _doc():
    """Grid A,B,C x 1,2 (x 0/4000/11000, y 0/7000) plus walls and a slab."""
    doc = ezdxf.new("R2018")
    doc.units = 4  # mm
    for name in ("GRID", "N- WALL HATCH BRICK", "N-WALL BRICK", "002 Structural Wall", "SLAB"):
        doc.layers.add(name)
    msp = doc.modelspace()
    ax = doc.blocks.new("AXIS BUBBLE")
    ax.add_attdef("AXIS", insert=(0, 0), height=250)
    for x, name in zip([0, 4000, 11000], "ABC"):
        msp.add_line((x, -2000), (x, 9000), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (x, 9500)).add_auto_attribs({"AXIS": name})
    for y, name in zip([0, 7000], "12"):
        msp.add_line((-2000, y), (13000, y), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (-2500, y)).add_auto_attribs({"AXIS": name})

    wall = doc.blocks.new("ANYWALL")  # 5000 x 120 horizontal wall, centred on origin
    wall.add_lwpolyline(_rect(-2500, -60, 2500, 60), close=True)
    wall.add_hatch(color=7).paths.add_polyline_path(_rect(-2500, -60, 2500, 60), is_closed=True)
    msp.add_blockref("ANYWALL", (5000, 7000), dxfattribs={"layer": "N- WALL HATCH BRICK"})  # on grid 2
    msp.add_blockref(
        "ANYWALL", (6000, 3000), dxfattribs={"layer": "N- WALL HATCH BRICK", "rotation": 90}
    )  # vertical, 2000 mm from B -> off grid

    stub = doc.blocks.new("STUB")  # 316 x 587: too small to be a wall
    stub.add_lwpolyline(_rect(0, 0, 316, 587), close=True)
    msp.add_blockref("STUB", (1000, 1000), dxfattribs={"layer": "002 Structural Wall"})

    msp.add_lwpolyline(_rect(8000, 2000, 11000, 2200), close=True, dxfattribs={"layer": "N-WALL BRICK"})
    msp.add_lwpolyline(
        [(0, 0), (500, 0), (500, 500), (250, 800), (0, 500)],
        close=True,
        dxfattribs={"layer": "N-WALL BRICK"},
    )  # pentagon: not a rectangle

    msp.add_lwpolyline(_rect(-500, -500, 11500, 7500), close=True, dxfattribs={"layer": "SLAB"})
    msp.add_circle((2000, 3000), 400, dxfattribs={"layer": "SLAB"})
    return doc


def _walls(doc):
    g = grids.extract_grids(doc)
    return g, walls.extract_walls(doc, g)


def test_block_and_direct_walls_found():
    _, r = _walls(_doc())
    assert len(r.walls) == 3
    assert {round(w.thickness) for w in r.walls} == {120, 200}
    assert all(w.kind == "brick" for w in r.walls)


def test_wall_on_gridline_and_off_gridline():
    _, r = _walls(_doc())
    on = [w for w in r.walls if w.grid_line is not None]
    assert [(w.orientation, w.grid_line) for w in on] == [("H", "2")]
    vertical = [w for w in r.walls if w.orientation == "V"]
    assert len(vertical) == 1 and vertical[0].grid_line is None


def test_small_structural_object_reported_not_extracted():
    _, r = _walls(_doc())
    assert [(layer, w, h) for _, layer, w, h in r.rejected_structural] == [
        ("002 Structural Wall", 316, 587)
    ]
    assert not any(w.kind == "structural" for w in r.walls)


def test_non_wall_shaped_block_on_wall_layer_counted():
    doc = _doc()
    blk = doc.blocks.new("SQUARISH")  # 2000 x 2000: thicker than any wall
    blk.add_lwpolyline(_rect(0, 0, 2000, 2000), close=True)
    doc.modelspace().add_blockref("SQUARISH", (5000, 2000), dxfattribs={"layer": "N-WALL BRICK"})
    _, r = _walls(doc)
    assert r.not_wall_shaped == 1 and len(r.walls) == 3


def test_non_rectangular_wall_polyline_counted():
    _, r = _walls(_doc())
    assert r.non_rectangular == 1


def test_slab_outline_area_and_coverage():
    doc = _doc()
    g = grids.extract_grids(doc)
    r = slabs.extract_slabs(doc, g)
    (s,) = r.slabs
    assert s.closed and s.orthogonal
    assert round(s.area_m2, 1) == 96.0  # 12000 x 8000 mm
    assert sorted(s.covers) == ["A1", "A2", "B1", "B2", "C1", "C2"]
    assert len(r.features) == 1 and r.features[0].radius == 400


def test_open_slab_outline_flagged_not_repaired():
    doc = ezdxf.new("R2018")
    doc.units = 4
    doc.layers.add("GRID")
    doc.layers.add("SLAB")
    msp = doc.modelspace()
    for x in (0, 4000):
        msp.add_line((x, -1000), (x, 5000), dxfattribs={"layer": "GRID"})
    for y in (0, 3000):
        msp.add_line((-1000, y), (5000, y), dxfattribs={"layer": "GRID"})
    msp.add_lwpolyline([(0, 0), (4000, 0), (4000, 3000), (0, 2000)], dxfattribs={"layer": "SLAB"})
    r = slabs.extract_slabs(doc, grids.extract_grids(doc))
    (s,) = r.slabs
    assert not s.closed and s.area_m2 is None and s.covers == []


def test_plan_without_slab_listed():
    doc = _doc()
    for e in list(doc.modelspace().query("LWPOLYLINE[layer=='SLAB']")):
        doc.modelspace().delete_entity(e)
    r = slabs.extract_slabs(doc, grids.extract_grids(doc))
    assert r.plans_without_slab == [1]


def test_layout_writes_all_structural_layers(tmp_path):
    lay = layout.extract_layout(_doc())
    out = layout.write_layout(lay, tmp_path / "layout.dxf")
    names = {la.dxf.name for la in ezdxf.readfile(out).layers}
    assert {"S-GRID", "S-WALL", "S-SLAB-EDGE", "S-SLAB-CHECK"} <= names
    assert "S-WALL-INFILL" not in names  # brick walls are never drawn
    text = layout.format_layout_report(lay, source="test.dwg")
    assert "DRAFT" in text and "WALLS" in text and "SLABS" in text
