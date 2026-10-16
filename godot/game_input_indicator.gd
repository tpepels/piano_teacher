extends Control

# Phase 7.9: a readable instrument-status lamp in the practice header.
# Connected/disconnected and recent input come solely from Python snapshots.
# A note reception is not a correct-note judgment or a mastery event.
const READY := Color("#82EBC2")
const QUIET := Color("#8BA59B")
const MISSING := Color("#E4AF83")

var connected := false
var is_preview := false
var label := "NO PIANO"
var activity := 0.0
var previous_count := -1
var previous_device := ""

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    custom_minimum_size = Vector2(150, 29)
    size_flags_horizontal = Control.SIZE_SHRINK_END
    size_flags_vertical = Control.SIZE_SHRINK_CENTER

func present(state: Dictionary) -> void:
    var current_device: String = str(state.get("device", ""))
    var current_connected: bool = not current_device.is_empty()
    var preview: bool = bool(state.get("preview_only", false))
    var count: int = maxi(0, int(state.get("midi_input_count", 0)))
    var age: Variant = state.get("midi_input_age")
    var recent: bool = (age != null and float(age) >= 0.0
        and float(age) < .6)
    # An existing count when the UI opens is not a newly received MIDI
    # event. A disconnected/reconnected device cannot inherit old glow.
    var new_input: bool = current_connected and current_device == previous_device \
        and previous_count >= 0 and count > previous_count and recent
    if not current_connected:
        activity = 0.0
    elif new_input:
        activity = 1.0
    previous_count = count
    previous_device = current_device
    var next_label: String = (
        "NO PIANO" if not current_connected else
        "PREVIEW" if preview else "MIDI CONNECTED")
    if connected != current_connected or is_preview != preview \
            or next_label != label or new_input:
        connected = current_connected
        is_preview = preview
        label = next_label
        queue_redraw()

func _process(delta: float) -> void:
    if activity <= 0.001:
        return
    activity = maxf(0.0, activity - maxf(0.0, delta) * 1.9)
    queue_redraw()

func _draw() -> void:
    if size.x < 35.0 or size.y < 15.0:
        return
    var tone: Color = (
        MISSING if not connected else QUIET if is_preview else READY)
    var y: float = size.y * .5
    var center := Vector2(12.0, y)
    var flash: float = activity if connected else 0.0
    # Console LEDs: clear connection status, with a short ring exclusively
    # when the physical device actually reports new MIDI input.
    draw_circle(center, 10.0 + flash * 5.0,
        Color(tone, .07 + flash * .16))
    draw_circle(center, 6.0, Color("#112422"))
    draw_arc(center, 6.4, 0, TAU, 32, Color(tone, .64), 1.25, true)
    draw_circle(center, 3.4 + flash * 2.0, Color(tone, .66 + flash * .34))
    var font: Font = ThemeDB.fallback_font
    var font_size := 13
    var available: float = maxf(0.0, size.x - 32.0)
    var baseline: float = y + (font.get_ascent(font_size)
        - font.get_descent(font_size)) * .5
    draw_string(font, Vector2(29.0, baseline), label,
        HORIZONTAL_ALIGNMENT_LEFT, available, font_size,
        Color("#E4F6EB") if connected and not is_preview else Color("#AFC7BC"))
