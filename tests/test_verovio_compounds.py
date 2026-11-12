"""Native musical compounds use real Verovio geometry, not fabricated paths."""
from __future__ import annotations

import base64
from io import BytesIO
from xml.etree import ElementTree as ET

from PIL import Image
import pytest


from verovio_test_score import (chord_xml, chords_by_names, prepare_musicxml,
                                rest_xml, score_xml)


def _atlas_for(tmp_path, right):
    prepared = prepare_musicxml(score_xml(right), tmp_path)
    atlas = prepared["layout"]["native_chord_templates"]
    chords = chords_by_names(prepared["model"])
    key_of = {name: next(key for key, item in atlas.items()
                         if leader["id"] in item.get("leaders", {}))
              for name, leader in chords.items()}
    return prepared, atlas, key_of


def test_whole_chord_ink_is_centred_on_source_head_positions(tmp_path):
    _, atlas, key_of = _atlas_for(tmp_path, [chord_xml("B4 D5", "whole", 16)])
    bounds = atlas[key_of[(1, "B4 D5")]]["heads_only"]["bounds"]
    assert abs(bounds[0] + bounds[2] / 2) < 15, bounds


def test_real_chord_stem_excludes_its_nested_flag(tmp_path):
    # A bare Leipzig stem is far narrower than half a staff space; a flag
    # nested inside Verovio's stem group would widen the crop to a space.
    _, atlas, key_of = _atlas_for(tmp_path, [
        chord_xml("B4 D5", "eighth", 2) + rest_xml(14, "half", 2)])
    stem = atlas[key_of[(1, "B4 D5")]]["stem_only"]["bounds"]
    assert 0 < stem[2] < 80, stem


def test_stem_direction_gets_its_own_chord_template(tmp_path):
    # The same shape engraved with the stem up and with the stem down.
    _, atlas, key_of = _atlas_for(tmp_path, [
        chord_xml("B4 D5", stem="up") + chord_xml("B4 D5", stem="down")
        + rest_xml(8, "half")])
    ups = [k for k in atlas if k.split("|")[1] == "up"]
    downs = [k for k in atlas if k.split("|")[1] == "down"]
    assert len(ups) == len(downs) == 1, list(atlas)
    up = atlas[ups[0]]["stem_only"]["bounds"]
    down = atlas[downs[0]]["stem_only"]["bounds"]
    assert up[0] > 0 > down[0], "Original stem attachments must switch sides with the stem"


@pytest.mark.parametrize("damage", ["missing_stem", "corrupt_png"])
def test_incomplete_cached_chord_is_rebuilt_instead_of_causing_fallback(tmp_path, damage):
    import verovio
    from piano_teacher.notation.assets import chords
    from piano_teacher.notation.assets.glyphs import native_glyphs

    prepared, atlas, key_of = _atlas_for(tmp_path, [chord_xml("C5 E5") + rest_xml(12, "half", 1)])
    pattern = key_of[(1, "C5 E5")]
    original = {k: v for k, v in atlas[pattern].items() if k != "leaders"}
    incomplete = {k: v for k, v in original.items() if k != "stem_only"}
    if damage == "corrupt_png":
        incomplete = {**original, "png_base64": original["png_base64"][:-16]}
    cache = prepared["cache"]
    key = cache.key("verovio-chords", chords.VERSION,
                    native_glyphs()["head_black"]["font"],
                    getattr(verovio, "__version__", "unknown"), pattern)
    cache.write_json("verovio-chord", key, incomplete)
    repaired = chords.chord_templates(prepared["model"], cache, pages=prepared["pages"])[pattern]
    assert repaired["stem_only"]["png_base64"] == original["stem_only"]["png_base64"]
    assert repaired["png_base64"] == original["png_base64"]


def _valid_sprite(asset,source):
    assert asset["source"] == source
    assert asset["units_per_space"] == 250
    assert len(asset["bounds"]) == 4
    assert asset["bounds"][2] > 0
    assert asset["bounds"][3] > 0
    image = base64.b64decode(asset["png_base64"],validate=True)
    with Image.open(BytesIO(image)) as picture:
        assert picture.mode == "RGBA"
        assert picture.getchannel("A").getbbox() is not None


