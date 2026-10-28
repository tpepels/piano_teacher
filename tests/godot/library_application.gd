extends "library_fixture.gd"

class OfflineApp extends "res://main.gd":
    var posts: Array[Dictionary] = []
    func _ready() -> void:
        _build_interface()
        _update_responsive_layout()
        set_process(false)
    func _send_post(path: String, payload: Dictionary) -> void:
        if action_pending:
            return
        action_pending = true
        last_post_path = path
        action_request_started_ms = Time.get_ticks_msec()
        posts.append({"path":path, "payload":payload.duplicate(true)})
    func _poll() -> void: pass
    func _request_library() -> void: pass
    func _request_library_health() -> void: pass
    func _request_settings() -> void: pass
    func _request_devices() -> void: pass
    func _request_lesson() -> void: pass
    func _request_layout() -> void: pass

func saved_state() -> Dictionary:
    return {"loaded":true,"revision":7,"title":"Saved music","phase":"ready",
        "mode":"practice","running":false,"paused":false,"warmup":false,
        "first_bar":9,"last_bar":12,"piece_last_bar":64,"selected_start_bar":9,
        "hand":"left","hands":["left","right","both"],"lesson_level":"outline",
        "bpm":64,"target_bpm":80,"streak":2,"lesson_step":17,"lesson_steps":40,
        "feedback_marks":[]}

func app_library(app: Control) -> Control:
    return app.screens["library"].find_child("LibraryScreen",true,false)

func test_app_open_resume(app: Control) -> void:
    app._on_library(0,200,PackedStringArray(),JSON.stringify(catalog()).to_utf8_buffer())
    app._navigate("library")
    await process_frame
    var view := app_library(app)
    check(view != null, "Main mounts the independent Library screen")
    if view == null:
        return
    entries(view)[0].pressed.emit()
    check(app.posts == [{"path":"/library/open","payload":{"id":"Collection/real.mid"}}],
        "Continue is coordinated through the real application open route")
    app._on_action(0,200,PackedStringArray(),JSON.stringify(saved_state()).to_utf8_buffer())
    check(app.current_screen == "practice" and not app.open_picker.visible and app.last_state.lesson_step == 17,
        "Continue preserves saved place and bypasses the source picker")
    app._navigate("library")
    entries(view)[1].pressed.emit()
    app._on_action(0,200,PackedStringArray(),JSON.stringify(saved_state()).to_utf8_buffer())
    check(app.open_picker.visible and app.open_picker.title_label.text == "Saved music",
        "Ordinary selection still opens the independent source picker")

func test_app_pending_failure(app: Control) -> void:
    app._on_library(0,200,PackedStringArray(),JSON.stringify(catalog()).to_utf8_buffer())
    app._navigate("library")
    var view := app_library(app)
    check(view != null, "Main mounts the independent Library screen")
    if view == null:
        return
    app.action_pending = true
    app.last_post_path = "/control"
    entries(view)[0].pressed.emit()
    check(app.pending_library_piece == "Collection/real.mid" and app.pending_library_resume,
        "Quick Continue retains both identifier and resume intent behind Pause")
    app._on_action(0,400,PackedStringArray(),JSON.stringify({"error":"Pause rejected"}).to_utf8_buffer())
    app._on_library(0,200,PackedStringArray(),JSON.stringify(catalog()).to_utf8_buffer())
    app._update_responsive_layout()
    check(app.pending_library_piece.is_empty() and not app.pending_library_resume,
        "A failed Pause discards queued music and resume intent")
    check(control(view,"LibraryMessage").visible and control(view,"LibraryMessage").text.contains("Pause rejected"),
        "The owned Library screen retains a failed queued selection after refresh")
    app._open_library_piece("other.mid")
    check(app.posts == [{"path":"/library/open","payload":{"id":"other.mid"}}],
        "A later selection cannot replay an abandoned Continue")

func test_app_open_failure_visible(app: Control) -> void:
    app._on_library(0,200,PackedStringArray(),JSON.stringify(catalog()).to_utf8_buffer())
    app._navigate("library")
    app._update_responsive_layout()
    app._open_library_piece("other.mid")
    app._on_action(0,400,PackedStringArray(),JSON.stringify({"error":"Unreadable file"}).to_utf8_buffer())
    var view := app_library(app)
    var message: Label = control(view,"LibraryMessage")
    check(message.visible and message.text.contains("Unreadable file"),
        "An import failure is visible immediately on a compact Library")

func run() -> void:
    var scenario := OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    var app := OfflineApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    match scenario:
        "app_open_resume": await test_app_open_resume(app)
        "app_open_failure_visible": test_app_open_failure_visible(app)
        "app_pending_failure": test_app_pending_failure(app)
    app.free()
    print("LIBRARY_SCREEN_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
