extends SceneTree

class FixtureApp extends "res://main.gd":
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

func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("GUIDED_UI_FAIL:", message)

func state(phase: String, hint: bool = false) -> Dictionary:
    return {"loaded": true, "mode": "learn", "phase": phase, "running": false,
        "paused": phase == "paused", "revision": 1, "transport_id": 4,
        "title": "Learn a short imported idea", "hand": "right", "hands": ["right"],
        "bpm": 80, "target_bpm": 100, "duration_beats": 8, "clock_beat": 0,
        "first_bar": 1, "last_bar": 2, "required_notes": 4, "lesson_level": "original",
        "feedback": "Find C4 at your own pace.", "streak": 0,
        "feedback_marks": [{"page": 0,"x": .3,"y": .2,"status":"expected"}],
        "teaching": {"phase": phase, "revision": 1, "target_index": 0, "target_count": 3,
            "completed": phase == "guided_complete", "hint_visible": hint,
            "hint_reason": "wrong_note" if hint else "", "heard_pitches": [61] if hint else [],
            "expected_notes": [] if phase == "guided_complete" else [{"id":"event-1", "pitch":60,"label":"C4","beat":0}],
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
    app.revision=1
    app.layout_revision=1
    app.rendered_revision=1
    app.current_page=0
    var picture:=Image.create(1000,300,false,Image.FORMAT_RGBA8)
    picture.fill(Color("#2D3532"))
    app.score_view.texture=ImageTexture.create_from_image(picture)
    app.score_overlay.image_size=Vector2(1000,300)
    app.score_layout={"anchors":[{"beat":0,"page":0,"x":.3,"top":.1,"bottom":.9}],"notes":[]}
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
    var position: Vector2=app.score_content.position
    app.last_state_tick -= 100000
    app._process(0.0)
    check(app.score_content.position == position,"Guided score never advances with wall-clock time")
    check(app.score_overlay.get("guided_active") == true,"Guided target path is distinct from the musical timing line")
    print("GUIDED_UI_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