def test_tie_is_real_verovio_engraved_curve_and_disk_cache(tmp_path,monkeypatch):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher.notation.assets import ties as tie
    cache=PreprocessingCache(tmp_path)
    templates=tie.tie_templates(cache)
    expected = {"up", "down"} | {
        f"{endpoint}_{kind}_{side}"
        for kind in ("eighth", "16th", "32nd", "64th", "128th")
        for endpoint, side in (("start", "above"), ("end", "below"))
    }
    assert set(templates) == expected
    for name, item in templates.items():
        _valid_sprite(item,"verovio-engraved-tie")
        assert item["span"]>0
        assert len(item["head_centers"]) == len(item["head_widths"]) == 2
        expected_heads = (["black", "half"] if name.startswith("start_") else
                          ["half", "black"] if name.startswith("end_") else
                          ["half", "half"])
        assert item["head_families"] == expected_heads
    assert templates["up"]["png_base64"] != templates["down"]["png_base64"]
    monkeypatch.setattr(tie,"_generate",lambda _:(_ for _ in ()).throw(
        AssertionError("Second use must never call Verovio again")))
    assert tie.tie_templates(PreprocessingCache(tmp_path))==templates


def test_one_shape_at_one_position_shares_one_template(tmp_path):
    # Templates are per engraved shape: the same chord twice is one asset
    # naming both leaders; a transposed chord sits elsewhere on the staff,
    # where Verovio may arrange it differently, and gets its own.
    _, atlas, key_of = _atlas_for(tmp_path, [
        chord_xml("C5 E5") + chord_xml("C5 E5") + chord_xml("D5 F5") + rest_xml(4, "quarter")])
    assert len(atlas) == 2
    assert len(atlas[key_of[(1, "C5 E5")]]["leaders"]) == 2
    assert key_of[(1, "D5 F5")] != key_of[(1, "C5 E5")]


def test_chord_sprite_is_actual_verovio_compound_and_reusable(tmp_path,monkeypatch):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher.notation.assets import chords
    prepared, atlas, key_of = _atlas_for(tmp_path, [chord_xml("C5 E5") + rest_xml(12, "half", 1)])
    sprite=atlas[key_of[(1, "C5 E5")]]
    _valid_sprite(sprite,"verovio-engraved-chord")
    assert sprite["heads_only"]["source"]=="verovio-engraved-chord-heads"
    assert len(sprite["heads_only"]["bounds"])==4
    with Image.open(BytesIO(base64.b64decode(
            sprite["heads_only"]["png_base64"]))) as head_bitmap:
        assert head_bitmap.getchannel("A").getbbox() is not None
    assert sprite["heads_only"]["bounds"][3] < sprite["bounds"][3]
    assert sprite["stem_only"]["source"]=="verovio-engraved-chord-stem"
    assert sprite["stem_only"]["bounds"][2]>0
    assert sprite["stem_only"]["bounds"][3]>0
    assert len(sprite["head_positions"])==2
    # Relative to the lowest head (template note 0): E5 lies above it.
    assert sprite["head_positions"][0] == [0.0, 0.0]
    assert sprite["head_positions"][1][1] < 0
    monkeypatch.setattr(chords,"_render_batch",lambda *_:(_ for _ in ()).throw(
        AssertionError("Cached chord re-rendered")))
    again = chords.chord_templates(prepared["model"], PreprocessingCache(tmp_path/"cache"),
                                   pages=prepared["pages"])
    assert again == atlas


def test_native_compound_code_has_no_drawn_tie_path():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    native=root/"godot/notation/native"
    source=(native/"symbol_painter.gd").read_text()
    geometry=(native/"connector_geometry.gd").read_text()
    renderers=source+geometry+(native/"view.gd").read_text()+(native/"context_painter.gd").read_text()
    assert "func _tie_shape(" not in renderers
    assert "func tie_shape(" not in renderers
    # Real source-contour framebuffer checks live in test_native_tie_attachments;
    # endpoint adaptation belongs to ConnectorGeometry and SymbolPainter.
    assert "glyphs.paint_chord(canvas" in source


def test_native_renderer_never_draws_imitated_beams_stems_or_tuplets():
    from pathlib import Path
    native=Path(__file__).resolve().parents[1]/"godot/notation/native"
    source=(native/"symbol_painter.gd").read_text()
    renderers="\n".join((native/name).read_text() for name in (
        "view.gd","symbol_painter.gd","context_painter.gd","connector_geometry.gd"))
    assert "func _beam_segment(" not in renderers
    assert "func beam_segment(" not in renderers
    assert "func _paint_flag(" not in renderers
    assert "func paint_flag(" not in renderers
    assert "draw_line(Vector2(stem_x,anchor_y)" not in renderers
    tuplet=source.split("func paint_tuplet_brackets(")[1].split(
        "func paint_rest(")[0]
    assert "draw_line(" not in tuplet
    assert "draw_string(" not in tuplet
    assert "glyphs.paint_tuplet(" in tuplet
    assert "glyphs.paint_note_stem(" in source
