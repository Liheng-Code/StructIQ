import ezdxf

from structiq.drawing import layers, restandardise, template, validate


def _doc_with(layer_names):
    doc = ezdxf.new("R2018")
    doc.units = 4
    msp = doc.modelspace()
    for i, name in enumerate(layer_names):
        if name not in doc.layers:
            doc.layers.add(name)
        msp.add_line((0, i * 100), (1000, i * 100), dxfattribs={"layer": name, "color": 1})
    return doc


def test_company_only_layers_are_defined_on_demand_with_standard_properties():
    doc = ezdxf.new("R2018", setup=False)
    layers.ensure_layers(doc, ["S-REBAR", "S-HIDDEN", "S-PT-TENDON", "NOT-A-LAYER"])
    assert "S-REBAR" in doc.layers and "S-HIDDEN" in doc.layers and "S-PT-TENDON" in doc.layers
    assert "NOT-A-LAYER" not in doc.layers
    assert doc.layers.get("S-HIDDEN").dxf.linetype == "STIQ-DOT"
    assert doc.layers.get("S-REBAR").dxf.lineweight == 25


def test_aliases_and_legacy_names_resolve_to_standard_layers():
    assert layers.resolve("S-SECT-CUT") == "S-ANNO-SECT"
    assert layers.resolve("S-TBLK-BORDER") == "S-TTLB-FRAME"
    assert layers.resolve("REBAR") == "S-REBAR" and layers.resolve("rc") == "S-CONC-OUTLINE"
    assert layers.resolve("S-GRID") == "S-GRID"
    assert layers.resolve("SOMETHING ELSE") is None


def test_the_blank_template_passes_validation(tmp_path):
    out = template.write_template(tmp_path)
    res = validate.validate(out)
    assert res["ok"], res["errors"]
    assert res["sheets"] == ["A3"]


def test_unknown_company_and_proposed_layers_are_reported(tmp_path):
    doc = template.build_template()
    layers.ensure_layers(doc, ["S-PT-TENDON"])
    for name in ("MYSTERY", "S-SECT-CUT"):
        doc.layers.add(name)
        doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": name})
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "S-PT-TENDON"})
    path = tmp_path / "x.dxf"
    doc.saveas(path)
    res = validate.validate(path)
    assert not res["ok"]
    assert any("'MYSTERY' is not in the layer standard" in e for e in res["errors"])
    assert any("'S-SECT-CUT' is the company name" in e and "S-ANNO-SECT" in e for e in res["errors"])
    assert any("S-PT-TENDON" in w and "PROPOSED" in w for w in res["warnings"])


def test_layer_definition_differences_are_errors(tmp_path):
    doc = template.build_template()
    layers.ensure_layers(doc, ["S-REBAR"])
    doc.layers.get("S-REBAR").dxf.lineweight = 50
    doc.modelspace().add_line((0, 0), (10, 0), dxfattribs={"layer": "S-REBAR"})
    path = tmp_path / "x.dxf"
    doc.saveas(path)
    assert any("S-REBAR: lineweight 50" in e for e in validate.validate(path)["errors"])


def test_text_must_use_a_stiq_style(tmp_path):
    doc = template.build_template()
    doc.modelspace().add_text("x", dxfattribs={"layer": "S-ANNO-TEXT", "style": "Standard", "height": 100})
    path = tmp_path / "x.dxf"
    doc.saveas(path)
    assert any("not a STIQ- Arial style" in e for e in validate.validate(path)["errors"])


def test_restandardise_maps_layers_resets_overrides_and_reports_the_unmapped(tmp_path):
    doc = _doc_with(["FRAME", "RC", "REBAR", "S-SECT-CUT", "WEIRD"])
    doc.modelspace().add_text("note", dxfattribs={"layer": "RC", "height": 2.0, "style": "Standard"})
    src = tmp_path / "old.dxf"
    doc.saveas(src)

    dst, report = restandardise.run(src, tmp_path / "out")

    assert dst.name == "old restandardised Rev 00.dxf"
    assert report["layer_moves"] == {"RC->S-CONC-OUTLINE": 2, "REBAR->S-REBAR": 1, "S-SECT-CUT->S-ANNO-SECT": 1}
    assert report["unmapped_layers_left_unchanged"] == {"WEIRD": 1}
    assert report["entities_dropped"] == 1  # FRAME
    assert report["text_moved_to_STIQ_TEXT"] == 1
    assert report["colour_lineweight_overrides_reset"] >= 4
    out = ezdxf.readfile(dst)
    assert {e.dxf.layer for e in out.modelspace()} == {"S-CONC-OUTLINE", "S-REBAR", "S-ANNO-SECT", "WEIRD"}
    assert all(not e.dxf.hasattr("color") for e in out.modelspace())
    assert (dst.parent / f"{dst.stem}-report.json").exists()
    assert ezdxf.readfile(src).modelspace().query('LINE[layer=="RC"]')  # the source is untouched


def test_restandardise_never_overwrites_a_revision(tmp_path):
    src = tmp_path / "a.dxf"
    _doc_with(["RC"]).saveas(src)
    first, _ = restandardise.run(src, tmp_path / "o")
    second, _ = restandardise.run(src, tmp_path / "o")
    assert first.name.endswith("Rev 00.dxf") and second.name.endswith("Rev 01.dxf") and first.exists()


def test_a_restandardised_sheet_has_no_layer_errors_when_everything_was_mapped(tmp_path):
    src = tmp_path / "a.dxf"
    _doc_with(["RC", "REBAR", "HIDDEN"]).saveas(src)
    dst, _ = restandardise.run(src, tmp_path / "o")
    res = validate.validate(dst)
    assert not [e for e in res["errors"] if "layer" in e.lower()], res["errors"]
