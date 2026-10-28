extends RefCounted
## Source-axis musical-ink reservations for native fingering placement.
## Borrows geometry/indices; owns only staff lines and authentic sprite envelopes.
const Geometry := preload("res://notation/native/geometry.gd")
const FingeringSpatialLayout := preload("res://notation/native/fingering_spatial_layout.gd")

var score_layout
var connector_geometry
var staff_lines: Array = []
var sprite_envelopes: Dictionary = {}

func _init(layout, connectors) -> void:
    score_layout = layout
    connector_geometry = connectors

func clear() -> void:
    staff_lines.clear()
    sprite_envelopes.clear()

func block(rect: Rect2, bins: Dictionary, cell: float) -> void:
    FingeringSpatialLayout.block(rect,bins,cell)

func is_clear(rect: Rect2, bins: Dictionary, cell: float) -> bool:
    return FingeringSpatialLayout.is_clear(rect,bins,cell,staff_lines,score_layout.size.y)

## Append source-coordinate reservations to caller-owned bins.
func build(gap: float, bins: Dictionary, cell: float, play_from_beat: float = 0.0) -> void:
    var density: float = score_layout.timeline.pixels_per_beat
    var unit: float = gap/250.0
    var span: float = maxf(score_layout.size.x,float(score_layout.ordered_events[-1].get("beat",0.0))*density+gap*12.0) if not score_layout.ordered_events.is_empty() else score_layout.size.x
    staff_lines.clear()
    for hand in ["right","left"]:
        for line in range(-2,3):
            staff_lines.append(Rect2(-gap*12.0,score_layout.staff_center(hand)+float(line)*gap-.5,span+gap*12.0,1.0))
    for event in score_layout.ordered_events:
        event_obstacles(event,gap,bins,cell)
    # Source beam masks and their stretched native stems, including chords.
    for group in score_layout.beam_groups:
        var ids := PackedStringArray()
        for event in group:
            ids.append(str(event.get("id","")))
        var key: String = "|".join(ids)
        if not score_layout.glyphs.beam_metadata.has(key):
            continue
        var info: Dictionary = score_layout.glyphs.beam_metadata[key]
        var box: Array = info["bounds"]
        var first: Dictionary = group[0]
        var last: Dictionary = group[-1]
        var x0: float = float(first["beat"])*density+score_layout.voice_column_offset(first,gap,score_layout.cached_head_offsets)
        var x1: float = float(last["beat"])*density+score_layout.voice_column_offset(last,gap,score_layout.cached_head_offsets)
        var source_offsets: Array = info["head_offsets"]
        block(Rect2(x0+(float(box[0])-float(source_offsets[0]))*unit,
            score_layout.event_y(first,gap)+float(box[1])*unit,
            x1-x0+(float(box[2])-float(source_offsets[-1])+float(source_offsets[0]))*unit,
            float(box[3])*unit),bins,cell)
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var extents: Dictionary = score_layout.chord_extents(event,gap,score_layout.cached_head_offsets)
            var head_y: float = float(extents["bottom_y" if info["stem_up"] else "top_y"])
            var tip_y: float = head_y+float(info["tip_offsets"][index])*unit
            var x: float = float(event["beat"])*density+score_layout.voice_column_offset(event,gap,score_layout.cached_head_offsets)
            var stem: Array = score_layout.source_stem_bounds(event,bool(info["stem_up"]))
            if stem.size() == 4:
                block(Rect2(x+float(stem[0])*unit,minf(head_y,tip_y),
                    float(stem[2])*unit,absf(head_y-tip_y)),bins,cell)
    for pair in score_layout.tie_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var place: Dictionary = connector_geometry.tie_placement(first,last,float(first["beat"])*density,
            float(last["beat"])*density,gap)
        if place.is_empty():
            continue
        block(connector_geometry.tie_contour_rect(first,last,place,gap),bins,cell)
    for pair in score_layout.slur_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var info: Dictionary = score_layout.glyphs.slur_metadata[pair["key"]]
        var box: Array = info["bounds"]
        var x0: float = float(first["beat"])*density+float(score_layout.cached_head_offsets.get(str(first["id"]),0.0))
        var x1: float = float(last["beat"])*density+float(score_layout.cached_head_offsets.get(str(last["id"]),0.0))
        var change: float = score_layout.event_y(last,gap)-score_layout.event_y(first,gap)-float(info.get("original_end_y",0.0))*unit
        var a: float = change*float(box[0])/float(info["span"])
        var b: float = change*(float(box[0])+float(box[2]))/float(info["span"])
        block(Rect2(x0+float(box[0])*(x1-x0)/float(info["span"]),
            score_layout.event_y(first,gap)+float(box[1])*unit+minf(a,b),
            float(box[2])*(x1-x0)/float(info["span"]),float(box[3])*unit+absf(b-a)),bins,cell)
    for group in score_layout.notation_tuplets:
        var events: Array = group.get("events",[])
        if events.is_empty() or (str(group.get("show_number","actual")) == "none" and str(group.get("bracket","yes")) == "no"):
            continue
        var ids := PackedStringArray()
        for event in events:
            ids.append(str(event["id"]))
        var info: Dictionary = score_layout.glyphs.tuplet_metadata.get("|".join(ids),{})
        var first: Dictionary = events[0]
        var x0: float = float(first["beat"])*density+score_layout.voice_column_offset(first,gap,score_layout.cached_head_offsets)
        var x1: float = float(events[-1]["beat"])*density+score_layout.voice_column_offset(events[-1],gap,score_layout.cached_head_offsets)
        var y: float = score_layout.rest_y(first,gap) if first["kind"] == "rest" else score_layout.event_y(first,gap)
        for kind in ["number","bracket"]:
            if not info.get(kind) is Dictionary or info[kind].is_empty():
                continue
            var box: Array = info[kind]["bounds"]
            var left: float = (x0+x1)*.5-float(box[2])*unit*.5 if kind == "number" and events.size() > 1 else x0+float(box[0])*unit
            var width: float = float(box[2])*unit if kind == "number" or events.size() == 1 else x1-x0+(float(box[2])-float(info["span"]))*unit
            block(Rect2(left,y+float(box[1])*unit,width,float(box[3])*unit),bins,cell)
    for mark in score_layout.source_expressions:
        var hand: String = score_layout.display_staff(mark)
        var kind: String = str(mark.get("kind",""))
        var value: String = str(mark.get("value",""))
        var x: float = float(mark.get("beat",0.0))*density
        var y: float = score_layout.staff_center(hand)+gap*(3.0 if kind == "dynamic" else 3.55)
        var name := ""
        if kind == "dynamic":
            name = "dynamic_"+value
        elif kind == "pedal":
            name = "pedal_start" if value == "start" else "pedal_stop"
        elif kind == "articulation":
            var event: Dictionary = score_layout.expression_note_index.get(str(mark.get("note_id","")),{})
            if event.is_empty():
                continue
            var step: int = Geometry.staff_step(event.get("spelling",{}),score_layout.clef_for(hand,score_layout.measure_for(event)))
            var below: bool = step < 4
            y = maxf(score_layout.event_y(event,gap)+gap*1.05,score_layout.staff_center(hand)+gap*2.9) if below else minf(score_layout.event_y(event,gap)-gap*1.05,score_layout.staff_center(hand)-gap*2.9)
            x = float(event["beat"])*density+float(score_layout.cached_head_offsets.get(str(event["id"]),0.0))
            name = "artic_"+value+("_below" if below else "_above")
        if score_layout.glyphs.bounds.has(name):
            var box: Array = score_layout.glyphs.bounds[name]
            var scale: float = unit*.9
            block(Rect2(x-float(box[2])*scale*.5,y+float(box[1])*scale,
                float(box[2])*scale,float(box[3])*scale),bins,cell)
    var translation: float = score_layout.timeline.screen_x(0.0,0.0,0.0,play_from_beat)
    var boundaries: Array = []
    for measure in score_layout.timeline.measures:
        boundaries.append(score_layout.barline_geometry(measure,0.0,0.0,gap,play_from_beat))
    boundaries.append(score_layout.terminal_barline_geometry(0.0,0.0,gap,play_from_beat))
    for boundary in boundaries:
        if boundary.is_empty():
            continue
        var x: float = float(boundary["x"])-translation
        var strokes: Array = score_layout.barline_strokes(str(boundary.get("style","regular")),gap)
        if strokes.is_empty():
            continue
        for stroke in strokes:
            var width: float = float(stroke["width"])
            var stroke_x: float = x+float(stroke["offset"])
            for segment in boundary.get("segments",[]):
                block(Rect2(stroke_x-width*.5,float(segment["top"]),width,
                    float(segment["bottom"])-float(segment["top"])),bins,cell)
        var repetition: String = str(boundary.get("repeat",""))
        var positions: Array = []
        if repetition in ["backward","both"]:
            positions.append(x-gap*.92)
        if repetition in ["forward","both"]:
            positions.append(x+gap*.56)
        var dot: Array = score_layout.glyphs.bounds.get("repeat_dot",[])
        if dot.size()==4:
            for dot_x in positions:
                for hand in ["right","left"]:
                    for dot_y in [score_layout.staff_center(hand)-gap*.5,score_layout.staff_center(hand)+gap*.5]:
                        block(Rect2(float(dot_x)-float(dot[2])*unit*.5,
                            float(dot_y)-float(dot[3])*unit*.5,
                            float(dot[2])*unit,float(dot[3])*unit),bins,cell)
    for grace in score_layout.attached_grace_notes:
        var target: Dictionary = score_layout.expression_note_index.get(str(grace.get("before_note_id","")),{})
        if target.is_empty():
            continue
        var hand: String = score_layout.display_staff(grace)
        var step: int = Geometry.staff_step(grace.get("spelling",{}),score_layout.clef_for(hand,score_layout.measure_for(grace)))
        var y: float = Geometry.note_y(step,score_layout.staff_center(hand)+gap*2.0,gap)
        var kind: String = str(grace.get("note_type","eighth"))
        var box: Array = score_layout.glyphs.note_bounds.get(kind+("_up" if step<4 else "_down"),[])
        if box.size() == 4:
            var scale: float = unit*.66
            var x: float = float(target["beat"])*density+float(score_layout.cached_head_offsets.get(str(target["id"]),0.0))-gap*1.4
            block(Rect2(x+float(box[0])*scale,y+float(box[1])*scale,
                float(box[2])*scale,float(box[3])*scale),bins,cell)
    var pending: Dictionary = {}
    for mark in score_layout.source_expressions:
        if str(mark.get("kind","")) != "hairpin":
            continue
        var hand: String = score_layout.display_staff(mark)
        var key: String = hand+"|"+str(mark.get("number","1"))
        if str(mark.get("value","")) in ["crescendo","diminuendo"]:
            pending[key] = mark
        elif str(mark.get("value","")) == "stop" and pending.has(key):
            var start: Dictionary = pending[key]
            pending.erase(key)
            var x0: float = float(start.get("beat",0.0))*density+gap*.48
            var x1: float = float(mark.get("beat",0.0))*density-gap*.25
            if x1>x0:
                block(Rect2(x0,score_layout.staff_center(hand)+gap*3.55-gap*.3,x1-x0,gap*.6),bins,cell)


