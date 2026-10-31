"""A single backend-owned attempt tick, with cached source-grid boundaries."""
from __future__ import annotations

from types import SimpleNamespace

from piano_teacher.application import attempt_progression as module
from piano_teacher.application.attempt_progression import AttemptProgression
from piano_teacher.music import Phrase


class Assessment:
    def __init__(self, recovery=None):
        self.recovery = recovery
        self.calls = []

    def recover(self, phrase, **kwargs):
        self.calls.append((phrase, kwargs))
        return self.recovery


class Engine:
    def __init__(self, strategy="default"):
        phrase = Phrase(1, 1, 2, 0.0, 8.0, ())
        self.plan = SimpleNamespace(
            active_phrase=phrase, piece=SimpleNamespace(
                bar_boundaries=(0.0, 4.0, 8.0)),
            exercise_strategy=SimpleNamespace(name=strategy),
            hand="right", bpm=60)
        self.policy = Assessment()
        self.assessment_policies = SimpleNamespace(select=lambda tempo: self.policy)
        self.mode = "practice"
        self.teaching = None
        self.paused = False
        self._preview_loop_pending = False
        self._preparation_pending = False
        self.pending_result = None
        self.awaiting_score_revision = None
        self.pending_rewind = None
        self.running = True
        self.run_at = 100.0
        self.play_from_beat = 0.0
        self.preview_only = False
        self.auto = True
        self.is_builtin_warmup = False
        self.next_boundary_beat = 4.0
        self.review_end_beat = None
        self.visual_gap_beats = 4.0
        self.recorder = None
        self.completed = []
        self.recovered = []

    def _elapsed_beat(self, seconds):
        return max(0.0, seconds)

    def _elapsed_seconds(self, beat):
        return beat

    def _active_tempo_map(self):
        return None

    def _complete_attempt(self, *args):
        self.completed.append(args)

    def _apply_rolling_recovery(self, *args):
        self.recovered.append(args)


def test_authoritative_tick_caches_source_grid_until_phrase_changes(monkeypatch):
    actual = module.phrase_grid
    calls = []
    def observed(*args):
        calls.append(args)
        return actual(*args)
    monkeypatch.setattr(module, "phrase_grid", observed)
    engine = Engine()
    progression = AttemptProgression()
    for now in (100.0, 102.0, 103.0, 104.0, 105.0, 107.9):
        progression.advance(engine, now)
    assert len(calls) == 1
    assert engine.next_boundary_beat == 8.0
    assert len(engine.policy.calls) == 1
    assert not engine.completed
    progression.advance(engine, 108.2)
    assert len(calls) == 1
    assert len(engine.policy.calls) == 2
    assert len(engine.completed) == 1
    assert engine.completed[0][1:4] == (8.0, 8.0, 8.0)

    replacement = Phrase(2, 1, 2, 0.0, 8.0, ())
    assert progression.grid_for(replacement, engine.plan.piece.bar_boundaries) == (
        0.0, 4.0, 8.0)
    assert len(calls) == 2


def test_coda_defers_rolling_assessment_until_end_of_phrase():
    engine = Engine(strategy="coda-part")
    progression = AttemptProgression()
    progression.advance(engine, 104.01)
    assert not engine.policy.calls
    assert engine.next_boundary_beat == 4.0
    progression.advance(engine, 108.19)
    assert len(engine.policy.calls) == 2
    assert not engine.completed


def test_recovery_preempts_attempt_completion():
    engine = Engine()
    engine.policy.recovery = object()
    progression = AttemptProgression()
    progression.advance(engine, 110.0)
    assert len(engine.recovered) == 1
    assert not engine.completed
    assert engine.next_boundary_beat == 4.0


def test_preview_shortens_settlement_without_grading():
    engine = Engine()
    engine.preview_only = True
    engine.visual_gap_beats = .05
    progression = AttemptProgression()
    progression.advance(engine, 108.04)
    assert not engine.completed
    progression.advance(engine, 108.06)
    assert len(engine.completed) == 1
    assert not engine.policy.calls
