extends SceneTree
# Replace HTTP only. UI, authenticated assets, callbacks, count-in, clock and
# the actual native CanvasItem run unchanged. No server or MIDI device needed.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        super._ready()
        set_process(false)
        state_poll_timer.stop()

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
var attempt := 100
var clock_matched := true

func _initialize() -> void:
    call_deferred("run")

func draw_frame() -> void:
    if bool(app.last_state.get("running", false)) and not bool(app.last_state.get("paused", false)):
        app.last_state.phase = "count_in" if app._transport_beat_now() < 0.0 else "playing"
    app._process(0.0)
    clock_matched = clock_matched and app.visual_transport_clock.matches(app.last_state) \
        and absf(app.timeline_preview.clock_beat - app._transport_beat_now()) < .01
    await process_frame
    await process_frame

func set_state(beat: float, running: bool, paused := false, play_from := 0.0) -> void:
    attempt += 1
    app.last_state = {"loaded":true, "revision":app.revision,
        "transport_id":attempt, "mode":"practice", "hand":"both",
        "phase":"paused" if paused else "count_in" if beat < 0.0 else
            "playing" if running else "ready",
        "running":running, "paused":paused, "clock_beat":beat,
        "bpm":120.0, "play_from_beat":play_from,
        "count_in_beats":.5, "count_in_bar_beats":4,
        "duration_beats":app.timeline_preview.timeline.duration_beats}
    app.last_state_tick = Time.get_ticks_msec()
    app.visual_transport_clock.accept(app.last_state, app.last_state_tick, app.last_state_tick)

func capture(label: String) -> Dictionary:
    var view = app.timeline_preview
    var heads: Array = []
    for event in view.ordered_events:
        var id: String = str(event.get("id", ""))
        if not view.drawn_noteheads.has(id):
            continue
        var point: Vector2 = view.drawn_noteheads[id]
        heads.append({"id":id, "onset":float(event.beat), "x":point.x, "y":point.y})
    var projected_clock: float = view.clock_beat if view.running or view.paused else 0.0
    var sample := {"label":label, "heads":heads, "width":view.size.x,
        "height":view.size.y, "density":view.timeline.pixels_per_beat,
        "clock":view.clock_beat, "play_from":view.play_from_beat,
        "musical_beat":view.play_from_beat+projected_clock,
        "staff_gap":view._gap(), "visible_count":app._visible_score_noteheads()}
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
    if app.timeline_preview == null or app.timeline_preview.get_script() != load(
            "res://notation/native/view.gd"):
        push_error("Production camera must use the app's native notation view")
        quit(1)
        return
    app.revision = int(payload.model.revision)
    app.last_state = {"loaded":true, "phase":"ready"}
    app.requested_layout_revision = app.revision
    app._on_layout(0, 200, PackedStringArray(), JSON.stringify(payload.layout).to_utf8_buffer())
    app._on_timeline_model(0, 200, PackedStringArray(), JSON.stringify(payload.model).to_utf8_buffer())
    if not app._native_score_ready():
        push_error("Real fixture assets and model must prepare the production view")
        quit(1)
        return
    var view = app.timeline_preview
    var timeline = view.timeline
    var events: Array = view.ordered_events
    var textures: Dictionary = view.glyphs.textures.duplicate()
    set_state(0.0, false)
    await draw_frame()
    capture("ready")
    var short_passage: bool = view.timeline.duration_beats * view.timeline.pixels_per_beat < view.size.x * .91
    set_state(-2.5, true)
    await draw_frame()
    set_state(-1.5, true)
    await draw_frame()
    # A short half-beat lead must scroll through zero at nominal BPM.
    print("NATIVE_CAMERA_TRANSPORT_BEGIN")
    set_state(-.5, true)
    var lead_samples := 0
    var playing_samples := 0
    for index in range(9):
        await draw_frame()
        capture("lead" if view.clock_beat < 0.0 else "playing")
        if view.clock_beat < 0.0:
            lead_samples += 1
        else:
            playing_samples += 1
        await create_timer(.06).timeout
    print("NATIVE_CAMERA_TRANSPORT_END")
    var first_playing: Dictionary = samples[-1]
    set_state(float(first_playing.clock), true, true)
    await draw_frame()
    var paused: Dictionary = capture("paused")
    await create_timer(.06).timeout
    await draw_frame()
    var frozen: Dictionary = capture("paused")
    set_state(float(frozen.clock), true)
    await draw_frame()
    var resumed: Dictionary = capture("resume")
    await create_timer(.06).timeout
    await draw_frame()
    var advanced: Dictionary = capture("resume")
    set_state(0.0, true, true, 3.0)
    await draw_frame()
    capture("seek")
    root.size = Vector2i(960, 720)
    await draw_frame()
    capture("seek")
    set_state(0.0, false)
    await draw_frame()
    capture("stopped")
    set_state(-.25, true)
    await draw_frame()
    capture("restart")
    var indexed: Array = view._visible_events(0.0, 1.0)
    var beats: Array = []
    for event in indexed:
        beats.append(float(event.beat))
    var report := {"samples":samples, "short_passage":short_passage,
        "screen":app.current_screen, "native_ready":app._native_score_ready(),
        "lead_samples":lead_samples, "playing_samples":playing_samples,
        "pause_frozen":paused.heads == frozen.heads and paused.clock == frozen.clock,
        "resume_advanced":float(advanced.clock) > float(resumed.clock),
        "clock_matched":clock_matched, "clipped":app.score_frame.clip_contents,
        "same_timeline":view.timeline == timeline,
        "same_index":is_same(view.ordered_events, events),
        "same_atlas":view.glyphs.textures == textures,
        "indexed_beats":beats, "scanned_events":view.frame_scanned_events,
        "total_events":view.ordered_events.size(),
        "high_click_bytes":app.click_high.data.size(),
        "low_click_bytes":app.click_low.data.size(),
        "click_stream_selected":app.click_player.stream != null}
    print("NATIVE_CAMERA_REPORT:", JSON.stringify(report))
    app.queue_free()
    await process_frame
    quit(0)
