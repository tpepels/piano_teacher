"""Preparation uses the installed engraving font's real musical symbols."""
from io import BytesIO
import xml.etree.ElementTree as ET

from PIL import Image


def test_preparation_symbols_have_real_visible_outlines_and_staff_units():
    from piano_teacher.notation.assets.glyphs import preparation_symbols
    from piano_teacher.raster import rasterize_score

    symbols = preparation_symbols()
    assert set(symbols) == {"treble", "bass", "quarter_rest", "eighth_rest"}
    for symbol in symbols.values():
        root = ET.fromstring(symbol["svg"])
        assert any(e.tag.endswith("path") and e.get("d") for e in root.iter())
        assert symbol["units_per_space"] == 250
        assert symbol["bounds"][2] > 0 and symbol["bounds"][3] > 0
        image = Image.open(BytesIO(rasterize_score(symbol["svg"], width=600)))
        assert image.convert("RGBA").getchannel("A").getbbox() is not None


def test_native_godot_atlas_is_authentic_and_covers_notation_symbols():
    import cairosvg
    from piano_teacher.notation.assets.glyphs import _NATIVE_CODES, native_glyphs

    atlas = native_glyphs()
    assert set(atlas) == set(_NATIVE_CODES)
    assert len(atlas) >= 35
    assert atlas["repeat_dot"]["code"] == "E044"
    font = {entry["font"] for entry in atlas.values()}
    assert len(font) == 1
    for name, item in atlas.items():
        assert item["source"] == "verovio", name
        assert item["code"] == _NATIVE_CODES[name], name
        assert item["units_per_space"] == 250, name
        assert len(item["bounds"]) == 4, name
        assert item["bounds"][2] > 0 and item["bounds"][3] > 0, name
        root = ET.fromstring(item["svg"])
        assert any(e.tag.endswith("path") and e.get("d") for e in root.iter()), name
    # These SVGs contain exactly one font glyph each, never a page/staff.
    assert "class=\"system\"" not in atlas["clef_g"]["svg"]
    for name in ("head_black", "head_half", "head_whole",
                 "clef_g", "clef_f", "rest_quarter", "acc_sharp"):
        png = Image.open(BytesIO(cairosvg.svg2png(
            bytestring=atlas[name]["svg"].encode("utf-8"), output_width=600)))
        assert png.convert("RGBA").getchannel("A").getbbox() is not None, name


def test_native_renderer_has_no_original_hand_drawn_musical_glyphs():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    native = root / "godot/notation/native"
    view = (native / "view.gd").read_text()
    gd = (native / "symbol_painter.gd").read_text()
    renderers = view+gd+(native / "context_painter.gd").read_text()
    atlas = (root / "godot/notation/native/glyphs.gd").read_text()
    assert "const VerovioGlyphs" in view
    assert "func _paint_ellipse(" not in renderers
    assert "func paint_ellipse(" not in renderers
    assert "draw_circle(" not in renderers
    assert "draw_arc(" not in renderers
    assert "glyphs.paint(canvas, \"head_black\"" in gd
    assert "glyphs.paint(canvas, \"rest_\" + note_type" in gd
    assert "load_svg_from_buffer(" in atlas
    assert "draw_texture_rect(" in atlas
