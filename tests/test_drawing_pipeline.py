import datetime

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
    assert "No RC wall segments identified" in layout.format_layout_report(lay)


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


def _title_values(sheet):
    (tb,) = [i for i in sheet.query("INSERT") if i.dxf.name == "STIQ-TITLEBLOCK"]
    return {a.dxf.tag: a.dxf.text for a in tb.attribs}


def test_each_plan_gets_an_a3_sheet_with_the_title_block_filled(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    result = pipeline.run(src, brain_dir=_brain(tmp_path), issue_date=datetime.date(2026, 11, 14))
    doc = ezdxf.readfile(result.dxf)
    assert [l.name for l in doc.layouts if l.name != "Model"] == ["A3-PLAN-1"]
    values = _title_values(doc.layouts.get("A3-PLAN-1"))
    assert values["PROJ_REF"] == "PJR-2026-999"
    assert values["REVISION"] == "R00"
    assert values["ISSUE_DATE"] == "14-NOV-2026" and values["DRAWN_BY"] == "STRUCTIQ"
    assert values["DRAWING_NAME"] == "STRUCTURAL LAYOUT PLAN 1"
    assert values["STAGE"] == "DRAFT FOR REVIEW" and values["CLIENT"] == ""
    assert values["SCALE"] == "1 : 75"  # 19 x 15 m with a 2 m margin fits at 1:75
    assert "SHEETS" in result.report_text and "A3-PLAN-1" in result.report_text


def test_sheet_viewport_is_at_the_fitted_scale_and_grid_uses_scaled_bubbles(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    doc = ezdxf.readfile(pipeline.run(src, brain_dir=_brain(tmp_path)).dxf)
    # the layout's own main viewport (id 1) comes first; ours is the last one
    vp = sorted(doc.layouts.get("A3-PLAN-1").query("VIEWPORT"), key=lambda v: v.dxf.id)[-1]
    # the viewport is cut to the plan (18 x 14 m at 1:75), so other plans stay out of the sheet
    assert (round(vp.dxf.width), round(vp.dxf.height)) == (240, 187)
    assert round(vp.dxf.view_height) == 14000
    bubbles = [i for i in doc.modelspace().query("INSERT") if i.dxf.name == "STIQ-GRID-BUBBLE"]
    assert len(bubbles) == 5 and all(b.dxf.xscale == 75 for b in bubbles)
    assert {a.dxf.text for b in bubbles for a in b.attribs} == {"A", "B", "C", "1", "2"}
    assert len(doc.modelspace().query("TEXT[layer=='S-GRID-TXT']")) == 0


def test_all_text_is_arial_and_prints_1_5_mm_at_a3(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    doc = ezdxf.readfile(pipeline.run(src, brain_dir=_brain(tmp_path)).dxf)
    texts = list(doc.modelspace().query("TEXT"))
    assert texts, "the slab label should be there"
    # plan sheet at 1:75 -> 1.5 mm x 75 = 112.5 model mm
    assert all(t.dxf.style == "STIQ-TEXT" and abs(t.dxf.height - 112.5) < 0.01 for t in texts)
    assert doc.styles.get("STIQ-TEXT").dxf.font.lower() == "arial.ttf"


def test_every_sheet_and_the_model_tab_open_zoomed_to_their_content(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    doc = ezdxf.readfile(pipeline.run(src, brain_dir=_brain(tmp_path)).dxf)
    main = sorted(doc.layouts.get("A3-PLAN-1").query("VIEWPORT"), key=lambda v: v.dxf.id)[0]
    assert 297 <= main.dxf.view_height <= 400
    vport = doc.viewports.get("*Active")[0]
    assert vport.dxf.height < 100000  # the plans are ~15 m: not the default or an absurd size


def test_file_opens_on_the_first_sheet_not_the_model_tab(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    doc = ezdxf.readfile(pipeline.run(src, brain_dir=_brain(tmp_path)).dxf)
    assert doc.header["$TILEMODE"] == 0
    active = doc.layouts.get_active_layout_key()
    assert doc.layouts.get("A3-PLAN-1").layout_key == active


def test_second_run_makes_second_revision_with_r01_in_the_title_block(tmp_path):
    src = _project_dxf(tmp_path, _doc())
    brain = _brain(tmp_path)
    pipeline.run(src, brain_dir=brain)
    second = pipeline.run(src, brain_dir=brain)
    values = _title_values(ezdxf.readfile(second.dxf).layouts.get("A3-PLAN-1"))
    assert values["REVISION"] == "R01"


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
