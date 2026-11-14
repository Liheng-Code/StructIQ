"""DWG -> DXF conversion.

Rule: every DWG that StructIQ reads is first converted to DXF. Downstream code
(ezdxf) only ever sees DXF, and the source DWG is never modified.

Two backends are supported:

* **ODA File Converter** (preferred). Found via the ``converter`` argument, the
  ``ODA_FILE_CONVERTER`` environment variable, or ``C:\\Program Files\\ODA``.
* **LibreDWG** ``dwg2dxf`` (fallback). Found via the ``LIBREDWG_DWG2DXF``
  environment variable or ``D:\\Dev\\tools\\libredwg*\\dwg2dxf.exe``.

``backend="auto"`` uses ODA when installed, otherwise LibreDWG.

Usage::

    python -m structiq.drawing.convert "path\\to\\drawing.dwg" [output folder]
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_VERSION = "ACAD2018"
ODA_ENV_VAR = "ODA_FILE_CONVERTER"
LIBREDWG_ENV_VAR = "LIBREDWG_DWG2DXF"
_ODA_PATTERNS = (
    r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe",
    r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe",
)
_LIBREDWG_PATTERNS = (r"D:\Dev\tools\libredwg*\dwg2dxf.exe",)


class ConverterNotFoundError(RuntimeError):
    """No DWG converter could be located."""


class ConversionError(RuntimeError):
    """The converter ran but did not produce the expected DXF."""


def _find(explicit, env_var: str, patterns: tuple[str, ...], label: str) -> Path:
    chosen = explicit or os.environ.get(env_var)
    if chosen:
        path = Path(chosen)
        if path.is_file():
            return path
        raise ConverterNotFoundError(f"{label} not found at: {path}")
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return Path(matches[-1])
    raise ConverterNotFoundError(
        f"{label} is not installed. Install it, or set the {env_var} environment variable."
    )


def find_converter(converter: str | os.PathLike[str] | None = None) -> Path:
    """Return the path to ODAFileConverter.exe or raise ConverterNotFoundError."""
    return _find(converter, ODA_ENV_VAR, _ODA_PATTERNS, "ODA File Converter")


def find_libredwg(converter: str | os.PathLike[str] | None = None) -> Path:
    """Return the path to LibreDWG's dwg2dxf.exe or raise ConverterNotFoundError."""
    return _find(converter, LIBREDWG_ENV_VAR, _LIBREDWG_PATTERNS, "LibreDWG dwg2dxf")


def build_command(
    exe: Path,
    in_dir: Path,
    out_dir: Path,
    filename: str,
    version: str = DEFAULT_VERSION,
    out_type: str = "DXF",
) -> list[str]:
    """ODA CLI: <exe> <in dir> <out dir> <version> <type> <recurse> <audit> <filter>."""
    return [str(exe), str(in_dir), str(out_dir), version, out_type, "0", "1", filename]


def build_libredwg_command(exe: Path, source: Path, dxf: Path) -> list[str]:
    """LibreDWG CLI: dwg2dxf -y -o <output.dxf> <input.dwg> (-y overwrites)."""
    return [str(exe), "-y", "-o", str(dxf), str(source)]


def _select_backend(backend: str, converter) -> tuple[str, Path]:
    if backend not in ("auto", "oda", "libredwg"):
        raise ValueError(f"Unknown backend: {backend}")
    if backend == "oda":
        return "oda", find_converter(converter)
    if backend == "libredwg":
        return "libredwg", find_libredwg(converter)
    try:
        return "oda", find_converter(converter)
    except ConverterNotFoundError:
        return "libredwg", find_libredwg()


def dwg_to_dxf(
    dwg: str | os.PathLike[str],
    out_dir: str | os.PathLike[str] | None = None,
    *,
    backend: str = "auto",
    converter: str | os.PathLike[str] | None = None,
    version: str = DEFAULT_VERSION,
    timeout: int = 600,
) -> Path:
    """Convert one DWG file to DXF and return the DXF path.

    The DXF is written to ``out_dir`` (default: a ``_dxf`` folder beside the DWG).
    """
    source = Path(dwg).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"DWG file not found: {source}")
    if source.suffix.lower() != ".dwg":
        raise ValueError(f"Not a DWG file: {source}")

    target_dir = Path(out_dir).resolve() if out_dir else source.parent / "_dxf"
    target_dir.mkdir(parents=True, exist_ok=True)
    dxf = target_dir / f"{source.stem}.dxf"

    name, exe = _select_backend(backend, converter)
    if name == "oda":
        command = build_command(exe, source.parent, target_dir, source.name, version)
    else:
        command = build_libredwg_command(exe, source, dxf)

    result = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )

    if result.returncode != 0 or not dxf.is_file():
        error_log = target_dir / f"{source.name}.err"
        detail = error_log.read_text(errors="replace") if error_log.is_file() else ""
        raise ConversionError(
            f"{name} conversion failed for {source.name} (exit {result.returncode}). "
            f"{result.stderr.strip()[-500:]} {detail}".strip()
        )
    return dxf


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) not in (1, 2):
        print("Usage: python -m structiq.drawing.convert <file.dwg> [output folder]")
        return 2
    dxf = dwg_to_dxf(args[0], args[1] if len(args) == 2 else None)
    print(dxf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
