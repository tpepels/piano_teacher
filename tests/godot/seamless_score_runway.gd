extends SceneTree
## One immutable forward-world-axis lifecycle: future score is precompiled,
## its requested lead is acknowledged, and its graded downbeat stays offscreen.
const Runway := preload("res://score_runway.gd")
const Session := preload("res://score_asset_session.gd")
const StepTimeline := preload("res://score_step_timeline.gd")

class MockView:
    extends Control
    signal retained_ink_compiled
    var native_ready := true
    var runway_origin_beat := 0.0
    var runway_cutoff_beat := INF
    var runway_overlay := true
    var retained_annotations := Node2D.new()
    var cleared := 0
    var timeline := {"pixels_per_beat": 100.0}
    var stream_passes: Array = []
    var last_world := -INF
    var arm_calls := 0
    var armed_world := NAN
    func _stream_right_beats() -> float:
        return 6.0
    func _stream_header_beats(_opening: float) -> float:
        return 3.5
    func arm_stream_take(world: float, _opening: float,
            planned: float = NAN) -> Dictionary:
        arm_calls += 1
        if not is_finite(planned) or planned <= world+9.5:
            return {}
        armed_world = planned
        stream_passes.append({"world_origin":planned,
            "source_floor":0.0,"source_ceiling":8.0})
        return {"start_world":planned}
    func present_flow(world: float, _state: Dictionary,
            _graded: float, _admission: bool = true) -> void:
        if last_world > world:
            push_error("Moving score went backwards")
        last_world = world
        for i in range(stream_passes.size()-1,-1,-1):
            if float(stream_passes[i]["world_origin"]) + \
                    float(stream_passes[i]["source_ceiling"]) < world:
                stream_passes.remove_at(i)
    func retained_ready() -> bool:
        return true
    func clear_score() -> void:
        cleared += 1
    func set_transport_overlay_enabled(_enabled: bool) -> void:
        pass

class MockStage:
    extends Node
    var renderer
    var score_frame := Control.new()
    func _init() -> void:
        add_child(score_frame)
        renderer = MockView.new()
        score_frame.add_child(renderer)

class MockRequest:
    extends Node
    var _pending_id := -1
    var requested: Array[String] = []
    var payloads: Array[Dictionary] = []
    func request(operation: String, payload: Dictionary = {}) -> Error:
        requested.append(operation)
        payloads.append(payload)
        return OK
    func cancel_request() -> void:
        pass

var failures := 0
func check(ok: bool, reason: String) -> void:
    if not ok:
        failures += 1
        print("SEAMLESS_SCORE_RUNWAY_FAILED:",reason)
