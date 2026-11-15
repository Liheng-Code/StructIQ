import datetime
from pathlib import Path

import pytest
import yaml
from openpyxl import load_workbook

from structiq.drawing import paths
from structiq.project import adopt, create, numbering, record
from structiq.project.cli import main as cli_main
from structiq.project.layout import LayoutError, check_length, load_layout, parse_layout

TODAY = datetime.date(2026, 11, 15)


def _layout_dict():
    return {
        "version": 1,
        "status": "DRAFT",
        "code_pattern": "PJR-{year}-{seq:03d}_{name}",
        "parent_folder": "01-Freelance",
        "register_columns": ["sheet_number", "sheet_name", "paper", "revision", "issue_date", "stage", "status"],
        "workflow_steps": ["Receive drawing", "Create folder", "Submit"],
        "folders": [
            {"name": "00-Project Management", "role": "management", "children": [{"name": "Correspondence"}]},
            {"name": "01-Received", "children": [{"name": "Architectural", "role": "received_architect"}]},
            {
                "name": "02-Design Review",
                "children": [
                    {"name": "Design Basis", "role": "design_basis"},
                    {
                        "name": "Structural Concept",
                        "children": [{"name": "StructIQ Draft", "role": "structiq_draft"}],
                    },
                ],
            },
            {
                "name": "05-Structural Drawing",
                "children": [{"name": "Working", "role": "drawing_working"}, {"name": "Issued", "role": "drawing_issued"}],
            },
            {"name": "99-Archive", "role": "archive"},
        ],
    }


@pytest.fixture()
def layout():
    return parse_layout(_layout_dict())


@pytest.fixture()
def parent(tmp_path):
    p = tmp_path / "01-Freelance"
    p.mkdir()
    return p


# ---------------------------------------------------------------- layout
def test_layout_flattens_paths_and_roles(layout):
    assert "02-Design Review/Structural Concept/StructIQ Draft" in layout.paths()
    assert layout.paths().index("02-Design Review") < layout.paths().index("02-Design Review/Design Basis")
    assert layout.roles()["structiq_draft"] == "02-Design Review/Structural Concept/StructIQ Draft"


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d["folders"].append({"name": "99-Other"}), "share a number"),
        (lambda d: d["folders"].append({"name": "Loose"}), "must start with 'NN-'"),
        (lambda d: d["folders"][0]["children"].append({"name": "Bad:Name"}), "Windows"),
        (lambda d: d["folders"][0]["children"].append({"name": "correspondence"}), "duplicate sibling"),
        (lambda d: d["folders"][4].update(role="management"), "duplicate roles"),
        (lambda d: d["folders"].pop(), "required roles"),
        (lambda d: d["folders"][0].update(role="Not-Snake"), "snake_case"),
    ],
)
def test_invalid_layouts_are_refused(mutate, message):
    data = _layout_dict()
    mutate(data)
    with pytest.raises(LayoutError, match=message):
        parse_layout(data)


def test_long_paths_are_warned_about(layout, tmp_path):
    deep = tmp_path / ("x" * 200)
    assert check_length(deep, layout)
    assert check_length(tmp_path, layout) == []


def test_the_real_core_brain_layout_is_valid_when_the_brain_is_available():
    try:
        lay, version = load_layout()
    except Exception:
        pytest.skip("Core Brain not available on this machine")
    assert lay.roles()["structiq_draft"].endswith("StructIQ Draft")
    assert version


# ---------------------------------------------------------------- numbering
def test_next_number_counts_per_year_and_ignores_other_folders(parent):
    for name in ("PJR-2026-001_A", "PJR-2026-004_B", "PJR-2025-009_Old", "00-2025 Projects", "notes"):
        (parent / name).mkdir()
    (parent / "PJR-2026-007_file.txt").write_text("x")  # a file, not a project
    assert numbering.next_seq(parent, 2026) == 5
    assert numbering.next_seq(parent, 2027) == 1


@pytest.mark.parametrize("bad", ["", "   ", "a/b", 'q"x', "end.", "x" * 80])
def test_bad_project_names_are_refused(bad):
    with pytest.raises(ValueError):
        numbering.clean_name(bad)


def test_names_are_tidied_not_reinterpreted():
    assert numbering.clean_name("  Chong   Cherng  School ") == "Chong Cherng School"


# ---------------------------------------------------------------- create
def test_new_project_builds_the_tree_and_files(parent, layout):
    (parent / "PJR-2026-002_Existing").mkdir()
    res = create.new_project("Villa Test", parent, layout, "0.3.1-draft", today=TODAY)
    assert res.root.name == "PJR-2026-003_Villa Test"
    for rel in layout.paths():
        assert (res.root / rel).is_dir(), rel
    data = record.read_record(res.root)
    assert data["code"] == "PJR-2026-003" and data["roles"] == layout.roles() and data["received"] == []
    assert data["brain_version"] == "0.3.1-draft"
    reg = (res.root / "00-Project Management" / "Drawing Register.csv").read_text(encoding="utf-8")
    assert reg.strip() == ",".join(layout.register_columns)
    ws = load_workbook(res.root / "00-Project Management" / "Project Tracker.xlsx")["Tracker"]
    assert [r[1].value for r in ws.iter_rows(min_row=2, max_row=4)] == list(layout.workflow_steps)
    assert ws["C2"].value == "Not started"


def test_dry_run_changes_nothing(parent, layout):
    res = create.new_project("Villa Test", parent, layout, "v", today=TODAY, dry_run=True)
    assert res.dry_run and res.folders and not res.root.exists()
    assert list(parent.iterdir()) == []


