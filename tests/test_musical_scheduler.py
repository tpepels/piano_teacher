"""Musical scheduling contracts: one grader deadline for every route.

These are the pure calculations consumed by the engine and supplied with real
engraver measurements; the Godot score queue still checks immutable ink.
"""
import math
import pytest

from piano_teacher.application.musical_scheduler import (
    SCHEDULER, MusicalDeadline, PreparationDeadline,
)
from piano_teacher.visual_transport import VisualTransport


def test_manual_play_uses_maximum_not_sum_of_count_in_and_reserved_ink():
    plan = SCHEDULER.initial(now=100,bpm=24,count_in_beats=2,
                             reading_lead_seconds=6.0)
    assert plan.run_at == pytest.approx(106)
    assert plan.count_in_at == pytest.approx(101)
    assert dict(plan.bounds) == {"count_in":105.0,"earliest_existing":106.0}
    reserved = SCHEDULER.initial(now=100,bpm=24,count_in_beats=2,
                                 reserved_at=107.0,continuation=True)
    assert reserved.run_at == 107.0
    assert reserved.count_in_at == pytest.approx(102.0)
    assert len(reserved.bounds) == 1


@pytest.mark.parametrize("bpm", [12.,24.,27.,40.,80.,132.,240.])
@pytest.mark.parametrize("count_in", [1.,2.,3.,4.,6.])
def test_start_count_in_is_one_bar_at_every_tempo(bpm,count_in):
    plan = SCHEDULER.initial(now=100.,bpm=bpm,count_in_beats=count_in)
    assert plan.run_at == pytest.approx(100.+count_in*60./bpm)
    assert plan.count_in_at == pytest.approx(100.)


def test_constraints_are_absolute_even_when_geometry_was_delivered_late():
    plan = SCHEDULER.resolve("handoff",now=100,bpm=24,count_in_beats=2,
                             latency=.4,physical_at=104,
                             reserved_at=102,earliest_at=105.1)
    assert plan.run_at == pytest.approx(105.4)
    assert len(plan.bounds) == 4
    assert plan.run_at == max(value for _,value in plan.bounds)


def test_authored_slowdown_is_integrated_by_source_map_not_nominal_tempo():
    class TwoRate:
        def seconds_at(self,beat):
            return min(beat,1)*60/24+max(beat-1,0)*60/12
    assert SCHEDULER.source_seconds(TwoRate(),2,24)==pytest.approx(7.5)
    assert SCHEDULER.source_seconds(None,2,24)==pytest.approx(5)
    assert SCHEDULER.seconds_beats(-2,24)==pytest.approx(-.8)


def test_repeat_and_preview_use_previous_grading_origin_not_poll_time():
    deadline = SCHEDULER.repeat(run_at=100,source_seconds=4.4444444,
                                gap_beats=2,bpm=27)
    assert deadline==pytest.approx(100+4.4444444+2*60/27)
    assert deadline==SCHEDULER.repeat(run_at=100,source_seconds=4.4444444,
                                       gap_beats=2,bpm=27)


def test_after_source_rest_and_header_respect_tempo_epoch():
    start=100.0
    geometry={"clear_beats":2.14279410045217,
              "header_beats":.513621934902367}
    no_step=SCHEDULER.short_rest(
        now=100.2,source_end=start,outgoing_bpm=27,
        incoming_bpm=27,count_in_beats=2,latency=.4,**geometry)
    transition=SCHEDULER.short_rest(
        now=100.2,source_end=start,outgoing_bpm=27,
        incoming_bpm=24,count_in_beats=2,latency=.4,
        tempo_epoch=100.2,**geometry)
    span=sum(geometry.values())
    expected=100.2+(span-.2*27/60)*60/24
    assert transition.run_at==pytest.approx(expected)
    assert no_step.run_at==pytest.approx(start+span*60/27)
    assert transition.run_at-start < 2.25*2*60/24
    assert transition.count_in_at==pytest.approx(transition.run_at-5)


def test_authoritative_announced_retry_does_not_gain_another_horizon():
    future=103.0
    assert SCHEDULER.automatic(
        announced_at=future,from_beat_matches=True,deadline=future,
        now=101,bpm=24,rest_beats=2,horizon_beats=7,
        short_rest_at=107)==future
    fresh=SCHEDULER.automatic(
        announced_at=None,from_beat_matches=False,deadline=future,
        now=101,bpm=24,rest_beats=2,horizon_beats=7,
        short_rest_at=107)
    assert fresh==107
    longer=SCHEDULER.automatic(
        announced_at=None,from_beat_matches=False,deadline=future,
        now=101,bpm=24,rest_beats=2,horizon_beats=7,
        short_rest_at=None)
    assert longer==pytest.approx(max(103+5*60/24,101+7*60/24))


