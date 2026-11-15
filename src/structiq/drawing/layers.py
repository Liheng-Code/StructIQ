"""Layers that StructIQ does not draw itself, and the aliases that map other layer names onto its own.

Source: the company layer standard imported from the SDSA project (05-04, 05-04a, 05-04b approved by the user;
05-04c still PROPOSED) and the decisions in ``docs/merge/layer-mapping.md``:

* StructIQ's own names, colours and sample-set lineweights win where the two standards differ.
* Layers only the company standard has are added here, drawn on demand (``ensure_layers``), so a plain
  layout file does not carry unused layers.
* ``ALIASES`` maps company names onto StructIQ names; ``LEGACY_MAP`` maps the layer names found in older
  drawing sets (FRAME, RC, REBAR...) onto the standard.

Lineweights are in 1/100 mm and follow the sample set scale (0.09 to 0.35 mm).
"""

from __future__ import annotations

from structiq.drawing import template as t

# name: (rgb, linetype, lineweight 1/100 mm, description)
EXTRA_LAYERS: dict[str, tuple[tuple[int, int, int], str, int, str]] = {
    "S-ANNO-LEADER": (t.BLACK, "Continuous", 13, "Leaders"),
    "S-STEEL-OUTLINE": (t.BLACK, "Continuous", 35, "Structural steel outlines"),
    "S-CONC-OUTLINE": (t.BLACK, "Continuous", 35, "Concrete outlines (imported or restandardised sheets)"),
    "S-HATCH-STEEL": (t.BLACK, "Continuous", 9, "Steel hatch"),
    "S-VIEW-ISO": (t.BLACK, "Continuous", 18, "Isometric / schematic views"),
    "S-REBAR": (t.DARK_RED, "Continuous", 25, "Reinforcement bars"),
    "S-STEEL-BRACE": (t.MAGENTA, "Continuous", 25, "Bracing members"),
    "S-MASONRY": (t.BROWN, "Continuous", 18, "Masonry / brickwork (restandardised sheets only)"),
    "S-SOIL": (t.GREY, "Continuous", 13, "Soil / ground lines"),
    "S-DETAIL-THIN": (t.GREY, "Continuous", 13, "Thin detail and construction lines"),
    "S-HIDDEN": (t.GREY, "STIQ-DOT", 13, "Hidden / below-ground outlines"),
}

# Proposed by the company standard (05-04c) but NOT approved: validation warns when they are used.
PROPOSED_LAYERS: dict[str, tuple[tuple[int, int, int], str, int, str]] = {
    "S-PT-TENDON": (t.LIME, "Continuous", 18, "Post-tensioning tendon lines in plan (PROPOSED)"),
    "S-CONC-DROP": (t.TEAL, "Continuous", 18, "Drop panels and thickened slab bands (PROPOSED)"),
}

# Company name -> StructIQ name (user decision 2026-11-15)
ALIASES: dict[str, str] = {
    "S-SECT-CUT": "S-ANNO-SECT",
    "S-TBLK-BORDER": "S-TTLB-FRAME",
    "S-TBLK-LINE": "S-TTLB-LINE",
    "S-TBLK-TEXT": "S-TTLB-TEXT",
}

DROP = "__DROP__"
# Layer names found in older drawing sets -> standard layer. The old title strip is handled by the caller.
LEGACY_MAP: dict[str, str] = {
    "FRAME": DROP,
    "TEXT": "S-ANNO-TEXT",
    "NOTE": "S-ANNO-NOTE",
    "DIM": "S-ANNO-DIMS",
    "GRID": "S-GRID",
    "STEEL": "S-STEEL-OUTLINE",
    "RC": "S-CONC-OUTLINE",
    "HATCH": "S-HATCH-CONC",
    "REBAR": "S-REBAR",
    "BRACE": "S-STEEL-BRACE",
    "BRICK": "S-MASONRY",
    "SOIL": "S-SOIL",
    "THIN": "S-DETAIL-THIN",
    "HIDDEN": "S-HIDDEN",
    "TITLE": "S-ANNO-TEXT",
    "0": "S-DETAIL-THIN",
}


def standard_layers() -> dict[str, tuple[tuple[int, int, int], str, int, str]]:
    """Every layer the standard knows: StructIQ's own, the company extras and the proposed ones."""
    return {**t.LAYERS, **EXTRA_LAYERS, **PROPOSED_LAYERS}


def resolve(name: str, layer_map: dict[str, str] | None = None) -> str | None:
    """Standard layer for ``name``: itself if standard, an alias, a legacy name, else None (unmapped)."""
    known = standard_layers()
    if name in known:
        return name
    if name in ALIASES:
        return ALIASES[name]
    return (layer_map if layer_map is not None else LEGACY_MAP).get(name.upper() if name != "0" else name)


def ensure_layers(doc, names) -> None:
    """Define the named standard layers in ``doc`` (linetypes first); layers already there are untouched."""
    t.define_styles(doc)
    known = standard_layers()
    for name in sorted(set(names)):
        if name in doc.layers or name not in known:
            continue
        rgb, linetype, weight, desc = known[name]
        layer = doc.layers.add(name, color=t._aci_for(rgb), linetype=linetype, lineweight=weight)
        layer.description = desc
        layer.rgb = rgb
