extends SceneTree
# Only visible controls drive the app. Python is a real-time MIDI learner;
# this harness observes ordinary HTTP state and captures actual rendered frames.

const Design := preload("res://practice_theme.gd")
var app: Control
var folder := ""
var failures: Array[String] = []
var frames: Array = []
var tracked_id := ""

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("INSTRUCTIONAL_FAIL:", description)

func wait_for(predicate: Callable, description: String, seconds: float = 25.0) -> bool:
    var deadline := Time.get_ticks_msec() + int(seconds * 1000)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            check(false, "Timed out: " + description + " [mode=%s phase=%s bpm=%s action_pending=%s]" % [str(app.last_state.get("mode","")),phase(),str(app.last_state.get("bpm",0)),str(app.action_pending)])
            return false
        await process_frame
    return true

func press(text: String) -> void:
    for button in app.find_children("*", "Button", true, false):
        if button.text == text and button.is_visible_in_tree() and not button.disabled:
            button.pressed.emit()
            return
    check(false, "Visible enabled control missing: " + text)

func score_ready() -> bool:
    return app.score_view.texture != null and app.layout_revision == app.revision \
        and app.rendered_revision == app.revision and not app.layout_pending and not app.score_pending

func phase() -> String:
    return str(app.last_state.get("phase", ""))

func visible_instruction() -> bool:
    var instruction := str(app.last_state.get("next_action", ""))
    if instruction.is_empty():
        return false
    for label in app.find_children("*", "Label", true, false):
        if label.is_visible_in_tree() and label.text.contains(instruction):
            return true
    return false

func position(note: Dictionary) -> Vector2:
    var local: Vector2 = (Vector2(float(note.x), float(note.y)) - app.score_crop_origin) \
        / app.score_crop_size * app.score_content.size
    return app.score_content.get_global_transform_with_canvas() * local

func track(beat: float) -> void:
    for note in app.score_layout.get("notes", []):
        if absf(float(note.get("beat", -100)) - beat) < .01:
            tracked_id = str(note.id)
            return
    check(false, "Displayed generated source has note at beat " + str(beat))

func ink(picture: Image, point: Vector2) -> int:
    var pixels := 0
    for y in range(int(point.y)-7, int(point.y)+8):
        for x in range(int(point.x)+1, int(point.x)+25):
            if x >= 0 and y >= 0 and x < picture.get_width() and y < picture.get_height():
                var color := picture.get_pixel(x,y)
                if maxf(color.r,maxf(color.g,color.b)) > .5:
                    pixels += 1
    return pixels

func capture(label: String, beat: float = -999) -> Dictionary:
    await process_frame
    await RenderingServer.frame_post_draw
    var picture := root.get_texture().get_image()
    var scale := Vector2(picture.get_size()) / root.get_visible_rect().size
    var panel: Rect2 = app.score_frame.get_global_rect()
    var pause_modal: Control = app.get("pause_sheet")
    var obscured := pause_modal != null and pause_modal.is_visible_in_tree()
    var selected: Dictionary = {}
    if beat > -998:
        track(beat)
        for note in app.score_layout.get("notes", []):
            if str(note.id) == tracked_id:
                selected = note
                break
    else:
        for note in app.score_layout.get("notes", []):
            var point := position(note)
            if panel.grow(-10).has_point(point) and ink(picture, point*scale) >= 8:
                selected = note
                break
    if obscured:
        var viewport := root.get_visible_rect()
        for control in [pause_modal.resume_button,pause_modal.retry_button,pause_modal.exit_button]:
            check(control.is_visible_in_tree() and viewport.encloses(control.get_global_rect()),
                "Actual pause choice fits the viewport in " + label)
    else:
        check(not selected.is_empty(), "Visible engraved note survives " + label)
    var entry := {"frame":label+".png", "phase":phase(), "mode":app.last_state.get("mode", ""),
        "beat":app._transport_beat_now(), "bpm":app.last_state.get("bpm", 0),
        "target_bpm":app.last_state.get("target_bpm", 0),
        "streak":app.last_state.get("streak", -1), "mastered":app.last_state.get("mastered", -1),
        "next_action":app.last_state.get("next_action", ""),
        "transition":app.last_state.get("transition_in_seconds"),
        "retry_range":app.last_state.get("retry_range"), "score_height":app.score_frame.size.y,
        "notation_occluded_by_pause":obscured}
    if str(app.last_state.get("mode","")) == "listen":
        entry["audio_playing"] = app.demo_player.player.playing
        entry["pcm_bytes"] = app.demo_player.player.stream.data.size() if app.demo_player.player.stream is AudioStreamWAV else 0
    if not selected.is_empty() and not obscured:
        var point := position(selected)*scale
        entry["note_id"] = str(selected.id)
        entry["note_x"] = point.x
        entry["note_y"] = point.y
        entry["notehead_ink"] = ink(picture, point)
        check(int(entry.notehead_ink) >= 8, "Actual notehead pixels exist in " + label)
    if str(app.last_state.get("mode", "")) == "practice" and bool(app.score_overlay.showing):
        var cursor: Dictionary = app.score_overlay.cursor
        var local: Vector2 = (Vector2(float(cursor.get("x", 0)), 0)-app.score_crop_origin) \
            / app.score_crop_size*app.score_content.size
        var line: Vector2 = app.score_content.get_global_transform_with_canvas()*local
        entry["line_x"] = line.x*scale.x
        check(absf(line.x-(panel.position.x+panel.size.x*.42)) < 2,
            "Timing line remains fixed in " + label)
    check(picture.save_png(folder+"/"+label+".png") == OK, "Save actual rendered " + label)
    if not obscured:
        check(app.start_button.is_visible_in_tree() and app.stop_button.is_visible_in_tree(),
            "Primary and Stop stay visible in " + label)
        check(root.get_visible_rect().encloses(app.start_button.get_global_rect()),
            "Primary control fits desktop during " + label)
    if phase() in ["recovering", "feedback", "paused"]:
        check(visible_instruction(), "The next musical action is actually displayed in " + label)
    frames.append(entry)
    print("INSTRUCTIONAL_FRAME:", label)
    return entry

