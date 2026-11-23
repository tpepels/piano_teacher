"""A2 rolling recovery: one durable take, one selected effect chain.

These tests exercise the real receipt owner and the worker's pending-decision
precedence without synthesizing a second grader or a replacement engine.
"""
from dataclasses import dataclass, replace
from types import SimpleNamespace

import pytest

from piano_teacher.application.take import Take
from piano_teacher.application.attempt_settlement import (
    AttemptSettlement, PendingTeachingDecision, RollingTake, TakeResult,
)
from piano_teacher.application.practice_timeline import PracticeTimeline
from piano_teacher.application.take_progression import TakeProgression
from piano_teacher.teaching_decisions import TeachingBinding


@dataclass(frozen=True)
class _Course:
    piece: object
    definition: object
    progress: object
    key: str


def _settled_rolling():
    piece = object()
    definition = object()
    progress = object()
    course = _Course(piece, definition, progress, "course:stage")
    decision = SimpleNamespace(
        decision_id="decided", definition_after=definition, progress_after=progress)
    pending = PendingTeachingDecision(
        event=SimpleNamespace(kind="rolling_result"),
        state=SimpleNamespace(course=course),
        decision=decision,
        phase="settled",
        receipt=SimpleNamespace(stage_changed=False, source_changed=False))
    binding = TeachingBinding(
        "run", "session", "source-sha", "course:stage", 4, 8, 20, 2)
    source_decision = SimpleNamespace(end_beat=4.0)
    phrase = object()
    transition = SimpleNamespace(
        uses_completed_rest=False, guided=False, action="repair")
    original = TakeResult(
        binding=binding, score_revision=11, attempt_id="original-attempt",
        mode="practice", hand="right", from_beat=0.0, end_beat=4.0,
        bpm=72, played=(), assessment=None, source_note_ids=("original-note",))
    frozen = RollingTake(
        source_decision, phrase, (0.0, 4.0), 4.0, 100.0, pending,
        transition, 72, 105.0, original)
    owner = AttemptSettlement(None, None, None, None)
    owner.pending = pending
    owner._rolling = frozen
    plan = SimpleNamespace(
        piece=piece, lesson_definition=definition,
        teaching_progress=lambda: progress)
    committed = replace(binding, authority_revision=9)
    return owner, frozen, plan, committed


def _replay(owner, frozen, plan, binding):
    return owner.complete_rolling(
        decision=frozen.decision, phrase=frozen.phrase, grid=frozen.grid,
        score_beat=frozen.score_beat, now=107.0,
        bpm=frozen.take.bpm, scored_end=frozen.scored_end,
        hand=frozen.take.hand, played=(),
        from_beat=frozen.take.from_beat, tempo=None,
        policies=None, prepare_decision=None, plan=plan, binding=binding,
        policy=None, score_revision=frozen.take.score_revision)


def test_rolling_retry_reuses_immutable_take_and_committed_progress():
    owner, frozen, plan, committed = _settled_rolling()
    assert _replay(owner, frozen, plan, committed) is frozen
    assert owner.rolling_record is frozen
    assert frozen.take.source_note_ids == ("original-note",)


@pytest.mark.parametrize("mutate", [
    {"run_id": "another-run"},
    {"session_id": "another-session"},
    {"fingerprint": "another-source"},
    {"transport_id": 21},
    {"cancellation_generation": 3},
    {"authority_revision": 8},
    {"authority_revision": 10},
    {"course_revision": 5},
    {"stage_key": "another-stage"},
])
def test_rolling_retry_rejects_different_source_or_lifetime(mutate):
    owner, frozen, plan, committed = _settled_rolling()
    with pytest.raises(ValueError):
        _replay(owner, frozen, plan, replace(committed, **mutate))
    assert owner.rolling_record is frozen
    assert frozen.pending.phase == "settled"


def test_rolling_retry_rejects_progress_or_course_replacement():
    owner, frozen, plan, committed = _settled_rolling()
    for changed in (
        SimpleNamespace(
            piece=object(), lesson_definition=plan.lesson_definition,
            teaching_progress=plan.teaching_progress),
        SimpleNamespace(
            piece=plan.piece, lesson_definition=object(),
            teaching_progress=plan.teaching_progress),
        SimpleNamespace(
            piece=plan.piece, lesson_definition=plan.lesson_definition,
            teaching_progress=lambda: object()),
    ):
        with pytest.raises(ValueError):
            _replay(owner, frozen, changed, committed)
    assert owner.rolling_record is frozen


