"""StructIQ A3 structural drawing template, converted from the sample structural set.

Everything here was measured from ``PJR-2026-002_7 Story Mix Use Building.pdf``
(12 sheets, A3 landscape, exported from Revit): sheet frame, title block cells and
fonts, text sizes, grid/section symbols, dash patterns and colours, general notes.

What the PDF could **not** give: lineweights. Every stroke in the export is 0.08 mm
(a "thin lines" export), so the lineweights below are proposals, not measurements.

Paper-space rule: text is ``TEXT_HEIGHT`` = 1.5 mm *at A3* (the cap height of Arial
6 pt). Model-space text and dimensions are scaled by the viewport scale (see
``model_text_height``); the template defines one dimension style per scale. Linetypes
are defined in paper mm and, with LTSCALE = 1 and PSLTSCALE = 1 (both set here), print
at that length in a viewport of any scale: do not change LTSCALE per viewport.

``define_styles(doc)`` adds the linetypes, text styles, dimension styles and layers
to any document, so generated layouts use the same styles as the template.
``build_template()`` makes the full template document.

Usage::

    python -m structiq.drawing.template "<output folder>"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment

SHEET_W, SHEET_H = 420.0, 297.0  # A3 landscape, mm
TEXT_HEIGHT = 1.5  # mm at A3 (Arial cap height, = 6 pt)
HEADING_HEIGHT = 2.0  # mm at A3 (8 pt): block titles, section ID, title block values
SMALL_HEIGHT = 1.3  # mm at A3 (5.1 pt): sheet number under a section marker
SCALES = (20, 25, 50, 75, 100, 120, 130, 150, 200)  # scales used in the sample, plus 1:20/1:200

# Sheet frame (mm from the top-left corner of the sheet, as in the sample)
OUTER = (0.2, 0.0, 408.3, 297.0)
INNER = (11.8, 5.0, 403.3, 292.0)
TITLE_BAND_BOTTOM = 27.0
ROW1, ROW2 = (7.0, 15.0), (17.0, 25.0)
# (label, tag, label x0, label x1 = value x0, value x1, row)
TITLE_CELLS = [
    ("PROJ. REFERENCE:", "PROJ_REF", 13.8, 45.8, 80.8, ROW1, "PJR-YYYY-NNN"),
    ("DRAWING NAME:", "DRAWING_NAME", 82.8, 114.8, 234.2, ROW1, "DRAWING NAME"),
    ("REVISION:", "REVISION", 236.2, 268.2, 292.2, ROW1, ""),
    ("DRAWN BY:", "DRAWN_BY", 294.2, 323.2, 349.3, ROW1, ""),
    ("DRAWING NUMBER:", "DRAWING_NO", 13.8, 45.8, 80.8, ROW2, "OF-STR-SD-100"),
    ("DRAWING STAGE:", "STAGE", 82.8, 114.8, 157.5, ROW2, "SHOP DRAWING"),
    ("CLIENT:", "CLIENT", 159.5, 191.5, 234.2, ROW2, "CLIENT NAME"),
    ("SCALE:", "SCALE", 236.2, 268.2, 292.2, ROW2, "AS-SHOWN"),
    ("ISSUE DATE:", "ISSUE_DATE", 294.2, 323.2, 349.3, ROW2, "DD-MMM-YYYY"),
]
KEY_BOX = (349.3, 5.0, 403.3, 27.0)  # grey frame holding the north arrow / logo box
KEY_INNER = (351.3, 7.0, 401.3, 25.0)

GENERAL_NOTES = [
    "UNLESS OTHERWISE STATED.",
    "1.  ALL DIMENSIONS ARE IN MILLIMETERS.",
    "2.  ALL DIMENSIONS ARE TO BE READ IN CONJUNCTION WITH OTHER DISCIPLINE PRIOR TO "
    "FABRICATION OR CONSTRUCTION.",
    "3.  STEEL REINFORCEMENT SHALL BE HIGH YIELD BAR WITH Fy = 390MPa FOR DIA ≥10mm "
    "AND Fy = 235MPa FOR DIA < 10mm.",
    "4.  ALL CONCRETE CHAIR SHALL BE THE SAME AS THE GRADE OF THE CONCRETE ELEMENT TO BE CASTED.",
    "5.  CONCRETE STRENGTH SLAB AND STAIR C30/37",
]
PILING_NOTES = [  # sheet 2 of the sample, with its project values blanked out
    "ALL PILES ARE TO BE PLACED AND INSTALLED WITHIN 75MM FROM THE CORRECT POSITION.",
    "UNLESS OTHERWISE STATED ALL STRUCTURAL CONCRETE TO BE USED FOR FOUNDATION SHALL BE "
    "GRADE ___ WITH CYLINDER STRENGTH OF ___ MPA @ 28 DAYS.",
    "ALL CONCRETE SPACER SHALL BE THE SAME GRADE OF THE CONCRETE ELEMENT TO BE CASTED.",
    "STEEL REINFORCEMENT SHALL BE HIGH YIELD BAR WITH fy = 390 MPa FOR D>10MM AND "
    "fy = 235 MPa D<10MM.",
    "PILING RECORDS TO BE KEPT FOR EVERY PILE. SET CALCULATION TO ACHIEVE REQUIRED CAPACITY "
    "TO BE SUBMITTED BY THE CONTRACTOR FOR ENGINEER'S APPROVAL.",
    "CONTRACTOR SHALL SUBMIT SPECIMEN SAMPLE OF ALL MATERIALS PRIOR TO APPROVAL. ALL "
    "MATERIAL SHALL MEET BS STANDARD CODES AND SPECIFICATION.",
    "WORKING LOAD OF BORED PILE : BP1(D___mm,DEPTH ___m) = ___ kN, BP2(D___mm,DEPTH ___m) = "
    "___ kN. SAFETY FACTOR ___.",
    "A PILE TESTING PROPOSAL SHALL BE SUBMITTED FOR THE ENGINEER'S APPROVAL PRIOR TO "
    "COMMENCEMENT OF PILING WORKS.",
]

BLACK = (0, 0, 0)
MAROON = (64, 0, 0)  # title block text, #400000
GREY = (192, 192, 192)  # concrete fill / hatch, #c0c0c0
TEAL = (64, 128, 128)  # gridlines, #408080
DARK_RED = (128, 0, 0)  # section lines, #800000
BROWN = (128, 64, 0)  # beams below / hidden, #804000
BLUE = (0, 128, 255)  # stair and lift openings, #0080ff
OLIVE = (128, 128, 0)  # level marks, #808000
LIME = (0, 255, 0)  # opening cross lines, #00ff00

# Linetypes: patterns in paper mm (dash +, gap -). Keep LTSCALE = 1 and PSLTSCALE = 1.
LINETYPES = {
    "STIQ-GRID": ("Grid: dash 6, gap 1, dot 1, gap 1", [9.0, 6.0, -1.0, 1.0, -1.0]),
    "STIQ-SECTION": ("Section line: dash 2, gap 0.6, dot 0.6, gap 0.6", [3.8, 2.0, -0.6, 0.6, -0.6]),
    "STIQ-DOT": ("Hidden / below: 0.6 on, 0.6 off", [1.2, 0.6, -0.6]),
    "STIQ-OPENING": ("Opening cross: 0.75 on, 0.75 off", [1.5, 0.75, -0.75]),
}

# name: (rgb, linetype, proposed lineweight in 1/100 mm, description)
LAYERS = {
    "S-TTLB-FRAME": (BLACK, "Continuous", 35, "Sheet frame"),
    "S-TTLB-LINE": (BLACK, "Continuous", 18, "Title block cells"),
    "S-TTLB-TEXT": (MAROON, "Continuous", 13, "Title block labels and values"),
    "S-GRID": (TEAL, "STIQ-GRID", 13, "Gridlines (dash-dot)"),
    "S-GRID-TXT": (BLACK, "Continuous", 13, "Grid labels"),
    "S-GRID-BUBBLE": (BLACK, "Continuous", 18, "Grid bubbles"),
    "S-COLS": (BLACK, "Continuous", 25, "Column outlines"),
    "S-COLS-HATCH": (GREY, "Continuous", 9, "Column fill"),
    "S-COLS-TXT": (BLACK, "Continuous", 13, "Column tags"),
    "S-WALL": (BLACK, "Continuous", 35, "RC walls"),
    "S-WALL-HATCH": (GREY, "Continuous", 9, "RC wall fill (solid grey)"),
    "S-OPEN-X": (LIME, "STIQ-OPENING", 13, "Opening cross lines (X) in shafts and wall openings"),
    "S-SLAB-EDGE": (BLACK, "Continuous", 35, "Slab outline"),
    "S-SLAB-CHECK": (DARK_RED, "Continuous", 13, "Slab items to review"),
    "S-SLAB-TXT": (BLACK, "Continuous", 13, "Slab labels"),
    "S-BEAM": (BROWN, "STIQ-DOT", 13, "Beams below (dotted)"),
    "S-BEAM-PT": (BROWN, "STIQ-DOT", 13, "PT bands (dotted, marked only)"),
    "S-BEAM-TXT": (BLACK, "Continuous", 13, "Beam tags"),
    "S-ANNO-TABLE": (BLACK, "Continuous", 13, "Schedule tables"),
    "S-OPEN": (BLUE, "STIQ-DOT", 13, "Shafts and slab openings (dotted)"),
    "S-OPEN-ROOM": (BLUE, "Continuous", 9, "Rooms next to openings"),
    "S-OPEN-CHECK": (DARK_RED, "Continuous", 13, "Openings to review"),
    "S-OPEN-TXT": (BLACK, "Continuous", 13, "Opening labels"),
    "S-STAIR": (BLUE, "STIQ-DOT", 13, "Stairs (dotted)"),
    "S-STAIR-TXT": (BLACK, "Continuous", 13, "Stair labels"),
    "S-HATCH-CONC": (GREY, "Continuous", 9, "Concrete hatch"),
    "S-ANNO-TEXT": (BLACK, "Continuous", 13, "General text"),
    "S-ANNO-NOTE": (BLACK, "Continuous", 13, "General notes"),
    "S-ANNO-DIMS": (BLACK, "Continuous", 13, "Dimensions"),
    "S-ANNO-SECT": (DARK_RED, "STIQ-SECTION", 13, "Section cut lines"),
    "S-ANNO-SECT-MARK": (BLACK, "Continuous", 18, "Section markers and end bars"),
    "S-ANNO-LEVEL": (OLIVE, "Continuous", 13, "Level marks"),
    "S-ANNO-TAG": (BLACK, "Continuous", 13, "Element tags"),
    "S-ANNO-VIEWTITLE": (BLACK, "Continuous", 13, "View and section titles"),
    "S-VPORT": (BLACK, "Continuous", 13, "Viewport frames (no plot)"),
}


def model_text_height(scale: int, paper_mm: float = TEXT_HEIGHT) -> float:
    """Model-space text height so it prints at ``paper_mm`` on a 1:scale viewport."""
    return paper_mm * scale


def text_height_for(scales: dict[int, int]):
    """Return ``height(plan)``: the model-space height that prints at 1.5 mm on that plan's sheet."""
    return lambda plan: model_text_height(scales.get(plan, 100))


