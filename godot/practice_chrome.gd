extends VBoxContainer
# Owns practice widget construction, popup presentation and responsive layout.
# Interactions leave through signals; no screen state or host-private access.
const UI := preload("res://ui_factory.gd")
const CaptionLayout := preload("res://practice_caption_layout.gd")
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const GameInputIndicator := preload("res://game_input_indicator.gd")
const GameStreak := preload("res://game_streak.gd")
const GameTransportButton := preload("res://game_transport_button.gd")
const PerformanceReviewStrip := preload("res://performance_review_strip.gd")
const ScoreStage := preload("res://practice_score_stage.gd")
const ObjectiveGlyph := preload("res://practice_objective_glyph.gd")
signal navigation_requested(destination: String)
signal command_requested(command: Dictionary)
signal play_requested
signal retry_requested
signal listen_requested
signal metronome_toggled(enabled: bool)
signal score_retry_requested
var stage: ScoreStage
var practice_layout_box: VBoxContainer
var practice_header: HBoxContainer
var practice_navigation: HBoxContainer
var details_popup: PopupPanel
var details_scroll: ScrollContainer
var details_caption: Label
var title_label: Label
var speed_label: Button
var tempo_popup: PopupPanel
var tempo_name_label: Label
var tempo_value_label: Label
var practice_details_button: Button
var details_panel: VBoxContainer
var game_input_indicator: Control
var lesson_info_label: Label
var progress_label: Label
var tempo_down_button: Button
var tempo_up_button: Button
var game_streak: Control
var practice_skip_button: Button
var practice_previous_button: Button
var feedback_label: Label
var performance_review: PerformanceReviewStrip
var performance_metrics: Control
var objective_panel: PanelContainer
var practice_controls: HFlowContainer
var practice_retry_button: Button
var start_button: Button
var listen_button: Button
# Practice flow (docs/practice-flow.md): one small status line under the title.
var flow_status_label: Label
# On-screen metronome switch (default on), the same "metronome" preference.
var metronome_switch: CheckButton
var practice_music_button: Button
var practice_settings_button: Button
var open_picker: Control
var pause_sheet: Control
var review_sheet: AcceptDialog
var resume_banner: PanelContainer
var resume_banner_message: Label
var resume_review_button: Button
var resume_continue_button: Button
var resume_measure_button: Button
var spoken_countin_toggle: CheckButton
var spoken_countin_status: Label
var spoken_countin_test_button: Button
signal previous_requested
signal skip_requested
signal dismiss_resume_requested
signal review_previous_requested
signal resume_measure_requested
signal confirm_source_requested
signal cancel_source_requested
var ui_scale := 1.0

