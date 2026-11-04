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
        self.warmed = []
    def ready(self, _selection):
        return True
    def warm(self, selection, *, number, label):
        self.warmed.append((selection, number, label))
    def failure(self, _selection):
        return None
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


def test_unready_future_extends_scrolling_runway_until_stage_is_compiled(tmp_path):
    engine = _engine(tmp_path)
    try:
        class Late(Prepared):
            available = False
            def ready(self, _selection):
                return self.available
            def adopt(self, selection):
                return super().adopt(selection) if self.available else None

        late = Late(engine)
        engine.future_score = late
        old_stage = engine.plan.identity
        old_revision = engine.score_revision
        old_transport = engine.transport_id
        selection, number = engine._next_stage_selection()
        complete_at = _finish(engine)
        assert engine.plan.identity == old_stage
        assert engine.pending_result is not None
        deadline = engine.visual_transport.next_at
        assert deadline > complete_at
        beat_at_deadline = engine._visual_motion(deadline)[0]
        engine._advance_pending_feedback(deadline)
        # No replacement score, revision reset, hidden count-in or grading
        # before native notation has actually been acknowledged.
        assert engine.plan.identity == old_stage
        assert engine.score_revision == old_revision
        assert engine.awaiting_score_revision is None
        assert engine.auto and not engine.running
        assert engine.pending_result is not None
        assert engine.transport_id == old_transport
        assert engine._visual_motion(deadline + .05)[0] > beat_at_deadline
        assert engine.visual_transport.next_at == pytest.approx(deadline + .10)

        late.available = True
        assert engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)["accepted"]
        ready_at = deadline + .10
        before = engine._visual_motion(ready_at)[0]
        engine._advance_pending_feedback(ready_at)
        start_beat = before + 2.0
        start_at = engine.visual_transport.next_at
        assert start_at == pytest.approx(ready_at + 2 * 60.0 / engine.plan.bpm)
        assert engine._stage_handoff_visual_beat == pytest.approx(start_beat)
        assert engine._state_snapshot()["next_stage_start_beat"] == pytest.approx(start_beat)
        assert engine._visual_motion(start_at)[0] == pytest.approx(start_beat)

        engine._advance_pending_feedback(start_at)
        assert engine.plan.lesson_step_number == number
        assert engine.plan.mastered
        assert engine.score_revision == old_revision + 1
        assert engine.awaiting_score_revision is None
        assert engine.score_artifacts is late.assets
        assert engine.running and engine.auto
        assert engine.transport_id == old_transport + 1
        assert engine.visual_transport.run_at == pytest.approx(start_at)
        assert engine.visual_transport.visual_offset_beats == pytest.approx(start_beat)
        assert engine._visual_motion(start_at)[0] == pytest.approx(start_beat)
        assert engine.count_in_beats == 0
        assert engine.pending_result is None
        assert "next_stage_start_beat" not in engine._state_snapshot()
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


def test_two_consecutive_prepared_stage_transitions_keep_global_beat(tmp_path):
    engine = _engine(tmp_path)
    try:
        prepared = Prepared(engine)
        engine.future_score = prepared
        first_offset = engine.visual_transport.visual_offset_beats
        for advancement in (2, 3):
            engine.plan.set_bpm(engine.plan.target_bpm)
            engine.plan.streak = 2
            selection, target_number = engine._next_stage_selection()
            assert target_number == advancement
            current_bpm = engine.plan.bpm
            length = (engine.plan.active_phrase.end -
                      engine.plan.active_phrase.start)
            engine.acknowledge_preloaded_stage(
                stage_key=selection.stage_key, revision=selection.revision)
            finished_at = _finish(engine)
            assert engine.plan.lesson_step_number == advancement
            assert engine.awaiting_score_revision is None
            assert engine.running
            assert engine.count_in_beats == 0.0
            assert engine.visual_transport.run_at == pytest.approx(finished_at)
            first_offset += length + SETTLEMENT_SECONDS * current_bpm / 60.0
            assert engine.visual_transport.visual_offset_beats == pytest.approx(first_offset)
        assert len(prepared.adoptions) == 2
        assert prepared.adoptions[0].stage_key != prepared.adoptions[1].stage_key
    finally:
        engine.db.close()


