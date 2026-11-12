extends SceneTree
## R1 F1 regression: an automatic continuation's source is bound to the take
## its backend plan names (plan identity, no onset tolerance), and its one
## count-in bar is spoken in the bar right before the announced deadline.
const Coordinator := preload("res://metronome_frame_coordinator.gd")

class FakeSegment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []
    var synced_take := ""
    func sync_note_status(take_key: String, _source, _visible_ink: bool) -> void:
        synced_take = take_key

class InstrumentedView:
    extends "res://notation/native/view.gd"
    func retained_ready() -> bool:
        return true
    func _new_retained_segment(kind: String):
        var segment := FakeSegment.new()
        add_child(segment)
        retained_all_segments.append(segment)
        if kind == "source":
            for i in range(4):
                segment.note_instances.append({"event_id":"attack-%d" % i,
                    "source_id":"source-%d" % i,
                    "position":Vector2(float(i)*96.0,200.0)})
        return segment

class CountIn:
    extends RefCounted
    var spoken: Array[int] = []
    var spoken_at: Array[float] = []
    var shown := 0
    var circles := 0
    var last_beat := NAN
    func present(beat: float, bar: int, visible: bool, _paused: bool,
            _count_in_beats: float = -1.0) -> void:
        last_beat = beat
        if visible:
            shown += 1
            if beat < 0.0:  # GameCountIn hides itself from beat 0 on
                circles = bar
    func speak_beat(number: int) -> bool:
        spoken.append(number)
        spoken_at.append(last_beat)
        return true

class Stage:
    extends RefCounted
    var count_in := CountIn.new()

class Practice:
    extends RefCounted
    var stage := Stage.new()

class Clock:
    extends RefCounted
    var retry_active := false
    var has_backend_offset := true
    var backend_offset_ms := 250.0
    func retry_preparing(_now: int) -> bool:
        return false
    func retry_count_in_beat(_now: int) -> float:
        return NAN

class Settings:
    extends RefCounted
    var calibration_beat_pulse = null
    func animate_calibration_beat(_beat: float, _active: bool,
            _bars: int = 12, _count: int = 4) -> void:
        pass

var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("CONTINUATION_PLAN_FAILED:",message)

func _state(phase: String, transport: int, running: bool) -> Dictionary:
    return {"running":running,"paused":false,"phase":phase,"auto":true,
        "mode":"practice","piece_fingerprint":"plan","revision":1,
        "transport_id":transport,"play_from_beat":0.0}

func _key(transport: int) -> String:
    return "plan|1|%d|practice" % transport

func _owner_key(v, owner_serial: int) -> String:
    for item in v.stream_passes:
        if int(item.get("take_owner",-1)) == owner_serial and \
                str(item.get("kind","")) == "source":
            return str(item.get("take_key",""))
    return ""

func _view() -> InstrumentedView:
    var v := InstrumentedView.new()
    v.size = Vector2(800,440)
    v.native_ready = true
    v.timeline.duration_beats = 8.0
    v.timeline.measures = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    v.timeline.pixels_per_beat = 96.0
    v.present_flow(0.0,_state("ready",0,false),0.0)
    check(not v.arm_stream_take(0.0,0.0).is_empty() and v.acknowledge_stream_arm(),
        "fixture plays its first take")
    v.present_flow(.1,_state("count_in",1,true),-3.9)
    check(_owner_key(v,v._stream_live_serial) == _key(1),"Play binds take 1")
    return v

func _plan(transport: int, deadline_world: float) -> Dictionary:
    return {"plan_id":"plan:1:%d:0.000000:%.3f" % [transport,deadline_world],
        "source_from_beat":0.0,"deadline_at_ms":deadline_world*1000.0,
        "transport_id":transport,"count_in_beats":4.0}