func build() -> void:
    var layout: VBoxContainer = self
    layout.name = "PracticeChrome"
    layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    layout.size_flags_vertical = Control.SIZE_EXPAND_FILL
    layout.theme = Design.create()
    var practice_layout: VBoxContainer = layout
    practice_layout_box = practice_layout
    practice_header = HBoxContainer.new()
    practice_header.add_theme_constant_override("separation",14)
    practice_layout.add_child(practice_header)
    practice_music_button = _button("Back",func(): navigation_requested.emit("library"),false,"navigation")
    practice_music_button.tooltip_text = "Back to music · Escape"
    practice_music_button.call("set_icon_only",true)
    practice_header.add_child(practice_music_button)
    var heading := UI.stack(0)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    heading.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    heading.custom_minimum_size.x = 0.0
    heading.clip_contents = true
    practice_header.add_child(heading)
    title_label = UI.title("Choose your music",30)
    title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(title_label)
    flow_status_label = UI.label("", 14, MUTED)
    flow_status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    flow_status_label.clip_text = true
    flow_status_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    flow_status_label.visible = false
    heading.add_child(flow_status_label)
    var context := HBoxContainer.new()
    context.size_flags_horizontal = Control.SIZE_SHRINK_END
    context.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_header.add_child(context)
    # Only BPM and Settings belong in the header. Play/Pause lives in the
    # single large transport control beneath the music.
    practice_navigation = HBoxContainer.new()
    practice_navigation.alignment = BoxContainer.ALIGNMENT_END
    practice_navigation.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_navigation.add_theme_constant_override("separation",8)
    context.add_child(practice_navigation)
    speed_label = _button("-- BPM ▾",toggle_tempo_popup,false,"practice_tempo")
    speed_label.custom_minimum_size = Vector2(182,40)
    speed_label.tooltip_text = "Adjust tempo"
    speed_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_navigation.add_child(speed_label)
    practice_settings_button = _button("Settings",
        func(): navigation_requested.emit("settings"),false,"settings")
    practice_settings_button.tooltip_text = "Settings"
    practice_settings_button.call("set_icon_only",true)
    practice_settings_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_navigation.add_child(practice_settings_button)
    practice_details_button = _button("More",_toggle_details,false,"utility")
    practice_details_button.tooltip_text = "More lesson options and performance"
    practice_details_button.call("set_icon_only",true)
    tempo_popup = PopupPanel.new()
    tempo_popup.name = "TempoAdjustment"
    tempo_popup.add_theme_stylebox_override("panel",Design.modal_surface())
    layout.add_child(tempo_popup)
    var tempo_margin := MarginContainer.new()
    for side in ["left","right","top","bottom"]:
        tempo_margin.add_theme_constant_override("margin_"+side,7)
    tempo_popup.add_child(tempo_margin)
    var tempo_body := VBoxContainer.new()
    tempo_body.add_theme_constant_override("separation",5)
    tempo_margin.add_child(tempo_body)
    tempo_name_label = UI.label("Tempo",15,INK,true)
    tempo_body.add_child(tempo_name_label)
    tempo_value_label = UI.label("-- BPM · steps of 5 BPM",12,MUTED)
    tempo_value_label.visible = false
    tempo_body.add_child(tempo_value_label)
    var tempo_actions := HBoxContainer.new()
    tempo_actions.add_theme_constant_override("separation",6)
    tempo_body.add_child(tempo_actions)
    game_input_indicator = GameInputIndicator.new()
    lesson_info_label = UI.label("", 14, MUTED)
    lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    # Saved progress offers an unobtrusive, non-modal inline choice. It does
    # not intercept the transport, keyboard shortcuts or score input.
    resume_banner = PanelContainer.new()
    resume_banner.name = "ResumePracticeChoice"
    resume_banner.visible = false
    resume_banner.size_flags_horizontal = Control.SIZE_SHRINK_END
    resume_banner.add_theme_stylebox_override("panel",
        Design.bordered_surface(Design.CHARCOAL,6,.32))
    layout.add_child(resume_banner)
    var resume_row := HBoxContainer.new()
    resume_row.add_theme_constant_override("separation",8)
    resume_banner.add_child(resume_row)
    resume_banner_message = UI.label("",13,MUTED)
    resume_banner_message.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    resume_banner_message.clip_text = true
    resume_banner_message.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    resume_row.add_child(resume_banner_message)
    resume_review_button = _button("Review 2",func(): review_previous_requested.emit(),false,"secondary")
    resume_row.add_child(resume_review_button)
    resume_continue_button = _button("Continue",func(): dismiss_resume_requested.emit(),false,"utility")
    resume_row.add_child(resume_continue_button)
    resume_measure_button = _button("…",func(): resume_measure_requested.emit(),false,"utility")
    resume_measure_button.tooltip_text = "Choose a measure"
    resume_row.add_child(resume_measure_button)
    stage = ScoreStage.new()
    layout.add_child(stage)
    stage.navigation_requested.connect(func(destination: String): navigation_requested.emit(destination))
    stage.command_requested.connect(func(command: Dictionary): command_requested.emit(command))
    stage.score_retry_requested.connect(func(): score_retry_requested.emit())
    details_popup = PopupPanel.new()
    details_popup.name = "PracticeOptions"
    details_popup.add_theme_stylebox_override("panel",Design.modal_surface())
    layout.add_child(details_popup)
    details_popup.popup_hide.connect(_on_details_hidden)
    var details_margin := MarginContainer.new()
    for side in ["left","right","top","bottom"]:
        details_margin.add_theme_constant_override("margin_"+side,12)
    details_popup.add_child(details_margin)
    details_scroll = ScrollContainer.new()
    details_scroll.custom_minimum_size = Vector2(690,240)
    details_margin.add_child(details_scroll)
    details_panel = VBoxContainer.new()
    details_panel.name = "PracticeDetails"
    details_panel.visible = false
    details_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    details_panel.add_theme_constant_override("separation",10)
    details_scroll.add_child(details_panel)
    spoken_countin_toggle = CheckButton.new()
    spoken_countin_toggle.text = "Spoken count-in · Ichi, Ni, San, Shi"
    spoken_countin_toggle.tooltip_text = "Play the four bundled Japanese words on preparation beats"
    spoken_countin_toggle.set_pressed_no_signal(true)
    spoken_countin_toggle.toggled.connect(func(enabled: bool):
        stage.count_in.set_spoken_enabled(enabled)
        _present_countin_audio_status())
    details_panel.add_child(spoken_countin_toggle)
    spoken_countin_test_button = _button("Test voice",_test_countin_voice,false,"utility")
    spoken_countin_test_button.tooltip_text = "Play the bundled Ichi recording now"
    details_panel.add_child(spoken_countin_test_button)
    spoken_countin_status = UI.label("",12,MUTED)
    spoken_countin_status.visible = false
    details_panel.add_child(spoken_countin_status)
    # Reuse the existing RH/LH/Together stage indicators in More, not above
    # the score; state updates and unlock animations remain wired.
    stage.practice_stage_bar.reparent(details_panel,false)
    # Fingering diagnostics remain available in More without permanently
    # occupying a caption row or shrinking the engraving viewport.
    stage.fingering_status_label.reparent(details_panel,false)
    var details_header := HBoxContainer.new()
    details_header.add_theme_constant_override("separation",10)
    details_panel.add_child(details_header)
    details_header.add_child(game_input_indicator)
    details_caption = UI.label("",12,MUTED)
    details_caption.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    details_header.add_child(details_caption)
    var challenge_bar := HBoxContainer.new()
    challenge_bar.add_theme_constant_override("separation", 18)
    details_panel.add_child(challenge_bar)
    progress_label = UI.label("", 14, MUTED)
    progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    progress_label.clip_text = true
    progress_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    progress_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    challenge_bar.add_child(progress_label)
    # Keep navigation separate from both notation ink and the progress/tempo
    # row, whose combined minimum width would clip an 800x600 practice window.
    tempo_down_button = _button("−", func(): command_requested.emit({"action":"tempo_down"}),
        false, "secondary")
    tempo_down_button.tooltip_text = "Decrease tempo · Keeps the song target"
    tempo_actions.add_child(tempo_down_button)
    tempo_up_button = _button("+", func(): command_requested.emit({"action":"tempo_up"}),
        false, "secondary")
    tempo_up_button.tooltip_text = "Increase tempo · No mastery credit"
    tempo_up_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    tempo_actions.add_child(tempo_up_button)
    game_streak = GameStreak.new()
    challenge_bar.add_child(game_streak)
    var path_button := _button("Lesson path",func():
        details_popup.hide()
        navigation_requested.emit("lesson"),false,"navigation")
    path_button.tooltip_text = "Browse the lesson path"
    challenge_bar.add_child(path_button)
    # Direct backward navigation does not award mastery or traverse the
    # previous passage index: it selects the exact previous lesson step.
    practice_previous_button = _button("Previous lesson", func(): previous_requested.emit(),
        false, "navigation")
    practice_previous_button.tooltip_text = "Return to the previous lesson step without changing mastery"
    practice_previous_button.call("set_icon_only",true)
    practice_previous_button.disabled = true
    practice_previous_button.visible = false
    practice_previous_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(practice_previous_button)
    # Navigation stays outside the three fixed transport controls.
    practice_skip_button = _button("Next lesson", func(): skip_requested.emit(),
        false, "navigation")
    practice_skip_button.tooltip_text = "Go to the next lesson without earning mastery"
    practice_skip_button.call("set_icon_only",true)
    practice_skip_button.disabled = true
    practice_skip_button.visible = false
    practice_skip_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(practice_skip_button)
    feedback_label = UI.label("Ready", 14, MUTED)
    feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    feedback_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    var detail_row := HBoxContainer.new()
    detail_row.add_theme_constant_override("separation",12)
    details_panel.add_child(detail_row)
    objective_panel = UI.card()
    objective_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    detail_row.add_child(objective_panel)
    var objective := UI.stack(4)
    UI.card_body(objective_panel,0).add_child(objective)
    var objective_heading := HBoxContainer.new()
    objective_heading.add_theme_constant_override("separation",10)
    objective.add_child(objective_heading)
    objective_heading.add_child(ObjectiveGlyph.new())
    var objective_title := UI.title("Current exercise",16)
    objective_title.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    objective_heading.add_child(objective_title)
    objective.add_child(_caption_slot(lesson_info_label, 1))
    objective.add_child(_caption_slot(feedback_label, 1))
    performance_metrics = preload("res://practice_metrics.gd").new()
    detail_row.add_child(performance_metrics)
    performance_review = PerformanceReviewStrip.new()
    performance_review.ui_scale = ui_scale
    performance_review.review_requested.connect(func(summary: Dictionary):
        if review_sheet != null:
            review_sheet.call("open_review", summary))
    details_panel.add_child(performance_review)
    # Flow containers wrap whole readable buttons instead of clipping labels
    # when the practice window is narrow or the user uses larger UI fonts.
    var controls := HFlowContainer.new()
    practice_controls = controls
    controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    controls.alignment = FlowContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("h_separation", 8)
    controls.add_theme_constant_override("v_separation", 8)
    practice_layout.add_child(controls)
    practice_retry_button = _transport_button("Retry", func(): retry_requested.emit(), "retry")
    practice_retry_button.tooltip_text = "Repeat the current passage · R"
    controls.add_child(practice_retry_button)
    start_button = _transport_button("Play", func():
        dismiss_resume_requested.emit()
        play_requested.emit(), "play", true)
    controls.add_child(start_button)
    listen_button = _transport_button("Listen", func(): listen_requested.emit(), "listen")
    listen_button.tooltip_text = "Hear this passage, or return to practice · L"
    controls.add_child(listen_button)
    controls.add_child(practice_details_button)
    metronome_switch = CheckButton.new()
    metronome_switch.text = "Metronome"
    metronome_switch.button_pressed = true
    metronome_switch.focus_mode = Control.FOCUS_NONE
    metronome_switch.tooltip_text = "Metronome clicks while you play in tempo"
    metronome_switch.add_theme_font_size_override("font_size", 15)
    metronome_switch.toggled.connect(func(enabled: bool): metronome_toggled.emit(enabled))
    controls.add_child(metronome_switch)
    var modal_layer := CanvasLayer.new()
    modal_layer.layer = 1
    layout.add_child(modal_layer)
    # The saved-progress strip is anchored under the header without taking
    # height away from the moving notation. Dismissing it on Play must not
    # resize the score or invalidate retained engraving.
    resume_banner.reparent(modal_layer,false)
    resume_banner.z_index = 3
    open_picker = preload("res://source_measure_picker.gd").new()
    open_picker.confirmed.connect(func(_bar: int, _mode: String): confirm_source_requested.emit())
    open_picker.cancel_requested.connect(func(): cancel_source_requested.emit())
    modal_layer.add_child(open_picker)
    pause_sheet = preload("res://pause_sheet.gd").new()
    pause_sheet.z_index = 30
    modal_layer.add_child(pause_sheet)
    pause_sheet.chosen.connect(func(command: Dictionary):
        if command.get("action") == "exit":
            command_requested.emit({"action":"stop"})
            navigation_requested.emit("library")
        else: command_requested.emit(command))
    # The resume choice above is inline, never a blocking Window.
    review_sheet = preload("res://review_sheet.gd").new()
    modal_layer.add_child(review_sheet)
    review_sheet.retry_requested.connect(func(first_bar: int, last_bar: int):
        command_requested.emit({"action":"review_retry","first_bar":first_bar,"last_bar":last_bar}))

