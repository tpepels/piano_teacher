extends SceneTree

# Keep the production library, navigation and response handlers; replace
# only the worker transport so saved server state can be exercised
# deterministically. Command ownership stays in the real CommandRequestState.
class RecordingRequest extends RefCounted:
    var timeout := 5.0
    var calls: Array[Dictionary]
    func _init(recorded: Array[Dictionary]) -> void:
        calls = recorded
    func request(operation: String, payload: Dictionary = {}) -> int:
        calls.append({"operation": operation, "payload": payload.duplicate(true)})
        return OK

class FixtureApp extends "res://main.gd":
    var commands: Array[Dictionary] = []

    func _ready() -> void:
        _build_interface()
        action_request = RecordingRequest.new(commands)
        startup_last_music_checked = true
        frame_coordinator = PracticeFrameCoordinator.new(
            practice_view, settings_view, lesson_view, lesson_session,
            null, frame_meter)
        state_presenter = PracticeStatePresenter.new(
            practice_view, settings_view, lesson_view, lesson_session, null)
        command_failure_presenter = CommandFailurePresenter.new(
            library_view, practice_view, settings_view, home_view)
        command_success_presenter = CommandSuccessPresenter.new(
            library_view, practice_view, settings_view, lesson_session)
        command_success_effects = CommandSuccessEffects.new(command_success_presenter)
        command_success_effects.publish_state.connect(_on_state)
        command_success_effects.navigate_practice.connect(_navigate)
        command_success_effects.request_settings.connect(_request_settings)
        command_success_effects.request_library.connect(_request_library)
        command_success_effects.request_library_health.connect(_request_library_health)
        command_success_effects.refresh_score.connect(_refresh_score_status)
        metronome_frame = MetronomeFrameCoordinator.new(
            settings_view, practice_view, visual_transport_clock,
            _transport_beat_at, _count_tick, _raw_click)
        command_coordinator.configure(practice_view,settings_view,metronome_frame,
            score_flow,visual_transport_clock,action_request,command_failure_presenter)
        command_coordinator.succeeded.connect(command_success_effects.apply)
        command_coordinator.learning_accepted.connect(_learning_command_accepted)
        command_coordinator.refresh_requested.connect(_poll)
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _poll() -> void:
        pass

    func _request_library() -> void:
        pass

    func _request_library_health() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_layout() -> void:
        pass

var failures: Array[String] = []
const TITLE := "A Real Long Piano Title From the Library Metadata"

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("LIBRARY_RESUME_FAIL:", message)

func entries(app: FixtureApp) -> Array[Button]:
    var result: Array[Button] = []
    for child in app.library_view.find_children("*", "Button", true, false):
        if child.has_meta("library_title"):
            result.append(child)
    return result

func saved_state() -> Dictionary:
    return {"loaded": true, "revision": 7, "title": TITLE,
        "phase": "ready", "mode": "practice", "running": false,
        "paused": false, "warmup": false, "first_bar": 9, "last_bar": 12,
        "selected_start_bar": 9, "piece_last_bar": 64,
        "hand": "left", "hands": ["left", "right", "both"],
        "lesson_level": "outline", "bpm": 64, "target_bpm": 80,
        "streak": 2, "lesson_step": 17, "lesson_steps": 40,
        "feedback": "Saved practice is ready", "feedback_marks": []}

func _initialize() -> void:
    run.call_deferred()