def test_manual_retry_uses_one_written_rest_and_preserves_reserved_onset():
    assert SCHEDULER.reserved_retry_reverse(
        lead_seconds=12.0,rest_seconds=10.0)==2.0
    vt=VisualTransport()
    end=vt.schedule_preparation({"duration_beats":4},
        source_from_beat=0,from_visual=10,now=100,
        reverse_seconds=2,bpm=24,reading_lead_included=True)
    assert end==pytest.approx(112)
    # Unreserved recovery gets one horizon instead of adding it twice.
    with_horizon=vt.schedule_preparation({"duration_beats":4},
        source_from_beat=0,from_visual=10,now=100,
        reverse_seconds=2,bpm=24,horizon_beats=6,
        reading_lead_included=False)
    assert with_horizon==pytest.approx(117)
    short=vt.schedule_preparation({"duration_beats":4},
        source_from_beat=0,from_visual=10,now=100,
        reverse_seconds=2,bpm=24,horizon_beats=6,
        reading_lead_included=False,short_deadline=106)
    assert short==106
    assert vt.preparation_schedule()["deadline_at_ms"]==106000


def test_final_boundary_rolling_recovery_starts_on_same_short_rest_deadline():
    now=100.2
    rest=SCHEDULER.short_rest(now=now,source_end=100,outgoing_bpm=27,
        incoming_bpm=24,clear_beats=2.14,header_beats=.514,
        count_in_beats=2,latency=.4,tempo_epoch=now)
    transport=VisualTransport()
    deadline=transport.schedule_preparation({"duration_beats":2},
        source_from_beat=0,from_visual=6,now=now,
        reverse_seconds=3,bpm=24,short_deadline=rest.run_at,
        horizon_beats=9,reading_lead_included=False)
    assert deadline==rest.run_at
    assert (deadline-100)/(2*60/24)<2.25
    assert transport._visual_rewind_at<=transport._preparation_at<=deadline


def test_lesson_handoff_uses_physical_clearance_and_count_in_in_parallel():
    now=100.5
    result=SCHEDULER.handoff(now=now,previous_deadline=102,
        lead_beats=3.5,clear_beats=0,count_in_beats=2,
        bpm=24,rest_take_end=(100,27),latency=.4)
    remaining=3.5-.5*27/60
    assert result.run_at==pytest.approx(now+remaining*60/24)
    assert result.run_at>=now+.4+2*60/24
    fallback=SCHEDULER.handoff(now=now,previous_deadline=102,
        lead_beats=5,clear_beats=None,count_in_beats=2,
        bpm=24,rest_take_end=None,latency=.4)
    assert fallback.run_at==pytest.approx(102+5*60/24)


@pytest.mark.parametrize("bpm", [24.,60.,120.])
def test_tempo_up_or_down_uses_new_rate_without_retiming_notes(bpm):
    lead=SCHEDULER.offscreen(deadline=100,lead_beats=4,bpm=bpm)
    assert lead==pytest.approx(100+240/bpm)
    assert lead==pytest.approx(100+SCHEDULER.beats_seconds(4,bpm))


def test_pause_resume_shifts_all_active_epochs_and_preserves_zero_sentinels():
    t=VisualTransport(run_at=90)
    t.schedule_preparation({"duration_beats":2},
                           source_from_beat=0,from_visual=4,
                           now=100,reverse_seconds=1,bpm=24)
    t.announce_continuation(0,t.next_at,24)
    before=t.announced_continuation
    t.pause(at=101)
    t.resume(now=111,shift_run_at=True)
    assert t.run_at==100
    assert t.announced_continuation[1]==pytest.approx(before[1]+10)
    assert t.next_at==pytest.approx(before[1]+10)
    empty=VisualTransport()
    empty.pause(at=101)
    empty.resume(now=111,shift_run_at=False)
    assert empty.run_at==empty.next_at==empty._preparation_at==0


def test_resume_reuse_retains_existing_ink_but_fresh_copy_uses_clearance():
    now=100.
    assert SCHEDULER.fresh_resume(now=now,old_deadline=110,
        reading_lead_seconds=2,horizon_beats=7,bpm=24,
        short_rest_at=113,reuse=True)==102
    assert SCHEDULER.fresh_resume(now=now,old_deadline=110,
        reading_lead_seconds=2,horizon_beats=7,bpm=24,
        short_rest_at=113,reuse=False)==113
    assert SCHEDULER.fresh_resume(now=now,old_deadline=110,
        reading_lead_seconds=2,horizon_beats=7,bpm=24,
        short_rest_at=None,reuse=False)==pytest.approx(117.5)


def test_resume_during_playing_preserves_existing_count_in_not_readd_it():
    now=100.0
    bound,grading=SCHEDULER.resume_playing(
        now=now,origin=105,bpm=24,count_in_beats=2,
        reading_lead_seconds=6,already_waiting=3,reuse=False)
    assert bound==108 and grading==106
    reserved=SCHEDULER.resume_playing(
        now=now,origin=105,bpm=24,count_in_beats=2,
        reading_lead_seconds=6,already_waiting=3,reuse=True)
    assert reserved==(106,106)


def test_failed_and_unprepared_stage_enforce_safe_reservation():
    assert SCHEDULER.late_ready(now=100,outgoing_bpm=24)==105
    fallback=SCHEDULER.handoff(now=103,previous_deadline=100,
        lead_beats=6,clear_beats=None,count_in_beats=2,
        bpm=24,rest_take_end=None,latency=.4)
    assert fallback.run_at==118
    assert SCHEDULER.shift_epoch(0,10,active=False)==0


