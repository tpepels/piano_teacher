"""Invariants of the practice flow lesson state machine
(docs/architecture.md#practice-state-and-timing). Walks every transition."""
import itertools

import pytest

from piano_teacher.application import practice_flow as flow
from piano_teacher.application.practice_flow import Outcome, Step

TARGET = 80
FLOOR, STEP = flow.floor_bpm(TARGET), flow.step_bpm(TARGET)


def tempo(final=False):
    state = flow.enter_stage("s", final=final, target_bpm=TARGET).state
    if not final:
        state = flow.free_completed(flow.listen_finished(state).state).state
    return state


def test_a_stage_starts_listen_free_tempo_and_resume_starts_free():
    entry = flow.enter_stage("s", final=False, target_bpm=TARGET).state
    assert entry.step is Step.LISTEN and entry.bpm == TARGET
    free = flow.listen_finished(entry).state
    assert free.step is Step.FREE
    started = flow.free_completed(free).state
    assert started.step is Step.TEMPO and started.bpm == FLOOR
    assert flow.enter_stage("s", final=False, target_bpm=TARGET, resumed=True).state.step is Step.FREE
    final = flow.enter_stage("s", final=True, target_bpm=TARGET).state
    assert final.step is Step.TEMPO and final.bpm == FLOOR


def test_events_out_of_order_are_rejected():
    entry = flow.enter_stage("s", final=False, target_bpm=TARGET).state
    with pytest.raises(ValueError):
        flow.free_completed(entry)
    with pytest.raises(ValueError):
        flow.take_graded(entry, passed=True)
    with pytest.raises(ValueError):
        flow.listen_finished(tempo())


@pytest.mark.parametrize("final", (False, True))
def test_every_take_sequence_keeps_tempo_bounds_and_only_legal_steps(final):
    for results in itertools.product((True, False), repeat=7):
        state = tempo(final)
        clean_at_target_in_a_row = 0
        for passed in results:
            if state.step is not Step.TEMPO:
                break
            before = state
            t = flow.take_graded(state, passed=passed)
            state = t.state
            assert FLOOR <= state.bpm <= TARGET
            if passed:
                assert t.outcome in (Outcome.FASTER, Outcome.CLEAN_ONCE,
                                     Outcome.STAGE_DONE, Outcome.PIECE_DONE)
                assert state.bpm >= before.bpm
                clean_at_target_in_a_row = (clean_at_target_in_a_row + 1
                                            if before.bpm == TARGET else 0)
            else:
                clean_at_target_in_a_row = 0
                if state.step is Step.TEMPO:
                    assert state.bpm <= before.bpm
            if state.step is Step.DONE:
                # Done only after two clean takes in a row at the target.
                assert clean_at_target_in_a_row == 2
                assert t.outcome is (Outcome.PIECE_DONE if final else Outcome.STAGE_DONE)
            if state.step is Step.FREE:
                # Back to Free only from 50%, after two failures, never in the final test.
                assert not final and before.bpm == FLOOR and before.failures == 1
                assert state.free_returns == before.free_returns + 1


def test_tempo_steps_follow_the_owner_rules():
    state = tempo()
    t = flow.take_graded(state, passed=True)
    assert t.outcome is Outcome.FASTER and t.state.bpm == FLOOR + STEP
    once = flow.take_graded(t.state, passed=False)
    assert once.outcome is Outcome.AGAIN and once.state.bpm == FLOOR + STEP
    twice = flow.take_graded(once.state, passed=False)
    assert twice.outcome is Outcome.SLOWER and twice.state.bpm == FLOOR


def test_settled_state_counters_come_from_progress_and_step_from_outcome():
    previous = tempo()
    state = flow.settle(previous, Outcome.BACK_TO_FREE, stage_key="s", final=False,
                        bpm=FLOOR, target_bpm=TARGET, failures=0, clean=0)
    assert state.step is Step.FREE and state.free_returns == 1
    done = flow.settle(state, Outcome.STAGE_DONE, stage_key="s", final=False,
                       bpm=TARGET, target_bpm=TARGET, failures=0, clean=0)
    assert done.step is Step.DONE
