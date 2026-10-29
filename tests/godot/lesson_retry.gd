extends "library_fixture.gd"
class App extends "res://main.gd":
    var lesson_calls := 0
    func _ready() -> void:
        _build_interface()
        _update_responsive_layout()
        set_process(false)
        lesson_request = HTTPRequest.new()
        add_child(lesson_request)
    func _request_lesson() -> void:
        lesson_calls += 1
        super._request_lesson()
    func _request_layout() -> void: pass
    func _poll() -> void: pass
    func _request_settings() -> void: pass
    func _request_devices() -> void: pass
    func _request_library() -> void: pass
func run() -> void:
    var app := App.new()
    root.add_child(app)
    await process_frame
    var state := {"loaded":true,"piece_fingerprint":"retry-song","phase":"ready"}
    app._on_state(0,200,PackedStringArray(),JSON.stringify(state).to_utf8_buffer())
    check(app.lesson_calls == 1,"Loaded song requests its first lesson overview")
    if OS.get_cmdline_user_args()[0] == "listen_caption_regression":
        state["warmup"] = true
        state["mode"] = "listen"
        app._on_state(0,200,PackedStringArray(),JSON.stringify(state).to_utf8_buffer())
        check(app.lesson_view.mode_choice.text == "Listen","Lesson Activity names Listen instead of overwriting it with Warm-up practice")
        app.free()
        print("LESSON_FAILURES:",failures.size())
        quit(0 if failures.is_empty() else 1)
        return
    app._on_lesson(0,503,PackedStringArray(),PackedByteArray())
    var deadline := Time.get_ticks_msec() + 1100
    while Time.get_ticks_msec() < deadline: await process_frame
    app._process(0.0)
    check(app.lesson_calls == 2,"A failed lesson response retries the unchanged song instead of poisoning its fingerprint")
    app.free()
    print("LESSON_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