func _test_binding() -> void:
    var v := _view()
    # Take 1 finished; the engine announces take 2 at world 40 for the rest.
    var plan := _plan(2,40.0)
    var rest := _state("recovering",1,false)
    rest["score_queue_next"] = plan
    # A failed take's preparation for the same opening is in progress.
    rest["practice_preparation"] = {"source_from_beat":0.0,"phase":"preparing"}
    check(v.enqueue_recovery_queue(20.0,0.0,40.0,plan["plan_id"]),
        "announced repeat is admitted offscreen at its deadline")
    var owner_serial: int = v._stream_last_admitted
    v.present_flow(20.0,rest,0.0)
    var strips := 0
    for item in v.stream_passes:
        if int(item.get("take_owner",-1)) == owner_serial:
            strips += 1
    check(strips == 2,
        "the whole announced two-measure repeat survives the feedback rest")
    var again: bool = v.enqueue_recovery_queue(21.0,0.0,40.0004,plan["plan_id"])
    var openings := 0
    for item in v.stream_passes:
        if str(item.get("take_key","")) == "autopending" and \
                str(item.get("kind","")) == "source" and \
                float(item.get("source_floor",-1.0)) == 0.0:
            openings += 1
    check(again and v._stream_last_admitted == owner_serial and openings == 1,
        "re-projected polls of one plan never add a second copy")
    # A snapshot of another take must not claim it.
    var other := _state("playing",3,true)
    other["score_queue_next"] = _plan(3,55.0)
    v.present_flow(39.0,other,0.0)
    check(_owner_key(v,owner_serial) == "autopending",
        "a different take's plan cannot bind this repeat")
    # Take 2 starts. The polled graded estimate is 0.1 beat off the
    # admitted onset (> the old .025 tolerance); the plan still binds.
    var running := _state("playing",2,true)
    running["score_queue_next"] = plan
    v.present_flow(40.1,running,0.0)
    check(_owner_key(v,owner_serial) == _key(2) and
        v._stream_live_serial == owner_serial,
        "the take named by the plan binds its own admitted source")
    v.free()

func _test_count_in() -> void:
    var practice := Practice.new()
    var clock := Clock.new()
    var owner := Coordinator.new(Settings.new(),practice,clock,
        func(_now: int) -> float: return NAN,
        func(_accent: bool, _beat: float) -> void: pass,
        func(_accent: bool) -> void: pass)
    var deadline_ms := 100000.0
    var rest := _state("feedback",1,false)
    rest["bpm"] = 60.0
    rest["score_queue_next"] = {"plan_id":"p","source_from_beat":0.0,
        "deadline_at_ms":deadline_ms,"transport_id":2,"count_in_beats":4.0}
    var local_deadline: int = int(deadline_ms+clock.backend_offset_ms)
    for at in range(local_deadline-12000,local_deadline,16):
        owner.update(rest,at,NAN,at)
    check(practice.stage.count_in.spoken == [1,2,3,4],
        "exactly one Ichi Ni San Shi in the bar before the deadline, got %s" %
            str(practice.stage.count_in.spoken))
    check(practice.stage.count_in.shown > 0,"the count-in circles are shown")
    var started := _state("playing",2,true)
    started["bpm"] = 60.0
    started["count_in_beats"] = 0.0
    for at in range(local_deadline,local_deadline+3000,16):
        owner.update(started,at,float(at-local_deadline)/1000.0,at)
    check(practice.stage.count_in.spoken == [1,2,3,4],
        "the take that starts at the deadline counts nothing again")

func _test_flow_rate_switch() -> void:
    var Flow := preload("res://continuous_score_flow.gd")
    var flow = Flow.new()
    flow.sample(0,40.0)
    flow.sample(1000,40.0)
    # The tempo step happened at 900 ms; this client learns it at 1000 ms.
    flow.switch_rate_at(900.0,44.0)
    check(is_equal_approx(flow.beat,1000.0*40.0/60000.0+100.0*4.0/60000.0),
        "a faster take start is accounted from its exact run_at")
    var before: float = flow.beat
    flow.sample(2000,44.0)
    check(is_equal_approx(flow.beat-before,44.0/60.0),"then runs at the new rate")
    flow.switch_rate_at(1900.0,40.0)
    var at_switch: float = flow.beat
    var previous: float = at_switch
    var monotonic := true
    for at in range(2016,2400,16):
        flow.sample(at,40.0)
        monotonic = monotonic and flow.beat > previous
        previous = flow.beat
    check(monotonic,"a slower take start never moves the axis back or stops it")
    check(is_equal_approx(flow.beat,at_switch+384.0*40.0/60000.0-100.0*4.0/60000.0),
        "and the slower rate is repaid exactly")
    # A deadline projected while debt is still owed lands where the axis
    # really is then (the debt is repaid on the way).
    var second = Flow.new()
    second.sample(0,108.0)
    second.sample(1000,108.0)
    second.switch_rate_at(800.0,40.0)
    var projected: float = second.project_authored_future(3000,1000,0.0,40.0,[])
    for at in range(1016,3001,16):
        second.sample(at,40.0)
    second.sample(3000,40.0)
    check(absf(second.beat-projected) < .0005,
        "a projected deadline includes the slow-down still owed: %f vs %f" % [
            second.beat,projected])

