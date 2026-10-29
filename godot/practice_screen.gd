extends VBoxContainer
# Owns Practice widgets, guidance, dialogs and presentation/input state.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL
const ChallengeFlow := preload("res://challenge_flow.gd")
const GameInputIndicator := preload("res://game_input_indicator.gd")
const GameStreak := preload("res://game_streak.gd")
const GameTransportButton := preload("res://game_transport_button.gd")
const PerformanceReviewStrip := preload("res://performance_review_strip.gd")
const ScoreStage := preload("res://practice_score_stage.gd")
signal navigation_requested(destination: String)
signal command_requested(command: Dictionary)
signal play_requested
signal retry_requested
signal listen_requested
signal score_retry_requested
var stage: ScoreStage
var practice_layout_box: VBoxContainer
var practice_header: HBoxContainer
var practice_navigation: HFlowContainer
var game_brand: Label
var title_label: Label
var passage_label: Label
var speed_label: Label
var hand_label: Label
var game_input_indicator: Control
var lesson_info_label: Label
var practice_progress: ProgressBar
var progress_label: Label
var tempo_down_button: Button
var tempo_up_button: Button
var game_streak: Control
var practice_skip_button: Button
var feedback_label: Label
var performance_review: PerformanceReviewStrip
var practice_controls: HFlowContainer
var practice_retry_button: Button
var start_button: Button
var listen_button: Button
var practice_music_button: Button
var practice_settings_button: Button
var open_picker: Control
var pause_sheet: Control
var review_sheet: AcceptDialog
var advanced_pause_open := false
var ui_scale := 1.0
var _state: Dictionary = {}
var _previous_state: Dictionary = {}
var _score_ready := false
var _score_error := ""
var _busy := false
var _audio_error := false
var _active := true
var _hand_unlock_message := ""
var _hand_unlock_until_ms := 0
var _last_input_count := -1
var _fresh_piano_key := false

