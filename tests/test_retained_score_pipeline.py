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


def test_superseded_svg_score_renderer_and_preview_pipelines_are_removed():
    obsolete = {
        "score_overlay.gd", "notehead_ink.gd", "note_reactions.gd",
        "staff_continuity.gd", "preview_motion.gd",
    }
    assert all(not (ROOT/"godot"/name).exists() for name in obsolete)
    assert not (ROOT/"tests/test_score_overlay.py").exists()
    # No production scene, compositor or helper may preload deleted
    # legacy script resources to resurrect an alternate score camera.
    for source_file in (ROOT/"godot").rglob("*.gd"):
        if "addons" in source_file.parts:
            continue
        contents = source_file.read_text()
        assert not any(("res://"+name) in contents for name in obsolete), source_file


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
    lifecycle = (ROOT/"godot/notation/native/stream_lifecycle.gd").read_text()
    queue = (ROOT/"godot/score_stream_queue.gd").read_text()
    assert "_stream_queue.enqueue(self,specs" in view
    assert "StreamQueue.new()" in view
    assert "_stream_queue.expire_front(" in view
    assert "_stream_queue.withdraw_tail(" in view
    assert "offline_stream_queue: Array:" in view
    assert "var online: Array = []" in queue
    assert "var offline: Array:" in queue
    assert "return _archive.pending" in queue
    assert "var history: Array:" in queue
    assert "_archive.materialize(matching,specs)" in queue
    assert 'not _archive.record("withdrawn"' in queue
    archive = (ROOT/"godot/score_stream_archive.gd").read_text()
    assert "func bind_score(" in archive
    assert "func compatible(" in archive
    assert "func materialize(" in archive
    assert "func original_plan(" in archive
    assert "payload.sha256_text()" in archive
    assert "FileAccess.open(" in archive
    runway = (ROOT/"godot/score_runway.gd").read_text()
    assert "offline_history" not in runway
    assert "Lifecycle._admit(owner,online,prepared" in queue
    assert "Lifecycle.validate_batch(online,specs)" in queue
    assert "online.pop_front()" in queue
    assert "online.pop_back()" in queue
    assert "func expire_front(" in queue
    assert "func withdraw_tail(" in queue
    assert "ever_visible" in queue
    assert "func _stream_extend_offscreen(" not in view
    assert "func _stream_complete_measure(" not in view
    assert "StreamAdmission.automatic_horizon(" not in view
    assert "successor_reserved" not in view
    assert "final_mastery" not in view
    owner = (ROOT/"godot/practice_command_coordinator.gd").read_text()
    assert "StreamAdmission.automatic_horizon(" in owner
    assert 'state.get("preview_only",false)' in view
    app = (ROOT/"godot/main.gd").read_text()
    backend = (ROOT/"piano_teacher/server.py").read_text()
    assert "StreamAdmission.automatic_horizon(" in owner
    assert "self._automatic_stream_deadline(" in backend
    assert "repeat_deadline(" in backend
    assert owner.count("_cancel_pending_stream_arm()") >= 3
    assert "last_published_control_started_ms" in app
    assert "state_request_started_ms <= command_coordinator.last_published_control_started_ms" in app
    assert "_pending_stream_renderer.acknowledge_stream_arm()" in owner
    assert "StreamLifecycle.activate(" in view
    assert "StreamLifecycle.reposition(" not in view
    assert "StreamLifecycle.widen_source(" not in view
    assert "StreamAdmission.position(" in view
    assert "StreamAdmission.select(" in view
    assert "func _stream_add_rest(" not in view
    assert "StreamLifecycle.create(" not in view
    assert "func _stream_claim_pending_auto(" in view
    assert "static func _admit(" in lifecycle
    assert "static func activate(" in lifecycle
    assert "static func reposition(" not in lifecycle
    assert "static func widen_source(" not in lifecycle
    assert "static func prune(" not in lifecycle
    assert "static func release_all(" not in lifecycle
    assert "static func discard_owner(" not in lifecycle
    assert "static func screen_bounds(" in lifecycle
    admission = (ROOT/"godot/score_stream_admission.gd").read_text()
    assert "static func select(" in admission
    assert "static func position(" in admission
    assert "static func pending_index(" not in admission
    assert "static func paused_unplayed_index(" not in admission
    assert "static func idle_reservation_index(" not in admission
    assert "static func future_start(" not in admission
    assert "static func occupied_end(" not in admission
    assert "stream_passes.append(" not in view
    assert 'item["world_origin"] =' not in view
    assert 'existing["world_origin"] =' not in view
    assert 'item["source_floor"] =' not in view
    assert "StreamLifecycle.prune(self,stream_passes" not in view
    assert "StreamLifecycle.release_all(self,stream_passes)" not in view
    assert "_stream_queue.reset(self)" in view
    assert "StreamLifecycle.attach_compiled(_stream_queue.online)" in view
    assert "return _stream_queue.online.duplicate(true)" in view
    assert "return _archive.pending.duplicate(true)" in queue
    assert "return _archive.history.duplicate(true)" in queue
    assert "StreamLifecycle.project(item,stream_world_beat" in view
    assert "StreamLifecycle.present_pool(retained_all_segments" in view
    assert "func _hide_retained_segments(" not in view
    assert "segment.visible =" not in view
    assert "segment.position =" not in view
    assert "segment.reparent(" not in view
    assert "clip.queue_free()" not in view
    assert "stream_passes.remove_at(" not in view
    assert "segment.reparent(clip,false)" in lifecycle
    assert "segment.reparent(owner,false)" in lifecycle
    assert "clip.visible = false" in lifecycle
    assert "clip.visible = true" in lifecycle
    assert "segment.compiled" not in lifecycle.split("func _offstage(",1)[0]


