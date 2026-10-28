extends RefCounted
## Authentic alpha geometry for density fitting; no canvas or transport state.
## Owns only texture-row cache; score indices/positions belong to ScoreLayout.
const Geometry := preload("res://notation/native/geometry.gd")
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
const MAX_STAFF_GAP := 22.0
var score
var texture_bands: Dictionary = {}

func _init(score_layout) -> void:
    score = score_layout

func clear_cache() -> void:
    texture_bands.clear()

func minimum_density(preferred: float, gap: float = MAX_STAFF_GAP) -> Dictionary:
    # The view owns glyph geometry; the shared calculation owns spacing math.
    var heads: Dictionary = score.engraved_head_offsets(gap)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        score.ordered_events,gap,heads,score.glyphs.bounds)
    var beam_stems: Dictionary = outgoing_beam_stems(gap,heads)
    var positioned_ink: Array = []
    for event in score.ordered_events:
        positioned_ink.append({
            "staff":str(event.get("staff","right")),
            "beat":float(event.get("beat",0.0)),
            "ink":score.event_ink_rect(event,gap,heads,accidentals),
            "boundary_ink":outgoing_glyph_bands(event,gap,heads,accidentals,beam_stems),
            "event":event,
        })
    var result: Dictionary = InkSpacing.minimum_density(positioned_ink,preferred,gap,
        outgoing_boundary_strokes(gap))
    return result

func texture_ink_bands(texture: Texture2D, box: Array, origin: Vector2, gap: float) -> Array:
    # Cache finite alpha-row envelopes once per authentic texture. Unlike
    # enclosing sprite rectangles these do not reserve empty flag margins
    # above a short/tick barline or outside the grand staff.
    var key: int = texture.get_instance_id()
    if not texture_bands.has(key):
        var picture: Image = texture.get_image()
        var rows: Array = []
        for y in range(picture.get_height()):
            var left := picture.get_width()
            var right := -1
            for x in range(picture.get_width()):
                if picture.get_pixel(x,y).a > 0.0:
                    left = mini(left,x)
                    right = maxi(right,x)
            if right >= left:
                var row := Rect2(float(left)/picture.get_width(),float(y)/picture.get_height(),
                    float(right-left+1)/picture.get_width(),1.0/picture.get_height())
                if not rows.is_empty() and is_equal_approx(rows[-1].end.y,row.position.y) and \
                        rows[-1].position.x == row.position.x and rows[-1].size.x == row.size.x:
                    rows[-1].size.y += row.size.y
                else:
                    rows.append(row)
        texture_bands[key] = rows
    var result: Array = []
    var unit: float = gap/250.0
    for row in texture_bands[key]:
        result.append(Rect2(origin+Vector2(float(box[0])+row.position.x*float(box[2]),
            float(box[1])+row.position.y*float(box[3]))*unit,
            Vector2(row.size.x*float(box[2]),row.size.y*float(box[3]))*unit))
    return result

func centered_glyph_bands(name: String, x: float, y: float, gap: float) -> Array:
    var box: Array = score.glyphs.bounds[name].duplicate()
    box[0] = -float(box[2])*.5
    return texture_ink_bands(score.glyphs.textures[name],box,Vector2(x,y),gap)

func outgoing_glyph_bands(event: Dictionary, gap: float,
        heads: Dictionary, accidentals: Dictionary, beam_stems: Dictionary) -> Array:
    var id: String = str(event.get("id",""))
    var kind: String = str(event.get("note_type","quarter"))
    var x: float = float(heads.get(id,0.0))
    var rest: bool = str(event.get("kind","")) == "rest"
    var y: float = score.rest_y(event,gap) if rest else score.event_y(event,gap)
    var bands: Array = []
    if rest:
        bands = centered_glyph_bands("rest_"+kind,0.0,y,gap)
    elif score.chord_members.has(id):
        var key: String = score.chord_template_key(event)
        var beamed: bool = score.beamed_note_ids.has(id)
        bands = texture_ink_bands(score.glyphs.chord_heads_textures[key] if beamed else score.glyphs.chord_textures[key],
            score.glyphs.chord_heads_bounds[key] if beamed else score.glyphs.chord_metadata[key]["bounds"],
            Vector2(score.voice_column_offset(event,gap,heads),y),gap)
    elif not bool(event.get("chord",false)) and not score.beamed_note_ids.has(id):
        var up: bool = bool(score.chord_extents(event,gap)["up"])
        var key: String = "whole" if kind == "whole" else kind+("_up" if up else "_down")
        bands = texture_ink_bands(score.glyphs.note_textures[key],score.glyphs.note_bounds[key],Vector2(x,y),gap)
    else:
        bands = centered_glyph_bands(score.head_family(event),x,y,gap)
    bands.append_array(beam_stems.get(id,[]))
    if not rest:
        var step: int = Geometry.staff_step(event.get("spelling",{}),
            score.clef_for(str(event.get("staff","right")),score.measure_for(event)))
        var bottom: float = score.staff_center(str(event.get("staff","right")))+2.0*gap
        var line: int = -2 if step < 0 else 10
        while line >= step if step < 0 else line <= step:
            var half: float = maxf(18.0,gap*.95)
            var weight: float = maxf(1.6,gap*.075)
            bands.append(Rect2(x-half,Geometry.note_y(line,bottom,gap)-weight*.5,half*2.0,weight))
            line += -2 if step < 0 else 2
        if accidentals.has(id):
            bands.append_array(centered_glyph_bands(str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])]),
                x+float(accidentals[id]),y,gap))
    # Dots follow the same chord-wide anchors and staff spaces as the painter.
    var anchors: Dictionary = {}
    if score.chord_members.has(id):
        var group: Array = score.chord_members[id].duplicate()
        group.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        var centers: Array = []
        for member in group:
            centers.append(Vector2(float(heads.get(str(member.get("id","")),0.0)),score.event_y(member,gap)))
        anchors = score.chord_dot_anchors(group,centers,gap)
        for member in group:
            var anchor: Vector2 = anchors.get(str(member["id"]),Vector2(x,y))
            for dot in range(int(member.get("dots",0))):
                bands.append_array(centered_glyph_bands("augmentation_dot",anchor.x+gap*(1.05+dot*.63),anchor.y-gap*.24,gap))
    elif not bool(event.get("chord",false)):
        for dot in range(int(event.get("dots",0))):
            bands.append_array(centered_glyph_bands("augmentation_dot",x+gap*(1.05+dot*.63),
                y+gap*(Geometry.rest_dot_offset(kind) if rest else 0.0)-gap*.24,gap))
    # Beams, ties and slurs are separate intentional crossing contours and
    # are never included in these ordinary glyph bands.
    return bands

