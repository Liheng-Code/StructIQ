"""Report which CAD / analysis software and Python libraries exist on THIS computer.

Ported from the SDSA ``probe_cad.py``. It only looks (PATH, standard install folders and the
``tools:`` section of ``config/paths.yaml``); it never launches or modifies anything.

    python -m structiq.tools.probe
"""

from __future__ import annotations

import glob
import importlib.util
import json
import platform
import shutil
from typing import Any

from structiq.core.config import load_config

PATTERNS = {
    "autocad_console": [r"C:\Program Files\Autodesk\AutoCAD*\accoreconsole.exe"],
    "autocad": [r"C:\Program Files\Autodesk\AutoCAD*\acad.exe"],
    "oda_file_converter": [
        r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
        "/usr/bin/ODAFileConverter*",
        "/Applications/ODAFileConverter.app",
    ],
    "etabs": [r"C:\Program Files\Computers and Structures\ETABS*\ETABS.exe"],
    "safe": [r"C:\Program Files\Computers and Structures\SAFE*\SAFE.exe"],
    "libreoffice": [r"C:\Program Files\LibreOffice\program\soffice.exe"],
    "excel": [
        r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
    ],
}
PATH_TOOLS = ["accoreconsole", "ODAFileConverter", "soffice", "libreoffice", "pdftoppm"]
LIBS = ["ezdxf", "matplotlib", "openpyxl", "docx", "yaml", "numpy", "PIL", "shapely", "fitz", "mcp"]


def probe(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = load_config() if config is None else config
    configured = cfg.get("tools") or {}
    found = {}
    for name, patterns in PATTERNS.items():
        hits = sorted(p for pat in patterns for p in glob.glob(pat))
        if configured.get(name):
            hits.insert(0, str(configured[name]))
        found[name] = hits or "NOT FOUND in configured or standard locations"
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "installed_software": found,
        "on_path": {t: shutil.which(t) or "not on PATH" for t in PATH_TOOLS},
        "python_libraries": {m: ("installed" if importlib.util.find_spec(m) else "missing") for m in LIBS},
        "note": "NOT FOUND means not in the places searched; set it under 'tools:' in config/paths.yaml.",
    }


def main() -> int:
    print(json.dumps(probe(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
