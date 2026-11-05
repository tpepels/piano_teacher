extends SceneTree
## Exact prepared-ink promotion without clearing score, dispatching layout,
## or interrupting the authoritative transport. No MIDI/hardware required.
const Runway := preload("res://score_runway.gd")
const Session := preload("res://score_asset_session.gd")
const StepTimeline := preload("res://score_step_timeline.gd")

class MockView:
    extends Control
    signal retained_ink_compiled
    var stream_enabled := false
    var native_ready := true
    var runway_origin_beat := 0.0
    var runway_cutoff_beat := INF
    var runway_overlay := true
    var retained_annotations := Node2D.new()
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
    var marker_call: Dictionary = {}
    func _init() -> void:
        add_child(score_frame)
        renderer = MockView.new()
        score_frame.add_child(renderer)
    func present_runway_steps(_state: Dictionary, _visual_beat: float,
            next_start: float = INF, _label: String = "",
            next_density: float = NAN) -> void:
        marker_call = {"start":next_start,"density":next_density}

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
    runway._report = MockRequest.new()
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
    # Dense future engraving can differ substantially from the current page.
    # Its title marker must use the future renderer's pixels per beat.
    future.timeline["pixels_per_beat"] = 160.0
    runway._future_intro_offset = 2.25
    var old_renderer = stage.renderer
    # A fully retained late score must remain invisible until the engine
    # confirms its delayed global origin; provisional placement would jump.
    runway.present_frame({
        "loaded":true,"practice_timeline":{"stride_beats":4.0},
        "visual_offset_beats":0.0,"duration_beats":4.0,
        "bpm":120.0,
        "streak":2,"clean_runs_required":3,"target_bpm":120.0,
        "phase":"feedback"},20.0)
    check(future.modulate.a < .01 and
        absf(old_renderer.runway_cutoff_beat - 4.4) < .0001,
        "late score remains hidden until the backend confirms its global origin")

    # A late next-stage preload moves its global origin forward without
    # changing the scrolling source camera or presenting a stale score.
    runway.present_frame({
        "loaded":true,"practice_timeline":{"stride_beats":4.0},
        "visual_offset_beats":0.0,"duration_beats":4.0,
        "next_stage_start_beat":21.75,"bpm":120.0,
        "streak":2,"clean_runs_required":3,"target_bpm":120.0,
        "phase":"feedback"},20.0)
    check(absf(future.previous_camera + 1.75) < .0001,
        "delayed future ink follows the authoritative global start beat")
    check(absf(old_renderer.runway_cutoff_beat - 21.75) < .0001,
        "outgoing notation clips only when delayed future ink begins")
    check(absf(float(stage.marker_call.get("start",INF)) - 24.0) < .0001 and
        absf(float(stage.marker_call.get("density",NAN)) - 160.0) < .0001,
        "upcoming title is anchored at the actual first attack with future score density")
    check(old_renderer.cleared == 0,
        "extending an unprepared runway never clears the active score")
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
    # Real staff rest at the START of the same source measure. Returning
    # measure.start_beat (the former implementation) incorrectly labels that rest.
    var written := {
        "notes":[{"hand":"right","onset_beats":5.251},
                 {"hand":"left","onset_beats":9.0}],
        "notation_events":[
            {"kind":"rest","hand":"right","beat":4.0},
            {"kind":"note","hand":"right","is_attack":false,"beat":4.5},
            {"kind":"note","hand":"right","is_attack":true,"beat":5.25},
            {"kind":"note","hand":"left","is_attack":true,"beat":9.0}],
        "measures":[{"start_beat":0.0,"end_beat":4.0},
                    {"start_beat":4.0,"end_beat":8.0},
                    {"start_beat":8.0,"end_beat":12.0}]
    }
    check(StepTimeline.first_playable_beat(written,"right") == 5.25 and
          StepTimeline.first_playable_beat(written,"left") == 9.0 and
          StepTimeline.first_playable_beat(written,"both") == 5.25,
          "active and preloaded lesson titles follow their first actual printed attack")
    check(StepTimeline.first_playable_beat(
            {"notes":[{"hand":"right","onset_beats":5.251}]}, "right") == 5.251,
          "MIDI-only score fixtures use real source attack beats")
    check(not is_finite(StepTimeline.first_playable_beat(
            {"notes":[],"notation_events":[{"kind":"rest","beat":0.0}]},"both")),
          "rest-only scores must not place titles on invented notes")
    var overlay_beat := 23.0
    markers.set_density(97.0)
    markers.present({"loaded":true,"lesson_step":2,"lesson_steps":3},
        overlay_beat,12.17,24.0,"Next source",160.0)
    # Native future score: .33*width + (first_attack-(global - origin))*future_density
    var future_note_x: float = 900.0*.33 + (2.25-(overlay_beat-21.75))*160.0
    check(absf(StepTimeline.marker_x(markers._next_start,overlay_beat,
            markers._next_density,markers.size.x)-future_note_x) < .0001 and
          markers._density == 97.0 and markers._next_density == 160.0,
          "stage labels align in native pixels across different score densities")
    runway._future = null
    runway._bundle.clear()
    runway.present_frame({
        "loaded":true, "mode":"practice",
        "lesson_step":2,"lesson_steps":3,
        "visual_offset_beats":12.17,"duration_beats":4.0,
        "bpm":120.0,"target_bpm":120.0,
        "streak":2,"clean_runs_required":3,
        "phase":"feedback"},16.4)
    check(absf(stage.renderer.runway_cutoff_beat - 4.4) < .0001,
        "unready future stage never exposes stale repeated source notes")
    check(stage.renderer.cleared == 0,
        "failed future score must not clear the active renderer")

    runway._register_preload_failure("temporary glyph atlas error")
    check(runway._native_failures == 1 and not runway._terminal_preload_failure,
        "first native failure retains retryable runway")
    runway._register_preload_failure("temporary glyph atlas error")
    check(runway._native_failures == 2 and not runway._terminal_preload_failure,
        "second native failure remains bounded and retryable")
    runway._register_preload_failure("permanent native ink error")
    check(runway._terminal_preload_failure,
        "third native failure terminates the rendering retry loop")
    runway._request_if_needed({
        "loaded":true,"mode":"practice","lesson_step":2,
        "lesson_steps":3},Time.get_ticks_msec()+6000)
    check(runway._report.requested == ["score.stage_failed"],
        "terminal native failure reports to authoritative in-process engine")
    var report: Dictionary = runway._report.payloads[0]
    check(str(report.get("fingerprint","")) == "piece-a" and
        int(report.get("step_number",-1)) == 3 and
        int(report.get("revision",-1)) == 3,
        "report is scoped to exact upcoming fingerprint, step and revision")
    runway._on_report_reply(0, '{"accepted":true}'.to_utf8_buffer())
    runway._request_if_needed({
        "loaded":true,"mode":"practice","lesson_step":2,
        "lesson_steps":3},Time.get_ticks_msec()+10000)
    check(runway._report.requested.size() == 1,
        "accepted terminal report does not duplicate failure commands")
    print("SEAMLESS_SCORE_RUNWAY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
