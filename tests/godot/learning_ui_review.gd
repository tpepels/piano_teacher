extends SceneTree
# Reusable real learning-screen captures and ordinary pause-sheet interactions.

var app: Control
var folder := ""
var failures: Array[String] = []
var frames: Array = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("LEARNING_UI_FAIL:",description)

func wait_for(predicate: Callable,description: String,seconds: float = 25.0) -> bool:
    var deadline := Time.get_ticks_msec()+int(seconds*1000)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            check(false,"Timed out: "+description)
            return false
        await process_frame
    return true

func imported_row() -> Button:
    for row in app.library_rows.find_children("*", "Button", true, false):
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

func sheet() -> Control:
    return app.get("pause_sheet")

func score_ready() -> bool:
    return app.score_view.texture != null and app.layout_revision == app.revision \
        and app.rendered_revision == app.revision and not app.layout_pending and not app.score_pending

func key(code: Key) -> void:
    for down in [true,false]:
        var event := InputEventKey.new()
        event.keycode = code
        event.physical_keycode = code
        event.pressed = down
        Input.parse_input_event(event)
        await process_frame

func resize_to(dimensions: Vector2i) -> void:
    root.size = dimensions
    await create_timer(.15).timeout
    await process_frame
    await process_frame

func note_position(note: Dictionary) -> Vector2:
    var local: Vector2 = (Vector2(float(note.x),float(note.y))-app.score_crop_origin) \
        /app.score_crop_size*app.score_content.size
    return app.score_content.get_global_transform_with_canvas()*local

func note_ink(picture: Image,point: Vector2) -> int:
    var pixels := 0
    for y in range(int(point.y)-7,int(point.y)+8):
        for x in range(int(point.x)+1,int(point.x)+25):
            if x >= 0 and y >= 0 and x < picture.get_width() and y < picture.get_height():
                var color := picture.get_pixel(x,y)
                if maxf(color.r,maxf(color.g,color.b)) > .5:
                    pixels += 1
    return pixels

