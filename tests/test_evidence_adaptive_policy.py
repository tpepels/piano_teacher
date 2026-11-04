"""Source-bound deterministic decisions, not evidence of teaching effectiveness."""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from piano_teacher.application.mistake_responses import (
    AdaptiveAttempt, AdaptiveContext, adaptive_attempt_from_assessment,
    resolve_mistake_policy, whole_response, rolling_response,
)
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.music import Note
from piano_teacher.recovery import RecoveryDecision

GRID = (0., 4., 7., 11., 15.)
IDENTITY = "piece:stage:both:rules-v1"


def trial(*, wrong=(), missed=(), start=0., end=15., bpm=100, accepted=False,
          timing=0, hold=0, assisted=False, action="repeat", identity=IDENTITY):
    return AdaptiveAttempt(identity, start, end, bpm, tuple(wrong), tuple(missed),
        timing, hold, accepted, assisted=assisted, action=action)


def choose(*attempts, count=0, density=1., bpm=100, start=0., reference=100):
    context = AdaptiveContext(IDENTITY, tuple(attempts), count, 0., 15.,
        source_attacks=12, attacks_per_beat=density, reference_bpm=reference)
    return whole_response(resolve_mistake_policy("evidence-adaptive"),
        SimpleNamespace(notes=(), passed=False), phrase=SimpleNamespace(start=20., end=35., notes=()),
        grid=GRID, bpm=bpm, minimum_bpm=12, play_from_beat=start, context=context)


def test_first_failure_repeats_current_tempo_and_missing_history_has_safe_fallback():
    result = choose(trial(wrong=(4., 5.)))
    assert (result.action, result.bpm, result.restart_beat, result.end_beat) == ("repeat", 100, 0., 15.)
    missing = whole_response(resolve_mistake_policy("evidence-adaptive"), SimpleNamespace(notes=()),
        phrase=SimpleNamespace(start=0., end=15., notes=()), grid=GRID,
        bpm=100, minimum_bpm=12, play_from_beat=0.)
    assert missing.action == "repeat" and missing.reason == "insufficient_comparable_evidence"


def test_repeated_cluster_uses_authored_three_beat_measure_not_fixed_four_beats():
    result = choose(trial(wrong=(4., 5.)), trial(missed=(6.,)))
    assert (result.action, result.restart_beat, result.end_beat, result.bpm) == ("isolate", 4., 7., 100)
    assert not result.guided


def test_scattered_pitch_errors_do_not_infer_tempo_problem_or_arbitrary_focus():
    result = choose(trial(wrong=(0., 4., 7.)), trial(wrong=(1., 5., 11.)))
    assert result.action == "repeat" and result.bpm == 100 and result.end_beat == 15.


def test_persistent_timing_load_uses_native_difficulty_and_actual_independent_errors():
    attempts = (trial(timing=4), trial(timing=3))
    assert choose(*attempts, density=3.).action == "slow"
    assert choose(*attempts, density=.25).action == "repeat"
    assert choose(*attempts, density=3.).bpm == 90


def test_two_failed_focused_attempts_slow_and_two_failures_at_slow_setting_offer_guidance():
    focused = (trial(wrong=(4.,), start=4., end=7., action="isolate"),
               trial(missed=(5.,), start=4., end=7.))
    assert choose(*focused, start=4.).action == "slow"
    slow = (trial(wrong=(4.,), start=4., end=7., bpm=90, action="slow"),
            trial(missed=(5.,), start=4., end=7., bpm=90))
    result = choose(*slow, bpm=90, start=4.)
    assert result.action == "guided" and result.guided and result.bpm == 90


def test_guidance_success_requires_unsupported_timed_retry_before_reintegration():
    result = choose(trial(start=4., end=7., accepted=True, assisted=True, action="guided"), start=4.)
    assert result.action == "isolate" and not result.guided and result.end_beat == 7.


