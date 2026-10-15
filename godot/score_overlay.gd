extends Control

const Design := preload("res://practice_theme.gd")

var cursor: Dictionary = {}
var showing := false
var transport_active := false
var guided_active := false
var image_size := Vector2.ZERO
var marks: Array = []
var hit_pulses: Array = []
var active_page := -1
var crop_origin := Vector2.ZERO
var crop_size := Vector2.ONE
var lead_first: Dictionary = {}
var lead_width_px := 0.0
var lead_staff_lines: Array = []
var lead_beats := 0.0
var lead_meter: Array = [4, 4]
var preparation_clefs: Dictionary = {}
var _symbols: Dictionary = {}


func load_symbols(raw: Dictionary) -> void:
    _symbols.clear()
    for name in raw:
        if typeof(raw[name]) != TYPE_DICTIONARY:
            continue
        var source: Dictionary = raw[name]
        var values: Array = source.get("bounds", [])
        if values.size() != 4:
            continue
        var bounds := Rect2(float(values[0]), float(values[1]),
                           float(values[2]), float(values[3]))
        var units: float = float(source.get("units_per_space", 250.0))
        if bounds.size.x <= 0.0 or bounds.size.y <= 0.0 or units <= 0.0:
            continue
        var picture := Image.new()
        # These standalone SVGs contain paths only, with the same font metrics
        # as the score. A small high resolution texture keeps their curves crisp.
        var error: Error = picture.load_svg_from_buffer(
            str(source.get("svg", "")).to_utf8_buffer(), 128.0 / bounds.size.y)
        if error != OK or picture.is_empty():
            continue
        _symbols[str(name)] = {"texture": ImageTexture.create_from_image(picture),
            "bounds": bounds, "units_per_space": units}
    queue_redraw()


func _sheet_xy(x: float, y: float) -> Vector2:
    # Preserve Verovio notehead coordinates after cropping and scrolling.
    return size * ((Vector2(x, y) - crop_origin) / crop_size)


func _draw_symbol(name: String, origin: Vector2, staff_gap: float) -> void:
    if not _symbols.has(name):
        return
    var symbol: Dictionary = _symbols[name]
    var scale: float = staff_gap / float(symbol.units_per_space)
    var bounds: Rect2 = symbol.bounds
    draw_texture_rect(symbol.texture,
        Rect2(origin + bounds.position * scale, bounds.size * scale), false)


func _draw_meter(center_x: float, staff_top: float, staff_gap: float) -> void:
    if lead_meter.size() < 2:
        return
    var font: Font = ThemeDB.fallback_font
    var font_size: int = maxi(12, int(round(staff_gap * 2.0)))
    var baseline_offset: float = (font.get_ascent(font_size) - font.get_descent(font_size)) * .5
    for index in range(2):
        var text: String = str(int(lead_meter[index]))
        var text_width: float = font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
        var center_y: float = staff_top + staff_gap * float(1 + index * 2)
        draw_string(font, Vector2(center_x - text_width * .5, center_y + baseline_offset),
            text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size, Design.STONE)


func _draw_preparation() -> void:
    if not showing or lead_width_px <= 2.0 or lead_first.is_empty():
        return
    var first_x: float = _sheet_xy(float(lead_first.get("x", 0.0)), 0.0).x
    var top: float = _sheet_xy(0.0, float(lead_first.get("top", 0.0))).y
    var bottom: float = _sheet_xy(0.0, float(lead_first.get("bottom", 1.0))).y
    var lines: Array[float] = []
    for staff_y in lead_staff_lines:
        lines.append(_sheet_xy(0.0, float(staff_y)).y)
    var gap: float = lines[1] - lines[0] if lines.size() >= 2 else 12.0
    if gap <= 0.0:
        return
    var left: float = first_x - lead_width_px
    var margin_left: float = left - gap * 9.0
    var ink_left: float = _sheet_xy(float(lead_first.get("ink_left", lead_first.get("x", 0.0))), 0.0).x
    var mask_end: float = minf(first_x, ink_left) - 1.0
    # The preparation measure stays on the moving canvas after the downbeat.
    # Preserve the complete opening accidental/ledger ink, not only its
    # notehead. These bounds come from the actual engraved source glyphs.
    draw_rect(Rect2(margin_left, top - 16.0, maxf(0.0, mask_end - margin_left),
                    bottom - top + 32.0), Design.PANEL, true)
    var ink := Color(Design.SLATE, .52)
    for sy in lines:
        draw_line(Vector2(margin_left, sy), Vector2(first_x, sy), ink, 1.1, true)
    if lines.size() < 10:
        return
    _draw_preparation_clef("right", left - gap * 7.0, lines, 0, gap)
    _draw_preparation_clef("left", left - gap * 7.0, lines, 5, gap)
    _draw_meter(left - gap * 2.7, lines[0], gap)
    _draw_meter(left - gap * 2.7, lines[5], gap)
    if lead_beats <= 0.0:
        return
    var beat_width: float = lead_width_px / lead_beats
    for index in range(ceili(lead_beats)):
        var remaining: float = lead_beats - float(index)
        var name := "quarter_rest" if remaining >= .999 else "eighth_rest"
        var x: float = first_x + (-lead_beats + float(index)) * beat_width
        _draw_symbol(name, Vector2(x, lines[2]), gap)
        _draw_symbol(name, Vector2(x, lines[7]), gap)


