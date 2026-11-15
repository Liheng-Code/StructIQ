"""Check a StructIQ DXF against the layer and text standard.

Ported in spirit from the SDSA ``validate_dxf.py``, rewritten for the StructIQ standard (decisions in
``docs/merge/layer-mapping.md``): layers from ``layers.standard_layers``, Arial text styles ``STIQ-*``,
A3 sheets with a ``STIQ-TITLEBLOCK``. Text heights are not checked here: model-space height depends on
each sheet's scale (Arial 1.5 mm at A3 = 1.5 x scale).

This validates the DXF file only. It does not validate a DWG, an AutoCAD plot, installed fonts or plot styles,
and a clean result is not an engineering review.

    python -m structiq.drawing.validate "<file.dxf>"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ezdxf

from structiq.drawing import layers as L
from structiq.drawing import template as t

TEXT_TYPES = ("TEXT", "MTEXT", "ATTRIB", "ATTDEF")
TITLE_BLOCK = "STIQ-TITLEBLOCK"
ALWAYS_OK_LAYERS = {"0", "Defpoints", "VIEWPORTS"}  # VIEWPORTS: layer ezdxf gives the sheet's own main viewport
NEEDED_ON_SHEET = ("REVISION", "SCALE", "DRAWING_NAME")  # blank values here are warnings


def _entities(doc):
    for layout in doc.layouts:
        for e in layout:
            yield layout.name, e
    for blk in doc.blocks:
        if blk.name.startswith(("*", "_")):  # anonymous and built-in blocks
            continue
        for e in blk:
            yield f"block {blk.name}", e


def validate(path: str | Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        doc = ezdxf.readfile(path)
    except Exception as exc:  # noqa: BLE001
        return {"file": str(path), "ok": False, "errors": [f"cannot open DXF: {exc}"], "warnings": []}

    for a in doc.audit().errors:
        errors.append(f"audit: {a.message}")
    if doc.header.get("$INSUNITS") != 4:
        errors.append(f"drawing units are not millimetres ($INSUNITS={doc.header.get('$INSUNITS')})")

    std = L.standard_layers()
    used: set[str] = set()
    flagged: set[str] = set()
    for where, e in _entities(doc):
        kind = e.dxftype()
        lay = e.dxf.get("layer", "0")
        used.add(lay)
        if lay in std or lay in ALWAYS_OK_LAYERS:
            if lay == "0" and kind not in ("INSERT", "VIEWPORT") and (lay, where) not in flagged:
                flagged.add((lay, where))
                errors.append(f"{where}: {kind} on layer 0 (use a named layer)")
        elif (lay, "name") not in flagged:
            flagged.add((lay, "name"))
            if lay in L.ALIASES:
                errors.append(f"layer '{lay}' is the company name; StructIQ uses '{L.ALIASES[lay]}'")
            else:
                errors.append(f"layer '{lay}' is not in the layer standard")
        if kind in TEXT_TYPES:
            style = e.dxf.get("style", "Standard")
            if not str(style).startswith("STIQ-") and (style, where) not in flagged:
                flagged.add((style, where))
                errors.append(f"{where}: {kind} uses text style '{style}', not a STIQ- Arial style")

    for name in ("STIQ-TEXT", "STIQ-TEXT-BOLD"):
        if name in doc.styles and not doc.styles.get(name).dxf.font.lower().startswith("arial"):
            errors.append(f"text style {name} font is {doc.styles.get(name).dxf.font}, expected Arial")

    for name in sorted(used):
        if name in L.PROPOSED_LAYERS:
            warnings.append(f"layer {name} is PROPOSED in the company standard (not approved)")
        if name not in std:
            continue
        if name not in doc.layers:
            errors.append(f"layer {name} is used but not defined in the file")
            continue
        rgb, linetype, weight, _ = std[name]
        layer = doc.layers.get(name)
        if layer.color != t._aci_for(rgb):
            errors.append(f"layer {name}: colour {layer.color} != standard {t._aci_for(rgb)}")
        if layer.dxf.linetype.upper() != linetype.upper():
            errors.append(f"layer {name}: linetype {layer.dxf.linetype} != standard {linetype}")
        if layer.dxf.lineweight != weight:
            errors.append(f"layer {name}: lineweight {layer.dxf.lineweight} != standard {weight}")

    sheets = [layout for layout in doc.layouts if layout.name != "Model"]
    title_blocks: dict[str, dict[str, str]] = {}
    if not sheets:
        warnings.append("no paper-space sheet: the plan is not on an A3 sheet")
    for sheet in sheets:
        blocks = [i for i in sheet.query("INSERT") if i.dxf.name == TITLE_BLOCK]
        if len(blocks) != 1:
            errors.append(f"sheet {sheet.name}: expected one {TITLE_BLOCK}, found {len(blocks)}")
            continue
        values = {a.dxf.tag: a.dxf.text.strip() for a in blocks[0].attribs}
        title_blocks[sheet.name] = values
        for tag in NEEDED_ON_SHEET:
            if not values.get(tag):
                warnings.append(f"sheet {sheet.name}: title block {tag} is blank")
        for tag in ("DRAWING_NO", "CLIENT"):
            if tag in values and not values[tag]:
                warnings.append(f"sheet {sheet.name}: title block {tag} is blank (left for the engineer)")

    return {
        "file": str(path),
        "ok": not errors,
        "errors": errors,
        "warnings": sorted(set(warnings)),
        "layers_used": sorted(used),
        "sheets": [s.name for s in sheets],
        "title_blocks": title_blocks,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m structiq.drawing.validate")
    ap.add_argument("dxf")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    res = validate(ns.dxf)
    print(json.dumps(res, indent=2))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
