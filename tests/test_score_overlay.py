"""The preparation overlay loads and draws the real engraving-font glyphs."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_godot_preparation_overlay_loads_visible_symbols_and_draws_fractional_count_in(tmp_path):
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot 4 is unavailable")
    from piano_teacher.notation.assets.glyphs import preparation_symbols

    (tmp_path / "symbols.json").write_text(json.dumps(preparation_symbols()))
    script = tmp_path / "check_overlay.gd"
    script.write_text('''extends SceneTree
const Overlay := preload("res://score_overlay.gd")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var overlay := Overlay.new()
    root.add_child(overlay)
    var symbols: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    overlay.load_symbols(symbols)
    assert(overlay._symbols.size() == 4, "all preparation symbols must load")
    for name in overlay._symbols:
        var item: Dictionary = overlay._symbols[name]
        var texture: Texture2D = item.texture
        assert(texture.get_image().get_used_rect().get_area() > 0,
               "engraving symbol must contain visible pixels")
        var bounds: Rect2 = item.bounds
        assert(absf(float(texture.get_width()) / texture.get_height()
                    - bounds.size.x / bounds.size.y) < .02,
               "glyph raster must preserve the font proportions")
    overlay.size = Vector2(1200, 400)
    overlay.image_size = overlay.size
    overlay.lead_first = {"x": .7, "top": .1, "bottom": .84}
    overlay.lead_width_px = 420.0
    overlay.lead_beats = 3.5
    overlay.lead_meter = [4, 4]
    overlay.lead_staff_lines = [.2, .23, .26, .29, .32, .62, .65, .68, .71, .74]
    overlay.cursor = {"page": 0, "x": .5, "top": .1, "bottom": .84}
    overlay.active_page = 0
    overlay.showing = true
    overlay.marks = [{"page": 0, "x": .8, "y": .3, "status": "correct"},
                     {"page": 0, "x": .9, "y": .3, "status": "wrong"}]
    overlay.queue_redraw()
    await process_frame
    await process_frame
    print("PREPARATION_OVERLAY_OK")
    quit()
''')
    result = subprocess.run(
        [godot, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(script), "--", str(tmp_path / "symbols.json")],
        capture_output=True, text=True, timeout=15)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "PREPARATION_OVERLAY_OK" in output, output