func wait_running(bpm: int, offset: float) -> bool:
    return await wait_for(func(): return score_ready() and phase() == "count_in" \
        and int(app.last_state.get("bpm", 0)) == bpm \
        and absf(float(app.last_state.get("play_from_beat", -1))-offset) < .01,
        "count-in at %d BPM from beat %s" % [bpm,str(offset)])

func finish_earned_modes() -> void:
    check(int(app.last_state.target_bpm) == 240,"Earned stage preserves chosen target before manual tempo change")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending and not app.action_pending,"choose tempo for earned-stage example")
    app.tempo_setting.value = 240
    await wait_for(func(): return not app.apply_tempo_button.disabled,"tempo control is available after pending transport")
    app.apply_tempo_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("bpm",0)) == 240,"ordinary Apply target sets current example tempo")
    press("← Back")
    await wait_for(func(): return score_ready() and not app.action_pending,"earned original score and controls ready")
    press("Listen")
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "listen" \
        and phase() == "playing" and app.demo_player.player.playing,"same earned original notes play actual local PCM")
    check(app.demo_player.player.stream is AudioStreamWAV and app.demo_player.player.stream.data.size() > 10000,
        "Continuous learner journey includes an actual AudioStreamWAV")
    await capture("29-earned-original-listen")
    await wait_for(func(): return str(app.last_state.get("mode","")) == "listen" and phase() == "ready","earned original example finishes naturally")
    check(int(app.last_state.mastered) == 1 and int(app.last_state.streak) == 0,"Example adds no original-stage mastery")
    app.mode_choice.select(2)
    app.mode_choice.item_selected.emit(2)
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "perform" and phase() == "count_in","same original variant enters Perform")
    await capture("30-earned-original-perform-count-in")
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 9,"all missed original notes do not interrupt Perform")
    var first := await capture("31-earned-original-perform-moving-a",13)
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 10,"original Perform keeps moving through misses")
    var second := await capture("32-earned-original-perform-moving-b",13)
    check(float(second.note_x) < float(first.note_x)-8,"Continuous journey ends with actual uninterrupted score movement")
    await wait_for(func(): return phase() == "performance_complete","original Perform reaches its held endpoint")
    check(int(app.last_state.mastered) == 1 and int(app.last_state.streak) == 0,"All-missed original Perform adds no mastery")
    await capture("33-earned-original-performance-review")
    press("Lesson path")
    await wait_for(func(): return app.current_screen == "lesson" and not app.lesson_pending,"saved source trouble appears in lesson path")
    var revisit: Button = null
    for button in app.find_children("*","Button",true,false):
        if button.is_visible_in_tree() and not button.disabled and button.text.begins_with("Revisit bars"):
            revisit = button
            break
    check(revisit != null,"Actual saved trouble has an actionable lesson-row control")
    if revisit != null:
        revisit.pressed.emit()
    await wait_for(func(): return app.current_screen == "practice" and score_ready() \
        and str(app.last_state.get("mode","")) == "learn" and phase() == "guided_wait", "saved trouble returns to its exact source in Learn")
    check(int(app.last_state.first_bar) == 1 and int(app.last_state.last_bar) == 2,
        "The earliest equally weak saved source chunk is revisited")
    await capture("34-saved-original-trouble-revisited",0)
    print("INSTRUCTIONAL_STAGE:trouble-revisited")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    var continue_modes := args.size() > 2 and args[2] == "1"
    var music := args[1]
    check(DisplayServer.get_name() != "headless", "Actual desktop renderer required")
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536,960)
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await wait_for(func(): return not app.preferences.is_empty(), "normal initial settings")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending and not app.action_pending, "normal Settings")
    app.folder_edit.text = music
    press("Save folder")
    await wait_for(func(): return not app.action_pending and str(app.preferences.get("music_dir", "")) == music,
        "user import folder saved")
    press("Choose USB MIDI piano")
    await wait_for(func(): return not app.device_pending and app.device_names.has("Journey test piano"), "test piano listed")
    app.device_menu.id_pressed.emit(app.device_names.find("Journey test piano"))
    app.device_menu.hide()
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("device", "")) == "Journey test piano",
        "input selected through visible MIDI menu")
    press("← Back")
    press("Browse library  →")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending \
        and app.library_rows.get_child_count() == 1, "temporary user file listed")
    var piece := app.library_rows.get_child(0) as Button
    check(piece.text.contains("Imported four-bar lesson"), "Library shows the user-imported MIDI")
    piece.pressed.emit()
    await wait_for(func(): return app.current_screen == "practice" and score_ready() and phase() == "guided_wait",
        "import enters source-generated Learn")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending and not app.action_pending, "choose target tempo")
    app.tempo_setting.value = 240
    await wait_for(func(): return not app.apply_tempo_button.disabled,"tempo control is available after pending transport")
    app.apply_tempo_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("target_bpm", 0)) == 240,
        "chosen target tempo remains authoritative")
    press("← Back")
    await wait_for(func(): return score_ready() and phase() == "guided_wait", "new guided engraving ready")
    await capture("01-learn-ready", 0)
    print("INSTRUCTIONAL_STAGE:wrong-ready")
    await wait_for(func(): return app.hint_keyboard.is_visible_in_tree(), "wrong note reveals contextual keyboard")
    await capture("02-learn-wrong-hint", 1)
    check(app.hint_keyboard._expected_label.text.contains("C5"), "Hint names actual expected C5")
    check(app.hint_keyboard._heard_label.text.contains("C#4"), "Heard wrong pitch remains separate")
    print("INSTRUCTIONAL_STAGE:hint-rendered")
    await wait_for(func(): return phase() == "guided_complete", "learner finds opening pitches")
    await capture("03-learn-complete", 7)
    while bool(app.last_state.teaching.get("has_more_units",false)):
        check(app.start_button.text.to_lower().contains("next idea"),"Preparation offers the next useful source idea")
        app.start_button.pressed.emit()
        await wait_for(func(): return score_ready() and phase() == "guided_wait" \
            and int(app.last_state.get("first_bar",0)) == 3,"Next idea loads the successive two-bar source unit")
        await capture("03-next-guided-idea",0)
        print("INSTRUCTIONAL_STAGE:next-idea-ready")
        await wait_for(func(): return phase() == "guided_complete","all source ideas are prepared with actual MIDI")
        await capture("03-all-guided-ideas-complete",7)
    app.start_button.pressed.emit()
    await wait_running(240,0)
    await capture("04-practice-count-in",0)
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 9,
        "first clean chunk followed by missed required notes")
    var missed_a := await capture("05-errors-score-moving-a",13)
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 10,
        "mistakes do not stop musical time")
    var missed_b := await capture("06-errors-score-moving-b",13)
    check(float(missed_b.note_x) < float(missed_a.note_x)-8, "Rendered score keeps moving despite missed notes")
    check(absf(float(missed_b.line_x)-float(missed_a.line_x)) < 1, "Fixed timing line does not drift under mistakes")
    await wait_for(func(): return phase() == "recovering" and not bool(app.last_state.get("guided_recovery", false)),
        "first boundary retry")
    check(int(app.last_state.bpm) == 216, "First failure slows by ten percent")
    check(str(app.last_state.next_action).contains("Retry bars 3-4"), "First failure names the exact failed chunk")
    check(app.last_state.get("transition_in_seconds") != null, "Retry has a visible nonblocking break")
    await capture("07-retry-instruction")
    app.start_button.pressed.emit()
    await wait_for(func(): return phase() == "paused" and str(app.last_state.get("pause_context", "")) == "recovering",
        "Pause freezes instructional break")
    var remaining := float(app.last_state.transition_in_seconds)
    var paused_id := int(app.last_state.transport_id)
    await capture("08-retry-paused")
    await create_timer(.65).timeout
    check(phase() == "paused" and int(app.last_state.transport_id) == paused_id,
        "Paused break cannot start another attempt")
    check(absf(float(app.last_state.transition_in_seconds)-remaining) < .05,
        "Paused feedback countdown remains frozen")
    app.pause_sheet.resume_button.pressed.emit()
    await wait_running(216,8)
    await capture("09-exact-chunk-retry-count-in")
    await wait_for(func(): return phase() == "recovering" and bool(app.last_state.get("guided_recovery", false)),
        "same chunk repeated trouble selects guided help")
    check(int(app.last_state.bpm) == 194, "Second failure slows by ten percent")
    check(str(app.last_state.next_action).contains("Learn bars 3-4"), "Guided recovery explains why and where")
    await capture("10-guided-recovery-instruction")
    await wait_for(func(): return score_ready() and phase() == "guided_wait" \
        and str(app.last_state.get("mode", "")) == "learn" and int(app.last_state.get("first_bar",0)) == 3,
        "exact bars 3-4 become untimed source fragment")
    var guided := await capture("11-guided-failed-bars",0)
    await create_timer(.35).timeout
    var still := await capture("12-guided-failed-bars-still",0)
    check(absf(float(guided.note_x)-float(still.note_x)) < .1, "Guided recovery has no wall-clock score drift")
    print("INSTRUCTIONAL_STAGE:recovery-guided-ready")
    await wait_for(func(): return phase() == "guided_complete", "failed pitches acquired with fresh input")
    check(int(app.last_state.mastered) == 0 and int(app.last_state.streak) == 0,
        "Guided recovery cannot count toward mastery")
    await capture("13-guided-recovery-complete",7)
    app.start_button.pressed.emit()
    await wait_running(194,8)
    await capture("14-return-to-failed-chunk-count-in")
    await wait_for(func(): return phase() == "recovering" \
        and str(app.last_state.get("next_action", "")).to_lower().contains("whole passage"), "clean partial resumes whole passage")
    check(int(app.last_state.mastered) == 0 and int(app.last_state.streak) == 0,
        "Clean partial cannot award mastery or target clean credit")
    await capture("15-partial-success-whole-passage-next")
    for bpm in [194,213,234,240,240,240]:
        await wait_running(bpm,0)
        var number := frames.size()
        await capture("%02d-whole-count-in-%d" % [number,bpm],0)
        await wait_for(func(): return phase() == "feedback", "clean whole musical attempt at " + str(bpm))
        check(int(app.last_state.mastered) == 0, "Mastery waits until full target streak is committed")
        await capture("%02d-whole-feedback-%d" % [frames.size(),bpm])
    await wait_for(func(): return score_ready() and phase() == "guided_wait" and int(app.last_state.get("mastered",0)) == 1 \
        and str(app.last_state.get("lesson_level", "")) == "original", "actual next generated level after three target passes")
    check(str(app.last_state.get("mode","")) == "learn" and int(app.last_state.get("required_notes",0)) == 16,
        "Next original variant prepares its first real chord idea")
    await capture("28-next-original-variant")
    if continue_modes:
        await finish_earned_modes()
    app.stop_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and not bool(app.last_state.get("running",true)), "Stop remains available after advancement")
    for child in app.get_children():
        if child is Timer:
            child.stop()
    await wait_for(func(): return not app.state_pending and not app.device_pending and not app.library_pending \
        and not app.settings_pending and not app.lesson_pending and not app.action_pending \
        and not app.layout_pending and not app.score_pending, "drain ordinary HTTP requests before exit")
    var file := FileAccess.open(folder+"/result.json",FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"failures":failures,"renderer":DisplayServer.get_name()},"  "))
    print("INSTRUCTIONAL_RESULT:", "PASS" if failures.is_empty() else "FAIL")
    quit(0 if failures.is_empty() else 1)
