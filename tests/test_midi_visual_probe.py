from copy import deepcopy
from PIL import Image,ImageDraw
from midi_visual_probe import MidiProbeReview

def head(status="missed",source="target",take="take"):
    return {"take":take,"source":source,"event":"event","slot":"slot","layer":1,
            "status":status,"x":.4,"y":.3,"rx":.015,"ry":.015}

def event(label="wrong",baseline=()):
    return {"kind":"midi","label":label,"pitch":61,"targets":["target"],"take":"take",
            "at_ms":1,"midi_count":0,"baseline_feedback":list(baseline)}

def sample(t,heads=(),events=(),count=1):
    return {"time_ms":t,"midi_count":count,"painted_feedback":list(heads),"events":list(events)}

def painted(color,at=(256,120)):
    im=Image.new("RGB",(640,400),(15,45,35))
    x,y=at
    ImageDraw.Draw(im).rectangle((x-3,y-3,x+3,y+3),fill=color)
    return im

def test_wrong_free_marks_target_not_wrong_pitch_ghost():
    r=MidiProbeReview()
    assert r.observe(sample(40,[head()],[event()]),painted((241,121,120)))[0]==[]
    assert r.completed[0]["visible_ms"]==39

def test_correct_pale_head_and_lightweight_draw():
    for image in (None,painted((180,237,218))):
        r=MidiProbeReview()
        assert r.observe(sample(60,[head("hit")],[event("correct")]),image)[0]==[]
        assert r.completed[0]["visible_ms"]==59

def test_unrelated_color_or_old_feedback_cannot_pass():
    for h,baseline,im in [(head(source="other"),[],None),
                         (head(take="old"),[],None),
                         (head(),[head()],None),
                         (head(),[],painted((240,100,100),(320,120)))]:
        r=MidiProbeReview()
        r.observe(sample(40,[h],[event(baseline=baseline)]),im)
        reasons,_=r.observe(sample(300,[h]),im)
        assert "midi_feedback_missing_or_late" in reasons

def test_receipt_is_required_even_with_real_core_draw():
    r=MidiProbeReview()
    r.observe(sample(40,[head()],[event()],count=0))
    assert "midi_feedback_missing_or_late" in r.observe(sample(300,[head()],count=0))[0]