func event_obstacles(event: Dictionary, gap: float, bins: Dictionary, cell: float) -> void:
    var id: String = str(event["id"])
    var kind: String = str(event.get("note_type","quarter"))
    var unit: float = gap/250.0
    var anchor: float = float(event["beat"])*score_layout.timeline.pixels_per_beat
    var x: float = anchor+float(score_layout.cached_head_offsets.get(id,0.0))
    var y: float = score_layout.rest_y(event,gap) if event["kind"] == "rest" else score_layout.event_y(event,gap)
    var box: Array
    if event["kind"] == "rest":
        box = score_layout.glyphs.bounds["rest_"+kind]
        block(Rect2(anchor-float(box[2])*unit*.5,y+float(box[1])*unit,
            float(box[2])*unit,float(box[3])*unit),bins,cell)
    else:
        box = score_layout.glyphs.bounds["head_"+(kind if kind in ["whole","half"] else "black")]
        block(Rect2(x-float(box[2])*unit*.5,y+float(box[1])*unit,
            float(box[2])*unit,float(box[3])*unit),bins,cell)
        var step: int = Geometry.staff_step(event.get("spelling",{}),score_layout.clef_for(str(event["staff"]),score_layout.measure_for(event)))
        var bottom: float = score_layout.staff_center(str(event["staff"]))+gap*2.0
        var line_step: int = -2 if step<0 else 10
        while line_step>=step if step<0 else line_step<=step:
            var line_y: float = Geometry.note_y(line_step,bottom,gap)
            var half: float = maxf(18.0,gap*.95)
            var weight: float = maxf(1.6,gap*.075)
            block(Rect2(x-half,line_y-weight*.5,half*2.0,weight),bins,cell)
            line_step += -2 if step<0 else 2
        if not bool(event.get("chord",false)) and not score_layout.beamed_note_ids.has(id) and kind != "whole":
            var up: bool = bool(score_layout.chord_extents(event,gap,score_layout.cached_head_offsets)["up"])
            var stem: Array = score_layout.source_stem_bounds(event,up)
            if stem.size()==4:
                var stem_x: float = anchor+score_layout.voice_column_offset(event,gap,score_layout.cached_head_offsets)
                block(Rect2(stem_x+float(stem[0])*unit,y+float(stem[1])*unit,
                    float(stem[2])*unit,float(stem[3])*unit),bins,cell)
            if kind not in ["quarter","half"]:
                # A flagged sprite's enclosing note/stem rectangle contains
                # empty space beside the shaft. Ledger/accidental unions make
                # that empty region even larger. Reserve the authentic flag
                # side of the sprite; heads, ledgers and shaft are separate.
                var chord_key: String = score_layout.chord_template_key(event) if score_layout.chord_members.has(id) else ""
                var envelope: Rect2 = nonhead_envelope(kind,up,chord_key)
                var origin: float = anchor+score_layout.voice_column_offset(event,gap,score_layout.cached_head_offsets) if score_layout.chord_members.has(id) else x
                block(Rect2(Vector2(origin,y)+envelope.position*unit,envelope.size*unit),bins,cell)
        if score_layout.cached_accidental_offsets.has(id):
            var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])])
            box = score_layout.glyphs.bounds[name]
            var center: float = x+float(score_layout.cached_accidental_offsets[id])
            block(Rect2(center-float(box[2])*unit*.5,y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit),bins,cell)
    box = score_layout.glyphs.bounds["augmentation_dot"]
    # Chord dots share the painter's rightmost head and distinct staff spaces.
    # The leader reserves the complete group once; other tones keep their
    # independent head/ledger/accidental reservations above.
    if bool(event.get("chord",false)):
        return
    var dot_events: Array = score_layout.chord_members.get(id,[event]).duplicate()
    var dot_anchors: Dictionary = {}
    if score_layout.chord_members.has(id):
        dot_events.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        var centers: Array = []
        for member in dot_events:
            centers.append(Vector2(anchor+float(score_layout.cached_head_offsets.get(str(member["id"]),0.0)),
                score_layout.event_y(member,gap)))
        dot_anchors = score_layout.chord_dot_anchors(dot_events,centers,gap)
    for member in dot_events:
        var dot_anchor: Vector2 = dot_anchors.get(str(member["id"]),
            Vector2(x,y+(Geometry.rest_dot_offset(kind)*gap if event["kind"] == "rest" else 0.0)))
        var dot_y: float = dot_anchor.y-gap*.24
        for index in range(int(member.get("dots",0))):
            var dot_x: float = dot_anchor.x+gap*(1.05+float(index)*.63)
            block(Rect2(dot_x-float(box[2])*unit*.5,dot_y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit),bins,cell)


