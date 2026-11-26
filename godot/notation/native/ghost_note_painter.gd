extends RefCounted
## Paint authoritative unmatched MIDI pitches inside their existing source strip.
## Spelling and clef choose ink placement only; no target or grade is inferred.
const Geometry := preload("res://notation/native/geometry.gd")
const RED := Color("#F17978")
const WARMUP := preload("res://practice_theme.gd").SECONDARY_INK

static func paint(canvas: CanvasItem, painter, ghost: Dictionary, screen_x: float = NAN) -> void:
    var age: float = maxf(0.0,float(Time.get_ticks_msec()-int(ghost.get("shown_ms",Time.get_ticks_msec()))))
    var life: float = maxf(1.0,float(ghost.get("lifetime_ms",600)))
    if age >= life:
        return
    var alpha: float = 1.0-smoothstep(0.0,life,age)
    var color := Color(WARMUP if bool(ghost.get("warmup",false)) else RED,alpha)
    var position := pitch_position(painter,ghost)
    if position.is_empty():
        return
    var gap: float = painter.staff_gap()
    var step: int = int(position["step"])
    var bottom: float = float(position["bottom"])
    var y: float = float(position["y"])
    var x: float = screen_x if is_finite(screen_x) else painter.timeline.x_at_beat(float(ghost["beat"]))
    painter.engraving.symbols.paint_ledger(canvas,null,x,y,step,bottom,gap,color)
    painter.glyphs.paint_note(canvas,"quarter",step < 4,x,y,gap,color)
    # Only deviations from the printed signature need an accidental.
    var accidental: String = str(position["accidental"])
    if not accidental.is_empty():
        painter.glyphs.paint(canvas,accidental,x-gap*1.65,y,gap,color,true)

## Shared vertical projection of the actual MIDI pitch. Both fading notes
## and attack dots use identical key, clef and ledger-line geometry.
static func pitch_position(painter, played: Dictionary) -> Dictionary:
    var layout = painter.layout
    var gap: float = painter.staff_gap()
    var beat: float = float(played["beat"])
    var pitch: int = int(played["pitch"])
    if pitch < 0 or pitch > 127 or not is_finite(beat):
        return {}
    var staff: String = str(played.get("staff","right"))
    if staff not in ["right","left"]:
        staff = "right"
    var measure: Dictionary = painter.timeline.measures[0] if not painter.timeline.measures.is_empty() else {}
    # Count-in belongs to the incoming written key, not hidden neighbour ink.
    for candidate in painter.timeline.measures:
        if float(candidate["start_beat"]) <= beat:
            measure = candidate
        else:
            break
    var fifths: int = int(measure.get("keys",{}).get(staff,0))
    var spelling: Dictionary = Geometry.key_signature_spelling(pitch,fifths)
    if spelling.is_empty():
        return {}
    var step: int = Geometry.staff_step(spelling,layout.clef_for(staff,measure))
    var bottom: float = layout.staff_center(staff)+gap*2.0
    return {"step":step,"bottom":bottom,"y":Geometry.note_y(step,bottom,gap),
        "accidental":spelling["accidental"]}
