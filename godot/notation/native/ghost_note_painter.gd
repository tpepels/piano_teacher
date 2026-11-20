extends RefCounted
## Paint authoritative unmatched MIDI pitches inside their existing source strip.
## Spelling and clef choose ink placement only; no target or grade is inferred.
const Geometry := preload("res://notation/native/geometry.gd")
const RED := Color("#F17978")

static func paint(canvas: CanvasItem, painter, ghost: Dictionary) -> void:
    var layout = painter.layout
    var gap: float = painter.staff_gap()
    var beat: float = float(ghost["beat"])
    var pitch: int = int(ghost["pitch"])
    var staff: String = str(ghost.get("staff","right"))
    if staff not in ["right","left"]:
        staff = "right"
    var measure: Dictionary = {}
    for candidate in painter.timeline.display_measures:
        if float(candidate["start_beat"]) <= beat:
            measure = candidate
        else:
            break
    var fifths: int = int(measure.get("keys",{}).get(staff,0))
    var names: Array = (["C","D","D","E","E","F","G","G","A","A","B","B"]
        if fifths < 0 else ["C","C","D","D","E","F","F","G","G","A","A","B"])
    var alters: Array = ([0,-1,0,-1,0,0,-1,0,-1,0,-1,0]
        if fifths < 0 else [0,1,0,1,0,0,1,0,1,0,1,0])
    var spelling: Dictionary = {"step":names[pitch%12],"alter":alters[pitch%12],"octave":pitch/12-1}
    var step: int = Geometry.staff_step(spelling,layout.clef_for(staff,measure))
    var bottom: float = layout.staff_center(staff)+gap*2.0
    var y: float = Geometry.note_y(step,bottom,gap)
    var x: float = painter.timeline.x_at_beat(beat)
    painter.engraving.symbols.paint_ledger(canvas,null,x,y,step,bottom,gap,RED)
    painter.glyphs.paint_note(canvas,"quarter",step < 4,x,y,gap,RED)
    # A wrong key must show its actual chromatic pitch unambiguously even
    # when it differs from the current signature's ordinary spelling.
    var alteration: int = int(alters[pitch%12])
    var accidental: String = "acc_flat" if alteration < 0 else "acc_sharp" if alteration > 0 else "acc_natural"
    painter.glyphs.paint(canvas,accidental,x-gap*1.65,y,gap,RED,true)
