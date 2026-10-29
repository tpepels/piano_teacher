extends SceneTree
# Real Godot controls, HTTP polling, downloaded PCM and rendered moving notation.

var app: Control
var folder := ""
var frames: Array = []
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("MODES_FAIL:",description)

func wait_for(predicate: Callable, description: String, seconds: float = 25.0) -> bool:
    print("MODES_WAIT:",description)
    var deadline := Time.get_ticks_msec()+int(seconds*1000)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            check(false,"Timed out: "+description)
            return false
        await process_frame
    return true

func imported_row() -> Button:
    for row in app.library_view.library_rows.find_children("*", "Button", true, false):
        if row is Button and str(row.get_meta("library_title", "")).begins_with("Imported"):
            return row
    return null

func press(text: String) -> void:
    for button in app.find_children("*","Button",true,false):
        if text == "Practice" and app.current_screen != "practice" and not app.navigation_rail.is_ancestor_of(button):
            continue
        if button.is_visible_in_tree() and button.text == text and not button.disabled:
            button.pressed.emit()
            return
    check(false,"Visible enabled control missing: "+text)

func phase() -> String:
    return str(app.last_state.get("phase",""))

func score_ready() -> bool:
    return app.practice_view.stage.renderer != null and app._native_score_ready() \
        and app.practice_view.stage.renderer.is_visible_in_tree() and not app.layout_pending \
        and not app.timeline_model_pending

func demo_player() -> AudioStreamPlayer:
    for player in app.find_children("*","AudioStreamPlayer",true,false):
        if player.stream is AudioStreamWAV and player.stream.data.size() > 10000:
            return player
    return null

func note_position(note: Dictionary) -> Vector2:
    var renderer = app.practice_view.stage.renderer
    if renderer != null and renderer.drawn_noteheads.has(str(note.id)):
        return renderer.get_global_transform_with_canvas() * \
            Vector2(renderer.drawn_noteheads[str(note.id)])
    return Vector2(-10000,-10000)

func note_ink(picture: Image, point: Vector2) -> int:
    var pixels := 0
    for y in range(int(point.y)-7,int(point.y)+8):
        for x in range(int(point.x)+1,int(point.x)+25):
            if x >= 0 and y >= 0 and x < picture.get_width() and y < picture.get_height():
                var color := picture.get_pixel(x,y)
                if maxf(color.r,maxf(color.g,color.b)) > .5:
                    pixels += 1
    return pixels

