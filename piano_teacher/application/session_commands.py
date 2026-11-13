"""Validated manual teaching requests and exact progress application.

The engine supplies facts under its lock; this owner never receives the engine
or a callback bag. Infrastructure acknowledgements do not create decisions.
"""
from dataclasses import dataclass
from ..teaching_decisions import validate_teaching_decision


@dataclass(frozen=True, slots=True)
class CommandEffect:
    event: object
    state: object
    decision: object


class SessionCommands:
    def __init__(self):
        self.active = None
        self.applied = None
        self.prepared = None

    def prepare(self, *, event, state, generator):
        decision = generator.decide_teaching(event, state)
        validate_teaching_decision(decision, event=event, state=state)
        return CommandEffect(event, state, decision)

    def apply_progress(self, effect, *, plan):
        if self.applied is effect:
            return False
        plan.apply_teaching_progress(effect.decision.progress_after,
            definition=effect.decision.definition_after, expected=effect.decision.before_progress)
        self.applied = effect
        self.prepared = effect.decision.next_exposure
        return True

    @staticmethod
    def start_route(effect, *, source_changed):
        exposure = effect.decision.next_exposure
        if exposure.mode == "listen":
            return "listen"
        if effect.state.route.mode == "learn" and exposure.mode == "practice":
            return "prepare_practice"
        if source_changed:
            return "reload_score"
        return "rewind" if exposure.preparation == "rewind" else "start"
