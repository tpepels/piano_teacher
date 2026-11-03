"""Next MIDI stages must move on one musical axis without reloading ink.

All tests exercise the current engine and its actual grading/persistence
routes. Only ahead-of-time bitmap completion is injected; failure retries use
the existing source-bound transport rules.
"""
from __future__ import annotations

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.application.attempt_progression import SETTLEMENT_SECONDS
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.server import PracticeEngine


def _engine(tmp_path):
    notes = (
        Note(0, .5, 60, 0, 0, "right", "a"),
        Note(1, 1.5, 62, 0, 0, "right", "b"),
        Note(2, 2.5, 64, 0, 0, "right", "c"),
        Note(3, 3.5, 65, 0, 0, "right", "d"),
        Note(0, .75, 48, 1, 0, "left", "e"),
        Note(2, 2.75, 50, 1, 0, "left", "f"),
    )
    piece = Piece("Seamless source", 110, notes,
                  (Phrase(1, 1, 1, 0, 4, notes),),
                  bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
    engine.fingerprint = "seamless-source"
    engine.plan.set_bpm(engine.plan.target_bpm)
    engine.plan.streak = 2
    engine.midi.port = object()
    engine.start()
    assert engine.auto and not engine.preview_only
    assert engine.plan.lesson_step_number < len(engine.plan.lesson_steps)
    return engine


def _assess(engine, status="correct"):
    notes = tuple(n for n in engine.plan.active_phrase.notes
                  if n.hand == engine.plan.hand or engine.plan.hand == "both")
    return Assessment(tuple(NoteAssessment(note, status) for note in notes), 0)


class Prepared:
    def __init__(self, engine):
        self.assets = ScoreArtifacts(engine.preprocessing)
        self.adoptions = []
    def ready(self, _selection):
        return True
    def adopt(self, selection):
        self.adoptions.append(selection)
        return self.assets


def _finish(engine, status="correct"):
    duration = 4 * 60.0 / engine.plan.bpm
    at = engine.visual_transport.run_at + duration + SETTLEMENT_SECONDS
    engine.running = False
    engine.recorder = None
    engine._finish_full_passage(_assess(engine, status), 4.0, duration, at)
    return at


def test_precompiled_target_stage_replaces_current_without_score_ack_gap(tmp_path):
    engine = _engine(tmp_path)
    try:
        future = Prepared(engine)
        engine.future_score = future
        selection, number = engine._next_stage_selection()
        assert number == engine.plan.lesson_step_number + 1
        assert selection.revision == engine.score_revision + 1
        ack = engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)
        assert ack["accepted"] and ack["step_number"] == number

        prior_revision = engine.score_revision
        prior_attempt = engine.transport_id
        prior_origin = engine.visual_transport.visual_offset_beats
        old_bpm = engine.plan.bpm
        completed_at = _finish(engine)
        assert engine.plan.lesson_step_number == number
        assert engine.plan.mastered
        assert engine.score_revision == prior_revision + 1
        assert engine.score_artifacts is future.assets
        assert future.adoptions[0].identity == selection.identity
        assert engine.awaiting_score_revision is None
        assert engine.running and engine.auto
        assert engine.transport_id == prior_attempt + 1
        assert engine.visual_transport.run_at == pytest.approx(completed_at)
        assert engine.count_in_beats == 0.0
        assert engine.visual_transport.visual_offset_beats == pytest.approx(
            prior_origin + 4.0 + SETTLEMENT_SECONDS * old_bpm / 60.0)
        assert engine.pending_result is None
    finally:
        engine.db.close()


def test_unready_future_keeps_safe_revision_ack_handshake(tmp_path):
    engine = _engine(tmp_path)
    try:
        old_stage = engine.plan.identity
        old_revision = engine.score_revision
        old_transport = engine.transport_id
        complete_at = _finish(engine)
        # The required full rest still separates any unprepared transition.
        assert engine.plan.identity == old_stage
        assert engine.pending_result is not None
        assert engine.visual_transport.next_at > complete_at
        old_deadline = engine.visual_transport.next_at
        engine._advance_pending_feedback(old_deadline)
        assert engine.plan.identity != old_stage
        assert engine.score_revision == old_revision + 1
        assert engine.awaiting_score_revision == engine.score_revision
        assert not engine.auto
        assert not engine.running
        assert engine.transport_id == old_transport
        assert engine.visual_transport.visual_offset_beats == 0.0
    finally:
        engine.db.close()


def test_wrong_take_keeps_existing_backward_recovery_not_stage_promotion(
        tmp_path):
    engine = _engine(tmp_path)
    try:
        next_stage = engine._next_stage_selection()
        engine.future_score = Prepared(engine)
        selection, _ = next_stage
        engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)
        old_revision = engine.score_revision
        old_stage = engine.plan.identity
        _finish(engine, "wrong")
        assert engine.plan.identity == old_stage
        assert engine.score_revision == old_revision
        assert engine.visual_transport._retry_previous_pass
        assert engine.visual_transport._preparation_pending
        assert engine.visual_transport.pending_rewind is not None
        assert engine.pending_result is not None
    finally:
        engine.db.close()
