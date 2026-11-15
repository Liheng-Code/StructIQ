import copy
import json

import pytest
import yaml
from docx import Document
from qaqc_fixtures import anchorage_inputs, design_basis

from structiq.calc.runs import anchorage_check
from structiq.qaqc import docgen

SPEC = {
    "doc": {"type": "specification", "number": "TB-STR-SP-001", "title": "Structural specification"},
    "sections": [
        {"title": "General", "blocks": [
            {"type": "paragraph", "text": "Scope of the test specification."},
            {"type": "clause", "text": "Concrete shall be of the stated class.", "source": "test source"},
        ]},
        {"title": "Materials", "blocks": [{"type": "db_materials"}, {"type": "db_standards"}]},
    ],
}
REPORT = {
    "doc": {"type": "calculation-report", "number": "TB-STR-CR-001", "title": "Anchorage report"},
    "sections": [{"title": "Anchorage", "blocks": [{"type": "calc", "ref": "CALC-TEST-001"}]}],
}


def _text(path):
    d = Document(path)
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        parts += [c.text for r in t.rows for c in r.cells]
    for s in d.sections:
        parts += [p.text for p in s.header.paragraphs]
    return "\n".join(parts)


@pytest.fixture()
def results(tmp_path):
    inp = tmp_path / "in.yaml"
    inp.write_text(yaml.safe_dump(anchorage_inputs()), encoding="utf-8")
    out = tmp_path / "r.json"
    assert anchorage_check.main([str(inp), str(out)]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    return {res["id"]: res}


def test_specification_is_stamped_draft_and_numbered(tmp_path):
    res = docgen.build(SPEC, design_basis(), {}, tmp_path / "spec")
    text = _text(res["docx"])
    assert "DRAFT - NOT FOR ISSUE" in text
    assert "PJR-2026-999" in text  # project code comes from the design basis
    assert "1.1" in text
    assert "Confirm the concrete class with the client" in text  # open items always listed


def test_report_has_the_calculation_and_blank_signoff(tmp_path, results):
    res = docgen.build(REPORT, design_basis(), results, tmp_path / "rep")
    assert "CALC-TEST-001" in _text(res["docx"])
    ctrl = {r.cells[0].text: r.cells[1].text for r in Document(res["docx"]).tables[0].rows}
    assert ctrl["Checked by"] == "" and ctrl["Approved by"] == ""


def test_clause_without_a_source_stops_the_build(tmp_path):
    bad = copy.deepcopy(SPEC)
    bad["sections"][0]["blocks"].append({"type": "clause", "text": "Unsourced requirement."})
    with pytest.raises(docgen.BuildError):
        docgen.build(bad, design_basis(), {}, tmp_path / "bad")


def test_a_calc_block_without_results_stops_the_build(tmp_path):
    with pytest.raises(docgen.BuildError):
        docgen.build(REPORT, design_basis(), {}, tmp_path / "bad")


def test_approving_the_basis_removes_the_stamp_but_never_fills_signoff(tmp_path):
    db = design_basis()
    db["approval"]["status"] = "APPROVED"
    res = docgen.build(SPEC, db, {}, tmp_path / "appr")
    assert "DRAFT - NOT FOR ISSUE" not in _text(res["docx"])
    ctrl = {r.cells[0].text: r.cells[1].text for r in Document(res["docx"]).tables[0].rows}
    assert ctrl["Approved by"] == ""


@pytest.mark.requires_soffice
def test_pdf_is_produced_when_libreoffice_is_available(tmp_path):
    import pathlib

    res = docgen.build(SPEC, design_basis(), {}, tmp_path / "pdf")
    assert pathlib.Path(res["pdf"]).stat().st_size > 5000
