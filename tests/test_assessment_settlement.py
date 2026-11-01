"""Completed-take grading is independent of engine transitions."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.assessment_settlement import assess_completed_take
from piano_teacher.music import Phrase


PHRASE = Phrase(1, 1, 2, 0, 8, ())


class Policies:
    def __init__(self, *, projection_error=None):
        self.calls = []
        self.projection_error = projection_error
        self.result = SimpleNamespace(notes=(object(), object()), summary="two hits")

    def select(self, tempo):
        self.calls.append(("select", tempo))
        return self

    def grade(self, phrase, **kwargs):
        self.calls.append(("grade", phrase, kwargs))
        return self.result

    def project(self, result, phrase, **kwargs):
        self.calls.append(("project", result, phrase, kwargs))
        if self.projection_error is not None:
            raise self.projection_error
        return {"marks": [{"status": "correct"}], "unmapped": 1}


def run(policies, layout):
    return assess_completed_take(
        phrase=PHRASE, hand="right", bpm=85,
        played=[], from_beat=2, end_beat=8,
        tempo=None, policies=policies, layout_for_feedback=layout)


def test_grade_precedes_layout_lookup_and_uses_same_result_for_projection():
    policies = Policies()
    ordering = []

    def layout():
        ordering.append("layout")
        assert policies.calls[-1][0] == "grade"
        return {"notes": []}

    output = run(policies, layout)
    assert ordering == ["layout"]
    assert [c[0] for c in policies.calls] == ["select", "grade", "project"]
    assert policies.calls[1][2]["from_beat"] == 2
    assert policies.calls[1][2]["end_beat"] == 8
    assert policies.calls[2][3]["layout"] == {"notes": []}
    assert output.result is policies.result
    assert output.marks == [{"status": "correct"}]
    assert output.unmapped == 1
    assert output.feedback == "two hits"


@pytest.mark.parametrize("error", [
    RuntimeError("engraving unavailable"),
    ValueError("invalid layout"),
    KeyError("marks"),
])
def test_projection_failure_preserves_grading_and_unmapped_count(error):
    policies = Policies(projection_error=error)
    output = run(policies, lambda: {"notes": []})
    assert output.result is policies.result
    assert output.marks == []
    assert output.unmapped == 2
    assert output.feedback.startswith("Engraving feedback unavailable:")
    assert [c[0] for c in policies.calls] == ["select", "grade", "project"]


def test_layout_failure_is_reported_without_regrading():
    policies = Policies()
    def broken_layout():
        raise RuntimeError("renderer missing")
    output = run(policies, broken_layout)
    assert output.unmapped == 2
    assert [c[0] for c in policies.calls] == ["select", "grade"]


def test_grading_failure_propagates_before_layout_access():
    class Broken(Policies):
        def grade(self, *args, **kwargs):
            raise ValueError("invalid graded phrase")
    with pytest.raises(ValueError, match="graded phrase"):
        run(Broken(), lambda: pytest.fail("layout must not load"))
