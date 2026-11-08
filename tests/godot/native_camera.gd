extends SceneTree
# Replace HTTP only. UI, authenticated assets, callbacks, count-in, clock and
# the actual native CanvasItem run unchanged. No server or MIDI device needed.
class SilentRequest extends RefCounted:
    # Accepts a score command and never answers; the fixture supplies the
    # authentic responses itself.
    var timeout := 5.0
    func request(_operation: String, _payload: Dictionary = {}) -> int:
        return OK
    func cancel_request() -> void:
        pass

class OfflineRequest extends RefCounted:
    var timeout := 5.0
    func request(_operation: String, _payload: Dictionary = {}) -> int:
        return OK

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        super._ready()
        set_process(false)
        state_poll_timer.stop()
        score_queue.layout_request = SilentRequest.new()
        score_queue.model_request = SilentRequest.new()
        action_request = OfflineRequest.new()
        native_started = true  # No engine: every response is supplied below.

    func _poll() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_library() -> void:
        pass

    func _request_timeline_model() -> void:
        pass

var app: Control
var samples: Array = []
const FINGERPRINT := "native-camera-fixture"
# A fast tempo keeps the wall-clock wait for a take to reach the screen short.
const BPM := 240.0
var attempt := 100
# World position of source beat 0 for the take being sampled. The monotonic
# world axis is wall-clock time (ContinuousScoreFlow); the engine's transport
# clock is that axis relative to this origin.
var take_origin := 0.0
var clock_matched := true

func _initialize() -> void:
    call_deferred("run")

func draw_frame() -> void:
    if bool(app.last_state.get("running", false)) and not bool(app.last_state.get("paused", false)):
        app.last_state.phase = "count_in" if app._transport_beat_now() < 0.0 else "playing"
    app._process(0.0)
    clock_matched = clock_matched and app.visual_transport_clock.matches(app.last_state) \
        and absf(app.practice_view.stage.renderer.clock_beat - app._transport_beat_now()) < .01
    await process_frame
    await process_frame

func set_state(beat: float, running: bool, paused := false, play_from := 0.0,
        new_transport := true) -> void:
    # Each Play/Restart is one transport; pause, resume and the camera
    # samples inside it keep their transport id.
    if new_transport:
        attempt += 1
    app.last_state = {"loaded":true, "revision":app.revision,
        "piece_fingerprint":FINGERPRINT, "transport_id":attempt, "mode":"practice", "hand":"both",
        "phase":"paused" if paused else "count_in" if beat < 0.0 else
            "playing" if running else "ready",
        "running":running, "paused":paused, "clock_beat":beat,
        "bpm":BPM, "play_from_beat":play_from,
        "count_in_beats":4, "count_in_bar_beats":4,
        "duration_beats":app.practice_view.stage.renderer.timeline.duration_beats}
    app.last_state_tick = Time.get_ticks_msec()
    app.visual_transport_clock.accept(app.last_state, app.last_state_tick, app.last_state_tick)

func begin_take(action: String, play_from: float) -> bool:
    # Play and Restart go through the one production route: a preflighted
    # reservation binds a prepared take, and the engine's acknowledgement
    # arms it. An unreserved transport cannot create note ink.
    set_state(0.0, false, false, play_from)
    await draw_frame()
    var view = app.practice_view.stage.renderer
    var deadline := Time.get_ticks_msec() + 5000
    while not view.retained_ready() and Time.get_ticks_msec() < deadline:
        await process_frame
    app._send_action({"action": action})
    if not app.command_state.pending:
        push_error("Transport action was refused: no reservation reached the engine")
        return false
    var armed: int = view._stream_armed_serial
    for item in view._stream_queue.online:
        if int(item.get("take_owner", item["serial"])) == armed:
            take_origin = float(item["world_origin"])
            break
    attempt += 1
    app._on_action(0, JSON.stringify({"loaded":true, "revision":app.revision,
        "phase":"count_in", "running":true, "paused":false, "mode":"practice",
        "piece_fingerprint":FINGERPRINT, "transport_id":attempt, "hand":"both", "bpm":BPM, "clock_beat":-2.5,
        "play_from_beat":play_from, "count_in_beats":4, "count_in_bar_beats":4,
        "duration_beats":app.practice_view.stage.renderer.timeline.duration_beats}).to_utf8_buffer())
    return true

