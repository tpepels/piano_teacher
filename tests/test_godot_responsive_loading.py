"""Source-level checks for key Godot usability regressions.

These complement (but do not replace) interactive testing with Godot on Linux.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / 'godot' / 'main.gd').read_text(encoding='utf-8')
SETTINGS = (ROOT / 'godot' / 'settings_screen.gd').read_text(encoding='utf-8')
LIBRARY = (ROOT / 'godot' / 'library_screen.gd').read_text(encoding='utf-8')


def test_fullscreen_layout_has_adaptive_margins_and_stackable_cards():
    assert 'resized.connect(_update_responsive_layout)' in SCRIPT
    assert 'func _update_responsive_layout() -> void:' in SCRIPT
    assert 'home_cards.vertical = width < 1380' in SCRIPT
    # Settings now uses a fixed vertical folder field with wrap-safe actions.
    # The previous window-wide threshold forced a horizontal row inside a
    # narrow drawer, hiding Browse/Save on the user's 1536x960 screen.
    assert 'folder_controls = VBoxContainer.new()' in SETTINGS
    assert 'var folder_actions := HFlowContainer.new()' in SETTINGS
    assert 'overlay_drawer.offset_left = inset' in SCRIPT
    assert 'margin_left' in SCRIPT and 'margin_right' in SCRIPT
    assert 'folder_edit.custom_minimum_size = Vector2(0, 40)' in SETTINGS
    assert 'scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED' in SCRIPT
    assert 'func _configure_ui_scaling() -> void:' in SCRIPT
    assert 'window.content_scale_factor = factor' in SCRIPT


def test_long_song_names_cannot_force_controls_wider():
    # File entries now use a two-line row; the title and detail each have
    # independent ellipsis clipping instead of one unreadable joined string.
    library_row = (ROOT / 'godot' / 'library_row.gd').read_text(encoding='utf-8')
    assert 'title_label.clip_text = true' in library_row
    assert 'detail_label.clip_text = true' in library_row
    assert 'title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in library_row
    assert 'title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in SCRIPT
    assert 'home_recent_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in SCRIPT
    assert 'library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS' in LIBRARY


def test_score_error_does_not_disappear_during_state_polling(tmp_path):
    from test_native_production import test_native_production_readiness_and_failure_gate

    test_native_production_readiness_and_failure_gate(tmp_path, "default")


def test_failed_library_import_keeps_error_in_library():
    assert 'library_view.present_open_status("Cannot open score: " + message, true)' in SCRIPT
    assert 'if not library_error.is_empty():' in LIBRARY
    assert 'library_message.text = library_error' in LIBRARY
