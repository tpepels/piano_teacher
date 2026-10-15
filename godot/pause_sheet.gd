extends Control
const Design := preload("res://practice_theme.gd")

# Practice pauses must remain usable from a piano bench at 1024x768 and on
# smaller screens. The underlying musical engine remains frozen by Python.
signal chosen(command: Dictionary)

var resume_button: Button
var retry_button: Button
var listen_button: Button
var slower_button: Button
var faster_button: Button
var exit_button: Button
var hand_choice: OptionButton
var bar_choice: SpinBox
var seek_button: Button
var heading: Label
var detail_label: Label
var tempo_value: Label
var modal_panel: PanelContainer
var scroll: ScrollContainer
var current: Dictionary = {}


func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    mouse_filter = Control.MOUSE_FILTER_STOP
    var shade := ColorRect.new()
    shade.color = Color(0.015, 0.045, 0.035, 0.67)
    shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    shade.mouse_filter = Control.MOUSE_FILTER_STOP
    add_child(shade)

    var center := CenterContainer.new()
    center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(center)
    modal_panel = PanelContainer.new()
    var panel_style := Design.surface(Design.PANEL, 14)
    panel_style.set_border_width_all(2)
    panel_style.border_color = Color(Design.TEAL, 0.7)
    panel_style.set_content_margin_all(20)
    modal_panel.add_theme_stylebox_override("panel", panel_style)
    center.add_child(modal_panel)

    scroll = ScrollContainer.new()
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    modal_panel.add_child(scroll)
    var content := VBoxContainer.new()
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    content.add_theme_constant_override("separation", 12)
    scroll.add_child(content)

    heading = _label("Practice paused", 28, Design.STONE, true, content)
    detail_label = _label("Review your next action", 18, Design.SLATE, false, content)
    detail_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    _separator(content)

    resume_button = _button("Resume  ·  Space", {"action": "resume"}, content, true)
    resume_button.custom_minimum_size.y = 62
    var main_actions := HBoxContainer.new()
    main_actions.add_theme_constant_override("separation", 10)
    content.add_child(main_actions)
    retry_button = _button("Retry from start", {}, main_actions)
    retry_button.pressed.connect(func():
        chosen.emit({"action": "learn_retry" if current.get("mode") == "learn"
            else "listen" if current.get("mode") == "listen" else "restart"}))
    listen_button = _button("Listen", {"action": "listen"}, main_actions)

    _label("TEMPO", 16, Design.SLATE, true, content)
    var tempo_row := HBoxContainer.new()
    tempo_row.add_theme_constant_override("separation", 10)
    content.add_child(tempo_row)
    slower_button = _button("Slower -10%", {}, tempo_row)
    slower_button.pressed.connect(func():
        chosen.emit({"action":"tempo", "bpm":maxi(12, roundi(float(current.get("bpm",80)) * 0.9))}))
    tempo_value = _label("68 BPM", 20, Design.STONE, true, tempo_row)
    tempo_value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    tempo_value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    faster_button = _button("Faster +10%", {}, tempo_row)
    faster_button.pressed.connect(func():
        chosen.emit({"action":"tempo", "bpm":mini(300,
            maxi(int(current.get("bpm",80))+1, roundi(float(current.get("bpm",80)) * 1.1)))}))

    _label("HAND", 16, Design.SLATE, true, content)
    hand_choice = OptionButton.new()
    hand_choice.custom_minimum_size.y = 54
    hand_choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    hand_choice.add_theme_font_size_override("font_size", 20)
    hand_choice.item_selected.connect(func(index: int):
        chosen.emit({"action":"hand", "hand":hand_choice.get_item_metadata(index)}))
    content.add_child(hand_choice)

    _label("STARTING MEASURE", 16, Design.SLATE, true, content)
    var seek := HBoxContainer.new()
    seek.add_theme_constant_override("separation", 10)
    content.add_child(seek)
    bar_choice = SpinBox.new()
    bar_choice.prefix = "Measure "
    bar_choice.step = 1
    bar_choice.custom_minimum_size = Vector2(150, 54)
    bar_choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    bar_choice.add_theme_font_size_override("font_size", 20)
    seek.add_child(bar_choice)
    seek_button = _button("Practise from here", {}, seek)
    seek_button.pressed.connect(func():
        chosen.emit({"action":"seek", "bar":int(bar_choice.value)}))
    # Don't let arrow-navigation inside an editable field leave the modal.
    for editor in [bar_choice.get_line_edit(), hand_choice]:
        for direction in ["left", "right", "top", "bottom"]:
            editor.set("focus_neighbor_" + direction, editor.get_path())
    _separator(content)
    exit_button = _button("Exit to library", {"action": "exit"}, content)
    get_viewport().size_changed.connect(_fit_panel)
    _fit_panel()
    visible = false