def test_rolling_effects_are_acknowledged_once_and_cannot_publish_early():
    owner, frozen, _plan, _binding = _settled_rolling()
    fired = []

    def effect(name):
        return lambda: fired.append(name)

    owner.rolling_effect(frozen, "tempo", effect("tempo"))
    owner.rolling_effect(frozen, "tempo", effect("tempo-repeated"))
    assert fired == ["tempo"]
    with pytest.raises(ValueError, match="unapplied"):
        owner.finish_rolling_publication(frozen)
    for name in ("prepare", "streak", "attempt", "notices"):
        owner.rolling_effect(frozen, name, effect(name))
    owner.finish_rolling_publication(frozen)
    assert frozen.pending.phase == "published"
    assert owner.rolling_record is None
    with pytest.raises(ValueError, match="superseded"):
        owner.rolling_effect(frozen, "tempo", effect("late"))


def test_failed_rolling_effect_keeps_prior_acknowledgements_for_retry():
    owner, frozen, _plan, _binding = _settled_rolling()
    calls = []

    owner.rolling_effect(frozen, "tempo", lambda: calls.append("tempo"))

    def failed_prepare():
        calls.append("failed-prepare")
        raise OSError("visual preparation unavailable")

    with pytest.raises(OSError):
        owner.rolling_effect(frozen, "prepare", failed_prepare)
    assert frozen.pending.phase == "settled"
    assert owner.rolling_record is frozen

    owner.rolling_effect(frozen, "tempo", lambda: calls.append("duplicate-tempo"))
    owner.rolling_effect(frozen, "prepare", lambda: calls.append("retry-prepare"))
    for name in ("streak", "attempt", "notices"):
        owner.rolling_effect(frozen, name, lambda: None)
    owner.finish_rolling_publication(frozen)
    assert calls == ["tempo", "failed-prepare", "retry-prepare"]


def test_rolling_pause_requires_all_cancel_effects():
    owner, frozen, _plan, _binding = _settled_rolling()
    frozen = replace(frozen, transition=SimpleNamespace(
        uses_completed_rest=True, guided=True, action="pause"))
    owner._rolling = frozen
    for name in ("tempo", "take_end", "prepare", "streak",
                 "attempt", "notices", "withdraw", "stop_auto",
                 "cancel_preparation"):
        owner.rolling_effect(frozen, name, lambda: None)
    with pytest.raises(ValueError, match="unapplied"):
        owner.finish_rolling_publication(frozen)
    owner.rolling_effect(frozen, "cancel_continuation", lambda: None)
    owner.finish_rolling_publication(frozen)
    assert frozen.pending.phase == "published"


def test_worker_replays_pending_rolling_result_before_grading_next_boundary():
    owner, frozen, _plan, _binding = _settled_rolling()
    applied = []
    transport = SimpleNamespace(
        mode="practice", running=True, paused=False, intent=None)
    progression = TakeProgression(
        lesson=None, transport=transport,
        take=Take(runtime=SimpleNamespace(performance_summary=None),
                  settlement=owner),
        midi_input=None, transport_timing=None,
        attempt_progression=SimpleNamespace(
            inspect=lambda *args, **kwargs: pytest.fail(
                "Previously graded boundary must not be assessed again")),
        rolling_recovery=SimpleNamespace(
            apply_rolling_recovery=lambda *args: applied.append(args)),
        completion=None)
    transitions = SimpleNamespace(run=lambda now: (False, False))
    worker = PracticeTimeline(
        observations=SimpleNamespace(observe=lambda: 110.0),
        transitions=transitions, progression=progression)

    assert worker.update_transition() is False
    assert applied == [(frozen.decision, frozen.phrase, frozen.grid,
                        frozen.score_beat, 110.0)]
    transport.intent = object()
    transitions.run = lambda now: (True, False)
    assert worker.update_transition() is False
    assert len(applied) == 1  # External admission is still authoritative.
