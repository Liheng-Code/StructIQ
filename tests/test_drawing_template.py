import ezdxf
import pytest

from structiq.drawing import template as tpl


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    path = tpl.write_template(tmp_path_factory.mktemp("tpl"))
    return ezdxf.readfile(path)


def test_text_styles_use_arial_and_ink_free(doc):
    fonts = {s.dxf.name: s.dxf.font.lower() for s in doc.styles if s.dxf.name.startswith("STIQ")}
    assert fonts["STIQ-TEXT"] == "arial.ttf"
    assert fonts["STIQ-TEXT-BOLD"] == "arialbd.ttf"
    assert fonts["STIQ-TTLB-LABEL"] == "inkfree.ttf"


def test_text_height_is_1_5_mm_at_a3_and_scales_with_the_viewport():
    assert tpl.TEXT_HEIGHT == 1.5
    assert tpl.model_text_height(100) == 150.0
    assert tpl.model_text_height(50) == 75.0


def test_dimension_styles_per_scale_print_1_5_mm(doc):
    for scale in tpl.SCALES:
        ds = doc.dimstyles.get(f"STIQ-{scale}")
        assert ds.dxf.dimtxt == 1.5 and ds.dxf.dimscale == scale


def _elements(doc, name):
    """Dash (+) and gap (-) lengths of a linetype, from DXF group code 49."""
    return [round(v, 3) for code, v in doc.linetypes.get(name).pattern_tags.tags if code == 49]


def test_linetype_patterns_match_the_sample(doc):
    assert _elements(doc, "STIQ-GRID") == [6.0, -1.0, 1.0, -1.0]
    assert _elements(doc, "STIQ-SECTION") == [2.0, -0.6, 0.6, -0.6]
    assert _elements(doc, "STIQ-DOT") == [0.6, -0.6]


def test_layers_carry_sample_colours_and_linetypes(doc):
    grid = doc.layers.get("S-GRID")
    assert grid.rgb == (64, 128, 128) and grid.dxf.linetype == "STIQ-GRID"
    assert doc.layers.get("S-ANNO-SECT").rgb == (128, 0, 0)
    assert doc.layers.get("S-TTLB-TEXT").rgb == (64, 0, 0)
    assert doc.layers.get("S-VPORT").dxf.plot == 0


def test_title_block_has_all_nine_fields_and_ten_frame_pieces(doc):
    blk = doc.blocks.get("STIQ-TITLEBLOCK")
    tags = {a.dxf.tag for a in blk.query("ATTDEF")}
    assert tags == {t[1] for t in tpl.TITLE_CELLS} and len(tags) == 9
    labels = {t.dxf.text for t in blk.query("TEXT")}
    assert {"PROJ. REFERENCE:", "DRAWING NAME:", "DRAWN BY:", "ISSUE DATE:"} <= labels


def test_a3_layout_has_title_block_notes_and_viewport(doc):
    layout = doc.layouts.get("A3")
    assert layout.dxf.paper_width == 420.0 and layout.dxf.paper_height == 297.0
    inserts = {i.dxf.name for i in layout.query("INSERT")}
    assert {"STIQ-TITLEBLOCK", "STIQ-GENERAL-NOTES"} <= inserts
    assert len(layout.query("VIEWPORT")) >= 1


def test_general_notes_and_blocks(doc):
    notes = doc.blocks.get("STIQ-GENERAL-NOTES")
    text = " ".join(m.text for m in notes.query("MTEXT"))
    assert "ALL DIMENSIONS ARE IN MILLIMETERS" in text and "C30/37" in text
    for name in (
        "STIQ-GRID-BUBBLE",
        "STIQ-SECTION-MARK",
        "STIQ-SECTION-END",
        "STIQ-VIEW-TITLE",
        "STIQ-LEVEL-MARK",
        "STIQ-TAG-HEX",
        "STIQ-NOTES-PILING",
    ):
        assert name in doc.blocks
    bubble = doc.blocks.get("STIQ-GRID-BUBBLE")
    assert bubble.query("CIRCLE").first.dxf.radius == 2.5  # 5.0 mm bubble


def test_main_viewport_is_fitted_to_the_sheet_so_it_does_not_open_as_a_dot(doc):
    layout = doc.layouts.get("A3")
    main = sorted(layout.query("VIEWPORT"), key=lambda v: v.dxf.id)[0]
    assert main.dxf.id == 1
    assert 297 <= main.dxf.view_height <= 400  # about the sheet height, not hundreds of metres
    centre = main.dxf.view_center_point
    assert (round(centre.x), round(centre.y)) == (210, 148)
    assert tuple(layout.dxf.extmax)[:2] == (420.0, 297.0)


def test_sheet_plots_at_1_to_1(doc):
    layout = doc.layouts.get("A3")
    assert layout.dxf.scale_numerator == 1 and layout.dxf.scale_denominator == 1
    assert (layout.dxf.paper_width, layout.dxf.paper_height) == (420.0, 297.0)


def test_template_opens_on_the_a3_sheet(doc):
    assert doc.header["$TILEMODE"] == 0
    assert doc.layouts.get("A3").layout_key == doc.layouts.get_active_layout_key()


def test_fit_scale_picks_the_smallest_standard_scale_that_fits():
    assert tpl.fit_scale(1000, 1000) == 20
    assert tpl.fit_scale(20000, 20000) == 100  # 20 m needs 1:85 -> next standard is 1:100
    assert tpl.fit_scale(300000, 100000) % 50 == 0 and tpl.fit_scale(300000, 100000) > 200


def test_add_sheet_fills_fields_and_leaves_missing_ones_blank():
    d = ezdxf.new("R2018")
    layout = tpl.add_sheet(d, "S1", {"PROJ_REF": "PJR-2026-001"}, (5000.0, 6000.0), 50)
    (tb,) = [i for i in layout.query("INSERT") if i.dxf.name == "STIQ-TITLEBLOCK"]
    values = {a.dxf.tag: a.dxf.text for a in tb.attribs}
    assert values["PROJ_REF"] == "PJR-2026-001" and values["CLIENT"] == ""
    vp = sorted(layout.query("VIEWPORT"), key=lambda v: v.dxf.id)[-1]
    centre = vp.dxf.view_center_point
    assert (round(centre.x), round(centre.y)) == (5000, 6000)
    assert round(vp.dxf.view_height) == 13150  # 263 mm x 50


def test_write_template_never_overwrites(tmp_path):
    a = tpl.write_template(tmp_path)
    b = tpl.write_template(tmp_path)
    assert a.name.endswith("Rev 00.dxf") and b.name.endswith("Rev 01.dxf") and a.exists()


def test_define_styles_is_idempotent_on_an_existing_document():
    d = ezdxf.new("R2018")
    tpl.define_styles(d)
    tpl.define_styles(d)  # second call must not raise
    assert "S-GRID" in d.layers
