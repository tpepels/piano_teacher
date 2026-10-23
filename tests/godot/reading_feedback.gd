extends SceneTree

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)
    func _send_action(_command: Dictionary) -> void: pass
    func _request_lesson() -> void: pass
    func _request_library() -> void: pass
    func _request_settings() -> void: pass
    func _request_devices() -> void: pass
    func _request_layout() -> void: pass

var app: FixtureApp
var failures: Array[String] = []
var folder: String
var original: Dictionary

func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("READING_FEEDBACK_FAIL:", message)

func state(phase: String, status: String) -> Dictionary:
    var mark: Dictionary = original.notes[0].duplicate(true)
    mark["status"] = status
    return {"loaded":true,"mode":"learn","phase":phase,"running":false,
        "paused":false,"revision":1,"transport_id":1,"title":"A little further, one note at a time",
        "hand":"right","hands":["right"],"bpm":60,"target_bpm":80,"duration_beats":6,
        "first_bar":1,"last_bar":2,"lesson_level":"original","device":"MIDI piano",
        "feedback":"You found every note. Ready to add rhythm?" if phase == "guided_complete" else "Find F5 on the keyboard below, then try again." if status == "wrong" else "Play F5. Take your time.",
        "progress":1.0 if phase == "guided_complete" else 0.2,"feedback_marks":[mark],"teaching":{"phase":phase,"target_index":6 if phase == "guided_complete" else 1,
            "target_count":6,"completed":phase == "guided_complete","hint_visible":status == "wrong",
            "hint_reason":"wrong_note" if status == "wrong" else "", "heard_pitches":[78] if status == "wrong" else [],
            "expected_notes":[] if phase == "guided_complete" else [{"pitch":77,"label":"F5","beat":0}]}}

func show(value: Dictionary) -> void:
    app._on_state(0,200,PackedStringArray(),JSON.stringify(value).to_utf8_buffer())
    await process_frame
    await process_frame
    app._process(0)

func capture(name: String) -> Image:
    await process_frame
    await RenderingServer.frame_post_draw
    var picture := root.get_texture().get_image()
    picture.save_png(folder+"/"+name+".png")
    return picture

func run() -> void:
    folder = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536,960)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    app._navigate("practice")
    app.revision=1; app.layout_revision=1; app.requested_revision=1; app.requested_page=0
    original = JSON.parse_string(FileAccess.get_file_as_string(folder+"/layout.json"))
    app.score_layout = original.duplicate(true)
    app.source_layout = original.duplicate(true)
    app.last_state = {"phase":"ready"}
    app._on_score(0,200,PackedStringArray(),FileAccess.get_file_as_bytes(folder+"/score.png"))
    var cue: Label = app.get("reading_status")
    check(cue != null,"Reading feedback must identify the learner's current action beside the score")
    if cue == null:
        quit(1)
        return
    for dimensions in [Vector2i(1536,960),Vector2i(1024,768),Vector2i(800,600)]:
        root.size = dimensions
        await create_timer(.1).timeout
        await show(state("guided_wait","expected"))
        check(cue.text.contains("TURN"),"Untimed target is identified as the learner's turn")
        check(app.feedback_label.get_global_rect().end.y <= app.score_frame.global_position.y,
            "The instruction appears above the music, never over noteheads")
        check(app.score_frame.size.y >= dimensions.y * .38,"The score is the dominant compact reading surface")
        await capture("reading-%dx%d" % [dimensions.x,dimensions.y])
        await show(state("guided_wait","wrong"))
        check(cue.text.contains("AGAIN"),"A wrong note has an explicit retry cue as well as color")
        check(app.score_frame.size.y >= 135,"Revealing a hint retains readable notation")
        for control in [app.feedback_label,app.progress_label,app.hint_keyboard,app.practice_controls]:
            check(root.get_visible_rect().encloses(control.get_global_rect()),"Hints and actions fit the viewport")
        await capture("retry-%dx%d" % [dimensions.x,dimensions.y])
    await show(state("guided_complete","correct"))
    check(cue.text.contains("FOUND"),"Guided completion confirms note finding without implying mastery")
    var confirmation := await capture("correct-confirmation")
    await create_timer(1.1).timeout
    var settled := await capture("correct-settled")
    var score_rect := Rect2i(app.score_frame.get_global_rect())
    check(confirmation.get_region(score_rect).get_data() != settled.get_region(score_rect).get_data(),
        "Accepting a note produces a visible score confirmation that settles")
    await show(state("guided_complete","correct"))
    var repeated := await capture("correct-repeated-poll")
    check(settled.get_data() == repeated.get_data(),"Repeated state polls must not replay the success animation")
    await show(state("ready","expected"))
    check(cue.text == "READY","Stopped learning must not ask for a note while MIDI input is inactive")
    print("READING_FEEDBACK_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
