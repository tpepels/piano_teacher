extends RefCounted
## Single owner of visual state reconciliation and renderer presentation order.
## A state poll updates canonical time, score assets, preloading and physical
## admission in ONE transaction-like order before any stage is painted.
## Main owns the scene tree and event requests, not this domain sequence.
const TempoTimeline := preload("res://tempo_timeline.gd")
const LivingScore := preload("res://living_score.gd")
const StatusHeadPreloader := preload("res://status_head_preloader.gd")

var visual_clock
var score_flow
var guided
var score_session
var runway
var admission
var practice_view
var score_effects
var demo_player
var feedback
var metronome
var frames
var source_groups: Array = []
var frame_diagnostics := false
var listen_diagnostics := false
var smoke := false
var _status_preloader := StatusHeadPreloader.new()

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

func bind_frames(feedback_session, metronome_frame, frame_coordinator,
        diagnostics: bool, listen_sync: bool, phase0_smoke: bool) -> void:
    feedback = feedback_session
    metronome = metronome_frame
    frames = frame_coordinator
    frame_diagnostics = diagnostics
    listen_diagnostics = listen_sync
    smoke = phase0_smoke
    score_session.assets_invalidated.connect(_source_invalidated)
    score_session.layout_published.connect(_layout_published)
    score_session.score_published.connect(_score_published)
    score_session.score_failed.connect(_score_failed)
    score_session.status_changed.connect(refresh_status)

func score_ready() -> bool:
    return score_session.is_ready()

func refresh_status(status: Dictionary = {}) -> void:
    var values: Dictionary = status.duplicate() if not status.is_empty() else score_session.status()
    if runway != null and runway.staff_renderer() != null and \
            not bool(values.get("retry_visible",false)) and str(values.get("error","")).is_empty():
        values["visible"] = false
    practice_view.present_score(values)

func _source_invalidated(_revision: int) -> void:
    feedback.source_invalidated()
    source_groups.clear()

func _layout_published(revision: int, values: Dictionary) -> void:
    source_groups = LivingScore.prepare(values)
    feedback.layout_published(values,revision)

func _score_published(revision: int) -> void:
    if runway != null:
        runway.active_revision_published(revision)
    if smoke:
        print("PHASE0_SCORE_READY_NATIVE: REVISION:",revision)
    var renderer = practice_view.stage.renderer
    print("NATIVE_MODEL_READY: ",revision," NOTES: ",renderer.timeline.notes.size(),
        " DENSITY: ",renderer.timeline.pixels_per_beat)
    _status_preloader.warm(renderer)

func _score_failed(message: String) -> void:
    if smoke:
        print("PHASE0_SCORE_ERROR:",message)
    practice_view.present_message(message)

func retry_score() -> void:
    score_session.retry(Time.get_ticks_msec())

func advance(state: Dictionary, state_tick_ms: int, now_ms: int,
        delta: float, busy: bool, screen: String, precise_ms: float = NAN) -> void:
    # One sampled frame instant, one source beat and one forward world
    # coordinate feed every consumer in this fixed presentation order.
    # Hold/release is a projection operation, not a backend command.
    # Apply it on EVERY displayed frame. A Resume intent can be admitted
    # before the next state receipt; a one-time paused-state hold would
    # otherwise trap the source world behind its old limit indefinitely.
    score_session.advance_preparation()
    guided.update_hold(state)
    var frame_ms: float = precise_ms if is_finite(precise_ms) else float(now_ms)
    var beat: float = transport_beat(state,frame_ms)
    var world: float = score_flow.sample(frame_ms)
    feedback.poll(now_ms,score_session.layout_revision
        if score_session.layout_revision == score_session.revision else -1)
    metronome.update(state,state_tick_ms,beat,now_ms)
    present_frame(state,beat,world)
    var arrivals: Array = frames.advance(state,beat,world,now_ms,delta,busy,
        screen,score_ready(),source_groups,frame_diagnostics,listen_diagnostics,smoke,frame_ms,
        runway.staff_renderer() if runway != null else null)
    if not arrivals.is_empty():
        score_effects.record_preview(arrivals,practice_view.stage)
    if runway != null:
        runway.present_frame(state,world)

func _source_rate(state: Dictionary, beat: float) -> float:
    var nominal: float = float(state.get("bpm",40.0))
    if bool(state.get("running",false)) or bool(state.get("paused",false)):
        return TempoTimeline.bpm_at_beat(
            beat,nominal,state.get("tempo_segments",[]))
    return nominal

func transport_beat(state: Dictionary, at_ms: float) -> float:
    return visual_clock.score_beat(at_ms) if visual_clock.matches(state) \
        else float(state.get("clock_beat",0.0))

func present_frame(state: Dictionary, beat: float, world: float) -> void:
    # Single native stream presentation owner. The frame coordinator
    # consumes only visual effects; it must never attempt another queue
    # lifecycle reconciliation from the same or stale backend snapshot.
    # Unloaded/reloading states still have previously exposed clips that
    # must leave by the same forward world coordinate.
    var renderer = practice_view.stage.renderer
    if renderer == null or not is_instance_valid(renderer):
        return
    renderer.present_clock(beat,world-float(renderer.runway_origin_beat))
    renderer.present_flow(world,state,beat)
    practice_view.stage.feedback.present_source_beat(state,beat)
    # The trace uses the shared world projection, including run offsets.
    # It owns no musical clock and never assigns a grade.
    practice_view.stage.attack_trace.present(
        practice_view.stage.feedback.attack_markers(),practice_view.stage.feedback,score_flow,world)


func accept(state: Dictionary, request_midpoint_ms: int,
        received_ms: int) -> void:
    score_effects.transition_mode(state,practice_view.stage)
    visual_clock.accept(state,request_midpoint_ms,received_ms)
    # Both the source beat and scrolling world must see the same timeline
    # publication. Do not evaluate the new take ID against the old timeline.
    score_flow.follow(state.get("musical_timeline"),received_ms)
    var beat: float = transport_beat(state,received_ms)
    guided.update_hold(state)
    var playback: Variant = state.get("playback_timeline")
    var authorized: Variant = playback.get("current") \
        if playback is Dictionary else null
    if authorized is Dictionary:
        score_flow.sample(received_ms)
    else:
        # This is an uncommitted source's projected BPM. The canonical
        # flow refuses to install it over already-authorized predecessor
        # epochs while the next source is still awaiting physical ACK.
        score_flow.sample_uncommitted(received_ms,_source_rate(state,beat))
    if runway != null:
        runway.preserve_unprepared_revision(state)
    if demo_player != null and bool(state.get("loaded",false)):
        demo_player.synchronize(state,beat)
    score_session.update_context(state,received_ms)
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
        # A newly accepted PLAYING snapshot can be observed by the UI
        # before the next process frame. Bind its already-attested stream
        # owner NOW, in this same accepted-state transaction, so there is
        # never a frame with a running transport and missing source ink.
        # The later process-frame projection remains idempotent.
        present_frame(state,beat,score_flow.project(received_ms))
    elif admission != null:
        admission.observe(state,received_ms)
