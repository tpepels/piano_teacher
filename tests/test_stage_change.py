"""Lesson-plan selection mutations have no engine or transport dependency."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.stage_change import (
    StageChange, apply_stage_change, prepare_stage_change, guided_reentry,
)


class Plan:
    def __init__(self):
        self.lesson_steps = [SimpleNamespace(key="first"),
                             SimpleNamespace(key="second")]
        self.hands = ("right", "left", "both")
        self.hand_index = 0
        self.mastered = {}
        self.events = []

    def select_step(self, number):
        self.events.append(("step", number))

    def jump(self, direction):
        self.events.append(("jump", direction))

    def set_hand(self, hand):
        self.events.append(("hand", hand))

    def set_bpm(self, bpm):
        self.events.append(("bpm", bpm))

    def increase_tempo(self):
        self.events.append(("up",))

    def decrease_tempo(self):
        self.events.append(("down",))


@pytest.mark.parametrize("invalid", [None, True, False, 0, 3, 1.5, "a", {}, []])
def test_invalid_step_selection_is_rejected_before_effects(invalid):
    plan = Plan()
    with pytest.raises(ValueError):
        prepare_stage_change(plan, "select_step", {"number": invalid})
    assert not plan.events


def test_prepared_step_changes_and_tempo_do_not_touch_transport():
    plan = Plan()
    step = prepare_stage_change(plan, "select_step", {"number": "2"})
    assert step == StageChange("select_step", number=2)
    assert step.resets_open_position and not step.tempo_only
    apply_stage_change(plan, step, warmup=False)
    tempo = prepare_stage_change(plan, "tempo", {"bpm": "55"})
    assert tempo.tempo_only and not tempo.resets_open_position
    apply_stage_change(plan, tempo, warmup=False)
    apply_stage_change(plan, StageChange("next"), warmup=False)
    apply_stage_change(plan, StageChange("previous"), warmup=False)
    assert plan.events == [("step", 2), ("bpm", 55),
                           ("jump", 1), ("jump", -1)]


def test_warmup_hand_change_requires_previous_mastered_stage():
    plan = Plan()
    hand = prepare_stage_change(plan, "hand", {"hand": "left"})
    with pytest.raises(ValueError, match="three clean passes"):
        apply_stage_change(plan, hand, warmup=True)
    plan.mastered["first"] = True
    apply_stage_change(plan, hand, warmup=True)
    assert plan.events == [("hand", "left")]


@pytest.mark.parametrize("action", ["unknown", "bad_action", "calibrate"])
def test_unsupported_action_reports_original_error(action):
    with pytest.raises(ValueError, match="Unsupported action"):
        apply_stage_change(Plan(), StageChange(action), warmup=False)


def test_guided_reentry_preserves_source_anchor_only_after_matching_tempo_change():
    change=StageChange("tempo")
    assert guided_reentry(
        change=change,was_guided=True,course_guided=True,
        previous_return=("right",4.0),current_stage="right").route == "same_fragment"
    assert guided_reentry(
        change=change,was_guided=True,course_guided=True,
        previous_return=("right",4.0),current_stage="right").recovery
    assert not guided_reentry(
        change=change,was_guided=True,course_guided=True,
        previous_return=("right",4.0),current_stage="left").recovery
    assert guided_reentry(
        change=change,was_guided=False,course_guided=True,
        previous_return=None,current_stage="right").route == "none"
    hand=guided_reentry(
        change=StageChange("hand",hand="left"),was_guided=True,
        course_guided=True,previous_return=None,current_stage="left")
    assert (hand.route,hand.explicit_learn)==("course",True)
    ordinary=guided_reentry(
        change=StageChange("next"),was_guided=True,
        course_guided=False,previous_return=None,current_stage="right")
    assert (ordinary.route,ordinary.recovery)==("fresh",False)
