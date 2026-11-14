import ezdxf

from structiq.drawing import grids


def _doc_with_grid(offsets=(0.0,)):
    """3 vertical (A,B,C) x 2 horizontal (1,2) grid per offset; labels are block attributes."""
    doc = ezdxf.new("R2018")
    blk = doc.blocks.new("COLUNM AXIS")
    blk.add_attdef("AXIS", insert=(0, 0), height=250)
    msp = doc.modelspace()
    doc.layers.add("GRID")
    for offset_x in offsets:
        for x, name in zip([0, 4000, 11000], "ABC"):
            msp.add_line((offset_x + x, -2000), (offset_x + x, 9000), dxfattribs={"layer": "GRID"})
            msp.add_blockref("COLUNM AXIS", (offset_x + x, 9500)).add_auto_attribs({"AXIS": name})
        for y, name in zip([0, 7000], "12"):
            msp.add_line((offset_x - 2000, y), (offset_x + 13000, y), dxfattribs={"layer": "GRID"})
            msp.add_blockref("COLUNM AXIS", (offset_x - 2500, y)).add_auto_attribs({"AXIS": name})
    return doc


def test_extracts_lines_labels_and_spacing():
    result = grids.extract_grids(_doc_with_grid())
    assert len(result.clusters) == 1
    c = result.clusters[0]
    assert [ln.label for ln in c.vertical] == ["A", "B", "C"]
    assert [ln.label for ln in c.horizontal] == ["1", "2"]
    assert c.spacings(c.vertical) == [4000.0, 7000.0]
    assert c.spacings(c.horizontal) == [7000.0]
    assert c.warnings == [] and result.unmatched_labels == []


def test_two_plans_become_two_clusters():
    result = grids.extract_grids(_doc_with_grid(offsets=(0.0, 50000.0)))
    assert len(result.clusters) == 2
    assert all([ln.label for ln in c.vertical] == ["A", "B", "C"] for c in result.clusters)


def test_diagonal_and_wrong_layer_lines_ignored():
    doc = _doc_with_grid()
    msp = doc.modelspace()
    msp.add_line((0, 0), (5000, 5000), dxfattribs={"layer": "GRID"})
    msp.add_line((-9000, 100), (9000, 100), dxfattribs={"layer": "WALL"})
    result = grids.extract_grids(doc)
    assert len(result.clusters[0].vertical) == 3
    assert len(result.clusters[0].horizontal) == 2


def test_missing_label_is_warned():
    doc = _doc_with_grid()
    for ins in list(doc.modelspace().query("INSERT")):
        if ins.attribs[0].dxf.text == "B":
            doc.modelspace().delete_entity(ins)
    result = grids.extract_grids(doc)
    assert any("no label" in w for w in result.clusters[0].warnings)


def test_write_grid_dxf_has_structural_layers(tmp_path):
    result = grids.extract_grids(_doc_with_grid())
    out = grids.write_grid_dxf(result, tmp_path / "grid.dxf")
    doc = ezdxf.readfile(out)
    assert "S-GRID" in doc.layers and "S-GRID-TXT" in doc.layers
    assert len(doc.modelspace().query("LINE")) == 5
    assert len(doc.modelspace().query("TEXT")) == 5
