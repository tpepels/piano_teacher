extends Control
## The pause menu: a game menu over the frozen score. Python stays the
## authority for every action; this only offers the projected controls.
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")

signal chosen(command: Dictionary)

var heading: Label
var where_label: Label
var resume_button: Button
var listen_button: Button
var checkpoint_row: HFlowContainer
var hand_row: HBoxContainer
var slower_button: Button
var tempo_value: Label
var faster_button: Button
var exit_button: Button
var panel: PanelContainer
var current: Dictionary = {}
var _checkpoints: Array = []
var _hands: Array = []


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(Design.NIGHT, .82)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(shade)
	# Left-aligned menu column on the stage, like a game's pause screen.
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	margin.add_theme_constant_override("margin_left", 72)
	margin.add_theme_constant_override("margin_top", 56)
	margin.add_theme_constant_override("margin_bottom", 40)
	add_child(margin)
	panel = PanelContainer.new()
	panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	panel.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	margin.add_child(panel)
	var menu := VBoxContainer.new()
	menu.add_theme_constant_override("separation", 6)
	panel.add_child(menu)

	heading = Label.new()
	heading.text = "Paused"
	heading.add_theme_font_override("font", Design.title_font())
	heading.add_theme_font_size_override("font_size", 54)
	heading.add_theme_color_override("font_color", Design.STONE)
	menu.add_child(heading)
	where_label = _small("", menu)
	_gap(menu, 18)

	resume_button = _item("Resume", {"action": "ui_primary"}, menu)
	listen_button = _item("Listen again", {"action": "ui_listen"}, menu)
	_gap(menu, 18)

	_small("Checkpoints", menu)
	checkpoint_row = HFlowContainer.new()
	checkpoint_row.add_theme_constant_override("h_separation", 8)
	checkpoint_row.add_theme_constant_override("v_separation", 8)
	checkpoint_row.custom_minimum_size.x = 420
	menu.add_child(checkpoint_row)
	_gap(menu, 18)

	hand_row = HBoxContainer.new()
	hand_row.add_theme_constant_override("separation", 0)
	menu.add_child(hand_row)
	_gap(menu, 6)
	var tempo_row := HBoxContainer.new()
	tempo_row.add_theme_constant_override("separation", 0)
	menu.add_child(tempo_row)
	slower_button = _item("−", {"action": "ui_tempo_down"}, tempo_row, 30)
	slower_button.tooltip_text = "Slower"
	tempo_value = _small("", tempo_row)
	tempo_value.add_theme_font_size_override("font_size", 22)
	tempo_value.add_theme_color_override("font_color", Design.STONE)
	tempo_value.custom_minimum_size.x = 104
	tempo_value.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	faster_button = _item("+", {"action": "ui_tempo_up"}, tempo_row, 30)
	faster_button.tooltip_text = "Faster"
	_gap(menu, 18)
	exit_button = _item("Exit", {"action": "exit"}, menu, 30, "menu_danger")
	visible = false


func _small(text: String, parent: Node) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_override("font", Design.font(500))
	label.add_theme_font_size_override("font_size", 17)
	label.add_theme_color_override("font_color", Design.SLATE)
	parent.add_child(label)
	return label


func _gap(parent: Node, height: float) -> void:
	var gap := Control.new()
	gap.custom_minimum_size.y = height
	parent.add_child(gap)


func _item(text: String, command: Dictionary, parent: Node, font_size := 34,
		role := "menu") -> Button:
	var button := ActionButton.new()
	button.text = text
	button.add_theme_font_size_override("font_size", font_size)
	button.configure(role)
	button.custom_minimum_size.y = font_size + 22
	parent.add_child(button)
	if not command.is_empty():
		button.pressed.connect(func(): chosen.emit(command))
	return button


func _checkpoint(entry: Dictionary) -> Button:
	# One measure number per checkpoint: filled when complete, ringed
	# where you are now. Choosing one starts that measure from Listen.
	var bar := int(entry.get("bar", 1))
	var button := ActionButton.new()
	button.text = str(bar)
	button.tooltip_text = "Measures %d–%d" % [bar, int(entry.get("last_bar", bar))]
	button.add_theme_font_size_override("font_size", 18)
	button.configure("choice")
	button.set_selected(bool(entry.get("current", false)))
	button.custom_minimum_size = Vector2(52, 44)
	if bool(entry.get("complete", false)) and not bool(entry.get("current", false)):
		button.add_theme_color_override("font_color", Design.MINT)
	button.pressed.connect(func(): chosen.emit({"action": "open_at", "bar": bar, "mode": "learn"}))
	return button


func present(state: Dictionary) -> void:
	var opening: bool = not visible and bool(state.get("paused", false))
	current = state
	visible = bool(state.get("paused", false))
	if not visible:
		return
	var screen: Dictionary = state.get("screen", {}) if state.get("screen") is Dictionary else {}
	where_label.text = str(screen.get("status", ""))
	var controls: Dictionary = state.get("controls", {}) if state.get("controls") is Dictionary else {}
	var primary: Dictionary = controls.get("primary", {})
	resume_button.disabled = str(primary.get("action", "")) != "resume" \
		or not bool(primary.get("enabled", false))
	listen_button.disabled = not bool(controls.get("listen", {}).get("enabled", false))
	slower_button.disabled = not bool(controls.get("tempo_down", {}).get("enabled", false))
	faster_button.disabled = not bool(controls.get("tempo_up", {}).get("enabled", false))
	tempo_value.text = "%d BPM" % int(state.get("bpm", 0))
	var checkpoints: Array = state.get("checkpoints", []) if state.get("checkpoints") is Array else []
	if checkpoints != _checkpoints:
		_checkpoints = checkpoints.duplicate(true)
		for child in checkpoint_row.get_children():
			child.queue_free()
		for entry in checkpoints:
			if entry is Dictionary:
				checkpoint_row.add_child(_checkpoint(entry))
	var hands: Array = state.get("hands", []) if state.get("hands") is Array else []
	var hand_actions: Dictionary = controls.get("hands", {})
	var hand_key := [hands, str(state.get("hand", "")), hand_actions]
	if hand_key != _hands:
		_hands = hand_key.duplicate(true)
		for child in hand_row.get_children():
			child.queue_free()
		for hand in hands:
			var name: String = {"right": "Right", "left": "Left"}.get(str(hand), "Both")
			var button := _item(name, {"action": "hand", "hand": hand}, hand_row, 26)
			button.set_selected(str(hand) == str(state.get("hand", "")))
			button.disabled = not bool(hand_actions.get(str(hand), {}).get("enabled", false))
	if opening:
		resume_button.grab_focus()


func _input(event: InputEvent) -> void:
	# Up/Down/Tab walk the menu without leaving it.
	if not visible or not event is InputEventKey or not event.pressed or event.echo:
		return
	if event.keycode not in [KEY_UP, KEY_DOWN, KEY_TAB]:
		return
	var choices: Array[Control] = []
	for button in [resume_button, listen_button]:
		if not button.disabled: choices.append(button)
	for child in checkpoint_row.get_children() + hand_row.get_children():
		if child is Button and not child.disabled: choices.append(child)
	for button in [slower_button, faster_button, exit_button]:
		if not button.disabled: choices.append(button)
	if choices.is_empty():
		return
	var reverse: bool = event.shift_pressed if event.keycode == KEY_TAB else event.keycode == KEY_UP
	var index: int = choices.find(get_viewport().gui_get_focus_owner())
	choices[posmod(index + (-1 if reverse else 1), choices.size())].grab_focus()
	get_viewport().set_input_as_handled()