def test_real_score_framebuffer_uses_production_world_axis():
    harness = (ROOT/"tests/godot/native_verovio_overlay.gd").read_text()
    oracle = (ROOT/"piano_teacher/notation/pixel_proof.py").read_text()
    phase3 = (ROOT/"piano_teacher/notation/phase3_pixels.py").read_text()
    native = (ROOT/"godot/notation/shared/view_base.gd").read_text()
    assert "renderer._stream_add_take(0.0,0.0,0.0," in harness
    assert "renderer.present_flow(at,snapshot,at)" in harness
    assert "PLAYHEAD_FRACTION = 0.33" in oracle
    # Verifiers anchor on the photographed timing rule, falling back to the
    # production fraction only for rasters without one.
    assert "return image.width * PLAYHEAD_FRACTION" in oracle
    assert "xpos=round(playhead_x(image))" in phase3
    rest = (ROOT/"piano_teacher/notation/rest_intervention.py").read_text()
    assert "playhead_x(Image.fromarray(original" in rest
    assert "PLAYHEAD_FRACTION := .33" in native


def test_production_journey_does_not_depend_on_removed_camera_switch():
    scenario = (ROOT/"godot/production_session_journey.gd").read_text()
    assert "stream_enabled" not in scenario
    assert "retained_ready()" in scenario
    assert "stream_world_beat" in scenario


def test_production_ready_smoke_accepts_hidden_offscreen_queue_replacement():
    script = (ROOT/"godot/production_ui_smoke.gd").read_text()
    # One logical READY take may hold several strips; the gate counts takes,
    # not strips (queued_takes), so strip-count text is intentionally absent.
    assert "queued_takes.size() != 1" in script
    assert "pending_count != 1" not in script
    assert "ready_world_origin = float(prepared[\"world_origin\"])" in script
    assert "moved hidden ink backwards" in script
    assert "Ready world-axis stopped or repositioned source" not in script