func _draw_preparation_clef(hand: String, x: float, lines: Array[float], first_line: int, gap: float) -> void:
    var fallback := {"sign":"G", "line":2} if hand == "right" else {"sign":"F", "line":4}
    var clef: Dictionary = preparation_clefs.get(hand, fallback)
    var sign: String = str(clef.get("sign", fallback["sign"]))
    var line: int = clampi(int(clef.get("line", fallback["line"])), 1, 5)
    _draw_symbol("bass" if sign == "F" else "treble", Vector2(x, lines[first_line + 5 - line]), gap)
    var octaves: int = int(clef.get("octave_change", 0))
    if octaves != 0:
        var y: float = lines[first_line] - gap * 1.1 if octaves > 0 else lines[first_line + 4] + gap * 2.1
        draw_string(ThemeDB.fallback_font, Vector2(x + gap * .35, y), "8" if absi(octaves) == 1 else "15", HORIZONTAL_ALIGNMENT_LEFT, -1, maxi(9, roundi(gap * 1.4)), Design.STONE)


func _draw() -> void:
    if image_size.x <= 0.0 or image_size.y <= 0.0:
        return
    _draw_preparation()
    # A faint green ring confirms correct notes; stronger colour markers
    # distinguish mistakes without altering the underlying engraving.
    var palette := {
        "correct": Color("#4A987B"), "assisted": Color("#C8AC7C"), "expected": Design.TEAL, "wrong": Color("#BB4A4A"),
        "missed": Color("#BB4A4A"), "extra": Color("#BB4A4A"),
        "early": Color("#BA852B"), "late": Color("#BA852B"),
        "short": Color("#8660AF"), "long": Color("#8660AF")
    }
    var labels := {"wrong":"×", "missed":"!", "extra":"+",
                   "early":"←", "late":"→", "short":"−", "long":"+"}
    for marker in marks:
        if int(marker.get("page", -1)) != active_page:
            continue
        var status: String = str(marker.get("status", ""))
        var color: Color = palette.get(status, Color("#BB4A4A"))
        var center: Vector2 = _sheet_xy(float(marker.get("x", 0.0)), float(marker.get("y", 0.0)))
        if status == "expected":
            draw_arc(center, 12.0, 0.0, TAU, 24, color, 2.5, true)
            draw_circle(center + Vector2(0, -18), 3.0, color)
        elif status == "assisted":
            draw_arc(center, 10.0, 0.0, TAU, 24, color, 2.0, true)
            draw_string(ThemeDB.fallback_font, center + Vector2(12, -9), "?", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, color)
        elif status == "correct":
            draw_arc(center, 9.0, 0.0, TAU, 20, Color(color, .37), 1.5, true)
            draw_string(ThemeDB.fallback_font, center + Vector2(12, -9), "✓", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, color)
        else:
            var radius := 12.0 if status == "missed" else 10.0
            draw_arc(center, radius, 0.0, TAU, 24, color, 2.5, true)
            var symbol: String = str(labels.get(status, "!"))
            var font: Font = ThemeDB.fallback_font
            draw_string(font, center + Vector2(12, -9), symbol, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, color)
            if status == "extra":
                draw_string(font, center + Vector2(12, 5), str(marker.get("label", "")), HORIZONTAL_ALIGNMENT_LEFT, -1, 11, color)
    # A real physical attack produces a prominent short-lived pulse at the
    # mapped engraved notehead. These pulses are provisional and distinct from
    # the authoritative assessment marks rendered above.
    var ticks: int = Time.get_ticks_msec()
    for pulse in hit_pulses:
        if int(pulse.get("page", -1)) != active_page:
            continue
        var alpha: float = clampf(float(int(pulse.get("until_ms", 0)) - ticks) / 700.0, 0.0, 1.0)
        if alpha <= 0.0:
            continue
        var status: String = str(pulse.get("status", "heard"))
        var color: Color = Color("#63D9AE") if status == "on_time" else Color("#D6AC61")
        var center := _sheet_xy(float(pulse.get("x", 0.0)), float(pulse.get("y", 0.0)))
        draw_circle(center, 15.0, Color(color, alpha * .17))
        draw_arc(center, 14.0 + (1.0-alpha) * 12.0, 0.0, TAU, 32, Color(color, alpha), 4.0, true)

    if showing and not guided_active and not cursor.is_empty() and int(cursor.get("page", -1)) == active_page:
        var x: float = float(cursor.get("x", 0.0))
        var top: float = float(cursor.get("top", 0.0))
        var bottom: float = float(cursor.get("bottom", 1.0))
        var start: Vector2 = _sheet_xy(x, top)
        var end: Vector2 = _sheet_xy(x, bottom)
        # The timing rule follows the clock's BPM, including silent beats.
        var cyan := Design.TEAL if transport_active else Design.SAGE
        draw_line(start, end, Color(cyan, .09), 16.0, true)
        draw_line(start, end, Color(cyan, .18), 7.0, true)
        draw_line(start, end, cyan, 2.5, true)
