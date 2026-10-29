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

from dataclasses import replace
from types import SimpleNamespace

from piano_teacher.application.practice_transitions import (
    TransitionContext, phase, run_before_assessment,
)


def test_transition_priority_is_explicit_and_pure():
    base = TransitionContext(
        has_plan=True, learning=False, paused=False, listening=False,
        preview_pending=False, preparation_pending=False,
        feedback_pending=False, awaiting_score=False, rewind_pending=False,
        running=True, run_at=100.0)
    assert phase(base, 99.0) == "idle"
    assert phase(base, 100.0) == "performing"
    assert phase(replace(base, feedback_pending=True, rewind_pending=True), 101) == "feedback"
    assert phase(replace(base, preview_pending=True, feedback_pending=True), 101) == "preview"
    assert phase(replace(base, awaiting_score=True, rewind_pending=True), 101) == "awaiting_score"
    assert phase(replace(base, learning=True, paused=True), 101) == "learning"
    assert phase(replace(base, paused=True, listening=True), 101) == "paused"
    assert phase(replace(base, has_plan=False, learning=True), 101) == "no_plan"


def test_preview_continuation_uses_original_deadline_and_never_grades(tmp_path):
    app = _app(tmp_path)
    try:
        app._preview_loop_pending = True
        app.next_at = 200.0
        app.running = False
        called = []
        app._source_model = lambda: {"practice_timeline": {"stride_beats": 12.0}}
        app._continue_at = lambda deadline: called.append(deadline)
        assert run_before_assessment(app, 199.9)
        assert called == []
        assert run_before_assessment(app, 201.0)
        assert called == [200.0]
        assert app.visual_offset_beats == 12.0
    finally:
        app.db.close()


def test_rewind_waits_for_deadline_then_resumes_exact_target(tmp_path):
    app = _app(tmp_path)
    try:
        app.pending_rewind = 3.0
        app.next_at = 90.0
        app.running = False
        called = []
        app._continue_at = lambda deadline, *, from_beat: called.append(
            (deadline, from_beat))
        assert run_before_assessment(app, 89.9)
        assert called == []
        assert run_before_assessment(app, 90.0)
        assert called == [(90.0, 3.0)]
    finally:
        app.db.close()


def test_loading_and_paused_takes_cannot_finish_assessment(tmp_path):
    app = _app(tmp_path)
    try:
        app.running = True
        app.run_at = 0.0
        app.awaiting_score_revision = 42
        assert run_before_assessment(app, 100.0)
        app.awaiting_score_revision = None
        app.paused = True
        assert run_before_assessment(app, 100.0)
        app.paused = False
        assert not run_before_assessment(app, 100.0)
    finally:
        app.db.close()