def test_two_clean_focused_outcomes_expand_context_and_recover_only_known_episode_tempo():
    attempts = (trial(start=4., end=7., bpm=80, accepted=True),
                trial(start=4., end=7., bpm=80, accepted=True))
    result = choose(*attempts, bpm=80, start=4., reference=90)
    assert (result.action, result.restart_beat, result.end_beat, result.bpm) == ("reintegrate", 0., 11., 85)
    assert not result.guided
    # Warnings accepted by mastery are not strict clean focused outcomes.
    assert choose(attempts[0], trial(start=4., end=7., bpm=80, accepted=True, timing=1),
        bpm=80, start=4., reference=90).action == "repeat"


def test_foreign_identity_tempo_or_assisted_history_cannot_trigger_focus():
    for old in (trial(wrong=(4., 5.), identity="other-source"),
                trial(wrong=(4., 5.), bpm=80), trial(wrong=(4., 5.), assisted=True)):
        result = choose(old, trial(missed=(6.,)))
        assert result.action == "repeat"


def test_twelve_corrective_actions_pause_with_no_extra_slowdown():
    result = choose(trial(wrong=(4., 5.)), trial(missed=(6.,)), count=12)
    assert result.action == "pause" and result.bpm == 100 and not result.guided


def test_rolling_inadequate_evidence_continues_without_a_tempo_change():
    result = rolling_response(resolve_mistake_policy("evidence-adaptive"),
        RecoveryDecision(11., 7., 5, 3, 2), identity=IDENTITY,
        bpm=100, minimum_bpm=12, previous_key=None, previous_count=0, grid=GRID)
    assert result.action == "continue" and result.bpm == 100 and not result.guided


def test_assessment_adapter_retains_actual_source_positions_and_independent_flags():
    note = Note(25., 26., 60, 0, 0, "right", "source-note")
    observation = SimpleNamespace(timing_error="late", hold_error="short")
    assessed = Assessment((NoteAssessment(note, "wrong", 61, observation),), 0)
    attempt = adaptive_attempt_from_assessment(assessed, identity=IDENTITY,
        start_beat=4., end_beat=7., bpm=100, phrase_start=20.)
    assert attempt.wrong_beats == (5.,) and attempt.timing_errors == 1 and attempt.hold_errors == 1
    assert attempt.accepted is False
    with pytest.raises(FrozenInstanceError):
        attempt.bpm = 50


def test_invalid_history_cannot_supply_outside_source_error_beats():
    with pytest.raises(ValueError):
        trial(wrong=(25.,))


def test_rolling_repeated_cluster_can_interrupt_at_its_authored_boundary_and_success_resets_pattern():
    prior = trial(wrong=(4., 5.))
    current = trial(missed=(6.,), end=7.)
    policy = resolve_mistake_policy("evidence-adaptive")
    def rolling(history):
        return rolling_response(policy, RecoveryDecision(7., 4., 5, 3, 2),
            identity=IDENTITY, bpm=100, minimum_bpm=12, previous_key=None,
            previous_count=0, grid=GRID, context=AdaptiveContext(IDENTITY, history, original_end_beat=15.))
    result = rolling((prior, current))
    assert result.action == "isolate" and result.restart_beat == 4. and result.end_beat == 7.
    assert rolling((prior, trial(accepted=True), current)).action == "continue"
    assert rolling((prior, trial(assisted=True), current)).action == "continue"


def test_minimum_tempo_never_underflows_and_full_accepted_outcome_uses_normal_progression():
    slowed = choose(trial(start=4., end=7., bpm=12, wrong=(4.,)),
                    trial(start=4., end=7., bpm=12, wrong=(5.,)), bpm=12, start=4.)
    assert slowed.action == "slow" and slowed.bpm == 12
    accepted = choose(trial(accepted=True))
    assert accepted.action == "continue" and accepted.bpm == 100


