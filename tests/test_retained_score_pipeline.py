"""Retained notation is compiled once and translated independently of transport."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_frame_path_never_reassembles_source_or_preparation_ink():
    view = (ROOT/"godot/notation/native/view.gd").read_text()
    draw = view.split("func _draw() -> void:", 1)[1].split(
        "\nfunc ",1)[0]
    assert "_paint_source_pass(" not in draw
    assert "symbols.paint_" not in draw
    assert "context_painter.paint_" not in draw
    assert "_project_stream(playhead_x)" in draw
    assert "_place_retained_score" not in view
    assert "present_ambient" not in view
    assert "displayed_scroll_beat" not in view
    assert "retained_annotations.queue_redraw()" in draw
    assert "RetainedNoteProjection.append_visible(" in view
    assert "retained_ready()" in view
    assert 'call_deferred("emit_signal","retained_ink_compiled")' in view
    assert "SourcePassPainter.paint(self,canvas)" in view
    source = (ROOT/"godot/notation/native/source_pass_painter.gd").read_text()
    assert 'variant == "recovery"' not in source
    assert "_practice_context_before" not in source
    assert "symbols.paint_beams(" in source
    assert "symbols.paint_beams(" not in draw
    assert "_paint_source_pass" not in view
    assert "RETAINED_POOL_SIZE" not in view
    assert "_required_repeat_copies()" not in view
    session = (ROOT/"godot/score_asset_session.gd").read_text()
    assert 'renderer.connect("retained_ink_compiled",_finish_native_score)' in session
    assert 'not _renderer.retained_ready()' in session


@pytest.mark.skipif(shutil.which("godot") is None and
                    shutil.which("godot4") is None,
                    reason="Godot unavailable")
def test_moving_retained_score_does_not_repaint_it():
    binary = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT/"godot"),
         "--script", str(ROOT/"tests/godot/retained_segments.gd")],
        capture_output=True, text=True, timeout=25)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "RETAINED_SEGMENT_FAILURES:0" in output, output


@pytest.mark.skipif(shutil.which("godot") is None and
                    shutil.which("godot4") is None,
                    reason="Godot unavailable")
def test_retained_note_spatial_index_and_identity():
    binary = shutil.which("godot") or shutil.which("godot4")
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT/"godot"),
         "--script", str(ROOT/"tests/godot/retained_note_projection.gd")],
        capture_output=True, text=True, timeout=20)
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "RETAINED_NOTE_PROJECTION_FAILURES:0" in output, output


def test_fingering_overlay_has_bounded_source_window():
    source = (ROOT/"godot/notation/native/fingering_annotations.gd").read_text()
    assert "fingering_layout.sort_custom(" in source
    assert "widest_fingering" in source
    assert "for index in range(low,fingering_layout.size()):" in source
    assert "for item in fingering_layout:" not in source.split(
        "func paint(",1)[1].split("\nfunc ",1)[0]


def test_single_score_renderer_has_no_legacy_execution_selector():
    source = (ROOT/"godot/notation/native/view.gd").read_text()
    stage = (ROOT/"godot/practice_score_stage.gd").read_text()
    runway = (ROOT/"godot/score_runway.gd").read_text()
    assert "stream_enabled" not in source
    assert "stream_enabled" not in stage
    assert "stream_enabled" not in runway
    assert "present_ambient" not in source
    assert "_place_retained_score" not in source
    assert "displayed_scroll_beat" not in source
    assert 'variant == "recovery"' not in (ROOT/"godot/notation/native/source_pass_painter.gd").read_text()


def test_legacy_ambience_source_cameras_and_recovery_variants_are_absent():
    view = (ROOT/"godot/notation/native/view.gd").read_text()
    coordinator = (ROOT/"godot/practice_frame_coordinator.gd").read_text()
    runway = (ROOT/"godot/score_runway.gd").read_text()
    source = (ROOT/"godot/notation/native/source_pass_painter.gd").read_text()
    for path in ("idle_preview.gd", "measure_light.gd", "source_visibility.gd"):
        assert not (ROOT/"godot/notation/native"/path).exists()
    assert "present_ambient" not in coordinator
    assert "_place_retained_score" not in view
    assert "stream_enabled" not in view
    assert "present_clock(" not in runway
    assert "SourcePassPainter.paint(self,canvas)" in view
    assert '"autopending"' in view
    assert "ScoreStreamAdmission" not in view
    assert 'variant == "recovery"' not in source
    assert 'frame.score_loop_enabled' not in source
    assert "clip.visible = false" in view
    assert "clip.visible = segment.compiled" in view


def test_real_score_framebuffer_uses_production_world_axis():
    harness = (ROOT/"tests/godot/native_verovio_overlay.gd").read_text()
    oracle = (ROOT/"piano_teacher/notation/pixel_proof.py").read_text()
    phase3 = (ROOT/"piano_teacher/notation/phase3_pixels.py").read_text()
    native = (ROOT/"godot/notation/shared/view_base.gd").read_text()
    assert "renderer._stream_add_take(0.0,0.0,0.0," in harness
    assert "renderer.present_flow(at,snapshot,at)" in harness
    assert "PLAYHEAD_FRACTION = 0.33" in oracle
    assert "image.width*PLAYHEAD_FRACTION" in phase3
    rest = (ROOT/"piano_teacher/notation/rest_intervention.py").read_text()
    assert "shape[1]*PLAYHEAD_FRACTION" in rest
    assert "PLAYHEAD_FRACTION := .33" in native


def test_production_journey_does_not_depend_on_removed_camera_switch():
    scenario = (ROOT/"godot/production_session_journey.gd").read_text()
    assert "stream_enabled" not in scenario
    assert "retained_ready()" in scenario
    assert "stream_world_beat" in scenario


def test_production_ready_smoke_accepts_hidden_future_reservation_retiming():
    script = (ROOT/"godot/production_ui_smoke.gd").read_text()
    assert "pending_count != 1" in script
    assert "ready_world_origin = float(prepared[\"world_origin\"])" in script
    assert "moved hidden ink backwards" in script
    assert "Ready world-axis stopped or repositioned source" not in script
