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
var checkpoint_row: HBoxContainer
var checkpoint_scroll: ScrollContainer
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
	# One strip, like a level select; it scrolls for long pieces.
	checkpoint_scroll = ScrollContainer.new()
	checkpoint_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	checkpoint_scroll.custom_minimum_size = Vector2(640, 86)
	menu.add_child(checkpoint_scroll)
	checkpoint_row = HBoxContainer.new()
	checkpoint_row.add_theme_constant_override("separation", 6)
	checkpoint_scroll.add_child(checkpoint_row)
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
	# A small picture of the checkpoint's first measure, so you can find a
	# place by its shape. Choosing one starts that measure from Listen.
	var bar := int(entry.get("bar", 1))
	var tile := CheckpointTile.new()
	tile.setup(entry)
	tile.tooltip_text = "Measures %d–%d" % [bar, int(entry.get("last_bar", bar))]
	tile.pressed.connect(func(): chosen.emit({"action": "open_at", "bar": bar, "mode": "learn"}))
	return tile


class CheckpointTile extends Button:
	const Look := preload("res://practice_theme.gd")
	const LINE_GAP := 5.0
	var bar := 1
	var notes: Array = []
	var complete := false
	var current := false

	func setup(entry: Dictionary) -> void:
		bar = int(entry.get("bar", 1))
		var preview: Dictionary = entry.get("preview", {}) if entry.get("preview") is Dictionary else {}
		notes = preview.get("notes", []) if preview.get("notes") is Array else []
		complete = bool(entry.get("complete", false))
		current = bool(entry.get("current", false))
		custom_minimum_size = Vector2(100, 74)
		focus_mode = Control.FOCUS_ALL
		mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		flat = true
		for state in ["normal", "hover", "pressed", "hover_pressed", "focus", "disabled"]:
			add_theme_stylebox_override(state, StyleBoxEmpty.new())
		mouse_entered.connect(queue_redraw)
		mouse_exited.connect(queue_redraw)
		focus_entered.connect(queue_redraw)
		focus_exited.connect(queue_redraw)

	func _draw() -> void:
		var lit := is_hovered() or has_focus()
		if current or lit:
			# The same mint key as the menu words, under the tile.
			var key := Rect2(Vector2(6, size.y-4), Vector2(size.x-12, 3))
			for i in range(3, 0, -1):
				draw_rect(key.grow(float(i)*2.0), Color(Look.MINT, .06), true)
			draw_rect(key, Color(Look.MINT, 1.0 if current else .7), true)
		var top := 12.0
		var left := 8.0
		var width := size.x-16.0
		var line := Color(Look.STONE, .28)
		for i in range(5):
			draw_line(Vector2(left, top+i*LINE_GAP), Vector2(left+width, top+i*LINE_GAP), line, 1.0)
		var ink := Look.MINT if complete else Color(Look.STONE, .9 if (lit or current) else .7)
		var bottom := top+4.0*LINE_GAP
		for note in notes:
			if not note is Array or note.size() < 2:
				continue
			var x: float = left+4.0+float(note[0])*(width-8.0)
			var y: float = bottom-float(note[1])*LINE_GAP*.5
			draw_set_transform(Vector2(x, y), -.35, Vector2(1.0, .72))
			draw_circle(Vector2.ZERO, 3.0, ink)
			draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		var font := Look.font(600)
		var label := str(bar)
		var w := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 15).x
		draw_string(font, Vector2((size.x-w)*.5, size.y-9), label, HORIZONTAL_ALIGNMENT_LEFT,
			-1, 15, Look.MINT if current else Color(Look.STONE, .85))


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
		var here: Control = null
		for entry in checkpoints:
			if entry is Dictionary:
				var tile := _checkpoint(entry)
				checkpoint_row.add_child(tile)
				if bool(entry.get("current", false)):
					here = tile
		if here != null:
			checkpoint_scroll.call_deferred("ensure_control_visible", here)
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
