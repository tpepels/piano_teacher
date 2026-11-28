"""Tests use artificial ratings only; no human evidence is generated."""
import importlib.util
from pathlib import Path
import copy
import pytest

SPEC = importlib.util.spec_from_file_location("d0_pilot",
    Path(__file__).resolve().parents[1]/"docs/difficulty-research/pilot.py")
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)
PLAN = pilot.load(pilot.HERE/"pilot-plan.json")


def fixture():
    packet = {"plan_digest": pilot.digest(PLAN), "units": [{"unit_id": str(i)} for i in range(40)]}
    packet["packet_id"] = pilot.digest(packet)
    sheets = []
    for r in range(3):
        rows = []
        for i in range(40):
            row = dict(packet_id=packet["packet_id"], unit_id=str(i), rater_id=str(r),
                       rater_background="artificial unit test", judgment_mode="score",
                       severity="0" if i < 20 else "3", confidence="high", evidence="test")
            row.update({c: "absent" if i < 20 else "present" for c in pilot.CATEGORIES})
            rows.append(row)
        sheets.append(rows)
    return packet, sheets


def test_ordinal_alpha_known_extremes():
    assert pilot.ordinal_alpha([[0,0,0],[3,3,3]]) == 1
    assert pilot.ordinal_alpha([[1,1,1],[1,1]]) is None
    assert pilot.ordinal_alpha([[0,3],[0,3]]) == pytest.approx(-0.5)
    assert pilot.ordinal_alpha([[0,0],[3,3,3],[]]) == 1


def test_perfect_artificial_pilot_does_not_certify_d0():
    packet,sheets = fixture()
    result = pilot.agreement(packet,sheets,PLAN)
    assert result["pilot_status"] == "pass"
    assert result["d0_status"].startswith("requires")
    assert result["metrics"]["ordinal_alpha"] == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate_rater", "wrong_packet", "blank"])
def test_invalid_evidence_rejected(fault):
    packet,sheets = fixture()
    if fault == "missing":
        sheets[0].pop()
    elif fault == "duplicate_rater":
        for row in sheets[1]:
            row["rater_id"]="0"
    elif fault == "wrong_packet":
        sheets[0][0]["packet_id"]="stale"
    else:
        sheets[0][0]["severity"]=""
    with pytest.raises(ValueError):
        pilot.agreement(packet,sheets,PLAN)


def test_unknown_and_absent_are_not_equivalent():
    packet,sheets = fixture()
    for sheet in sheets:
        for row in sheet:
            row["severity"]="unknown"
            row.update({c:"unknown" for c in pilot.CATEGORIES})
    result=pilot.agreement(packet,sheets,PLAN)
    assert result["pilot_status"]=="open"
    assert result["metrics"]["ordinal_alpha"] is None
    assert result["metrics"]["severity_coverage"]==0


def test_tampered_packet_rejected():
    packet,sheets=fixture()
    packet["units"][0]["unit_id"]="changed"
    with pytest.raises(ValueError, match="identity"):
        pilot.agreement(packet,sheets,PLAN)
