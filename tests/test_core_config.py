import pytest

from structiq.core import config
from structiq.tools import probe


def test_missing_config_file_gives_empty_settings(tmp_path):
    assert config.load_config(tmp_path / "none.yaml") == {}


def test_tool_path_only_returns_existing_files(tmp_path):
    exe = tmp_path / "soffice.exe"
    exe.write_text("x")
    cfg = tmp_path / "paths.yaml"
    cfg.write_text(f"tools:\n  libreoffice: '{exe}'\n  etabs: '{tmp_path / 'gone.exe'}'\n", encoding="utf-8")
    assert config.tool_path("libreoffice", cfg) == exe
    assert config.tool_path("etabs", cfg) is None
    assert config.tool_path("safe", cfg) is None


def test_config_must_be_a_mapping(tmp_path):
    cfg = tmp_path / "paths.yaml"
    cfg.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError):
        config.load_config(cfg)


def test_env_variable_selects_the_config(tmp_path, monkeypatch):
    cfg = tmp_path / "p.yaml"
    cfg.write_text("projects: x\n", encoding="utf-8")
    monkeypatch.setenv(config.CONFIG_ENV, str(cfg))
    assert config.load_config() == {"projects": "x"}


def test_probe_reports_configured_tool_first(tmp_path):
    exe = tmp_path / "ETABS.exe"
    exe.write_text("x")
    out = probe.probe({"tools": {"etabs": str(exe)}})
    assert out["installed_software"]["etabs"][0] == str(exe)
    assert set(out) >= {"platform", "python", "on_path", "python_libraries"}
