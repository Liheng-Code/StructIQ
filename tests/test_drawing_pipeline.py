import ezdxf
import pytest

from structiq.drawing import layout, pipeline


def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _doc(with_rc=False):
    doc = ezdxf.new("R2018")
    doc.units = 4
    for name in ("GRID", "SLAB", "N-WALL BRICK", "RC WALL"):
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
    msp.add_lwpolyline(_rect(8000, 2000, 11000, 2200), close=True, dxfattribs={"layer": "N-WALL BRICK"})
    if with_rc:
        msp.add_lwpolyline(_rect(4000, 3000, 7000, 3300), close=True, dxfattribs={"layer": "RC WALL"})
    return doc


def _brain(tmp_path, version="1.2.3"):
    brain = tmp_path / "brain"
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("rules")
    (brain / "VERSION").write_text(version + "\n")
    return brain


def _project_dxf(tmp_path, doc):
    src = tmp_path / "PJR-2026-999_Test" / "01-Architect drawing" / "plan.dxf"
    src.parent.mkdir(parents=True)
    doc.saveas(src)
    return src


def test_only_rc_walls_are_drawn_brick_is_only_counted(tmp_path):
    lay = layout.extract_layout(_doc(with_rc=True), rc_layer_pattern=r"RC WALL")
    out = layout.write_layout(lay, tmp_path / "l.dxf")
    msp = ezdxf.readfile(out).modelspace()
    assert len(msp.query("LWPOLYLINE[layer=='S-WALL']")) == 1
    assert len(msp.query("LWPOLYLINE[layer=='S-WALL-INFILL']")) == 0
    assert any(w.kind == "brick" for w in lay.walls.walls)  # still extracted, still a barrier
    text = layout.format_layout_report(lay)
    assert "1 RC wall segment(s) drawn" in text and "not drawn" in text


def test_no_rc_layer_means_no_walls_drawn_and_a_clear_flag(tmp_path):
    lay = layout.extract_layout(_doc(with_rc=False))
    out = layout.write_layout(lay, tmp_path / "l.dxf")
    assert len(ezdxf.readfile(out).modelspace().query("LWPOLYLINE[layer=='S-WALL']")) == 0
    assert "No RC walls identified anywhere" in layout.format_layout_report(lay)


def test_pipeline_writes_next_revision_each_run_and_never_overwrites(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    brain = _brain(tmp_path)
    first = pipeline.run(src, brain_dir=brain)
    second = pipeline.run(src, brain_dir=brain)
    assert (first.revision, second.revision) == (0, 1)
    out_dir = tmp_path / "PJR-2026-999_Test" / "02-Structural Drawing"
    names = sorted(p.name for p in out_dir.iterdir())
    assert names == [
        "S-LAYOUT plan Rev 00-report.txt",
        "S-LAYOUT plan Rev 00.dxf",
        "S-LAYOUT plan Rev 01-report.txt",
        "S-LAYOUT plan Rev 01.dxf",
    ]
    assert "Core Brain version: 1.2.3" in first.report_text
    assert first.report_text.splitlines()[0].startswith("DRAFT")


def test_pipeline_stops_when_brain_unreadable(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    with pytest.raises(pipeline.BrainNotFoundError):
        pipeline.run(src, brain_dir=tmp_path / "missing")
    assert not (tmp_path / "PJR-2026-999_Test" / "02-Structural Drawing").exists()


def test_pipeline_rejects_other_file_types(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        pipeline.run(f, brain_dir=_brain(tmp_path))
