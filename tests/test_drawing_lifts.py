import ezdxf

from structiq.drawing import grids, layout, lifts, slabs

# Core wall body of the test drawing's lift, relative to its corner: 200 mm walls around an
# 1800 x 1810 shaft with a 1000 mm door opening on the right side.
CORE = [
    (0, 2210), (0, 0), (2200, 0), (2200, 575), (2000, 575), (2000, 200),
    (200, 200), (200, 2010), (2000, 2010), (2000, 1615), (2200, 1615), (2200, 2210),
]


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _doc(core=True):
    doc = ezdxf.new("R2018")
    doc.units = 4
    for name in ("GRID", "SLAB", "N- WALL HATCH BRICK", "N- WALL BRICK", "X-ELEVATOR"):
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
    msp.add_lwpolyline(_rect(-500, -500, 11500, 7500), close=True, dxfattribs={"layer": "SLAB"})

    car = doc.blocks.new("CAR")  # the lift car symbol, on an ELEVATOR layer
    car.add_line((0, 0), (800, 800), dxfattribs={"layer": "X-ELEVATOR"})
    lift = doc.blocks.new("LIFTBLK")
    lift.add_blockref("CAR", (900, 900))  # nested one level down
    if core:
        lift.add_lwpolyline(CORE, close=True, dxfattribs={"layer": "N- WALL HATCH BRICK"})
        bigger = [(x * 1.02 - 22, y * 1.02 - 22) for x, y in CORE]  # finishes outline, larger
        lift.add_lwpolyline(bigger, close=True, dxfattribs={"layer": "N- WALL BRICK"})
    msp.add_blockref("LIFTBLK", (5000, 1000))
    return doc


def _lifts(doc):
    g = grids.extract_grids(doc)
    s = slabs.extract_slabs(doc, g)
    return g, s, lifts.extract_lifts(doc, g, s)


def test_lift_found_from_its_car_symbol_even_when_nested():
    _, _, r = _lifts(_doc())
    (lift,) = r.lifts
    assert lift.block == "LIFTBLK" and len(lift.core) == 12


def test_core_wall_body_cavity_and_thickness():
    _, _, r = _lifts(_doc())
    (lift,) = r.lifts
    assert round(lift.thickness) == 200
    cw, ch = lift.cavity[2] - lift.cavity[0], lift.cavity[3] - lift.cavity[1]
    assert (round(cw), round(ch)) == (1800, 1810)
    # the smaller outline (wall body) is used, not the larger finishes outline
    assert round(lift.outer[2] - lift.outer[0]) == 2200


def test_lift_is_related_to_the_grid_and_slab():
    _, _, r = _lifts(_doc())
    (lift,) = r.lifts
    assert lift.bay == ("B-C", "1-2") and lift.inside_slab is True


def test_lift_block_without_a_core_outline_is_counted_not_drawn():
    _, _, r = _lifts(_doc(core=False))
    assert r.lifts == [] and r.without_core == 1


def test_no_lift_message():
    doc = _doc()
    for e in list(doc.modelspace().query("INSERT")):
        if e.dxf.name == "LIFTBLK":
            doc.modelspace().delete_entity(e)
    _, _, r = _lifts(doc)
    assert "No lift detected" in lifts.format_lifts_report(r)


def test_report_and_drawing_of_the_core(tmp_path):
    lay = layout.extract_layout(_doc())
    text = layout.format_layout_report(lay)
    assert "LIFTS" in text and "core wall 200 mm thick" in text
    assert "Shaft is inside the slab outline" in text
    out = layout.write_layout(lay, tmp_path / "l.dxf")
    msp = ezdxf.readfile(out).modelspace()
    core = [e for e in msp.query("LWPOLYLINE[layer=='S-WALL']") if len(e) == 12]
    assert len(core) == 1  # the core wall is drawn as an RC wall
    assert len(msp.query("LWPOLYLINE[layer=='S-OPEN']")) == 1  # the clear shaft
    label = [t for t in msp.query("TEXT") if t.dxf.text == "LIFT"]
    assert len(label) == 1 and label[0].dxf.style == "STIQ-TEXT"
