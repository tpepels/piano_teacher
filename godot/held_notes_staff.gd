extends Control
## The keys held on the piano right now, drawn as whole notes on a small
## grand staff. Nothing else: no history, no rhythm, no key signature.
## Black keys are spelled with sharps, or flats in a flat key.

const Design = preload("res://practice_theme.gd")
const HEAD_SPACES := 1.7   # width of a whole notehead, in staff spaces
const MIDDLE_C := 28       # diatonic step number of C4

## Verovio glyph atlas of the score; until it loads only lines are drawn.
var glyphs
var ui_scale := 1.0
var _held: Array = []
var _flats := false

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    name = "HeldNotesStaff"
    set_ui_scale(1.0)

func set_ui_scale(value: float) -> void:
    ui_scale = value
    custom_minimum_size.x = 112.0 * value
    queue_redraw()

func present(held: Array, key_fifths: int, atlas) -> void:
    var pitches: Array = []
    for value in held:
        var pitch := int(value)
        if pitch >= 21 and pitch <= 108 and not pitches.has(pitch):
            pitches.append(pitch)
    pitches.sort()
    var flats := key_fifths < 0
    var ready: bool = atlas != null and atlas.textures.has("clef_g")
    var had: bool = glyphs != null and glyphs.textures.has("clef_g")
    if pitches == _held and flats == _flats and ready == had:
        return
    _held = pitches
    _flats = flats
    glyphs = atlas
    queue_redraw()

## Diatonic step (C4 = 28) and accidental (-1, 0, 1) of a key.
func _spell(pitch: int) -> Vector2i:
    var sharp_steps := [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
    var flat_steps := [0, 1, 1, 2, 2, 3, 4, 4, 5, 5, 6, 6]
    var pc := posmod(pitch, 12)
    var black := pc in [1, 3, 6, 8, 10]
    var step: int = (flat_steps if _flats else sharp_steps)[pc]
    var octave := floori(float(pitch) / 12.0) - 1
    return Vector2i(octave * 7 + step, (-1 if _flats else 1) if black else 0)

func _draw() -> void:
    var notes: Array = []
    var low := 14    # two ledger lines below the bass staff
    var high := 42   # two ledger lines above the treble staff
    for pitch in _held:
        var spelled := _spell(int(pitch))
        notes.append({"pitch": pitch, "step": spelled.x, "accidental": spelled.y})
        low = mini(low, spelled.x - 1)
        high = maxi(high, spelled.x + 1)
    var half := (size.y - 4.0) / float(high - low)   # one diatonic step
    var gap := half * 2.0                             # one staff space
    var y := func(step: int) -> float: return 2.0 + float(high - step) * half
    # The staff is only as wide as it needs and sits at the right edge.
    var right := size.x - 2.0 * ui_scale
    var left := maxf(2.0, right - gap * 11.5)
    var line_ink := Color(Design.STAFF_INK, .78)
    var ink := Design.STAFF_INK
    var width := maxf(1.0, gap * .09)
    for staff in [[30, 38], [18, 26]]:
        for step in range(staff[0], staff[1] + 1, 2):
            draw_line(Vector2(left, y.call(step)), Vector2(right, y.call(step)), line_ink, width, true)
    draw_line(Vector2(left, y.call(38)), Vector2(left, y.call(18)), line_ink, width * 1.4, true)
    var ready: bool = glyphs != null and glyphs.textures.has("clef_g")
    if ready:
        glyphs.paint(self, "clef_g", left + gap * 1.6, y.call(32), gap, Color(ink, .9), true)
        glyphs.paint(self, "clef_f", left + gap * 1.6, y.call(24), gap, Color(ink, .9), true)
    if notes.is_empty():
        return
    # Notes a step apart in a chord sit on either side of a shared stem
    # position, as engraved; accidentals step left when they would collide.
    var head := gap * HEAD_SPACES
    var x := left + gap * 7.6
    var previous_step := -100
    var previous_shifted := false
    var accidental_columns: Array = []
    for note in notes:
        var step: int = note.step
        var shifted := step - previous_step == 1 and not previous_shifted
        previous_step = step
        previous_shifted = shifted
        var center := x + (head * .92 if shifted else 0.0)
        var treble := int(note.pitch) >= 60
        var ledgers: Array = []
        if treble and step <= MIDDLE_C:
            ledgers = range(MIDDLE_C, step - 1, -2)
        elif treble and step >= 40:
            ledgers = range(40, step + 1, 2)
        elif not treble and step >= MIDDLE_C:
            ledgers = range(MIDDLE_C, step + 1, 2)
        elif not treble and step <= 16:
            ledgers = range(16, step - 1, -2)
        for ledger in ledgers:
            draw_line(Vector2(center - head * .5 - gap * .35, y.call(ledger)),
                Vector2(center + head * .5 + gap * .35, y.call(ledger)), line_ink, width * 1.3, true)
        if ready:
            glyphs.paint(self, "head_whole", center, y.call(step), gap, ink, true)
        else:
            draw_circle(Vector2(center, y.call(step)), gap * .5, ink)
        if int(note.accidental) != 0:
            var column := 0
            while accidental_columns.any(func(used): return used.column == column and absi(used.step - step) < 6):
                column += 1
            accidental_columns.append({"column": column, "step": step})
            var ax := x - head * .5 - gap * (.75 + 1.1 * column)
            var name := "acc_flat" if int(note.accidental) < 0 else "acc_sharp"
            if ready:
                glyphs.paint(self, name, ax, y.call(step), gap, ink, true)
