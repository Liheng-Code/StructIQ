import datetime
import subprocess
from pathlib import Path

import ezdxf
import pytest

from structiq.project import create, derive, receive, record, register
from structiq.project.cli import main as cli_main
from structiq.project.layout import parse_layout
from structiq.project.receive import Item
from structiq.tools import autocad
from test_drawing_split import _plan
from test_project_folders import _layout_dict

D1 = datetime.date(2026, 11, 15)


@pytest.fixture(autouse=True)
def _work_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTIQ_WORK_DIR", str(tmp_path / "work"))
    monkeypatch.setattr(register, "MAX_PATH", 400)  # pytest temp folders are long


@pytest.fixture()
def project(tmp_path):
    parent = tmp_path / "01-Freelance"
    parent.mkdir()
    return create.new_project("Villa", parent, parse_layout(_layout_dict()), "v", today=D1).root


def _combined(path: Path) -> Path:
    doc = ezdxf.new("R2018")
    doc.units = 4
    msp = doc.modelspace()
    _plan(msp, 0, 0, "Ground Floor Plan")
    _plan(msp, 60000, 0, "1st Floor Plan", n=80)
    msp.add_line((-300000, 5000), (400000, 5000))
    doc.saveas(path)
    return path


@pytest.fixture()
def stored(project, tmp_path):
    """A combined DXF received and named (RCV-001, drawing no SET, revision A)."""
    src = _combined(tmp_path / "combined.dxf")
    receive.receive(project, [Item(src, "SET", "Combined Drawing Set", "A")], "Issue A", today=D1)
    return project


def test_views_lists_what_is_in_a_stored_file(stored):
    views, _ = derive.scan(stored, "RCV-001", min_entities=40)
    assert [v.title for v in views] == ["Ground Floor Plan", "1st Floor Plan"]


def test_split_writes_one_file_per_chosen_drawing_and_registers_each(stored):
    created = derive.split_received(
        stored, "RCV-001", [(1, "Ground Floor Plan"), (2, "First Floor Plan")], today=D1
    )
    names = sorted(p.name for p in created)
    assert names == [
        "RCV-001.01_SET_Ground Floor Plan_RevA.dxf",
        "RCV-001.02_SET_First Floor Plan_RevA.dxf",
    ]
    assert all(p.parent.name == "Split Sheets" and p.parent.parent.name == "DWG" for p in created)
    rows = {r["rcv_no"]: r for r in record.read_record(stored)["received"]}
    assert rows["RCV-001"]["status"] == "Current"  # the original is untouched
    assert rows["RCV-001.01"]["status"] == "Derived" and rows["RCV-001.01"]["derived_from"] == "RCV-001"
    assert "view 1" in rows["RCV-001.01"]["note"] and "kept" in rows["RCV-001.01"]["note"]
    doc = ezdxf.readfile(created[0])
    assert [e.dxf.text for e in doc.modelspace().query("TEXT")] == ["Ground Floor Plan"]


def test_a_second_split_continues_the_numbers_and_never_overwrites(stored):
    derive.split_received(stored, "RCV-001", [(1, "Ground Floor Plan")], today=D1)
    (more,) = derive.split_received(stored, "RCV-001", [(2, "First Floor Plan")], today=D1)
    assert more.name.startswith("RCV-001.02_")
    with pytest.raises(FileExistsError):
        # the same title again would get RCV-001.03, a new name: asking for a name that exists must be refused
        existing = more.parent / "RCV-001.03_SET_First Floor Plan_RevA.dxf"
        existing.write_bytes(b"x")
        derive.split_received(stored, "RCV-001", [(2, "First Floor Plan")], today=D1)


def test_the_parent_must_be_named_before_it_can_be_split(project, tmp_path):
    src = _combined(tmp_path / "combined.dxf")
    receive.receive(project, [src], "Issue A", today=D1)  # unnamed: To confirm
    with pytest.raises(ValueError, match="confirm"):
        derive.split_received(project, "RCV-001", [(1, "Ground")], today=D1)


def test_pdfs_and_split_pieces_cannot_be_split_again(stored, tmp_path):
    derive.split_received(stored, "RCV-001", [(1, "Ground Floor Plan")], today=D1)
    with pytest.raises(ValueError, match="itself a split piece"):
        derive.split_received(stored, "RCV-001.01", [(1, "x")], today=D1)
    with pytest.raises(KeyError):
        derive.split_received(stored, "RCV-009", [(1, "x")], today=D1)


def test_an_unknown_view_number_changes_nothing(stored):
    with pytest.raises(ValueError, match="no view"):
        derive.split_received(stored, "RCV-001", [(1, "Ground"), (7, "Nope")], today=D1)
    assert len(record.read_record(stored)["received"]) == 1