func outgoing_beam_stems(gap: float, heads: Dictionary) -> Dictionary:
    # Shafts are ordinary note ink. The horizontally spanning source beam
    # itself is excluded, but its authentic tip determines the shaft length.
    var result: Dictionary = {}
    var unit: float = gap/250.0
    for group in score.beam_groups:
        if group.size() < 2:
            continue
        var ids := PackedStringArray()
        for event in group:
            ids.append(str(event["id"]))
        var tips: Array = score.glyphs.beam_tips("|".join(ids))
        for i in range(group.size()):
            var event: Dictionary = group[i]
            var up: bool = bool(score.beam_stem_up_by_note[str(event["id"])])
            var extent: Dictionary = score.chord_extents(event,gap,heads)
            var y: float = float(extent["bottom_y"] if up else extent["top_y"])
            var tip: float = y+float(tips[i])*unit
            var box: Array = score.source_stem_bounds(event,up)
            var chord: String = score.chord_template_key(event)
            var note: String = str(event["note_type"])+("_up" if up else "_down")
            var texture: Texture2D = score.glyphs.note_stem_textures[note] if chord.is_empty() else score.glyphs.chord_stem_textures[chord]
            result[str(event["id"])] = texture_ink_bands(texture,
                [box[0],minf(y,tip)/unit,box[2],absf(y-tip)/unit],
                Vector2(score.voice_column_offset(event,gap,heads),0.0),gap)
    return result

func outgoing_boundary_strokes(gap: float) -> Array:
    var result: Array = []
    var boundaries: Array = []
    for measure in score.timeline.measures:
        boundaries.append({"beat":float(measure["start_beat"]),"geometry":score.barline_geometry(measure,0.0,0.0,gap)})
    boundaries.append({"beat":score.timeline.duration_beats,"geometry":score.terminal_barline_geometry(0.0,0.0,gap)})
    # The terminal boundary also owns the source-to-preparation junction D.
    # Repetition changes the camera offset, not its local outgoing spacing.
    for boundary in boundaries:
        var info: Dictionary = boundary["geometry"]
        if info.is_empty():
            continue
        var style: String = str(info["style"])
        var strokes: Array = score.barline_strokes(style,gap)
        if strokes.is_empty():
            continue
        for stroke in strokes:
            var left: float = -gap*BarlineLayout.LEAD_STAFF_SPACES+float(stroke["offset"])-float(stroke["width"])*.5
            for segment in info["segments"]:
                var top: float = float(segment["top"])
                var bottom: float = float(segment["bottom"])
                var length: float = gap*(.65 if style == "dashed" else .13)
                var skip: float = gap*(.35 if style == "dashed" else .27)
                while top < bottom:
                    var end: float = minf(bottom,top+length) if style in ["dashed","dotted"] else bottom
                    result.append({"beat":boundary["beat"],"ink":Rect2(left,top,float(stroke["width"]),end-top)})
                    top = end+skip
        var repetition: String = str(info.get("repeat",""))
        var positions: Array = []
        if repetition in ["backward","both"]:
            positions.append(-gap*(BarlineLayout.LEAD_STAFF_SPACES+.92))
        if repetition in ["forward","both"]:
            positions.append(gap*(-BarlineLayout.LEAD_STAFF_SPACES+.56))
        var dot: Array = score.glyphs.bounds["repeat_dot"]
        var center_offset: float = (float(dot[1])+float(dot[3])*.5)*gap/250.0
        for x in positions:
            for staff in ["right","left"]:
                for dy in [-.5,.5]:
                    for ink in centered_glyph_bands("repeat_dot",float(x),
                            score.staff_center(staff)+dy*gap-center_offset,gap):
                        result.append({"beat":boundary["beat"],"ink":ink})
    return result