def test_reintegration_requires_same_unsupported_tempo_and_never_uses_a_future_target():
    first = trial(start=4., end=7., bpm=80, accepted=True)
    assert choose(first, trial(start=4., end=7., bpm=85, accepted=True),
        bpm=85, start=4.).action == "repeat"
    result = choose(first, first, bpm=80, start=4., reference=None)
    assert result.action == "reintegrate" and result.bpm == 80


def test_invalid_external_decisions_cannot_speed_up_an_ordinary_retry_or_leave_source_grid():
    from piano_teacher.application.mistake_responses import MistakePolicy, WholeResponse
    def evaluate(response):
        custom = MistakePolicy("external-invalid", "External", "Explicit contract", True,
            1., 1., 1, None, whole_handler=lambda facts: response)
        return whole_response(custom, SimpleNamespace(notes=()),
            phrase=SimpleNamespace(start=0., end=15.), grid=GRID,
            bpm=80, minimum_bpm=12, play_from_beat=0.)
    with pytest.raises(ValueError, match="Invalid source-bound"):
        evaluate(WholeResponse(100, 0., "external-invalid", end_beat=15., action="repeat"))
    with pytest.raises(ValueError, match="Invalid source-bound"):
        evaluate(WholeResponse(80, 0., "external-invalid", end_beat=6., action="isolate"))


def test_complete_graduated_episode_reaches_unsupported_original_target_within_action_bound():
    history = []
    actions = []
    stage = dict(start=0., end=15., bpm=100, action="repeat")
    observations = [dict(wrong=(4., 5.)), dict(missed=(6.,)),
                    dict(wrong=(4.,)), dict(missed=(5.,)),
                    dict(wrong=(4.,)), dict(missed=(5.,)),
                    dict(accepted=True, assisted=True), dict(accepted=True),
                    dict(accepted=True), dict(accepted=True), dict(accepted=True), dict(accepted=True)]
    for observation in observations:
        history.append(trial(**stage, **observation))
        response = choose(*history, count=len(actions), bpm=stage["bpm"], start=stage["start"], reference=100)
        if response.action != "continue":
            actions.append(response.action)
        stage = dict(start=response.restart_beat, end=response.end_beat, bpm=response.bpm, action=response.action)
    assert actions == ["repeat", "isolate", "repeat", "slow", "repeat", "guided",
                       "isolate", "repeat", "reintegrate", "repeat", "reintegrate"]
    assert response.action == "continue"
    assert (stage["start"], stage["end"], stage["bpm"]) == (0., 15., 100)
    assert len(actions) == 11 and not response.guided


def test_sustain_expanded_focus_that_is_still_full_target_does_not_repeat_isolation_forever():
    result = choose(trial(wrong=(4., 5.)), trial(missed=(6.,)),
                    trial(wrong=(4., 5.), action="isolate"))
    assert result.action == "slow" and result.bpm == 90


def test_rolling_context_cannot_borrow_assessment_from_beyond_current_boundary():
    result = rolling_response(resolve_mistake_policy("evidence-adaptive"),
        RecoveryDecision(7., 4., 5, 3, 2), identity=IDENTITY, bpm=100,
        minimum_bpm=12, previous_key=None, previous_count=0, grid=GRID,
        context=AdaptiveContext(IDENTITY, (trial(wrong=(4., 5.)), trial(missed=(6.,))), original_end_beat=15.))
    assert result.action == "continue" and result.bpm == 100


def test_concentration_threshold_keeps_exact_sixty_percent_and_sparse_evidence_explicit():
    exact = choose(trial(wrong=(0., 4., 5.)), trial(missed=(1., 6.)))
    assert exact.action == "isolate" and exact.restart_beat == 4.
    below = choose(trial(wrong=(0., 4., 5.)), trial(missed=(1., 6., 11.)))
    assert below.action == "repeat"
    sparse = choose(trial(wrong=(4.,)), trial(missed=(5.,)))
    assert sparse.action == "repeat"