func transport_clock(play_from: float) -> float:
    return app.score_flow.project(Time.get_ticks_msec()) - take_origin - play_from

func tick(running: bool, paused: bool, play_from: float, frozen_clock := NAN) -> void:
    # The engine reports its transport clock; a paused engine holds it while
    # the visual world axis keeps moving.
    var clock: float = frozen_clock if is_finite(frozen_clock) else transport_clock(play_from)
    set_state(clock, running, paused, play_from, false)
    await draw_frame()

func run_until_musical(beat: float, play_from: float) -> bool:
    var view = app.practice_view.stage.renderer
    var deadline := Time.get_ticks_msec() + 12000
    while Time.get_ticks_msec() < deadline:
        await tick(true, false, play_from)
        if view.stream_world_beat - take_origin >= beat:
            return true
    push_error("The reserved take never reached beat %.2f" % beat)
    return false

func capture(label: String) -> Dictionary:
    var view = app.practice_view.stage.renderer
    var heads: Array = []
    for event in view.layout.ordered_events:
        var id: String = str(event.get("id", ""))
        if not view.drawn_noteheads.has(id):
            continue
        var point: Vector2 = view.drawn_noteheads[id]
        heads.append({"id":id, "onset":float(event.beat), "x":point.x, "y":point.y})
    # The beat under the fixed playhead on the monotonic world axis.
    var musical: float = view.stream_world_beat - take_origin
    var sample := {"label":label, "heads":heads, "width":view.size.x,
        "height":view.size.y, "density":view.timeline.pixels_per_beat,
        "clock":musical-view.play_from_beat, "play_from":view.play_from_beat,
        "musical_beat":musical, "playhead_x":view.size.x*view.PLAYHEAD_FRACTION,
        "staff_gap":view.staff_gap(), "visible_count":app._visible_score_noteheads()}
    samples.append(sample)
    return sample