func _toggle_details() -> void:
    if details_popup.visible:
        details_popup.hide()
        return
    details_panel.visible = true
    practice_details_button.call("set_selected",true)
    practice_details_button.tooltip_text = "Close lesson options"
    var popup_width := mini(740,maxi(320,roundi(size.x)-32))
    var popup_height := mini(330,maxi(210,roundi(size.y*.52)))
    var anchor := Vector2i(practice_details_button.get_screen_position())
    var viewport_width := roundi(get_viewport_rect().size.x)
    anchor.x = clampi(anchor.x+roundi(practice_details_button.size.x)-popup_width,
        8,maxi(8,viewport_width-popup_width-8))
    anchor.y = maxi(8,anchor.y-popup_height-12)
    details_popup.popup(Rect2i(anchor,Vector2i(popup_width,popup_height)))

func _on_details_hidden() -> void:
    details_panel.visible = false
    practice_details_button.call("set_selected",false)
    practice_details_button.tooltip_text = "More lesson options and performance"

func toggle_tempo_popup() -> void:
    if tempo_popup.visible:
        tempo_popup.hide()
        return
    if speed_label.disabled:
        return
    var origin := Vector2i(speed_label.get_screen_position())
    origin.y += roundi(speed_label.size.y) + 5
    var width := 190
    origin.x = clampi(origin.x,8,maxi(8,roundi(get_viewport_rect().size.x)-width-8))
    tempo_popup.popup(Rect2i(origin,Vector2i(width,98)))

