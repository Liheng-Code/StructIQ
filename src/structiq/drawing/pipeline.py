"""One-command Drawing Intelligence: architect DWG/DXF -> structural layout DXF + report.

Steps: check the Core Brain is readable (and record its version) -> convert DWG to
DXF into the local work cache -> extract grid, columns, RC walls, slabs, openings
and stairs -> write ``S-LAYOUT <name> Rev NN.dxf`` and a DRAFT report into the
project's ``02-Structural Drawing`` folder.

Existing revisions are never overwritten: each run writes the next revision.

Usage::

    python -m structiq.drawing.pipeline "<drawing.dwg|.dxf>" [--rc-layers REGEX] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import ezdxf
import yaml

from structiq.drawing import convert, layout, paths

CONFIG_FILE = Path(__file__).resolve().parents[3] / "config" / "paths.yaml"
SAFETY_RULES = Path("03-Safety Rules") / "safety-rules.md"


class BrainNotFoundError(RuntimeError):
    """The Core Brain folder cannot be read; engineering work must not continue."""


@dataclass
class PipelineResult:
    dxf: Path
    report: Path
    revision: int
    brain_version: str
    report_text: str


def read_brain(brain_dir: str | Path | None = None) -> tuple[Path, str]:
    """Return (brain folder, VERSION). Raises BrainNotFoundError if it is not readable."""
    if brain_dir is None:
        if not CONFIG_FILE.is_file():
            raise BrainNotFoundError(f"Config not found: {CONFIG_FILE} (copy paths.example.yaml)")
        brain_dir = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")).get("core_brain")
    brain = Path(brain_dir) if brain_dir else None
    if brain is None or not (brain / "VERSION").is_file() or not (brain / SAFETY_RULES).is_file():
        raise BrainNotFoundError(
            f"Core Brain not readable at {brain}. Check Google Drive is available offline "
            "and core_brain in config/paths.yaml. Stopping: do not work from memory."
        )
    return brain, (brain / "VERSION").read_text(encoding="utf-8").strip()


def next_revision(out_dir: Path, stem: str) -> int:
    pattern = re.compile(rf"^S-LAYOUT {re.escape(stem)} Rev (\d\d)\.dxf$", re.I)
    found = [int(m.group(1)) for f in out_dir.glob("*.dxf") if (m := pattern.match(f.name))]
    return max(found) + 1 if found else 0


def run(
    source: str | Path,
    *,
    rc_layer_pattern: str | None = None,
    out_dir: str | Path | None = None,
    brain_dir: str | Path | None = None,
) -> PipelineResult:
    src = Path(source).resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Drawing not found: {src}")
    if src.suffix.lower() not in (".dwg", ".dxf"):
        raise ValueError(f"Expected a .dwg or .dxf file: {src}")

    _, brain_version = read_brain(brain_dir)  # stop before any work if the brain is unreadable

    target = Path(out_dir) if out_dir else paths.project_output_dir(src)
    target.mkdir(parents=True, exist_ok=True)

    dxf_in = convert.dwg_to_dxf(src) if src.suffix.lower() == ".dwg" else src
    lay = layout.extract_layout(ezdxf.readfile(dxf_in), rc_layer_pattern)

    rev = next_revision(target, src.stem)
    dxf_out = target / f"S-LAYOUT {src.stem} Rev {rev:02d}.dxf"
    report_out = dxf_out.with_name(f"{dxf_out.stem}-report.txt")
    text = layout.format_layout_report(lay, source=src.name, brain_version=brain_version)
    layout.write_layout(lay, dxf_out)
    report_out.write_text(text + "\n", encoding="utf-8")
    return PipelineResult(dxf_out, report_out, rev, brain_version, text)


def main(argv: list[str] | None = None) -> int:
    logging.disable(logging.CRITICAL)  # ezdxf logs a line per unsupported object copy
    parser = argparse.ArgumentParser(prog="python -m structiq.drawing.pipeline")
    parser.add_argument("drawing", help="architect drawing (.dwg or .dxf)")
    parser.add_argument("--rc-layers", help="regex for layer names that hold RC walls")
    parser.add_argument("--out-dir", help="output folder (default: <project>\\02-Structural Drawing)")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = run(ns.drawing, rc_layer_pattern=ns.rc_layers, out_dir=ns.out_dir)
    except BrainNotFoundError as err:
        print(f"STOPPED: {err}")
        return 3
    print(result.report_text)
    print(f"\nRevision {result.revision:02d} (Core Brain {result.brain_version})")
    print(f"Wrote {result.dxf}\nWrote {result.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
