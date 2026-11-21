extends VBoxContainer
# Practice interaction and snapshot presentation. Chrome owns widget/layout
# construction; this owner keeps backend snapshots and command/input policy.
const Chrome := preload("res://practice_chrome.gd")
const Design := preload("res://practice_theme.gd")
const TempoVocabulary := preload("res://tempo_vocabulary.gd")
const ChallengeFlow := preload("res://challenge_flow.gd")
const ScoreStage := preload("res://practice_score_stage.gd")
const PerformanceReviewStrip := preload("res://performance_review_strip.gd")
const INK := Design.STONE
var _chrome := Chrome.new()
signal navigation_requested(destination: String)
signal command_requested(command: Dictionary)
signal midi_start_suppression_requested(input_count: int)
signal play_requested
signal retry_requested
signal listen_requested
signal metronome_toggled(enabled: bool)
signal score_retry_requested
var stage: ScoreStage:
    get: return _chrome.stage
var practice_layout_box: VBoxContainer:
    get: return _chrome.practice_layout_box
var practice_header: HBoxContainer:
    get: return _chrome.practice_header
var practice_navigation: HBoxContainer:
    get: return _chrome.practice_navigation
var details_popup: PopupPanel:
    get: return _chrome.details_popup
var details_scroll: ScrollContainer:
    get: return _chrome.details_scroll
var details_caption: Label:
    get: return _chrome.details_caption
var title_label: Label:
    get: return _chrome.title_label
var speed_label: Button:
    get: return _chrome.speed_label
var tempo_popup: PopupPanel:
    get: return _chrome.tempo_popup
var tempo_name_label: Label:
    get: return _chrome.tempo_name_label
var tempo_value_label: Label:
    get: return _chrome.tempo_value_label
var practice_details_button: Button:
    get: return _chrome.practice_details_button
var details_panel: VBoxContainer:
    get: return _chrome.details_panel
var game_input_indicator: Control:
    get: return _chrome.game_input_indicator
var lesson_info_label: Label:
    get: return _chrome.lesson_info_label
var progress_label: Label:
    get: return _chrome.progress_label
var tempo_down_button: Button:
    get: return _chrome.tempo_down_button
var tempo_up_button: Button:
    get: return _chrome.tempo_up_button
var game_streak: Control:
    get: return _chrome.game_streak
var practice_skip_button: Button:
    get: return _chrome.practice_skip_button
var practice_previous_button: Button:
    get: return _chrome.practice_previous_button
var feedback_label: Label:
    get: return _chrome.feedback_label
var performance_review: PerformanceReviewStrip:
    get: return _chrome.performance_review
var performance_metrics: Control:
    get: return _chrome.performance_metrics
var objective_panel: PanelContainer:
    get: return _chrome.objective_panel
var practice_controls: HFlowContainer:
    get: return _chrome.practice_controls
var practice_retry_button: Button:
    get: return _chrome.practice_retry_button
var start_button: Button:
    get: return _chrome.start_button
var listen_button: Button:
    get: return _chrome.listen_button
var flow_status_label: Label:
    get: return _chrome.flow_status_label
var metronome_switch: CheckButton:
    get: return _chrome.metronome_switch
var practice_music_button: Button:
    get: return _chrome.practice_music_button
var practice_settings_button: Button:
    get: return _chrome.practice_settings_button
var open_picker: Control:
    get: return _chrome.open_picker
var pause_sheet: Control:
    get: return _chrome.pause_sheet
var review_sheet: AcceptDialog:
    get: return _chrome.review_sheet
var resume_banner: PanelContainer:
    get: return _chrome.resume_banner
var resume_banner_message: Label:
    get: return _chrome.resume_banner_message
var resume_review_button: Button:
    get: return _chrome.resume_review_button
var resume_continue_button: Button:
    get: return _chrome.resume_continue_button
var resume_measure_button: Button:
    get: return _chrome.resume_measure_button
var spoken_countin_toggle: CheckButton:
    get: return _chrome.spoken_countin_toggle
var spoken_countin_status: Label:
    get: return _chrome.spoken_countin_status
var spoken_countin_test_button: Button:
    get: return _chrome.spoken_countin_test_button