func bind_countin_voice_player(service: Node) -> void:
    stage.count_in.attach_voice_service(service)
    spoken_countin_toggle.set_pressed_no_signal(
        bool(service.get("spoken_enabled")))
    _present_countin_audio_status()

func _present_countin_audio_status() -> void:
    if spoken_countin_status == null:
        return
    var status: Dictionary = stage.count_in.voice_status()
    var unavailable: bool = not bool(status.get("available",false))
    var muted: bool = bool(status.get("master_muted",false))
    spoken_countin_status.visible = unavailable or muted
    spoken_countin_status.text = (
        "Spoken count-in files unavailable · metronome clicks used"
        if unavailable else "Master audio bus is muted · unmute to hear speech"
        if muted else "")

func _test_countin_voice() -> void:
    var status: Dictionary = stage.count_in.voice_status()
    if not bool(status.get("enabled",false)):
        spoken_countin_status.text = "Enable spoken count-in before testing"
    elif not bool(status.get("available",false)):
        spoken_countin_status.text = "Spoken count-in files unavailable"
    elif bool(status.get("master_muted",false)):
        spoken_countin_status.text = "Master audio bus is muted"
    elif stage.count_in.speak_beat(1):
        spoken_countin_status.text = "Playing Ichi on the Master audio bus"
    else:
        spoken_countin_status.text = "Audio playback failed · check terminal"
    spoken_countin_status.visible = true

