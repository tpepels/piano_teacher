"""Public practice-state projections must remain independent of engine state."""
from copy import deepcopy
import pytest
from piano_teacher.state_projection import hand_stage_rows, guided_learning_fields


def test_warmup_unlocking_is_ordered():
    options = dict(kind="warmup", exercise_index=0, current_hand="right",
        available_hands=("right", "left", "both"), builtin_warmup=True,
        lesson_steps=[(0,"right","r"),(0,"left","l"),(0,"both","b"),(1,"right","x")])
    assert [x["locked"] for x in hand_stage_rows(**options, mastered={})] == [False, True, True]
    assert [x["locked"] for x in hand_stage_rows(**options, mastered={"r"})] == [False, False, True]
    assert hand_stage_rows(**{**options, "kind":"perform"}, mastered={}) == []


@pytest.mark.parametrize(("phase","expected","action"), [
    ("loading","Preparing a short idea to learn",None),
    ("disconnected","No piano connected","Connect your piano in Settings"),
    ("guided_complete","You found every note.","Ready to add rhythm?"),
    ("paused","Paused — resume when you are ready.",None),
    ("guided_wait","Play C + E together.",None),
])
def test_guided_projection_contract(phase,expected,action):
    teaching={"feedback":"Original","expected_notes":[{"label":"C"},{"label":"E"}],
              "target_index":0,"target_count":3}
    original=deepcopy(teaching)
    fragment={"first_bar":5,"last_bar":6,"start_beat":12.0,"end_beat":20.0}
    fields=guided_learning_fields(teaching=teaching,fragment=fragment,session_id=42,
             has_more_units=False,returning=False,phase=phase,
             required_notes=7,duration_beats=8.0)
    assert expected in fields["feedback"]
    assert fields["teaching"]["fragment"] == fragment and fields["teaching"]["session_id"] == 42
    assert fields["first_bar"] == 5 and fields["required_notes"] == 7
    assert fields["clock_beat"] == 0.0 and not fields["running"]
    assert fields["paused"] == (phase == "paused") and teaching == original
    assert ("next_action" in fields) == (action is not None)
    if action: assert action in fields["next_action"]


def test_guided_retry_more_units_and_wrong_note_hints():
    common=dict(fragment={"first_bar":1,"last_bar":1,"start_beat":0,"end_beat":4},
                session_id=2,phase="guided_complete",required_notes=3,duration_beats=4.0)
    retry=guided_learning_fields(**common,teaching={},has_more_units=False,returning=True)
    assert retry["next_action"] == "Retry rhythm from these bars."
    more=guided_learning_fields(**common,teaching={},has_more_units=True,returning=False)
    assert more["next_action"] == "Choose Next idea to learn the next part of the passage."
    wait=guided_learning_fields(**{**common, "phase":"guided_wait"},
          teaching={"expected_notes":[{"label":"F"}],"hint_reason":"wrong_note"},
          has_more_units=False,returning=False)
    assert wait["feedback"] == "Find F on the keyboard below, then try again."