def _aci_for(rgb) -> int:
    return {
        BLACK: 7, MAROON: 1, GREY: 8, TEAL: 4, DARK_RED: 1, BROWN: 30, BLUE: 5, OLIVE: 62, LIME: 3
    }[rgb]


def define_styles(doc) -> None:
    """Add StructIQ linetypes, text styles, dimension styles and layers (idempotent)."""
    doc.units = 4  # mm
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LTSCALE"] = 1.0
    doc.header["$PSLTSCALE"] = 1
    doc.header["$LWDISPLAY"] = 1

    for name, (desc, pattern) in LINETYPES.items():
        if name not in doc.linetypes:
            doc.linetypes.add(name, pattern=pattern, description=desc)

    for name, font in (
        ("STIQ-TEXT", "arial.ttf"),
        ("STIQ-TEXT-BOLD", "arialbd.ttf"),
        ("STIQ-TTLB-LABEL", "Inkfree.ttf"),
        ("STIQ-TTLB-VALUE", "arialbd.ttf"),
    ):
        if name not in doc.styles:
            doc.styles.add(name, font=font)

    for scale in SCALES:
        name = f"STIQ-{scale}"
        if name in doc.dimstyles:
            continue
        ds = doc.dimstyles.new(
            name,
            dxfattribs={
                "dimtxsty": "STIQ-TEXT",
                "dimtxt": TEXT_HEIGHT,  # paper mm, multiplied by DIMSCALE
                "dimscale": scale,
                "dimasz": 0.6,
                "dimexe": 1.0,
                "dimexo": 1.0,
                "dimgap": 0.6,
                "dimtad": 1,  # text above the dimension line
                "dimtih": 0,
                "dimtoh": 0,
                "dimdec": 0,
                "dimzin": 8,
                "dimlunit": 2,
            },
        )
        ds.set_arrows(blk=ezdxf.ARROWS.dot_small)

    for name, (rgb, linetype, weight, desc) in LAYERS.items():
        if name in doc.layers:
            continue
        layer = doc.layers.add(name, color=_aci_for(rgb), linetype=linetype, lineweight=weight)
        layer.description = desc
        layer.rgb = rgb
        if name == "S-VPORT":
            layer.dxf.plot = 0