var ui_scale: float:
    get: return _chrome.ui_scale
var _last_import_notice := ""
var _resume_open_state: Dictionary = {}
var advanced_pause_open := false
var _state: Dictionary = {}
var _previous_state: Dictionary = {}
var _score_ready := false
var _score_status: Dictionary = {"ready":false,"visible":true,
    "text":"Choose a piece to begin","error":"","retry_visible":false,
    "browse_visible":true}
var _busy := false
var _audio_error := false
var _audio_banner_active := false
var _active := true
var _hand_unlock_message := ""
var _hand_unlock_until_ms := 0

func _ready() -> void:
    name = "PracticeScreen"
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    add_child(_chrome)
    _chrome.build()
    _chrome.navigation_requested.connect(func(destination: String): navigation_requested.emit(destination))
    _chrome.command_requested.connect(func(command: Dictionary): command_requested.emit(command))
    _chrome.play_requested.connect(func(): play_requested.emit())
    _chrome.retry_requested.connect(func(): retry_requested.emit())
    _chrome.listen_requested.connect(func(): listen_requested.emit())
    _chrome.metronome_toggled.connect(func(enabled: bool): metronome_toggled.emit(enabled))
    _chrome.score_retry_requested.connect(func(): score_retry_requested.emit())
    _chrome.previous_requested.connect(_previous_lesson)
    _chrome.skip_requested.connect(_skip_lesson)
    _chrome.dismiss_resume_requested.connect(_dismiss_resume_hint)
    _chrome.review_previous_requested.connect(_review_previous_steps)
    _chrome.resume_measure_requested.connect(_resume_choose_measure)
    _chrome.confirm_source_requested.connect(confirm_source_picker)
    _chrome.cancel_source_requested.connect(cancel_source_picker)

func apply_viewport(view_size: Vector2, scale: float) -> void:
    _chrome.apply_viewport(view_size, scale)

func bind_countin_voice_player(service: Node) -> void:
    _chrome.bind_countin_voice_player(service)

func _toggle_tempo_popup() -> void:
    _chrome.toggle_tempo_popup()

func present_metronome(enabled: bool) -> void:
    if metronome_switch != null and metronome_switch.button_pressed != enabled:
        metronome_switch.set_pressed_no_signal(enabled)

func _present_flow(parsed: Dictionary) -> bool:
    # Practice flow: everything advances by itself; only Pause/Resume and
    # "Listen again" stay (docs/practice-flow.md, On screen > Controls).
    var flow: Dictionary = parsed.get("flow", {}) if parsed.get("flow") is Dictionary else {}
    var active := not flow.is_empty()
    flow_status_label.visible = active
    if active:
        var status := str(flow.get("status", ""))
        if flow_status_label.text != status:
            flow_status_label.text = status
    practice_retry_button.visible = not active
    speed_label.visible = not active
    practice_details_button.visible = not active
    if active:
        practice_previous_button.visible = false
        practice_skip_button.visible = false
        if listen_button.text != "Listen again":
            listen_button.text = "Listen again"
            listen_button.call("configure", "listen")
            _chrome.style_transport(listen_button)
        listen_button.tooltip_text = "Hear this passage again at the target tempo · L"
        listen_button.disabled = str(parsed.get("mode", "")) == "listen"
    return active

