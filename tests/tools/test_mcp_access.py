"""Read-only access layer on a made-up repo, brain and projects folder."""

import pytest
import yaml
from qaqc_fixtures import design_basis

from structiq.tools.mcp import access, ask_local


@pytest.fixture()
def acc(tmp_path):
    repo, brain, projects = tmp_path / "repo", tmp_path / "brain", tmp_path / "projects"
    (repo / ".claude" / "skills" / "demo-skill").mkdir(parents=True)
    (repo / ".claude" / "skills" / "demo-skill" / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill for tests\n---\n# Demo\nAnchorage lengths need the concrete class.\n",
        encoding="utf-8",
    )
    (repo / "config").mkdir()
    (repo / "config" / "paths.yaml").write_text("core_brain: secret-location\n", encoding="utf-8")
    (repo / "config" / "paths.example.yaml").write_text("core_brain: example\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("x", encoding="utf-8")
    (repo / "model.dxf").write_bytes(b"0\nSECTION")
    (brain / "03-Safety Rules").mkdir(parents=True)
    (brain / "03-Safety Rules" / "safety-rules.md").write_text("# Safety\nNever invent values.\n", encoding="utf-8")
    p = projects / "01-Freelance" / "PJR-2026-999_Test"
    p.mkdir(parents=True)
    (p / "design-basis.yaml").write_text(yaml.safe_dump(design_basis()), encoding="utf-8")
    (p / "secret-notes.md").write_text("client confidential", encoding="utf-8")
    return access.Access(repo, brain, projects)


def test_reads_text_from_both_roots(acc):
    assert "Never invent values" in acc.brain_rules()
    assert "core_brain: example" in acc.read_file("repo/config/paths.example.yaml")


@pytest.mark.parametrize("path", ["repo/../brain/03-Safety Rules/safety-rules.md", "/etc/passwd", "other/x.md", "repo/../../x"])
def test_paths_outside_the_roots_are_refused(acc, path):
    with pytest.raises((PermissionError, FileNotFoundError)):
        acc.read_file(path)


@pytest.mark.parametrize("path", ["repo/config/paths.yaml", "repo/.git/config"])
def test_local_config_and_vcs_data_are_never_served(acc, path):
    with pytest.raises(PermissionError):
        acc.read_file(path)


def test_binary_files_are_not_read(acc):
    with pytest.raises(ValueError):
        acc.read_file("repo/model.dxf")


def test_long_files_are_truncated_with_a_note(acc, tmp_path):
    (acc.repo / "docs").mkdir()
    (acc.repo / "docs" / "big.md").write_text("x" * 500, encoding="utf-8")
    assert "truncated at 100 of 500" in acc.read_file("repo/docs/big.md", max_chars=100)


def test_the_brain_missing_is_an_error_not_a_fallback(tmp_path):
    acc = access.Access(tmp_path)
    with pytest.raises(FileNotFoundError):
        acc.brain_rules()


def test_skills_are_listed_and_their_context_starts_with_the_rules(acc):
    assert acc.list_skills() == [
        {"name": "demo-skill", "description": "Demo skill for tests", "path": "repo/.claude/skills/demo-skill/SKILL.md"}
    ]
    ctx = acc.skill_context("demo-skill")
    assert ctx.startswith("Rules for any AI") and "Anchorage lengths" in ctx
    with pytest.raises(KeyError):
        acc.skill_context("nope")


def test_search_covers_both_roots_or_one(acc):
    assert {h["path"] for h in acc.search("never invent")} == {"brain/03-Safety Rules/safety-rules.md"}
    assert acc.search("anchorage", scope="brain") == []
    assert acc.search("ANCHORAGE", scope="repo")[0]["path"].startswith("repo/.claude/skills/")
    assert not any("paths.yaml" in h["path"] or ".git" in h["path"] for h in acc.search("core_brain"))


def test_design_bases_are_listed_and_validated_but_other_project_files_are_not_served(acc):
    listed = acc.list_design_bases()
    assert listed == ["projects/01-Freelance/PJR-2026-999_Test/design-basis.yaml"]
    assert "error(s)" in acc.validate_design_basis(listed[0])
    with pytest.raises(PermissionError):
        acc.validate_design_basis("projects/01-Freelance/PJR-2026-999_Test/secret-notes.md")
    with pytest.raises(PermissionError):
        acc.read_file("projects/01-Freelance/PJR-2026-999_Test/secret-notes.md")


def test_local_model_retrieval_is_grounded_on_the_brain_and_the_chosen_skill(acc, monkeypatch):
    monkeypatch.setattr(ask_local, "ACCESS", acc)
    labels = [label for label, _ in ask_local.retrieve("anchorage concrete class", "demo-skill")]
    assert any("demo-skill/SKILL.md" in label for label in labels)
    assert ask_local.retrieve("anchorage concrete class", "core") == []  # the skill is not in scope
    msgs = ask_local.build_messages("what is the rule?", "core")
    assert "SOURCE extracts" in msgs[0]["content"] and msgs[1]["content"] == "what is the rule?"


def test_server_registers_read_only_tools():
    pytest.importorskip("mcp")
    from structiq.tools.mcp import server

    assert server.server is not None
    names = {"get_core_brain_rules", "list_skills", "get_skill_context", "read_project_file",
             "list_project_files", "search_project", "list_design_bases", "validate_design_basis"}
    assert names <= set(dir(server))
