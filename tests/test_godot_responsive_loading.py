"""Source-level checks for key Godot usability regressions.

These complement (but do not replace) interactive testing with Godot on Linux.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'godot' / 'main.gd').read_text(encoding='utf-8')


def test_fullscreen_layout_has_adaptive_margins_and_stackable_cards():
    assert 'resized.connect(_update_responsive_layout)' in SCRIPT
    assert 'func _update_responsive_layout() -> void:' in SCRIPT
    assert 'home_cards.vertical = width < 1380' in SCRIPT
    # Settings now uses a fixed vertical folder field with wrap-safe actions.
    # The previous window-wide threshold forced a horizontal row inside a
    # narrow drawer, hiding Browse/Save on the user's 1536x960 screen.
    assert 'var folder_row := VBoxContainer.new()' in SCRIPT
    assert 'var folder_actions := HFlowContainer.new()' in SCRIPT
    assert 'overlay_drawer.offset_left = - drawer_width' in SCRIPT
    assert 'margin_left' in SCRIPT and 'margin_right' in SCRIPT
    assert 'folder_edit.custom_minimum_size = Vector2(0, 48)' in SCRIPT
    assert 'home_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED' in SCRIPT
    assert 'settings_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED' in SCRIPT


def test_long_song_names_cannot_force_controls_wider():
    # File entries now use a two-line row; the title and detail each have
    # independent ellipsis clipping instead of one unreadable joined string.
    library_row = (ROOT / 'godot' / 'library_row.gd').read_text(encoding='utf-8')
    assert 'title_label.clip_text = true' in library_row
    assert 'detail_label.clip_text = true' in library_row
    assert 'title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in library_row
    assert 'title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in SCRIPT
    assert 'home_recent_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in SCRIPT
    assert 'library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in SCRIPT


def test_score_error_does_not_disappear_during_state_polling():
    assert 'func _score_failed(message: String) -> void:' in SCRIPT
    assert 'func _refresh_score_status() -> void:' in SCRIPT
    assert 'score_status_label.text = "Unable to display sheet music:' in SCRIPT
    assert 'score_retry_button.visible = true' in SCRIPT
    assert 'func _retry_score() -> void:' in SCRIPT
    assert 'score_error = ""\n        _refresh_score_status()' in SCRIPT
    assert '"Placeholder"' not in SCRIPT
    assert 'layout_request.timeout = 90.0' in SCRIPT
    assert 'score_request.timeout = 45.0' in SCRIPT
    assert 'action_request.timeout = 90.0' in SCRIPT


def test_failed_library_import_keeps_error_in_library():
    assert 'library_error = "Cannot open score: " + message' in SCRIPT
    assert 'if not library_error.is_empty():' in SCRIPT
    assert 'library_message.text = library_error' in SCRIPT
