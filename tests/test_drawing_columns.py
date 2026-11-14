import ezdxf

from structiq.drawing import columns, grids


def _rect(cx, cy, w, h):
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def _doc():
    """Grid A,B,C x 1,2 with columns at A1, C1, C2 (none at A2, B1, B2) plus distractors."""
    doc = ezdxf.new("R2018")
    doc.layers.add("GRID")
    msp = doc.modelspace()
    ax = doc.blocks.new("AXIS BUBBLE")
    ax.add_attdef("AXIS", insert=(0, 0), height=250)
    xs, ys = [0, 4000, 11000], [0, 7000]
    for x, name in zip(xs, "ABC"):
        msp.add_line((x, -2000), (x, 9000), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (x, 9500)).add_auto_attribs({"AXIS": name})
    for y, name in zip(ys, "12"):
        msp.add_line((-2000, y), (13000, y), dxfattribs={"layer": "GRID"})
        msp.add_blockref("AXIS BUBBLE", (-2500, y)).add_auto_attribs({"AXIS": name})

    col = doc.blocks.new("ANY NAME")  # solid hatch + outline = column
    col.add_lwpolyline(_rect(0, 0, 500, 600), close=True)
    col.add_hatch(color=7).paths.add_polyline_path(_rect(0, 0, 500, 600), is_closed=True)
    for x, y in [(0, 0), (11000, 0), (11000, 7000)]:
        msp.add_blockref("ANY NAME", (x, y))

    wall = doc.blocks.new("BRICK")  # patterned hatch, same size: must NOT count
    h = wall.add_hatch(color=7)
    h.set_pattern_fill("ANSI31", scale=10)
    h.paths.add_polyline_path(_rect(0, 0, 500, 600), is_closed=True)
    msp.add_blockref("BRICK", (4000, 7000))

    text = doc.blocks.new("LABELLED")  # has text: must NOT count
    text.add_hatch(color=7).paths.add_polyline_path(_rect(0, 0, 500, 600), is_closed=True)
    text.add_text("X")
    msp.add_blockref("LABELLED", (4000, 0))

    big = doc.blocks.new("SLABISH")  # too large: must NOT count
    big.add_hatch(color=7).paths.add_polyline_path(_rect(0, 0, 5000, 5000), is_closed=True)
    msp.add_blockref("SLABISH", (6000, 3500))
    return doc


def _run(doc):
    g = grids.extract_grids(doc)
    return g, columns.extract_columns(doc, g)


def test_finds_only_solid_column_blocks_on_grid():
    _, r = _run(_doc())
    assert sorted(c.grid_ref for c in r.columns) == ["A1", "C1", "C2"]
    assert all(c.on_grid for c in r.columns)
    assert all(round(c.width) == 500 and round(c.height) == 600 for c in r.columns)


def test_missing_intersections_listed():
    _, r = _run(_doc())
    (missing,) = r.missing.values()
    assert sorted(missing) == ["A2", "B1", "B2"]


def test_off_grid_column_flagged_with_offset():
    doc = _doc()
    doc.modelspace().add_blockref("ANY NAME", (4400, 7000))  # 400 mm off line B2
    _, r = _run(doc)
    off = [c for c in r.columns if not c.on_grid]
    assert len(off) == 1 and off[0].grid_ref == "B2"
    assert round(off[0].dx) == 400 and round(off[0].dy) == 0


def test_direct_polyline_on_column_layer():
    doc = _doc()
    doc.layers.add("Column")
    doc.modelspace().add_lwpolyline(
        _rect(4000, 0, 400, 400), close=True, dxfattribs={"layer": "Column"}
    )
    _, r = _run(doc)
    # a bare polyline has no solid hatch, but sits on a column layer: counted once
    assert "B1" in [c.grid_ref for c in r.columns]


def test_write_layout_dxf_has_column_layers(tmp_path):
    g, r = _run(_doc())
    out = columns.write_layout_dxf(g, r, tmp_path / "layout.dxf")
    doc = ezdxf.readfile(out)
    assert {"S-GRID", "S-COLS", "S-COLS-TXT"} <= {la.dxf.name for la in doc.layers}
    assert len(doc.modelspace().query("LWPOLYLINE[layer=='S-COLS']")) == 3