func _ready() -> void:
    name = "PracticeScreen"
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    theme = Design.create()
    var practice_layout: VBoxContainer = self
    practice_layout_box = practice_layout
    # One compact lesson header. Music occupies the expanding stage below;
    # navigation never gets a separate full-width toolbar of its own.
    practice_header = HBoxContainer.new()
    practice_header.add_theme_constant_override("separation", 20)
    practice_layout.add_child(practice_header)
    var heading := UI.stack(5)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    heading.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_header.add_child(heading)
    title_label = UI.title("Choose your music", 26)
    title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(title_label)
    passage_label = UI.label("A little practice. A little progress.", 14, MUTED)
    passage_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    passage_label.clip_text = true
    passage_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(passage_label)
    var context := UI.stack(6)
    context.custom_minimum_size.x = 435
    context.size_flags_horizontal = Control.SIZE_SHRINK_END
    practice_header.add_child(context)
    practice_navigation = HFlowContainer.new()
    practice_navigation.alignment = FlowContainer.ALIGNMENT_END
    practice_navigation.add_theme_constant_override("h_separation", 6)
    context.add_child(practice_navigation)
    game_brand = UI.title("Piano Teacher", 18)
    game_brand.visible = false
    practice_navigation.add_child(game_brand)
    practice_music_button = _button("Music", func(): navigation_requested.emit("library"), false, "library")
    practice_music_button.tooltip_text = "Choose a piece · Escape"
    practice_navigation.add_child(practice_music_button)
    var path_button := _button("Path", func(): navigation_requested.emit("lesson"), false, "navigation")
    path_button.tooltip_text = "Learning stages and advanced practice"
    practice_navigation.add_child(path_button)
    practice_settings_button = _button("Settings", func(): navigation_requested.emit("settings"), false, "settings")
    practice_navigation.add_child(practice_settings_button)
    var details := HBoxContainer.new()
    details.add_theme_constant_override("separation", 14)
    details.alignment = BoxContainer.ALIGNMENT_END
    context.add_child(details)
    speed_label = UI.label("-- BPM", 14, INK)
    speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    speed_label.size_flags_horizontal = Control.SIZE_SHRINK_END
    details.add_child(speed_label)
    hand_label = UI.label("", 14, ACCENT)
    hand_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    hand_label.size_flags_horizontal = Control.SIZE_SHRINK_END
    details.add_child(hand_label)
    game_input_indicator = GameInputIndicator.new()
    details.add_child(game_input_indicator)
    lesson_info_label = UI.label("", 14, MUTED)
    lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    stage = ScoreStage.new()
    add_child(stage)
    stage.navigation_requested.connect(func(destination: String): navigation_requested.emit(destination))
    stage.command_requested.connect(func(command: Dictionary): command_requested.emit(command))
    stage.score_retry_requested.connect(func(): score_retry_requested.emit())
    practice_progress = ProgressBar.new()
    practice_progress.show_percentage = false
    practice_progress.max_value = 1.0
    practice_progress.custom_minimum_size = Vector2(0, 4)
    practice_progress.add_theme_stylebox_override("background", Design.surface(Color("#25443E"), 3))
    practice_progress.add_theme_stylebox_override("fill", Design.surface(Color("#70E5BF"), 3))
    (practice_progress.get_theme_stylebox("background") as StyleBoxFlat).set_content_margin_all(0)
    (practice_progress.get_theme_stylebox("fill") as StyleBoxFlat).set_content_margin_all(0)
    practice_layout.add_child(practice_progress)
    # Progress already appears as a single thin rail *inside* GameStage.
    # A second full-width bar below the notation made this a dashboard.
    practice_progress.visible = false
    var information := VBoxContainer.new()
    information.add_theme_constant_override("separation", 4)
    practice_layout.add_child(information)
    var challenge_bar := HBoxContainer.new()
    challenge_bar.add_theme_constant_override("separation", 18)
    information.add_child(challenge_bar)
    progress_label = UI.label("", 14, MUTED)
    progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    progress_label.clip_text = true
    progress_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    progress_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    challenge_bar.add_child(progress_label)
    # Keep navigation separate from both notation ink and the progress/tempo
    # row, whose combined minimum width would clip an 800x600 practice window.
    tempo_down_button = _button("-5 BPM", func(): command_requested.emit({"action":"tempo_down"}),
        false, "settings")
    tempo_down_button.tooltip_text = "Slow this lesson step without changing its song target"
    challenge_bar.add_child(tempo_down_button)
    tempo_up_button = _button("+5 BPM", func(): command_requested.emit({"action":"tempo_up"}),
        false, "settings")
    tempo_up_button.tooltip_text = "Advance this stage's tempo without changing its target or awarding clean passes"
    tempo_up_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(tempo_up_button)
    game_streak = GameStreak.new()
    challenge_bar.add_child(game_streak)
    # Navigation is deliberately outside the three transport buttons.
    # The progress row directly below the score gives Skip a stable,
    # immediately visible location without changing the control cluster.
    practice_skip_button = _button("Next lesson", _skip_lesson,
        false, "navigation")
    practice_skip_button.tooltip_text = "Go to the next lesson without earning mastery"
    practice_skip_button.disabled = true
    practice_skip_button.visible = false
    practice_skip_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(practice_skip_button)
    feedback_label = UI.label("Ready", 14, MUTED)
    feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    feedback_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    information.add_child(_caption_slot(feedback_label, 1))
    information.add_child(_caption_slot(lesson_info_label, 1))
    performance_review = PerformanceReviewStrip.new()
    performance_review.ui_scale = ui_scale
    performance_review.review_requested.connect(func(summary: Dictionary):
        if review_sheet != null:
            review_sheet.call("open_review", summary))
    information.add_child(performance_review)
    # Flow containers wrap whole readable buttons instead of clipping labels
    # when the practice window is narrow or the user uses larger UI fonts.
    var controls := HFlowContainer.new()
    practice_controls = controls
    controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    controls.alignment = FlowContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("h_separation", 12)
    controls.add_theme_constant_override("v_separation", 8)
    practice_layout.add_child(controls)
    practice_retry_button = _transport_button("Retry", func(): retry_requested.emit(), "retry")
    practice_retry_button.tooltip_text = "Repeat the current passage · R"
    controls.add_child(practice_retry_button)
    start_button = _transport_button("Play", func(): play_requested.emit(), "play", true)
    controls.add_child(start_button)
    listen_button = _transport_button("Listen", func(): listen_requested.emit(), "listen")
    listen_button.tooltip_text = "Hear this passage, or return to practice · L"
    controls.add_child(listen_button)
    var modal_layer := CanvasLayer.new()
    modal_layer.layer = 1
    add_child(modal_layer)
    open_picker = preload("res://source_measure_picker.gd").new()
    open_picker.confirmed.connect(func(_bar: int, _mode: String): confirm_source_picker())
    open_picker.cancel_requested.connect(cancel_source_picker)
    modal_layer.add_child(open_picker)
    pause_sheet = preload("res://pause_sheet.gd").new()
    pause_sheet.z_index = 30
    modal_layer.add_child(pause_sheet)
    pause_sheet.chosen.connect(func(command: Dictionary):
        if command.get("action") == "exit":
            command_requested.emit({"action":"stop"})
            navigation_requested.emit("library")
        else: command_requested.emit(command))
    review_sheet = preload("res://review_sheet.gd").new()
    modal_layer.add_child(review_sheet)
    review_sheet.retry_requested.connect(func(first_bar: int, last_bar: int):
        command_requested.emit({"action":"review_retry","first_bar":first_bar,"last_bar":last_bar}))