func run() -> void:
    var dimensions := OS.get_cmdline_user_args()[0].split("x")
    root.size = Vector2i(int(dimensions[0]), int(dimensions[1]))
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var listing := {"last_piece": "Collection/real.mid", "folder": "/music",
        "count": 2, "warmups": [], "pieces": [
            {"id": "other.mid", "title": "Another piece", "format": "MIDI", "folder": ""},
            {"id": "Collection/real.mid", "title": TITLE, "format": "MIDI", "folder": "Collection"}]}
    app._on_library(0, JSON.stringify(listing).to_utf8_buffer())
    app._navigate("library")
    for frame in range(6):
        await process_frame
    var rows := entries(app)
    check(rows.size() == 2, "Recent piece must not duplicate its ordinary catalog row")
    var recent: Button = null
    if not rows.is_empty() and str(rows[0].get_meta("library_title", "")) == TITLE:
        var detail := rows[0].find_child("MusicDetail", true, false) as Label
        if detail != null and detail.text.begins_with("Continue"):
            recent = rows[0]
    check(recent != null, "Music must expose the actual last-opened piece as its first Continue action")
    check(not app.library_view.library_search.placeholder_text.contains("composer"),
        "Search must describe supported catalog metadata")
    check(app.library_view.library_scroll.size.y >= 130.0,
        "Recent music must preserve a usable compact library viewport")
    if recent != null:
        check(recent.tooltip_text.contains(TITLE) and recent.tooltip_text.contains("Collection"),
            "Continue must preserve the complete real title and folder")
        recent.pressed.emit()
        check(app.commands == [{"operation": "library.open", "payload": {"id": "Collection/real.mid"}}],
            "Continue opens the actual stored identifier through the existing backend")
        app._on_action(0, JSON.stringify(saved_state()).to_utf8_buffer())
        await process_frame
        check(app.current_screen == "practice" and not app.practice_view.open_picker.visible,
            "Continue returns to restored practice without replacing it through a starting-point chooser")
        check(app.last_state.get("lesson_step") == 17 and app.last_state.get("hand") == "left"
            and app.last_state.get("bpm") == 64 and app.last_state.get("streak") == 2,
            "Continue must present the backend's saved lesson, hand, tempo and streak")
        app.commands.clear()
        app._navigate("library")
        app._send_action({"action": "pause"})
        app.commands.clear()
        app.home_view.resume_button.pressed.emit()
        check(app.commands.is_empty(), "Continue waits for an in-flight transport action")
        app._on_action(0, JSON.stringify(saved_state()).to_utf8_buffer())
        await process_frame
        await process_frame
        check(app.commands == [{"operation": "library.open", "payload": {"id": "Collection/real.mid"}}],
            "Queued Continue retains the exact saved identifier")
        app._on_action(0, JSON.stringify(saved_state()).to_utf8_buffer())
        check(not app.practice_view.open_picker.visible, "Queued Continue retains resume intent after transport completion")

        # A failed Pause must cancel its queued Continue. Otherwise the next
        # successful ordinary open drains the stale queue and reopens A.
        app._navigate("library")
        app.commands.clear()
        app._send_action({"action": "pause"})
        app.commands.clear()
        app.home_view.resume_button.pressed.emit()
        check(app.command_coordinator.state.queued_library_piece == "Collection/real.mid",
            "Continue queues the recent piece behind an in-flight Pause")
        app._on_action(400,
            JSON.stringify({"error": "Pause rejected"}).to_utf8_buffer())
        check(app.command_coordinator.state.queued_library_piece.is_empty() and not app.command_coordinator.state.queued_library_resume,
            "Failed actions must discard queued library selection and resume intent")
        check(app.library_view.library_message.text.contains("Pause rejected")
            and not app.library_view.library_message.text.contains("Preparing"),
            "A rejected Pause must explain why queued Continue did not open")
        app._open_library_piece("other.mid")
        var other := saved_state()
        other["title"] = "Another piece"
        # A piece with no saved lesson progress opens the starting-point
        # chooser; progress beyond step 1 asks to continue instead.
        other["lesson_step"] = 1
        app._on_action(0, JSON.stringify(other).to_utf8_buffer())
        await process_frame
        await process_frame
        check(app.commands == [{"operation": "library.open", "payload": {"id": "other.mid"}}],
            "Opening B after a failed Pause cannot replay stale Continue A")
        check(app.practice_view.open_picker.visible and app.practice_view.open_picker.title_label.text == "Another piece",
            "The later ordinary selection retains its own starting-point chooser")
        app.practice_view.open_picker.hide()

    # Ordinary title/folder searches remain complete and must not surface an
    # unrelated pinned recent entry, nor show the same music twice.
    for query in ["REAL LONG", "collection"]:
        app.library_view.library_search.text = query
        app.library_view.library_search.text_changed.emit(query)
        await create_timer(.17).timeout
        rows = entries(app)
        check(rows.size() == 1 and str(rows[0].get_meta("library_title", "")) == TITLE,
            "Search still matches actual title/folder metadata: " + query)
    app.library_view.library_search.text = ""
    listing["last_piece"] = "deleted.mid"
    app._on_library(0, JSON.stringify(listing).to_utf8_buffer())
    app.commands.clear()
    app.home_view.resume_button.pressed.emit()
    check(app.commands.is_empty(), "A missing last-opened file must not expose a broken Continue action")
    for row in entries(app):
        var detail := row.find_child("MusicDetail", true, false) as Label
        check(detail != null and not detail.text.begins_with("Continue"),
            "A missing last-opened identifier cannot remain advertised as recent")
    app._open_library_piece("other.mid")
    var fresh := saved_state()
    fresh["lesson_step"] = 1
    app._on_action(0, JSON.stringify(fresh).to_utf8_buffer())
    check(app.practice_view.open_picker.visible, "Ordinary music selection retains its starting-point chooser")
    app.practice_view.open_picker.hide()
    app._open_library_piece("other.mid")
    app._on_action(0, JSON.stringify(saved_state()).to_utf8_buffer())
    check(app.practice_view.is_resume_prompt_open() and not app.practice_view.open_picker.visible,
        "Ordinary selection of music with saved lesson progress asks to continue instead of choosing a start")
    listing["last_piece"] = "warmup:chords"
    listing["warmups"] = [{"id": "warmup:chords", "title": "Chord Changes", "bpm": 68, "focus": "Triads"}]
    app._on_library(0, JSON.stringify(listing).to_utf8_buffer())
    rows = entries(app)
    check(str(rows[0].get_meta("library_title", "")) == "Chord Changes",
        "Built-in recent music uses its catalog title instead of an identifier")
    app.commands.clear()
    rows[0].pressed.emit()
    check(app.commands == [{"operation": "library.open", "payload": {"id": "warmup:chords"}}],
        "Continue also uses the actual built-in music identifier")
    var warmup := saved_state()
    warmup["warmup"] = true
    warmup["title"] = "Chord Changes"
    app._on_action(0, JSON.stringify(warmup).to_utf8_buffer())
    check(app.current_screen == "practice" and not app.practice_view.open_picker.visible,
        "Recent warm-up continues through the same saved-state route")
    print("LIBRARY_RESUME_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