func run() -> void:
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    root.size = Vector2i(1600, 1000)
    app = FixtureApp.new()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    app._navigate("practice")
    if app.practice_view.stage.renderer == null or app.practice_view.stage.renderer.get_script() != load(
            "res://notation/native/view.gd"):
        push_error("Production camera must use the app's native notation view")
        quit(1)
        return
    # The score session owns revision and request lifecycle: select the
    # revision through a state snapshot, then answer its layout and model.
    app.last_state = {"loaded":true, "phase":"ready", "revision":int(payload.model.revision),
        "piece_fingerprint":FINGERPRINT}
    app.score_session.update_context(app.last_state, Time.get_ticks_msec())
    app._on_layout(0, JSON.stringify(payload.layout).to_utf8_buffer())
    app._on_timeline_model(0, JSON.stringify(payload.model).to_utf8_buffer())
    # Readiness includes the retained CanvasItems compiling after their draw.
    var ready_deadline := Time.get_ticks_msec() + 5000
    while not app._native_score_ready() and Time.get_ticks_msec() < ready_deadline:
        await process_frame
    if not app._native_score_ready():
        push_error("Real fixture assets and model must prepare the production view")
        quit(1)
        return
    var view = app.practice_view.stage.renderer
    var timeline = view.timeline
    var events: Array = view.layout.ordered_events
    var textures: Dictionary = view.glyphs.textures.duplicate()
    set_state(0.0, false)
    await draw_frame()
    await process_frame
    await process_frame
    var ready_frame: Dictionary = capture("ready")
    # READY ink is a hidden immutable take outside the right viewport edge
    # (docs/architecture/immutable-score-queues.md): it must be prepared and
    # compiled, but no notehead may be on screen before Play.
    var opening_attack_exists := false
    var initial_cursor_x: float = view.size.x * view.PLAYHEAD_FRACTION
    for event in view.layout.ordered_events:
        if str(event.get("kind", "")) != "note" or bool(event.get("chord", false)):
            continue
        var predicted_x: float = initial_cursor_x + \
            (float(event.get("beat", 0.0)) - view.play_from_beat) * \
            timeline.pixels_per_beat
        if predicted_x >= 0.0 and predicted_x < view.size.x:
            opening_attack_exists = true
            break
    if int(ready_frame.visible_count) != 0 or view._stream_queue.online.is_empty():
        push_error("READY must hold a hidden offscreen take and show no ink before Play")
        quit(1)
        return
    if not opening_attack_exists:
        push_error("Fixture needs an opening attack that fits the camera")
        quit(1)
        return
    var short_passage: bool = view.timeline.duration_beats * view.timeline.pixels_per_beat < view.size.x * .91
    if not await begin_take("start", 0.0):
        quit(1)
        return
    # Count-in: the take travels in from offscreen before its clock reaches 0.
    if not await run_until_musical(-3.0, 0.0):
        quit(1)
        return
    print("NATIVE_CAMERA_TRANSPORT_BEGIN")
    var lead_samples := 0
    var playing_samples := 0
    for index in range(10):
        await tick(true, false, 0.0)
        var moving: Dictionary = capture("lead" if float(view.stream_world_beat-take_origin) < 0.0 else "playing")
        if str(moving.label) == "lead":
            lead_samples += 1
        else:
            playing_samples += 1
        await create_timer(.15).timeout
    print("NATIVE_CAMERA_TRANSPORT_END")
    # Pause holds the engine clock only; the visual axis is monotonic.
    var hold: float = float(samples[-1].clock)
    await tick(true, true, 0.0, hold)
    var paused: Dictionary = capture("paused")
    await create_timer(.15).timeout
    await tick(true, true, 0.0, hold)
    var later: Dictionary = capture("paused")
    var pause_axis_continues := float(later.musical_beat) > float(paused.musical_beat)
    for head in paused.heads:
        for other in later.heads:
            if other.id == head.id:
                pause_axis_continues = pause_axis_continues and absf(
                    (float(head.x) - float(other.x)) - (
                    float(later.musical_beat) - float(paused.musical_beat)) *
                    float(paused.density)) < .5
    await tick(true, false, 0.0)
    var resumed: Dictionary = capture("resume")
    await create_timer(.15).timeout
    await tick(true, false, 0.0)
    var advanced: Dictionary = capture("resume")
    # Restart from bar 2 and a later resize go through the same reservation.
    if not await begin_take("restart", 3.0):
        quit(1)
        return
    if not await run_until_musical(3.0 - 3.0, 3.0):
        quit(1)
        return
    await tick(true, false, 3.0)
    capture("seek")
    root.size = Vector2i(960, 720)
    # A resize recompiles every retained strip; ink returns once they compile.
    var resize_deadline := Time.get_ticks_msec() + 5000
    while not view.retained_ready() and Time.get_ticks_msec() < resize_deadline:
        await tick(true, false, 3.0)
    await tick(true, false, 3.0)
    await tick(true, false, 3.0)
    capture("seek")
    # A stopped score returns to READY: its new take waits offscreen.
    set_state(0.0, false)
    await draw_frame()
    capture("stopped")
    if not await begin_take("restart", 0.0):
        quit(1)
        return
    if not await run_until_musical(-3.0, 0.0):
        quit(1)
        return
    await tick(true, false, 0.0)
    capture("restart")
    var indexed: Array = view._visible_events(0.0, 1.0)
    var beats: Array = []
    for event in indexed:
        beats.append(float(event.beat))
    var report := {"samples":samples, "short_passage":short_passage,
        "screen":app.current_screen, "native_ready":app._native_score_ready(),
        "lead_samples":lead_samples, "playing_samples":playing_samples,
        "pause_axis_continues":pause_axis_continues,
        "resume_advanced":float(advanced.clock) > float(resumed.clock),
        "clock_matched":clock_matched, "clipped":app.practice_view.stage.score_frame.clip_contents,
        "same_timeline":view.timeline == timeline,
        "same_index":is_same(view.layout.ordered_events, events),
        "same_atlas":view.glyphs.textures == textures,
        "indexed_beats":beats, "scanned_events":view.frame_scanned_events,
        "total_events":view.layout.ordered_events.size(),
        "high_click_bytes":app.click_high.data.size(),
        "low_click_bytes":app.click_low.data.size(),
        "click_stream_selected":app.click_player.stream != null}
    print("NATIVE_CAMERA_REPORT:", JSON.stringify(report))
    app.queue_free()
    await process_frame
    quit(0)
