extends Control
## A read-only diagram of the current guided target, driven entirely by MIDI state.

const Design = preload("res://practice_theme.gd")
const EXPECTED := Color("#C8AC7C")
const NATURAL := Color("#525E57")
const ACCIDENTAL := Color("#202925")
const KEY_GAP := 1.0
const REGISTER_GAP := 22.0

var _expected_label: Label
var _heard_label: Label
var _expected: Dictionary = {}
var _heard: Dictionary = {}
var _registers: Array[Dictionary] = []
var _keys: Dictionary = {}

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    custom_minimum_size = Vector2(0, 100)
    visible = false

func _ready() -> void:
    _expected_label = _label(EXPECTED)
    _heard_label = _label(Design.SLATE)
    _heard_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    resized.connect(_layout_keys)
    get_viewport().size_changed.connect(_update_compact_height)
    _update_compact_height()

func _label(color: Color) -> Label:
    var label := Label.new()
    label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    label.add_theme_color_override("font_color", color)
    label.add_theme_font_size_override("font_size", 12)
    label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    add_child(label)
    return label

func _update_compact_height() -> void:
    custom_minimum_size.y = 88 if get_viewport_rect().size.y < 720 else 100
    _layout_keys()

func update_state(teaching: Dictionary) -> void:
    _expected.clear()
    _heard.clear()
    for note in teaching.get("expected_notes", []):
        if not note is Dictionary:
            continue
        var pitch := int(note.get("pitch", -1))
        if pitch < 21 or pitch > 108:
            continue
        var name := str(note.get("label", ""))
        _expected[pitch] = name if not name.is_empty() else _pitch_name(pitch)
    for value in teaching.get("heard_pitches", []):
        var pitch := int(value)
        if pitch >= 0 and pitch <= 127:
            _heard[pitch] = true
    var phase := str(teaching.get("phase", ""))
    visible = bool(teaching.get("hint_visible", false)) and not _expected.is_empty() \
        and not bool(teaching.get("completed", false)) \
        and phase not in ["guided_complete", "finished", "complete"]
    if not is_node_ready():
        await ready
    var expected_names: PackedStringArray = []
    var heard_names: PackedStringArray = []
    var pitches: Array = _expected.keys()
    pitches.sort()
    for pitch in pitches:
        expected_names.append(str(_expected[pitch]))
    var heard_pitches: Array = _heard.keys()
    heard_pitches.sort()
    for pitch in heard_pitches:
        heard_names.append(_pitch_name(int(pitch)))
    var prompt := "Find" if str(teaching.get("hint_reason", "")) == "stall" else "Play"
    _expected_label.text = prompt + "  " + " · ".join(expected_names)
    _expected_label.tooltip_text = _expected_label.text
    _heard_label.text = "Heard  " + (" · ".join(heard_names) if not heard_names.is_empty() else "—")
    _heard_label.tooltip_text = _heard_label.text
    _registers.clear()
    if not pitches.is_empty():
        var groups: Array = []
        _split_registers(pitches, groups)
        for group in groups:
            _registers.append(_context_range(group, groups.size() == 1))
    _layout_keys()

func _pitch_name(pitch: int) -> String:
    return ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][pitch % 12] \
        + str(pitch / 12 - 1)

func _black(pitch: int) -> bool:
    return pitch % 12 in [1, 3, 6, 8, 10]

func _split_registers(pitches: Array, groups: Array) -> void:
    if int(pitches[-1]) - int(pitches[0]) <= 24:
        groups.append(pitches)
        return
    # Remove empty octaves between the hands rather than shrinking an 88-key piano.
    var split := 1
    var widest := 0
    for index in range(1, pitches.size()):
        var gap := int(pitches[index]) - int(pitches[index - 1])
        if gap > widest:
            widest = gap
            split = index
    _split_registers(pitches.slice(0, split), groups)
    _split_registers(pitches.slice(split), groups)

func _context_range(pitches: Array, single: bool) -> Dictionary:
    var low := int(pitches[0])
    var high := int(pitches[-1])
    var span := 24 if single else mini(24, maxi(12, high - low + 4))
    var first := clampi(floori(float(low + high - span) / 2.0), 21, 108 - span)
    var last := first + span
    first = mini(first, low)
    last = maxi(last, high)
    if _black(first):
        first -= 1
    if _black(last):
        last += 1
    return {"low": first, "high": last}

