"""Enter the aid that Practice Flow selected (docs/practice-flow.md:
the second return to Free announces one real Coda/Fukuda simplification).
SelectedRecovery executes that decision; it never chooses one."""
from __future__ import annotations
from ..remediation import RemedialAssignment
from .exposure_preparation import prepare_remedial


class SelectedRecovery:
    def __init__(self, *, lesson, notices, course, exposure_workflows):
        self.lesson = lesson
        self.notices = notices
        self.course = course
        self.exposure_workflows = exposure_workflows

    def start_remedial_assignment(self, assignment: RemedialAssignment,
                                  *, exposure=None) -> None:
        """Enter Free with the announced aid (second return to Free)."""
        if self.lesson.plan is None:
            raise ValueError("Remediation requires an installed lesson source")
        assignment = prepare_remedial(
            self.exposure_workflows.source(), assignment, exposure)
        if assignment is None:
            raise ValueError("Remediation belongs to a superseded source stage")
        self.course.begin_learn(from_beat=assignment.start_beat, recovery=True,
                                remediation=assignment, exposure=exposure)
        self.notices.feedback = "Reviewing recurring pitch mistakes"
