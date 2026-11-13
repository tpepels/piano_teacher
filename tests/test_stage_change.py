"""Lesson-plan selection mutations have no engine or transport dependency."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.stage_change import (
    StageChange, prepare_stage_change,
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


def test_prepared_step_and_tempo_are_scalar_intents():
    plan=Plan()
    assert prepare_stage_change(plan,"select_step",{"number":"2"})==StageChange("select_step",number=2)
    tempo=prepare_stage_change(plan,"tempo",{"bpm":"55"})
    assert tempo.tempo_only and tempo.bpm==55 and not tempo.resets_open_position
    assert not plan.events


def test_warmup_hand_change_requires_previous_mastered_stage():
    plan=Plan()
    with pytest.raises(ValueError,match="three clean passes"):
        prepare_stage_change(plan,"hand",{"hand":"left"},warmup=True)
    plan.mastered["first"]=True
    assert prepare_stage_change(plan,"hand",{"hand":"left"},warmup=True).hand=="left"

@pytest.mark.parametrize("action",["unknown","bad_action","calibrate"])
def test_unsupported_action_reports_original_error(action):
    with pytest.raises(ValueError,match="Unsupported action"):
        prepare_stage_change(Plan(),action,{})


def test_guided_tempo_choice_retains_the_exact_fragment():
    from dataclasses import replace
    from teaching_fixtures import teaching
    p,event,state=teaching(mode="learn")
    state=replace(state,route=replace(state.route,guided_range=(4.,8.),guided_return=(p.identity,4.)))
    event=replace(event,kind="manual",assessment=None,action="tempo",manual=StageChange("tempo",bpm=55))
    decision=p.lesson_generator.decide_teaching(event,state)
    assert (decision.next_exposure.from_beat,decision.next_exposure.end_beat,decision.next_exposure.bpm)==(4.,8.,55)
