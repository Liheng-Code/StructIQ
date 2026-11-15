"""Design-basis validator. Fixtures are made up for the tests (no project data)."""

import copy
import pathlib

import yaml

from structiq.core import design_basis as vdb

TEMPLATE = pathlib.Path(__file__).resolve().parents[2] / "templates" / "design-basis" / "design-basis.yaml"


def template():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def errors(db):
    return [(path, msg) for sev, path, msg in vdb.validate(db) if sev == "ERROR"]


def test_blank_template_is_not_ready_and_names_the_missing_fields():
    paths = {p for p, _ in errors(template())}
    for need in ("project.code", "project.name", "project.client", "design_assumptions.consequence_class"):
        assert need in paths


def test_incomplete_project_is_reported():
    paths = {p for p, _ in errors({"project": {"code": "BAD"}})}
    for need in ("standards", "national_annex", "approval", "project.name", "project.code"):
        assert need in paths


def test_a_draft_cannot_be_approved_without_names_and_closed_items():
    db = copy.deepcopy(template())
    db["approval"]["status"] = "APPROVED"
    db["open_items"] = [{"id": "F1", "status": "open", "description": "something to confirm"}]
    errs = errors(db)
    paths = {p for p, _ in errs}
    assert "approval.checked_by" in paths and "approval.approved_by" in paths
    assert any("open item" in m for _, m in errs)


def test_unresolved_national_annex_is_flagged_not_assumed():
    msgs = " ".join(m for _, _, m in vdb.validate(template()))
    assert "National Annex choice is unresolved" in msgs


def test_main_returns_nonzero_for_the_blank_template(capsys):
    assert vdb.main([str(TEMPLATE)]) == 1
    assert "NOT READY" in capsys.readouterr().out
