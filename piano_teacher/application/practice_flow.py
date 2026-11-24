"""Pure selected Practice Flow policy (docs/architecture.md#practice-state-and-timing).

These reducers calculate the next Listen/Free/Tempo step and the outcome
of one accepted, source-bound graded take. Durable BPM, failures, clean
passes and mastery belong to LearningPlan, not this stateless module.
PracticeFlowCourseSession only retains a transient phase keyed to the
installed lesson; this module never mutates or stores application state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

CLEAN_TAKES_AT_TARGET = 2
FAILURES_BEFORE_SLOWER = 2


class Step(str, Enum):
    LISTEN = "listen"
    FREE = "free"
    # Free on the announced simplified notes (second return to Free); it
    # earns no credit and returns to the original Free (docs/practice-flow.md).
    AID = "aid"
    TEMPO = "tempo"
    DONE = "done"


class Outcome(str, Enum):
    """What a graded Tempo take decided (stored in the course decision)."""
    AGAIN = "again"
    FASTER = "faster"
    CLEAN_ONCE = "clean_once"
    SLOWER = "slower"
    BACK_TO_FREE = "back_to_free"
    STAGE_DONE = "stage_done"
    PIECE_DONE = "piece_done"


@dataclass(frozen=True)
class FlowState:
    stage_key: str
    final: bool
    step: Step
    bpm: int
    target_bpm: int
    failures: int = 0
    clean_at_target: int = 0
    free_returns: int = 0

    @property
    def tempo_percent(self) -> int:
        return round(100 * self.bpm / self.target_bpm) if self.target_bpm else 100


@dataclass(frozen=True)
class Transition:
    state: FlowState
    message: str
    outcome: Outcome | None = None


def floor_bpm(target_bpm: int) -> int:
    """Tempo starts at half the target tempo and never goes below it."""
    return max(1, round(target_bpm * .5))


def step_bpm(target_bpm: int) -> int:
    """Tempo changes in steps of 10% of the target tempo."""
    return max(1, round(target_bpm * .1))


def _require(state: FlowState, *steps: Step) -> None:
    if state.step not in steps:
        raise ValueError(f"Practice flow: {state.step.value} cannot take this event")


def enter_stage(stage_key: str, *, final: bool, target_bpm: int,
                resumed: bool = False, hand_text: str = "") -> Transition:
    """A new phrase/link/hand starts with Listen; a resumed one warms up in
    Free; the final whole-piece test goes straight into Tempo at 50%."""
    floor = floor_bpm(target_bpm)
    if final and not resumed:
        return Transition(FlowState(stage_key, True, Step.TEMPO, floor, target_bpm),
                          "Whole piece · 50%")
    if resumed:
        return Transition(FlowState(stage_key, final, Step.FREE, target_bpm, target_bpm),
                          "Now without tempo")
    return Transition(FlowState(stage_key, False, Step.LISTEN, target_bpm, target_bpm),
                      f"Listen · {hand_text}" if hand_text else "Listen")


def listen_again(state: FlowState) -> Transition:
    """Listen again (button): play the passage at the target tempo, then Free."""
    return Transition(replace(state, step=Step.LISTEN, bpm=state.target_bpm), "Listen")


def listen_finished(state: FlowState) -> Transition:
    _require(state, Step.LISTEN)
    return Transition(replace(state, step=Step.FREE, bpm=state.target_bpm),
                      "Now without tempo")


def tempo_increase(target_bpm: int, *, quality: float, attacks: int) -> int:
    """How far one clean take below target raises the tempo (BPM).

    10% of target x (1 + timing quality) x length factor: well-timed takes
    climb faster, and short windows (few attacks) climb faster still, so
    two quarter notes do not need five takes to reach the target.
    """
    quality = min(1.0, max(0.0, quality))
    length = min(2.5, max(1.0, 8.0/max(1, attacks)))
    return max(1, round(target_bpm * .1 * (1.0+quality) * length))


def take_graded(state: FlowState, *, passed: bool, quality: float = 0.0,
                attacks: int = 8) -> Transition:
    """docs/practice-flow.md Tempo, one graded take."""
    _require(state, Step.TEMPO)
    floor, step = floor_bpm(state.target_bpm), step_bpm(state.target_bpm)
    if not passed:
        failures = state.failures + 1
        if failures < FAILURES_BEFORE_SLOWER:
            return Transition(replace(state, failures=failures, clean_at_target=0),
                              "Again at the same tempo", Outcome.AGAIN)
        if state.bpm > floor:
            bpm = max(floor, state.bpm - step)
            return Transition(replace(state, bpm=bpm, failures=0, clean_at_target=0),
                              f"Slower: {bpm} BPM", Outcome.SLOWER)
        if state.final:
            # The final test has no Free step; it stays at 50%.
            return Transition(replace(state, failures=0, clean_at_target=0),
                              "Again at the same tempo", Outcome.AGAIN)
        return Transition(replace(state, step=Step.FREE, bpm=state.target_bpm,
                                  failures=0, clean_at_target=0,
                                  free_returns=state.free_returns + 1),
                          "Once more without tempo", Outcome.BACK_TO_FREE)
    if state.bpm < state.target_bpm:
        bpm = min(state.target_bpm, state.bpm + tempo_increase(
            state.target_bpm, quality=quality, attacks=attacks))
        return Transition(replace(state, bpm=bpm, failures=0, clean_at_target=0),
                          f"Faster: {bpm} BPM", Outcome.FASTER)
    clean = state.clean_at_target + 1
    if clean < CLEAN_TAKES_AT_TARGET:
        return Transition(replace(state, failures=0, clean_at_target=clean),
                          "Clean! Once more", Outcome.CLEAN_ONCE)
    done = replace(state, step=Step.DONE, failures=0, clean_at_target=clean)
    if state.final:
        return Transition(done, "Piece mastered", Outcome.PIECE_DONE)
    return Transition(done, "Well done", Outcome.STAGE_DONE)


def settle(state: FlowState | None, outcome: Outcome, *, stage_key: str,
           final: bool, bpm: int, target_bpm: int, failures: int,
           clean: int) -> FlowState:
    """The engine's lesson state after a settled take decision. The counters
    come from the persisted course progress (one source); the step follows
    from the outcome."""
    step = (Step.FREE if outcome is Outcome.BACK_TO_FREE else
            Step.DONE if outcome in (Outcome.STAGE_DONE, Outcome.PIECE_DONE) else
            Step.TEMPO)
    returns = (state.free_returns if state is not None
               and state.stage_key == stage_key else 0)
    if outcome is Outcome.BACK_TO_FREE:
        returns += 1
    return FlowState(stage_key, final, step, int(bpm), int(target_bpm),
                     int(failures), int(clean), returns)
