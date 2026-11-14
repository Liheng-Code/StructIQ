import subprocess

import pytest

from structiq.drawing import convert


@pytest.fixture(autouse=True)
def _work_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("STRUCTIQ_WORK_DIR", str(tmp_path / "work"))


def test_build_command_matches_oda_cli():
    cmd = convert.build_command(
        convert.Path("oda.exe"), convert.Path("in"), convert.Path("out"), "a.dwg"
    )
    assert cmd == ["oda.exe", "in", "out", "ACAD2018", "DXF", "0", "1", "a.dwg"]


def test_find_converter_missing_raises(monkeypatch):
    monkeypatch.delenv(convert.ODA_ENV_VAR, raising=False)
    monkeypatch.setattr(convert.glob, "glob", lambda pattern: [])
    with pytest.raises(convert.ConverterNotFoundError):
        convert.find_converter()


def test_dwg_to_dxf_runs_converter_and_returns_dxf(tmp_path, monkeypatch):
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1018")
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"")

    def fake_run(command, **kwargs):
        out_dir = convert.Path(command[2])
        (out_dir / "plan.dxf").write_text("0\nEOF\n")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    dxf = convert.dwg_to_dxf(dwg, converter=exe)
    assert dxf == tmp_path / "work" / "dxf" / "plan.dxf"
    assert dwg.read_bytes() == b"AC1018"  # source untouched


def test_build_libredwg_command():
    cmd = convert.build_libredwg_command(
        convert.Path("dwg2dxf.exe"), convert.Path("a.dwg"), convert.Path("a.dxf")
    )
    assert cmd == ["dwg2dxf.exe", "-y", "-o", "a.dxf", "a.dwg"]


def test_auto_falls_back_to_libredwg_when_oda_missing(tmp_path, monkeypatch):
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1018")
    lib = tmp_path / "dwg2dxf.exe"
    lib.write_bytes(b"")
    monkeypatch.delenv(convert.ODA_ENV_VAR, raising=False)
    monkeypatch.setenv(convert.LIBREDWG_ENV_VAR, str(lib))
    monkeypatch.setattr(convert.glob, "glob", lambda pattern: [])

    def fake_run(command, **kwargs):
        assert command[0] == str(lib)
        convert.Path(command[3]).write_text("0\nEOF\n")  # the -o target
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(convert.subprocess, "run", fake_run)
    assert convert.dwg_to_dxf(dwg).name == "plan.dxf"


def test_dwg_to_dxf_failure_raises(tmp_path, monkeypatch):
    dwg = tmp_path / "plan.dwg"
    dwg.write_bytes(b"AC1018")
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(
        convert.subprocess,
        "run",
        lambda command, **kw: subprocess.CompletedProcess(command, 1, "", "boom"),
    )
    with pytest.raises(convert.ConversionError):
        convert.dwg_to_dxf(dwg, converter=exe)