func capture(label: String) -> Dictionary:
    await process_frame
    RenderingServer.force_draw()
    var picture := root.get_texture().get_image()
    picture.save_png(folder+"/"+label+".png")
    var viewport := root.get_visible_rect()
    var scale := Vector2(picture.get_size())/viewport.size
    var paused := sheet() != null and sheet().is_visible_in_tree()
    var entry := {"frame":label+".png","width":picture.get_width(),"height":picture.get_height(),
        "fullscreen":root.mode == Window.MODE_FULLSCREEN,"screen":app.current_screen,
        "mode":app.last_state.get("mode",""),"phase":phase(),"bpm":app.last_state.get("bpm",0),
        "target_bpm":app.last_state.get("target_bpm",0),"hand":app.last_state.get("hand",""),
        "from_beat":app.last_state.get("play_from_beat",0),"pause_sheet":paused}
    var background := picture.get_pixel(5,5)
    check(background.r < .2 and background.g < .32 and background.b < .28,
        "Low-glare dark background in "+label)
    if app.open_picker.visible:
        var modal: Rect2 = app.open_panel.get_global_rect()
        entry["starting_measure_bounds"] = str(modal)
        check(modal.size.x >= 280.0 and modal.size.x <= 680.0,
            "Starting-measure dialog must have readable width in " + label)
        check(modal.size.y <= viewport.size.y * .92,
            "Starting-measure dialog must not fill the whole screen vertically in " + label)
        check(viewport.encloses(modal),
            "Starting-measure dialog must stay inside viewport in " + label)
        var actions: Control = app.find_child("StartPickerActions", true, false)
        check(actions != null, "Starting-measure modal must have a fixed action footer")
        if actions != null:
            check(actions.is_visible_in_tree() and viewport.encloses(actions.get_global_rect()),
                "Cancel/Open music must be visible without scrolling in " + label)
            for button in actions.get_children():
                check(button is Button and button.is_visible_in_tree()
                    and viewport.encloses(button.get_global_rect()),
                    "Starting-measure action must fit the viewport in " + label)
    if app.current_screen == "practice" and not app.open_picker.visible:
        entry["score_height"] = app.score_frame.size.y
        check(app.score_frame.size.y >= 135,"Notation retains readable height in "+label)
        check(viewport.encloses(app.practice_navigation.get_global_rect()),"Learning navigation fits actual viewport in "+label)
        for label_node in [app.speed_label,app.hand_label]:
            var font: Font = label_node.get_theme_font("font")
            var text_width := font.get_string_size(label_node.text,HORIZONTAL_ALIGNMENT_LEFT,-1,label_node.get_theme_font_size("font_size")).x
            check(viewport.encloses(label_node.get_global_rect()),"Speed/hand label fits actual viewport in "+label)
            check(label_node.size.x >= text_width,"Speed/hand text is not clipped in "+label)
        if not paused and bool(app.last_state.get("loaded", false)):
            var panel: Rect2 = app.score_frame.get_global_rect()
            var found := false
            if app.native_notation_enabled and app.timeline_preview != null and \
                    app.timeline_preview.visible:
                # Native noteheads live in the fixed musical-time viewport.
                # Testing the retired strip positions reports false blank
                # scores once full-page PNGs stop being downloaded.
                var view: Control = app.timeline_preview
                for id in view.drawn_noteheads:
                    var local: Vector2 = view.drawn_noteheads[id]
                    var point: Vector2 = view.get_global_transform_with_canvas()*local
                    var pixels := note_ink(picture,point*scale)
                    if panel.grow(-8).has_point(point) and pixels >= 8:
                        entry["note_id"] = str(id)
                        entry["notehead_ink"] = pixels
                        found = true
                        break
            else:
                for note in app.score_layout.get("notes",[]):
                    var point := note_position(note)
                    var pixels := note_ink(picture,point*scale)
                    if panel.grow(-8).has_point(point) and pixels >= 8:
                        entry["note_id"] = str(note.id)
                        entry["notehead_ink"] = pixels
                        found = true
                        break
            check(found or phase() == "count_in",
                "Actual engraved note pixels remain visible after the count-in in "+label)
            for button in [app.start_button,app.practice_retry_button,app.listen_button]:
                check(button.is_visible_in_tree() and viewport.encloses(button.get_global_rect()),
                    "Three transport controls fit actual viewport in "+label)
        for button in app.practice_navigation.get_children():
            if button is Button and button.is_visible_in_tree() and not button.text.is_empty():
                var font: Font = button.get_theme_font("font")
                var width := font.get_string_size(button.text,HORIZONTAL_ALIGNMENT_LEFT,-1,button.get_theme_font_size("font_size")).x
                check(button.size.x >= width+8,"Navigation text has visible width: "+button.text)
        if app.hint_keyboard.is_visible_in_tree() and not paused:
            entry["hint_bounds"] = str(app.hint_keyboard.get_global_rect())
            check(viewport.encloses(app.hint_keyboard.get_global_rect()),"Conditional keyboard fits actual viewport in "+label)
            check(not app.hint_keyboard._expected_label.text.is_empty(),"Keyboard identifies the actual expected pitch")
        if paused:
            entry["pause_bounds"] = str(sheet().get_global_rect())
            var commands: Array = []
            for control in [sheet().resume_button,sheet().retry_button,sheet().listen_button,
                    sheet().slower_button,sheet().faster_button,sheet().exit_button,
                    sheet().hand_choice,sheet().bar_choice,sheet().seek_button]:
                sheet().scroll.ensure_control_visible(control)
                await process_frame
                await process_frame
                check(control.is_visible_in_tree() and viewport.encloses(control.get_global_rect()),
                    "Pause choice can be scrolled into the actual viewport in "+label)
                commands.append(str(control.get_global_rect()))
            entry["pause_controls"] = commands
            sheet().scroll.scroll_vertical = 0
    check(picture.save_png(folder+"/"+label+".png") == OK,"Save actual learning UI frame "+label)
    frames.append(entry)
    print("LEARNING_UI_FRAME:",label)
    return entry

