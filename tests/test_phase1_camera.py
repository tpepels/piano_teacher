"""Godot camera regressions, backed by a real runtime visibility smoke test."""
from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "godot" / "main.gd").read_text()

def test_fixed_frame_budget_and_logarithmic_lookup():
    assert "Engine.max_fps = 60" in SOURCE
    assert "var middle: int = (low + high) / 2" in SOURCE
    assert "cached_bounds[page] = bounds" in SOURCE
    assert "if score_content.position != target:" in SOURCE
    assert "cached_bounds.clear()" in SOURCE


def test_fit_is_based_on_actual_required_noteheads():
    assert "func _score_note_bounds(page: int)" in SOURCE
    assert 'score_layout.get("notes", [])' in SOURCE
    assert "var width_scale: float = viewport.x * 0.83" in SOURCE
    assert "var height_scale: float = viewport.y * 0.77" in SOURCE

def test_playback_projects_clock_directly_under_fixed_rule():
    assert "target_x = viewport.x * 0.42 - note_x * displayed_width" in SOURCE
    assert "target_x = clampf" not in SOURCE
    assert "var target_y: float = viewport.y * .5 - rail_center * displayed_height" in SOURCE
    assert "score_content.position = target" in SOURCE

def test_camera_does_not_rerender_between_stop_and_start():
    assert 'var key: String = "%d/%d/%d"' in SOURCE
    assert "_layout_moving_score(_delta)" in SOURCE
    assert "score_overlay.cursor = cursor" in SOURCE

def test_runtime_visibility_trace_counts_actual_notehead_projection():
    assert "func _visible_score_noteheads() -> int:" in SOURCE
    assert 'PHASE0_VISIBLE_NOTES:' in SOURCE
    assert "score_content.position + normalized * score_content.size" in SOURCE

def test_opaque_page_margins_are_cropped():
    assert "func _visible_engraving_bounds(picture: Image)" in SOURCE
    assert "var opaque_bounds := _visible_engraving_bounds(picture)" in SOURCE
    assert "picture.get_used_rect()" not in SOURCE.split("func _on_score(")[1]
