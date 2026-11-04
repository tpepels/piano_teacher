"""Source-bound mistake responses: configurable, deterministic, no extra clocks."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from piano_teacher.application.mistake_responses import (
    MistakePolicy, RollingResponse, WholeResponse,
    available_mistake_policies, register_mistake_policy,
    resolve_mistake_policy, rolling_response, whole_response,
)
from piano_teacher.application.rolling_recovery import plan_rolling_recovery
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.library import ScoreLibrary
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.recovery import RecoveryDecision
from piano_teacher.server import PracticeEngine


def _decision():
    return RecoveryDecision(12.0, 4.0, 5, 2, 3)


def _rolling(name, previous_key=None, count=0, allow_guided=True):
    return plan_rolling_recovery(
        _decision(), identity="song:stage-one", bpm=100,
        previous_key=previous_key, previous_count=count,
        grid=(0.0, 4.0, 8.0, 12.0), first_bar=9,
        now=1000.0, strategy=name, allow_guided=allow_guided)


def test_all_six_strategies_are_registered_with_valid_user_labels():
    expected = {"adaptive", "steady-repeat", "slow-practice",
                "micro-loop", "guided-repair", "finish-then-review"}
    choices = available_mistake_policies()
    assert {c["id"] for c in choices} == expected
    assert all(c["label"] and c["description"] for c in choices)
    assert all("Coda" not in c["label"] for c in choices)
    with pytest.raises(ValueError, match="Unknown mistake-response"):
        resolve_mistake_policy("legacy-fallback")
    with pytest.raises(ValueError, match="Unknown mistake-response"):
        resolve_mistake_policy(None)
    with pytest.raises(FrozenInstanceError):
        resolve_mistake_policy("adaptive").focus_measures = 8


@pytest.mark.parametrize("strategy,bpm,start,guided", [
    ("adaptive", 90, 4.0, False),
    ("steady-repeat", 100, 4.0, False),
    ("slow-practice", 80, 4.0, False),
    ("micro-loop", 90, 8.0, False),
    ("guided-repair", 90, 4.0, True),
    ("finish-then-review", 100, 4.0, False),
])
def test_recovery_selection_keeps_real_bar_positions_and_expected_tempo(
        strategy, bpm, start, guided):
    selected = _rolling(strategy)
    assert selected.bpm == bpm
    assert selected.restart_beat == start
    assert selected.display.retry_range["start_beat"] == start
    assert selected.display.retry_range["first_bar"] == (
        10 if start == 4.0 else 11)
    assert selected.display.retry_range["last_bar"] == 11
    assert selected.display.notice["to_bpm"] == bpm
    assert selected.guided is guided
    assert selected.trouble_key == ("song:stage-one", start, 12.0)
    assert selected.mode == strategy


def test_guided_escalation_tracks_exact_source_and_never_overrides_explicit_block():
    baseline = _rolling("adaptive")
    second = _rolling("adaptive", previous_key=baseline.trouble_key, count=1)
    assert second.trouble_count == 2 and second.guided
    assert "Learn bars" in second.display.next_action
    assert not _rolling("adaptive", previous_key=baseline.trouble_key,
                        count=1, allow_guided=False).guided
    first_micro = _rolling("micro-loop")
    third_micro = _rolling("micro-loop", previous_key=first_micro.trouble_key, count=2)
    assert third_micro.guided
    assert not _rolling("steady-repeat", previous_key=baseline.trouble_key,
                        count=100).guided
    assert _rolling("micro-loop", previous_key=baseline.trouble_key,
                    count=20).trouble_count == 1


def test_no_rolling_interruptions_when_whole_phrase_review_is_chosen():
    assert not resolve_mistake_policy("finish-then-review").interrupt_rolling
    for mode in ("adaptive", "steady-repeat", "slow-practice",
                 "micro-loop", "guided-repair"):
        assert resolve_mistake_policy(mode).interrupt_rolling


def test_whole_take_response_is_metrical_and_never_credits_partial_recovery():
    phrase = SimpleNamespace(start=10.0, end=22.0)
    mistakes = (
        SimpleNamespace(note=SimpleNamespace(start=10.0), status="correct"),
        SimpleNamespace(note=SimpleNamespace(start=15.0), status="wrong"),
        SimpleNamespace(note=SimpleNamespace(start=19.0), status="missed"),
    )
    assessment = SimpleNamespace(notes=mistakes)
    grid = (0.0, 4.0, 8.0, 12.0)
    selected = whole_response(
        resolve_mistake_policy("micro-loop"), assessment,
        phrase=phrase, grid=grid, bpm=100, minimum_bpm=12,
        play_from_beat=0.0)
    assert selected.bpm == 90 and selected.restart_beat == 8.0
    slow = whole_response(
        resolve_mistake_policy("slow-practice"), assessment,
        phrase=phrase, grid=grid, bpm=100, minimum_bpm=12,
        play_from_beat=0.0)
    assert slow.bpm == 90 and slow.restart_beat == 0
    assert whole_response(
        resolve_mistake_policy("micro-loop"),
        SimpleNamespace(notes=()), phrase=phrase, grid=grid,
        bpm=12, minimum_bpm=12, play_from_beat=4.0).restart_beat == 4.0


def test_invalid_recovery_boundary_is_rejected_before_transport_mutation():
    with pytest.raises(ValueError, match="boundary"):
        rolling_response(
            resolve_mistake_policy("adaptive"),
            RecoveryDecision(11.0, 4.0, 5, 3, 2),
            identity="source", bpm=80, minimum_bpm=12,
            previous_key=None, previous_count=0,
            grid=(0.0, 4.0, 8.0, 12.0))
    with pytest.raises(ValueError, match="outside the source"):
        whole_response(
            resolve_mistake_policy("micro-loop"),
            SimpleNamespace(notes=(
                SimpleNamespace(note=SimpleNamespace(start=50.0),
                                status="wrong"),)),
            phrase=SimpleNamespace(start=40.0, end=60.0),
            grid=(0.0, 4.0), bpm=80, minimum_bpm=12,
            play_from_beat=0.0)


def _song():
    notes = (Note(0, .5, 60, 0, 0, "right", "a"),
             Note(1, 1.5, 62, 0, 0, "right", "b"),
             Note(2, 2.5, 64, 0, 0, "right", "c"),
             Note(3, 3.5, 65, 0, 0, "right", "d"))
    return Piece("Policy switch", 100, notes,
                 (Phrase(1, 1, 1, 0, 4, notes),),
                 bar_boundaries=(0, 4), time_signatures=((0, 4, 4),))


def test_live_setting_switch_is_atomic_persistent_and_keeps_current_take(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(_song(), exercise_strategy="source-progression")
        engine.fingerprint = "policy-fixture"
        engine.midi.port = object()
        engine.start()
        recorder = engine.recorder
        revision = engine.score_revision
        transport = engine.transport_id
        start = engine.visual_transport.run_at
        engine.set_preferences(mistake_response_strategy="finish-then-review")
        assert engine.library.settings["mistake_response_strategy"] == "finish-then-review"
        assert engine._state_snapshot()["mistake_response_strategy"] == "finish-then-review"
        assert not engine._assess_rolling_boundary(4.0, (0.0, 4.0))
        assert engine.recorder is recorder and engine.running
        assert engine.score_revision == revision
        assert engine.transport_id == transport
        assert engine.visual_transport.run_at == start
        with pytest.raises(ValueError, match="Unknown mistake-response"):
            engine.set_preferences(mistake_response_strategy="unregistered")
        assert engine.library.settings["mistake_response_strategy"] == "finish-then-review"
        loaded = ScoreLibrary(tmp_path / "config")
        assert loaded.settings["mistake_response_strategy"] == "finish-then-review"
    finally:
        engine.db.close()


def test_external_mistake_algorithm_registers_without_engine_changes(monkeypatch):
    from piano_teacher.application import mistake_responses as registry

    def choose_rolling(facts):
        return RollingResponse(
            restart_beat=8.0, end_beat=facts.decision.end_beat,
            bpm=max(facts.minimum_bpm, facts.bpm-7),
            guided=False, count=1,
            trouble_key=(facts.identity, 8.0, facts.decision.end_beat),
            mode="custom-pedagogy")

    def choose_whole(facts):
        return WholeResponse(
            bpm=facts.bpm, restart_beat=facts.play_from_beat,
            mode="custom-pedagogy")

    new = MistakePolicy(
        "custom-pedagogy", "Focused specialist", "Externally registered algorithm",
        True, 1.0, 1.0, 1, None,
        rolling_handler=choose_rolling, whole_handler=choose_whole)
    try:
        register_mistake_policy(new)
        assert resolve_mistake_policy(new.name) is new
        with pytest.raises(ValueError, match="Duplicate"):
            register_mistake_policy(new)
        result = _rolling(new.name)
        assert result.restart_beat == 8.0 and result.bpm == 93
        assert result.display.retry_range["start_beat"] == 8.0
        phrase = SimpleNamespace(start=0.0, end=12.0)
        again = whole_response(
            new, SimpleNamespace(notes=()), phrase=phrase,
            grid=(0.0,4.0,8.0,12.0),
            bpm=100, minimum_bpm=12, play_from_beat=0)
        assert again.bpm == 100 and again.restart_beat == 0
    finally:
        monkeypatch.delitem(registry._POLICIES, new.name, raising=False)


def test_external_algorithm_cannot_return_wrong_score_or_musical_deadline():
    policy = MistakePolicy(
        "invalid-source", "Broken", "Exercise contract verification",
        True, 1, 1, 1, None,
        rolling_handler=lambda facts: RollingResponse(
            3.0, facts.decision.end_beat, 99, False, 1,
            (facts.identity,3.0,facts.decision.end_beat), "invalid-source"),
        whole_handler=lambda facts: WholeResponse(
            facts.bpm, 100.0, "invalid-source"))
    with pytest.raises(ValueError, match="Invalid source-bound rolling"):
        rolling_response(
            policy, _decision(), identity="test", bpm=100,
            minimum_bpm=12, previous_key=None, previous_count=0,
            grid=(0.0,4.0,8.0,12.0))
    with pytest.raises(ValueError, match="Invalid source-bound whole"):
        whole_response(
            policy, SimpleNamespace(notes=()),
            phrase=SimpleNamespace(start=0.0,end=12.0),
            grid=(0.0,4.0,8.0,12.0),
            bpm=100, minimum_bpm=12, play_from_beat=0)