def test_derived_pieces_do_not_take_part_in_revision_status():
    rows = [
        {"rcv_no": "RCV-001", "drawing_no": "SET", "revision": "A"},
        {"rcv_no": "RCV-001.01", "drawing_no": "SET", "revision": "A", "derived_from": "RCV-001"},
        {"rcv_no": "RCV-001.02", "drawing_no": "SET", "revision": "A", "derived_from": "RCV-001"},
    ]
    register.refresh_status(rows)
    assert [r["status"] for r in rows] == ["Current", "Derived", "Derived"]


def test_dwg_output_goes_through_autocad_and_is_registered_as_dwg(stored, monkeypatch):
    calls = []

    def fake(dxf, dwg, **kw):
        calls.append((Path(dxf).name, Path(dwg).name))
        Path(dwg).write_bytes(b"AC1032 fake dwg")
        return Path(dwg)

    monkeypatch.setattr(autocad, "dxf_to_dwg", fake)
    (path,) = derive.split_received(stored, "RCV-001", [(1, "Ground Floor Plan")], dwg=True, today=D1)
    assert path.suffix == ".dwg" and calls == [("RCV-001.01.dxf", "RCV-001.01_SET_Ground Floor Plan_RevA.dwg")]
    assert record.read_record(stored)["received"][-1]["format"] == "DWG"


def test_cli_views_and_split(stored, tmp_path, monkeypatch, capsys):
    import yaml

    brain = tmp_path / "brain"
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("r")
    (brain / "VERSION").write_text("9\n")
    (brain / "04-Global Workflows").mkdir()
    (brain / "04-Global Workflows" / "project-folder-layout.yaml").write_text(yaml.safe_dump(_layout_dict()))
    cfg = tmp_path / "paths.yaml"
    cfg.write_text(f"core_brain: '{brain}'\n", encoding="utf-8")
    monkeypatch.setenv("STRUCTIQ_CONFIG", str(cfg))
    monkeypatch.setattr("structiq.drawing.pipeline.CONFIG_FILE", cfg)

    assert cli_main(["views", str(stored), "RCV-001"]) == 0
    assert "Ground Floor Plan" in capsys.readouterr().out
    assert cli_main(["split", str(stored), "RCV-001", "--view", "1=Ground Floor Plan"]) == 0
    assert "RCV-001.01_SET_Ground Floor Plan_RevA.dxf" in capsys.readouterr().out
    assert cli_main(["split", str(stored), "RCV-001", "--view", "bad"]) == 1  # not NUMBER=Title: stopped, not a crash


# ---------------------------------------------------------------- AutoCAD
def test_the_autocad_script_audits_then_saves_as_dwg_and_can_purge():
    script = autocad.build_script(Path("C:/out/a.dwg"), purge_passes=3)
    lines = script.splitlines()
    assert lines.count("_.-PURGE") == 3 and "_.SAVEAS" in lines and lines[-2:] == ["_.QUIT", "Y"]
    assert lines[:2] == ["_.AUDIT", "Y"] and "_.-PURGE" not in autocad.build_script(Path("C:/out/a.dwg"))
    assert '"C:' in script and "2018" in lines


def test_autocad_runs_headless_and_checks_the_result(tmp_path):
    dxf = tmp_path / "in.dxf"
    dxf.write_text("0\nEOF\n")
    out = tmp_path / "o" / "out.dwg"
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[cmd.index("/s") + 1]).read_text()  # the script exists while AutoCAD runs
        out.write_bytes(b"AC1032" + b"\0" * 20)

    result = autocad.dxf_to_dwg(dxf, out, console=Path("accoreconsole.exe"), runner=runner)
    assert result == out.resolve() and seen["cmd"][1] == "/i"


def test_autocad_failures_are_reported_not_hidden(tmp_path):
    dxf = tmp_path / "in.dxf"
    dxf.write_text("0\nEOF\n")
    with pytest.raises(autocad.AutoCadError, match="wrote no DWG"):
        autocad.dxf_to_dwg(dxf, tmp_path / "a.dwg", console=Path("x"), runner=lambda *a, **k: None)

    def junk(cmd, **kw):
        (tmp_path / "b.dwg").write_bytes(b"not a dwg at all")

    with pytest.raises(autocad.AutoCadError, match="not a DWG"):
        autocad.dxf_to_dwg(dxf, tmp_path / "b.dwg", console=Path("x"), runner=junk)
    assert not (tmp_path / "b.dwg").exists()

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)

    with pytest.raises(autocad.AutoCadError, match="did not finish"):
        autocad.dxf_to_dwg(dxf, tmp_path / "c.dwg", console=Path("x"), runner=slow)

    existing = tmp_path / "d.dwg"
    existing.write_bytes(b"x")
    with pytest.raises(FileExistsError):
        autocad.dxf_to_dwg(dxf, existing, console=Path("x"), runner=lambda *a, **k: None)
