extends Control
# Self-contained modal for selecting a source measure before opening a lesson.
# No HTTP, navigation or practice-state dependencies. The parent reacts to
# confirmed/cancel_requested signals. The panel remains inside the game window.
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL

signal confirmed(bar: int, mode: String)
signal cancel_requested

var panel: PanelContainer
var measure: SpinBox
var measure_slider: HSlider
var mode_choice: OptionButton
var title_label: Label
var intro: Tween
var ui_scale := 1.0

func _font_size(base: int) -> int:
    return maxi(14, int(round(float(base) * ui_scale)))

func _stack(separation: int) -> VBoxContainer:
    var stack := VBoxContainer.new()
    stack.add_theme_constant_override("separation", separation)
    return stack

func _label(value: String, font_size: int, color: Color, bold := false) -> Label:
    var label := Label.new()
    label.text = value
    label.add_theme_color_override("font_color", color)
    label.set_meta("ui_font_base", font_size)
    label.add_theme_font_size_override("font_size", _font_size(font_size))
    label.add_theme_font_override("font", Design.font(700 if bold else 400))
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return label

func _button(value: String, primary := false, role: String = "") -> Button:
    var button := ActionButton.new()
    button.text = value
    button.clip_text = false
    button.set_meta("ui_font_base", 15)
    button.add_theme_font_size_override("font_size", _font_size(15))
    button.configure(role if not role.is_empty() else "primary" if primary else "secondary")
    var text_width: float = Design.font(400).get_string_size(
        value, HORIZONTAL_ALIGNMENT_LEFT, -1, _font_size(15)).x
    button.custom_minimum_size = Vector2(
        maxf(96.0, text_width+48.0*ui_scale), 38.0*ui_scale)
    return button

func _ready() -> void:
    name = "StartingMeasureOverlay"
    z_index = 20
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    mouse_filter = Control.MOUSE_FILTER_STOP
    visible = false
    var scrim := ColorRect.new()
    scrim.color = Color("#06110F", .81)
    scrim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    scrim.mouse_filter = Control.MOUSE_FILTER_STOP
    scrim.gui_input.connect(func(event: InputEvent):
        if event is InputEventMouseButton and event.pressed:
            cancel_requested.emit())
    add_child(scrim)
    panel = PanelContainer.new()
    panel.name = "StartingMeasurePanel"
    panel.mouse_filter = Control.MOUSE_FILTER_STOP
    panel.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    panel.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    panel.add_theme_stylebox_override("panel", Design.modal_surface())
    add_child(panel)
    var start_scroll := ScrollContainer.new()
    start_scroll.name = "StartContentScroll"
    start_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    start_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
    start_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    var column := _stack(10)
    column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    column.size_flags_vertical = Control.SIZE_EXPAND_FILL
    var margins := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        margins.add_theme_constant_override("margin_"+side, 18)
    panel.add_child(margins)
    margins.add_child(column)
    column.add_child(start_scroll)
    var content := _stack(12)
    start_scroll.add_child(content)
    content.add_child(_label("CHOOSE A STARTING POINT", 14, ACCENT, true))
    title_label = _label("", 24, INK, true)
    title_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    content.add_child(title_label)
    content.add_child(_label("Start at any measure of this piece.", 16, MUTED))
    content.add_child(_label("SOURCE MEASURE", 14, ACCENT, true))
    measure = SpinBox.new()
    measure.min_value = 1
    measure.max_value = 1
    measure.step = 1
    measure.custom_minimum_size = Vector2(0, 54)
    measure.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    measure.set_meta("ui_font_base", 19)
    measure.add_theme_font_size_override("font_size", _font_size(19))
    content.add_child(measure)
    measure_slider = HSlider.new()
    measure_slider.min_value = 1
    measure_slider.max_value = 1
    measure_slider.step = 1
    measure_slider.custom_minimum_size.y = 32
    content.add_child(measure_slider)
    measure.value_changed.connect(func(value: float):
        measure_slider.set_value_no_signal(value))
    measure_slider.value_changed.connect(func(value: float):
        measure.set_value_no_signal(value))
    var jumps := HBoxContainer.new()
    jumps.name = "SourceMeasureQuickJumps"
    jumps.add_theme_constant_override("separation", 10)
    content.add_child(jumps)
    for kind in ["Beginning", "Middle", "End"]:
        var choice: String = kind
        var jump := _button(kind, false, "utility")
        jump.pressed.connect(func():
            var target := 1 if choice == "Beginning" else (
                int(ceil(measure.max_value/2.0)) if choice == "Middle"
                else int(measure.max_value))
            measure.value = target)
        jump.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        jump.custom_minimum_size = Vector2(0, 40)
        jump.set_meta("ui_font_base", 13)
        jump.add_theme_font_size_override("font_size", _font_size(13))
        jumps.add_child(jump)
    content.add_child(_label("BEGIN WITH", 14, ACCENT, true))
    mode_choice = OptionButton.new()
    mode_choice.add_item("Learn notes (without timing)")
    mode_choice.add_item("Practice rhythm")
    mode_choice.custom_minimum_size.y = 54
    mode_choice.set_meta("ui_font_base", 16)
    mode_choice.add_theme_font_size_override("font_size", _font_size(16))
    content.add_child(mode_choice)
    content.add_child(_label(
        "Learn starts with notes only. Practice uses the metronome and rhythm.",
        14, MUTED))
    var actions := HBoxContainer.new()
    actions.name = "StartPickerActions"
    actions.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    actions.add_theme_constant_override("separation", 12)
    column.add_child(actions)
    var cancel := _button("Cancel", false, "navigation")
    cancel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    cancel.pressed.connect(func(): cancel_requested.emit())
    actions.add_child(cancel)
    var confirm := _button("Open music", true)
    confirm.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    confirm.pressed.connect(func(): confirmed.emit(
        selected_bar(), selected_mode()))
    actions.add_child(confirm)
    resized.connect(func(): resize_panel(size))
    resize_panel(size)

func resize_panel(view_size: Vector2) -> void:
    if panel == null:
        return
    var width: float = minf(620.0, maxf(280.0, view_size.x-36.0))
    var height: float = minf(570.0, view_size.y*.84)
    panel.custom_minimum_size = Vector2(width, 0)
    panel.size = Vector2(width, height)
    panel.position = (view_size-panel.size)*.5

func show_piece(state: Dictionary) -> void:
    var last_bar: int = maxi(1, int(state.get("piece_last_bar", 1)))
    title_label.text = str(state.get("title", "Untitled piece")).replace("_", " ")
    measure.max_value = last_bar
    measure.min_value = 1
    measure.value = clampi(int(state.get("selected_start_bar", 1)), 1, last_bar)
    measure.suffix = " / %d" % last_bar
    measure_slider.max_value = last_bar
    measure_slider.min_value = 1
    measure_slider.set_value_no_signal(measure.value)
    mode_choice.select(0)
    resize_panel(size)
    visible = true
    if intro != null and intro.is_running():
        intro.kill()
    panel.modulate.a = 0.0
    intro = create_tween()
    intro.tween_property(panel, "modulate:a", 1.0, .18) \
        .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
    measure.get_line_edit().grab_focus()

func selected_bar() -> int:
    # Enter arrives before SpinBox commits its embedded LineEdit.
    if get_viewport().gui_get_focus_owner() == measure.get_line_edit():
        measure.value = clampi(measure.get_line_edit().text.to_int(),
            1, int(measure.max_value))
    return int(measure.value)

func selected_mode() -> String:
    return "practice" if mode_choice.selected == 1 else "learn"

func is_mode_popup_open() -> bool:
    return mode_choice.get_popup().visible