func present(parsed: Dictionary, ready: bool, busy := false, audio_error := false) -> void:
    _previous_state = _state
    _state = parsed.duplicate(true)
    _score_ready = ready
    _audio_error = audio_error
    var count: int = int(parsed.get("midi_input_count",0))
    _fresh_piano_key = _last_input_count >= 0 and count > _last_input_count
    _last_input_count = count
    var unlocked: String = ChallengeFlow.newly_unlocked(_previous_state,parsed)
    if not unlocked.is_empty():
        _hand_unlock_message = unlocked
        _hand_unlock_until_ms = Time.get_ticks_msec() + 2600
        game_streak.pulse_unlock()
        stage.pulse_hand_unlock()
    present_busy(busy)
    stage.present(parsed,busy)
    game_input_indicator.present(parsed)
    if not bool(parsed.get("loaded",false)):
        stage.renderer.visible = false
        game_streak.present({})
        feedback_label.text = str(parsed.get("feedback","Open a score"))
        present_score(ready,_score_error)
        return
    title_label.text = str(parsed.get("title", "Piano Teacher")).replace("_", " ")
    var kind := str(parsed.get("kind", "learn")).capitalize()
    var passage_text: String = ("%s · Measures %d–%d" % [
        kind, int(parsed.get("first_bar", 0)), int(parsed.get("last_bar", 0))])
    if bool(parsed.get("warmup", false)):
        var hand_step: int = (["left", "right", "both"].find(str(parsed.get("hand", "left"))) + 1)
        passage_text = "WARM-UP %d/3 · %s · Measures %d–%d" % [
            hand_step, str(parsed.get("hand", "left")).to_upper(),
            int(parsed.get("first_bar", 1)), int(parsed.get("last_bar", 8))]
    if not bool(parsed.get("warmup", false)):
        var chosen_bar: int = int(parsed.get("selected_start_bar", 1))
        if chosen_bar > int(parsed.get("first_bar", 1)):
            passage_text += " · Start at measure %d" % chosen_bar
    # The live bar number comes from Python's source meter grid. Do not infer
    # measures from elapsed seconds in Godot (pickup and changing meters).
    var current_bar: int = int(parsed.get("current_bar", 0))
    var phase_for_bar: String = str(parsed.get("phase", "ready"))
    if current_bar > 0 and phase_for_bar in ["count_in", "playing", "paused"]:
        var first_bar: int = int(parsed.get("first_bar", 1))
        var last_bar: int = int(parsed.get("last_bar", first_bar))
        var bar_text := "Measure %d of %d" % [current_bar, last_bar]
        if bool(parsed.get("warmup", false)):
            var hand_step: int = ["left", "right", "both"].find(str(parsed.get("hand", "left"))) + 1
            passage_text = "WARM-UP %d/3 · %s · %s" % [
                hand_step, str(parsed.get("hand", "left")).to_upper(), bar_text]
        else:
            passage_text = "%s · %s" % [kind, bar_text]
    if tempo_down_button != null:
        tempo_down_button.text = "-%d BPM" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_down_button.disabled = (_busy or not bool(parsed.get("can_decrease_tempo", false))
            or str(parsed.get("phase", "")) in ["count_in", "playing", "loading"])
    if tempo_up_button != null:
        tempo_up_button.text = "+%d BPM" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_up_button.disabled = (_busy or not bool(parsed.get("can_increase_tempo",false))
            or str(parsed.get("phase","")) in ["count_in","playing","loading"])
    var speed_text := "%d BPM" % int(parsed.get("bpm", 0))
    if int(parsed.get("bpm", 0)) != int(parsed.get("target_bpm", parsed.get("bpm", 0))):
        speed_text += " · target %d" % int(parsed.get("target_bpm", 0))
    speed_label.text = speed_text
    var recovery_notice: Variant = parsed.get("recovery_notice")
    speed_label.tooltip_text = "Current practice tempo and your selected target"
    hand_label.text = "Both hands" if str(parsed.get("hand", "right")) == "both" else str(parsed.get("hand", "right")).capitalize() + " hand"
    hand_label.tooltip_text = "Current hand of the backend lesson"
    game_input_indicator.present(parsed)
    var stage: String = str(parsed.get("lesson_level", "original"))
    var explanations := {"skeleton": "Find the main notes first.",
        "outline": "Add the chord notes while keeping the pulse.",
        "original": "Bring every note together."}
    # Assemble each caption before assigning it. Writing a default and then
    # replacing/appending it dirties the canvas on every identical state poll.
    var instruction_text: String = str(explanations.get(stage, ""))
    if stage.begins_with("section-"):
        instruction_text = "Play this complete section smoothly, then continue to the next."
    var instruction_tone: Color = INK
    var import_warnings: Array = parsed.get("import_warnings", [])
    if not import_warnings.is_empty() and str(parsed.get("phase", "")) in ["ready", "feedback", "performance_complete"]:
        instruction_text = "MIDI imported with repairs: " + "  ".join(import_warnings)
        instruction_tone = Color("#F1C67D")
    var learning: bool = str(parsed.get("mode", "practice")) == "learn"
    var teaching: Dictionary = parsed.get("teaching", {}) if parsed.get("teaching") is Dictionary else {}
    var learner: Dictionary = parsed.get("learner", {}) if parsed.get("learner") is Dictionary else {}
    practice_skip_button.visible = bool(parsed.get("loaded", false))
    practice_skip_button.disabled = not bool(parsed.get("skip_available", false)) or _busy
    var progress_text := ""
    var progress_tone: Color = progress_label.get_theme_color("font_color")
    if learning:
        var targets: int = int(teaching.get("target_count", 0))
        instruction_text = "Find the highlighted notes at your own pace."
        progress_text = "Notes found %d of %d · No rhythm scoring yet" % [int(teaching.get("target_index", 0)), targets]
        if not learner.is_empty():
            var unit_number: int = int(learner.get("unit_number", 0))
            var context: String = "Idea %d of %d" % [unit_number, int(learner.get("total_units", 1))] if unit_number > 0 else "Selected bars %d–%d" % [int(parsed.get("first_bar", 1)), int(parsed.get("last_bar", 1))]
            progress_text = "%s · Notes found %d of %d" % [context, int(teaching.get("target_index", 0)), targets]
    practice_progress.value = float(parsed.get("progress", 0.0))
    var phase: String = str(parsed.get("phase", "ready"))
    if not bool(parsed.get("paused",false)): advanced_pause_open = false
    _present_pause()
    start_button.visible = true
    listen_button.disabled = not bool(parsed.get("loaded", false))
    listen_button.text = "Practice" if str(parsed.get("mode", "")) == "listen" else "Listen"
    var listen_kind := "practice" if listen_button.text == "Practice" else "listen"
    if str(listen_button.get("action_kind")) != listen_kind:
        listen_button.call("configure", listen_kind)
        _game_button(listen_button)
    practice_retry_button.disabled = (not bool(parsed.get("loaded", false))
        or not _score_ready)
    var summary: Dictionary = parsed.get("performance_summary", {}) if parsed.get("performance_summary") is Dictionary else {}
    performance_review.present(summary)
    var selected_retry: Variant = parsed.get("review_range")
    if selected_retry is Dictionary:
        passage_text = "Repeating measures %d–%d · %s" % [
            int(selected_retry.get("first_bar", 1)),
            int(selected_retry.get("last_bar", 1)),
            "No full-passage mastery"]
    var active_transport: bool = _active_transport(parsed)
    var feedback_text := ""
    if learning:
        feedback_text = str(parsed.get("feedback", "Find the highlighted notes at your own pace."))
    elif phase == "paused":
        feedback_text = "Paused · press Play to resume"
    elif phase == "loading":
        feedback_text = "Preparing next passage · count-in waits for score"
    elif phase == "recovering":
        feedback_text = str(parsed.get("feedback", "Short break before retry"))
    elif phase == "count_in":
        feedback_text = "GET READY · follow the teal playhead"
    elif phase == "playing":
        var midi_count: int = int(parsed.get("midi_notes", 0))
        if bool(parsed.get("preview_only", false)):
            feedback_text = "PREVIEW · connect your piano to earn clean runs"
        else:
            feedback_text = "PLAYING · %d notes heard" % midi_count if midi_count > 0 else "PLAYING · waiting for your piano"
    else:
        feedback_text = str(parsed.get("feedback", ""))
    if str(parsed.get("mode", "")) == "listen":
        var demo_info: Dictionary = parsed.get("demo", {}) if parsed.get("demo") is Dictionary else {}
        var instrument: String = str(demo_info.get("instrument", "Preparing piano audio"))
        feedback_text = ("Listening · " + instrument if bool(parsed.get("running", false))
            else str(parsed.get("feedback", "Preparing Listen audio")))
        if bool(parsed.get("paused", false)):
            feedback_text = "Listen paused · " + instrument
        if bool(demo_info.get("audio_available", false)) and not bool(demo_info.get("sampled", false)):
            instruction_text = "Basic piano sound · install the Salamander samples for acoustic Listen (see README)."
        elif bool(demo_info.get("sampled", false)):
            instruction_text = "Acoustic grand piano · " + instrument
        if _audio_error:
            feedback_text = "Listen audio could not load. Choose Listen to try again."
    var unpositioned: int = int(parsed.get("feedback_unmapped", 0))
    if unpositioned > 0:
        feedback_text += " · %d unpositioned note(s)" % unpositioned
    if (not learning and phase in ["ready", "performance_complete"]
            and not str(parsed.get("device", "")).is_empty()):
        instruction_text = "Play any piano key to start the count-in. Release it, then play after the count-in."
    elif learning and phase == "guided_complete" and not str(parsed.get("device", "")).is_empty():
        instruction_text = "Idea complete · play one new piano key to continue."
    elif phase == "feedback" and not bool(parsed.get("auto", false)) and not str(parsed.get("device", "")).is_empty():
        instruction_text = "Review the red notes · play a new piano key to retry."
    if not learning:
        var needed_runs: int = int(parsed.get("clean_runs_required", 3))
        progress_text = "Clean runs %d of %d at %d BPM" % [
            int(parsed.get("streak", 0)), needed_runs, int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
        if bool(parsed.get("warmup", false)):
            var name: String = "Both hands" if str(parsed.get("hand", "")) == "both" else str(parsed.get("hand", "")).capitalize() + " hand"
            progress_text = "%s · %d of %d clean runs · Next hand unlocks when mastered" % [
                name, int(parsed.get("streak", 0)), needed_runs]
        if str(parsed.get("mode", "")) == "perform":
            progress_text = "Perform · keep going to the end; review follows"
        elif str(parsed.get("mode", "")) == "listen":
            progress_text = "Listen · example audio; your playing is not graded"
    var next_action: String = str(parsed.get("next_action", ""))
    if not next_action.is_empty() and (phase in ["feedback", "recovering", "loading", "paused"] or bool(parsed.get("guided_recovery", false))):
        instruction_text = next_action
        var remaining = parsed.get("transition_in_seconds")
        if remaining != null:
            instruction_text = ("After resume · " if phase == "paused" else "Next in %.1f s · " % maxf(0.0, float(remaining))) + next_action
    # The backend's judged take and persisted streak are the ONLY sources
    # for this three-clean-pass challenge. No UI-side scoring or timers.
    var challenge: Dictionary = ChallengeFlow.present(parsed)
    game_streak.present(challenge)
    if bool(challenge.get("visible", false)):
        progress_text = str(challenge.get("label", ""))
        progress_label.tooltip_text = str(challenge.get("detail", ""))
        var challenge_kind: String = str(challenge.get("kind", ""))
        progress_tone = Color("#78DBAD") if challenge_kind == "success" else \
            Color("#F0B971") if challenge_kind in ["retry", "recovering"] else INK
        if challenge_kind == "success" and next_action.is_empty():
            instruction_text = str(challenge.get("detail", ""))
        if Time.get_ticks_msec() < _hand_unlock_until_ms:
            progress_text = _hand_unlock_message
            progress_tone = Color("#78DBAD")
            progress_label.tooltip_text = _hand_unlock_message
    # Some recovery transitions provide only recovery_notice, without a
    # next_action. Keep the essential tempo and measure changes in the normal
    # instruction line; never restore the in-score banner.
    if (recovery_notice is Dictionary and next_action.is_empty()
            and str(parsed.get("mode", "")) == "practice"
            and phase in ["ready", "feedback", "recovering", "loading"]
            and str(challenge.get("kind", "")) != "success"):
        var notice: Dictionary = recovery_notice
        var previous_tempo: int = int(notice.get("from_bpm", 0))
        var new_tempo: int = int(notice.get("to_bpm", 0))
        if str(notice.get("kind", "")) == "speedup":
            instruction_text = "Tempo %d → %d BPM · keep practising" % [previous_tempo, new_tempo]
        else:
            instruction_text = "Tempo %d → %d BPM · retry measures %d–%d" % [
                previous_tempo, new_tempo, int(notice.get("first_bar", 1)),
                int(notice.get("last_bar", 1))]
    passage_label.text = passage_text
    progress_label.text = progress_text
    lesson_info_label.text = instruction_text
    feedback_label.text = feedback_text
    if progress_label.get_theme_color("font_color") != progress_tone:
        progress_label.add_theme_color_override("font_color", progress_tone)
    if lesson_info_label.get_theme_color("font_color") != instruction_tone:
        lesson_info_label.add_theme_color_override("font_color", instruction_tone)
    # During graded playback, notation and MIDI note reactions provide the
    # information. Preserve warnings for ungraded previews and audio errors.
    var busy_music: bool = phase in ["playing", "count_in"] and not learning
    var audio_problem: bool = _audio_error
    feedback_label.visible = not busy_music or bool(parsed.get("preview_only", false)) \
        or audio_problem or unpositioned > 0
    lesson_info_label.visible = (learning or not busy_music
        or bool(parsed.get("guided_recovery", false)))
    feedback_label.tooltip_text = feedback_label.text
    lesson_info_label.tooltip_text = lesson_info_label.text
    # One short verb belongs on the central game control. Shortcuts and
    # explanations live in the tooltip instead of making every button a menu.
    var start_text := "Resume" if bool(parsed.get("paused", false)) else "Pause" if active_transport else "Play"
    if learning:
        start_text = "Resume" if phase == "paused" else "Try rhythm" if phase in ["guided_complete", "disconnected"] else "Pause" if phase in ["guided_wait", "loading"] else "Learn"
        if phase == "guided_complete" and bool(parsed.get("guided_recovery", false)):
            start_text = "Retry rhythm"
        elif phase == "guided_complete" and bool(teaching.get("has_more_units", false)):
            start_text = "Next idea"
    elif str(parsed.get("mode", "")) == "listen" and not active_transport:
        start_text = "Back to warm-up" if bool(parsed.get("warmup", false)) else "Listen again"
    start_button.text = start_text
    start_button.tooltip_text = "Play, pause or resume · Space · Play any piano key when ready"
    start_button.disabled = not active_transport and (not _score_ready)
    start_button.call("configure", "pause" if start_button.text == "Pause" else "play",
        active_transport and not bool(parsed.get("paused", false)))
    listen_button.call("configure", "practice" if str(parsed.get("mode", "")) == "listen" else "listen",
        str(parsed.get("mode", "")) == "listen")

func present_busy(busy: bool) -> void:
    _busy = busy
    var blocked: bool = busy or not bool(_state.get("loaded",false)) or str(_state.get("phase","")) in ["count_in","playing","loading"]
    tempo_down_button.disabled = blocked or not bool(_state.get("can_decrease_tempo",false))
    tempo_up_button.disabled = blocked or not bool(_state.get("can_increase_tempo",false))
    practice_skip_button.disabled = busy or not bool(_state.get("skip_available",false))
    stage.steps.present_busy(busy)

func present_score(ready: bool, error: String) -> void:
    _score_ready = ready
    _score_error = error
    stage.present_score_status(bool(_state.get("loaded",false)),ready,error)
    start_button.disabled = not _active_transport(_state) and not ready
    practice_retry_button.disabled = not bool(_state.get("loaded",false)) or not ready

func present_message(message: String, reveal := false) -> void:
    feedback_label.text = message
    if reveal: feedback_label.visible = true

func begin_action(requested: String, pending := "") -> void:
    if not pending.is_empty():
        present_message("Please wait · finishing " + pending,true)
        return
    var verb: String = {"listen":"Preparing piano audio","practice":"Returning to practice",
        "start":"Starting count-in","pause":"Pausing","resume":"Resuming","restart":"Restarting the passage",
        "skip_stage":"Loading next lesson","stop":"Stopping"}.get(requested,"Applying " + requested.replace("_"," "))
    present_message(verb + "…",true)
    stage.practice_playback_banner.text = verb + "…"
    stage.practice_playback_banner.visible = true

func finish_action() -> void:
    stage.practice_playback_banner.visible = false

func _active_transport(state: Dictionary) -> bool:
    return bool(state.get("running",false)) or str(state.get("phase","")) in ["count_in","playing","paused","feedback","recovering","loading","preview_gap"]

func set_active(active: bool) -> void:
    _active = active
    _present_pause()

func _present_pause() -> void:
    pause_sheet.present(_state if _active and advanced_pause_open else {})

func open_advanced_pause() -> void:
    navigation_requested.emit("practice")
    advanced_pause_open = true
    if bool(_state.get("paused",false)): _present_pause()
    elif _active_transport(_state): command_requested.emit({"action":"pause"})
    else: advanced_pause_open = false

func _skip_lesson() -> void:
    if not _busy and bool(_state.get("skip_available",false)):
        command_requested.emit({"action":"skip_stage","reason":"Learner skipped to the next lesson from the practice screen"})

func is_source_picker_open() -> bool:
    return open_picker != null and open_picker.visible

func show_source_picker(state: Dictionary) -> void:
    navigation_requested.emit("practice")
    suppress_piano_input(state)
    open_picker.show_piece(state)

func cancel_source_picker() -> void:
    open_picker.visible = false
    navigation_requested.emit("library")

func confirm_source_picker() -> void:
    if _busy or not is_source_picker_open(): return
    var bar: int = open_picker.selected_bar()
    var mode: String = open_picker.selected_mode()
    open_picker.visible = false
    navigation_requested.emit("practice")
    command_requested.emit({"action":"open_at","bar":bar,"mode":mode})

func suppress_piano_input(state: Dictionary) -> void:
    _last_input_count = int(state.get("midi_input_count",0))
    _fresh_piano_key = false

func consider_piano_start(polled: bool, active: bool) -> void:
    var fresh := _fresh_piano_key
    _fresh_piano_key = false
    var phase: String = str(_state.get("phase",""))
    if (not fresh or not polled or not active or _busy or not _score_ready or is_source_picker_open()
            or int(_previous_state.get("revision",-1)) != int(_state.get("revision",-1))
            or str(_previous_state.get("phase","")) != phase or str(_state.get("device","")).is_empty()): return
    if phase in ["ready","performance_complete","guided_complete"] or (phase == "feedback" and str(_state.get("mode","")) == "practice" and not bool(_state.get("auto",false))):
        if str(_state.get("mode","")) == "learn": play_requested.emit()
        elif phase == "feedback": command_requested.emit({"action":"restart"})
        elif str(_state.get("mode","")) in ["practice","perform"]: command_requested.emit({"action":"start"})

func apply_viewport(view_size: Vector2, scale: float) -> void:
    ui_scale = scale
    _resize_fonts(self)
    var width: float = view_size.x
    var compact: bool = view_size.y < 750.0
    var margin: int = 26 if width >= 1100.0 else 14
    stage.apply_viewport(view_size,scale,compact)
    open_picker.resize_panel(view_size)
    # The reserved score header keeps navigation outside the notation region.
    var compact_steps: bool = width < 1250.0
    progress_label.visible = true
    for bpm_button in [tempo_down_button, tempo_up_button]:
        bpm_button.custom_minimum_size.x = 84.0 if compact_steps else 100.0
    practice_header.add_theme_constant_override("separation", 10 if width < 950.0 else 20)
    game_brand.visible = false
    practice_navigation.add_theme_constant_override("h_separation", 8 if width >= 1000.0 else 5)
    practice_navigation.add_theme_constant_override("v_separation", 4)
    for child in practice_navigation.get_children():
        if child is Button:
            var button := child as Button
            var font_size := _ui_font(12)
            button.add_theme_font_size_override("font_size", font_size)
            var measured: float = button.get_theme_font("font").get_string_size(
                button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
            # Icon + label still need one accessible, unclipped click target.
            button.custom_minimum_size = Vector2(maxf(78.0, measured + 40.0),
                32.0)
            button.clip_text = false
    if practice_controls != null:
        practice_layout_box.add_theme_constant_override("separation", 6 if compact else 9)
        # The expanding score panel gets all remaining vertical space.
        # A window-relative minimum ignored the keyboard/status heights and
        # pushed the transport below the screen when those became visible.
        for child in practice_controls.get_children():
            if child is Button:
                var button := child as Button
                var central: bool = button == start_button
                var font_size := _ui_font(16 if central else 15)
                button.add_theme_font_size_override("font_size", font_size)
                var measured: float = button.get_theme_font("font").get_string_size(
                    button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                var available: float = maxf(0.0, width - float(margin * 2) - 56.0)
                var ideal: float = maxf(180.0 if central else 145.0, measured + 68.0)
                # At 800px all three keys must fit on one row, without
                # shrinking their active hit areas to website-sized chips.
                var per_button: float = maxf(155.0, (available - 48.0) / 3.0)
                button.custom_minimum_size = Vector2(
                    minf(ideal * (1.13 if width >= 1600.0 else 1.0), per_button * (1.18 if central else .91)),
                    54.0)
                button.clip_text = false
        title_label.add_theme_font_size_override("font_size", _ui_font(24))
        passage_label.add_theme_font_size_override("font_size", _ui_font(15))
        speed_label.add_theme_font_size_override("font_size", _ui_font(14))
        hand_label.add_theme_font_size_override("font_size", _ui_font(14))
        progress_label.add_theme_font_size_override("font_size", _ui_font(15))
        game_streak.custom_minimum_size = Vector2(130 if width < 950 else 155, 30)
        game_input_indicator.custom_minimum_size.y = 22
        feedback_label.add_theme_font_size_override("font_size", _ui_font(14))
        lesson_info_label.add_theme_font_size_override("font_size", _ui_font(14))
        var instruction_lines := 2 if width < 1000.0 else 1
        lesson_info_label.set_meta("caption_lines", instruction_lines)
        lesson_info_label.max_lines_visible = instruction_lines
        lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if instruction_lines == 2 else TextServer.AUTOWRAP_OFF
        _resize_caption_slots()
func _caption_slot(caption: Label, lines: int) -> Control:
    # Containers must reserve this space even when the phase hides its text.
    # A plain Control prevents wrapped label minimum sizes resizing the score.
    var slot := Control.new()
    slot.name = "FeedbackCaption" if caption == feedback_label else "InstructionCaption"
    slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    slot.clip_contents = true
    caption.set_meta("caption_lines", lines)
    caption.max_lines_visible = lines
    caption.mouse_filter = Control.MOUSE_FILTER_PASS
    caption.clip_text = true
    caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    caption.autowrap_mode = TextServer.AUTOWRAP_OFF if lines == 1 else TextServer.AUTOWRAP_WORD_SMART
    slot.add_child(caption)
    caption.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    return slot


func _resize_caption_slots() -> void:
    for caption in [feedback_label, lesson_info_label]:
        var lines: int = int(caption.get_meta("caption_lines", 1))
        var font: Font = caption.get_theme_font("font")
        var font_size: int = caption.get_theme_font_size("font_size")
        var line_spacing: int = caption.get_theme_constant("line_spacing")
        caption.get_parent().custom_minimum_size.y = ceilf(
            font.get_height(font_size) * lines + line_spacing * (lines - 1))


func _game_button(button: Button, central := false) -> void:
    # Buttons on the piano stage are instrument controls rather than
    # generic form submissions. Keep a fixed tactile vocabulary.
    button.add_theme_font_size_override("font_size", _ui_font(17 if central else 15))
    var normal := StyleBoxFlat.new()
    var kind: String = str(button.get("action_kind"))
    var role: String = "play" if central else kind
    var accent: Color = Design.role_accent(role)
    normal.bg_color = Design.MINT if central else Design.role_fill(role)
    button.set_meta("ui_button_role",
        "transport_primary" if central else "transport_retry" if kind == "retry" else "transport_listen")
    normal.set_corner_radius_all(7)
    normal.set_content_margin_all(12)
    normal.set_border_width_all(1)
    normal.border_color = Color(accent, .7 if central else .22)
    normal.shadow_color = Color(Design.MINT, .10) if central else Color.TRANSPARENT
    normal.shadow_size = 10 if central else 0
    button.add_theme_stylebox_override("normal", normal)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = normal.bg_color.lightened(.16)
    hover.border_color = accent.lightened(.14)
    hover.shadow_size = 0
    button.add_theme_stylebox_override("hover", hover)
    var pressed := normal.duplicate() as StyleBoxFlat
    pressed.bg_color = normal.bg_color.darkened(.18)
    pressed.shadow_size = 0
    pressed.shadow_offset = Vector2.ZERO
    button.add_theme_stylebox_override("pressed", pressed)
    var disabled := normal.duplicate() as StyleBoxFlat
    disabled.bg_color = Design.PANEL_RECESSED
    disabled.border_color = Color(Design.BORDER, .3)
    disabled.shadow_size = 0
    button.add_theme_stylebox_override("disabled", disabled)
    var focus := normal.duplicate() as StyleBoxFlat
    focus.bg_color = Color.TRANSPARENT
    focus.border_color = Design.FOCUS
    focus.set_border_width_all(2)
    focus.shadow_size = 0
    button.add_theme_stylebox_override("focus", focus)
    if not button is GameTransportButton:
        button.add_theme_color_override("font_color", Color("#F4FFF9") if central else Color("#D6E7DD"))
        button.add_theme_color_override("font_hover_color", Color.WHITE)
        button.add_theme_color_override("font_pressed_color", Color.WHITE)
        button.add_theme_color_override("font_disabled_color", Color("#748B82"))
    button.clip_text = false


func _transport_button(label: String, callback: Callable, kind: String, central := false) -> Button:
    var button := GameTransportButton.new()
    button.text = label
    button.clip_text = false
    button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
    button.pressed.connect(callback)
    button.configure(kind)
    button.custom_minimum_size = Vector2(250 if central else 205, 76 if central else 70)
    _game_button(button, central)
    return button


func _ui_font(base: int) -> int:
    return UI.font_size(base,ui_scale)

func _resize_fonts(node: Node) -> void:
    if node is Control and node.has_meta("ui_font_base"):
        node.add_theme_font_size_override("font_size",_ui_font(int(node.get_meta("ui_font_base"))))
    if node.has_method("set_text_scale"): node.call("set_text_scale",ui_scale)
    for child in node.get_children(): _resize_fonts(child)

func _button(caption: String, action: Callable, primary := false, role := "") -> Button:
    var button := UI.button(caption,role if not role.is_empty() else "primary" if primary else "secondary",ui_scale)
    button.pressed.connect(action)
    return button

func handle_source_input(event: InputEvent) -> bool:
    if not is_source_picker_open(): return false
    if event is InputEventKey and event.pressed and not event.echo:
        if event.keycode == KEY_ESCAPE:
            cancel_source_picker()
            get_viewport().set_input_as_handled()
        elif event.keycode in [KEY_ENTER,KEY_KP_ENTER] and not open_picker.is_mode_popup_open():
            confirm_source_picker()
            get_viewport().set_input_as_handled()
    return true

func retains_modal_navigation(code: Key) -> bool:
    return pause_sheet.visible and code in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]
