extends SceneTree

# Keep the real request arbitration, navigation and response handlers. The wire
# alone is controlled so a user can navigate before a worker reply arrives.
class RecordingRequest extends RefCounted:
    var timeout := 5.0
    var calls: Array[Dictionary]
    func _init(recorded: Array[Dictionary]) -> void:
        calls = recorded
    # Start/Resume carry timing derived from the renderer's score admission.
    # These scenarios assert which commands are sent, and in what order.
    const ADMISSION_TIMING := ["presentation_lead_seconds",
        "continuous_horizon_beats", "reuse_pending_score",
        "presentation_deadline_ms", "continuation_clear_beats",
        "continuation_header_beats"]
    func request(_operation: String, payload: Dictionary) -> int:
        # Navigation asserts command intent and order. Verify the transport
        # metadata independently before omitting it from the comparison.
        # These are real production admission fields, not extra commands.
        if str(payload.get("action", "")) in ["start", "resume", "restart"]:
            if not payload.has("presentation_deadline_ms") or                     not is_finite(float(payload["presentation_deadline_ms"])) or                     float(payload["presentation_deadline_ms"]) <= 0.0:
                push_error("PENDING_NAVIGATION_BAD_DEADLINE")
                return ERR_INVALID_PARAMETER
            for key in ["continuation_clear_beats", "continuation_header_beats"]:
                if not payload.has(key) or not is_finite(float(payload[key])) or                         float(payload[key]) < 0.0:
                    push_error("PENDING_NAVIGATION_BAD_GEOMETRY: " + key)
                    return ERR_INVALID_PARAMETER
        var recorded := payload.duplicate(true)
        for key in ADMISSION_TIMING:
            recorded.erase(key)
        calls.append(recorded)
        return OK

class FixtureApp extends "native_production_fixture.gd":
    var wire_commands: Array[Dictionary] = []

    func _ready() -> void:
        super._ready()
        action_request = RecordingRequest.new(wire_commands)
        # Main's coordinator owns the actual outbound request adapter after
        # Phase 5 extraction. Override the transport only at that boundary.
        command_coordinator.action_request = action_request

    func _poll() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_library() -> void:
        pass

    func _request_lesson() -> void:
        pass

    func _request_layout() -> void:
        pass

var app: FixtureApp
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("PENDING_NAVIGATION_FAIL:", message)

func state(phase: String) -> Dictionary:
    return {"loaded": true, "phase": phase,
        "running": phase in ["count_in", "playing", "paused"],
        "paused": phase == "paused", "revision": 1, "title": "Navigation fixture",
        "piece_fingerprint":str(app.last_state.get("piece_fingerprint","")),
        "clock_beat": -1.0 if phase == "count_in" else 2.0,
        "transport_id": 3, "target_bpm": 80, "bpm": 80,
        "hands": ["right", "left", "both"], "hand": "right",
        "feedback_marks": [], "duration_beats": 12.0}

func show_state(phase: String) -> void:
    app._on_state(0,JSON.stringify(state(phase)).to_utf8_buffer())
    # Presenting a state can focus a staff or admit more source strips; the
    # renderer refuses a transport action until their ink has been drawn and
    # compiled (notation_not_compiled). A user acts frames later; so does this.
    var renderer = app.practice_view.stage.renderer
    await process_frame
    var deadline := Time.get_ticks_msec() + 5000
    while not renderer.retained_ready() and Time.get_ticks_msec() < deadline:
        await process_frame
    check(renderer.retained_ready(), "Retained ink is compiled after presenting " + phase)
    # Regression: focusing the presented hand's staff dropped the prepared
    # source geometry without rebuilding it, so painting hit a stale cache.
    check(renderer.layout.cached_offsets_gap > 0.0,
        "Presenting a hand keeps the prepared static engraving geometry: " + phase)

func acknowledge(phase: String, code: int = 0) -> void:
    var body: Dictionary = state(phase) if code == 0 else {"error": "Temporary request failure"}
    app._on_action(code,JSON.stringify(body).to_utf8_buffer())

func test_pending_start_or_resume(action: String, destination: String) -> void:
    await show_state("paused" if action == "resume" else "ready")
    app._send_action({"action": action})
    app._navigate(destination)
    check(app.wire_commands == [{"action": action}],
        "Navigation waits for the in-flight " + action + " request before sending another request")
    acknowledge("playing" if action == "resume" else "count_in")
    var wanted := "pause" if destination != "home" else ""
    var expected: Array[Dictionary] = []
    expected.append({"action": action})
    if not wanted.is_empty():
        expected.append({"action": wanted})
    check(app.wire_commands == expected,
        action + " immediately followed by " + destination + " preserves the user's " + wanted + " intent: " + str(app.wire_commands))
    check(app.command_coordinator.state.pending == not wanted.is_empty(),
        "Only a real pending overlay pause should remain after acknowledgement")