func ensure_paused() -> void:
    await wait_for(func(): return not app.action_pending and score_ready(),"rendered score and controls ready")
    if phase() == "paused" and sheet() != null and sheet().is_visible_in_tree():
        return
    if not bool(app.last_state.get("running",false)) and phase() not in ["guided_wait","loading","feedback","recovering"]:
        app.start_button.pressed.emit()
        await wait_for(func(): return bool(app.last_state.get("running",false)) or phase() == "guided_wait" or phase() == "loading",
            "ordinary Start before pausing")
    await wait_for(func(): return not app.action_pending,"transport control ready")
    press("Path")
    await wait_for(func(): return app.current_screen == "lesson" and phase() == "paused" and not app.action_pending,
        "Path pauses the attempt before exposing advanced controls")
    press("Advanced practice controls")
    await wait_for(func(): return phase() == "paused" and sheet() != null and sheet().is_visible_in_tree(),
        "visible Pause sheet freezes engine")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    var music := args[1]
    check(DisplayServer.get_name() != "headless","Actual desktop renderer required")
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536,960)
    app = load("res://main.gd").new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await wait_for(func(): return not app.preferences.is_empty(),"normal initial settings")
    await resize_to(Vector2i(1536,960))
    await capture("01-home")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending,"normal Settings")
    app.folder_edit.text = music
    press("Save folder")
    await wait_for(func(): return not app.action_pending and str(app.preferences.get("music_dir","")) == music,"user folder saved")
    press("Choose USB MIDI piano")
    await wait_for(func(): return not app.device_pending and app.device_names.has("Journey test piano"),"test MIDI adapter listed")
    app.device_menu.id_pressed.emit(app.device_names.find("Journey test piano"))
    app.device_menu.hide()
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("device","")) == "Journey test piano","MIDI input selected in real menu")
    await capture("02-settings")
    press("Library")
    await wait_for(func(): return app.current_screen == "library" and not app.library_pending and imported_row() != null,"user MIDI listed")
    await capture("03-library")
    (imported_row()).pressed.emit()
    await wait_for(func(): return app.open_picker.visible, "starting-point dialog opens")
    await capture("03b-starting-measure-1536x960")
    await resize_to(Vector2i(800,600))
    await capture("03c-starting-measure-800x600")
    await resize_to(Vector2i(1536,960))
    app.open_mode.select(0)
    press("Open music")
    await wait_for(func(): return app.current_screen == "practice" and score_ready() and phase() == "guided_wait","generated Learn opens")
    press("Settings")
    await wait_for(func(): return app.current_screen == "settings" and not app.settings_pending,"choose practice target")
    await wait_for(func(): return not app.action_pending and not app.apply_tempo_button.disabled,"Pause acknowledged and tempo control enabled")
    app.tempo_setting.value = 80
    press("Apply tempo")
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("target_bpm",0)) == 80,"chosen target acknowledged")
    press("Practice")
    await wait_for(func(): return score_ready() and phase() == "guided_wait","guided revision ready")
    check(sheet() != null,"Learning app integrates a real Pause sheet")
    print("LEARNING_UI_STAGE:input-ready")
    await wait_for(func(): return app.hint_keyboard.is_visible_in_tree(),"real wrong MIDI input reveals keyboard")
    for dimensions in [Vector2i(1536,960),Vector2i(1024,768),Vector2i(800,600)]:
        await resize_to(dimensions)
        await capture("hinted-learn-%dx%d" % [dimensions.x,dimensions.y])
    await key(KEY_F11)
    await wait_for(func(): return root.mode == Window.MODE_FULLSCREEN,"ordinary F11 enters fullscreen")
    await create_timer(.2).timeout
    await capture("hinted-learn-fullscreen")
    await ensure_paused()
    var guided_index := int(app.last_state.teaching.target_index)
    var guided_session := int(app.last_state.transport_id)
    await capture("pause-sheet-fullscreen")
    await key(KEY_F11)
    await wait_for(func(): return root.mode != Window.MODE_FULLSCREEN,"ordinary F11 exits fullscreen")
    for dimensions in [Vector2i(1536,960),Vector2i(1024,768),Vector2i(800,600)]:
        await resize_to(dimensions)
        await capture("pause-sheet-%dx%d" % [dimensions.x,dimensions.y])
    sheet().resume_button.pressed.emit()
    await wait_for(func(): return phase() == "guided_wait" and not sheet().visible,"Resume returns to same guided target")
    check(int(app.last_state.teaching.target_index) == guided_index and int(app.last_state.transport_id) == guided_session,
        "Ordinary Resume preserves guided target and attempt")
    await capture("resume-guided-same-target")
    app.mode_choice.select(1)
    app.mode_choice.item_selected.emit(1)
    await wait_for(func(): return score_ready() and phase() == "playing" and app._transport_beat_now() >= .15,"ordinary timed Practice starts")
    await capture("practice-playing-compact")
    await ensure_paused()
    var previous_attempt := int(app.last_state.transport_id)
    sheet().retry_button.pressed.emit()
    await wait_for(func(): return score_ready() and phase() == "count_in" and int(app.last_state.transport_id) > previous_attempt,"Retry creates a fresh timed attempt")
    await capture("pause-retry-fresh-count-in")
    await ensure_paused()
    sheet().slower_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("bpm",0)) == 72 \
        and int(app.last_state.get("target_bpm",0)) == 72,"Slower changes selected tempo by ten percent")
    await ensure_paused()
    sheet().faster_button.pressed.emit()
    await wait_for(func(): return not app.action_pending and int(app.last_state.get("bpm",0)) == 79 \
        and int(app.last_state.get("target_bpm",0)) == 79,"Faster changes selected tempo by ten percent")
    await ensure_paused()
    var left := -1
    for index in range(sheet().hand_choice.item_count):
        if str(sheet().hand_choice.get_item_metadata(index)) == "left":
            left = index
    check(left >= 0,"Pause sheet offers actual source left-hand notes")
    sheet().hand_choice.select(left)
    sheet().hand_choice.item_selected.emit(left)
    await wait_for(func(): return not app.action_pending and str(app.last_state.get("hand","")) == "left" and score_ready(),"Hand choice changes actual generated variant")
    await ensure_paused()
    check(not sheet().seek_button.disabled,"Source-grid seek is available for timed Practice")
    sheet().bar_choice.value = 2
    sheet().seek_button.pressed.emit()
    await wait_for(func(): return score_ready() and phase() == "count_in" \
        and absf(float(app.last_state.get("play_from_beat",-1))-4) < .01,"Seek starts the selected source measure")
    await capture("pause-seek-left-hand-bar2")
    await ensure_paused()
    sheet().listen_button.pressed.emit()
    await wait_for(func(): return str(app.last_state.get("mode","")) == "listen" and phase() == "playing" \
        and app.demo_player.player.playing,"Pause Listen produces real local audio")
    var first_token: String = app.demo_player.token
    await capture("pause-listen-real-audio")
    await ensure_paused()
    check(sheet().seek_button.disabled,"Audio Listen does not expose a misleading seek action")
    sheet().retry_button.pressed.emit()
    await wait_for(func(): return str(app.last_state.get("mode","")) == "listen" and phase() == "playing" \
        and app.demo_player.player.playing and app.demo_player.token != first_token,"Pause Retry restarts a new real Listen session")
    await capture("pause-retry-listen")
    await ensure_paused()
    sheet().exit_button.pressed.emit()
    await wait_for(func(): return app.current_screen == "library" and not app.action_pending \
        and not bool(app.last_state.get("running",true)),"Pause Exit returns to library and stops transport")
    check(not app.demo_player.player.playing,"Exit stops local demo audio")
    await capture("pause-exit-library")
    for child in app.get_children():
        if child is Timer:
            child.stop()
    await wait_for(func(): return not app.state_pending and not app.device_pending and not app.library_pending \
        and not app.settings_pending and not app.lesson_pending and not app.action_pending \
        and not app.layout_pending and not app.score_pending,"drain ordinary requests before exit")
    var result := FileAccess.open(folder+"/result.json",FileAccess.WRITE)
    result.store_string(JSON.stringify({"frames":frames,"failures":failures,"renderer":DisplayServer.get_name()},"  "))
    print("LEARNING_UI_RESULT:","PASS" if failures.is_empty() else "FAIL")
    quit(0 if failures.is_empty() else 1)
