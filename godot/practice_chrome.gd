extends VBoxContainer
# Owns practice widget construction, popup presentation and responsive layout.
# Interactions leave through signals; no screen state or host-private access.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const GameTransportButton := preload("res://game_transport_button.gd")
const ScoreStage := preload("res://practice_score_stage.gd")
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
var title_label: Label
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
var resume_banner: PanelContainer
var resume_banner_message: Label
var resume_review_button: Button
var resume_continue_button: Button
var resume_measure_button: Button
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
    practice_settings_button = _button("Settings",
        func(): navigation_requested.emit("settings"),false,"settings")
    practice_settings_button.tooltip_text = "Settings"
    practice_settings_button.call("set_icon_only",true)
    practice_settings_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_navigation.add_child(practice_settings_button)
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
    # Retry is the R shortcut only; Practice Flow shows Pause/Resume and
    # Listen again (docs/practice-flow.md, On screen).
    practice_retry_button.visible = false
    controls.add_child(practice_retry_button)
    start_button = _transport_button("Play", func():
        dismiss_resume_requested.emit()
        play_requested.emit(), "play", true)
    controls.add_child(start_button)
    listen_button = _transport_button("Listen", func(): listen_requested.emit(), "listen")
    listen_button.tooltip_text = "Hear this passage, or return to practice · L"
    controls.add_child(listen_button)
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

func bind_countin_voice_player(service: Node) -> void:
    stage.count_in.attach_voice_service(service)

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
                button.custom_minimum_size = Vector2(120,40)
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
                else:
                    button.custom_minimum_size = Vector2(56.0,46.0 if not compact else 42.0)
                button.clip_text = not central
        title_label.add_theme_font_size_override("font_size",_ui_font(
            20 if width < 1024.0 else 28 if width >= 1400.0 else 24))

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

