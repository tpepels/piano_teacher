extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    var commands: Array = []
    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)
    func _send_action(command: Dictionary) -> void:
        commands.append(command)
    func _request_lesson() -> void: pass
    func _request_library() -> void: pass
    func _request_settings() -> void: pass
    func _request_devices() -> void: pass
    func _request_layout() -> void: pass

var app: FixtureApp
var failures: Array = []
var target: Dictionary = {}

func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("GUIDED_UI_FAIL:", message)

func state(phase: String, hint: bool = false) -> Dictionary:
    return {"loaded": true, "mode": "learn", "phase": phase, "running": false,
        "paused": phase == "paused", "revision": 1, "transport_id": 4,
        "title": "Learn a short imported idea", "hand": "right", "hands": ["right"],
        "bpm": 80, "target_bpm": 100, "duration_beats": app.timeline_preview.timeline.duration_beats, "clock_beat": 0,
        "first_bar": 1, "last_bar": 2, "required_notes": 4, "lesson_level": "original",
        "feedback": "Find C4 at your own pace.", "streak": 0,
        "feedback_marks": [{"source_id":str(target.id),"status":"expected"}],
        "teaching": {"phase": phase, "revision": 1, "target_index": 0, "target_count": 3,
            "completed": phase == "guided_complete", "hint_visible": hint,
            "hint_reason": "wrong_note" if hint else "", "heard_pitches": [61] if hint else [],
            "expected_notes": [] if phase == "guided_complete" else [{"id":str(target.id), "pitch":int(target.midi_pitch),"label":"Source note","beat":float(target.onset_beats)}],
            "fragment": {"first_bar":1,"last_bar":2,"start_beat":0,"end_beat":8}}}

func show(phase: String, hint: bool = false) -> void:
    app._on_state(0,200,PackedStringArray(),JSON.stringify(state(phase,hint)).to_utf8_buffer())

func expect(action: String, description: String) -> void:
    check(app.commands == [{"action":action}],description+str(app.commands))
    app.commands.clear()

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    app._navigate("practice")
    var fixture_error: String = app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(fixture_error.is_empty(), fixture_error)
    if not fixture_error.is_empty():
        quit(1)
        return
    target = app.timeline_preview.timeline.notes[0]
    show("guided_wait")
    app.start_button.pressed.emit()
    expect("pause","Learn primary pauses without starting timed playback: ")
    check(not app.stop_button.disabled,"Stop is available during untimed Learn")
    show("paused")
    app.start_button.pressed.emit()
    expect("resume","Resume retains guided target: ")
    show("guided_complete")
    app.start_button.pressed.emit()
    expect("practice","Guided success offers real rhythm practice: ")
    show("guided_wait")
    app._navigate("lesson")
    expect("pause","Lesson detour pauses untimed acquisition: ")
    app._navigate("practice")
    show("guided_wait",true)
    await process_frame
    await process_frame
    var keyboard: Control = app.get("hint_keyboard")
    check(keyboard != null,"The live practice screen contains the contextual keyboard")
    if keyboard != null:
        check(keyboard.is_visible_in_tree(),"Wrong-note hint reveals the actual keyboard")
        check(keyboard.get_global_rect().end.y <= 600,"Hints fit inside compact viewport")
        check(app.score_frame.size.y >= 135,"Hints retain readable notation height")
        show("guided_wait",false)
        check(not keyboard.visible,"Successful unaided acquisition keeps hints hidden")
    show("guided_wait")
    app._process(0.0)
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    var id: String = str(app.native_score_feedback.source_to_id.get(str(target.id), ""))
    check(app.timeline_preview.drawn_noteheads.has(id), "Guided source target is actually painted")
    var painted: Dictionary = app.timeline_preview.drawn_noteheads.duplicate()
    var position: float = app.timeline_preview.clock_beat
    app.last_state_tick -= 100000
    app._process(0.0)
    app.timeline_preview.queue_redraw()
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    check(app.timeline_preview.clock_beat == position,"Guided score never advances with wall-clock time")
    check(app.timeline_preview.drawn_noteheads == painted,
        "Actual guided source head projection stays fixed across wall-clock time")
    check(app.native_score_feedback.markers.get(id, "") == "expected",
        "Guided feedback marks the real source target")
    if painted.has(id):
        check(app.native_score_feedback.note_position(id) == painted[id],
            "Guided feedback uses the compositor's painted source head")
    check(app.native_score_feedback.score == app.timeline_preview, "Guided feedback binds the actual production view")
    check(app._native_score_ready(), "Guided transport preserves native revision readiness")
    print("GUIDED_UI_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
