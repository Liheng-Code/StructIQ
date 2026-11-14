import ezdxf
import yaml

from structiq.drawing import layout, pipeline
from structiq.framing import arrange, rules

from test_framing_arrange import RULES, _doc


def _brain(tmp_path, rules_dict=None):
    brain = tmp_path / "brain"
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("rules")
    (brain / "02-Engineering Principles").mkdir()
    if rules_dict is not None:
        (brain / "02-Engineering Principles" / "beam-rules.yaml").write_text(yaml.safe_dump(rules_dict))
    (brain / "VERSION").write_text("9.9.9\n")
    return brain


def _project_dxf(tmp_path, doc):
    src = tmp_path / "PJR-2026-999_Test" / "01-Architect drawing" / "plan.dxf"
    src.parent.mkdir(parents=True)
    doc.saveas(src)
    return src


def _run(tmp_path, rules_dict, **kw):
    src = _project_dxf(tmp_path, _doc(stair=True, lift=True))
    return pipeline.run(src, brain_dir=_brain(tmp_path, rules_dict), **kw)


def test_beams_are_drawn_on_their_layers_with_tags(tmp_path):
    result = _run(tmp_path, RULES)
    msp = ezdxf.readfile(result.dxf).modelspace()
    lay = layout.extract_layout(_doc(stair=True, lift=True), beam_rules=rules.from_dict(RULES))
    assert len(msp.query("LWPOLYLINE[layer=='S-BEAM']")) == len(lay.beams.beams)
    assert len(msp.query("LWPOLYLINE[layer=='S-BEAM-PT']")) == len(lay.beams.bands) == 4
    tags = {t.dxf.text for t in msp.query("TEXT[layer=='S-BEAM-TXT']")}
    assert {"RCB1", "RCB3", "RCB5", "PTB1", "PTB3"} <= tags


def test_beam_tags_are_arial_1_5_mm_at_a3(tmp_path):
    result = _run(tmp_path, RULES)
    doc = ezdxf.readfile(result.dxf)
    scale = int(next(a.dxf.text for i in doc.layouts.get("A3-PLAN-1").query("INSERT")
                     if i.dxf.name == "STIQ-TITLEBLOCK" for a in i.attribs if a.dxf.tag == "SCALE").split(":")[1])
    for t in doc.modelspace().query("TEXT[layer=='S-BEAM-TXT']"):
        assert t.dxf.style == "STIQ-TEXT" and abs(t.dxf.height - 1.5 * scale) < 0.01


def test_sheet_carries_a_preliminary_framing_schedule(tmp_path):
    result = _run(tmp_path, RULES, plan_names={1: "4F-6F"})
    sheet = ezdxf.readfile(result.dxf).layouts.get("A3-PLAN-1")
    texts = [t.dxf.text for t in sheet.query("TEXT")]
    assert "Framing Schedule (PRELIMINARY)" in texts
    assert "RCB1-(400x500)mm" in texts and "PTB1-(2400x500)mm" in texts
    assert texts.count("4F-6F") >= 5  # the Level column
    tb = next(i for i in sheet.query("INSERT") if i.dxf.name == "STIQ-TITLEBLOCK")
    assert {a.dxf.tag: a.dxf.text for a in tb.attribs}["DRAWING_NAME"] == "4F-6F STRUCTURAL LAYOUT"


def test_report_has_a_beams_section_and_the_rules_status(tmp_path):
    text = _run(tmp_path, RULES, plan_names={1: "4F-6F"}).report_text
    assert "BEAMS (preliminary arrangement" in text and "Plan 1 (4F-6F)" in text
    assert "PT band" in text and "marked only, not designed" in text


def test_missing_or_draft_rules_leave_the_layout_without_beams(tmp_path):
    none = _run(tmp_path, None).report_text
    assert "BEAMS: not arranged" in none and "not found" in none
    other = tmp_path / "second"
    other.mkdir()
    draft = _run(other, {**RULES, "status": "draft"}).report_text
    assert "BEAMS: not arranged" in draft and "not marked 'status: approved'" in draft


def test_no_beams_flag_skips_the_arrangement(tmp_path):
    result = _run(tmp_path, RULES, beams=False)
    assert "BEAMS" not in result.report_text
    msp = ezdxf.readfile(result.dxf).modelspace()
    assert len(msp.query("LWPOLYLINE[layer=='S-BEAM']")) == 0
    sheet = ezdxf.readfile(result.dxf).layouts.get("A3-PLAN-1")
    assert not any(t.dxf.text.startswith("Framing Schedule") for t in sheet.query("TEXT"))


def test_framing_report_lists_roles_and_flags():
    lay = layout.extract_layout(_doc(slab=False), beam_rules=rules.from_dict(RULES))
    text = arrange.format_beams_report(lay.beams)
    assert "Plan 1: not arranged" in text and "! no slab outline" in text