func _fit_panel() -> void:
    if not is_instance_valid(modal_panel):
        return
    var viewport: Vector2 = get_viewport_rect().size
    modal_panel.custom_minimum_size.x = minf(580.0, maxf(285.0, viewport.x - 40.0))
    scroll.custom_minimum_size.y = minf(630.0, maxf(230.0, viewport.y - 74.0))


func _label(text: String, font_size: int, color: Color, bold: bool, parent: Node) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", color)
    if bold:
        var face := SystemFont.new()
        face.font_names = PackedStringArray(["Inter", "Noto Sans", "DejaVu Sans"])
        face.font_weight = 700
        label.add_theme_font_override("font", face)
    parent.add_child(label)
    return label


func _separator(parent: Node) -> void:
    var line := HSeparator.new()
    line.add_theme_constant_override("separation", 6)
    parent.add_child(line)


func _button(text: String, command: Dictionary, parent: Node, primary: bool = false) -> Button:
    var button := Button.new()
    button.text = text
    button.custom_minimum_size.y = 53
    button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    button.add_theme_font_size_override("font_size", 19)
    button.add_theme_color_override("font_color", Design.STONE)
    button.add_theme_color_override("font_hover_color", Color.WHITE)
    button.add_theme_color_override("font_disabled_color", Design.SLATE)
    var normal := Design.surface(Design.PINE if primary else Design.FOREST, 7)
    normal.set_border_width_all(1)
    normal.border_color = Design.TEAL if primary else Color(Design.SLATE, .3)
    button.add_theme_stylebox_override("normal", normal)
    var hover := Design.surface(Design.SAGE, 7)
    button.add_theme_stylebox_override("hover", hover)
    button.add_theme_stylebox_override("pressed", hover)
    var focus := Design.surface(Color.TRANSPARENT)
    focus.set_border_width_all(2)
    focus.border_color = Design.TEAL
    button.add_theme_stylebox_override("focus", focus)
    parent.add_child(button)
    if not command.is_empty():
        button.pressed.connect(func(): chosen.emit(command))
    return button


func present(state: Dictionary) -> void:
    var opening: bool = not visible and bool(state.get("paused", false))
    current = state
    visible = bool(state.get("paused", false))
    if not visible:
        return
    var hand: String = str(state.get("hand", "both"))
    var hand_text := "Both hands" if hand == "both" else hand.capitalize() + " hand"
    detail_label.text = "%s  ·  Measures %d-%d" % [
        hand_text, int(state.get("first_bar", 1)), int(state.get("last_bar", 1))]
    tempo_value.text = "%d BPM" % int(state.get("bpm", 80))
    if opening:
        hand_choice.clear()
        for available in state.get("hands", []):
            hand_choice.add_item("Both hands" if available == "both" else str(available).capitalize() + " hand")
            var index: int = hand_choice.item_count - 1
            hand_choice.set_item_metadata(index, available)
            if available == state.get("hand"):
                hand_choice.select(index)
    var seek_range: Dictionary = state.get("seek_range", {}) if state.get("seek_range") is Dictionary else {}
    bar_choice.min_value = int(seek_range.get("first_bar", state.get("first_bar", 1)))
    bar_choice.max_value = int(seek_range.get("last_bar", state.get("last_bar", 1)))
    if opening:
        bar_choice.value = bar_choice.min_value
        resume_button.grab_focus()
    seek_button.disabled = state.get("mode") == "listen" or not state.get("seek_available", false)
    bar_choice.editable = not seek_button.disabled


func _input(event: InputEvent) -> void:
    if not visible or not event is InputEventKey:
        return
    var owner: Control = get_viewport().gui_get_focus_owner()
    var tab: bool = event.keycode == KEY_TAB
    var direction: bool = event.keycode in [KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT] and not (owner is LineEdit or owner is OptionButton)
    if not tab and not direction:
        return
    if event.pressed and not event.echo:
        var choices: Array[Control] = [resume_button, retry_button, listen_button, slower_button, faster_button, hand_choice]
        if not seek_button.disabled:
            choices.append(bar_choice.get_line_edit())
            choices.append(seek_button)
        choices.append(exit_button)
        var reverse: bool = event.shift_pressed if tab else event.keycode in [KEY_UP, KEY_LEFT]
        var index: int = choices.find(owner)
        choices[posmod(index + (-1 if reverse else 1), choices.size())].grab_focus()
    get_viewport().set_input_as_handled()
