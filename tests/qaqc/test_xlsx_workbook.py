import json
import shutil

import pytest
import yaml
from openpyxl import load_workbook
from qaqc_fixtures import anchorage_inputs, design_basis

from structiq.calc.rc import ec2_anchorage as a
from structiq.calc.runs import anchorage_check
from structiq.qaqc.xlsx import anchorage_workbook as bw
from structiq.qaqc.xlsx import verify as vw


def test_hand_values_typed_into_the_checks_sheet_agree_with_the_library():
    fyd = a.fyd(390)
    good12 = a.bond_stress("C30/37", True, 12).fbd
    lib = {
        "T1": a.fctd("C30/37"),
        "T2": fyd,
        "T3": good12,
        "T4": a.bond_stress("C30/37", False, 12).fbd,
        "T5": a.lb_rqd(12, fyd, good12),
        "T6": a.lb_rqd(12, fyd, a.bond_stress("C30/37", False, 12).fbd),
        "T7": 1.5 * a.lb_rqd(12, fyd, good12),
        "T8": a.lb_rqd(25, fyd, a.bond_stress("C30/37", True, 25).fbd),
    }
    for tid, _desc, expected, tol, _ref, _how in bw.HAND:
        assert lib[tid] == pytest.approx(expected, abs=max(tol, 1e-6)), tid


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wb")
    path = tmp / "base.xlsx"
    bw.build(anchorage_inputs(), design_basis(), path)
    return path


def test_workbook_builds_with_formulas_checks_and_blank_signoff(built):
    wb = load_workbook(built)
    assert {"Cover", "Inputs", "Calc", "Outputs", "Checks", "Log"} <= set(wb.sheetnames)
    formulas = [c.value for row in wb["Calc"].iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith("=")]
    assert len(formulas) > 20  # live formulas, not pasted numbers
    cover = {str(r[0].value): r[1].value for r in wb["Cover"].iter_rows() if r[0].value}
    assert cover.get("Checked by") in (None, "") and cover.get("Approved by") in (None, "")
    assert wb["Inputs"].data_validations.dataValidation


@pytest.fixture()
def results(tmp_path):
    inp = tmp_path / "in.yaml"
    inp.write_text(yaml.safe_dump(anchorage_inputs()), encoding="utf-8")
    out = tmp_path / "r.json"
    anchorage_check.main([str(inp), str(out)])
    return json.loads(out.read_text(encoding="utf-8"))


@pytest.mark.requires_soffice
def test_recalculated_workbook_verifies_and_ties_out_to_the_report(built, tmp_path, results):
    p = tmp_path / "ok.xlsx"
    shutil.copyfile(built, p)
    out = vw.verify(p, results)
    assert out["problems"] == []
    assert out["checks_passed"] == 8
    assert out["cover_status"] == "CROSS-CHECKED - NOT ENGINEER-REVIEWED"


@pytest.mark.requires_soffice
def test_a_typed_number_in_calc_is_detected(built, tmp_path):
    p = tmp_path / "typed.xlsx"
    shutil.copyfile(built, p)
    wb = load_workbook(p)
    wb["Calc"]["E11"] = 339.1
    wb.save(p)
    assert any("typed number" in x for x in vw.verify(p)["problems"])


@pytest.mark.requires_soffice
def test_a_wrong_hand_value_makes_the_workbook_fail(built, tmp_path):
    p = tmp_path / "bad.xlsx"
    shutil.copyfile(built, p)
    wb = load_workbook(p)
    wb["Checks"]["C9"] = 400.0
    wb.save(p)
    out = vw.verify(p)
    assert any("FAILS" in x for x in out["problems"])
    assert out["cover_status"].startswith("CHECKS FAILING")