func nonhead_envelope(kind: String, up: bool, chord_key: String = "") -> Rect2:
    # Read the authentic sprite once per template, including faint edge ink.
    # Excluding only its separately reserved head rectangles leaves an exact
    # conservative shaft/flag envelope without a guessed flag-side cutoff.
    var key: String = kind+("_up" if up else "_down")
    var cache_key: String = "note|"+key if chord_key.is_empty() else "chord|"+chord_key
    if sprite_envelopes.has(cache_key):
        return sprite_envelopes[cache_key]
    var box: Array = score_layout.glyphs.note_bounds[key] if chord_key.is_empty() else score_layout.glyphs.chord_metadata[chord_key]["bounds"]
    var texture: Texture2D = score_layout.glyphs.note_textures[key] if chord_key.is_empty() else score_layout.glyphs.chord_textures[chord_key]
    var picture: Image = texture.get_image()
    var pixel := Vector2(float(box[2])/picture.get_width(),float(box[3])/picture.get_height())
    var head_box: Array = score_layout.glyphs.bounds["head_"+(kind if kind in ["half","whole"] else "black")]
    var positions: Array = [[0.0,0.0]] if chord_key.is_empty() else score_layout.glyphs.chord_metadata[chord_key]["head_positions"]
    var heads: Array = []
    for position in positions:
        heads.append(Rect2(float(position[0])-float(head_box[2])*.5,
            float(position[1])+float(head_box[1]),float(head_box[2]),float(head_box[3])))
    var envelope := Rect2()
    var found := false
    for row in range(picture.get_height()):
        for column in range(picture.get_width()):
            if picture.get_pixel(column,row).a == 0.0:
                continue
            var point := Vector2(float(box[0]),float(box[1]))+Vector2(column+.5,row+.5)*pixel
            var in_head := false
            for head in heads:
                if head.has_point(point):
                    in_head = true
                    break
            if in_head:
                continue
            var cell := Rect2(point-pixel*.5,pixel)
            envelope = envelope.merge(cell) if found else cell
            found = true
    sprite_envelopes[cache_key] = envelope
    return envelope
