"""Actual Verovio-engraved note sprites must be reusable without Godot geometry."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image


def test_engrave_complete_notes_once_then_reuse_across_loads(tmp_path, monkeypatch):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher import verovio_note_templates as templates

    first = PreprocessingCache(tmp_path)
    atlas = templates.note_templates(first)
    assert set(atlas) == set(templates.keys())
    assert len(atlas) == 13
    assert atlas["eighth_up"]["png_base64"] != atlas["eighth_down"]["png_base64"]
    assert atlas["quarter_up"]["png_base64"] != atlas["quarter_down"]["png_base64"]
    assert atlas["whole"]["png_base64"] != atlas["quarter_up"]["png_base64"]
    for key, item in atlas.items():
        assert item["source"] == "verovio-engraved-note", key
        if key != "whole":
            stem = item["stem_only"]
            assert stem["source"] == "verovio-engraved-note-stem"
            assert stem["units_per_space"] == 250
            assert stem["bounds"][2] > 0 and stem["bounds"][3] > 0
            with Image.open(BytesIO(base64.b64decode(stem["png_base64"]))) as png:
                assert png.getchannel("A").getbbox() is not None
        assert item["units_per_space"] == 250, key
        assert len(item["bounds"]) == 4, key
        png = base64.b64decode(item["png_base64"], validate=True)
        assert png.startswith(b"\x89PNG\r\n\x1a\n")
        with Image.open(BytesIO(png)) as image:
            assert image.size[0] > 2 and image.size[1] > 2
            assert image.getchannel("A").getbbox() is not None
    # A new engine or process gets the persisted versioned assets; no new
    # Verovio engraving or PNG conversion may occur on repeat launch.
    monkeypatch.setattr(templates, "_generate",
                        lambda _: (_ for _ in ()).throw(
                            AssertionError("cache miss triggered re-engraving")))
    second = PreprocessingCache(tmp_path)
    assert templates.note_templates(second) == atlas


def test_note_stems_are_only_verovio_svg_graphics():
    from piano_teacher.verovio_note_templates import _only_stem_svg
    from xml.etree import ElementTree as ET
    svg='''<svg xmlns="http://www.w3.org/2000/svg">
    <g class="note"><g class="notehead"><circle cx="0" cy="0" r="5"/></g>
    <g class="stem"><path d="M0 0 L0 40"/></g></g>
    <g class="staff"><path d="M0 10 L200 10"/></g></svg>'''
    filtered = _only_stem_svg(svg)
    root = ET.fromstring(filtered)
    classes = {c for el in root.iter() for c in el.get("class","").split()}
    assert "stem" in classes
    assert "notehead" not in classes
    assert "staff" not in classes


def test_note_template_musicxml_has_verovio_stem_and_real_note_duration():
    from piano_teacher.verovio_note_templates import _one_note_xml, KINDS
    from xml.etree import ElementTree as ET
    for kind in KINDS:
        for direction in ("up", "down"):
            root = ET.fromstring(_one_note_xml(kind, direction))
            note = root.find(".//note")
            assert note is not None and note.get("id") == "template"
            assert note.findtext("type") == kind
            assert note.findtext("stem") == (
                direction if kind != "whole" else None)
