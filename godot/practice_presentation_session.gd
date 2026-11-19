extends RefCounted
## Single owner of visual state reconciliation and renderer presentation order.
## A state poll updates canonical time, score assets, preloading and physical
## admission in ONE transaction-like order before any stage is painted.
## Main owns the scene tree and event requests, not this domain sequence.
const TempoTimeline := preload("res://tempo_timeline.gd")

var visual_clock
var score_flow
var guided
var score_session
var runway
var admission
var practice_view
var score_effects
var demo_player

func _init(clock, flow, guided_owner, assets, score_runway,
        score_gateway, practice, effects, demo) -> void:
    visual_clock = clock
    score_flow = flow
    guided = guided_owner
    score_session = assets
    runway = score_runway
    admission = score_gateway
    practice_view = practice
    score_effects = effects
    demo_player = demo

func _source_rate(state: Dictionary, beat: float) -> float:
    var nominal: float = float(state.get("bpm",40.0))
    if bool(state.get("running",false)) or bool(state.get("paused",false)):
        return TempoTimeline.bpm_at_beat(
            beat,nominal,state.get("tempo_segments",[]))
    return nominal

func transport_beat(state: Dictionary, at_ms: int) -> float:
    return visual_clock.score_beat(at_ms) if visual_clock.matches(state) \
        else float(state.get("clock_beat",0.0))

func present_frame(state: Dictionary, beat: float, world: float) -> void:
    # Single native stream presentation owner. The frame coordinator
    # consumes only visual effects; it must never attempt another queue
    # lifecycle reconciliation from the same or stale backend snapshot.
    if not bool(state.get("loaded",false)):
        return
    var renderer = practice_view.stage.renderer
    if renderer == null or not is_instance_valid(renderer):
        return
    renderer.present_clock(beat,world-float(renderer.runway_origin_beat))
    renderer.present_flow(world,state,beat)


func accept(state: Dictionary, request_midpoint_ms: int,
        received_ms: int) -> void:
    visual_clock.accept(state,request_midpoint_ms,received_ms)
    var beat: float = transport_beat(state,received_ms)
    guided.update_hold(state)
    var playback: Variant = state.get("playback_timeline")
    var authorized: Variant = playback.get("current") \
        if playback is Dictionary else null
    if authorized is Dictionary:
        score_flow.sample(received_ms)
    else:
        score_flow.sample(received_ms,_source_rate(state,beat))
    var prepared_stage_waiting: bool = runway != null and \
        runway.has_prepared_destination(state)
    if runway != null and not prepared_stage_waiting:
        runway.preserve_unprepared_revision(state)
    if demo_player != null and bool(state.get("loaded",false)):
        demo_player.synchronize(state,beat)
    if not prepared_stage_waiting:
        score_session.update_context(state,received_ms)
    if runway != null:
        runway.update_state(state,received_ms)
    if bool(state.get("loaded",false)) and practice_view.stage.renderer != null:
        var world: float = score_flow.project(received_ms)
        var current_renderer = practice_view.stage.renderer
        current_renderer.present(
            state,beat,world-float(current_renderer.runway_origin_beat))
        guided.publish_authorized_target(state,current_renderer,world,
            received_ms,
            visual_clock.backend_offset_ms
                if visual_clock.has_backend_offset else NAN,
            beat)
        # Backend snapshot can reach us before its present() reply. Reconcile
        # the receipt (including a prepared-stage promotion) before drawing
        # or binding its now-authorized target.
        if admission != null:
            admission.observe(state,received_ms)
        if practice_view.stage.renderer != current_renderer:
            var new_renderer = practice_view.stage.renderer
            new_renderer.present(
                state,beat,world-float(new_renderer.runway_origin_beat))
        practice_view.stage.renderer.present_flow(world,state,beat)
    elif admission != null:
        admission.observe(state,received_ms)