def _y(top_mm: float) -> float:
    """Sample coordinates run down from the top of the sheet; DXF runs up from the bottom."""
    return SHEET_H - top_mm


def _rect(blk, x0, y0, x1, y1, layer):
    return blk.add_lwpolyline(
        [(x0, _y(y0)), (x1, _y(y0)), (x1, _y(y1)), (x0, _y(y1))],
        close=True,
        dxfattribs={"layer": layer},
    )


def _fill(blk, points, rgb, layer):
    hatch = blk.add_hatch(dxfattribs={"layer": layer})
    hatch.rgb = rgb
    hatch.paths.add_polyline_path(points, is_closed=True)
    return hatch


def _title_block(doc) -> None:
    blk = doc.blocks.new("STIQ-TITLEBLOCK")
    _rect(blk, *OUTER, "S-TTLB-FRAME")
    _rect(blk, *INNER, "S-TTLB-FRAME")
    blk.add_line(
        (INNER[0], _y(TITLE_BAND_BOTTOM)), (INNER[2], _y(TITLE_BAND_BOTTOM)),
        dxfattribs={"layer": "S-TTLB-FRAME"},
    )
    for label, tag, x0, xm, x1, (r0, r1), default in TITLE_CELLS:
        _rect(blk, x0, r0, xm, r1, "S-TTLB-LINE")
        _rect(blk, xm, r0, x1, r1, "S-TTLB-LINE")
        mid = _y((r0 + r1) / 2)
        blk.add_text(
            label,
            height=HEADING_HEIGHT,
            dxfattribs={"style": "STIQ-TTLB-LABEL", "layer": "S-TTLB-TEXT"},
        ).set_placement((x0 + 1.2, mid), align=TextEntityAlignment.MIDDLE_LEFT)
        att = blk.add_attdef(
            tag,
            (xm + 1.2, mid),
            text=default,
            height=HEADING_HEIGHT,
            dxfattribs={"style": "STIQ-TTLB-VALUE", "layer": "S-TTLB-TEXT"},
        )
        att.set_placement((xm + 1.2, mid), align=TextEntityAlignment.MIDDLE_LEFT)

    kx0, ky0, kx1, ky1 = KEY_BOX
    _fill(blk, [(kx0, _y(ky0)), (kx1, _y(ky0)), (kx1, _y(ky1)), (kx0, _y(ky1))], GREY, "S-TTLB-FRAME")
    ix0, iy0, ix1, iy1 = KEY_INNER
    white = _fill(blk, [(ix0, _y(iy0)), (ix1, _y(iy0)), (ix1, _y(iy1)), (ix0, _y(iy1))], (255, 255, 255), "S-TTLB-FRAME")
    white.dxf.hatch_style = 0
    _rect(blk, ix0, iy0, ix1, iy1, "S-TTLB-LINE")
    # north arrow in the top-right corner of the key box
    nx, ny = 398.5, _y(14.0)
    blk.add_text(
        "N", height=HEADING_HEIGHT, dxfattribs={"style": "STIQ-TTLB-LABEL", "layer": "S-TTLB-TEXT"}
    ).set_placement((nx, ny + 6.5), align=TextEntityAlignment.MIDDLE_CENTER)
    _fill(blk, [(nx - 1.4, ny + 2.0), (nx + 1.4, ny + 2.0), (nx, ny + 5.0)], MAROON, "S-TTLB-TEXT")