func position_resume_banner() -> void:
    if resume_banner == null or practice_header == null:
        return
    var header: Rect2 = practice_header.get_global_rect()
    var viewport_width: float = get_viewport_rect().size.x
    # Do not insert another full-width toolbar above the score.
    var width: float = minf(430.0,maxf(230.0,viewport_width-16.0))
    var right: float = minf(header.end.x,viewport_width-8.0)
    resume_banner.position = Vector2(maxf(8.0,right-width),header.end.y+5.0)
    resume_banner.size = Vector2(width,40.0)

func apply_viewport(view_size: Vector2, scale: float) -> void:
    ui_scale = scale
    _resize_fonts(self)
    var width: float = view_size.x
    var compact: bool = view_size.y < 750.0
    var margin: int = 26 if width >= 1100.0 else 14
    stage.apply_viewport(view_size,scale,compact)
    position_resume_banner()
    open_picker.resize_panel(view_size)
    details_scroll.custom_minimum_size.x = minf(690.0,maxf(290.0,width-68.0))
    # The reserved score header keeps navigation outside the notation region.
    var compact_steps: bool = width < 1250.0
    progress_label.visible = true
    for bpm_button in [tempo_down_button, tempo_up_button]:
        bpm_button.custom_minimum_size = Vector2(58.0 if compact_steps else 66.0,34.0)
        bpm_button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    practice_header.add_theme_constant_override("separation",8 if width < 950.0 else 16)
    practice_navigation.add_theme_constant_override("separation", 7 if width >= 1000.0 else 4)
    for child in practice_navigation.get_children():
        if child is Button:
            var button := child as Button
            button.add_theme_font_size_override("font_size",_ui_font(14))
            if bool(button.get("icon_only")):
                button.custom_minimum_size = Vector2(40,40)
                button.clip_text = true
            else:
                button.custom_minimum_size = Vector2(
                    192 if button == speed_label and width >= 1050.0
                    else 174 if button == speed_label else 120,40)
    practice_music_button.custom_minimum_size = Vector2(40,40)
    if practice_controls != null:
        practice_layout_box.add_theme_constant_override("separation", 4 if compact else 6)
        # The expanding score panel gets all remaining vertical space.
        # A window-relative minimum ignored the keyboard/status heights and
        # pushed the transport below the screen when those became visible.
        for child in practice_controls.get_children():
            if child is Button:
                var button := child as Button
                var central: bool = button == start_button
                button.add_theme_font_size_override("font_size",_ui_font(18 if central else 15))
                if central:
                    button.custom_minimum_size = Vector2(
                        minf(225.0,maxf(170.0,width*.16)),58.0 if not compact else 48.0)
                elif button == practice_details_button:
                    button.custom_minimum_size = Vector2(48.0,46.0 if not compact else 42.0)
                else:
                    button.custom_minimum_size = Vector2(56.0,46.0 if not compact else 42.0)
                button.clip_text = not central
        title_label.add_theme_font_size_override("font_size",_ui_font(
            20 if width < 1024.0 else 28 if width >= 1400.0 else 24))
        speed_label.add_theme_font_size_override("font_size", _ui_font(14))
        progress_label.add_theme_font_size_override("font_size", _ui_font(15))
        game_streak.custom_minimum_size = Vector2(130 if width < 950 else 155, 30)
        game_input_indicator.custom_minimum_size.y = 22
        feedback_label.add_theme_font_size_override("font_size", _ui_font(14))
        lesson_info_label.add_theme_font_size_override("font_size", _ui_font(14))
        performance_metrics.custom_minimum_size.x = 270 if width < 1000 else 315
        var instruction_lines := 2
        lesson_info_label.set_meta("caption_lines", instruction_lines)
        lesson_info_label.max_lines_visible = instruction_lines
        lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if instruction_lines == 2 else TextServer.AUTOWRAP_OFF
        _resize_caption_slots()

