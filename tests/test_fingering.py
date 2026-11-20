"""Real local inference and durable human corrections remain honest."""
import pytest

from piano_teacher.fingering import FingeringService, LumikeyProvider
from piano_teacher.music import Note, Piece


def piece(notes):
    return Piece("Fingerings", 100, tuple(notes), ())


@pytest.mark.usefixtures("lumikey_runtime")
def test_real_models_assign_playable_fingers_to_both_hands_and_respect_held_key():
    source = piece([Note(0, 2, pitch, i // 3, 0,
                         "left" if i < 3 else "right", f"n{i}")
                    for i, pitch in enumerate((48, 52, 55, 60, 64, 67))])
    result = LumikeyProvider().predict(source, {"n3": 2})
    assert set(result) == {n.source_id for n in source.notes}
    assert all(a.finger in range(1, 6) for a in result.values())
    assert len({result[f"n{i}"].finger for i in range(3)}) == 3
    assert len({result[f"n{i}"].finger for i in range(3, 6)}) == 3
    assert result["n3"].finger == 2
    overlap = piece([Note(0, 2, 60, 0, 0, "right", "held"),
                     Note(1, 2, 64, 0, 0, "right", "next"),
                     Note(1, 2, 67, 0, 0, "right", "chord")])
    held = LumikeyProvider().predict(overlap, {"held": 3})
    assert len({a.finger for a in held.values()}) == 3
    assert all(a.finger in range(1, 6) for a in held.values())


@pytest.mark.usefixtures("lumikey_runtime")
def test_six_simultaneous_keys_in_one_hand_remain_unknown():
    source = piece([Note(0, 1, 60 + i, 0, 0, "right", f"n{i}") for i in range(6)])
    result = LumikeyProvider().predict(source, {})
    assert all(a.finger is None and a.reason for a in result.values())


def test_unavailable_runtime_keeps_manual_correction_across_reopen_and_source_scope(tmp_path):
    source = piece([Note(0, 1, 60, 0, 0, "right", "note")])
    unavailable = LumikeyProvider(node="/missing/fingering-node")
    service = FingeringService(tmp_path, provider=unavailable)
    plan = service.prepare(source, "first-piece")
    assert plan.status == "unavailable" and plan.summary()["error"]
    assert plan.assignments["note"].finger is None
    service.correct(source, "first-piece", "note", 4)
    restored = FingeringService(tmp_path, provider=unavailable).prepare(source, "first-piece")
    assert restored.assignments["note"].finger == 4
    assert restored.assignments["note"].origin == "manual"
    assert service.prepare(source, "other-piece").assignments["note"].finger is None
    for finger in (0, 6, True, "3"):
        with pytest.raises(ValueError):
            service.correct(source, "first-piece", "note", finger)
    with pytest.raises(ValueError, match="Unknown"):
        service.correct(source, "first-piece", "other-note", 3)
    assert service.prepare(source, "first-piece").assignments["note"].finger == 4
    assert service.correct(source, "first-piece", "note", None).assignments["note"].finger is None


@pytest.mark.usefixtures("lumikey_runtime")
def test_disposable_plan_corruption_never_loses_saved_manual_correction(tmp_path):
    source = piece([Note(0, 1, 60, 0, 0, "right", "note")])
    failed = FingeringService(tmp_path, provider=LumikeyProvider(node="/missing/fingering-node"))
    assert failed.prepare(source, "piece").status == "unavailable"
    service = FingeringService(tmp_path)
    assert service.prepare(source, "piece").assignments["note"].finger in range(1, 6)
    service.correct(source, "piece", "note", 4)
    for path in tmp_path.glob("*/plan-*.json"):
        path.write_text("{broken")
    restored = FingeringService(tmp_path).prepare(source, "piece")
    assert restored.assignments["note"].finger == 4
    assert restored.assignments["note"].origin == "manual"