func _layout_keys() -> void:
    _keys.clear()
    if not is_instance_valid(_expected_label):
        return
    _expected_label.position = Vector2.ZERO
    _expected_label.size = Vector2(maxf(0, size.x * .58 - 8), 20)
    _heard_label.position = Vector2(size.x * .58, 0)
    _heard_label.size = Vector2(maxf(0, size.x * .42), 20)
    var white_total := 0
    for register in _registers:
        var white_count := 0
        for pitch in range(int(register.low), int(register.high) + 1):
            if not _black(pitch):
                white_count += 1
        register["whites"] = white_count
        white_total += white_count
    if white_total == 0:
        queue_redraw()
        return
    var width := maxf(1, (size.x - REGISTER_GAP * (_registers.size() - 1)) / white_total)
    var x := 0.0
    var top := 24.0
    var height := maxf(1, size.y - top - 2)
    for register in _registers:
        var begin := x
        for pitch in range(int(register.low), int(register.high) + 1):
            if _black(pitch):
                continue
            _keys[pitch] = {"rect": Rect2(x, top, width - KEY_GAP, height),
                "black": false, "expected": _expected.has(pitch), "heard": _heard.has(pitch)}
            x += width
        # All black-key positions derive from the preceding natural key, including B/C and E/F gaps.
        for pitch in range(int(register.low), int(register.high) + 1):
            if not _black(pitch) or not _keys.has(pitch - 1):
                continue
            var preceding: Rect2 = _keys[pitch - 1].rect
            _keys[pitch] = {"rect": Rect2(preceding.end.x + KEY_GAP - width * .32, top,
                width * .64, height * .62), "black": true,
                "expected": _expected.has(pitch), "heard": _heard.has(pitch)}
        register["rect"] = Rect2(begin, top, x - begin, height)
        x += REGISTER_GAP
    queue_redraw()

func _draw() -> void:
    var font := get_theme_default_font()
    for black in [false, true]:
        for pitch in _keys:
            var key: Dictionary = _keys[pitch]
            if bool(key.black) != black:
                continue
            var rect: Rect2 = key.rect
            var fill := ACCIDENTAL if black else NATURAL
            if bool(key.expected):
                fill = Design.SAGE.darkened(.18) if black else Design.SAGE
            draw_style_box(Design.surface(fill, 2), rect)
            if bool(key.expected):
                draw_rect(rect.grow(-1), EXPECTED, false, 1.5)
                var marker := Vector2(rect.get_center().x, rect.position.y + 8 if black else rect.end.y - 24)
                draw_colored_polygon(PackedVector2Array([marker + Vector2(-4, 0), marker + Vector2(4, 0),
                    marker + Vector2(0, 5)]), EXPECTED)
            if bool(key.heard):
                # A round slate marker survives alongside the triangular expected marker on the same key.
                var heard_at := Vector2(rect.end.x - 6, rect.position.y + 8 if black else rect.end.y - 14)
                draw_circle(heard_at, 3, Design.SLATE)
                draw_arc(heard_at, 4.5, 0, TAU, 16, Design.SLATE, 1, true)
            var label := ""
            if bool(key.expected):
                label = str(_expected[pitch])
            elif bool(key.heard) or int(pitch) % 12 == 0:
                label = _pitch_name(int(pitch))
            if not label.is_empty():
                var font_size := 11 if black else 12
                var text_width := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                var position := Vector2(rect.get_center().x - text_width / 2, rect.end.y - 4)
                draw_string(font, position, label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size,
                    EXPECTED if bool(key.expected) else Design.STONE)
    for index in range(1, _registers.size()):
        var register_rect: Rect2 = _registers[index].rect
        var center := Vector2(register_rect.position.x - REGISTER_GAP / 2, register_rect.get_center().y)
        draw_line(center + Vector2(-3, -6), center + Vector2(1, -1), Design.SLATE, 1, true)
        draw_line(center + Vector2(-1, 1), center + Vector2(3, 6), Design.SLATE, 1, true)
