"""Validated manual teaching requests and exact progress application.

The engine supplies facts under its lock; this owner never receives the engine
or a callback bag. Infrastructure acknowledgements do not create decisions.
"""
from dataclasses import dataclass
from contextlib import contextmanager
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

    @contextmanager
    def executing(self, effect):
        """Scope the original chosen effect while applying an authorization."""
        previous = self.active
        self.active = effect
        try:
            yield
        finally:
            self.active = previous

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
    def transition(effect, *, action: str, source_changed):
        from .playback_transitions import PlaybackTransition
        return PlaybackTransition.from_effect(
            effect,action=action,source_changed=source_changed)

    @staticmethod
    def start_route(effect, *, source_changed):
        # The same pure route planner serves graphical and direct/headless
        # command adapters. There is no second decision tree here.
        return SessionCommands.transition(
            effect,action="start",source_changed=source_changed).route
