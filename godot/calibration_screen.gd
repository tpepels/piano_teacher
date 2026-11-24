extends VBoxContainer
## Timing calibration, on its own page. Python runs the measurement
## (midi_calibration.py); this page shows the clicks, each tap, the result.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")

signal calibration_requested(action: String)
signal navigation_requested(destination: String)

var ui_scale := 1.0
var count_label: Label
var calibration_beat_pulse: Control
var tap_strip: TapStrip
var result_label: Label
var saved_label: Label
var start_button: Button
var apply_button: Button
var cancel_button: Button


func _ready() -> void:
	name = "CalibrationScreen"
	theme = Design.create()
	add_theme_constant_override("separation", 14)
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var back := _key("Back to settings", func(): navigation_requested.emit("settings"))
	back.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	add_child(back)
	add_child(UI.title("Timing", 44))
	var intro := UI.label("Tap one key on your piano with every click. The result "
		+ "corrects for the delay of your piano, speakers and your own timing.", 16, Design.SECONDARY_INK)
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(intro)
	count_label = UI.label("", 40, Design.STONE, true)
	count_label.add_theme_font_override("font", Design.title_font())
	add_child(count_label)
	calibration_beat_pulse = preload("res://calibration_beat_pulse.gd").new()
	add_child(calibration_beat_pulse)
	tap_strip = TapStrip.new()
	tap_strip.custom_minimum_size = Vector2(0, 92)
	tap_strip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_child(tap_strip)
	result_label = UI.label("", 20, Design.STONE)
	result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(result_label)
	saved_label = UI.label("", 15, Design.SECONDARY_INK)
	add_child(saved_label)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 10)
	add_child(actions)
	start_button = _key("Start", func(): calibration_requested.emit("calibration_start"))
	actions.add_child(start_button)
	apply_button = _key("Use this", func(): calibration_requested.emit("calibration_apply"))
	apply_button.disabled = true
	actions.add_child(apply_button)
	cancel_button = _key("Stop", func(): calibration_requested.emit("calibration_cancel"))
	actions.add_child(cancel_button)
	actions.add_child(_key("Reset to 0 ms", func(): calibration_requested.emit("calibration_reset"), "key_danger"))


func _key(text: String, action: Callable, role := "key") -> Button:
	var button := ActionButton.new()
	button.text = text
	button.add_theme_font_size_override("font_size", 16)
	button.configure(role)
	button.custom_minimum_size = Vector2(0, 44)
	button.pressed.connect(action)
	return button


func apply_viewport(_view_size: Vector2, scale: float) -> void:
	ui_scale = scale


func animate_calibration_beat(beat: float, active: bool,
		round_beats: int = 8, preparation: int = 4) -> void:
	calibration_beat_pulse.call("present_beat", beat, active, round_beats, preparation)


func present_calibration(state: Dictionary, offset_ms: int) -> void:
	var active: bool = bool(state.get("active", false))
	var phase: String = str(state.get("phase", "ready"))
	var taps: int = maxi(1, int(state.get("taps", 24)))
	count_label.visible = active
	if phase == "ready":
		count_label.text = "Get ready"
	elif phase == "count_in":
		count_label.text = str(int(state.get("countdown", 4)))
	else:
		count_label.text = "Tap %d of %d" % [int(state.get("tap_number", 0)), taps]
	tap_strip.present(state.get("tap_offsets_ms", []) if state.get("tap_offsets_ms") is Array else [])
	start_button.text = "Again" if state.get("result") is Dictionary else "Start"
	start_button.disabled = active
	cancel_button.visible = active
	saved_label.text = "Current correction: %d ms" % offset_ms
	var result: Variant = state.get("result")
	apply_button.disabled = active or not (result is Dictionary and bool(result.get("reliable", false)))
	if active:
		result_label.text = "Tap with each click. Each dot is one tap: left is early, right is late."
	elif result is Dictionary:
		var r: Dictionary = result
		if bool(r.get("reliable", false)):
			result_label.text = "Measured %d ms (taps within ±%d ms). %s" % [
				int(r.get("measured_ms", 0)), int(r.get("spread_ms", 0)),
				str(r.get("note", "Choose Use this to save it."))]
		else:
			result_label.text = str(r.get("error", "Try again."))
	else:
		result_label.text = "Press Start, then tap along with %d clicks." % taps


class TapStrip extends Control:
	## One line: the click is the centre; each tap is a dot left (early)
	## or right (late) of it, newest brightest. Range ±250 ms.
	const Look := preload("res://practice_theme.gd")
	var offsets: Array = []

	func present(values: Array) -> void:
		if values != offsets:
			offsets = values.duplicate()
			queue_redraw()

	func _draw() -> void:
		var mid := size.y*.5
		var center := size.x*.5
		var span := size.x*.45
		draw_line(Vector2(center-span, mid), Vector2(center+span, mid), Color(Look.STONE, .2), 2.0)
		draw_line(Vector2(center, mid-26), Vector2(center, mid+26), Look.MINT, 2.0)
		var font := Look.font(500)
		for item in [["early", center-span], ["late", center+span-32.0]]:
			draw_string(font, Vector2(float(item[1]), mid+42), str(item[0]),
				HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(Look.STONE, .5))
		draw_string(font, Vector2(center-24.0, mid-34), "on the click",
			HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(Look.MINT, .8))
		for i in range(offsets.size()):
			var ms := clampf(float(offsets[i]), -250.0, 250.0)
			var x := center + ms/250.0*span
			var newest := i == offsets.size()-1
			var alpha := .35 + .65*float(i+1)/float(offsets.size())
			draw_circle(Vector2(x, mid), 7.0 if newest else 5.0, Color(Look.STONE, alpha))