func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var stage := MockStage.new()
    root.add_child(stage)
    var session := Session.new(stage.renderer)
    session.adopt_prepared({
        "loaded":true,"revision":1,"piece_fingerprint":"piece-a"},
        stage.renderer,{"anchors":[]})
    check(session.is_ready(),"prepared score is already retained")
    var runway := Runway.new()
    root.add_child(runway)
    runway.stage = stage
    runway.score_session = session
    runway._fetch = MockRequest.new()
    runway._ack = MockRequest.new()
    runway._report = MockRequest.new()
    runway._source_fingerprint = "piece-a"
    runway._source_revision = 1
    runway._source_step = 1
    runway._bundle = {"fingerprint":"piece-a","revision":2,
        "step_number":2,"stage_key":"next-stage"}
    runway._layout = {"anchors":[]}
    var future := MockView.new()
    future.timeline["pixels_per_beat"] = 160.0
    stage.score_frame.add_child(future)
    runway._future = future
    stage.renderer.stream_passes = [{
        "world_origin":18.0,"source_floor":0.0,"source_ceiling":12.0}]
    var old = stage.renderer
    runway.present_frame({"loaded":true,"phase":"feedback"},20.0)
    check(future.modulate.a < .01,
        "unacknowledged future score cannot flash onscreen")
    check(runway._ack.requested == ["score.stage_ready"],
        "future copy acknowledges the actual compiled native ink")
    var request: Dictionary = runway._ack.payloads[0]
    check(str(request.get("stage_key","")) == "next-stage" and \
        float(request.get("presentation_lead_beats",0.0)) >= 10.0,
        "future handoff reserves its whole header and visible right horizon")

    runway._acknowledged = true
    runway._ack_waiting = false
    var early: Dictionary = {
        "loaded":true,"revision":2,"piece_fingerprint":"piece-a",
        "lesson_step":2,"clock_beat":-2.0}
    check(runway.promote_if_ready(early) == false,
        "backend deadline too close to playhead must be rejected")
    check(stage.renderer == old and old.cleared == 0,
        "a late handoff cannot silently seek or replace the old bar")
    var ready: Dictionary = early.duplicate(true)
    ready["clock_beat"] = -14.0
    check(runway.promote_if_ready(ready),
        "precompiled next lesson must promote with offscreen lead")
    check(stage.renderer == future and session._renderer == future and \
            session.revision == 2 and session.is_ready(),
        "same source-bound retained renderer becomes authoritative")
    check(future.arm_calls == 2 and \
            is_equal_approx(future.armed_world,34.0),
        "promoted future source keeps its exactly scheduled world coordinate")
    check(runway._tails == [old] and old.cleared == 0,
        "outgoing score survives until its own clips exit left")
    runway._advance_tails(29.0)
    check(runway._tails == [old] and old.last_world == 29.0,
        "previous notes scroll on the same one-way world axis")
    runway._advance_tails(31.0)
    check(runway._tails.is_empty(),
        "outgoing renderer is retired when its final note passes")
    # Two rapid promotions cannot destroy the older stage's still-visible
    # notes, even when an unrelated preload gets invalidated.
    var first_tail := MockView.new()
    stage.score_frame.add_child(first_tail)
    first_tail.stream_passes = [{
        "world_origin":33.0,"source_floor":0.0,"source_ceiling":12.0}]
    var second_tail := MockView.new()
    stage.score_frame.add_child(second_tail)
    second_tail.stream_passes = [{
        "world_origin":36.0,"source_floor":0.0,"source_ceiling":12.0}]
    runway._retain_tail(first_tail)
    runway._retain_tail(second_tail)
    runway._discard()
    check(runway._tails.size()==2 and
        is_instance_valid(first_tail) and is_instance_valid(second_tail),
        "preload reset cannot remove either visible outgoing lesson")
    runway._advance_tails(46.0)
    check(runway._tails.size()==1 and runway._tails[0] == second_tail,
        "each outgoing lesson expires independently on the world axis")
    runway._advance_tails(49.0)
    check(runway._tails.is_empty(),
        "all outgoing renderers eventually retire without leaking nodes")
    runway._next_poll_ms = 0
    runway._request_if_needed({"loaded":true,"mode":"practice",
        "lesson_step":2,"lesson_steps":3},Time.get_ticks_msec()+1000)
    check(runway._fetch.requested == ["score.next_stage"],
        "preloader advances only when the next authentic step exists")
    runway._request_if_needed({"loaded":true,"mode":"practice",
        "lesson_step":3,"lesson_steps":3},Time.get_ticks_msec()+1001)
    check(runway._fetch.requested.size() == 1,
        "last lesson does not invent an extra source copy")
    var written := {"notes":[{"hand":"right","onset_beats":5.251},
                {"hand":"left","onset_beats":9.0}],
        "notation_events":[
            {"kind":"rest","hand":"right","beat":4.0},
            {"kind":"note","hand":"right","is_attack":true,"beat":5.25},
            {"kind":"note","hand":"left","is_attack":true,"beat":9.0}]}
    check(StepTimeline.first_playable_beat(written,"right")==5.25 and \
          StepTimeline.first_playable_beat(written,"left")==9.0,
          "source-local first attacks survive the world-time handoff")
    runway._future = null
    runway._bundle.clear()
    runway._register_preload_failure("temporary glyph atlas")
    runway._register_preload_failure("temporary glyph atlas")
    runway._register_preload_failure("permanent engraving error")
    check(runway._terminal_preload_failure,
        "third native failure terminates retries without fake notation")
    runway._request_if_needed({"loaded":true,"mode":"practice",
        "lesson_step":2,"lesson_steps":3},Time.get_ticks_msec()+7000)
    check(runway._report.requested == ["score.stage_failed"],
        "terminal failure uses single authoritative engine report")
    print("SEAMLESS_SCORE_RUNWAY_FAILURES:",failures)
    quit(0 if failures==0 else 1)