def test_two_projects_get_consecutive_numbers_and_nothing_is_overwritten(parent, layout):
    a = create.new_project("One", parent, layout, "v", today=TODAY)
    b = create.new_project("Two", parent, layout, "v", today=TODAY)
    assert (a.code, b.code) == ("PJR-2026-001", "PJR-2026-002")
    with pytest.raises(FileNotFoundError):
        create.new_project("X", parent / "missing", layout, "v", today=TODAY)


# ---------------------------------------------------------------- adopt and roles
def _old_project(tmp_path):
    root = tmp_path / "PJR-2026-002_7 Story"
    for n in ("01-Document from Client", "02-Calculation Note", "03-Drawing", "04-Etabs", "05-Revit", "random"):
        (root / n).mkdir(parents=True)
    return root


def test_adopt_maps_old_folders_and_moves_nothing(tmp_path):
    root = _old_project(tmp_path)
    before = sorted(p.name for p in root.iterdir())
    plan = adopt.adopt(root, today=TODAY)
    assert plan.roles["received_client"] == "01-Document from Client"
    assert plan.roles["calc_note"] == "02-Calculation Note"
    assert plan.roles["drawing"] == plan.roles["structiq_draft"] == "03-Drawing"
    assert plan.roles["etabs"] == "04-Etabs" and plan.roles["revit"] == "05-Revit"
    assert "random" in plan.unmatched and "received_architect" in plan.missing
    assert sorted(p.name for p in root.iterdir()) == sorted([*before, "project.yaml"])
    with pytest.raises(FileExistsError):
        adopt.adopt(root)


def test_adopt_does_not_mistake_rate_analysis_for_structural_analysis(tmp_path):
    root = tmp_path / "PJR-2026-001_Tender"
    for n in ("10_RATE_ANALYSIS", "04_DRAWINGS", "07_QUANTITY_TAKEOFF"):
        (root / n).mkdir(parents=True)
    plan = adopt.plan_adopt(root)
    assert "etabs" not in plan.roles and plan.roles["drawing"] == "04_DRAWINGS" and plan.roles["boq"] == "07_QUANTITY_TAKEOFF"


def test_adopt_rejects_a_folder_that_is_not_a_project(tmp_path):
    (tmp_path / "Other").mkdir()
    with pytest.raises(ValueError):
        adopt.plan_adopt(tmp_path / "Other")


def test_role_lookup_uses_the_record_then_the_old_names(tmp_path, parent, layout):
    old = tmp_path / "PJR-2026-000_Test Project"
    (old / "01-Architect drawing").mkdir(parents=True)
    f = old / "01-Architect drawing" / "a.dwg"
    f.write_bytes(b"x")
    assert paths.project_output_dir(f) == (old / "02-Structural Drawing").resolve()  # legacy fallback

    new = create.new_project("Villa", parent, layout, "v", today=TODAY).root
    src = new / "01-Received" / "Architectural" / "a.dwg"
    src.write_bytes(b"x")
    assert paths.project_output_dir(src) == (new / "02-Design Review/Structural Concept/StructIQ Draft").resolve()
    assert paths.project_folder(src, "drawing_working") == (new / "05-Structural Drawing/Working").resolve()
    with pytest.raises(KeyError):
        paths.project_folder(src, "nonsense")


def test_an_adopted_project_sends_drafts_to_its_drawing_folder(tmp_path):
    root = _old_project(tmp_path)
    adopt.adopt(root, today=TODAY)
    f = root / "03-Drawing" / "a.dwg"
    f.write_bytes(b"x")
    assert paths.project_output_dir(f) == (root / "03-Drawing").resolve()


# ---------------------------------------------------------------- command line
def test_cli_new_dry_run_and_where(parent, layout, tmp_path, monkeypatch, capsys):
    brain = tmp_path / "brain"
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("r")
    (brain / "VERSION").write_text("9.9.9\n")
    (brain / "04-Global Workflows").mkdir()
    (brain / "04-Global Workflows" / "project-folder-layout.yaml").write_text(yaml.safe_dump(_layout_dict()))
    cfg = tmp_path / "paths.yaml"
    cfg.write_text(f"core_brain: '{brain}'\nprojects: '{parent.parent}'\n", encoding="utf-8")
    monkeypatch.setenv("STRUCTIQ_CONFIG", str(cfg))
    monkeypatch.setattr("structiq.drawing.pipeline.CONFIG_FILE", cfg)

    assert cli_main(["new", "Villa", "--parent", str(parent), "--dry-run"]) == 0
    assert "WOULD CREATE" in capsys.readouterr().out and list(parent.iterdir()) == []
    assert cli_main(["new", "Villa", "--parent", str(parent)]) == 0
    root = next(parent.iterdir())
    capsys.readouterr()
    assert cli_main(["where", str(root), "design_basis"]) == 0
    assert Path(capsys.readouterr().out.strip()) == root / "02-Design Review" / "Design Basis"
    with pytest.raises(SystemExit):
        cli_main(["where", str(root), "nope"])


def test_cli_stops_when_the_core_brain_is_unreadable(parent, tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "paths.yaml"
    cfg.write_text(f"core_brain: '{tmp_path / 'missing'}'\n", encoding="utf-8")
    monkeypatch.setattr("structiq.drawing.pipeline.CONFIG_FILE", cfg)
    with pytest.raises(Exception, match="Core Brain not readable"):
        cli_main(["new", "Villa", "--parent", str(parent)])
    assert list(parent.iterdir()) == []


def test_record_file_is_plain_yaml(parent, layout):
    res = create.new_project("Villa", parent, layout, "v", today=TODAY)
    data = yaml.safe_load(Path(res.files[0]).read_text(encoding="utf-8"))
    assert set(data) >= {"code", "name", "created", "stage", "roles", "received"}
