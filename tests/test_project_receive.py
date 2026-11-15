import csv
import datetime
from pathlib import Path

import pymupdf
import pytest
import yaml

from structiq.project import create, receive, record, register
from structiq.project.cli import main as cli_main
from structiq.project.layout import parse_layout
from structiq.project.receive import Item
from test_project_folders import _layout_dict

D1 = datetime.date(2026, 11, 15)
D2 = datetime.date(2026, 12, 1)


@pytest.fixture()
def project(tmp_path):
    parent = tmp_path / "01-Freelance"
    parent.mkdir()
    return create.new_project("Villa", parent, parse_layout(_layout_dict()), "v", today=D1).root


def _pdf(path: Path, pages: int = 1, text: str = "plan") -> Path:
    with pymupdf.open() as doc:
        for i in range(pages):
            doc.new_page().insert_text((72, 72), f"{text} {i + 1}")
        doc.save(path)
    return path


def _entries(project):
    return record.read_record(project)["received"]


# ---------------------------------------------------------------- naming helpers
@pytest.mark.parametrize("raw, token", [("B", "B"), ("rev b", "B"), ("Rev.03", "03"), ("Revision C", "C"), ("p01", "P01")])
def test_revision_tokens(raw, token):
    assert register.revision_token(raw) == token


def test_name_parts_replace_illegal_characters_and_cap_length():
    assert register.part("Section A/A: north") == "Section A-A- north"
    assert len(register.part("x" * 100)) == register.MAX_PART


def test_numbers_are_per_project_and_never_reused():
    rows = [{"rcv_no": "RCV-001"}, {"rcv_no": "RCV-004"}, {"rcv_no": "RCV-004.02"}]
    assert register.next_number(rows) == 5
    assert register.rcv_id(7, 3) == "RCV-007.03"
    with pytest.raises(ValueError):
        register.rcv_id(1000)


# ---------------------------------------------------------------- receive
def test_a_named_drawing_gets_the_standard_file_name_and_a_register_row(project, tmp_path):
    src = _pdf(tmp_path / "GF plan final.pdf")
    (path,) = receive.receive(project, [Item(src, "A-101", "Ground Floor Plan", "rev b")], "Issue A", today=D1)
    assert path.relative_to(project).as_posix() == (
        "01-Received/Architectural/2026-11-15 Issue A/PDF/RCV-001_A-101_Ground Floor Plan_RevB.pdf"
    )
    (row,) = _entries(project)
    assert (row["rcv_no"], row["drawing_no"], row["revision"], row["status"]) == ("RCV-001", "A-101", "B", "Current")
    assert row["original_name"] == "GF plan final.pdf" and row["format"] == "PDF"
    assert src.exists()  # the source is untouched
    with open(project / "00-Project Management" / "Received Register.csv", encoding="utf-8") as fh:
        assert list(csv.DictReader(fh))[0]["file"] == row["file"]


def test_an_unnamed_drawing_keeps_its_name_and_is_flagged_to_confirm(project, tmp_path):
    src = _pdf(tmp_path / "Elevations.pdf")
    (path,) = receive.receive(project, [src], "Issue A", today=D1)
    assert path.name == "RCV-001_Elevations.pdf"
    assert _entries(project)[0]["status"] == "To confirm"


def test_a_combined_pdf_is_stored_whole_and_split_into_sheets(project, tmp_path):
    src = _pdf(tmp_path / "set.pdf", pages=3)
    created = receive.receive(project, [src], "Issue A", today=D1)
    names = sorted(p.name for p in created)
    assert names == ["RCV-001.01_p01-of-03.pdf", "RCV-001.02_p02-of-03.pdf", "RCV-001.03_p03-of-03.pdf", "RCV-001_set.pdf"]
    whole = next(p for p in created if p.name == "RCV-001_set.pdf")
    with pymupdf.open(whole.parent / "Split Sheets" / "RCV-001.02_p02-of-03.pdf") as one:
        assert one.page_count == 1 and "plan 2" in one[0].get_text()
    rows = _entries(project)
    assert [r["rcv_no"] for r in rows] == ["RCV-001", "RCV-001.01", "RCV-001.02", "RCV-001.03"]
    assert all(r["status"] == "To confirm" for r in rows)
    assert "3 pages" in rows[0]["note"] and rows[2]["note"] == "page 2 of 3 of RCV-001"


def test_splitting_can_be_switched_off(project, tmp_path):
    created = receive.receive(project, [_pdf(tmp_path / "set.pdf", pages=3)], "Issue A", today=D1, split=False)
    assert len(created) == 1 and len(_entries(project)) == 1


def test_a_newer_revision_supersedes_the_older_one_and_nothing_is_deleted(project, tmp_path):
    a = _pdf(tmp_path / "a.pdf", text="first")
    b = _pdf(tmp_path / "b.pdf", text="second")
    (old,) = receive.receive(project, [Item(a, "A-101", "Ground Floor Plan", "A")], "Issue A", today=D1)
    (new,) = receive.receive(project, [Item(b, "A-101", "Ground Floor Plan", "B")], "Issue B", today=D2)
    assert old.exists() and new.exists() and old != new
    rows = {r["rcv_no"]: r for r in _entries(project)}
    assert (rows["RCV-001"]["status"], rows["RCV-002"]["status"]) == ("Superseded", "Current")
    assert "2026-12-01 Issue B" in rows["RCV-002"]["file"]


