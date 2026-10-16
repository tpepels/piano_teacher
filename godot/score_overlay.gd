extends Control

const Design := preload("res://practice_theme.gd")
const Ink := preload("res://notehead_ink.gd")
const Effects := preload("res://note_reactions.gd")

var cursor: Dictionary = {}
var showing := false
var transport_active := false
var onset_until_ms := 0
var guided_active := false
var image_size := Vector2.ZERO
var marks: Array = []
var next_chord: Array = []
var wrong_ghosts: Array = []
var hit_pulses: Array = []
var preview_pulses: Array = []
var staff_gap_fraction := 0.02
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
    var lines: Array[float] = []
    for staff_y in lead_staff_lines:
        lines.append(_sheet_xy(0.0, float(staff_y)).y)
    var gap: float = lines[1] - lines[0] if lines.size() >= 2 else 12.0
    if gap <= 0.0:
        return
    var left: float = first_x - lead_width_px
    var margin_left: float = left - gap * 9.0
    # No opaque starting rectangle. The old mask covered the actual score
    # as it scrolled underneath and looked like a dark square that lagged
    # behind the timing line. All preparation ink is transparent.
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
    # Noteheads are genuine Verovio positions. Use thin ellipses shaped to
    # the engraved glyph, never opaque blobs, checkmarks or floating labels.
    var gap: float = maxf(5.0, staff_gap_fraction * size.y)
    var radii: Vector2 = Ink.radii(gap)
    var judged: Dictionary = {}
    # The scored attack wins visually over the warm pre-attack cue. Polling
    # may still reference the same "next" chord until the next HTTP tick.
    for hit in hit_pulses:
        var hit_id: String = str(hit.get("note_id", ""))
        if not hit_id.is_empty():
            judged[hit_id] = true
    for marker in marks:
        if not marker is Dictionary:
            continue
        var note_id: String = str(marker.get("note_id", marker.get("id", "")))
        var source_id: String = str(marker.get("source_id", ""))
        if not note_id.is_empty():
            judged[note_id] = true
        if not source_id.is_empty():
            judged[source_id] = true

    # Indicate only the next unassessed note/chord. The halo does not flare
    # merely because the clock arrived at the note; that is MIDI-triggered.
    for note in next_chord:
        if int(note.get("page", -1)) != active_page:
            continue
        if judged.has(str(note.get("id", ""))) or judged.has(str(note.get("source_id", ""))):
            continue
        var focus: Vector2 = _sheet_xy(float(note.get("x", 0.0)), float(note.get("y", 0.0)))
        var strength: float = clampf(float(note.get("emphasis", 0.0)), 0.0, 1.0)
        var breathe: float = .5 + .5 * sin(float(Time.get_ticks_msec()) * .0038)
        # Next-note anticipation is warm ivory/gold, deliberately
        # distinct from teal (a genuinely graded successful attack).
        # Two outline passes surround the exact Verovio notehead rather
        # than painting over its accidentals or filling in its pitch.
        var extent: Vector2 = radii * (1.55 + .12 * breathe)
        var anticipation := Color("#F6D5A0")
        draw_polyline(Ink.ellipse(focus, extent.x * 1.16, extent.y * 1.16),
            Color(anticipation, .13 + .09 * breathe + .05 * strength), 5.0, true)
        draw_polyline(Ink.ellipse(focus, extent.x, extent.y),
            Color(anticipation, .65 + .19 * strength + .10 * breathe), 2.15, true)

    for marker in marks:
        if int(marker.get("page", -1)) != active_page:
            continue
        var status: String = str(marker.get("status", ""))
        # Correct timing is shown as a transient pulse behind the noteheads,
        # not a permanent checkmark drawn over the engraved score.
        if status in ["correct", "on_time"]:
            continue
        var tone: Color = Color("#F0807A") if status in ["wrong", "missed", "extra"] else (
            Color("#E7B776") if status in ["early", "late", "short", "long", "assisted"] else
            Color("#91E9CA"))
        var focus: Vector2 = _sheet_xy(float(marker.get("x", 0.0)), float(marker.get("y", 0.0)))
        var extent: Vector2 = radii * (1.17 if status in ["wrong", "missed", "extra"] else 1.12)
        draw_polyline(Ink.ellipse(focus, extent.x, extent.y),
            tone, 1.7 if status in ["wrong", "missed"] else 1.4, true)

    # An unexpected physical note briefly outlines the associated expected
    # notehead. Do not draw another simulated note or the word WRONG on staff.
    var now_ms: int = Time.get_ticks_msec()
    for event in wrong_ghosts:
        if int(event.get("page", -1)) != active_page:
            continue
        var remaining: float = clampf(
            float(int(event.get("until_ms", 0)) - now_ms) /
                float(maxi(1, int(event.get("duration_ms", 420)))), 0.0, 1.0)
        if remaining <= 0.0:
            continue
        var center: Vector2 = _sheet_xy(float(event.get("x", 0.0)), float(event.get("y", 0.0)))
        var extent: Vector2 = radii * 1.19
        draw_polyline(Ink.ellipse(center, extent.x, extent.y),
            Color("#F0807A", remaining * .92), 1.8, true)

    # Bold, outside-the-ink notehead flash. The lower layer carries the
    # sixteen-particle burst; this bright rim stays readable above even
    # opaque staff ink. It never triggers merely on playhead crossing.
    for hit in hit_pulses + preview_pulses:
        if int(hit.get("page", -1)) != active_page:
            continue
        var duration: float = maxf(1.0, float(hit.get("duration_ms", 450)))
        var remaining: float = clampf(float(int(hit.get("until_ms", 0)) - now_ms) /
            duration, 0.0, 1.0)
        if remaining <= 0.0:
            continue
        var progress: float = 1.0 - remaining
        var attack: float = 1.0 - clampf(progress * 3.8, 0.0, 1.0)
        var focus: Vector2 = _sheet_xy(float(hit.get("x", 0.0)),
            float(hit.get("y", 0.0)))
        var tone: Color = (Color("#9DC8FF") if str(hit.get("status", "")) == "preview"
            else Color("#A0FFDA") if str(hit.get("status", "")) == "on_time"
            else Color("#FFD49A"))
        var extent: Vector2 = radii * (1.55 + progress * 1.65)
        draw_polyline(Ink.ellipse(focus, extent.x * 1.27,
            extent.y * 1.27), Color(tone, (.12 + .24 * attack) * remaining),
            4.0, true)
        draw_polyline(Ink.ellipse(focus, extent.x, extent.y),
            Color(tone, (.90 + .10 * attack) * remaining),
            2.75, true)
        # Front-layer sparks: the raster score otherwise hides most of the
        # existing particles drawn behind opaque engraved PNG tiles. These
        # start well outside the notehead, so the pitch remains readable.
        # Preview uses blue; assessed success uses bright mint.
        # Eight distinct comet trails, not sixteen equally prominent
        # spokes. Ease outward quickly, linger, then dissolve. This keeps
        # the notehead readable and halves foreground particle overdraw.
        var travel: float = 1.0 - pow(remaining, 2.4)
        for particle in range(0, Effects.PARTICLE_COUNT, 2):
            var endpoint: Vector2 = Effects.particle_endpoint(
                focus, gap, travel, particle)
            var radial: Vector2 = (endpoint - focus).normalized()
            var brightness: float = pow(remaining, 1.45)
            var tip_radius: float = maxf(1.1, gap * .095) * brightness
            draw_line(endpoint - radial * gap * (.34 + .18 * progress),
                endpoint, Color(tone, .82 * brightness),
                1.55 + .25 * attack, true)
            draw_circle(endpoint, tip_radius, Color(tone, .94 * brightness))
        # Short four-point glint outside the ellipse: a much more visible
        # confirmation than the old hairline green circle.
        if attack > .0:
            for direction in [Vector2.LEFT, Vector2.RIGHT,
                    Vector2.UP, Vector2.DOWN]:
                var edge: Vector2 = focus + direction * gap * 1.5
                draw_line(edge, edge + direction * gap * (.5 + .35 * progress),
                    Color(tone, attack * .84), 2.0, true)

    # The particle glow is drawn by NoteReactions *behind* the actual
    # raster tiles. Nothing here paints over correct notes.
    if showing and not guided_active and not cursor.is_empty() and int(cursor.get("page", -1)) == active_page:
        var x: float = float(cursor.get("x", 0.0))
        var top: float = float(cursor.get("top", 0.0))
        var bottom: float = float(cursor.get("bottom", 1.0))
        var start: Vector2 = _sheet_xy(x, top)
        var end: Vector2 = _sheet_xy(x, bottom)
        # A stable vertical strike line and two compact edge pointers make
        # the note arrival legible without painting a glow over the pitches.
        # The note itself only reacts to the physical MIDI attack.
        var cyan := Design.TEAL if transport_active else Design.SAGE
        # The timing line reacts at the *musical onset*, not the notehead.
        # Actual notehead illumination remains MIDI-triggered only.
        var onset: float = clampf(float(onset_until_ms - Time.get_ticks_msec()) / 180.0, 0.0, 1.0)
        draw_line(start, end, Color(cyan, .15 + onset * .17),
            5.0 + onset * 4.0, true)
        draw_line(start, end, Color(cyan, .93), 1.7 + onset * .55, true)
        var marker := 7.0
        draw_colored_polygon(PackedVector2Array([
            start + Vector2(-marker, -marker * .6),
            start + Vector2(marker, -marker * .6),
            start + Vector2(0, marker * .55)]), Color(cyan, .93))
        draw_colored_polygon(PackedVector2Array([
            end + Vector2(-marker, marker * .6),
            end + Vector2(marker, marker * .6),
            end + Vector2(0, -marker * .55)]), Color(cyan, .93))
