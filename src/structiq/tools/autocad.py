"""Turn a DXF into a DWG with AutoCAD's own headless console (``accoreconsole.exe``), purging it on the way.

Only runs when AutoCAD is installed (``tools.autocad_console`` in ``config/paths.yaml``, or the standard Autodesk folder).
The DXF is not changed. The result is checked: the file must exist, be new and start with a DWG header.
"""

from __future__ import annotations

import glob
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from structiq.core.config import tool_path

DWG_HEADERS = {b"AC1032": "2018", b"AC1027": "2013", b"AC1024": "2010"}


class AutoCadError(RuntimeError):
    """AutoCAD is missing or did not produce a usable DWG."""


def find_console() -> Path | None:
    configured = tool_path("autocad_console")
    if configured:
        return configured
    hits = sorted(glob.glob(r"C:\Program Files\Autodesk\AutoCAD*\accoreconsole.exe"))
    return Path(hits[-1]) if hits else None  # the newest version by name


def build_script(dwg: Path, *, version: str = "2018", purge_passes: int = 0) -> str:
    """AutoCAD script: audit and fix, optionally purge (repeated, because purging can free more), zoom to extents, save as DWG.

    PURGE is off by default: StructIQ's own purge already ran, and AutoCAD's PURGE crashed on a drawing converted by LibreDWG."""
    lines: list[str] = ["_.AUDIT", "Y"]
    for _ in range(purge_passes):
        lines += ["_.-PURGE", "A", "*", "N"]
    lines += ["_.ZOOM", "E", "_.SAVEAS", version, f'"{dwg}"', "_.QUIT", "Y"]
    return "\n".join(lines) + "\n"


def dxf_to_dwg(
    dxf: str | Path,
    dwg: str | Path,
    *,
    version: str = "2018",
    purge: bool = False,
    timeout: int = 600,
    console: Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> Path:
    src, out = Path(dxf).resolve(), Path(dwg).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"{src} not found")
    if out.exists():
        raise FileExistsError(f"{out} already exists; nothing was overwritten")
    exe = console or find_console()
    if exe is None:
        raise AutoCadError("AutoCAD (accoreconsole.exe) not found: set tools.autocad_console in config/paths.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        scr = Path(tmp) / "save_dwg.scr"
        scr.write_text(build_script(out, version=version, purge_passes=3 if purge else 0), encoding="utf-8")
        try:
            runner([str(exe), "/i", str(src), "/s", str(scr), "/l", "en-US"], capture_output=True, text=True, timeout=timeout, cwd=tmp)
        except subprocess.TimeoutExpired as exc:
            out.unlink(missing_ok=True)
            raise AutoCadError(f"AutoCAD did not finish within {timeout} s") from exc
    if not out.is_file() or out.stat().st_size == 0:
        raise AutoCadError("AutoCAD finished but wrote no DWG (check the licence and that the DXF opens)")
    if out.read_bytes()[:6] not in DWG_HEADERS:
        out.unlink(missing_ok=True)
        raise AutoCadError("the file AutoCAD wrote is not a DWG")
    return out
