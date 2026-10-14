"""Source-level checks pending runtime Godot visual acceptance."""
from pathlib import Path
SOURCE = (Path(__file__).resolve().parents[1] / 'godot' / 'main.gd').read_text()

def test_camera_tracks_active_system():
    assert 'system_span: float = clampf(bottom - top, 0.20, 1.0)' in SOURCE
    assert 'score_crop_origin.y' in SOURCE
    assert 'target_y = clampf(' in SOURCE

def test_camera_smooths_without_detaching_cursor():
    assert 'func _layout_moving_score(delta: float = 0.0)' in SOURCE
    assert 'var blend: float = 1.0 - exp(-14.0 * delta)' in SOURCE
    assert 'score_content.position.lerp(Vector2(target_x, target_y), blend)' in SOURCE
    assert '_layout_moving_score(_delta)' in SOURCE

def test_system_wrap_snaps_correctly():
    assert 'key != follow_system_key' in SOURCE
    assert 'str(cursor.get("system", ""))' in SOURCE
    assert 'score_overlay.cursor = cursor' in SOURCE
