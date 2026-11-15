"""Cross-document QA on a small synthetic package (made-up project) and on deliberately broken ones."""

import csv
import shutil

import pytest
import yaml
from docx import Document
from qaqc_fixtures import design_basis
from test_docgen import SPEC

from structiq.qaqc import docgen
from structiq.qaqc import package_qa as qa

REGISTER_COLUMNS = ["sheet_number", "sheet_name", "paper", "revision", "issue_date", "stage", "status"]


def _package(tmp_path):
    pkg = tmp_path / "pkg"
    out = pkg / "output"
    out.mkdir(parents=True)
    db = design_basis()
    (pkg / "design-basis.yaml").write_text(yaml.safe_dump(db), encoding="utf-8")
    docgen.build(SPEC, db, {}, out)
    with open(pkg / "document-register.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, REGISTER_COLUMNS)
        w.writeheader()
        w.writerow({"sheet_number": "TB-STR-SP-001", "sheet_name": "SPECIFICATION", "paper": "A4", "revision": "R00",
                    "issue_date": "01-JAN-2027", "stage": "PRELIMINARY", "status": "DRAFT"})
    return pkg


def _hits(q, severity=None, text=None):
    return [f for f in q.f if (severity is None or f["severity"] == severity)
            and (text is None or text in f["finding"] + f["evidence"] + f["location"])]


def test_a_missing_design_basis_is_critical_and_nothing_else_is_checked(tmp_path):
    q = qa.run(tmp_path)
    assert _hits(q, qa.CRIT, "design basis file is missing")


def test_a_consistent_draft_package_has_no_critical_or_major_finding(tmp_path):
    q = qa.run(_package(tmp_path))
    assert not _hits(q, qa.CRIT) and not _hits(q, qa.MAJ), [f["finding"] for f in q.f]
    assert qa.summarise(q)["consistency_gate_pass"]


def test_a_missing_register_is_major(tmp_path):
    pkg = _package(tmp_path)
    (pkg / "document-register.csv").unlink()
    assert _hits(qa.run(pkg), qa.MAJ, "document register is missing")


def test_a_file_name_that_breaks_the_convention_is_reported(tmp_path):
    pkg = _package(tmp_path)
    shutil.copy(next((pkg / "output").glob("*.docx")), pkg / "output" / "notes final.docx")
    assert _hits(qa.run(pkg), qa.MIN, "does not follow")


def test_a_register_error_is_carried_into_the_qa_findings(tmp_path):
    pkg = _package(tmp_path)
    reg = (pkg / "document-register.csv").read_text(encoding="utf-8").replace("A4", "A9")
    (pkg / "document-register.csv").write_text(reg, encoding="utf-8")
    assert _hits(qa.run(pkg), qa.MAJ, "paper")


def test_a_placeholder_in_the_document_text_is_flagged(tmp_path):
    pkg = _package(tmp_path)
    path = next((pkg / "output").glob("TB-STR-SP-001_R00.docx"))
    doc = Document(path)
    doc.add_paragraph("Concrete cover is TBD.")
    doc.save(path)
    assert _hits(qa.run(pkg), text="TBD")


def test_qa_never_approves_anything(tmp_path):
    q = qa.run(_package(tmp_path))
    assert not any("APPROVED" == f["review_status"] for f in q.f)
    assert all(f["review_status"] == "Open" for f in q.f)


@pytest.mark.parametrize("name", ["summarise", "write", "run", "main"])
def test_public_entry_points_exist(name):
    assert callable(getattr(qa, name))
