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
    custom_minimum_size.y = (88 if get_viewport_rect().size.y < 720 else 100) * ui_scale
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

func update_live(expected_pitches: Array, held_pitches: Array, events: Array, connected: bool) -> void:
    # Physical keyboard display is active during timed practice, independently
    # of the Learn-mode hint keyboard. No preview marker awards score credit.
    var recent: Array = []
    for event in events:
        if event is Dictionary and float(event.get("age", 999.0)) < .8:
            recent.append([event.get("pitch", -1), event.get("status", "heard")])
    var last: Dictionary = events[-1] if not events.is_empty() else {}
    var presentation := {"live":true, "expected":expected_pitches, "held":held_pitches,
        "recent":recent, "last":[last.get("pitch", -1), last.get("status", "heard"),
            float(last.get("age", 999.0)) < .8], "connected":connected}
    # Ages change on every poll, but the key colors/caption change only when
    # a note arrives, is released, or crosses the existing .8s expiry boundary.
    if presentation == _presentation:
        return
    _presentation = presentation.duplicate(true)
    _live_mode = true
    _expected.clear()
    _heard.clear()
    _pressed.clear()
    for raw in expected_pitches:
        var pitch := int(raw)
        if pitch >= 21 and pitch <= 108:
            _expected[pitch] = _pitch_name(pitch)
    for raw in held_pitches:
        var pitch := int(raw)
        if pitch >= 21 and pitch <= 108:
            _heard[pitch] = true
            _pressed[pitch] = "heard"
    _last_pitch = -1
    _last_status = ""
    _last_age = 999.0
    if not events.is_empty():
        # Keep independent colors for chord notes, not just the final attack.
        for event in events:
            if not event is Dictionary or float(event.get("age", 999.0)) >= 0.8:
                continue
            var played_pitch: int = int(event.get("pitch", -1))
            if played_pitch >= 21 and played_pitch <= 108:
                _pressed[played_pitch] = str(event.get("status", "heard"))
        _last_pitch = int(last.get("pitch", -1))
        _last_status = str(last.get("status", "heard"))
        _last_age = float(last.get("age", 999.0))
    visible = connected
    if not is_node_ready():
        await ready
    var pitches: Array = _expected.keys()
    for pitch in _heard:
        if not pitches.has(pitch):
            pitches.append(pitch)
    if _last_age < 0.8 and _last_pitch >= 21 and _last_pitch <= 108 and not pitches.has(_last_pitch):
        pitches.append(_last_pitch)
    if pitches.is_empty():
        pitches = [48, 72]
    pitches.sort()
    _registers.clear()
    var groups: Array = []
    _split_registers(pitches, groups)
    for group in groups:
        _registers.append(_context_range(group, groups.size() == 1))
    var names: PackedStringArray = []
    for pitch in _expected:
        names.append(_pitch_name(int(pitch)))
    names.sort()
    _expected_label.text = "NEXT  " + (" + ".join(names) if not names.is_empty() else "Follow the score")
    var status_labels := {
        "heard": "Key received", "count_in": "Wait for the first beat",
        "on_time": "On time · keep holding", "early": "Early note",
        "late": "Late note", "unexpected": "Unexpected note"
    }
    _heard_label.text = (
        "%s  %s" % [str(status_labels.get(_last_status, "Key received")), _pitch_name(_last_pitch)]
        if _last_age < 0.8 and _last_pitch >= 21 and _last_pitch <= 108
        else ("%d key(s) held" % _heard.size() if not _heard.is_empty() else "Play a note")
    )
    _heard_label.add_theme_color_override("font_color",
        Color("#DA8580") if _last_status == "unexpected" and _last_age < 0.8
        else Color("#D5AD66") if _last_status in ["early", "late", "count_in"] and _last_age < 0.8
        else Color("#66D3AA") if _last_age < 0.8 else Design.SLATE)
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
    _expected_label.position = Vector2.ZERO
    _expected_label.size = Vector2(maxf(0, size.x * .58 - 8), 20 * ui_scale)
    _heard_label.position = Vector2(size.x * .58, 0)
    _heard_label.size = Vector2(maxf(0, size.x * .42), 20 * ui_scale)
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
    var top := 28.0 * ui_scale
    var height := maxf(1, size.y - top - 2 * ui_scale)
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
            if _live_mode and _pressed.has(pitch):
                var status: String = str(_pressed[pitch])
                fill = Color("#BB514D") if status == "unexpected" else Color("#C68D4D") if status in ["early", "late", "count_in"] else Color("#4AA989")
            draw_style_box(Design.surface(fill, 2), rect)
            if bool(key.expected):
                draw_rect(rect.grow(-1), EXPECTED, false, 1.5)
                var marker := Vector2(rect.get_center().x, rect.position.y + 8 if black else rect.end.y - 24)
                draw_colored_polygon(PackedVector2Array([marker + Vector2(-4, 0), marker + Vector2(4, 0),
                    marker + Vector2(0, 5)]), EXPECTED)
            if bool(key.heard) and not _live_mode:
                # A round slate marker survives alongside the triangular expected marker on the same key.
                var heard_at := Vector2(rect.end.x - 6, rect.position.y + 8 if black else rect.end.y - 14)
                draw_circle(heard_at, 3, Design.SLATE)
                draw_arc(heard_at, 4.5, 0, TAU, 16, Design.SLATE, 1, true)
            var label := ""
            if bool(key.expected):
                label = str(_expected[pitch])
            elif bool(key.heard) or (_live_mode and _pressed.has(pitch)) or int(pitch) % 12 == 0:
                label = _pitch_name(int(pitch))
            if not label.is_empty():
                var font_size := _ui_font(11 if black else 12)
                var text_width := font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                var position := Vector2(rect.get_center().x - text_width / 2, rect.end.y - 4)
                draw_string(font, position, label, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size,
                    EXPECTED if bool(key.expected) else Design.STONE)
    for index in range(1, _registers.size()):
        var register_rect: Rect2 = _registers[index].rect
        var center := Vector2(register_rect.position.x - REGISTER_GAP / 2, register_rect.get_center().y)
        draw_line(center + Vector2(-3, -6), center + Vector2(1, -1), Design.SLATE, 1, true)
        draw_line(center + Vector2(-1, 1), center + Vector2(3, 6), Design.SLATE, 1, true)
