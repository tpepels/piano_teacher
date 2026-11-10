"""Preparation uses the installed engraving font's real musical symbols."""
import re
from io import BytesIO
import xml.etree.ElementTree as ET

from PIL import Image


def test_preparation_symbols_have_real_visible_outlines_and_staff_units():
    from piano_teacher.notation.assets.glyphs import preparation_symbols

    symbols = preparation_symbols()
    assert set(symbols) == {"treble", "bass", "quarter_rest", "eighth_rest"}
    for symbol in symbols.values():
        root = ET.fromstring(symbol["svg"])
        assert any(e.tag.endswith("path") and e.get("d") for e in root.iter())
        assert symbol["units_per_space"] == 250
        assert symbol["bounds"][2] > 0 and symbol["bounds"][3] > 0


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
    # Owner decision: circles around noteheads were an old implementation.
    # Note status is delivered by softly recolouring the notehead itself
    # (note_status_layer.gd, 6858f62b), never by a ring, halo or badge.
    assert "draw_circle(" not in gd and "draw_arc(" not in gd
    context = (native / "context_painter.gd").read_text()
    assert "draw_circle(" not in context and "draw_arc(" not in context
    # The only circles in the native view are the fixed playhead dot and beat
    # pulse, anchored at playhead_x inside the transport-overlay block.
    start = view.index("if transport_overlay_enabled and not runway_overlay:")
    end = view.index("# The count-in runs on the same clock", start)
    overlay = view[start:end]
    assert view.count("draw_circle(") + view.count("draw_arc(") == overlay.count("draw_circle(") + overlay.count("draw_arc(")
    for call in re.findall(r"draw_(?:circle|arc)\(([^,]+),", overlay):
        assert "playhead_x" in call or call.strip() == "center", call
    assert "var center := Vector2(playhead_x," in overlay
    # No other native-notation file, and no non-score widget outside the
    # reviewed list, draws a circle or arc that could sit at a notehead.
    reviewed = {"hint_keyboard.gd", "calibration_beat_pulse.gd", "game_input_indicator.gd",
                "game_impact_callout.gd", "action_button.gd", "practice_objective_glyph.gd",
                "game_countin.gd", "game_phase_cue.gd", "game_stage.gd", "game_streak.gd",
                "game_transport_button.gd", "practice_metrics.gd", "score_step_timeline.gd"}
    found = set()
    for path in (root / "godot").rglob("*.gd"):
        relative = path.relative_to(root / "godot")
        if relative.parts[0] == "addons" or "diagnostics" in relative.parts:
            continue
        text = path.read_text()
        if "draw_circle(" in text or "draw_arc(" in text:
            found.add(path.name if relative.parts[0:2] != ("notation", "native") else str(relative))
    assert found == reviewed | {"notation/native/view.gd"}, found
    assert "glyphs.paint(canvas, \"head_black\"" in gd
    assert "glyphs.paint(canvas, \"rest_\" + note_type" in gd
    assert "load_svg_from_buffer(" in atlas
    assert "draw_texture_rect(" in atlas