def test_the_same_file_twice_is_refused_and_nothing_is_copied(project, tmp_path):
    a = _pdf(tmp_path / "a.pdf")
    receive.receive(project, [Item(a, "A-101", "Plan", "A")], "Issue A", today=D1)
    copy = tmp_path / "copy of a.pdf"
    copy.write_bytes(a.read_bytes())
    with pytest.raises(FileExistsError, match="already received as RCV-001"):
        receive.receive(project, [copy], "Issue B", today=D2)
    assert not (project / "01-Received/Architectural/2026-12-01 Issue B").exists()
    assert len(_entries(project)) == 1


def test_one_bad_file_in_a_batch_copies_nothing(project, tmp_path):
    good = _pdf(tmp_path / "good.pdf")
    bad = tmp_path / "notes.txt"
    bad.write_text("x")
    with pytest.raises(ValueError, match="only"):
        receive.receive(project, [good, bad], "Issue A", today=D1)
    assert _entries(project) == []
    assert not (project / "01-Received/Architectural/2026-11-15 Issue A").exists()


def test_numbers_keep_counting_across_sets_so_names_never_clash(project, tmp_path):
    a, b = _pdf(tmp_path / "a.pdf", text="x"), _pdf(tmp_path / "b.pdf", text="y")
    receive.receive(project, [Item(a, "A-1", "Plan", "A")], "Issue A", today=D1)
    receive.receive(project, [Item(b, "A-1", "Plan", "A")], "Issue A", today=D1)
    assert [r["rcv_no"] for r in _entries(project)] == ["RCV-001", "RCV-002"]


def test_dwg_files_go_in_the_dwg_folder_and_are_not_split(project, tmp_path):
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1032 fake")
    (path,) = receive.receive(project, [Item(dwg, "A-101", "Ground Floor Plan", "A")], "Issue A", today=D1)
    assert path.parent.name == "DWG" and path.suffix == ".dwg"


def test_long_titles_are_capped_and_a_path_over_the_limit_is_refused(project, tmp_path, monkeypatch):
    src = _pdf(tmp_path / "a.pdf")
    with pytest.raises(ValueError, match="limit"):  # pytest's own temp path is already long
        receive.receive(project, [Item(src, "A-1", "t" * 200, "A")], "Issue A", today=D1)
    assert _entries(project) == []  # refused before anything was copied
    monkeypatch.setattr(register, "MAX_PATH", 400)
    (path,) = receive.receive(project, [Item(src, "A-1", "t" * 200, "A")], "Issue A", today=D1)
    assert len(path.name) < 90  # the title part is capped at 40 characters


# ---------------------------------------------------------------- confirm
def test_confirm_renames_the_file_and_updates_the_register(project, tmp_path):
    receive.receive(project, [_pdf(tmp_path / "set.pdf", pages=2)], "Issue A", today=D1)
    new = receive.confirm(project, "RCV-001.02", "A-201", "East Elevation", "A")
    assert new.name == "RCV-001.02_A-201_East Elevation_RevA.pdf" and new.exists()
    row = next(r for r in _entries(project) if r["rcv_no"] == "RCV-001.02")
    assert row["status"] == "Current" and row["file"].endswith("East Elevation_RevA.pdf")
    assert not (new.parent / "RCV-001.02_p02-of-02.pdf").exists()
    with pytest.raises(KeyError):
        receive.confirm(project, "RCV-999", "A-1", "x", "A")


def test_confirm_can_record_what_a_combined_file_contains(project, tmp_path):
    dwg = tmp_path / "set.dwg"
    dwg.write_bytes(b"AC1032 fake")
    receive.receive(project, [dwg], "Issue A", today=D1)
    receive.confirm(project, "RCV-001", "SET", "Combined Drawing Set", "A", note="floor plans G-10, sections A-A to C-C")
    (row,) = _entries(project)
    assert row["file"].endswith("RCV-001_SET_Combined Drawing Set_RevA.dwg")
    assert row["note"] == "floor plans G-10, sections A-A to C-C" and row["status"] == "Current"


# ---------------------------------------------------------------- command line
def _cfg(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("r")
    (brain / "VERSION").write_text("9.9.9\n")
    (brain / "04-Global Workflows").mkdir()
    (brain / "04-Global Workflows" / "project-folder-layout.yaml").write_text(yaml.safe_dump(_layout_dict()))
    cfg = tmp_path / "paths.yaml"
    cfg.write_text(f"core_brain: '{brain}'\n", encoding="utf-8")
    monkeypatch.setenv("STRUCTIQ_CONFIG", str(cfg))
    monkeypatch.setattr("structiq.drawing.pipeline.CONFIG_FILE", cfg)


def test_cli_receive_with_a_meta_csv_then_register_and_confirm(project, tmp_path, monkeypatch, capsys):
    _cfg(tmp_path, monkeypatch)
    a, b = _pdf(tmp_path / "a.pdf", text="a"), _pdf(tmp_path / "b.pdf", text="b")
    meta = tmp_path / "meta.csv"
    meta.write_text("file,drawing_no,title,revision\na.pdf,A-101,Ground Floor Plan,A\n", encoding="utf-8")
    assert cli_main(["receive", str(project), str(a), str(b), "--meta", str(meta), "--label", "Issue A"]) == 0
    capsys.readouterr()
    assert cli_main(["register", str(project)]) == 0
    out = capsys.readouterr().out
    assert "RCV-001" in out and "Current" in out and "RCV-002" in out and "To confirm" in out
    args = ["confirm", str(project), "RCV-002", "--drawing-no", "A-102", "--title", "First Floor Plan", "--revision", "A"]
    assert cli_main(args) == 0
    assert cli_main(["receive", str(project), str(a), "--label", "Again"]) == 1  # a duplicate is refused, not a crash
