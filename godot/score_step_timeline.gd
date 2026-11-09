extends Control
## Small music-axis markers. Lesson steps advance along the score rather than
## being presented as replacement pages or interrupting score movement.
const Design := preload("res://practice_theme.gd")
const ScoreView := preload("res://notation/shared/view_base.gd")
const FUTURE := Design.SECONDARY_INK
var _loaded := false
var _step := 0
var _total := 0
var _phase := "ready"
var _label := ""
var _next_label := ""
var _current_start := 0.0
var _next_start := INF
var _beat := 0.0
var _current_beat := 0.0
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
    return width*ScoreView.PLAYHEAD_FRACTION + (at-visual_beat)*density

func present(state: Dictionary, visual_beat: float,
        current_origin: float, next_origin: float = INF,
        next_label: String = "", next_density: float = NAN,
        current_visual_beat: float = NAN) -> void:
    var current_camera: float = current_visual_beat if is_finite(current_visual_beat) else visual_beat
    var upcoming_density: float = next_density if is_finite(next_density) and next_density > 0.0 else _density
    var next_phase: String = str(state.get("phase","ready"))
    var presented_label: String = "%s · %s" % [
        str(state.get("hand","both")).capitalize(),
        str(state.get("stage_label",""))]
    var changed: bool = (_loaded != bool(state.get("loaded",false)) or \
            _step != int(state.get("lesson_step",0)) or \
            _total != int(state.get("lesson_steps",0)) or \
            _phase != next_phase or \
            _label != presented_label or \
            _next_label != next_label or \
            absf(_next_density-upcoming_density) > .001 or \
            absf(_current_start-current_origin) > .001 or \
            _next_start != next_origin or \
            absf(_current_beat-current_camera) > .0001 or \
            absf(_beat-visual_beat) > .0001)
    _loaded = bool(state.get("loaded",false))
    _step = int(state.get("lesson_step",0))
    _total = int(state.get("lesson_steps",0))
    _phase = next_phase
    _label = presented_label
    _next_label = next_label
    _next_density = upcoming_density
    _current_start = current_origin
    _next_start = next_origin
    _beat = visual_beat
    _current_beat = current_camera
    if changed:
        queue_redraw()

func set_density(pixels: float) -> void:
    if pixels > 0 and absf(_density-pixels) > .001:
        _density = pixels
        queue_redraw()

# Keep short step labels on the musical axis. Full stage descriptions already
# appear in the Practice header; long floating text must not cover the score.
# Hide the next label when two markers would occupy the same text region.
static func markers_separated(current_x: float, next_x: float) -> bool:
    return not is_finite(current_x) or next_x >= current_x + 168.0

func _marker(at: float, tint: Color, density: float,
        visual_beat: float) -> void:
    if not is_finite(at):
        return
    var x: float = marker_x(at,visual_beat,density,size.x)
    if x < -10.0 or x > size.x-10.0:
        return
    # The source-aligned stage entry remains discoverable without repeating
    # lesson names above the score. A subtle pin replaces its old text card.
    draw_line(Vector2(x,5),Vector2(x,20),Color(tint,.53),1.2,true)
    draw_circle(Vector2(x,6),2.4,Color(tint,.88))

func _draw() -> void:
    if not _loaded or _step <= 0:
        return
    var current_x := marker_x(_current_start,_current_beat,_density,size.x) if is_finite(_current_start) else -INF
    var next_x := marker_x(_next_start,_beat,_next_density,size.x) if is_finite(_next_start) else INF
    var current_visible := is_finite(current_x) and current_x >= -10.0 and current_x < size.x-10.0
    # The fixed glowing playhead already marks the current step. Do not
    # duplicate it with a tiny disconnected pin at the top of the stage.
    # Future preloaded steps still retain their on-score markers below.
    # A preloaded next stage can project directly onto the current marker.
    # Its note ink remains visible; only the duplicate caption is suppressed.
    # Keep future-stage pins off the fixed playhead. A pin projected only a
    # few pixels from the glowing strike looked like a stray dot above it.
    var playhead_x: float = size.x * ScoreView.PLAYHEAD_FRACTION
    if current_visible and current_x >= playhead_x + 110.0:
        _marker(_current_start,Design.STONE,_density,_current_beat)
    if is_finite(next_x) and next_x >= playhead_x + 110.0 and (
            next_x < size.x - 10.0) and (
            not current_visible or markers_separated(current_x,next_x)):
        _marker(_next_start,FUTURE,_next_density,_beat)
