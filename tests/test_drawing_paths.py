import pytest

from structiq.drawing import paths


def test_work_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.WORK_ENV_VAR, str(tmp_path))
    assert paths.work_dir() == tmp_path


def test_project_output_dir_finds_pjr_folder(tmp_path):
    src = tmp_path / "PJR-2026-000_Test Project" / "01-Architect drawing" / "a.dwg"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"x")
    expected = tmp_path / "PJR-2026-000_Test Project" / "02-Structural Drawing"
    assert paths.project_output_dir(src) == expected.resolve()


def test_project_output_dir_outside_project_raises(tmp_path):
    f = tmp_path / "a.dwg"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        paths.project_output_dir(f)
