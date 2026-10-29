"""Guided mode owns source fragments and the lifetime of physical key state."""
import importlib
from dataclasses import FrozenInstanceError

import pytest

from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Note, Phrase


def selected():
    module = importlib.import_module("piano_teacher.application.guided_session")
    notes = (Note(7, 16, 60, 0, 0, "right", "source-A"),
             Note(15, 16, 64, 0, 0, "right", "source-B"))
    variant = ExerciseVariant("original", Phrase(1, 1, 6, 0, 20, notes), (3, 9))
    fragment = module.select_fragment(variant, (0, 3, 6, 10, 14, 18, 20), from_beat=0)
    return module, fragment


def test_fragment_skips_empty_ideas_and_keeps_exact_source_attacks_and_held_endings():
    _, fragment = selected()
    assert fragment.beat_range == (6, 14)
    assert fragment.phrase == Phrase(1, 3, 4, 6, 14, (fragment.variant.notes[0],))
    assert fragment.phrase.notes[0] is fragment.variant.notes[0]
    assert fragment.phrase.notes[0].end == 16  # Never truncate a held source note.
    assert fragment.variant.source_indices == (3, 9)
    with pytest.raises(FrozenInstanceError):
        fragment.start_beat = 0


@pytest.mark.parametrize("position", (-1, 20, float("nan"), float("inf")))
def test_out_of_range_selection_fails_before_it_can_replace_a_live_fragment(position):
    module, fragment = selected()
    with pytest.raises(ValueError, match="Choose a measure inside"):
        module.select_fragment(fragment.variant, (0, 3, 6, 10, 14, 18, 20), from_beat=position)


def test_empty_final_selection_is_rejected():
    module, fragment = selected()
    with pytest.raises(ValueError, match="No note attacks"):
        module.select_fragment(fragment.variant, (0, 3, 6, 10, 14, 18, 20), from_beat=18)


def test_retry_reuses_controller_and_requires_release_of_a_physically_held_key():
    module, fragment = selected()
    session = module.GuidedSession()
    session.bind(fragment, stage_key="stage", revision=7, now=0, connected=True, recovery=True)
    controller = session.controller
    assert session.return_context == ("stage", 6)
    controller.start(now=1)
    controller.receive(pitch=60, is_on=True, at=1.1)
    assert controller.snapshot(now=1.1)["completed"]
    session.prepared = True
    session.stop()
    assert not session.prepared and session.return_context is None
    assert session.fragment is fragment
    session.bind(fragment, stage_key="stage", revision=8, now=2, connected=True)
    assert session.controller is controller
    controller.start(now=2.1)
    controller.receive(pitch=60, is_on=True, at=2.2)
    assert controller.snapshot(now=2.2)["target_index"] == 0
    controller.receive(pitch=60, is_on=False, at=2.3)
    controller.receive(pitch=60, is_on=True, at=2.4)
    assert controller.snapshot(now=2.4)["completed"]


def test_leaving_guidance_releases_selection_but_keeps_preference_and_rhythm_return():
    module, fragment = selected()
    session = module.GuidedSession()
    session.set_hints(True, now=0)
    session.bind(fragment, stage_key="stage", revision=7, now=1, connected=True, recovery=True)
    controller = session.controller
    controller.start(now=2)
    assert controller.snapshot(now=2)["hint_visible"]
    session.clear_selection()
    assert session.controller is None and session.fragment is None
    assert session.persistent_hints and session.return_context == ("stage", 6)
    session.bind(fragment, stage_key="next-stage", revision=8, now=3, connected=True)
    assert session.controller is not controller and session.return_context is None
    session.controller.start(now=4)
    assert session.controller.snapshot(now=4)["hint_visible"]
    session.set_hints(False, now=4)
    assert not session.persistent_hints


def test_marks_use_only_expected_feedback_and_matching_source_attack_glyphs():
    module, fragment = selected()
    session = module.GuidedSession()
    session.bind(fragment, stage_key="stage", revision=7, now=0, connected=True)
    glyph = {"id": "glyph-A", "pitch": 60, "hand": "right", "is_attack": True}
    layout = {"notes": [glyph], "attack_map": {"source-A": "glyph-A"}}
    teaching = {"expected_notes": [{"id": "stage:3"}],
                "note_feedback": [{"id": "stage:3", "status": "wrong", "hint_used": True}],
                "fragment": {"start_beat": 999}, "session_id": -1}
    assert session.marks(teaching, layout) == [
        {**glyph, "target_id": "stage:3", "status": "wrong", "hint_used": True}]
    teaching["note_feedback"] = []
    assert session.marks(teaching, layout) == [
        {**glyph, "target_id": "stage:3", "status": "expected", "hint_used": False}]
    for changes in ({"is_attack": False}, {"pitch": 61}, {"hand": "left"}):
        assert session.marks(teaching, {**layout, "notes": [{**glyph, **changes}]}) == []
    assert session.marks(teaching, {}) == []
    session.clear_selection()
    assert session.marks(teaching, layout) == []