def test_transport_and_voice_have_no_parallel_production_owners():
    """Ban the exact duplicate paths responsible for recurring regressions."""
    main = (ROOT / "godot/main.gd").read_text()
    view = (ROOT / "godot/notation/native/view.gd").read_text()
    queue = (ROOT / "godot/score_stream_queue.gd").read_text()
    planner = (ROOT / "godot/score_transport_reservation.gd").read_text()
    cues = (ROOT / "godot/countin_cue_timeline.gd").read_text()
    coordinator = (ROOT / "godot/metronome_frame_coordinator.gd").read_text()
    visuals = (ROOT / "godot/game_countin.gd").read_text()
    voice = (ROOT / "godot/countin_voice_player.gd").read_text()
    assert "renderer.reserve_transport_action(" in main
    assert "renderer.arm_stream_take(" not in main
    assert "renderer.trim_resume_speculation(" not in main
    assert "renderer.trim_future_queue(" not in main
    assert "TransportReservation.plan(" in view
    assert "func trim_resume_speculation(" not in view
    assert "preview_tail_withdrawal(" in queue
    assert "preview_tail_withdrawal(" in planner
    assert 'planned["protected_take"]' in view
    assert "CountInCueTimeline" in cues or "func observe(" in cues
    assert "_cues.observe(" in coordinator
    assert "count_tick_index" not in coordinator
    assert "recovery_click_tick" not in coordinator
    assert "AudioStreamPlayer.new()" not in visuals
    assert "AudioStreamPlayer.new()" in voice
    assert "practice_view.bind_countin_voice_player(spoken_countin)" in main


def test_note_status_feedback_has_one_owner_and_no_detached_glow():
    """Guard against restoring rings, particles, overlays or queue copies."""
    score = (ROOT / "godot/native_score_feedback.gd").read_text()
    registry = (ROOT / "godot/note_status_registry.gd").read_text()
    ink = (ROOT / "godot/note_status_ink.gd").read_text()
    layer = (ROOT / "godot/notation/native/note_status_layer.gd").read_text()
    segment = (ROOT / "godot/notation/native/retained_segment.gd").read_text()
    native = (ROOT / "godot/notation/native/view.gd").read_text()
    main = (ROOT / "godot/main.gd").read_text()
    # One ledger, fed only by sequenced backend events; it draws nothing.
    assert 'var statuses := Statuses.new()' in score
    assert 'func ingest(event: Dictionary) -> String:' in score
    assert 'func _draw(' not in score and 'extends Node' in score
    assert 'midi_visual_events' not in score and 'feedback_marks' not in score
    assert 'stream_passes' not in score
    # Status ink is painted by each retained source strip, inside its clip.
    assert 'status_layer = NoteStatusLayer.new(self)' in segment
    assert 'segment.sync_note_status(take_key,note_status_source,note_status_visible)' in native
    assert 'Ink.paint(layer,glyphs' in layer
    for source in (score, layer, ink):
        assert 'draw_arc(' not in source and 'draw_circle(' not in source
        assert 'GlowField' not in source and 'note_glow' not in source
    assert 'func observe(' in registry and 'func prune(' in registry
    assert 'static func display_status(record: Dictionary) -> String:' in registry
    assert 'EARLY_RELEASE := "early_release"' in registry
    assert 'EARLY_ONSET := "early_onset"' in registry
    assert 'if status == Status.UNPLAYED' in ink and 'return false' in ink
    assert 'OUTER_GLOW_ALPHA := 0.045' in ink
    assert 'glyphs.paint_head(' in ink and 'draw_arc(' not in ink
    assert 'BLEND_MODE_SUB' in ink and 'BLEND_MODE_ADD' in ink
    # One acknowledged channel; no second snapshot path or stale-state check.
    assert 'feedback_inbox.acknowledge(' in main
    assert 'accept_live_event' not in main and 'poll_midi' not in main
    assert '_consume_live_piano_hits' not in main
    # Rendering never copies the online queue.
    projection = native[native.index("func _project_stream"):native.index("func present(")]
    assert 'stream_passes' not in projection and 'duplicate(' not in projection
    assert '_project_stream(playhead_x)' in native
