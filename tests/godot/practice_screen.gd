extends SceneTree
var failures: Array[String] = []
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("PRACTICE_SCREEN_FAIL:",message)
func state(phase: String = "ready") -> Dictionary:
    return {"loaded":true,"revision":1,"piece_fingerprint":"song","title":"A_real_piece",
        "mode":"practice","phase":phase,"hand":"right","bpm":72,"target_bpm":80,
        "first_bar":1,"last_bar":4,"current_bar":2,"device":"Test piano","midi_input_count":0,
        "clean_runs_required":3,"streak":1,"feedback":"Ready to play","skip_available":true,
        "lesson_step":2,"lesson_steps":4,
        "can_decrease_tempo":true,"can_increase_tempo":true,"manual_tempo_step_bpm":4,
        "running":phase in ["count_in","playing","paused"],"paused":phase == "paused",
        "hand_stages":[{"hand":"right","active":true},{"hand":"left","locked":true},{"hand":"both","locked":true}]}
func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    if not ResourceLoader.exists("res://practice_screen.gd"):
        check(false,"Independent Practice screen is not implemented")
    else:
        var view = load("res://practice_screen.gd").new()
        view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(view)
        await process_frame
        view.apply_viewport(Vector2(800,600),1.0)
        var scenario := OS.get_cmdline_user_args()[0]
        match scenario:
            "captions":
                var values := state()
                view.present(values,true)
                values.title = "mutated"
                view.present_busy(true)
                check(view.title_label.text == "A real piece" and view.speed_label.text == "♪ 72 BPM ▾" and view.speed_label.tooltip_text.contains("target 80 BPM"),"Practice captures title and tempo values")
                var named_source := state()
                named_source.exercise_strategy = "coda-fukuda-midi"
                named_source.stage_label = "Melody outline"
                view.present(named_source,true)
                check("Coda" not in view.title_label.tooltip_text and
                    "Melody outline" in view.title_label.tooltip_text,
                    "Practice introduces music without internal generator labels")
                view.present_busy(true)
                check(view.tempo_up_button.disabled and view.tempo_down_button.disabled and
                    view.practice_skip_button.disabled and view.practice_previous_button.disabled,
                    "Busy state updates every immediate Practice control")
                view.present(state("playing"),true)
                check(not view.details_panel.visible and view.stage.practice_stage_bar.visible == false,
                    "Practice keeps repeated learning HUD hidden")
                check(view.title_label.tooltip_text == "Learn · Measure 2 of 4" and view.start_button.text == "Pause","Live source-bar and transport captions are backend-derived")
                check(not view.feedback_label.visible and not view.lesson_info_label.visible,"Graded music keeps ordinary coaching outside the score")
                var learn := state("guided_complete")
                learn.mode = "learn"
                learn.teaching = {"target_count":4,"target_index":4,"has_more_units":true}
                view.present(learn,true)
                check(view.start_button.text == "Next idea" and "4 of 4 notes found" in view.progress_label.tooltip_text,"Learn owns its next-unit presentation: " + view.start_button.text + " / " + view.progress_label.text)
                var listening := state("playing")
                listening.mode = "listen"
                listening.demo = {"instrument":"Grand","sampled":true}
                view.present(listening,true,false,true)
                check(view.listen_button.text == "Practice" and view.feedback_label.visible and "could not load" in view.feedback_label.text,"Audio errors remain visible over busy Listen guidance")
            "signals":
                var intent: Array = []
                view.navigation_requested.connect(func(destination: String): intent.append(destination))
                view.play_requested.connect(func(): intent.append("play"))
                view.retry_requested.connect(func(): intent.append("retry"))
                view.listen_requested.connect(func(): intent.append("listen"))
                view.command_requested.connect(func(command: Dictionary): intent.append(command))
                view.present(state(),true)
                view._toggle_tempo_popup()
                check(view.tempo_popup.visible,"BPM button reveals tempo controls")
                view.tempo_popup.hide()
                view.practice_music_button.pressed.emit()
                view.practice_settings_button.pressed.emit()
                view.start_button.pressed.emit()
                view.practice_retry_button.pressed.emit()
                view.listen_button.pressed.emit()
                view.tempo_up_button.pressed.emit()
                view.practice_previous_button.pressed.emit()
                view.practice_skip_button.pressed.emit()
                check(intent == ["library","settings","play","retry","listen",{"action":"tempo_up"},
                    {"action":"select_step","number":1},
                    {"action":"skip_stage","reason":"Learner skipped to the next lesson from the practice screen"}],
                    "Previous and next lesson controls emit exact navigation without main callbacks")
                var first := state()
                first.lesson_step = 1
                view.present(first,true)
                view.practice_previous_button.pressed.emit()
                check(view.practice_previous_button.disabled and intent.size() == 8,
                    "Previous lesson is blocked on step one")
                var busy := state()
                busy.lesson_step = 3
                view.present(busy,true,true)
                view.practice_previous_button.pressed.emit()
                check(intent.size() == 8,"Busy previous navigation cannot dispatch")
            "score_gate":
                view.present(state(),false)
                view.present_score({
                    "ready":false,"visible":true,"text":"Missing note geometry",
                    "error":"Missing note geometry","retry_visible":true,
                    "browse_visible":false})
                check(view.stage.score_status_panel.visible and view.stage.score_retry_button.visible and not view.stage.score_browse_button.visible,"Persistent score errors own the stage status")
                check("Missing note geometry" in view.stage.score_status_label.text and view.start_button.disabled and view.practice_retry_button.disabled,"Score readiness gates both starts and retries")
                view.present(state("playing"),true)
                view.present_score({
                    "ready":true,"visible":false,"text":"","error":"",
                    "retry_visible":false,"browse_visible":false})
                check(not view.stage.score_status_panel.visible and not view.stage.phase_cue.visible and not view.start_button.disabled,"Ready notation hides the preparation capsule")
                view.stage.present_fingering({"unknown":2},1,"")
                check("2 unknown fingers" in view.stage.fingering_status_label.text and "1 needs space" in view.stage.fingering_status_label.text,"Fingering warnings receive explicit placement counts")
            "intro_markers":
                # A measure starts with an engraved rest but the real first
                # note is two beats later. The marker must follow the attack
                # on the renderer's global musical axis.
                var model := {
                    "schema":"piano-teacher-score-model-v1",
                    "beat_unit":"quarter","revision":77,
                    "duration_beats":8.0,
                    "notes":[
                        {"id":"right","onset_beats":2.0,"duration_beats":1.0,"hand":"right"},
                        {"id":"left","onset_beats":6.25,"duration_beats":1.0,"hand":"left"}],
                    "notation_events":[
                        {"kind":"rest","beat":0.0,"hand":"right"},
                        {"kind":"note","beat":2.0,"hand":"right","is_attack":true},
                        {"kind":"note","beat":6.25,"hand":"left","is_attack":true}],
                    "measures":[{"start_beat":0.0,"end_beat":4.0},
                                {"start_beat":4.0,"end_beat":8.0}]
                }
                check(view.stage.renderer.timeline.load_model(model),
                    "Native marker fixture uses an authentic contiguous source beat axis")
                view.stage.renderer.runway_origin_beat = 20.0
                var heading := state()
                heading.hand = "right"
                view.stage.present_runway_steps(heading,20.0)
                check(is_equal_approx(view.stage.runway_steps._current_start,22.0),
                    "Right-hand name sits on beat two's first note, not the opening rest")
                heading.hand = "left"
                view.stage.present_runway_steps(heading,20.0)
                check(is_equal_approx(view.stage.runway_steps._current_start,26.25),
                    "Changing active hand recomputes its own section start")
                heading.hand = "both"
                view.stage.present_runway_steps(heading,20.0)
                check(is_equal_approx(view.stage.runway_steps._current_start,22.0),
                    "Both hands use their earliest actually playable attack")
                view.stage.present_runway_steps(heading,20.0,30.0,"Next",240.0)
                check(is_equal_approx(view.stage.runway_steps._next_start,30.0) and
                    is_equal_approx(view.stage.runway_steps._next_density,240.0),
                    "The preloaded step retains its independent native score density")
            "source_picker":
                var intent: Array = []
                view.command_requested.connect(func(command: Dictionary): intent.append(command))
                view.navigation_requested.connect(func(destination: String): intent.append(destination))
                var values := state()
                values.piece_last_bar = 80
                view.present(values,true)
                view.show_source_picker(values)
                check(view.is_source_picker_open() and intent == ["practice"],"Source selection owns its overlay and requests the Practice route")
                view.open_picker.measure_slider.grab_focus()
                view.open_picker.measure_slider.value = 9
                view.open_picker.mode_choice.select(0)
                view.present_busy(true)
                view.confirm_source_picker()
                check(view.is_source_picker_open() and intent == ["practice"],"A pending command cannot silently drop source selection")
                view.present_busy(false)
                view.confirm_source_picker()
                check(not view.is_source_picker_open() and intent == ["practice","practice",{"action":"open_at","bar":9,"mode":"learn"}],"Confirmation captures selected measure and mode")
                view.show_source_picker(values)
                view.cancel_source_picker()
                check(not view.is_source_picker_open() and intent.back() == "library","Cancel returns to the music drawer")
            "midi_guard":
                var commands: Array = []
                view.command_requested.connect(func(command: Dictionary): commands.append(command))
                var values := state()
                view.present(values,true)
                view.consider_piano_start(true,true)
                view.show_source_picker(values)
                values.midi_input_count = 1
                view.suppress_piano_input(values)
                view.cancel_source_picker()
                view.present(values,true)
                view.consider_piano_start(true,true)
                check(commands.is_empty(),"Keys heard under a picker cannot arm a later transport")
                values.midi_input_count = 2
                view.present(values,true)
                view.consider_piano_start(true,true)
                view.consider_piano_start(true,true)
                check(commands == [{"action":"start"}],"One fresh piano attack produces one start intent")
                values.midi_input_count = 3
                view.present(values,true)
                view.consider_piano_start(false,true)
                check(commands.size() == 1,"Action acknowledgements never act as physical input polls")
            "layout":
                for dimensions in [Vector2i(800,600),Vector2i(1536,960)]:
                    root.size = dimensions
                    view.apply_viewport(Vector2(dimensions),1.0)
                    var expected := Rect2()
                    for phase in ["ready","count_in","playing","paused","feedback","ready"]:
                        var values := state(phase)
                        values.feedback = "Long guidance ".repeat(80)
                        values.next_action = "Next instruction ".repeat(80)
                        view.present(values,true)
                        view.stage.present_fingering({},1 if phase != "ready" else 0,"")
                        for frame in range(8): await process_frame
                        var rect: Rect2 = view.stage.score_frame.get_global_rect()
                        if expected.size == Vector2.ZERO: expected = rect
                        check(rect.is_equal_approx(expected),"Phase captions preserve settled score bounds: " + phase)
                        check(root.get_visible_rect().encloses(view.practice_controls.get_global_rect()),"All transport controls remain inside the viewport")
        view.free()
    print("PRACTICE_SCREEN_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
