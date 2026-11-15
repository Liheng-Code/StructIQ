from qaqc_fixtures import design_basis

from structiq.qaqc import doc_control


def _rows():
    names = ["COVER PAGE", "DRAWING LIST", "GENERAL NOTES", "FIRST FLOOR LAYOUT", "SECTION DETAILS"]
    numbers = ["TB-STR-SD-001", "TB-STR-SD-002", "TB-STR-SD-003", "TB-STR-SD-101", "TB-STR-SD-201"]
    return [
        {"sheet_number": n, "sheet_name": s, "paper": "A3", "revision": "R00", "issue_date": "01-JAN-2027",
         "stage": "PRELIMINARY", "status": "DRAFT"}
        for n, s in zip(numbers, names, strict=True)
    ]


def _errors(res):
    return [r for r in res if r[0] == "ERROR"]


def test_a_consistent_register_has_no_errors():
    assert _errors(doc_control.check(_rows(), design_basis())) == []


def test_inconsistent_register_is_detected():
    rows = _rows()
    rows[3]["revision"] = "R01"  # differs from the design basis
    rows[4]["sheet_number"] = "TB-STR-SD-101"  # duplicate number
    rows[2]["sheet_number"] = "OF-STR-SD-003"  # wrong project prefix
    rows[1]["issue_date"] = "2027-01-01"  # bad date
    rows[0]["paper"] = "A5"
    text = " ".join(m for _, _, m in doc_control.check(rows, design_basis()))
    for fragment in ("differs from design basis R00", "duplicate", "prefix OF-STR", "DD-MMM-YYYY", "paper"):
        assert fragment in text


def test_main_reports_a_missing_column(tmp_path, capsys):
    reg = tmp_path / "r.csv"
    reg.write_text("sheet_number,sheet_name\nTB-STR-SD-001,COVER\n", encoding="utf-8")
    assert doc_control.main([str(reg)]) == 1
    assert "missing columns" in capsys.readouterr().out