func _test_retry_lead_after_slowdown_meets_reserved_onset() -> void:
    # Round 4 item 8: a Retry pressed during a slowed (tempo-mapped) take.
    # main.gd converts the reserved world lead at the selected BPM; the
    # engine notes its tempo epoch at the command, which this client learns
    # one snapshot later and applies retroactively. The world then reaches
    # the reserved onset exactly at the deadline it sent.
    var Flow := preload("res://continuous_score_flow.gd")
    var Admission := preload("res://score_stream_admission.gd")
    var flow = Flow.new()
    flow.sample(0,30.0)
    flow.sample(1000,30.0)
    var start_world: float = flow.project(1000)+6.0
    var lead_bpm: float = Admission.command_lead_bpm("restart",flow.bpm,40.0)
    check(lead_bpm == 40.0,"Retry converts its lead at the selected BPM")
    var deadline_ms: float = 1000.0+Admission.lead_seconds(
        start_world,flow.project(1000),lead_bpm)*1000.0
    flow.sample(1100,30.0)
    flow.switch_rate_at(1000.0,40.0)
    var at := 1116
    while at < int(deadline_ms):
        flow.sample(at,40.0)
        at += 16
    flow.sample(int(deadline_ms),40.0)
    check(absf(flow.beat-start_world) < .002,
        "the reserved Retry onset is at the playhead at its deadline: %f vs %f" % [
            flow.beat,start_world])
    check(Admission.command_lead_bpm("resume",30.0,40.0) == 30.0,
        "a mid-take Resume continues in the take's own tempo map")

func _test_count_in_at_announced_tempo() -> void:
    # A tempo-step repeat (rest at 60 BPM, next take announced at 72 BPM)
    # counts in at 72 BPM: cues 60/72 s apart, the last one beat before.
    var practice := Practice.new()
    var clock := Clock.new()
    var owner := Coordinator.new(Settings.new(),practice,clock,
        func(_now: int) -> float: return NAN,
        func(_accent: bool, _beat: float) -> void: pass,
        func(_accent: bool) -> void: pass)
    var deadline_ms := 200000.0
    var rest := _state("feedback",4,false)
    rest["bpm"] = 60.0
    rest["score_queue_next"] = {"plan_id":"q","source_from_beat":0.0,
        "deadline_at_ms":deadline_ms,"transport_id":5,"count_in_beats":4.0,
        "bpm":72.0}
    var local_deadline: int = int(deadline_ms+clock.backend_offset_ms)
    var cue_ms: Array = []
    for at in range(local_deadline-8000,local_deadline,1):
        var before: int = practice.stage.count_in.spoken.size()
        owner.update(rest,at,NAN,at)
        if practice.stage.count_in.spoken.size() > before:
            cue_ms.append(at)
    var beat_ms: float = 60000.0/72.0
    check(practice.stage.count_in.spoken == [1,2,3,4] and cue_ms.size() == 4,
        "one bar at the announced tempo, got %s" % str(practice.stage.count_in.spoken))
    if cue_ms.size() == 4:
        for i in range(3):
            check(absf(float(cue_ms[i+1]-cue_ms[i])-beat_ms) <= 2.0,
                "cue spacing is the announced take's beat")
        check(absf(float(local_deadline-int(cue_ms[3]))-beat_ms) <= 2.0,
            "last cue one announced beat before the deadline")

class PreparingClock:
    extends Clock
    func retry_preparing(_now: int) -> bool:
        return true
    func retry_count_in_beat(at: int) -> float:
        return (float(at)-110000.0)/1000.0

