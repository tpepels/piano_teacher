"""Live PracticeEngine Coda try/return uses the normal teaching owners.

A trial is intentionally a new, fingerprint-isolated lesson on one actual
transformed MIDI excerpt. Its Play/Listen/score APIs are the existing routes,
not a separate Coda-specific clock or renderer.
"""
from pathlib import Path

import pytest

from piano_teacher.server import PracticeEngine
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.practice import PlayedNote


MIDI=Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


def _engine(tmp_path):
    engine=PracticeEngine(tmp_path,enable_midi=False)
    engine.plan=LearningPlan(load_midi(MIDI))
    engine.fingerprint="source-fingerprint-coda-test"
    return engine


def test_trial_switches_real_engine_score_listen_grader_and_restores_source(tmp_path):
    engine=_engine(tmp_path)
    try:
        source=engine.plan
        original_identity=source.identity
        original_fingerprint=engine.fingerprint
        revision=engine.score_revision
        engine.control("coda_try",family="tempo-shaping")
        assert engine._coda_trial is not None
        assert engine.plan is not source
        assert engine.fingerprint!=original_fingerprint
        assert engine.plan.piece.source_format=="midi"
        assert engine.score_revision>revision
        assert engine.state()["coda_trial"]
        assert engine.state()["coda_family"]=="tempo-shaping"
        assert engine.state()["coda_available"]
        assert source.identity==original_identity
        selected=engine._score_selection()
        assert selected.piece is engine.plan.piece
        assert selected.phrase==engine.plan.active_phrase
        assert selected.transformed_rhythm is False  # canonical source is already retimed
        assert engine.plan.piece.bar_boundaries[-1] > source.exercise.phrase.end
        # The same selected trial piece enters the standard grading path.
        played=[PlayedNote(n.pitch,(n.start-engine.plan.active_phrase.start)*60/engine.plan.bpm,
                           (n.end-engine.plan.active_phrase.start)*60/engine.plan.bpm)
                for n in engine.plan.active_variant.notes]
        from piano_teacher.practice import evaluate
        assert evaluate(engine.plan.active_phrase,engine.plan.hand,engine.plan.bpm,played).clean
        engine.control("listen")
        assert engine.mode=="listen"
        assert engine.listen._selection.variant==engine.plan.active_variant
        assert engine.listen._selection.stage_key==engine.plan.identity
        engine.control("practice",wait_for_player=True)
        assert engine.mode=="practice"
        engine.control("coda_exit")
        assert engine._coda_trial is None
        assert engine.plan is source
        assert engine.fingerprint==original_fingerprint
        assert engine.plan.identity==original_identity
        assert not engine.state()["coda_trial"]
    finally:
        engine.listen.cancel()
        engine.db.close()


def test_invalid_trial_does_not_stop_or_mutate_live_source(tmp_path):
    engine=_engine(tmp_path)
    try:
        source=engine.plan
        revision=engine.score_revision
        with pytest.raises(ValueError,match="Choose"):
            engine.control("coda_try",family="not-a-family")
        assert engine.plan is source
        assert engine._coda_trial is None
        assert engine.score_revision==revision
        engine.control("coda_exit")
        assert engine.plan is source
    finally:
        engine.db.close()


def test_load_switches_clear_any_trial(tmp_path):
    engine=_engine(tmp_path)
    try:
        engine.control("coda_try",family="tempo-shaping")
        assert engine._coda_trial
        # An explicit new score is a new owning lesson, never the
        # temporary replacement of the previous source piece.
        engine.load(str(MIDI))
        assert engine._coda_trial is None
        assert not engine.state()["coda_trial"]
        assert engine.plan.piece.title==MIDI.stem
    finally:
        engine.db.close()
