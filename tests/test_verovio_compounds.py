"""Native musical compounds use real Verovio geometry, not fabricated paths."""
from __future__ import annotations

import base64
from io import BytesIO
from xml.etree import ElementTree as ET

from PIL import Image


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
    from piano_teacher.verovio_chord_templates import chord_pattern
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
    source=(root/"godot/score_native_notation.gd").read_text()
    assert "func _tie_shape(" not in source
    assert "glyphs.paint_tie(self" in source
    assert "glyphs.paint_chord(self" in source


def test_native_renderer_never_draws_imitated_beams_stems_or_tuplets():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1] /
            "godot/score_native_notation.gd").read_text()
    assert "func _beam_segment(" not in source
    assert "func _paint_flag(" not in source
    assert "draw_line(Vector2(stem_x,anchor_y)" not in source
    tuplet=source.split("func _paint_tuplet_brackets(")[1].split(
        "func _paint_rest(")[0]
    assert "draw_line(" not in tuplet
    assert "draw_string(" not in tuplet
    assert "glyphs.paint_tuplet(" in tuplet
    assert "glyphs.paint_note_stem(" in source
