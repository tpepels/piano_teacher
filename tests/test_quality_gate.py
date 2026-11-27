"""Regression checks for the diagnostic comparison in the quality gate."""

from scripts.quality_gate import Finding, regressions


def finding(line=1, path="example.py", message="unused import"):
    return Finding(path, line, "F401", message)


def test_existing_diagnostic_may_move_without_becoming_new():
    assert regressions([finding()], [finding(line=20)]) == []


def test_duplicate_diagnostic_increases_debt():
    added = finding(line=2)
    assert regressions([finding()], [finding(), added]) == [added]


def test_new_file_and_changed_message_are_not_grandfathered():
    other = finding(path="new.py")
    changed = finding(message="different import")
    assert regressions([finding()], [other, changed]) == [other, changed]


def test_removed_diagnostic_does_not_fail():
    assert regressions([finding()], []) == []
