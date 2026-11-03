extends SceneTree
## Exact prepared-ink promotion without clearing score, dispatching layout,
## or interrupting the authoritative transport. No MIDI/hardware required.
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
    var cleared := 0
    var timeline := {"pixels_per_beat": 100.0}
    var previous_camera := NAN
    func present_clock(_clock: float, visual: float = NAN) -> void:
        previous_camera = visual
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
    func request(operation: String, _payload: Dictionary = {}) -> Error:
        requested.append(operation)
        return OK
    func cancel_request() -> void:
        pass

var failures := 0

func check(ok: bool, title: String) -> void:
    if not ok:
        failures += 1
        print("SEAMLESS_SCORE_RUNWAY_FAILED:",title)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var stage := MockStage.new()
    root.add_child(stage)
    var session := Session.new(stage.renderer)
    var requests := []
    session.request_requested.connect(func(_kind, _id, _op, _timeout):
        requests.append(true))
    session.adopt_prepared({
        "loaded":true,"revision":1,"piece_fingerprint":"piece-a"},
        stage.renderer,{"anchors":[]})
    check(session.is_ready() and requests.is_empty(),
        "prepared native ink never starts another layout request")

    var runway := Runway.new()
    root.add_child(runway)
    runway.stage = stage
    runway.score_session = session
    runway._fetch = MockRequest.new()
    runway._ack = MockRequest.new()
    runway._source_fingerprint = "piece-a"
    runway._source_revision = 1
    runway._source_step = 1
    runway._acknowledged = true
    runway._bundle = {
        "fingerprint":"piece-a", "revision":2,
        "step_number":2, "stage_key":"next-stage"}
    runway._layout = {"anchors":[]}
    var future := MockView.new()
    stage.score_frame.add_child(future)
    runway._future = future
    var old_renderer = stage.renderer
    var proposed := {
        "loaded":true,"revision":2,"piece_fingerprint":"piece-a",
        "lesson_step":2,"visual_offset_beats":12.17}
    check(runway.promote_if_ready(proposed),
        "fully acknowledged future ink must promote immediately")
    check(stage.renderer == future and session._renderer == future,
        "same precompiled renderer must become the authoritative view")
    check(session.revision == 2 and session.is_ready(),
        "promoted score remains ready at the new revision")
    check(runway._tail == old_renderer and is_instance_valid(old_renderer),
        "prior notes must remain in the viewport after promotion")
    check(old_renderer.runway_overlay and
        absf(old_renderer.runway_cutoff_beat - 12.17) < .0001,
        "outgoing score clips its future copies at the stage boundary")
    runway._advance_tail(15.0)
    check(absf(old_renderer.previous_camera - 15.0) < .0001,
        "outgoing score scrolls at the same global beat as new score")
    check(absf(stage.renderer.runway_origin_beat - 12.17) < .0001,
        "new stage keeps global scroll origin")
    check(stage.renderer.runway_overlay == false,
        "after promotion score owns complete staff and ink")
    session.update_context(proposed,1000)
    check(requests.is_empty() and old_renderer.cleared == 0,
        "same score revision must not clear the old view or reload ink")
    runway._advance_tail(20.0)
    check(runway._tail == null,
        "outgoing ink is released only after its last note leaves the viewport")

    runway._next_poll_ms = 0
    runway._request_if_needed({
        "loaded":true,"mode":"practice","lesson_step":2,
        "lesson_steps":3},1001)
    check(runway._fetch.requested == ["score.next_stage"],
        "lesson count published by engine starts the next preloader")
    runway._request_if_needed({
        "loaded":true,"mode":"practice","lesson_step":3,
        "lesson_steps":3},1002)
    check(runway._fetch.requested.size() == 1,
        "last stage must not generate another future score")

    var markers := StepTimeline.new()
    root.add_child(markers)
    markers.size = Vector2(900,34)
    markers.set_density(97.0)
    markers.present({"loaded":true,"lesson_step":2,
        "stage_label":"Both hands"},12.17,12.17,21.0,"Next source")
    check(markers._step == 2 and markers._next_start == 21.0,
        "stage markers share current scroll and upcoming score axis")
    print("SEAMLESS_SCORE_RUNWAY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
