extends Control
## A read-only diagram of the current guided target, driven entirely by MIDI state.

const Design = preload("res://practice_theme.gd")
const EXPECTED := Color("#C8AC7C")
# A real piano: ivory naturals, ebony sharps, a felt strip under the lid.
const IVORY := Color("#F3EEDF")
const IVORY_SHADE := Color("#D9D1BC")
const EBONY := Color("#16181A")
const EBONY_SHINE := Color("#3A3E42")
const FELT := Color("#7A1F24")
const CASE := Color("#0B0C0D")
const TARGET := Color("#7FD8B5")
const TARGET_DARK := Color("#2E8F6E")
const KEY_GAP := 1.0
const REGISTER_GAP := 22.0
# A white key is about this many times as long as it is wide (a real one
# is ~6; shorter keeps the hint compact while still reading as a piano).
const KEY_ASPECT := 4.2
const BLACK_LENGTH := .63
const BLACK_WIDTH := .58
## Room kept free on each side, for the held-notes staff.
var side_reserve := 0.0

var _expected_label: Label
var _heard_label: Label
var _expected: Dictionary = {}
var _heard: Dictionary = {}
var _live_mode := false
var _pressed: Dictionary = {}
var _last_pitch := -1
var _last_status := ""
var _last_age := 999.0
var _registers: Array[Dictionary] = []
var _keys: Dictionary = {}
var _presentation: Dictionary = {}
var ui_scale := 1.0
var _key_fifths := 0

func set_key_fifths(value: int) -> void:
    var selected := clampi(value, -7, 7)
    if _key_fifths != selected:
        _key_fifths = selected
        _presentation.clear()
        queue_redraw()

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
    label.add_theme_font_size_override("font_size", _ui_font(13))
    label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    add_child(label)
    return label

func _ui_font(base: int) -> int:
    return maxi(12, int(round(float(base) * ui_scale)))

func set_ui_scale(value: float) -> void:
    ui_scale = value
    if is_instance_valid(_expected_label):
        _expected_label.add_theme_font_size_override("font_size", _ui_font(13))
        _heard_label.add_theme_font_size_override("font_size", _ui_font(13))
    _update_compact_height()

func _update_compact_height() -> void:
    custom_minimum_size.y = (72 if get_viewport_rect().size.y < 720 else 84) * ui_scale
    _layout_keys()

func update_state(teaching: Dictionary) -> void:
    var presentation := {"live":false, "expected":teaching.get("expected_notes", []),
        "heard":teaching.get("heard_pitches", []), "visible":teaching.get("hint_visible", false),
        "completed":teaching.get("completed", false), "phase":teaching.get("phase", ""),
        "reason":teaching.get("hint_reason", "")}
    if presentation == _presentation:
        return
    _presentation = presentation.duplicate(true)
    _live_mode = false
    _pressed.clear()
    _expected.clear()
    _heard.clear()
    for note in teaching.get("expected_notes", []):
        if not note is Dictionary:
            continue
        var pitch := int(note.get("pitch", -1))
        if pitch < 21 or pitch > 108:
            continue
        var name := str(note.get("label", ""))
        _expected[pitch] = _pitch_name(pitch) if _key_fifths != 0 else (name if not name.is_empty() else _pitch_name(pitch))
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
    var names := ["C", "D", "E", "F", "G", "A", "B"]
    var semitones := [0, 2, 4, 5, 7, 9, 11]
    var changes: Dictionary = {}
    var order := ["B", "E", "A", "D", "G", "C", "F"] if _key_fifths < 0 else ["F", "C", "G", "D", "A", "E", "B"]
    for i in range(absi(_key_fifths)):
        changes[order[i]] = -1 if _key_fifths < 0 else 1
    for i in range(names.size()):
        var alter: int = int(changes.get(names[i], 0))
        if posmod(semitones[i] + alter, 12) == posmod(pitch, 12):
            var octave := floori(float(pitch - semitones[i] - alter) / 12.0) - 1
            return names[i] + ("b" if alter < 0 else "#" if alter > 0 else "") + str(octave)
    var fallback := (["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
        if _key_fifths < 0 else
        ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])
    return fallback[posmod(pitch, 12)] + str(floori(float(pitch) / 12.0) - 1)

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
    var white_total := 0
    for register in _registers:
        var white_count := 0
        for pitch in range(int(register.low), int(register.high) + 1):
            if not _black(pitch):
                white_count += 1
        register["whites"] = white_count
        white_total += white_count
    var top := 24.0 * ui_scale
    var lid := 5.0 * ui_scale
    var height := maxf(1, size.y - top - lid - 2 * ui_scale)
    # Proportions of a real keyboard, centred; never wider than the space
    # between the side reserves.
    var gaps := REGISTER_GAP * maxf(0, _registers.size() - 1)
    var room := maxf(1, size.x - 2.0 * side_reserve - gaps)
    var width := minf(height / KEY_ASPECT, room / maxf(1, white_total))
    var total := width * white_total + gaps
    var x := (size.x - total) / 2.0
    _expected_label.position = Vector2(x, 0)
    _expected_label.size = Vector2(maxf(0, total * .5 - 6), 20 * ui_scale)
    _heard_label.position = Vector2(x + total * .5, 0)
    _heard_label.size = Vector2(maxf(0, total * .5), 20 * ui_scale)
    if white_total == 0:
        queue_redraw()
        return
    var key_top := top + lid
    for register in _registers:
        var begin := x
        for pitch in range(int(register.low), int(register.high) + 1):
            if _black(pitch):
                continue
            _keys[pitch] = {"rect": Rect2(x, key_top, width - KEY_GAP, height),
                "black": false, "expected": _expected.has(pitch), "heard": _heard.has(pitch)}
            x += width
        # All black-key positions derive from the preceding natural key, including B/C and E/F gaps.
        for pitch in range(int(register.low), int(register.high) + 1):
            if not _black(pitch) or not _keys.has(pitch - 1):
                continue
            var preceding: Rect2 = _keys[pitch - 1].rect
            _keys[pitch] = {"rect": Rect2(preceding.end.x + KEY_GAP * .5 - width * BLACK_WIDTH * .5,
                key_top, width * BLACK_WIDTH, height * BLACK_LENGTH), "black": true,
                "expected": _expected.has(pitch), "heard": _heard.has(pitch)}
        register["rect"] = Rect2(begin, top, x - begin, height + lid)
        x += REGISTER_GAP
    queue_redraw()

