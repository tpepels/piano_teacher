"""Route precedence protects bounded work and recovery from granting mastery."""
import pytest
from piano_teacher.completion_route import completion_route


@pytest.mark.parametrize(("mode", "review_end", "offset", "expected"), [
    ("perform", None, 0, "perform"),
    ("perform", 4, 2, "perform"),
    ("practice", 4, 0, "section_review"),
    ("practice", 4, 2, "section_review"),
    ("practice", None, 0, "full_passage"),
    ("practice", None, 1e-7, "full_passage"),
    ("practice", None, 2, "partial_recovery"),
])
def test_completion_routes(mode, review_end, offset, expected):
    assert completion_route(mode, review_end, offset) == expected
