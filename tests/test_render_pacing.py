from render_pacing import review
import pytest


def frames(gap=16.667,hitch=False):
    time=0.
    result=[]
    for i in range(100):
        time+=gap if i!=50 or not hitch else 14000.
        result.append({"frame":i,"engine_frame":i+100,"time_ms":time,"fps":60,
                       "capture_cost_ms":.2,"step":"hitch_recover","screen":"practice","ready":True,
                       "events":[{"kind":"injected_hitch"}] if i==50 and hitch else []})
    return result


MANIFEST={"fps":60,"pacing_only":True,"frames":100,"success":True}


def test_60fps_good_with_explicit_hitch():
    result=review(frames(hitch=True),MANIFEST,["hitch_recover"])
    assert result["failures"]==[]
    assert result["timing"]["injected_hitches"]==1


def test_untagged_freeze_is_a_failure():
    data=frames(hitch=True)
    data[50]["events"]=[]
    result=review(data,MANIFEST)
    assert any("render_frame_hitch" in f["reasons"] for f in result["failures"])


def test_sustained_30fps_is_not_60fps():
    result=review(frames(gap=33.333),MANIFEST)
    assert any("recurring_frame_pacing_failure" in f["reasons"] for f in result["failures"])


def test_missing_rendered_frames_fail_closed():
    data=frames()
    data[50]["engine_frame"]+=1
    with pytest.raises(ValueError,match="Missing real rendered frame"):
        review(data,MANIFEST)
