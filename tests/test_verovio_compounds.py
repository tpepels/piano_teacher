"""Native musical compounds use real Verovio geometry, not fabricated paths."""
from __future__ import annotations

import base64
from io import BytesIO
from xml.etree import ElementTree as ET

from PIL import Image
import pytest


def _whole_chord_model():
    return {"measures": [{"number": 1, "clefs": {"right": {"sign": "G", "line": 2}}}],
            "notation_events": [
                {"id": "a", "kind": "note", "staff": "right", "voice": "1",
                 "measure": 1, "beat": 0, "chord": False, "note_type": "whole",
                 "spelling": {"step": "B", "octave": 4}},
                {"id": "b", "kind": "note", "staff": "right", "voice": "1",
                 "measure": 1, "beat": 0, "chord": True, "note_type": "whole",
                 "spelling": {"step": "D", "octave": 5}}]}


def test_whole_chord_ink_is_centred_on_source_head_positions():
    from piano_teacher.notation.assets.chords import chord_templates

    item = chord_templates(_whole_chord_model())["whole|down|0,2"]
    bounds = item["heads_only"]["bounds"]
    assert abs(bounds[0] + bounds[2] / 2) < 15, bounds


def test_real_chord_stem_excludes_its_nested_flag():
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    from piano_teacher.notation.assets.chords import (
        _xml, _extract_chord, _only_original_chord_stems,
    )

    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.loadData(_xml("eighth|up|0,2"))
    chord = _extract_chord(toolkit.renderToSVG(1), {"c0", "c1"})
    stem = ET.fromstring(_only_original_chord_stems(chord))
    classes = {c for element in stem.iter() for c in element.get("class", "").split()}
    assert "stem" in classes
    assert "flag" not in classes, "Chord flags must not reappear inside a beamed attack"


def test_source_beam_direction_gets_its_own_reusable_chord_template():
    from piano_teacher.notation.assets.chords import chord_templates

    model = _whole_chord_model()
    model["notation_events"] = [{**event, "note_type": "eighth"}
                                for event in model["notation_events"]]
    atlas = chord_templates(model, stem_directions={"a": True})
    assert set(atlas) == {"eighth|up|0,2", "eighth|down|0,2"}
    up = atlas["eighth|up|0,2"]["stem_only"]["bounds"]
    down = atlas["eighth|down|0,2"]["stem_only"]["bounds"]
    assert up[0] > 0 > down[0], "Original stem attachments must switch sides with the beam"


@pytest.mark.parametrize("damage", ["missing_stem", "corrupt_png"])
def test_incomplete_cached_chord_is_rebuilt_instead_of_causing_fallback(tmp_path, damage):
    import verovio
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher.notation.assets import chords
    from piano_teacher.notation.assets.glyphs import native_glyphs

    cache = PreprocessingCache(tmp_path)
    model = _whole_chord_model()
    model["notation_events"] = [{**e, "note_type": "quarter"}
                                for e in model["notation_events"]]
    pattern = "quarter|down|0,2"
    original = chords.chord_templates(model, cache)[pattern]
    incomplete = {k: v for k, v in original.items() if k != "stem_only"}
    if damage == "corrupt_png":
        incomplete = {**original, "png_base64": original["png_base64"][:-16]}
    key = cache.key("verovio-chords", chords.VERSION,
                    native_glyphs()["head_black"]["font"],
                    getattr(verovio, "__version__", "unknown"), pattern)
    cache.write_json("verovio-chord", key, incomplete)
    repaired = chords.chord_templates(model, cache)[pattern]
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
    assert set(templates)=={"up","down"}
    for item in templates.values():
        _valid_sprite(item,"verovio-engraved-tie")
        assert item["span"]>0
    assert templates["up"]["png_base64"] != templates["down"]["png_base64"]
    monkeypatch.setattr(tie,"_generate",lambda _:(_ for _ in ()).throw(
        AssertionError("Second use must never call Verovio again")))
    assert tie.tie_templates(PreprocessingCache(tmp_path))==templates


def test_chord_intervals_reuse_transposed_shapes():
    from piano_teacher.notation.assets.chords import chord_pattern
    measure={"clefs":{"right":{"sign":"G","line":2}}}
    base={"staff":"right","note_type":"quarter",
          "spelling":{"step":"C","octave":5}}
    third={"staff":"right","note_type":"quarter",
           "spelling":{"step":"E","octave":5}}
    a=chord_pattern(base,[base,third],measure)
    assert a=="quarter|down|0,2"
    moved=[{**base,"spelling":{"step":"D","octave":5}},
           {**third,"spelling":{"step":"F","octave":5}}]
    assert chord_pattern(moved[0],moved,measure)==a


def test_chord_sprite_is_actual_verovio_compound_and_reusable(tmp_path,monkeypatch):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher.notation.assets import chords
    model={"measures":[{"number":1,"clefs":{"right":{"sign":"G","line":2}}}],
        "notation_events":[
            {"id":"a","kind":"note","staff":"right","voice":"1",
             "measure":1,"beat":0.0,"chord":False,"note_type":"quarter",
             "spelling":{"step":"C","octave":5}},
            {"id":"b","kind":"note","staff":"right","voice":"1",
             "measure":1,"beat":0.0,"chord":True,"note_type":"quarter",
             "spelling":{"step":"E","octave":5}}]}
    cache=PreprocessingCache(tmp_path)
    atlas=chords.chord_templates(model,cache)
    assert list(atlas)==["quarter|down|0,2"]
    sprite=atlas["quarter|down|0,2"]
    _valid_sprite(sprite,"verovio-engraved-chord")
    assert sprite["heads_only"]["source"]=="verovio-engraved-chord-heads"
    assert len(sprite["heads_only"]["bounds"])==4
    import base64
    from io import BytesIO
    with Image.open(BytesIO(base64.b64decode(
            sprite["heads_only"]["png_base64"]))) as head_bitmap:
        assert head_bitmap.getchannel("A").getbbox() is not None
    assert sprite["heads_only"]["bounds"][3] < sprite["bounds"][3]
    assert sprite["stem_only"]["source"]=="verovio-engraved-chord-stem"
    assert sprite["stem_only"]["bounds"][2]>0
    assert sprite["stem_only"]["bounds"][3]>0
    assert len(sprite["head_positions"])==2
    assert sprite["head_positions"][0][1]>sprite["head_positions"][1][1]
    monkeypatch.setattr(chords,"_render",lambda *_:(_ for _ in ()).throw(
        AssertionError("Cached chord re-rendered")))
    assert chords.chord_templates(model,PreprocessingCache(tmp_path))==atlas


def test_native_compound_code_has_no_drawn_tie_path():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    source=(root/"godot/notation/native/view.gd").read_text()
    assert "func _tie_shape(" not in source
    # Real source-contour framebuffer checks live in test_native_tie_attachments;
    # endpoint adaptation belongs to the production view's contour painter.
    assert "glyphs.paint_chord(self" in source


def test_native_renderer_never_draws_imitated_beams_stems_or_tuplets():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1] /
            "godot/notation/native/view.gd").read_text()
    assert "func _beam_segment(" not in source
    assert "func _paint_flag(" not in source
    assert "draw_line(Vector2(stem_x,anchor_y)" not in source
    tuplet=source.split("func _paint_tuplet_brackets(")[1].split(
        "func _paint_rest(")[0]
    assert "draw_line(" not in tuplet
    assert "draw_string(" not in tuplet
    assert "glyphs.paint_tuplet(" in tuplet
    assert "glyphs.paint_note_stem(" in source
