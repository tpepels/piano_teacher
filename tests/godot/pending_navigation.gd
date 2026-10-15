extends SceneTree

# Keep the real request arbitration, navigation and response handlers. The wire
# alone is controlled so a user can navigate before an HTTP response arrives.
class FixtureApp extends "res://main.gd":
    var wire_commands: Array[Dictionary] = []

    func _ready() -> void:
        _build_interface()
        set_process(false)

    func _send_post(path: String, payload: Dictionary) -> void:
        if action_pending:
            return
        action_pending = true
        last_post_path = path
        wire_commands.append(payload.duplicate(true))

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
        "clock_beat": -1.0 if phase == "count_in" else 2.0,
        "transport_id": 3, "target_bpm": 80, "bpm": 80,
        "hands": ["right", "left", "both"], "hand": "right",
        "feedback_marks": [], "duration_beats": 12.0}

func show_state(phase: String) -> void:
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(state(phase)).to_utf8_buffer())

func acknowledge(phase: String, code: int = 200) -> void:
    var body: Dictionary = state(phase) if code == 200 else {"error": "Temporary request failure"}
    app._on_action(0, code, PackedStringArray(), JSON.stringify(body).to_utf8_buffer())

func test_pending_start_or_resume(action: String, destination: String) -> void:
    show_state("paused" if action == "resume" else "ready")
    app._send_action({"action": action})
    app._navigate(destination)
    check(app.wire_commands == [{"action": action}],
        "Navigation waits for the in-flight " + action + " request before sending another request")
    acknowledge("playing" if action == "resume" else "count_in")
    var wanted := "pause" if destination in ["settings", "lesson"] else "stop"
    check(app.wire_commands == [{"action": action}, {"action": wanted}],
        action + " immediately followed by " + destination + " preserves the user's " + wanted + " intent: " + str(app.wire_commands))
    check(app.action_pending, "The queued navigation request is now awaiting its own acknowledgement")

func test_response_before_poll() -> void:
    show_state("ready")
    app._send_action({"action": "start"})
    acknowledge("count_in")
    check(str(app.last_state.get("phase", "")) == "count_in",
        "A successful control response refreshes transport state before the next poll")
    app.state_request_started_ms = 20 # Poll and click may share one millisecond.
    app.action_request_started_ms = 20
    show_state("ready") # A poll issued before Start returns after its response.
    check(str(app.last_state.get("phase", "")) == "count_in",
        "A delayed pre-Start poll cannot overwrite the acknowledged count-in")
    app._navigate("settings")
    check(app.wire_commands == [{"action": "start"}, {"action": "pause"}],
        "Navigating after Start acknowledgement pauses the count-in even before a state poll: " + str(app.wire_commands))

func test_stop_overrides_pending_pause() -> void:
    show_state("playing")
    app._navigate("settings")
    check(app.wire_commands == [{"action": "pause"}], "Opening Settings first requests a pause")
    app._navigate("library")
    acknowledge("paused")
    check(app.wire_commands == [{"action": "pause"}, {"action": "stop"}],
        "Leaving for Library while pause is pending still stops the attempt: " + str(app.wire_commands))

func test_failed_request_flushes_intent() -> void:
    show_state("ready")
    app._send_action({"action": "start"})
    app._navigate("settings")
    acknowledge("ready", 500)
    check(app.wire_commands == [{"action": "start"}, {"action": "pause"}],
        "A failed first response cannot strand the queued navigation intent: " + str(app.wire_commands))
    check(app.action_pending, "The navigation request is sent after the first failure")

func run() -> void:
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    app._navigate("practice")
    app.revision = 1
    app.layout_revision = 1
    app.rendered_revision = 1
    var image := Image.create(2, 2, false, Image.FORMAT_RGBA8)
    image.fill(Color.WHITE)
    app.score_view.texture = ImageTexture.create_from_image(image)
    var scenario := OS.get_cmdline_user_args()[0]
    match scenario:
        "start_settings": test_pending_start_or_resume("start", "settings")
        "start_lesson": test_pending_start_or_resume("start", "lesson")
        "resume_settings": test_pending_start_or_resume("resume", "settings")
        "resume_lesson": test_pending_start_or_resume("resume", "lesson")
        "start_library": test_pending_start_or_resume("start", "library")
        "start_home": test_pending_start_or_resume("start", "home")
        "response_before_poll": test_response_before_poll()
        "stop_overrides_pause": test_stop_overrides_pending_pause()
        "failure_flushes_intent": test_failed_request_flushes_intent()
        _: check(false, "Unknown scenario: " + scenario)
    print("PENDING_NAVIGATION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
