extends SceneTree

var failures: Array[String] = []
var redraws: Dictionary = {}

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("IDLE_RENDERING_FAIL:", message)

func settle() -> void:
    for frame in range(24):
        await process_frame

func watch(node: Node) -> void:
    if node is Control:
        var key := str(node.get_path())
        node.draw.connect(func(): redraws[key] = int(redraws.get(key, 0)) + 1)
    for child in node.get_children():
        watch(child)

func present(app: Control, state: Dictionary) -> void:
    # Every snapshot has a fresh sample timestamp even when its visible
    # musical state is identical. Comparing whole HTTP bodies cannot work.
    state["clock_sampled_at_ms"] = Time.get_ticks_msec()
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(state).to_utf8_buffer())

func unchanged_polls(app: Control, state: Dictionary, label: String) -> void:
    present(app, state)
    await settle()
    redraws.clear()
    var before: int = Engine.get_frames_drawn()
    for sample_index in range(8):
        present(app, state)
        await process_frame
        await process_frame
    check(redraws.is_empty(), label + " repeated polls repainted: " + JSON.stringify(redraws))
    check(Engine.get_frames_drawn() == before, label + " woke the idle framebuffer")
    check(OS.low_processor_usage_mode and Engine.max_fps == 30,
        label + " retains the idle presentation policy")

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1220, 780)
    var app = load(OS.get_cmdline_user_args()[1]).new()
    root.add_child(app)
    watch(app)
    app.set_process(true)
    var empty_state := {"loaded":false, "running":false, "paused":false,
        "clock_beat":0.0, "phase":"ready", "revision":-1}
    present(app, empty_state)
    await create_timer(1.5).timeout # Finish initial window/font/layout changes.
    await unchanged_polls(app, empty_state, "Empty application")
    var error: String = app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(error.is_empty(), "Production score loads: " + error)
    if not failures.is_empty():
        quit(1)
        return
    for entry in [["score", app.timeline_preview], ["feedback", app.native_score_feedback],
            ["speed", app.speed_label], ["progress", app.progress_label],
            ["instruction", app.lesson_info_label], ["passage", app.passage_label],
            ["caption", app.feedback_label],
            ["keyboard", app.hint_keyboard]]:
        var label: String = entry[0]
        entry[1].draw.connect(func(): redraws[label] = int(redraws.get(label, 0)) + 1)
    var state: Dictionary = app.last_state.duplicate(true)
    state.merge({"phase":"ready", "running":false, "paused":false,
        "mode":"practice", "preview_only":false, "clock_beat":0.0,
        "import_warnings":["Repaired source meter"], "feedback_marks":[],
        "midi_visual_events":[], "midi_input_age":null, "device":""}, true)
    app.set_process(true)
    present(app, state)
    await create_timer(1.5).timeout # Let the window and initial font/layout changes finish.
    await unchanged_polls(app, state, "Ready")
    state["feedback_unmapped"] = 1
    await unchanged_polls(app, state, "Ready with unmapped warning")
    check(app.feedback_label.text.ends_with("1 unpositioned note(s)"),
        "A retained unmapped assessment warning stays visible")
    state["feedback_unmapped"] = 0
    state["device"] = "Framebuffer MIDI fixture"
    await unchanged_polls(app, state, "Connected Ready")
    state.merge({"running":true, "paused":true, "phase":"paused"}, true)
    await unchanged_polls(app, state, "Paused")
    var attack: Dictionary = {}
    for event in app.timeline_preview.ordered_events:
        if bool(event.get("is_attack", false)):
            attack = event
            break
    check(not attack.is_empty(), "Imported fixture supplies an authentic attack")
    state["feedback_marks"] = [{"note_id":str(attack.id), "status":"missed"}]
    await unchanged_polls(app, state, "Paused assessed marks")
    redraws.clear()
    state["clock_beat"] = .5
    present(app, state)
    await settle()
    check(int(redraws.get("score", 0)) > 0 and int(redraws.get("feedback", 0)) > 0,
        "Paused seeks must move assessed marks with the engraved score")
    await unchanged_polls(app, state, "Paused after seeking")
    redraws.clear()
    state["feedback_marks"][0]["status"] = "late"
    present(app, state)
    await settle()
    check(int(redraws.get("feedback", 0)) > 0,
        "Changed assessment must repaint even with the transport frozen")
    redraws.clear()
    state["bpm"] = int(state["bpm"]) + 5
    present(app, state)
    await settle()
    check(int(redraws.get("speed", 0)) > 0 and app.speed_label.text.begins_with(str(state.bpm)),
        "Tempo changes still repaint the actual caption")
    redraws.clear()
    state["midi_visual_events"] = [{"sequence":11,"pitch":60,"status":"unexpected","age":.1}]
    present(app, state)
    await settle()
    check(int(redraws.get("keyboard", 0)) > 0 and app.hint_keyboard._pressed.get(60) == "unexpected",
        "New physical notes still paint their independent assessment color")
    redraws.clear()
    for sample_index in range(8):
        state["midi_visual_events"][0]["age"] = .1 + .05 * sample_index
        present(app, state)
        await process_frame
        await process_frame
    check(redraws.is_empty(), "Changing MIDI age within its visible lifetime must not repaint")
    state["midi_visual_events"][0]["age"] = .81
    state["midi_held_pitches"] = [60]
    present(app, state)
    await settle()
    check(int(redraws.get("keyboard", 0)) > 0 and app.hint_keyboard._pressed.get(60) == "heard",
        "Expiry removes a transient color while preserving a physically held key")
    redraws.clear()
    state["midi_held_pitches"] = []
    present(app, state)
    await settle()
    check(int(redraws.get("keyboard", 0)) > 0 and app.hint_keyboard._pressed.is_empty(),
        "Physical releases still repaint the keyboard")
    state.merge({"running":false, "paused":false, "phase":"ready", "preview_only":true}, true)
    await unchanged_polls(app, state, "Ungraded preview Ready")
    check(app.native_score_feedback.markers.is_empty(), "Preview clears assessed marks")
    state["mode"] = "listen"
    await unchanged_polls(app, state, "Listen Ready")
    state.merge({"running":true,"paused":true,"phase":"paused",
        "demo":{"instrument":"Framebuffer piano","audio_available":true,"sampled":true}}, true)
    await unchanged_polls(app, state, "Paused Listen")
    check(app.feedback_label.text == "Listen paused · Framebuffer piano",
        "Paused Listen retains the selected instrument caption")
    state.merge({"mode":"learn", "preview_only":false, "phase":"guided_wait",
        "running":false, "paused":false,
        "teaching":{"phase":"guided_wait", "hint_visible":true, "hint_reason":"stall",
            "expected_notes":[{"pitch":60,"label":"C4"}], "heard_pitches":[],
            "target_index":0, "target_count":1}}, true)
    await unchanged_polls(app, state, "Guided hint")
    redraws.clear()
    state["teaching"]["expected_notes"] = [{"pitch":67,"label":"G4"}]
    present(app, state)
    await settle()
    check(int(redraws.get("keyboard", 0)) > 0 and app.hint_keyboard._expected.has(67),
        "Changed guided targets still repaint their literal pitches")
    state.merge({"mode":"practice", "preview_only":false, "running":true,
        "paused":false, "phase":"playing", "clock_beat":0.0}, true)
    present(app, state)
    await settle()
    redraws.clear()
    await settle()
    check(int(redraws.get("score", 0)) > 0,
        "Active playback continues to repaint scrolling notation")
    check(not OS.low_processor_usage_mode and Engine.max_fps == 60,
        "Playing retains the full visual frame budget")
    print("IDLE_RENDERING_FAILURES:", failures.size())
    app.free()
    quit(0 if failures.is_empty() else 1)
