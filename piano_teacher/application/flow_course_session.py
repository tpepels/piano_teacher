"""One owner for the Practice Flow step reducer and its UI projection.

The teaching reducer alone selects the next Exercise/PracticeWindow and its
assessment verdict. This owner applies the resulting typed flow outcome to
the selected stage, tracks the Listen/Free/Tempo display phase, and formats
status. It cannot change a LearningPlan or authorize a timed take.
"""
from __future__ import annotations
from dataclasses import dataclass, replace

from ..application import practice_flow


@dataclass(frozen=True, slots=True)
class FlowStepEffect:
    step: practice_flow.Step
    feedback: str = ""
    next_action: str = ""


@dataclass(frozen=True, slots=True)
class FlowTempoEntry:
    active: bool
    clear_guided_return: bool = False


@dataclass(frozen=True, slots=True)
class FlowPhase:
    """Only the ungraded Listen/Free/Tempo phase is transient UI state."""
    stage_key: str
    final: bool
    step: practice_flow.Step


class PracticeFlowCourseSession:
    def __init__(self, clock, source_identity):
        self._clock = clock
        self._source_identity = source_identity
        self._phase: FlowPhase | None = None
        self._message: tuple[int, str, float] = (0, "", 0.0)
        self._settled_decision_id: str | None = None

    @property
    def state(self) -> practice_flow.FlowState | None:
        """Project progress from the canonical LearningPlan, never cache it.

        A stage's transient Listen/Free/Tempo display phase is the only
        independently retained state. All BPM, failures, clean runs and
        returns-to-Free are owned by the already persisted lesson course.
        """
        phase = self._phase
        plan = self._source_identity.plan
        if phase is None or plan is None:
            return None
        progress = plan.teaching_progress()
        return practice_flow.FlowState(
            phase.stage_key,phase.final,phase.step,
            int(plan.bpm),int(plan.target_bpm),
            failures=progress.failures,clean_at_target=progress.streak,
            free_returns=dict(progress.free_returns).get(phase.stage_key,0))

    @property
    def message(self) -> tuple[int, str, float]:
        return self._message

    @staticmethod
    def active(plan, *, warmup: bool) -> bool:
        return (plan is not None and not warmup
                and plan.lesson_definition.generator_name == "practice-flow")

    def stage_entry(self, plan, *, resumed: bool = False) -> practice_flow.Transition:
        return self.enter(stage_key=plan.identity,
            final=plan.exercise.kind == "perform",target_bpm=int(plan.target_bpm),
            resumed=resumed,hand_text={"right":"Right hand","left":"Left hand"}.get(
                plan.hand,"Both hands"))

    def opening(self, plan, *, resumed: bool = False) -> practice_flow.Transition:
        """A fresh course starts in Listen; a saved window warms up in Free."""
        return self.stage_entry(plan,resumed=resumed)

    def guided_entry(self, plan, *, warmup: bool, recovery: bool,
                     simplified: bool) -> practice_flow.Transition | None:
        """A new source window/hand enters its course step before Free binds."""
        if (self.active(plan,warmup=warmup) and not recovery and not simplified
                and (self._phase is None or self._phase.stage_key != plan.identity)):
            # Explicit Learn requests Free, including for the whole-piece
            # final. Automatic final entry uses its timed exposure directly.
            # Selecting Tempo here would conflict with the already selected
            # manual Learn exposure and start a take without guided targets.
            return self.stage_entry(plan,resumed=plan.exercise.kind == "perform")
        return None

    def tempo_entry(self, plan, *, warmup: bool, bpm: int) -> FlowTempoEntry:
        active = self.active(plan,warmup=warmup)
        if (active and self._phase is not None and self._phase.stage_key == plan.identity
                and self._phase.step is practice_flow.Step.FREE):
            progress = plan.teaching_progress()
            state = replace(self.state,step=practice_flow.Step.TEMPO,bpm=int(bpm),
                failures=progress.failures,clean_at_target=progress.streak)
            self.apply(practice_flow.Transition(
                state,f"Now in tempo · {state.tempo_percent}%"))
            return FlowTempoEntry(True,True)
        return FlowTempoEntry(active)

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
                state.step,"Listen",
                "Listen to the passage and follow the notes.")
        if state.step is practice_flow.Step.FREE:
            return FlowStepEffect(
                state.step,"Now without tempo",
                "Play the notes in order, at your own pace.")
        return FlowStepEffect(state.step)

    def apply(self, transition: practice_flow.Transition) -> practice_flow.FlowState:
        self._phase = FlowPhase(
            transition.state.stage_key,transition.state.final,
            transition.state.step)
        self.say(transition.message)
        return self.state

    def enter(self, *, stage_key: str, final: bool, target_bpm: int,
              resumed: bool, hand_text: str) -> practice_flow.Transition:
        return practice_flow.enter_stage(
            stage_key,final=final,target_bpm=target_bpm,
            resumed=resumed,hand_text=hand_text)

    def listen_finished(self) -> practice_flow.Transition:
        state = self.state
        if state is None:
            raise ValueError("No selected Practice Flow course")
        return practice_flow.listen_finished(state)

    def listen_again(self) -> practice_flow.Transition:
        state = self.state
        if state is None:
            raise ValueError("No selected Practice Flow course")
        return practice_flow.listen_again(state)

    def settle_decided(self, outcome: practice_flow.Outcome, *,
                       plan, message: str, decision_id: str | None = None
                       ) -> practice_flow.FlowState:
        """Only the course session may resolve the continuing stage label.

        A completed stage retains its previous identity until a new
        Listen/Free/Tempo entry is actually selected; a current-stage result
        follows the already-committed LearningPlan progression.
        """
        if decision_id is not None and decision_id == self._settled_decision_id:
            return self.state
        progress = plan.teaching_progress()
        done = outcome in (practice_flow.Outcome.STAGE_DONE,
                           practice_flow.Outcome.PIECE_DONE)
        stage_key = (self._phase.stage_key
                     if done and self._phase is not None else plan.identity)
        self.settle(
            outcome,stage_key=stage_key,
            final=plan.exercise.kind == "perform",
            bpm=int(plan.bpm),target_bpm=int(plan.target_bpm),
            failures=progress.failures,clean=progress.streak,message=message)
        self._settled_decision_id = decision_id
        return self.state

    def settle(self, outcome: practice_flow.Outcome, *, stage_key: str,
               final: bool, bpm: int, target_bpm: int, failures: int,
               clean: int, message: str) -> practice_flow.FlowState:
        current = self.state
        if current is None:
            raise ValueError("No active Practice Flow stage to settle")
        projected = practice_flow.settle(
            current,outcome,stage_key=stage_key,final=final,
            bpm=bpm,target_bpm=target_bpm,failures=failures,clean=clean)
        self._phase = FlowPhase(
            projected.stage_key,projected.final,projected.step)
        self.say(message)
        return self.state

    def status(self, plan, mode: str) -> dict:
        exercise = plan.exercise
        if exercise.kind == "perform":
            where = "Whole piece"
        else:
            first = exercise.phrase.first_bar
            last = exercise.phrase.last_bar
            where = (f"Measure {first}" if first == last
                     else f"Measures {first}–{last}")
        step = (self._phase.step.value if self._phase is not None
                and self._phase.stage_key == plan.identity else
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
