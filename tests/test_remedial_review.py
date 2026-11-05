"""Boundary validation precedes timed remedial session mutations."""
from types import SimpleNamespace

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.remediation import plan_timed_remedial_review
from piano_teacher.server import PracticeEngine


def test_review_uses_source_measure_numbers_for_offset_phrase():
    phrase = Phrase(2, 4, 6, 12, 24, ())
    assignment = SimpleNamespace(start_beat=4.0, end_beat=12.0)
    review = plan_timed_remedial_review(
        assignment, phrase, (0, 4, 8, 12, 16, 20, 24))
    assert review.retry_range == {
        "start_beat": 4.0, "end_beat": 12.0,
        "first_bar": 5, "last_bar": 6,
    }


@pytest.mark.parametrize(("start", "end"), [
    (1, 4), (0, 3), (4, 4), (8, 4), (0, 12),
])
def test_invalid_remedial_interval_is_rejected(start, end):
    phrase = Phrase(1, 1, 2, 0, 8, ())
    assignment = SimpleNamespace(start_beat=start, end_beat=end)
    with pytest.raises(ValueError, match="Remedial section"):
        plan_timed_remedial_review(assignment, phrase, (0, 4, 8))


def test_invalid_review_does_not_interrupt_running_take(tmp_path):
    notes = (
        Note(0, 1, 60, 0, 0, "right", "n0"),
        Note(4, 5, 62, 0, 0, "right", "n1"),
    )
    piece = Piece("Review fixture", 80, notes,
                  (Phrase(1, 1, 2, 0, 8, notes),),
                  bar_boundaries=(0, 4, 8))
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        app.plan = LearningPlan(piece)
        app.fingerprint = "invalid-remedial-review-fixture"
        app.start()
        before = (app.running, app.transport_id, app.visual_transport.run_at, app.mode)
        assignment = SimpleNamespace(
            stage_key=app.plan.identity, guided=False,
            start_beat=1.0, end_beat=4.0, focus="timing")
        with pytest.raises(ValueError, match="Remedial section"):
            app._start_remedial_assignment(assignment)
        assert (app.running, app.transport_id, app.visual_transport.run_at, app.mode) == before
    finally:
        app.db.close()



def test_automatic_pitch_remediation_remains_timed_and_returns_to_full_source(tmp_path):
    import time
    notes = (
        Note(0, 1, 60, 0, 0, "right", "note-0"),
        Note(4, 5, 62, 0, 0, "right", "note-1"),
    )
    piece = Piece("Automatic remedial", 90, notes,
                  (Phrase(1, 1, 2, 0, 8, notes),), bar_boundaries=(0, 4, 8))
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        app.plan = LearningPlan(piece)
        app.fingerprint = "automatic-remediation-fingerprint"
        app.midi.port = object()  # Connected: this is graded, not a preview.
        app.mode = "practice"
        app.auto = True
        assignment = SimpleNamespace(
            stage_key=app.plan.identity, guided=True,
            start_beat=0.0, end_beat=4.0, focus="pitch", reason="missed source")
        deadline = time.monotonic() + 0.5
        app._start_remedial_assignment(assignment, deadline=deadline)
        assert app.mode == "practice" and app.running and app.auto
        assert not app.preview_only and app._automatic_remedial_review
        assert app.review_end_beat == 4.0
        assert app.visual_transport.play_from_beat == 0.0
        assert app.visual_transport.run_at == deadline
        assert not app.plan.mastered and app.plan.streak == 0
        assert app.awaiting_score_revision is None
        # A focused attempt is assessed as partial source practice.
        from piano_teacher.completion_route import completion_route
        assert completion_route(app.mode, app.review_end_beat,
                                app.visual_transport.play_from_beat) == "section_review"
        app.measurement.finish()
        app._finish_partial_recovery(SimpleNamespace(summary="Focused section"),
                                     time.monotonic())
        assert not app._automatic_remedial_review
        assert app.review_end_beat is None and app.auto
        assert app.visual_transport.pending_rewind == 0.0
        assert app.plan.mastered == {}
    finally:
        app.db.close()


def test_manual_remediation_stays_explicit_and_can_be_cancelled(tmp_path):
    notes = (Note(0, 1, 60, 0, 0, "right", "note-0"),)
    piece = Piece("Manual remedial", 90, notes,
                  (Phrase(1, 1, 2, 0, 8, notes),), bar_boundaries=(0, 4, 8))
    app = PracticeEngine(tmp_path, enable_midi=False)
    try:
        app.plan = LearningPlan(piece)
        app.fingerprint = "manual-remediation-fingerprint"
        assignment = SimpleNamespace(
            stage_key=app.plan.identity, guided=False,
            start_beat=0.0, end_beat=4.0, focus="timing")
        app._start_remedial_assignment(assignment)
        assert app.mode == "practice" and not app.running
        assert app.review_end_beat == 4.0
        assert not app._automatic_remedial_review
        app._stop()
        assert app.review_end_beat is None
        assert not app._automatic_remedial_review
    finally:
        app.db.close()
