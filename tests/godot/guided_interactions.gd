extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    var commands: Array = []
    func _ready() -> void:
        super._ready()
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
        "piece_fingerprint":str(app.last_state.get("piece_fingerprint","")),
        "title": "Learn a short imported idea", "hand": "right", "hands": ["right"],
        "bpm": 80, "target_bpm": 100, "duration_beats": app.practice_view.stage.renderer.timeline.duration_beats, "clock_beat": 0,
        "first_bar": 1, "last_bar": 2, "required_notes": 4, "lesson_level": "original",
        "feedback": "Find C4 at your own pace.", "streak": 0,
        "feedback_marks": [{"source_id":str(target.id),"status":"expected"}],
        "teaching": {"phase": phase, "revision": 1, "target_index": 0, "target_count": 3,
            "completed": phase == "guided_complete", "hint_visible": hint,
            "hint_reason": "wrong_note" if hint else "", "heard_pitches": [61] if hint else [],
            "expected_notes": [] if phase == "guided_complete" else [{"id":str(target.id), "pitch":int(target.midi_pitch),"label":"Source note","beat":float(target.onset_beats)}],
            "fragment": {"first_bar":1,"last_bar":2,"start_beat":0,"end_beat":8}}}

func show(phase: String, hint: bool = false) -> void:
    app._on_state(0,JSON.stringify(state(phase,hint)).to_utf8_buffer())

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
    var fixture_error: String = await app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(fixture_error.is_empty(), fixture_error)
    if not fixture_error.is_empty():
        quit(1)
        return
    target = app.practice_view.stage.renderer.timeline.notes[0]
    show("guided_wait")
    app.practice_view.start_button.pressed.emit()
    expect("pause","Learn primary pauses without starting timed playback: ")
    check(not app.lesson_view.stop_button.disabled,"Stop is available during untimed Learn")
    show("paused")
    app.practice_view.start_button.pressed.emit()
    expect("resume","Resume retains guided target: ")
    show("guided_complete")
    app.practice_view.start_button.pressed.emit()
    expect("practice","Guided success offers real rhythm practice: ")
    show("guided_wait")
    app._navigate("lesson")
    expect("pause","Lesson detour pauses untimed acquisition: ")
    app._navigate("practice")
    show("guided_wait",true)
    await process_frame
    await process_frame
    var keyboard: Control = app.practice_view.stage.keyboard
    check(keyboard != null,"The live practice screen contains the contextual keyboard")
    if keyboard != null:
        check(keyboard.is_visible_in_tree(),"Wrong-note hint reveals the actual keyboard")
        check(keyboard.get_global_rect().end.y <= 600,"Hints fit inside compact viewport")
        check(app.practice_view.stage.score_frame.size.y >= 135,"Hints retain readable notation height")
        show("guided_wait",false)
        check(not keyboard.visible,"Successful unaided acquisition keeps hints hidden")
    show("guided_wait")
    app._process(0.0)
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    # Guided Learn is presented through the score stream: the engine publishes
    # the guided source as its next-score decision (score_queue_next) and the
    # application admits it at that deadline, exactly as for timed takes.
    # Untimed Learn then WAITS: the axis stops with the current target note on
    # the playhead and moves on only when the engine names the next target.
    var stream_view = app.practice_view.stage.renderer
    var notes: Array = stream_view.timeline.notes
    var second: Dictionary = {}
    for note in notes:
        if float(note.onset_beats) > float(target.onset_beats)+.2:
            second = note
            break
    check(not second.is_empty(),"Fixture has a later guided target")
    # Same backend time base the fixture app already calibrated against.
    var backend_now: float = float(Time.get_ticks_msec()) - app.visual_transport_clock.backend_offset_ms
    var guided := state("guided_wait")
    guided["clock_sampled_at_ms"] = backend_now
    guided["score_queue_next"] = {"plan_id":"guided-target-plan",
        "deadline_at_ms":backend_now+4000.0,"source_from_beat":0.0,
        "count_in_beats":0.0}
    app._on_state(0,JSON.stringify(guided).to_utf8_buffer())
    var playhead: float = stream_view.size.x*stream_view.PLAYHEAD_FRACTION
    var id: String = str(app.practice_view.stage.feedback.note_for_source(app.revision, str(target.id)))
    var drawn_x := func(identifier: String) -> float:
        var heads: Dictionary = stream_view.drawn_noteheads
        return float(heads[identifier].x) if heads.has(identifier) else NAN
    # Let the passage arrive (the engine plans it 4 s ahead) and settle.
    var deadline: int = Time.get_ticks_msec()+6500
    while Time.get_ticks_msec() < deadline:
        app._process(0.0)
        await process_frame
    RenderingServer.force_draw()
    check(stream_view.drawn_noteheads.has(id), "Guided source target is actually painted")
    var settled: float = drawn_x.call(id)
    check(absf(settled-playhead) <= 3.0,
        "Untimed Learn waits with the target note on the playhead (x=%.1f, playhead=%.1f)" % [settled,playhead])
    await create_timer(1.0).timeout
    for frame in range(4):
        app._process(0.0)
        await process_frame
    RenderingServer.force_draw()
    check(absf(drawn_x.call(id)-settled) < .5,
        "The waiting target does not scroll away while the learner thinks")
    # The learner plays the target: the engine names the next one.
    var advanced := state("guided_wait")
    advanced["teaching"]["target_index"] = 1
    advanced["teaching"]["expected_notes"] = [{"id":str(second.id),
        "pitch":int(second.midi_pitch),"label":"Source note","beat":float(second.onset_beats)}]
    app._on_state(0,JSON.stringify(advanced).to_utf8_buffer())
    var next_id: String = str(app.practice_view.stage.feedback.note_for_source(app.revision, str(second.id)))
    deadline = Time.get_ticks_msec()+4000
    while Time.get_ticks_msec() < deadline:
        app._process(0.0)
        await process_frame
    RenderingServer.force_draw()
    check(drawn_x.call(id) < settled-2.0,
        "Playing the target moves the passage on along the one forward axis")
    check(absf(drawn_x.call(next_id)-playhead) <= 3.0,
        "The next target waits on the playhead (x=%.1f)" % drawn_x.call(next_id))
    check(app.practice_view.stage.renderer.note_status_source == app.practice_view.stage.feedback,
        "Guided notation paints status ink only from the one note-status ledger")
    check(app.practice_view.stage.feedback.score == app.practice_view.stage.renderer, "Guided feedback binds the actual production view")
    check(app._native_score_ready(), "Guided transport preserves native revision readiness")
    print("GUIDED_UI_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
