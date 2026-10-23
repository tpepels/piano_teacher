"""The visual loop is independent of the original MIDI grading attempt."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import time

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def sample_piece() -> Piece:
    notes = (
        Note(0, 1, 60, 0, 0, "right", "first"),
        Note(4, 5, 62, 0, 0, "right", "second"),
    )
    return Piece("Loop example", 110, notes,
                 (Phrase(1, 1, 2, 0, 8, notes),),
                 bar_boundaries=(0, 4, 8))


def engine(tmp_path: Path) -> PracticeEngine:
    app = PracticeEngine(tmp_path, enable_midi=False)
    app.plan = LearningPlan(sample_piece())
    app.fingerprint = "score-loop-fixture"
    return app


def test_preview_continues_after_one_empty_measure_without_reloading(tmp_path):
    app = engine(tmp_path)
    try:
        app.start()
        assert app.preview_only
        first_revision = app.score_revision
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        # Simulate the end of one ungraded passage, one beat into its gap.
        app.run_at = time.monotonic() - (length + 1) * 60 / app.plan.bpm
        app._update()
        assert app._preview_loop_pending and not app.running
        position = app.state()
        assert length < position["visual_scroll_beat"] < length + app.visual_gap_beats
        assert position["visual_scroll_speed"] > 0
        app.next_at = time.monotonic() - .01
        app._update()
        assert app.running and app.preview_only
        assert app.visual_offset_beats == length + app.visual_gap_beats
        assert app.count_in_beats == 0.0
        assert app.score_revision == first_revision
        assert app.state()["score_loop_enabled"]
    finally:
        app.db.close()


def test_clean_auto_take_increases_bpm_without_reengraving(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        assert not app.preview_only and app.auto
        bpm, original_revision = app.plan.bpm, app.score_revision
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        app.running = False
        app.pending_result = SimpleNamespace(
            correct=2, notes=[object(), object()], extra_notes=0, clean=True)
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.plan.bpm > bpm
        assert app.score_revision == original_revision
        assert app.running and app.auto
        assert app.visual_offset_beats == length + app.visual_gap_beats
        assert app.count_in_beats == 0
        assert app.plan.streak == 0
    finally:
        app.db.close()


def test_failed_auto_take_moves_back_in_place_and_never_advances_repeat(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        app.running = False
        app.pending_result = SimpleNamespace(
            correct=1, notes=[object(), object()], extra_notes=0, clean=False)
        app._retry_previous_pass = True
        app._visual_rewind_from = length
        app._visual_rewind_to = 0.0
        app._visual_rewind_at = time.monotonic() - .25
        app._visual_rewind_seconds = 1.0
        before = app.state()
        assert before["visual_scroll_speed"] < 0
        assert 0 < before["visual_scroll_beat"] < length
        revision = app.score_revision
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.visual_offset_beats == 0.0
        assert app.plan.bpm == app.plan.start_bpm
        assert app.score_revision == revision
        assert app.running
        assert not app._retry_previous_pass
    finally:
        app.db.close()


def test_backward_recovery_is_still_local_to_source_measure_grid(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        app.running = False
        app.pending_rewind = 4.0
        app._visual_rewind_from = 8.0
        app._visual_rewind_to = 4.0
        app._visual_rewind_at = time.monotonic() - .25
        app._visual_rewind_seconds = 1.0
        app.next_at = time.monotonic() + 1
        progress = app.state()
        assert progress["visual_scroll_speed"] < 0
        assert 4 < progress["visual_scroll_beat"] < 8
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.running
        assert app.play_from_beat == 4.0
        assert app.visual_offset_beats == 0
    finally:
        app.db.close()


def test_native_renderer_reuses_source_score_for_visible_loop_copies():
    project = Path(__file__).resolve().parents[1]
    native = (project / "godot/notation/native/view.gd").read_text()
    base = (project / "godot/notation/shared/view_base.gd").read_text()
    assert "func _paint_source_pass(" in native
    assert "var stride: float = timeline.duration_beats + empty_bar_beats" in native
    assert "for pass_index in range(first_pass, last_pass + 1)" in native
    assert "visual_scroll_beat-pass_start-play_from_beat" in native
    assert "visual_scroll_beat" in base


def test_start_does_not_replace_source_engraving_at_slow_learning_bpm(tmp_path):
    app = engine(tmp_path)
    try:
        # Source engraving is immutable at 110 BPM while practice starts 40.
        app._layout_cache = object()
        app._layout_bpm = app.plan.piece.bpm
        assert app.plan.bpm != app._layout_bpm
        before = app.score_revision
        app.control("start")
        assert app.running
        assert app.count_in_beats > 0.0
        assert app.score_revision == before
        assert app.awaiting_score_revision is None
    finally:
        app.db.close()