func present(parsed: Dictionary, ready: bool, busy := false, audio_error := false) -> void:
    _previous_state = _state
    _state = parsed.duplicate(true)
    if is_resume_prompt_open() and (bool(parsed.get("running",false)) or
            str(parsed.get("mode","")) == "listen" or
            int(parsed.get("lesson_step",-1)) != int(
                _resume_open_state.get("lesson_step",-1))):
        _dismiss_resume_hint()
    performance_metrics.present(parsed)
    _score_ready = ready
    _audio_error = audio_error
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
        # A source picker / load failure must not blank the visual timeline.
        # NativeView draws an ungraded empty staff while music is absent.
        stage.renderer.visible = true
        game_streak.present({})
        feedback_label.text = str(parsed.get("feedback","Open a score"))
        present_score(_score_status)
        return
    title_label.text = str(parsed.get("title", "Piano Teacher")).replace("_", " ")
    var kind := str(parsed.get("kind", "learn")).capitalize()
    var range_first := int(parsed.get("first_bar",0))
    var range_last := int(parsed.get("last_bar",0))
    var passage_text: String = ("%s · Measure %d" % [kind,range_first]
        if range_first == range_last
        else "%s · Measures %d–%d" % [kind,range_first,range_last])
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
        tempo_down_button.text = "−"
        tempo_down_button.tooltip_text = "Decrease by %d BPM · Keeps the song target" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_down_button.disabled = (_busy or not bool(parsed.get("can_decrease_tempo", false))
            or str(parsed.get("phase", "")) in ["count_in", "playing", "loading", "admitting"])
    if tempo_up_button != null:
        tempo_up_button.text = "+"
        tempo_up_button.tooltip_text = "Increase by %d BPM · No mastery credit" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_up_button.disabled = (_busy or not bool(parsed.get("can_increase_tempo",false))
            or str(parsed.get("phase","")) in ["count_in","playing","loading","admitting"])
    var selected_bpm: float = float(parsed.get("bpm", 0))
    var effective_bpm: float = float(parsed.get("effective_bpm", selected_bpm))
    speed_label.text = TempoVocabulary.display(selected_bpm) + " ▾"
    tempo_name_label.text = TempoVocabulary.display(selected_bpm)
    tempo_value_label.text = "%d BPM · adjust by %d BPM" % [
        roundi(selected_bpm),int(parsed.get("manual_tempo_step_bpm",5))]
    speed_label.disabled = not bool(parsed.get("loaded",false))
    var recovery_notice: Variant = parsed.get("recovery_notice")
    speed_label.tooltip_text = ("Selected tempo %.1f BPM; effective first-segment tempo %.1f BPM; target %d BPM" %
        [selected_bpm, effective_bpm, int(parsed.get("target_bpm", 0))])
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
    if not import_warnings.is_empty():
        var import_notice := "MIDI imported with repairs: " + "  ".join(import_warnings)
        if import_notice != _last_import_notice:
            _last_import_notice = import_notice
            push_warning(import_notice)
    var learning: bool = str(parsed.get("mode", "practice")) == "learn"
    var teaching: Dictionary = parsed.get("teaching", {}) if parsed.get("teaching") is Dictionary else {}
    var learner: Dictionary = parsed.get("learner", {}) if parsed.get("learner") is Dictionary else {}
    practice_previous_button.visible = bool(parsed.get("loaded", false))
    practice_previous_button.disabled = _busy or int(parsed.get("lesson_step",1)) <= 1
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
    var phase: String = str(parsed.get("phase", "ready"))
    if not bool(parsed.get("paused",false)): advanced_pause_open = false
    _present_pause()
    start_button.visible = true
    listen_button.disabled = not bool(parsed.get("loaded", false))
    listen_button.text = "Practice" if str(parsed.get("mode", "")) == "listen" else "Listen"
    var listen_kind := "practice" if listen_button.text == "Practice" else "listen"
    if str(listen_button.get("action_kind")) != listen_kind:
        listen_button.call("configure", listen_kind)
        _chrome.style_transport(listen_button)
    practice_retry_button.disabled = (not bool(parsed.get("loaded", false))
        or not _score_ready or phase in ["admitting","loading"])
    var flow_active := _present_flow(parsed)
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
    elif phase == "admitting":
        feedback_text = "Preparing the next passage · checking score placement"
    elif phase == "recovering":
        feedback_text = str(parsed.get("feedback", "Short break before retry"))
    elif phase == "count_in":
        feedback_text = "GET READY · follow the teal playhead"
    elif phase == "playing":
        var midi_count: int = int(parsed.get("midi_notes", 0))
        if bool(parsed.get("preview_only", false)):
            feedback_text = "PREVIEW · connect your piano to earn accepted passes"
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
        elif phase == "admitting":
            feedback_text = "Preparing Listen · aligning score and audio"
        if bool(demo_info.get("audio_available", false)) and not bool(demo_info.get("sampled", false)):
            instruction_text = "Basic piano sound · install the Salamander samples for acoustic Listen (see README)."
        elif bool(demo_info.get("sampled", false)):
            instruction_text = "Acoustic grand piano · " + instrument
        if _audio_error:
            feedback_text = "Listen audio could not load. Choose Listen to try again."
    # Amber can mean onset drift OR an overly short/long key hold.
    if phase == "feedback" and not learning:
        var has_amber := false
        for mark in parsed.get("feedback_marks", []):
            if str(mark.get("status", "")) in ["early", "late", "short", "long"]:
                has_amber = true
                break
        if has_amber:
            feedback_text += " · Yellow: early/late press or short/long hold"
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
        progress_text = "Accepted passes %d of %d at %d BPM" % [
            int(parsed.get("streak", 0)), needed_runs, int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
        if bool(parsed.get("warmup", false)):
            var name: String = "Both hands" if str(parsed.get("hand", "")) == "both" else str(parsed.get("hand", "")).capitalize() + " hand"
            progress_text = "%s · %d of %d accepted passes · Next hand unlocks when mastered" % [
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
    if not bool(parsed.get("warmup", false)):
        # Show musical stage content, never the internal generator name.
        var transformation: String = str(parsed.get("stage_label", ""))
        if not transformation.is_empty():
            passage_text += " · " + transformation
    title_label.tooltip_text = passage_text
    details_caption.text = passage_text
    progress_label.text = progress_text
    lesson_info_label.text = instruction_text
    # The transport action is Play. Do not show the engine's obsolete
    # "Start" caption when presenting that same action.
    feedback_label.text = ("Press Play to practice"
        if phase == "ready" and feedback_text == "Press Start to practice"
        else feedback_text)
    if progress_label.get_theme_color("font_color") != progress_tone:
        progress_label.add_theme_color_override("font_color", progress_tone)
    if lesson_info_label.get_theme_color("font_color") != instruction_tone:
        lesson_info_label.add_theme_color_override("font_color", instruction_tone)
    # Secondary information is available on demand. Normal playing does not
    # shrink the music or repeat state already conveyed by score and controls.
    details_panel.visible = details_popup.visible
    if _audio_error:
        self.stage.practice_playback_banner.text = feedback_text
        self.stage.practice_playback_banner.visible = true
        _audio_banner_active = true
    elif _audio_banner_active:
        self.stage.practice_playback_banner.visible = false
        _audio_banner_active = false
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
    var primary_control: Dictionary = _control("primary")
    var listen_control: Dictionary = _control("listen")
    start_button.text = str(primary_control.get("label","Play"))
    start_button.tooltip_text = ("Pause or resume · Space" if flow_active
        else "Play, pause or resume · Space · Play any piano key when ready")
    start_button.disabled = _primary_blocked()
    start_button.call("configure", "pause" if str(primary_control.get("action","")) == "pause" else "play",
        active_transport and not bool(parsed.get("paused", false)))
    listen_button.disabled = not bool(listen_control.get("enabled",false))
    listen_button.call("configure", "practice" if str(listen_control.get("action","")) == "practice" else "listen",
        str(parsed.get("mode", "")) == "listen")

func present_busy(busy: bool) -> void:
    _busy = busy
    var blocked: bool = busy or not bool(_state.get("loaded",false)) or str(_state.get("phase","")) in ["count_in","playing","loading","admitting"]
    tempo_down_button.disabled = blocked or not bool(_state.get("can_decrease_tempo",false))
    tempo_up_button.disabled = blocked or not bool(_state.get("can_increase_tempo",false))
    practice_skip_button.disabled = busy or not bool(_state.get("skip_available",false))
    practice_previous_button.disabled = busy or int(_state.get("lesson_step",1)) <= 1

func present_score(status: Dictionary) -> void:
    _score_status = status.duplicate(true)
    _score_ready = bool(status.get("ready",false))
    stage.present_score_status(status)
    start_button.disabled = _primary_blocked()
    practice_retry_button.disabled = not bool(_state.get("loaded",false)) or not _score_ready

func present_message(message: String, reveal := false) -> void:
    feedback_label.text = message
    feedback_label.tooltip_text = message
    if reveal:
        feedback_label.visible = true
        # Keep exceptional command/status errors legible without restoring
        # permanent coaching panels around the notation.
        stage.practice_playback_banner.text = message
        stage.practice_playback_banner.visible = true

func begin_action(requested: String, pending := "") -> void:
    if not pending.is_empty():
        present_message("Please wait · finishing " + pending,true)
        return
    var verb: String = {"listen":"Preparing piano audio","practice":"Returning to practice",
        "start":"Starting count-in","pause":"Pausing","resume":"Resuming","restart":"Restarting the passage",
        "skip_stage":"Loading next lesson","select_step":"Opening lesson","stop":"Stopping"}.get(requested,"Applying " + requested.replace("_"," "))
    present_message(verb + "…",true)
    stage.practice_playback_banner.text = verb + "…"
    stage.practice_playback_banner.visible = true

func finish_action() -> void:
    stage.practice_playback_banner.visible = false

func _control(name: String) -> Dictionary:
    var controls: Dictionary = _state.get("controls",{})
    var choice: Variant = controls.get(name,{})
    return choice if choice is Dictionary else {}

func _primary_blocked() -> bool:
    var primary: Dictionary = _control("primary")
    return (not bool(primary.get("enabled",false)) or
        (bool(primary.get("requires_score",false)) and not _score_ready))

func _active_transport(state: Dictionary) -> bool:
    var controls: Dictionary = state.get("controls",{})
    return bool(controls.get("transport_active",false))

func set_active(active: bool) -> void:
    _active = active
    if not active:
        if details_popup.visible: details_popup.hide()
        if tempo_popup.visible: tempo_popup.hide()
    _present_pause()

func _present_pause() -> void:
    pause_sheet.present(_state if _active and advanced_pause_open else {})

func open_advanced_pause() -> void:
    navigation_requested.emit("practice")
    advanced_pause_open = true
    if bool(_state.get("paused",false)): _present_pause()
    elif _active_transport(_state): command_requested.emit({"action":"pause"})
    else: advanced_pause_open = false

func _previous_lesson() -> void:
    var current: int = int(_state.get("lesson_step",1))
    if not _busy and bool(_state.get("loaded",false)) and current > 1:
        command_requested.emit({"action":"select_step","number":current - 1})

func _skip_lesson() -> void:
    if not _busy and bool(_state.get("skip_available",false)):
        command_requested.emit({"action":"skip_stage","reason":"Learner skipped to the next lesson from the practice screen"})

## Bind the persistent audio service once, after PracticeScreen _ready().
## The status stays in More; no new warning strip overlaps the moving score.

func is_source_picker_open() -> bool:
    return open_picker != null and open_picker.visible

func is_resume_prompt_open() -> bool:
    return resume_banner != null and resume_banner.visible

func _dismiss_resume_hint() -> void:
    if resume_banner != null:
        resume_banner.hide()
    _resume_open_state.clear()

func show_resume_prompt(state: Dictionary, allow_measure: bool) -> void:
    var step: int = int(state.get("lesson_step",1))
    if bool(state.get("warmup",false)) or step <= 1:
        if allow_measure:
            show_source_picker(state)
        return
    navigation_requested.emit("practice")
    midi_start_suppression_requested.emit(int(state.get("midi_input_count",0)))
    _resume_open_state = state.duplicate(true)
    resume_measure_button.visible = allow_measure
    resume_banner_message.text = "Continue at step %d?" % step
    resume_banner_message.tooltip_text = "Your earlier progress is preserved. Play to continue the saved step."
    _chrome.position_resume_banner()
    resume_banner.show()

func _review_previous_steps() -> void:
    if _resume_open_state.is_empty():
        return
    var step: int = int(_resume_open_state.get("lesson_step",1))
    _dismiss_resume_hint()
    command_requested.emit({"action":"select_step","number":maxi(1,step-2)})

func _resume_choose_measure() -> void:
    if _resume_open_state.is_empty():
        return
    var state := _resume_open_state.duplicate(true)
    _dismiss_resume_hint()
    show_source_picker(state)

func show_source_picker(state: Dictionary) -> void:
    navigation_requested.emit("practice")
    midi_start_suppression_requested.emit(int(state.get("midi_input_count",0)))
    _dismiss_resume_hint()
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
