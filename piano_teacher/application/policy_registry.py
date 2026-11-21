"""Current grading and learning policy instances selected by persisted settings.

The policy implementations retain sole grading and diagnosis authority.
This registry only swaps their configured instances after settings persist;
every client resolves the same current instances.
"""
from __future__ import annotations
from .practice_assessment import PracticeAssessmentPolicies
from ..practice_history import PracticePolicyService


class PolicyRegistry:
    def __init__(self, *, assessment, ledger, settings):
        self.assessment = assessment
        self.ledger = ledger
        self.grading = PracticeAssessmentPolicies.defaults(
            assessment, grade_note_holds=settings["grade_note_holds"])
        self.learning = PracticePolicyService(
            ledger, diagnosis=settings["diagnosis_strategy"],
            learner=settings["learner_strategy"])

    def apply_hold_rule(self, grade_note_holds: bool) -> None:
        self.grading = PracticeAssessmentPolicies.defaults(
            self.assessment, grade_note_holds=grade_note_holds)

    def apply_learning_rules(self, settings) -> None:
        self.learning = PracticePolicyService(
            self.ledger, diagnosis=settings["diagnosis_strategy"],
            learner=settings["learner_strategy"])