def test_preloaded_stage_continues_in_guided_origin_practice(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.course_guided = True
        prepared = Prepared(engine)
        engine.future_score = prepared
        selection, next_number = engine._next_stage_selection()
        engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)
        _finish(engine)
        assert engine.plan.lesson_step_number == next_number
        assert engine.running and engine.mode == "practice"
        assert engine.awaiting_score_revision is None
    finally:
        engine.db.close()


def test_acknowledged_stage_without_adoptable_ink_fails_closed(tmp_path):
    engine = _engine(tmp_path)
    try:
        class Unavailable(Prepared):
            def adopt(self, _selection):
                return None

        engine.future_score = Unavailable(engine)
        selection, _ = engine._next_stage_selection()
        engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)
        first_revision = engine.score_revision
        _finish(engine)
        assert engine.score_revision == first_revision
        assert engine.awaiting_score_revision is None
        assert not engine.running and engine.visual_transport.paused
        assert engine.visual_transport.next_at == 0.0
        assert engine.visual_transport.visual_offset_beats == 0.0
        assert engine.pending_result is not None
        assert engine.feedback == "Cannot prepare the next lesson score"
    finally:
        engine.db.close()


def test_manual_stop_and_restart_do_not_waste_an_already_prepared_step(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.future_score = Prepared(engine)
        selection, number = engine._next_stage_selection()
        engine.acknowledge_preloaded_stage(
            stage_key=selection.stage_key, revision=selection.revision)
        engine.control("stop")
        assert engine._future_stage_ready == (selection.stage_key, selection.revision)
        engine.plan.set_bpm(engine.plan.target_bpm)
        engine.plan.streak = 2
        engine.start()
        assert engine.running and engine.auto
        _finish(engine)
        assert engine.plan.lesson_step_number == number
        assert engine.awaiting_score_revision is None
    finally:
        engine.db.close()

def test_second_warmed_stage_has_its_actual_future_revision(tmp_path):
    engine = _engine(tmp_path)
    try:
        prepared = Prepared(engine)
        engine.future_score = prepared
        first, first_number = engine._next_stage_selection()
        second, second_number = engine._next_stage_selection(offset=2)
        assert second_number == first_number + 1
        assert second.revision == first.revision + 1
        engine.acknowledge_preloaded_stage(
            stage_key=first.stage_key, revision=first.revision)
        assert prepared.warmed[0][0].identity == second.identity
        _finish(engine)
        current_next, next_number = engine._next_stage_selection()
        assert next_number == second_number
        assert current_next.identity == second.identity
    finally:
        engine.db.close()


def test_native_renderer_failure_fails_closed_only_at_mastery_deadline(tmp_path):
    engine = _engine(tmp_path)
    try:
        original_identity = engine.plan.identity
        original_revision = engine.score_revision
        original_transport = engine.transport_id
        next_score, next_number = engine._next_stage_selection()
        assert not engine.report_preload_failure(
            fingerprint="stale-score", step_number=next_number,
            revision=next_score.revision, error="Old source")["accepted"]
        assert not engine.report_preload_failure(
            fingerprint=engine.fingerprint, step_number=next_number,
            revision=next_score.revision - 1, error="Old revision")["accepted"]
        assert not engine.report_preload_failure(
            fingerprint=engine.fingerprint, step_number=next_number + 1,
            revision=next_score.revision, error="Wrong step")["accepted"]
        assert engine._native_preload_failure is None

        reported = engine.report_preload_failure(
            fingerprint=engine.fingerprint, step_number=next_number,
            revision=next_score.revision, error="Verovio glyph atlas invalid")
        assert reported["accepted"]
        finish_at = _finish(engine)
        assert engine.plan.identity == original_identity
        assert engine.score_revision == original_revision
        assert not engine.visual_transport.paused
        deadline = engine.visual_transport.next_at
        assert deadline > finish_at
        before = engine._visual_motion(deadline)[0]
        engine._advance_pending_feedback(deadline)
        assert engine.visual_transport.paused
        assert engine.visual_transport.next_at == 0.0
        assert engine._visual_motion(deadline + 2)[0] == pytest.approx(before)
        assert engine.plan.identity == original_identity
        assert engine.score_revision == original_revision
        assert engine.transport_id == original_transport
        assert engine.awaiting_score_revision is None
        assert engine.pending_result is not None
        assert "Verovio glyph atlas invalid" in engine.next_action
        engine.control("stop")
        assert engine._native_preload_failure is None
    finally:
        engine.db.close()
