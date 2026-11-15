"""Move an existing DXF onto the StructIQ layer and text standard. The source file is never modified.

Ported from the SDSA ``restandardise.py`` and made independent of the company title block: it remaps layers
(company names and legacy names, see ``layers``), puts text on the Arial ``STIQ-TEXT`` style, resets per-entity
colour and lineweight overrides to ByLayer, and falls back to ByLayer for linetypes the file does not define.
Geometry is not edited and text heights are not changed. Layers with no mapping are left as they are and
reported: nothing is silently moved. Output is DXF only and has not been seen in AutoCAD.

    python -m structiq.drawing.restandardise "<src.dxf>" "<out folder>" [--drop FRAME ...]

Each run writes the next ``<stem> restandardised Rev NN.dxf`` (+ ``-report.json``); earlier ones are kept.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf

from structiq.drawing import layers as L
from structiq.drawing import template as t

TEXT_TYPES = ("TEXT", "MTEXT")


def restandardise_doc(doc, layer_map: dict[str, str] | None = None, drop: set[str] | None = None) -> dict[str, Any]:
    """Apply the standard to ``doc`` in place; returns a report of what changed and what was left."""
    drop = {d.upper() for d in (drop or set())}
    t.define_styles(doc)
    msp = doc.modelspace()
    moved: Counter[str] = Counter()
    unmapped: Counter[str] = Counter()
    dropped = text_restyled = overrides = 0
    targets: set[str] = set()

    for e in list(msp):
        lay = e.dxf.layer
        if lay.upper() in drop:
            msp.delete_entity(e)
            dropped += 1
            continue
        new = L.resolve(lay, layer_map)
        if new == L.DROP:
            msp.delete_entity(e)
            dropped += 1
            continue
        if new is None:
            unmapped[lay] += 1
        elif new != lay:
            moved[f"{lay}->{new}"] += 1
            e.dxf.layer = new
            targets.add(new)
        else:
            targets.add(lay)
        for attr in ("color", "lineweight", "true_color"):
            if e.dxf.hasattr(attr):
                e.dxf.discard(attr)
                overrides += 1
        if e.dxftype() in TEXT_TYPES and e.dxf.get("style") != "STIQ-TEXT":
            e.dxf.style = "STIQ-TEXT"
            text_restyled += 1

    L.ensure_layers(doc, targets)
    defined = {lt.dxf.name.upper() for lt in doc.linetypes} | {"BYLAYER", "BYBLOCK"}
    linetype_reset = 0
    for e in msp:
        if e.dxf.hasattr("linetype") and e.dxf.linetype.upper() not in defined:
            e.dxf.linetype = "BYLAYER"
            linetype_reset += 1

    return {
        "layer_moves": dict(sorted(moved.items())),
        "unmapped_layers_left_unchanged": dict(sorted(unmapped.items())),
        "entities_dropped": dropped,
        "text_moved_to_STIQ_TEXT": text_restyled,
        "colour_lineweight_overrides_reset": overrides,
        "undefined_linetype_set_bylayer": linetype_reset,
        "note": "Text heights and geometry are unchanged. Not seen in AutoCAD.",
    }


def next_revision(out_dir: Path, stem: str) -> int:
    pattern = re.compile(rf"^{re.escape(stem)} restandardised Rev (\d\d)\.dxf$", re.I)
    found = [int(m.group(1)) for f in out_dir.glob("*.dxf") if (m := pattern.match(f.name))]
    return max(found) + 1 if found else 0


def run(src: str | Path, out_dir: str | Path, drop: set[str] | None = None) -> tuple[Path, dict[str, Any]]:
    src = Path(src)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    doc = ezdxf.readfile(src)
    report = restandardise_doc(doc, drop=drop)
    report["source"] = src.name
    dst = out / f"{src.stem} restandardised Rev {next_revision(out, src.stem):02d}.dxf"
    doc.saveas(dst)
    dst.with_name(f"{dst.stem}-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return dst, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m structiq.drawing.restandardise")
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--drop", nargs="*", default=[], help="layer names whose entities are deleted (e.g. FRAME)")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    dst, report = run(ns.src, ns.out, set(ns.drop))
    print(json.dumps(report, indent=2))
    print(f"Wrote {dst}")
    return 1 if report["unmapped_layers_left_unchanged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
