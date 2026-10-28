"""Characterize state-tick boundaries after splitting the update loop."""
from __future__ import annotations

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def _app(tmp_path):
    note = Note(0, 1, 60, 0, 0, "right")
    phrase = Phrase(1, 1, 2, 0, 8, (note,))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(Piece("Update", 100, (note,), (phrase,)))
    return engine


def test_idle_update_does_not_change_score_or_lesson(tmp_path):
    app = _app(tmp_path)
    try:
        previous = (app.score_revision, app.plan.identity, app.plan.streak)
        for _ in range(3):
            app._update()
        assert previous == (app.score_revision, app.plan.identity, app.plan.streak)
        assert app.pending_result is None and not app.running
    finally:
        app.db.close()


def test_pending_feedback_commits_only_at_the_deadline(tmp_path, monkeypatch):
    app = _app(tmp_path)
    try:
        called = []
        app.auto = True
        app.pending_result = object()
        app.next_at = 200.0
        app.feedback_marks = [{"status":"missed"}]
        app.feedback_unmapped = 1
        monkeypatch.setattr("piano_teacher.server.time.monotonic", lambda: 199.0)
        monkeypatch.setattr(app, "_commit_pending", lambda: called.append("commit") or "Piece mastered")
        app._update()
        assert called == []
        assert app.next_at == 200 and app.auto
        assert app.feedback_marks
        monkeypatch.setattr("piano_teacher.server.time.monotonic", lambda: 200.0)
        app._update()
        assert called == ["commit"]
        assert app.feedback_marks == [] and app.feedback_unmapped == 0
        assert app.next_at == 0 and app.auto is False
        assert app.feedback == "Piece mastered"
        app._update()
        assert called == ["commit"]
    finally:
        app.db.close()


def test_no_auto_commit_when_feedback_is_manual(tmp_path, monkeypatch):
    app = _app(tmp_path)
    try:
        app.auto = False
        app.pending_result = object()
        app.next_at = 10
        monkeypatch.setattr("piano_teacher.server.time.monotonic", lambda: 100.0)
        monkeypatch.setattr(app, "_commit_pending", lambda: (_ for _ in ()).throw(AssertionError("unexpected commit")))
        app._update()
        assert app.pending_result is not None
        assert app.next_at == 10
    finally:
        app.db.close()