func test_quick_music_selection_survives_pending_pause() -> void:
    await show_state("playing")
    app._navigate("library")
    check(app.command_coordinator.state.pending, "Opening the music drawer requests a pause")
    app._open_library_piece("selected.mid")
    check(app.command_coordinator.state.queued_library_piece == "selected.mid",
        "A quick music click is held while Pause is still in flight")
    acknowledge("paused")
    await process_frame
    check(app.wire_commands == [{"action": "pause"}, {"id": "selected.mid"}],
        "The selected file must open after Pause finishes: " + str(app.wire_commands))
    check(app.command_coordinator.state.queued_library_piece.is_empty(),
        "Successful queue draining must not reopen a song twice")


func test_start_picker_keyboard_is_modal() -> void:
    await show_state("ready")
    app.practice_view.show_source_picker({"title":"Test_-_MIDI", "piece_last_bar":77,
        "selected_start_bar":1})
    var pending_field: LineEdit = app.practice_view.open_picker.measure.get_line_edit()
    pending_field.grab_focus()
    pending_field.text = "63"
    var space := InputEventKey.new()
    space.keycode = KEY_SPACE
    space.pressed = true
    app._input(space)
    app._unhandled_key_input(space)
    check(app.wire_commands.is_empty(),
        "Modal Space cannot start the underlying playback transport")
    check(app.practice_view.open_picker.visible,
        "Using a modal keyboard shortcut must keep the source picker open")
    app.practice_view.confirm_source_picker()
    check(app.wire_commands == [{"action":"open_at", "bar":63, "mode":"learn"}],
        "Typed source measure commits before confirming the modal: "
        + str(app.wire_commands))


func test_response_before_poll() -> void:
    await show_state("ready")
    app._send_action({"action": "start"})
    app.state_request_started_ms = app.command_coordinator.state.started_ms
    await show_state("playing") # A pre-action poll arrives while Start is pending.
    check(str(app.last_state.get("phase", "")) == "ready",
        "A pre-Start poll cannot publish while the command owns the pending snapshot")
    acknowledge("count_in")
    check(str(app.last_state.get("phase", "")) == "count_in",
        "A successful control response refreshes transport state before the next poll")
    app._navigate("settings")
    check(app.wire_commands == [{"action": "start"}, {"action": "pause"}],
        "Navigating after Start acknowledgement pauses the count-in even before a state poll: " + str(app.wire_commands))

func test_stop_overrides_pending_pause() -> void:
    await show_state("playing")
    app._navigate("settings")
    check(app.wire_commands == [{"action": "pause"}], "Opening Settings first requests a pause")
    app._navigate("library")
    acknowledge("paused")
    check(app.wire_commands == [{"action": "pause"}],
        "Opening music while pause is pending preserves the same attempt: " + str(app.wire_commands))

func test_failed_request_flushes_intent() -> void:
    await show_state("ready")
    app._send_action({"action": "start"})
    app._navigate("settings")
    acknowledge("ready", 1)
    check(app.wire_commands == [{"action": "start"}, {"action": "pause"}],
        "A failed first response cannot strand the queued navigation intent: " + str(app.wire_commands))
    check(app.command_coordinator.state.pending, "The navigation request is sent after the first failure")

func run() -> void:
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    app._navigate("practice")
    var fixture_error: String = await app.load_native_fixture(OS.get_cmdline_user_args()[1])
    check(fixture_error.is_empty(), fixture_error)
    if not fixture_error.is_empty():
        quit(1)
        return
    var scenario := OS.get_cmdline_user_args()[0]
    match scenario:
        "start_settings": await test_pending_start_or_resume("start", "settings")
        "start_lesson": await test_pending_start_or_resume("start", "lesson")
        "resume_settings": await test_pending_start_or_resume("resume", "settings")
        "resume_lesson": await test_pending_start_or_resume("resume", "lesson")
        "start_library": await test_pending_start_or_resume("start", "library")
        "start_home": await test_pending_start_or_resume("start", "home")
        "response_before_poll": await test_response_before_poll()
        "stop_overrides_pause": await test_stop_overrides_pending_pause()
        "quick_music_click": await test_quick_music_selection_survives_pending_pause()
        "picker_modal": await test_start_picker_keyboard_is_modal()
        "failure_flushes_intent": await test_failed_request_flushes_intent()
        _: check(false, "Unknown scenario: " + scenario)
    print("PENDING_NAVIGATION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