func _test_unannounced_rest_is_silent() -> void:
    # A rest whose next take was NOT announced (settlement may reroute it)
    # speaks nothing, even while the engine's preparation clock runs; the
    # take counts its own last bar once it has started.
    var practice := Practice.new()
    var clock := PreparingClock.new()
    clock.retry_active = true
    var owner := Coordinator.new(Settings.new(),practice,clock,
        func(_now: int) -> float: return NAN,
        func(_accent: bool, _beat: float) -> void: pass,
        func(_accent: bool) -> void: pass)
    for phase in ["feedback","recovering","preview_gap"]:
        var rest := _state(phase,3,false)
        rest["bpm"] = 60.0
        rest["count_in_bar_beats"] = 4
        for at in range(100000,110000,16):
            owner.update(rest,at,NAN,at)
    check(practice.stage.count_in.spoken.is_empty() and
        practice.stage.count_in.shown == 0,
        "an unannounced rest speaks and shows no count-in, got %s" %
            str(practice.stage.count_in.spoken))

func _coordinator(practice: Practice):
    return Coordinator.new(Settings.new(),practice,Clock.new(),
        func(_now: int) -> float: return NAN,
        func(_accent: bool, _beat: float) -> void: pass,
        func(_accent: bool) -> void: pass)

func _test_compound_meter_count_in() -> void:
    # Owner decision M3: one syllable per dotted-quarter pulse, evenly across
    # the single bar, ending right before the first note; circles match.
    for case in [[[6,8],3.0,[1,2]],[[9,8],4.5,[1,2,3]],[[12,8],6.0,[1,2,3,4]],
            [[4,4],4.0,[1,2,3,4]],[[3,4],3.0,[1,2,3]]]:
        var practice := Practice.new()
        var owner = _coordinator(practice)
        var bar: float = float(case[1])
        var state := _state("count_in",7,true)
        state["bpm"] = 60.0
        state["count_in_meter"] = case[0]
        state["count_in_bar_beats"] = bar
        state["count_in_beats"] = bar
        var beat := -bar
        while beat < 0.5:
            owner.update(state,1000,beat,1000)
            beat += .01
        var pulse: float = 1.5 if int(case[0][1]) == 8 else 1.0
        check(practice.stage.count_in.spoken == Array(case[2],TYPE_INT,"",null),
            "%s speaks %s, got %s" % [str(case[0]),str(case[2]),
                str(practice.stage.count_in.spoken)])
        check(practice.stage.count_in.circles == (case[2] as Array).size(),
            "%s shows one circle per pulse" % str(case[0]))
        var on_pulses := true
        for i in range(practice.stage.count_in.spoken_at.size()):
            var at: float = practice.stage.count_in.spoken_at[i]
            on_pulses = on_pulses and absf(at*pulse-(-bar+pulse*i)) < .02
        check(on_pulses,"%s cues fall evenly on the pulses: %s" % [
            str(case[0]),str(practice.stage.count_in.spoken_at)])

func _test_resumed_count_in_cues_fall_on_beats() -> void:
    # R1 M4: Resume landing at -1.34 used to speak "San" at once and "Shi"
    # 0.34 beat later. A cue observed late is consumed; "Shi" is on -1.0.
    var practice := Practice.new()
    var owner = _coordinator(practice)
    var resumed := _state("count_in",8,true)
    resumed["bpm"] = 60.0
    resumed["count_in_bar_beats"] = 4
    resumed["count_in_beats"] = 4.0
    resumed["count_in_meter"] = [4,4]
    resumed["resume_count_in_beat"] = -1.34
    for at in range(1000,2400,16):
        owner.update(resumed,1000,NAN,at)
    var spoken: Array = practice.stage.count_in.spoken
    var at_beats: Array = practice.stage.count_in.spoken_at
    check(spoken == [4],"only the beats still ahead are spoken, got %s" % str(spoken))
    check(at_beats.size() == 1 and absf(float(at_beats[0])+1.0) < .02,
        "the resumed cue falls on its beat, at %s" % str(at_beats))

func _initialize() -> void:
    _test_compound_meter_count_in()
    _test_resumed_count_in_cues_fall_on_beats()
    _test_unannounced_rest_is_silent()
    _test_retry_lead_after_slowdown_meets_reserved_onset()
    _test_count_in_at_announced_tempo()
    _test_flow_rate_switch()
    _test_binding()
    _test_count_in()
    print("CONTINUATION_PLAN_FAILURES:",failures)
    quit(1 if failures else 0)
