extends SceneTree

# Keep the production library, navigation and response handlers; replace
# only HTTP transport so saved server state can be exercised deterministically.
class FixtureApp extends "res://main.gd":
    var posts: Array[Dictionary] = []

    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _send_post(path: String, payload: Dictionary) -> void:
        last_post_path = path
        action_pending = true
        action_request_started_ms = Time.get_ticks_msec()
        posts.append({"path": path, "payload": payload.duplicate(true)})

    func _poll() -> void:
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
    for child in app.library_rows.find_children("*", "Button", true, false):
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
    app._on_library(0, 200, PackedStringArray(), JSON.stringify(listing).to_utf8_buffer())
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
    check(not app.library_search.placeholder_text.contains("composer"),
        "Search must describe supported catalog metadata")
    check(app.library_scroll.size.y >= 130.0,
        "Recent music must preserve a usable compact library viewport")
    if recent != null:
        check(recent.tooltip_text.contains(TITLE) and recent.tooltip_text.contains("Collection"),
            "Continue must preserve the complete real title and folder")
        recent.pressed.emit()
        check(app.posts == [{"path": "/library/open", "payload": {"id": "Collection/real.mid"}}],
            "Continue opens the actual stored identifier through the existing backend")
        app._on_action(0, 200, PackedStringArray(), JSON.stringify(saved_state()).to_utf8_buffer())
        await process_frame
        check(app.current_screen == "practice" and not app.open_picker.visible,
            "Continue returns to restored practice without replacing it through a starting-point chooser")
        check(app.last_state.get("lesson_step") == 17 and app.last_state.get("hand") == "left"
            and app.last_state.get("bpm") == 64 and app.last_state.get("streak") == 2,
            "Continue must present the backend's saved lesson, hand, tempo and streak")
        app.posts.clear()
        app._navigate("library")
        app.action_pending = true
        app.last_post_path = "/control"
        app._resume_last()
        check(app.posts.is_empty(), "Continue waits for an in-flight transport action")
        app._on_action(0, 200, PackedStringArray(), JSON.stringify(saved_state()).to_utf8_buffer())
        await process_frame
        await process_frame
        check(app.posts == [{"path": "/library/open", "payload": {"id": "Collection/real.mid"}}],
            "Queued Continue retains the exact saved identifier")
        app._on_action(0, 200, PackedStringArray(), JSON.stringify(saved_state()).to_utf8_buffer())
        check(not app.open_picker.visible, "Queued Continue retains resume intent after transport completion")

        # A failed Pause must cancel its queued Continue. Otherwise the next
        # successful ordinary open drains the stale queue and reopens A.
        app._navigate("library")
        app.posts.clear()
        app.action_pending = true
        app.last_post_path = "/control"
        app._resume_last()
        check(app.pending_library_piece == "Collection/real.mid",
            "Continue queues the recent piece behind an in-flight Pause")
        app._on_action(0, 400, PackedStringArray(),
            JSON.stringify({"error": "Pause rejected"}).to_utf8_buffer())
        check(app.pending_library_piece.is_empty() and not app.pending_library_resume,
            "Failed actions must discard queued library selection and resume intent")
        check(app.library_message.text.contains("Pause rejected")
            and not app.library_message.text.contains("Preparing"),
            "A rejected Pause must explain why queued Continue did not open")
        app._open_library_piece("other.mid")
        var other := saved_state()
        other["title"] = "Another piece"
        app._on_action(0, 200, PackedStringArray(), JSON.stringify(other).to_utf8_buffer())
        await process_frame
        await process_frame
        check(app.posts == [{"path": "/library/open", "payload": {"id": "other.mid"}}],
            "Opening B after a failed Pause cannot replay stale Continue A")
        check(app.open_picker.visible and app.open_title.text == "Another piece",
            "The later ordinary selection retains its own starting-point chooser")
        app.open_picker.hide()

    # Ordinary title/folder searches remain complete and must not surface an
    # unrelated pinned recent entry, nor show the same music twice.
    for query in ["REAL LONG", "collection"]:
        app.library_search.text = query
        app._populate_library()
        rows = entries(app)
        check(rows.size() == 1 and str(rows[0].get_meta("library_title", "")) == TITLE,
            "Search still matches actual title/folder metadata: " + query)
    app.library_search.text = ""
    listing["last_piece"] = "deleted.mid"
    app._on_library(0, 200, PackedStringArray(), JSON.stringify(listing).to_utf8_buffer())
    app.posts.clear()
    app._resume_last()
    check(app.posts.is_empty(), "A missing last-opened file must not expose a broken Continue action")
    for row in entries(app):
        var detail := row.find_child("MusicDetail", true, false) as Label
        check(detail != null and not detail.text.begins_with("Continue"),
            "A missing last-opened identifier cannot remain advertised as recent")
    app.action_pending = false
    app._open_library_piece("other.mid")
    app._on_action(0, 200, PackedStringArray(), JSON.stringify(saved_state()).to_utf8_buffer())
    check(app.open_picker.visible, "Ordinary music selection retains its starting-point chooser")
    app.open_picker.hide()
    listing["last_piece"] = "warmup:chords"
    listing["warmups"] = [{"id": "warmup:chords", "title": "Chord Changes", "bpm": 68, "focus": "Triads"}]
    app._on_library(0, 200, PackedStringArray(), JSON.stringify(listing).to_utf8_buffer())
    rows = entries(app)
    check(str(rows[0].get_meta("library_title", "")) == "Chord Changes",
        "Built-in recent music uses its catalog title instead of an identifier")
    app.posts.clear()
    rows[0].pressed.emit()
    check(app.posts == [{"path": "/library/open", "payload": {"id": "warmup:chords"}}],
        "Continue also uses the actual built-in music identifier")
    var warmup := saved_state()
    warmup["warmup"] = true
    warmup["title"] = "Chord Changes"
    app._on_action(0, 200, PackedStringArray(), JSON.stringify(warmup).to_utf8_buffer())
    check(app.current_screen == "practice" and not app.open_picker.visible,
        "Recent warm-up continues through the same saved-state route")
    print("LIBRARY_RESUME_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
