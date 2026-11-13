"""Continuation executes the selected intent without pedagogical rerouting."""
from dataclasses import replace
import pytest
from teaching_fixtures import teaching
from piano_teacher.application.teaching_continuation import TeachingContinuation

@pytest.mark.parametrize("intent,changed,prepared,expected",[
    ("stop",False,False,"stop"),("pause",False,False,"stop"),
    ("repeat",False,False,"continue"),("advance",True,False,"await_score"),
    ("advance",True,True,"handoff"),("guided",False,False,"guided")])
def test_selected_continuation(intent,changed,prepared,expected):
    p,event,state=teaching()
    decision=p.lesson_generator.decide_teaching(event,state)
    exposure=decision.next_exposure
    if intent=="guided":
        exposure=replace(exposure,mode="learn")
    decision=replace(decision,continuation=intent,next_exposure=exposure)
    assert TeachingContinuation.after_settlement(decision,score_changed=changed,prepared=prepared).action==expected