func capture(label: String, track_beat: float = -999) -> Dictionary:
    await process_frame
    RenderingServer.force_draw()
    var picture := root.get_texture().get_image()
    var scale := Vector2(picture.get_size())/root.get_visible_rect().size
    var panel: Rect2 = app.practice_view.stage.score_frame.get_global_rect()
    var selected: Dictionary = {}
    for note in app.score_layout.get("notes",[]):
        if track_beat > -998:
            if absf(float(note.get("beat",-100))-track_beat) < .01:
                selected = note
                break
        elif panel.grow(-10).has_point(note_position(note)) and note_ink(picture,note_position(note)*scale) >= 8:
            selected = note
            break
    check(not selected.is_empty(),"Real engraved score remains visible in "+label)
    var entry := {"frame":label+".png","phase":phase(),"mode":app.last_state.get("mode",""),
        "beat":app._transport_beat_now(),"bpm":app.last_state.get("bpm",0),
        "mastered":app.last_state.get("mastered",-1),"streak":app.last_state.get("streak",-1),
        "score_height":app.practice_view.stage.score_frame.size.y}
    if not selected.is_empty():
        var point := note_position(selected)*scale
        entry["note_id"] = str(selected.id)
        entry["note_x"] = point.x
        entry["note_y"] = point.y
        entry["notehead_ink"] = note_ink(picture,point)
        check(int(entry.notehead_ink) >= 8,"Actual note pixels exist in "+label)
    var player := demo_player()
    if player != null:
        entry["audio_playing"] = player.playing
        entry["audio_position"] = player.get_playback_position()
        entry["pcm_bytes"] = player.stream.data.size()
    check(picture.save_png(folder+"/"+label+".png") == OK,"Save actual mode frame "+label)
    check(app.practice_view.start_button.is_visible_in_tree() and app.practice_view.practice_retry_button.is_visible_in_tree() and app.practice_view.listen_button.is_visible_in_tree(),
        "Transport controls stay visible in "+label)
    var viewport := root.get_visible_rect()
    entry["viewport"] = str(viewport)
    entry["primary_bounds"] = str(app.practice_view.start_button.get_global_rect())
    entry["stop_bounds"] = str(app.lesson_view.stop_button.get_global_rect())
    for control in [app.practice_view.start_button,app.practice_view.practice_retry_button,app.practice_view.listen_button]:
        check(viewport.encloses(control.get_global_rect()),"Transport control fits actual viewport in "+label)
    check(app.practice_view.stage.score_frame.size.y >= 135,"Notation retains135px height in "+label)
    if app.practice_view.performance_review.is_visible_in_tree():
        entry["review_bounds"] = str(app.practice_view.performance_review.get_global_rect())
        entry["weak_button_bounds"] = str(app.practice_view.performance_review.review_button.get_global_rect())
        check(viewport.encloses(app.practice_view.performance_review.get_global_rect()),"Summary fits actual viewport")
        check(viewport.encloses(app.practice_view.performance_review.review_button.get_global_rect()),"Weak-section button fits actual viewport")
    for button in app.practice_view.practice_navigation.get_children():
        if button is Button and button.is_visible_in_tree() and not button.text.is_empty():
            var font: Font = button.get_theme_font("font")
            var font_size: int = button.get_theme_font_size("font_size")
            var text_width := font.get_string_size(button.text,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x
            check(button.size.x >= text_width+12,
                "Navigation text has actual visible width: "+button.text+" in "+label)
    frames.append(entry)
    print("MODES_FRAME:",label)
    return entry

func labels_text() -> String:
    var text := ""
    for label in app.find_children("*","Label",true,false):
        if label.is_visible_in_tree():
            text += " "+label.text.to_lower()
    return text

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    var music := args[1]
    check(DisplayServer.get_name() != "headless","Actual desktop renderer required")
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(int(args[2]),int(args[3])) if args.size() >= 4 else Vector2i(1536,960)
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await wait_for(func(): return not app.preferences.is_empty(),"normal initial settings")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending,"normal Settings")
    app.settings_view.folder_edit.text = music
    press("Save folder")
    await wait_for(func(): return not app.action_pending and str(app.preferences.get("music_dir","")) == music,"user import folder saved")
    press("Choose USB MIDI piano")
    await wait_for(func(): return not app.device_pending and app.device_names.has("Journey test piano"),"test piano listed")
    app.settings_view.device_menu.id_pressed.emit(app.device_names.find("Journey test piano"))
    app.settings_view.device_menu.hide()
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("device","")) == "Journey test piano","input selected in MIDI menu")
    press("Library")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending and imported_row() != null,"temporary user file listed")
    var piece := imported_row()
    check(str(piece.get_meta("library_title", "")).contains("Imported rest and held ending"),"Library opens arbitrary user MIDI")
    piece.pressed.emit()
    await wait_for(func(): return app.practice_view.open_picker.visible, "starting-point dialog opens")
    app.practice_view.open_picker.mode_choice.select(0)
    press("Open music")
    await wait_for(func(): return app.current_screen == "practice" and score_ready() and phase() == "guided_wait","import enters generated Learn")
    # Explicitly choose the available full-source performance using the
    # existing lesson picker so Listen/Perform include
    # the opening rest, internal rest and held ending in bars 3-4.
    await wait_for(func(): return not app.lesson_session.pending and not app.action_pending \
        and not app.practice_view.stage.steps.picker.disabled,"normal lesson picker is ready")
    var full_step := -1
    for index in range(app.practice_view.stage.steps.entries.size()):
        var step: Dictionary = app.practice_view.stage.steps.entries[index]
        if str(step.get("kind","")) == "perform" and int(step.get("first_bar",0)) == 1 \
                and int(step.get("last_bar",0)) == 4 and str(step.get("level","")) == "original":
            full_step = index
            break
    check(full_step >= 0,"Lesson picker exposes the full four-bar original performance")
    if full_step >= 0:
        app.practice_view.stage.steps.picker.select(full_step)
        app.practice_view.stage.steps.picker.item_selected.emit(full_step)
    await wait_for(func(): return score_ready() and not app.action_pending \
        and str(app.last_state.get("kind","")) == "perform" \
        and int(app.last_state.get("lesson_step",0)) == full_step+1,
        "explicit full-source performance is selected without mastery")
    check(int(app.last_state.get("mastered",-1)) == 0,"Picker selection never invents mastery")
    print("MODES_STAGE:full-source-selected")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending,"choose tempo")
    await wait_for(func(): return not app.action_pending and not app.settings_view.apply_tempo_button.disabled,"Pause acknowledged and tempo control enabled")
    print("MODES_STAGE:tempo-ready")
    app.settings_view.tempo_setting.value = 240
    press("Apply tempo")
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("target_bpm",0)) == 240,"chosen target240 acknowledged")
    print("MODES_STAGE:tempo-applied")
    press("Practice")
    await wait_for(func(): return score_ready() and not app.action_pending \
        and int(app.last_state.get("required_notes",0)) == 26,"full original source score ready")
    await capture("01-imported-generated-lesson")
    print("MODES_STAGE:import-ready")
    await create_timer(.25).timeout
    press("Listen")
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "listen" \
        and phase() == "playing" and demo_player() != null and demo_player().playing,"real downloaded PCM starts playing")
    var player := demo_player()
    check(player.stream is AudioStreamWAV,"Listen uses actual AudioStreamWAV")
    var nonzero := false
    for value in player.stream.data:
        if value != 0:
            nonzero = true
            break
    check(nonzero,"Real AudioStreamWAV contains nonzero PCM samples")
    var audio_a := await capture("02-listen-player-active")
    print("MODES_STAGE:audio-playing")
    await create_timer(.3).timeout
    var audio_b := await capture("03-listen-player-advancing")
    check(float(audio_b.audio_position) > float(audio_a.audio_position)+.1,
        "The local audio player actually advances playback")
    await wait_for(func(): return str(app.last_state.get("mode","")) == "listen" and phase() == "ready","demo naturally completes")
    await capture("04-listen-complete-no-mastery")
    check(int(app.last_state.get("mastered",-1)) == 0 and int(app.last_state.get("streak",-1)) == 0,
        "Listen completion never confers clean credit")
    check(app.lesson_view.mode_choice.item_count >= 3,"Distinct Perform mode is visible")
    check(app.lesson_view.mode_choice.get_item_text(2).to_lower().contains("perform"),"Third mode clearly names Perform")
    app.lesson_view.mode_choice.select(2)
    app.lesson_view.mode_choice.item_selected.emit(2)
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "perform" and phase() == "count_in","Perform loads source score then counts in")
    await capture("05-perform-count-in")
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= .2,"uninterrupted performance starts")
    await capture("06-perform-playing")
    print("MODES_STAGE:perform-playing")
    var transport := int(app.last_state.transport_id)
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 7.5,"five missed notes do not interrupt")
    var before := await capture("07-perform-before-failed-boundary",10)
    await wait_for(func(): return phase() == "playing" and app._transport_beat_now() >= 8.5,"perform crosses completed failed chunk")
    var after := await capture("08-perform-after-failed-boundary",10)
    check(int(app.last_state.transport_id) == transport and int(app.last_state.bpm) == 240,
        "Perform never rewinds or slows after five missed notes")
    check(str(before.note_id) == str(after.note_id) and float(after.note_x) < float(before.note_x)-8,
        "Actual score continues moving across the failed two-bar boundary")
    await wait_for(func(): return phase() == "performance_complete","all-missed Perform reaches musical endpoint")
    await capture("09-performance-summary")
    var summary_text := labels_text()
    for word in ["0%","missed","wrong","timing/duration"]:
        check(summary_text.contains(word),"Visible performance summary includes "+word)
    var weak_button: Button = null
    for button in app.find_children("*","Button",true,false):
        var text: String = button.text.to_lower()
        if button.is_visible_in_tree() and not button.disabled and text.contains("review notes"):
            weak_button = button
            break
    check(weak_button != null,"Weakest section has a real visible Practice control")
    if weak_button != null:
        weak_button.pressed.emit()
    await wait_for(func(): return app.practice_view.review_sheet.visible, "Detailed source assessment opens")
    var repeat_button: Button = null
    for candidate in app.practice_view.review_sheet.find_children("*", "Button", true, false):
        if candidate.text.begins_with("Repeat Measures"):
            repeat_button = candidate
            break
    check(repeat_button != null, "Detailed assessment exposes a source-section Repeat action")
    if repeat_button != null:
        repeat_button.pressed.emit()
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "practice" \
        and phase() == "ready", "Reviewed source section waits for the learner")
    app.practice_view.start_button.pressed.emit()
    await wait_for(func(): return score_ready() and str(app.last_state.get("mode","")) == "practice" and phase() == "count_in","weak section starts actual timed Practice")
    await capture("10-weak-section-practice-count-in")
    print("MODES_STAGE:weak-practice-playing")
    await create_timer(.15).timeout
    app.lesson_view.stop_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and not bool(app.last_state.get("running",true)),"Stop abandons weak practice safely")
    for child in app.get_children():
        if child is Timer:
            child.stop()
    await wait_for(func(): return not app.state_pending and not app.device_pending and not app.library_pending \
        and not app.settings_pending and not app.lesson_session.pending and not app.action_pending \
        and not app.layout_pending and not app.timeline_model_pending,"drain normal requests before exit")
    var result := FileAccess.open(folder+"/result.json",FileAccess.WRITE)
    result.store_string(JSON.stringify({"frames":frames,"failures":failures,"renderer":DisplayServer.get_name()},"  "))
    print("MODES_RESULT:","PASS" if failures.is_empty() else "FAIL")
    quit(0 if failures.is_empty() else 1)
