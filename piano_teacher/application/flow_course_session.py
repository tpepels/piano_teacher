"""One owner for the Practice Flow step reducer and its UI projection.

The teaching reducer alone selects the next Exercise/PracticeWindow and its
assessment verdict. This owner applies the resulting typed flow outcome to
the selected stage, tracks the Listen/Free/Tempo display phase, and formats
status. It cannot change a LearningPlan or authorize a timed take.
"""
from __future__ import annotations
from dataclasses import dataclass

from ..application import practice_flow


@dataclass(frozen=True, slots=True)
class FlowStepEffect:
    step: practice_flow.Step
    bpm: int
    feedback: str = ""
    next_action: str = ""


class PracticeFlowCourseSession:
    def __init__(self, clock):
        self._clock = clock
        self._state: practice_flow.FlowState | None = None
        self._message: tuple[int, str, float] = (0, "", 0.0)

    @property
    def state(self) -> practice_flow.FlowState | None:
        return self._state

    @property
    def message(self) -> tuple[int, str, float]:
        return self._message

    def say(self, message: str) -> None:
        if not message:
            return
        sequence, previous, at = self._message
        now = self._clock()
        if previous and now-at < 0.5 and message not in previous:
            message = f"{previous} · {message}"
        self._message = (sequence+1,message,now)

    def execute(self, transition: practice_flow.Transition) -> FlowStepEffect:
        state = self.apply(transition)
        if state.step is practice_flow.Step.LISTEN:
            return FlowStepEffect(
                state.step,state.bpm,"Listen",
                "Listen to the passage and follow the notes.")
        if state.step is practice_flow.Step.FREE:
            return FlowStepEffect(
                state.step,state.bpm,"Now without tempo",
                "Play the notes in order, at your own pace.")
        return FlowStepEffect(state.step,state.bpm)

    def apply(self, transition: practice_flow.Transition) -> practice_flow.FlowState:
        self._state = transition.state
        self.say(transition.message)
        return self._state

    def enter(self, *, stage_key: str, final: bool, target_bpm: int,
              resumed: bool, hand_text: str) -> practice_flow.Transition:
        return practice_flow.enter_stage(
            stage_key,final=final,target_bpm=target_bpm,
            resumed=resumed,hand_text=hand_text)

    def listen_finished(self) -> practice_flow.Transition:
        if self._state is None:
            raise ValueError("No selected Practice Flow course")
        return practice_flow.listen_finished(self._state)

    def listen_again(self) -> practice_flow.Transition:
        if self._state is None:
            raise ValueError("No selected Practice Flow course")
        return practice_flow.listen_again(self._state)

    def free_completed(self) -> practice_flow.FlowState:
        if self._state is None:
            raise ValueError("No selected Practice Flow course")
        return self.apply(practice_flow.free_completed(self._state))

    def settle(self, outcome: practice_flow.Outcome, *, stage_key: str,
               final: bool, bpm: int, target_bpm: int, failures: int,
               clean: int, message: str) -> practice_flow.FlowState:
        if self._state is None:
            raise ValueError("No active Practice Flow stage to settle")
        self._state = practice_flow.settle(
            self._state,outcome,stage_key=stage_key,final=final,
            bpm=bpm,target_bpm=target_bpm,failures=failures,clean=clean)
        self.say(message)
        return self._state

    def status(self, plan, mode: str) -> dict:
        exercise = plan.exercise
        if exercise.kind == "perform":
            where = "Whole piece"
        else:
            first = exercise.phrase.first_bar
            last = exercise.phrase.last_bar
            where = (f"Measure {first}" if first == last
                     else f"Measures {first}–{last}")
        step = (self._state.step.value if self._state is not None
                and self._state.stage_key == plan.identity else
                "listen" if mode == "listen" else
                "free" if mode == "learn" else "tempo")
        if step == "done":
            step = "tempo"
        percent = round(100*plan.bpm/plan.target_bpm) if plan.target_bpm else 100
        label = {"listen":"Listen","free":"Without tempo",
                 "tempo":f"Tempo {percent}%"}[step]
        hand_text = {"right":"Right hand","left":"Left hand"}.get(
            plan.hand,"Both hands")
        sequence, message, _ = self._message
        return {"step":step,"where":where,"hand":plan.hand,
                "tempo_percent":percent,
                "status":f"{where} · {hand_text} · {label}",
                "message_id":sequence,"message":message}
