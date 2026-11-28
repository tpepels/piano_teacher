"""Fault injection for the independent rendered timing review."""
from copy import deepcopy
from PIL import Image, ImageDraw
from visual_timing import TimingReview, _policy_rate, _clearance

def meta(t=0, world=0, bpm=40, kind="take", speed=None):
    speed = bpm if speed is None else speed
    return {"timing_version":1,"fps":30,"time_ms":t,"sample_ms":t,
            "world":world,"run_offset":0,"following":True,"bpm":bpm,
            "mode":"practice","paused":False,"phase":"playing","transport":1,
            "midi_count":0,"button_text":"Pause","button_disabled":False,
            "score":[0,0,1,1],"playhead":.5,"events":[],"layers":[],
            "timeline":{"run":1,"end_world":None,"segments":[
                {"kind":kind,"world_start":0,"start_ms":0,"beats":20,
                 "spans":[[20,speed,speed]],"take_id":"t"}]}}

def image(color=None):
    im=Image.new("RGB",(640,400),(15,45,35))
    if color:
        ImageDraw.Draw(im).rectangle((315,195,325,205),fill=color)
    return im

def observe(review,old,new,before=None,after=None):
    return review.observe(old,new,before or image(),after or image())[0]

def test_render_hitch_is_not_confused_with_injected_hitch():
    review=TimingReview()
    old,new=meta(),meta(160,.1)
    assert "render_frame_hitch" in observe(review,old,new)
    new["events"]=[{"kind":"injected_hitch"}]
    assert "render_frame_hitch" not in observe(review,old,new)
    summary,_=review.finish()
    assert summary["injected_hitches"]==1
    assert summary["max_frame_ms"]==160

def test_microstutters_fail_the_percentile_gate():
    review=TimingReview()
    for i in range(1,41):
        observe(review,meta((i-1)*70,(i-1)*.0466667),meta(i*70,i*.0466667))
    _,failures=review.finish()
    assert any("recurring_frame_pacing_failure" in f["reasons"] for f in failures)

def test_stable_tempo_checks_both_slowdown_and_speedup():
    for rate in (30,40,55):
        review=TimingReview()
        reasons=[]
        for i in range(1,40):
            reasons+=observe(review,meta((i-1)*33,(i-1)*33*rate/60000),
                            meta(i*33,i*33*rate/60000))
        assert ("sustained_scroll_rate_error" in reasons)==(rate!=40)

def test_bad_schedule_is_not_an_authority_for_rest_speed():
    def rest(t,world):
        m=meta(t,world,bpm=22,kind="rest",speed=60)
        s=m["timeline"]["segments"][0]
        s.update(world_start=1,start_ms=2000)
        m["timeline"]["segments"].insert(0,
            {"kind":"take","world_start":0,"start_ms":0,"beats":1,"spans":[[1,22,22]]})
        return m
    review=TimingReview()
    reasons=[]
    for i in range(1,40):
        reasons+=observe(review,rest((i-1)*33,1+(i-1)*.033),rest(i*33,1+i*.033))
    assert "unauthorized_rest_or_free_speed" in reasons

def test_free_move_policy_caps_acceleration():
    m=meta(100,1,40,"rest",100)
    m["mode"]="learn"
    s=m["timeline"]["segments"][0]
    s.update(world_start=1,beats=2,spans=[[2,100,100]])
    m["timeline"]["segments"]=[
        {"kind":"hold","world_start":1,"start_ms":0,"beats":0,"spans":[[0,40,40]]},s,
        {"kind":"hold","world_start":3,"start_ms":3000,"beats":0,"spans":[[0,100,100]]}]
    assert _policy_rate(m)==80

def test_clearance_ignores_unseen_abandoned_source():
    event={"world":2,"layers":[{"strips":[
        {"ever_visible":True,"world_end":4},{"ever_visible":False,"world_end":16}]}]}
    assert _clearance(event)==2

def test_control_response_is_not_just_a_backend_ack():
    r=TimingReview()
    old,new=meta(),meta(40,.02)
    new["paused"]=True
    new["events"]=[{"kind":"transition","label":"pause_control","at_ms":1,
                    "transport":1,"button_text":"Pause"}]
    observe(r,old,new)
    late=deepcopy(new)
    late.update(time_ms=400,sample_ms=400,events=[])
    assert "control_response_missing_or_late" in observe(r,new,late)

def test_retry_rejects_excessive_placement_even_with_correct_rendering():
    r=TimingReview()
    old,new=meta(),meta(40,.02)
    event={"kind":"transition","label":"retry","at_ms":1,"world":0,"bpm":40,
           "transport":1,"button_text":"Pause","layers":[]}
    new.update(events=[event],transport=2,phase="count_in",
        playback={"current":{"segment_id":"new"},"presentation_confirmed":True})
    new["timeline"]["segments"]=[
        {"kind":"rest","world_start":0,"start_ms":0,"beats":10,"spans":[[10,40,40]]},
        {"kind":"count_in","world_start":10,"start_ms":15000,"beats":4,"spans":[[4,40,40]]},
        {"kind":"take","world_start":14,"start_ms":21000,"beats":4,"spans":[[4,40,40]],"take_id":"new"}]
    assert "unnecessary_transition_travel" in observe(r,old,new)

def test_midi_requires_receipt_new_feedback_and_pixels():
    for actual in (False,True):
        r=TimingReview()
        old,new=meta(),meta(40,.02)
        new.update(midi_count=1,events=[{"kind":"midi","label":"wrong","pitch":61,
                                        "at_ms":1,"midi_count":0}])
        new["layers"]=[{"id":1,"strips":[{"id":"s","visible":True,"left":.4,"right":.6,
                       "gutter":.05,"pitch_feedback":[["61","100"]]}]}]
        observe(r,old,new,after=image((240,100,100)) if actual else image())
        late=deepcopy(new)
        late.update(time_ms=300,sample_ms=300,events=[])
        reasons=observe(r,new,late)
        assert ("midi_feedback_missing_or_late" in reasons)==(not actual)
        assert r.completed[0].get("visible_ms")== (39 if actual else None)

def test_required_timing_probes_cannot_be_omitted():
    r=TimingReview()
    observe(r,meta(),meta(40,.02))
    _,failures=r.finish(["wrong_free","retry_wait"])
    reasons=[reason for f in failures for reason in f["reasons"]]
    assert "missing_timing_probe_coverage" in reasons
    assert "missing_retry_timing_coverage" in reasons