func _caption_slot(caption: Label, lines: int) -> Control:
    return CaptionLayout.create(caption, lines, caption == feedback_label)

func _resize_caption_slots() -> void:
    CaptionLayout.resize([feedback_label, lesson_info_label])

func style_transport(button: Button, central := false) -> void:
    # Buttons on the piano stage are instrument controls rather than
    # generic form submissions. Keep a fixed tactile vocabulary.
    button.add_theme_font_size_override("font_size", _ui_font(17 if central else 15))
    var normal := StyleBoxFlat.new()
    var kind: String = str(button.get("action_kind"))
    var role: String = "play" if central else kind
    var accent: Color = Design.role_accent(role)
    normal.bg_color = Color("#62F0BE") if central else Design.role_fill(role)
    button.set_meta("ui_button_role",
        "transport_primary" if central else "transport_retry" if kind == "retry" else "transport_listen")
    normal.set_corner_radius_all(7)
    normal.set_content_margin_all(12)
    normal.set_border_width_all(1)
    normal.border_color = Color(accent, .7 if central else .22)
    # Primary bloom is now GPU-drawn behind GameTransportButton. A
    # StyleBox shadow here produced a solid rectangular halo.
    normal.shadow_color = Color.TRANSPARENT
    normal.shadow_size = 0
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
    style_transport(button, central)
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

