"""Apply recovery decisions to the selected source, in two owners.

SelectedRecovery executes an already chosen policy response or remedial
assignment. It never chooses a policy.
"""
from __future__ import annotations
from ..music import Phrase
from ..remediation import RemedialAssignment
from ..lesson_settings import SETTINGS, course_rules
from .exposure_preparation import prepare_remedial, prepare_response
from .musical_scheduler import SCHEDULER


class SelectedRecovery:
    def __init__(self, *, lesson, notices, take, transport, transport_timing,
                 continuation, course, exposure_workflows, clock):
        self.lesson = lesson
        self.notices = notices
        self.take = take
        self.transport = transport
        self.transport_timing = transport_timing
        self.continuation = continuation
        self.course = course
        self.exposure_workflows = exposure_workflows
        self.clock = clock

    def _apply_prepared_recovery(self, prepared, *, now: float,
                                 deadline: float | None = None,
                                 visual_from: float | None = None,
                                 exposure=None) -> None:
        """Execute one source-bound recovery effect, without choosing a policy.

        Both selected whole-response and remedial effects share the same
        cursor, attempt, transport and notice writer. An untimed remedial
        selection prepares a new bounded take; an untimed whole-response
        schedules the original source's normal retry. Guided remediation
        keeps its note-isolation controller without overwriting the active
        timed-retry context.
        """
        if prepared.action not in ("pause", "guided", "continue", "prepare"):
            raise ValueError("Unknown selected recovery action")
        if prepared.action == "continue" and deadline is None:
            raise ValueError("Timed recovery requires a selected deadline")
        if prepared.action == "guided" and prepared.assignment is not None:
            self.course.begin_learn(
                from_beat=prepared.start, recovery=True,
                remediation=prepared.assignment, exposure=exposure)
        else:
            if prepared.action == "prepare" and prepared.assignment is not None:
                self.exposure_workflows.prepare_practice(exposure=exposure)
                self.transport.wait_for_player()
            self.lesson.select_opening(prepared.start)
            self.take.prepare_recovery(prepared)
            if prepared.action == "pause":
                self.transport.halt_continuation()
            elif prepared.action == "guided":
                self.course.begin_learn(
                    from_beat=prepared.start, recovery=True,
                    exposure=self.take.pending.decision.next_exposure)
            elif prepared.action == "continue":
                self.continuation.continue_measured(
                    deadline, from_beat=prepared.start)
            elif prepared.action == "prepare":
                if prepared.assignment is None:
                    self.transport_timing.schedule_preparation(
                        prepared.start, now=now,
                        from_visual=(self.transport_timing.visual_motion(now)[0]
                                     if visual_from is None else visual_from),
                        reverse_seconds=SETTINGS.feedback_seconds)
            else:
                raise ValueError("Unknown selected recovery action")
        if prepared.feedback:
            self.notices.feedback = prepared.feedback
        if prepared.next_action:
            self.notices.next_action = prepared.next_action

    def apply_policy_response(self, response, *, now: float,
                              deadline: float | None = None,
                              visual_from: float | None = None):
        prepared = prepare_response(
            response,
            source_duration=(self.lesson.plan.active_phrase.end
                             - self.lesson.plan.active_phrase.start),
            has_deadline=deadline is not None)
        self._apply_prepared_recovery(
            prepared, now=now, deadline=deadline, visual_from=visual_from)

    def start_remedial_assignment(self, assignment: RemedialAssignment,
                                  *, deadline: float | None = None,
                                  exposure=None) -> None:
        if self.lesson.plan is None:
            raise ValueError("Remediation requires an installed lesson source")
        prepared = prepare_remedial(
            self.exposure_workflows.source(), assignment, exposure,
            has_deadline=deadline is not None,
            automatic=self.transport.auto)
        if prepared is None:
            raise ValueError("Remediation belongs to a superseded source stage")
        self._apply_prepared_recovery(
            prepared, now=self.clock(), deadline=deadline, exposure=exposure)