def _notes(doc, name: str, heading: str, items: list[str], numbered: bool, heading_height: float) -> None:
    blk = doc.blocks.new(name)
    blk.add_mtext(
        f"\\L{heading}\\l",
        dxfattribs={
            "style": "STIQ-TEXT-BOLD",
            "char_height": heading_height,
            "layer": "S-ANNO-NOTE",
            "insert": (0.0, 0.0),
            "attachment_point": 1,
        },
    )
    text = "\\P".join(
        f"{i})  {t}" if numbered else t for i, t in enumerate(items, 1)
    )
    blk.add_mtext(
        text,
        dxfattribs={
            "style": "STIQ-TEXT",
            "char_height": TEXT_HEIGHT,
            "width": 70.0,
            "layer": "S-ANNO-NOTE",
            "insert": (0.0, -4.8),
            "attachment_point": 1,
            "line_spacing_factor": 0.96,  # 2.4 mm pitch, as in the sample
        },
    )


def _symbols(doc) -> None:
    # Grid bubble: circle 5.0 mm, label Arial Bold 1.5 mm
    b = doc.blocks.new("STIQ-GRID-BUBBLE")
    b.add_circle((0, 0), 2.5, dxfattribs={"layer": "S-GRID-BUBBLE"})
    b.add_attdef("GRID", (0, 0), text="A", height=TEXT_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT-BOLD", "layer": "S-GRID-TXT"}
                 ).set_placement((0, 0), align=TextEntityAlignment.MIDDLE_CENTER)

    # Section marker: 6.0 mm circle, 9.0 x 5.7 mm direction triangle, ID 2.0 mm,
    # sheet number 1.3 mm below (circle centre at the origin, view direction +Y)
    s = doc.blocks.new("STIQ-SECTION-MARK")
    s.add_circle((0, 0), 3.0, dxfattribs={"layer": "S-ANNO-SECT-MARK"})
    _fill(s, [(-4.5, 3.0), (4.5, 3.0), (0.0, 8.7)], BLACK, "S-ANNO-SECT-MARK")
    s.add_attdef("SECTION_ID", (0, 0), text="A1", height=HEADING_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-TEXT"}
                 ).set_placement((0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    s.add_attdef("SHEET_NO", (0, -4.2), text="OF-STR-SD-101", height=SMALL_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-TEXT"}
                 ).set_placement((0, -4.2), align=TextEntityAlignment.MIDDLE_CENTER)

    # Section line end bar: 1.0 x 5.0 mm solid black
    e = doc.blocks.new("STIQ-SECTION-END")
    _fill(e, [(-0.5, -2.5), (0.5, -2.5), (0.5, 2.5), (-0.5, 2.5)], BLACK, "S-ANNO-SECT-MARK")

    # View / section title: 6.0 mm circle with ID, title 2.0 mm, underline 22.5 mm, scale 1.5 mm
    t = doc.blocks.new("STIQ-VIEW-TITLE")
    t.add_circle((0, 0), 3.0, dxfattribs={"layer": "S-ANNO-VIEWTITLE"})
    t.add_attdef("VIEW_ID", (0, 0), text="1", height=HEADING_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-VIEWTITLE"}
                 ).set_placement((0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    t.add_attdef("TITLE", (4.5, 0.6), text="VIEW OR SECTION TITLE", height=HEADING_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-VIEWTITLE"}
                 ).set_placement((4.5, 0.6), align=TextEntityAlignment.MIDDLE_LEFT)
    t.add_line((4.5, -0.9), (27.0, -0.9), dxfattribs={"layer": "S-ANNO-VIEWTITLE"})
    t.add_attdef("SCALE", (3.5, -3.0), text="Scale :1 : 100", height=TEXT_HEIGHT,
                 dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-VIEWTITLE"}
                 ).set_placement((3.5, -3.0), align=TextEntityAlignment.MIDDLE_LEFT)

    # Level mark: 3.0 x 2.0 mm olive inverted triangle, level text and name 1.5 mm
    lv = doc.blocks.new("STIQ-LEVEL-MARK")
    _fill(lv, [(-1.5, 2.0), (1.5, 2.0), (0.0, 0.0)], OLIVE, "S-ANNO-LEVEL")
    lv.add_attdef("LEVEL", (2.5, 1.0), text="+0.000 (SFL)", height=TEXT_HEIGHT,
                  dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-LEVEL"}
                  ).set_placement((2.5, 1.0), align=TextEntityAlignment.MIDDLE_LEFT)
    lv.add_attdef("NAME", (2.5, -1.6), text="GF", height=TEXT_HEIGHT,
                  dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-LEVEL"}
                  ).set_placement((2.5, -1.6), align=TextEntityAlignment.MIDDLE_LEFT)

    # Element tag: hexagon 9.0 x 4.5 mm, tag text 1.5 mm
    tg = doc.blocks.new("STIQ-TAG-HEX")
    tg.add_lwpolyline(
        [(-4.5, 0.0), (-3.0, 2.25), (3.0, 2.25), (4.5, 0.0), (3.0, -2.25), (-3.0, -2.25)],
        close=True, dxfattribs={"layer": "S-ANNO-TAG"},
    )
    tg.add_attdef("TAG", (0, 0), text="C01", height=TEXT_HEIGHT,
                  dxfattribs={"style": "STIQ-TEXT", "layer": "S-ANNO-TAG"}
                  ).set_placement((0, 0), align=TextEntityAlignment.MIDDLE_CENTER)


def add_sheet_blocks(doc) -> None:
    """Add the title block, note and annotation symbol blocks (idempotent)."""
    define_styles(doc)
    if "STIQ-TITLEBLOCK" in doc.blocks:
        return
    _title_block(doc)
    _notes(doc, "STIQ-GENERAL-NOTES", "NOTE:", GENERAL_NOTES, False, TEXT_HEIGHT)
    _notes(doc, "STIQ-NOTES-PILING", "NOTE IN PILING", PILING_NOTES, True, HEADING_HEIGHT)
    _symbols(doc)


def viewport_area() -> tuple[float, float, float, float]:
    """Drawing area inside the frame, below the title band (paper mm, y up): l, b, r, t."""
    return (
        INNER[0] + 1.0,
        SHEET_H - INNER[3] + 1.0,
        INNER[2] - 1.0,
        SHEET_H - TITLE_BAND_BOTTOM - 1.0,
    )


def fit_scale(width_mm: float, height_mm: float, factor: float = 0.95) -> int:
    """Smallest standard scale (1:n) at which a model-space box fits the viewport.

    ``factor`` keeps a margin. If even 1:200 is too small, the scale is rounded up to
    the next multiple of 50.
    """
    l, b, r, t = viewport_area()
    avail_w, avail_h = (r - l) * factor, (t - b) * factor
    need = max(width_mm / avail_w, height_mm / avail_h)
    for s in SCALES:
        if s >= need:
            return s
    return int(-(-need // 50) * 50)


def add_sheet(
    doc,
    name: str,
    fields: dict[str, str],
    view_center: tuple[float, float],
    scale: int,
    extent: tuple[float, float] | None = None,
    schedule: dict | None = None,
):
    """Add an A3 layout with the title block filled from ``fields`` and one viewport.

    ``fields`` maps title block tags (PROJ_REF, DRAWING_NAME, ...) to text; tags that are
    missing are left blank. The viewport shows model space at 1:``scale`` centred on
    ``view_center``. With ``extent`` = (width, height) in model units the viewport is
    cut to just that box (so neighbouring plans in model space stay out of the sheet);
    without it the viewport fills the whole drawing area. ``schedule`` =
    {"title": str, "rows": [(level, mark, type, fck), ...]} adds a framing schedule table
    above the general notes (see ``add_schedule_table``).
    """
    add_sheet_blocks(doc)
    layout = doc.layouts.new(name)
    layout.page_setup(
        size=(SHEET_W, SHEET_H),
        margins=(0, 0, 0, 0),
        units="mm",
        offset=(0, 0),
        rotation=0,
        scale=(1, 1),  # plot scale 1:1 (a plain int would pick a standard scale such as 1:1689)
        name="ISO_A3_(420.00_x_297.00_MM)",
        device="DWG To PDF.pc3",
    )
    tb = layout.add_blockref("STIQ-TITLEBLOCK", (0, 0), dxfattribs={"layer": "S-TTLB-LINE"})
    tb.add_auto_attribs({tag: fields.get(tag, "") for _, tag, *_r in TITLE_CELLS})
    layout.add_blockref("STIQ-GENERAL-NOTES", (332.4, _y(263.7)), dxfattribs={"layer": "S-ANNO-NOTE"})

    l, b, r, t = viewport_area()
    width, height = r - l, t - b
    if extent is not None:
        width, height = min(width, extent[0] / scale), min(height, extent[1] / scale)
    layout.add_viewport(
        center=((l + r) / 2, (t + b) / 2),
        size=(width, height),
        view_center_point=view_center,
        view_height=height * scale,
        status=2,  # 1 is the layout's own main viewport (created by page_setup)
        dxfattribs={"layer": "S-VPORT"},
    )
    if schedule and schedule.get("rows"):
        add_schedule_table(layout, schedule["title"], schedule["rows"])
    # page_setup made the main viewport fit the paper (1:1), which is what AutoCAD uses
    # for the first display of the sheet. Give the layout real extents as well.
    layout.reset_extents(extmin=(0.0, 0.0, 0.0), extmax=(SHEET_W, SHEET_H, 0.0))
    return layout


SCHEDULE_COLS = (10.0, 12.0, 32.0, 16.0)  # Level, Mark, Type, Fck (mm at A3)
SCHEDULE_ROW = 3.4
SCHEDULE_X = 332.4  # left edge, same as the general notes
SCHEDULE_BOTTOM = 37.0  # paper y of the table bottom, just above the notes


def add_schedule_table(layout, title: str, rows: list[tuple[str, str, str, str]]) -> None:
    """Framing schedule like the sample: title row, header row (Level, Mark, Type, Fck), rows."""
    widths = SCHEDULE_COLS
    total_w = sum(widths)
    n = len(rows)
    height = SCHEDULE_ROW * (n + 2) + 1.6  # title row is a little taller
    x0, y0 = SCHEDULE_X, SCHEDULE_BOTTOM
    top = y0 + height
    attrs = {"layer": "S-ANNO-TABLE"}
    text_attrs = {"layer": "S-ANNO-TEXT", "style": "STIQ-TEXT"}
    layout.add_lwpolyline(
        [(x0, y0), (x0 + total_w, y0), (x0 + total_w, top), (x0, top)], close=True, dxfattribs=attrs
    )
    title_y = top - (SCHEDULE_ROW + 1.6)
    layout.add_line((x0, title_y), (x0 + total_w, title_y), dxfattribs=attrs)
    layout.add_text(title, height=TEXT_HEIGHT, dxfattribs=text_attrs).set_placement(
        (x0 + total_w / 2, top - (SCHEDULE_ROW + 1.6) / 2), align=TextEntityAlignment.MIDDLE_CENTER
    )
    header_y = title_y - SCHEDULE_ROW
    layout.add_line((x0, header_y), (x0 + total_w, header_y), dxfattribs=attrs)
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    for x in xs[1:-1]:
        layout.add_line((x, y0), (x, title_y), dxfattribs=attrs)
    for i, label in enumerate(("Level", "Mark", "Type", "Fck (MPa)")):
        layout.add_text(label, height=TEXT_HEIGHT, dxfattribs=text_attrs).set_placement(
            ((xs[i] + xs[i + 1]) / 2, title_y - SCHEDULE_ROW / 2), align=TextEntityAlignment.MIDDLE_CENTER
        )
    for r, row in enumerate(rows):
        y = header_y - SCHEDULE_ROW * (r + 0.5)
        for i, cell in enumerate(row):
            align = TextEntityAlignment.MIDDLE_LEFT if i == 2 else TextEntityAlignment.MIDDLE_CENTER
            px = xs[i] + 1.0 if i == 2 else (xs[i] + xs[i + 1]) / 2
            layout.add_text(cell, height=TEXT_HEIGHT, dxfattribs=text_attrs).set_placement((px, y), align=align)


def open_on_sheet(doc, name: str) -> None:
    """Make AutoCAD open the drawing on sheet ``name`` instead of the Model tab.

    The title block, notes and viewport live in the sheet (paper space), so a drawing that
    opens on the Model tab shows no title block until the sheet tab is clicked.
    """
    doc.layouts.set_active_layout(name)
    doc.header["$TILEMODE"] = 0


def build_template():
    """Return the full template document (model space empty; layout 'A3' ready to use)."""
    doc = ezdxf.new("R2018", setup=False)
    defaults = {tag: default for _, tag, *_r, default in TITLE_CELLS}
    add_sheet(doc, "A3", defaults, (0.0, 0.0), 100)
    if "Layout1" in doc.layouts:  # the default layout; a paper space layout must always remain
        doc.layouts.delete("Layout1")
    open_on_sheet(doc, "A3")
    return doc


def next_revision(out_dir: Path, stem: str) -> int:
    pattern = re.compile(rf"^{re.escape(stem)} Rev (\d\d)\.dxf$", re.I)
    found = [int(m.group(1)) for f in out_dir.glob("*.dxf") if (m := pattern.match(f.name))]
    return max(found) + 1 if found else 0


def write_template(out_dir: str | Path, stem: str = "STIQ-A3 Structural Template") -> Path:
    """Write the template as the next revision; earlier revisions are never overwritten."""
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stem} Rev {next_revision(folder, stem):02d}.dxf"
    build_template().saveas(path)
    return path


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print('Usage: python -m structiq.drawing.template "<output folder>"')
        return 2
    print(write_template(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
