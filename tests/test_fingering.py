"""Real local inference and durable human corrections remain honest."""
from pathlib import Path
import shlex
import shutil

import pytest

from piano_teacher.fingering import FingeringService, LumikeyProvider
from piano_teacher.music import Note, Piece, load_midi


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
def test_delayed_provider_receives_the_whole_piece(tmp_path):
    source = load_midi(Path(__file__).parents[1] / "midi" / "Moonlight_Sonata_I.midi")
    node = shlex.quote(shutil.which(LumikeyProvider().node))
    delayed = tmp_path / "delayed-node"
    delayed.write_text(f'#!/bin/sh\nsleep .15\nexec {node} "$@"\n')
    delayed.chmod(0o700)
    result = LumikeyProvider(node=str(delayed), timeout=10).predict(source, {})
    assert set(result) == {note.source_id for note in source.notes}
    assert all(any(result[note.source_id].finger for note in source.notes if note.hand == hand)
               for hand in ("left", "right"))


@pytest.mark.usefixtures("lumikey_runtime")
@pytest.mark.parametrize("hand,pitches", [
    ("right", (61, 63, 65, 67, 69, 72)),
    ("left", (48, 50, 53, 55, 61, 63)),
])
def test_six_keys_with_adjacent_thumb_pair_are_playable(hand, pitches):
    source = piece([Note(0, 1, pitch, 0, 0, hand, f"n{i}")
                    for i, pitch in enumerate(pitches)])
    result = LumikeyProvider().predict(source, {})
    assert all(a.finger in range(1, 6) for a in result.values())
    assert [result[f"n{i}"].finger for i in range(6)] == (
        [1, 1, 2, 3, 4, 5] if hand == "right" else [5, 4, 3, 2, 1, 1])
    fixed = {"n0": 1, "n1": 1} if hand == "right" else {"n4": 1, "n5": 1}
    corrected = LumikeyProvider().predict(source, fixed)
    assert all(corrected[k].finger == v and not corrected[k].reason for k, v in fixed.items())


@pytest.mark.usefixtures("lumikey_runtime")
def test_impossible_fixed_thumb_does_not_erase_unrelated_note():
    source = piece([Note(0, 2, 60, 0, 0, "right", "held"),
                    Note(1, 1, 62, 0, 0, "right", "conflict"),
                    Note(1, 1, 67, 0, 0, "right", "playable")])
    result = LumikeyProvider().predict(source, {"held": 1, "conflict": 1})
    assert result["conflict"].finger == 1 and result["conflict"].reason
    assert result["playable"].finger in range(2, 6)
    assert not result["playable"].reason


@pytest.mark.usefixtures("lumikey_runtime")
def test_mixed_height_thumb_pair_is_not_automatically_shared():
    source = piece([Note(0, 1, pitch, 0, 0, "right", f"n{i}")
                    for i, pitch in enumerate((60, 61, 64, 65, 67, 69))])
    result = LumikeyProvider().predict(source, {})
    assert any(a.finger is None and a.reason for a in result.values())
    assert sum(a.finger is not None for a in result.values()) <= 5


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