func _draw() -> void:
    var font := get_theme_default_font()
    # The case and the red felt under the lid, behind each register.
    for register in _registers:
        if not register.has("rect"):
            continue
        var case: Rect2 = register.rect
        draw_rect(Rect2(case.position - Vector2(3, 0), Vector2(case.size.x + 6, 5.0 * ui_scale)), CASE, true)
        draw_rect(Rect2(case.position + Vector2(0, 5.0 * ui_scale - 2), Vector2(case.size.x, 2)), FELT, true)
    var labels: Array = []
    for black in [false, true]:
        for pitch in _keys:
            var key: Dictionary = _keys[pitch]
            if bool(key.black) != black:
                continue
            var rect: Rect2 = key.rect
            var fill := EBONY if black else IVORY
            if bool(key.expected):
                fill = TARGET_DARK if black else TARGET
            if _live_mode and _pressed.has(pitch):
                var status: String = str(_pressed[pitch])
                fill = Color("#BB514D") if status == "unexpected" else Color("#C68D4D") if status in ["early", "late", "count_in"] else Color("#4AA989")
            var face := StyleBoxFlat.new()
            face.bg_color = fill
            face.corner_radius_bottom_left = 3 if not black else 2
            face.corner_radius_bottom_right = face.corner_radius_bottom_left
            face.anti_aliasing = true
            draw_style_box(face, rect)
            if black:
                # A lighter bevel at the front of an ebony key.
                var front := Rect2(rect.position.x + 1.5, rect.end.y - rect.size.y * .14,
                    rect.size.x - 3, rect.size.y * .1)
                draw_rect(front, (fill.lightened(.18) if bool(key.expected) else EBONY_SHINE), true)
            else:
                # The worn front edge of an ivory key.
                draw_rect(Rect2(rect.position.x, rect.end.y - 3, rect.size.x, 3),
                    fill.darkened(.12) if bool(key.expected) else IVORY_SHADE, true)
            if bool(key.heard) and not _live_mode:
                var heard_at := Vector2(rect.get_center().x, rect.position.y + rect.size.y * (.35 if black else .55))
                draw_circle(heard_at, maxf(2.0, rect.size.x * .16), Design.SLATE if black else Design.CHARCOAL)
            if not black:
                if bool(key.expected):
                    labels.append([0, rect, str(_expected[pitch]), Color("#173B30")])
                elif bool(key.heard) or (_live_mode and _pressed.has(pitch)):
                    labels.append([1, rect, _pitch_name(int(pitch)), Color("#3A372F")])
                elif int(pitch) % 12 == 0:
                    labels.append([2, rect, _pitch_name(int(pitch)), Color("#8A8577")])
    # Names on the white keys, most important first; a name that would
    # touch one already drawn is left out rather than overlapping it.
    labels.sort_custom(func(a, b): return int(a[0]) < int(b[0]))
    var taken: Array[Rect2] = []
    var font_size := _ui_font(10)
    for entry in labels:
        var rect: Rect2 = entry[1]
        var text: String = entry[2]
        var text_width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
        var box := Rect2(rect.get_center().x - text_width / 2 - 1, rect.end.y - 6 - font_size,
            text_width + 2, font_size + 2)
        if taken.any(func(other: Rect2): return other.intersects(box)):
            continue
        taken.append(box)
        draw_string(font, Vector2(box.position.x + 1, rect.end.y - 6), text,
            HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, entry[3])
    for index in range(1, _registers.size()):
        var register_rect: Rect2 = _registers[index].rect
        var center := Vector2(register_rect.position.x - REGISTER_GAP / 2, register_rect.get_center().y)
        draw_line(center + Vector2(-3, -6), center + Vector2(1, -1), Design.SLATE, 1, true)
        draw_line(center + Vector2(-1, 1), center + Vector2(3, 6), Design.SLATE, 1, true)
