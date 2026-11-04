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

static func first_sounding_measure_offset(model: Dictionary, hand: String = "both") -> float:
    # Mark the beginning of the first real, note-bearing source measure,
    # not the preparatory rest preceding it. Keep the complete measure
    # boundary rather than shifting the label to the first notehead.
    var earliest: float = INF
    for candidate in model.get("notes", []):
        if not candidate is Dictionary:
            continue
        if hand != "both" and str(candidate.get("hand","")) != hand:
            continue
        var onset: float = float(candidate.get("onset_beats",INF))
        if is_finite(onset):
            earliest = minf(earliest,onset)
    if not is_finite(earliest):
        return 0.0
    for measure in model.get("measures", []):
        if measure is Dictionary and \
                earliest >= float(measure.get("start_beat",-INF)) - .0001 and \
                earliest < float(measure.get("end_beat",-INF)) + .0001:
            return float(measure.get("start_beat",0.0))
    return 0.0

func present(state: Dictionary, visual_beat: float,
        current_origin: float, next_origin: float = INF,
        next_label: String = "") -> void:
    var presented_label: String = "%s · %s" % [
        str(state.get("hand","both")).capitalize(),
        str(state.get("stage_label",""))]
    var changed: bool = (_loaded != bool(state.get("loaded",false)) or \
            _step != int(state.get("lesson_step",0)) or \
            _total != int(state.get("lesson_steps",0)) or \
            _label != presented_label or \
            _next_label != next_label or \
            absf(_current_start-current_origin) > .001 or \
            _next_start != next_origin or \
            absf(_beat-visual_beat) > .0001)
    _loaded = bool(state.get("loaded",false))
    _step = int(state.get("lesson_step",0))
    _total = int(state.get("lesson_steps",0))
    _label = presented_label
    _next_label = next_label
    _current_start = current_origin
    _next_start = next_origin
    _beat = visual_beat
    if changed:
        queue_redraw()

func set_density(pixels: float) -> void:
    if pixels > 0 and absf(_density-pixels) > .001:
        _density = pixels
        queue_redraw()

func _marker(at: float, label: String, tint: Color) -> void:
    if not is_finite(at):
        return
    var x: float = size.x*.42 + (at-_beat)*_density
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
    _marker(_current_start,"%d/%d · %s" % [_step,_total,_label],INK)
    _marker(_next_start,"%d/%d · %s" % [_step+1,_total,_next_label],FUTURE)
