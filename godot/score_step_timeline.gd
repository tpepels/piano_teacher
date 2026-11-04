extends Control
## Small music-axis markers. Lesson steps advance along the score rather than
## being presented as replacement pages or interrupting score movement.
const INK := Color("#B6E7D8")
const FUTURE := Color("#78C6B4")
var _loaded := false
var _step := 0
var _total := 0
var _label := ""
var _next_label := ""
var _current_start := 0.0
var _next_start := INF
var _beat := 0.0
var _density := 96.0
var _next_density := 96.0

# The marker belongs at the FIRST ENGRAVED ATTACK, not the containing barline.
# A measure can start with rests; bar-start positioning labels those rests.
# Return INF for a genuinely silent active hand, rather than putting the
# exercise title on a preparatory rest.
static func first_playable_beat(model: Dictionary, hand: String = "both") -> float:
    var earliest: float = INF
    # Printed attacks are authoritative for visual placement. MIDI grading
    # uses the same semantic beat axis but quantized tuplets may differ by a
    # few milliseconds; the label must follow the notehead itself.
    for event in model.get("notation_events", []):
        if not event is Dictionary or str(event.get("kind","")) != "note" or \
                not bool(event.get("is_attack",false)):
            continue
        if hand != "both" and str(event.get("hand",event.get("staff",""))) != hand:
            continue
        var beat: float = float(event.get("beat",INF))
        if is_finite(beat) and beat >= 0.0:
            earliest = minf(earliest,beat)
    if is_finite(earliest):
        return earliest
    # A minimal MIDI source fixture need not carry its printed symbols yet.
    # Source attacks remain real; rest-only models do not.
    for note in model.get("notes", []):
        if not note is Dictionary:
            continue
        if hand != "both" and str(note.get("hand","")) != hand:
            continue
        var beat: float = float(note.get("onset_beats",INF))
        if is_finite(beat) and beat >= 0.0:
            earliest = minf(earliest,beat)
    return earliest


# The score and each pre-engraved future stage can use different note spacing.
# Project a marker with the SAME pixels/beat as its owner renderer.
static func marker_x(at: float, visual_beat: float,
        density: float, width: float) -> float:
    return width*.42 + (at-visual_beat)*density

func present(state: Dictionary, visual_beat: float,
        current_origin: float, next_origin: float = INF,
        next_label: String = "", next_density: float = NAN) -> void:
    var upcoming_density: float = next_density if is_finite(next_density) and next_density > 0.0 else _density
    var presented_label: String = "%s · %s" % [
        str(state.get("hand","both")).capitalize(),
        str(state.get("stage_label",""))]
    var changed: bool = (_loaded != bool(state.get("loaded",false)) or \
            _step != int(state.get("lesson_step",0)) or \
            _total != int(state.get("lesson_steps",0)) or \
            _label != presented_label or \
            _next_label != next_label or \
            absf(_next_density-upcoming_density) > .001 or \
            absf(_current_start-current_origin) > .001 or \
            _next_start != next_origin or \
            absf(_beat-visual_beat) > .0001)
    _loaded = bool(state.get("loaded",false))
    _step = int(state.get("lesson_step",0))
    _total = int(state.get("lesson_steps",0))
    _label = presented_label
    _next_label = next_label
    _next_density = upcoming_density
    _current_start = current_origin
    _next_start = next_origin
    _beat = visual_beat
    if changed:
        queue_redraw()

func set_density(pixels: float) -> void:
    if pixels > 0 and absf(_density-pixels) > .001:
        _density = pixels
        queue_redraw()

func _marker(at: float, label: String, tint: Color, density: float) -> void:
    if not is_finite(at):
        return
    var x: float = marker_x(at,_beat,density,size.x)
    if x < -10.0 or x > size.x+10.0:
        return
    var font: Font = ThemeDB.fallback_font
    draw_line(Vector2(x,5),Vector2(x,29),tint,2.0,true)
    draw_rect(Rect2(x,4,4,5),tint)
    draw_string(font,Vector2(x+9,19),label,
        HORIZONTAL_ALIGNMENT_LEFT,mini(240,int(size.x-x-12)),13,tint)

func _draw() -> void:
    if not _loaded or _step <= 0:
        return
    _marker(_current_start,"%d/%d · %s" % [_step,_total,_label],INK,_density)
    _marker(_next_start,"%d/%d · %s" % [_step+1,_total,_next_label],FUTURE,_next_density)
