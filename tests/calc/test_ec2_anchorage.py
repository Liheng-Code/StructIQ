"""Hand values, worked independently of the code (C30/37, fyk 390). Ported from SDSA test_calc_report_docgen."""

import json

import pytest
import yaml

from structiq.calc.rc import ec2_anchorage as a
from structiq.calc.runs import anchorage_check


def test_fctd():
    assert a.fctd("C30/37") == pytest.approx(2.0 / 1.5, abs=1e-6)


def test_bond_stress_good_and_poor():
    assert a.bond_stress("C30/37", True, 12).fbd == pytest.approx(3.0, abs=1e-6)  # 2.25 * 1 * 1 * 1.3333
    assert a.bond_stress("C30/37", False, 12).fbd == pytest.approx(2.1, abs=1e-6)  # x 0.7


def test_eta2_large_bars():
    assert a.bond_stress("C30/37", True, 40).eta2 == pytest.approx(0.92)


def test_lb_rqd_hand_value():
    fyd = 390 / 1.15  # 339.1304 MPa
    assert a.fyd(390) == pytest.approx(fyd, abs=1e-4)
    assert a.lb_rqd(12, fyd, 3.0) == pytest.approx(339.13, abs=0.01)


def test_untabulated_class_needs_an_explicit_value():
    with pytest.raises(KeyError):
        a.fctd("C90/105")
    assert a.fctd("C90/105", 3.0) == pytest.approx(2.0)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        a.bond_stress("C30/37", True, 0)
    with pytest.raises(ValueError):
        a.lb_rqd(12, 339, 0)


def _inputs(tmp_path, **over):
    data = {
        "id": "CALC-TEST-001",
        "title": "Synthetic anchorage run",
        "concrete_class": "C30/37",
        "fyk": 390,
        "bars": [12],
        "sources": {"concrete": "test input", "fyk": "test input"},
    }
    data.update(over)
    path = tmp_path / "in.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_runner_writes_results_that_match_the_hand_value(tmp_path):
    out = tmp_path / "r.json"
    assert anchorage_check.main([str(_inputs(tmp_path)), str(out)]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["results"]["lb_rqd_good"] == [339.1]
    assert res["results"]["lap_basic_good"] == [508.7]  # alpha6 = 1.5
    assert "not independently reviewed" in res["verification"]["status"]


def test_runner_refuses_an_untraceable_design_basis_item(tmp_path):
    db = tmp_path / "db.yaml"
    db.write_text(yaml.safe_dump({"materials": [{"id": "MAT-1"}]}), encoding="utf-8")
    inputs = _inputs(tmp_path, design_basis_refs=["MAT-9"])
    with pytest.raises(SystemExit) as exc:
        anchorage_check.main([str(inputs), str(tmp_path / "r.json"), "--design-basis", str(db)])
    assert "MAT-9" in str(exc.value)
