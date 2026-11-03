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
