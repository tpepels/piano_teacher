extends Control
const Design := preload("res://practice_theme.gd")
# A focused set of working choices while the engine is frozen.
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
var current: Dictionary = {}

func _ready() -> void:
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    mouse_filter = Control.MOUSE_FILTER_STOP
    var shade := ColorRect.new()
    shade.color = Color(0.02, 0.07, 0.055, 0.88)
    shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    shade.mouse_filter = Control.MOUSE_FILTER_STOP
    add_child(shade)
    var center := CenterContainer.new()
    center.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(center)
    var panel := PanelContainer.new()
    panel.custom_minimum_size = Vector2(350, 0)
    var style := StyleBoxFlat.new()
    style.bg_color = Color("2D3532")
    style.set_corner_radius_all(12)
    style.set_content_margin_all(18)
    panel.add_theme_stylebox_override("panel", style)
    center.add_child(panel)
    var column := VBoxContainer.new()
    column.add_theme_constant_override("separation", 10)
    panel.add_child(column)
    heading = Label.new()
    heading.text = "Paused · take your time"
    heading.add_theme_font_size_override("font_size", 20)
    column.add_child(heading)
    resume_button = _button("Resume · Space", {"action":"resume"}, column)
    var rows := GridContainer.new()
    rows.columns = 2
    rows.add_theme_constant_override("h_separation", 8)
    rows.add_theme_constant_override("v_separation", 8)
    column.add_child(rows)
    retry_button = _button("Retry", {}, rows)
    retry_button.pressed.connect(func(): chosen.emit({"action":"learn_retry" if current.get("mode") == "learn" else "listen" if current.get("mode") == "listen" else "restart"}))
    listen_button = _button("Listen", {"action":"listen"}, rows)
    slower_button = _button("Slower −10%", {}, rows)
    slower_button.pressed.connect(func(): chosen.emit({"action":"tempo", "bpm":maxi(12,roundi(float(current.get("bpm",80))*.9))}))
    faster_button = _button("Faster +10%", {}, rows)
    faster_button.pressed.connect(func(): chosen.emit({"action":"tempo", "bpm":mini(300,maxi(int(current.get("bpm",80))+1,roundi(float(current.get("bpm",80))*1.1)))}))
    hand_choice = OptionButton.new()
    hand_choice.item_selected.connect(func(index: int): chosen.emit({"action":"hand", "hand":hand_choice.get_item_metadata(index)}))
    column.add_child(hand_choice)
    var seek := HBoxContainer.new()
    column.add_child(seek)
    bar_choice = SpinBox.new()
    bar_choice.prefix = "Measure "
    bar_choice.step = 1
    bar_choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    seek.add_child(bar_choice)
    # Native editors can hand an arrow to GUI focus at the caret boundary.
    # Keep that focus inside this modal while retaining normal text editing.
    for editor in [bar_choice.get_line_edit(), hand_choice]:
        for direction in ["left", "right", "top", "bottom"]:
            editor.set("focus_neighbor_" + direction, editor.get_path())
    seek_button = _button("Practise from here", {}, seek)
    seek_button.pressed.connect(func(): chosen.emit({"action":"seek", "bar":int(bar_choice.value)}))
    exit_button = _button("Exit to library", {"action":"exit"}, column)
    visible = false

func _button(text: String, command: Dictionary, parent: Node) -> Button:
    var button := Button.new()
    button.text = text
    button.custom_minimum_size.y = 38
    button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    parent.add_child(button)
    button.add_theme_stylebox_override("normal", Design.surface(Design.PINE if text.begins_with("Resume") else Design.FOREST))
    button.add_theme_stylebox_override("hover", Design.surface(Design.PINE))
    button.add_theme_stylebox_override("pressed", Design.surface(Design.SAGE))
    var focus := Design.surface(Color.TRANSPARENT)
    focus.set_border_width_all(2)
    focus.border_color = Design.TEAL
    button.add_theme_stylebox_override("focus", focus)
    if not command.is_empty():
        button.pressed.connect(func(): chosen.emit(command))
    return button

func present(state: Dictionary) -> void:
    var opening: bool = not visible and bool(state.get("paused", false))
    current = state
    visible = bool(state.get("paused", false))
    if not visible:
        return
    if opening:
        hand_choice.clear()
        for hand in state.get("hands", []):
            hand_choice.add_item("Both hands" if hand == "both" else str(hand).capitalize() + " hand")
            var index: int = hand_choice.item_count-1
            hand_choice.set_item_metadata(index, hand)
            if hand == state.get("hand"):
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
        var choices: Array[Control] = [resume_button,retry_button,listen_button,slower_button,faster_button,hand_choice]
        if not seek_button.disabled:
            choices.append(bar_choice.get_line_edit())
            choices.append(seek_button)
        choices.append(exit_button)
        var reverse: bool = event.shift_pressed if tab else event.keycode in [KEY_UP,KEY_LEFT]
        var index: int = choices.find(owner)
        choices[posmod(index + (-1 if reverse else 1), choices.size())].grab_focus()
    get_viewport().set_input_as_handled()