@pytest.mark.parametrize("invalid", [float("nan"),float("inf"),float("-inf")])
def test_invalid_geometry_and_deadlines_fail_closed(invalid):
    with pytest.raises(ValueError):
        SCHEDULER.short_rest(now=100,source_end=99,outgoing_bpm=24,
            incoming_bpm=24,clear_beats=invalid,header_beats=2,
            count_in_beats=2,latency=.4)
    with pytest.raises(ValueError):
        SCHEDULER.initial(now=100,bpm=24,count_in_beats=2,
                           reading_lead_seconds=invalid)
    with pytest.raises(ValueError):
        SCHEDULER.offscreen(deadline=100,lead_beats=invalid,bpm=24)


def test_immutable_passage_plan_has_named_fields_and_tuple_compatibility():
    plan=SCHEDULER.passage(from_beat=4,deadline=130,bpm=24)
    assert plan==(4.0,130.0,24.0)
    assert plan.from_beat==4
    assert plan.run_at==130
    assert plan.bpm==24
    with pytest.raises(AttributeError):
        plan.run_at=140
    shifted=SCHEDULER.shift_passage(plan,seconds=2.5)
    assert shifted==(4,132.5,24)
    assert plan==(4,130,24)
    retimed=SCHEDULER.retime_passage(shifted,deadline=140)
    assert retimed==(4,140,24)


def test_authored_tempo_epoch_is_stable_except_when_stage_or_bpm_changes():
    key,epoch=SCHEDULER.tempo_epoch(
        stage="first",bpm=27,now=100,prior_key=None,prior_epoch=None)
    assert epoch==100
    key,epoch=SCHEDULER.tempo_epoch(
        stage="first",bpm=27,now=110,prior_key=key,prior_epoch=epoch)
    assert epoch==100
    key,epoch=SCHEDULER.tempo_epoch(
        stage="first",bpm=24,now=111,prior_key=key,prior_epoch=epoch)
    assert epoch==111
    key,epoch=SCHEDULER.tempo_epoch(
        stage="second",bpm=24,now=120,prior_key=key,prior_epoch=epoch)
    assert epoch==120


def test_guided_untimed_repetition_does_not_add_the_horizon_twice():
    assert SCHEDULER.guided(now=100,previous_deadline=None,
        duration_beats=4,count_in_beats=2,horizon_beats=3,
        bpm=24)==pytest.approx(105)
    assert SCHEDULER.guided(now=106,previous_deadline=105,
        duration_beats=4,count_in_beats=2,horizon_beats=3,
        bpm=24)==105
    # Once the full source plus reading horizon exited, the next entire
    # count-in is placed from whichever absolute bound is later.
    later=SCHEDULER.guided(now=125,previous_deadline=105,
        duration_beats=4,count_in_beats=2,horizon_beats=3,bpm=24)
    assert later==pytest.approx(max(130,105+7*60/24+5))


def test_recovery_rewind_budget_is_calculated_once_at_start_tempo():
    assert SCHEDULER.recovery_rewind(
        feedback_seconds=.5,passage_beats=2,bpm=24)==pytest.approx(5/3)
    assert SCHEDULER.recovery_rewind(
        feedback_seconds=2,passage_beats=8,bpm=12)==4
    assert SCHEDULER.count_in_beats(2,24)==2
    assert SCHEDULER.count_in_beats(4,120)==4


def test_timing_math_has_one_implementation_across_production_owners():
    """Reject another hand-coded beats/BPM time formula in an engine path."""
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    owned=[
        "piano_teacher/server.py",
        "piano_teacher/visual_transport.py",
        "piano_teacher/application/attempt_progression.py",
        "piano_teacher/application/transport_commands.py",
        "piano_teacher/application/teaching_continuation.py",
    ]
    offenders=[]
    for filename in owned:
        tree=ast.parse((root/filename).read_text(),filename=filename)
        for node in ast.walk(tree):
            if not isinstance(node,ast.BinOp) or not isinstance(
                    node.op,(ast.Mult,ast.Div)):
                continue
            if any(isinstance(side,ast.Constant) and type(side.value) in (
                    int,float) and side.value==60.0
                   for side in (node.left,node.right)):
                offenders.append((filename,node.lineno))
    assert not offenders,(
        "Musical beat/time arithmetic belongs to SCHEDULER only: "
        +repr(offenders))


def test_musical_conversions_include_signed_pickups_and_live_tempos():
    assert SCHEDULER.signed_beats_seconds(-.5,24)==pytest.approx(-1.25)
    assert SCHEDULER.beat_rate(24)==pytest.approx(.4)
    assert SCHEDULER.seconds_per_beat(24)==pytest.approx(2.5)
    assert SCHEDULER.seconds_beats(-1.25,24)==pytest.approx(-.5)
    with pytest.raises(ValueError):
        SCHEDULER.beats_seconds(-.5,24)
