import ezdxf
import pytest

from structiq.drawing import split


def _plan(msp, x0, y0, title, n=60, w=20000, h=15000, layer="PLAN", block=None):
    """A made-up 'drawing': a frame, n small lines inside it and a title text."""
    if layer not in msp.doc.layers:
        msp.doc.layers.add(layer)
    msp.add_lwpolyline([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], close=True, dxfattribs={"layer": layer})
    for i in range(n):
        x = x0 + 500 + (i % 20) * 500  # lines overlap, like the walls of a real plan
        y = y0 + 800 + (i // 20) * 450
        msp.add_line((x, y), (x + 600, y + 400), dxfattribs={"layer": layer})
    if block:
        msp.add_blockref(block, (x0 + 1000, y0 + 1000), dxfattribs={"layer": layer})
    msp.add_text(title, height=300, dxfattribs={"insert": (x0 + 1000, y0 + 300), "layer": layer})


@pytest.fixture()
def combined(tmp_path):
    doc = ezdxf.new("R2018")
    doc.units = 4
    msp = doc.modelspace()
    for name in ("UNUSED-A", "UNUSED-B"):
        doc.layers.add(name)
    blk = doc.blocks.new("DOOR")
    blk.add_line((0, 0), (900, 0))
    doc.blocks.new("NEVER-USED").add_line((0, 0), (10, 10))
    _plan(msp, 0, 0, "Ground Floor Plan", block="DOOR")
    _plan(msp, 60000, 0, "1st Floor Plan", n=80)
    _plan(msp, 0, 50000, "SECTION A-A", n=70)
    msp.add_line((-300000, 5000), (400000, 5000))  # a huge stray line that must not join the drawings
    path = tmp_path / "combined.dxf"
    doc.saveas(path)
    return path


def test_each_drawing_is_found_with_its_title_and_the_stray_line_does_not_join_them(combined):
    views = split.find_views(ezdxf.readfile(combined), max_entity=50000)
    assert [v.title for v in views] == ["SECTION A-A", "Ground Floor Plan", "1st Floor Plan"]  # top to bottom, left to right
    assert [v.id for v in views] == [1, 2, 3]
    ground = views[1]
    assert ground.count >= 60 and 19000 <= ground.size[0] <= 21000


def test_small_clusters_are_ignored(combined):
    doc = ezdxf.readfile(combined)
    doc.modelspace().add_line((200000, 200000), (200100, 200100))
    assert len(split.find_views(doc, max_entity=50000)) == 3


def test_export_keeps_only_the_chosen_drawing_and_purges_what_is_unused(combined, tmp_path):
    views = split.find_views(ezdxf.readfile(combined), max_entity=50000)
    ground = next(v for v in views if v.title == "Ground Floor Plan")
    out = tmp_path / "out" / "ground.dxf"
    report = split.export_window(combined, ground.box, out, margin=500)
    doc = ezdxf.readfile(out)
    texts = [e.dxf.text for e in doc.modelspace().query("TEXT")]
    assert texts == ["Ground Floor Plan"]
    assert report.kept == len(doc.modelspace()) and report.dropped_outside > 100
    assert "DOOR" in doc.blocks and "NEVER-USED" not in doc.blocks  # used kept, unused purged
    assert "UNUSED-A" not in doc.layers and "PLAN" in doc.layers and "0" in doc.layers
    assert doc.audit().errors == []
    assert "kept" in report.summary()


def test_the_source_is_not_changed_and_the_output_must_be_a_different_file(combined, tmp_path):
    before = combined.read_bytes()
    views = split.find_views(ezdxf.readfile(combined), max_entity=50000)
    split.export_window(combined, views[0].box, tmp_path / "x.dxf")
    assert combined.read_bytes() == before
    with pytest.raises(ValueError, match="different file"):
        split.export_window(combined, views[0].box, combined)


def test_entities_crossing_the_window_edge_are_dropped_and_counted(combined, tmp_path):
    views = split.find_views(ezdxf.readfile(combined), max_entity=50000)
    ground = next(v for v in views if v.title == "Ground Floor Plan")
    x0, y0, x1, y1 = ground.box
    report = split.export_window(combined, (x0 + 5000, y0, x1, y1), tmp_path / "half.dxf")
    assert report.dropped_crossing >= 1  # the frame crosses the new left edge


def test_a_failed_save_leaves_no_file_behind(combined, tmp_path, monkeypatch):
    views = split.find_views(ezdxf.readfile(combined), max_entity=50000)

    def boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("ezdxf.document.Drawing.saveas", boom)
    out = tmp_path / "bad.dxf"
    with pytest.raises(OSError):
        split.export_window(combined, views[0].box, out)
    assert not out.exists() and not list(tmp_path.glob("*.part"))


def test_the_second_level_scan_finds_drawings_inside_one_sheet(tmp_path):
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    doc.layers.add("A")
    msp.add_lwpolyline([(0, 0), (90000, 0), (90000, 40000), (0, 40000)], close=True, dxfattribs={"layer": "A"})
    _plan(msp, 3000, 3000, "Ground floor plan", w=25000, h=20000)
    _plan(msp, 45000, 3000, "1st floor plan", w=25000, h=20000)
    path = tmp_path / "sheet.dxf"
    doc.saveas(path)
    top = split.find_views(ezdxf.readfile(path), max_entity=100000)
    inner = split.find_views(ezdxf.readfile(path), within=top[0].box)
    assert [v.title for v in inner] == ["Ground floor plan", "1st floor plan"]


def test_scan_prints_a_table_and_cli_exports(combined, tmp_path, capsys):
    assert split.main(["scan", str(combined), "--max-entity", "50000", "--preview", str(tmp_path / "p.png")]) == 0
    out = capsys.readouterr().out
    assert "3 drawing(s) found" in out and "Ground Floor Plan" in out and (tmp_path / "p.png").stat().st_size > 1000
    target = tmp_path / "g.dxf"
    assert split.main(["export", str(combined), "--view", "2", "--max-entity", "50000", "--out", str(target)]) == 0
    assert target.is_file()
    assert split.main(["export", str(combined), "--view", "9", "--max-entity", "50000", "--out", str(tmp_path / "n.dxf")]) == 1
