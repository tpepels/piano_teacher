extends RefCounted
## Score-revision geometry and indices, independent of the canvas/transport UI.
## The borrowed semantic axis is read here; its transport/density owner is the view.
const Geometry := preload("res://notation/native/geometry.gd")
const ScoreIndex := preload("res://notation/native/score_index.gd")
const VoiceLayout := preload("res://notation/native/voice_layout.gd")
const RestLaneLayout := preload("res://notation/native/rest_lane_layout.gd")
var timeline
var glyphs
var size := Vector2.ZERO
var beam_groups: Array = []
var beamed_note_ids: Dictionary = {}
var beam_stem_up_by_note: Dictionary = {}
var voice_stem_up_by_note: Dictionary = {}
var chord_members: Dictionary = {}
var notation_tuplets: Array = []
var measure_by_number: Dictionary = {}
var ordered_events: Array = []
var attached_grace_notes: Array = []
var source_expressions: Array = []
var expression_note_index: Dictionary = {}
var tie_pairs: Array = []
var slur_pairs: Array = []
var previous_attack_before_measure: Dictionary = {}
var cached_staff_gap := -1.0
var cached_gap_height := -1.0
var cached_head_offsets: Dictionary = {}
var cached_accidental_offsets: Dictionary = {}
var rest_lane_offsets: Dictionary = {}
var unavoidable_rest_overlaps := 0
var cached_offsets_gap := -1.0

func _init(axis, atlas) -> void:
    timeline = axis
    glyphs = atlas

func set_viewport(value: Vector2) -> void:
    if absf(size.y-value.y) > .001:
        cached_staff_gap = -1.0
        cached_gap_height = -1.0
    size = value

func clear() -> void:
    beam_groups.clear()
    beamed_note_ids.clear()
    beam_stem_up_by_note.clear()
    voice_stem_up_by_note.clear()
    chord_members.clear()
    notation_tuplets.clear()
    measure_by_number.clear()
    ordered_events.clear()
    attached_grace_notes.clear()
    source_expressions.clear()
    expression_note_index.clear()
    tie_pairs.clear()
    slur_pairs.clear()
    previous_attack_before_measure.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_accidental_offsets.clear()
    rest_lane_offsets.clear()
    unavoidable_rest_overlaps = 0
    cached_offsets_gap = -1.0

func rebuild_index() -> void:
    var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)
    beam_groups = index["beam_groups"]
    beamed_note_ids = index["beamed_note_ids"]
    beam_stem_up_by_note = index["beam_stem_up_by_note"]
    notation_tuplets = index["notation_tuplets"]
    measure_by_number = index["measure_by_number"]
    ordered_events = index["ordered_events"]
    attached_grace_notes = timeline.model.get("grace_notes", []).duplicate(true)
    source_expressions = timeline.model.get("expressions", []).duplicate(true)
    expression_note_index.clear()
    for source_event in ordered_events:
        if str(source_event.get("kind", "")) == "note":
            expression_note_index[str(source_event.get("id", ""))] = source_event
    chord_members = index["chord_members"]
    voice_stem_up_by_note = polyphonic_stem_directions()
    previous_attack_before_measure = index["previous_attack_before_measure"]
    tie_pairs = index["tie_pairs"]
    slur_pairs = index["slur_pairs"]


func clef_for(staff: String, measure: Dictionary) -> Dictionary:
    var clefs: Dictionary = measure.get("clefs", {})
    return clefs.get(staff, {
        "sign":"G" if staff == "right" else "F",
        "line":2 if staff == "right" else 4, "octave_change":0})

func measure_for(event: Dictionary) -> Dictionary:
    var number: int = int(event.get("measure", -1))
    return measure_by_number.get(number, timeline.measures[0])

func event_y(event: Dictionary, gap: float) -> float:
    var staff: String = str(event.get("staff", "right"))
    var measure: Dictionary = measure_for(event)
    var clef: Dictionary = clef_for(staff, measure)
    var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
    var bottom: float = staff_center(staff) + 2.0 * gap
    return Geometry.note_y(step, bottom, gap)

func performing_hand(event: Dictionary) -> String:
    # The source performer is independent of the staff chosen for engraving.
    # Note-linked marks inherit that performer, including older expression
    # payloads whose `hand` field described only their display lane.
    var linked: String = str(event.get("note_id",event.get("before_note_id","")))
    var owner: Dictionary = expression_note_index.get(linked,event)
    return str(owner.get("hand",owner.get("staff","right")))

func display_staff(event: Dictionary) -> String:
    var linked: String = str(event.get("note_id",event.get("before_note_id","")))
    var owner: Dictionary = expression_note_index.get(linked,event)
    return str(owner.get("staff",owner.get("hand","right")))

func rest_y(event: Dictionary, gap: float) -> float:
    # The Verovio source glyph is positioned by its staff-line origin.
    # Multi-voice offsets are extra staff spaces, never arbitrary pixels.
    return staff_center(str(event.get("staff","right"))) + gap * (
        Geometry.rest_staff_offset(str(event.get("note_type","quarter"))) +
        float(rest_lane_offsets.get(str(event.get("id","")),0.0)))

func layout_rest_lanes(gap: float, density: float) -> void:
    rest_lane_offsets.clear()
    unavoidable_rest_overlaps = 0
    var heads: Dictionary = engraved_head_offsets(gap)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        ordered_events,gap,heads,glyphs.bounds)
    var voices_by_measure: Dictionary = {}
    var obstacles: Dictionary = {}
    for event in ordered_events:
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        if not voices_by_measure.has(lane_key):
            voices_by_measure[lane_key] = {}
            obstacles[lane_key] = []
        var voice: String = str(event.get("voice","1"))
        voices_by_measure[lane_key][voice] = true
        if str(event.get("kind","")) != "note":
            continue
        var ink: Rect2 = event_ink_rect(event,gap,heads,accidentals)
        ink.position.x += float(event.get("beat",0.0))*density
        obstacles[lane_key].append({"voice":voice,"ink":ink})
    # Production geometry stays in the view. Placement policy is stateless.
    # All rest glyph rectangles move linearly with their vertical staff lane.
    for event in ordered_events:
        if str(event.get("kind","")) != "rest":
            continue
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        var id: String = str(event.get("id",""))
        var voice: String = str(event.get("voice","1"))
        var voices: Array = voices_by_measure[lane_key].keys()
        voices.sort()
        rest_lane_offsets[id] = 0.0
        var source_rect: Rect2 = event_ink_rect(event,gap,heads,accidentals)
        source_rect.position.x += float(event.get("beat",0.0))*density
        var placement: Dictionary = RestLaneLayout.place_rest(source_rect,
            voice,voices,str(event.get("note_type","quarter")),gap,
            obstacles[lane_key])
        rest_lane_offsets[id] = placement["shift"]
        obstacles[lane_key].append({"voice":voice,"ink":placement["ink"]})
        if not bool(placement["placed"]):
            unavoidable_rest_overlaps += 1

func stem_attachment(note_type: String, gap: float, up: bool) -> float:
    # The musical anchor is the centred original Verovio notehead. Derive
    # its edge from that glyph's actual metrics rather than a hand-estimated
    # constant. The font asset includes 12 units of transparent padding.
    var name: String = ("head_whole" if note_type == "whole" else
        "head_half" if note_type == "half" else "head_black")
    var box: Array = glyphs.bounds.get(name, [])
    var half_width: float = gap*.61
    if box.size() == 4 and float(box[2]) > 24.0:
        half_width = (float(box[2])*.5-12.0)*gap/250.0
    return half_width if up else -half_width

func source_stem_bounds(event: Dictionary, up: bool) -> Array:
    if chord_members.has(str(event.get("id",""))):
        return glyphs.chord_stem_bounds.get(chord_template_key(event),[])
    var key: String = str(event.get("note_type","eighth"))+(
        "_up" if up else "_down")
    return glyphs.note_stem_bounds.get(key,[])


# Two independent simultaneous voices need separate shafts even when both
# lie on the same side of the staff. Index once per score, never per frame.
# Source beam and explicit stem directions remain authoritative.

func polyphonic_stem_directions() -> Dictionary:
    var y_by_id: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) == "note":
            y_by_id[str(event.get("id",""))] = event_y(event,1.0)
    for members in chord_members.values():
        for member in members:
            y_by_id[str(member.get("id",""))] = event_y(member,1.0)
    return VoiceLayout.stem_directions(ordered_events,chord_members,y_by_id)

func chord_extents(event: Dictionary, gap: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    var members: Array = chord_members.get(str(event.get("id", "")), [event])
    var top_y := INF
    var bottom_y := -INF
    var top_offset := 0.0
    var bottom_offset := 0.0
    var sum_step := 0.0
    var explicit_stem := ""
    for member in members:
        if str(member.get("stem","")) in ["up","down"]:
            explicit_stem = str(member["stem"])
        var head_y: float = event_y(member, gap)
        var offset: float = float(head_offsets.get(str(member.get("id", "")), 0.0))
        if head_y < top_y:
            top_y = head_y
            top_offset = offset
        if head_y > bottom_y:
            bottom_y = head_y
            bottom_offset = offset
        var clef: Dictionary = clef_for(
            str(member.get("staff", "right")), measure_for(member))
        sum_step += float(Geometry.staff_step(
            member.get("spelling", {}),clef))
    return {"top_y":top_y,"bottom_y":bottom_y,
        "top_offset":top_offset,"bottom_offset":bottom_offset,
        "up":explicit_stem == "up" if not explicit_stem.is_empty() else
            bool(voice_stem_up_by_note.get(str(event.get("id","")),
                sum_step/float(maxi(1,members.size())) < 4.0))}


# Chord sprites are keyed by their diatonic interval signature, which is
# invariant under octave transposition. Godot places only Verovio ink.

func chord_template_key(event: Dictionary) -> String:
    var notes: Array = chord_members.get(str(event.get("id","")),[])
    if notes.size() < 2 or notes.size() > 10:
        return ""
    var leader: int = Geometry.diatonic_index(event.get("spelling",{}))
    if leader < 0:
        return ""
    var differences: Array[int] = []
    for head in notes:
        if str(head.get("note_type","")) != str(event.get("note_type","")):
            return ""
        differences.append(Geometry.diatonic_index(
            head.get("spelling",{}))-leader)
    differences.sort()
    if differences.size() < 2 or differences[-1]-differences[0] > 28:
        return ""
    for i in range(1,differences.size()):
        if differences[i] == differences[i-1]:
            return ""
    var names: PackedStringArray = []
    for value in differences:
        names.append(str(value))
    var extents: Dictionary = chord_extents(event,1.0)
    # A source beam can force a chord opposite to its isolated pitch rule.
    # Its direction selects BOTH displaced heads and the stem-side mask,
    # including during load validation, before a frame has been painted.
    var up: bool = bool(beam_stem_up_by_note.get(
        str(event.get("id","")),extents["up"]))
    var direction: String = "up" if up else "down"
    return "%s|%s|%s" % [
        str(event.get("note_type","quarter")),direction,",".join(names)]

func engraved_head_offsets(gap: float) -> Dictionary:
    # All attachments use the SAME original head centres as the compound
    # sprite. Estimated second/unison spacing moves ties and slurs away
    # from the ink even though the musical beat itself is unchanged.
    var offsets: Dictionary = {}
    for leader_id in chord_members:
        var members: Array = chord_members[leader_id].duplicate()
        var leader: Dictionary = {}
        for member in members:
            if str(member.get("id","")) == str(leader_id):
                leader = member
                break
        var positions: Array = glyphs.chord_heads(chord_template_key(leader))
        if positions.size() != members.size():
            continue
        members.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < \
                Geometry.diatonic_index(b.get("spelling",{})))
        for i in range(members.size()):
            offsets[str(members[i].get("id",""))] = \
                float(positions[i][0])*gap/250.0
    var columns: Dictionary = polyphonic_column_offsets(gap,offsets)
    for id in columns:
        offsets[id] = float(offsets.get(id,0.0))+float(columns[id])
    return offsets

func head_family(event: Dictionary) -> String:
    return VoiceLayout.head_family(event)

func polyphonic_column_offsets(gap: float, heads: Dictionary) -> Dictionary:
    var y_by_id: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) == "note":
            y_by_id[str(event.get("id",""))] = event_y(event,gap)
    for members in chord_members.values():
        for member in members:
            y_by_id[str(member.get("id",""))] = event_y(member,gap)
    var stem_up: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) == "note" and not bool(event.get("chord",false)):
            var id: String = str(event.get("id",""))
            stem_up[id] = bool(beam_stem_up_by_note.get(
                id,chord_extents(event,gap)["up"]))
    return VoiceLayout.column_offsets(
        ordered_events,chord_members,stem_up,glyphs.bounds,heads,y_by_id,gap)

func voice_column_offset(event: Dictionary, gap: float, heads: Dictionary) -> float:
    var id: String = str(event.get("id",""))
    var intrinsic := 0.0
    var members: Array = chord_members.get(id,[]).duplicate()
    var positions: Array = glyphs.chord_heads(chord_template_key(event))
    if positions.size() == members.size():
        members.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        for i in range(members.size()):
            if str(members[i].get("id","")) == id:
                intrinsic = float(positions[i][0])*gap/250.0
    return float(heads.get(id,0.0))-intrinsic

func event_ink_rect(event: Dictionary, gap: float,
        heads: Dictionary, accidentals: Dictionary) -> Rect2:
    var unit: float = gap/250.0
    var id: String = str(event.get("id",""))
    var kind: String = str(event.get("note_type","quarter"))
    var head_x: float = float(heads.get(id,0.0))
    var box: Array = []
    if str(event.get("kind","")) == "rest":
        box = glyphs.bounds["rest_"+kind]
        var y: float = rest_y(event,gap)
        var left := -float(box[2])*unit*.5
        var right := float(box[2])*unit*.5
        var top := y+float(box[1])*unit
        var bottom := top+float(box[3])*unit
        var dots: int = int(event.get("dots",0))
        if dots > 0:
            var dot: Array = glyphs.bounds["augmentation_dot"]
            var dot_y: float = y+gap*(
                Geometry.rest_dot_offset(kind)-.24)
            top = minf(top,dot_y+float(dot[1])*unit)
            bottom = maxf(bottom,dot_y+float(dot[1]+dot[3])*unit)
            right = maxf(right,gap*(1.05+float(dots-1)*.63)+
                float(dot[2])*unit*.5)
        return with_single_tuplet_ink(event,Rect2(left,top,right-left,bottom-top),gap)
    if chord_members.has(id):
        var key: String = chord_template_key(event)
        box = glyphs.chord_heads_bounds[key] if beamed_note_ids.has(id) else \
            glyphs.chord_metadata[key]["bounds"]
    elif not bool(event.get("chord",false)) and not beamed_note_ids.has(id):
        var up: bool = bool(chord_extents(event,gap)["up"])
        var key: String = "whole" if kind == "whole" else kind+(
            "_up" if up else "_down")
        box = glyphs.note_bounds[key]
    var head_box: Array = glyphs.bounds["head_"+(
        kind if kind in ["whole","half"] else "black")]
    var left: float = head_x-float(head_box[2])*unit*.5
    var right: float = head_x+float(head_box[2])*unit*.5
    var y: float = event_y(event,gap)
    var top: float = y+float(head_box[1])*unit
    var bottom: float = y+(float(head_box[1])+float(head_box[3]))*unit
    var sprite_x: float = voice_column_offset(event,gap,heads) if chord_members.has(id) else head_x
    if box.size() == 4:
        left = minf(left,sprite_x+float(box[0])*unit)
        right = maxf(right,sprite_x+(float(box[0])+float(box[2]))*unit)
        top = minf(top,y+float(box[1])*unit)
        bottom = maxf(bottom,y+(float(box[1])+float(box[3]))*unit)
    if beamed_note_ids.has(id):
        var stem: Array = source_stem_bounds(event,bool(beam_stem_up_by_note[id]))
        left = minf(left,sprite_x+float(stem[0])*unit)
        right = maxf(right,sprite_x+(float(stem[0])+float(stem[2]))*unit)
        top = minf(top,y+float(stem[1])*unit)
        bottom = maxf(bottom,y+(float(stem[1])+float(stem[3]))*unit)
    var step: int = Geometry.staff_step(event.get("spelling",{}),
        clef_for(str(event.get("staff","right")),measure_for(event)))
    if step <= -2 or step >= 10:
        left = minf(left,head_x-maxf(18.0,gap*.95))
        right = maxf(right,head_x+maxf(18.0,gap*.95))
        var staff_bottom: float = staff_center(str(event.get("staff","right")))+2.0*gap
        if step <= -2:
            top = minf(top,Geometry.note_y(-2,staff_bottom,gap)-.675)
        else:
            bottom = maxf(bottom,Geometry.note_y(10,staff_bottom,gap)+.675)
    if accidentals.has(id):
        var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])])
        var width: float = float(glyphs.bounds[name][2])*unit
        var center: float = head_x+float(accidentals[id])
        left = minf(left,center-width*.5)
        right = maxf(right,center+width*.5)
        top = minf(top,y+float(glyphs.bounds[name][1])*unit)
        bottom = maxf(bottom,y+(float(glyphs.bounds[name][1])+ \
            float(glyphs.bounds[name][3]))*unit)
    var dots: int = int(event.get("dots",0))
    if dots > 0:
        right = maxf(right,head_x+gap*(1.05+float(dots-1)*.63)+ \
            float(glyphs.bounds["augmentation_dot"][2])*unit*.5)
    var rect := Rect2(left,top,right-left,bottom-top)
    if chord_members.has(id):
        var group: Array = chord_members[id].duplicate()
        group.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        var centers: Array = []
        for member in group:
            centers.append(Vector2(float(heads.get(str(member.get("id","")),0.0)),event_y(member,gap)))
        var anchors: Dictionary = chord_dot_anchors(group,centers,gap)
        var dot: Array = glyphs.bounds["augmentation_dot"]
        for member in group:
            var member_id: String = str(member.get("id",""))
            if anchors.has(member_id):
                var anchor: Vector2 = anchors[member_id]
                var count: int = int(member.get("dots",0))
                rect = rect.merge(Rect2(anchor.x+gap*1.05-float(dot[2])*unit*.5,
                    anchor.y-gap*.24+float(dot[1])*unit,
                    float(dot[2])*unit+float(count-1)*gap*.63,float(dot[3])*unit))
    return with_single_tuplet_ink(event,rect,gap)

func with_single_tuplet_ink(event: Dictionary, rect: Rect2, gap: float) -> Rect2:
    var id: String = str(event.get("id",""))
    if not glyphs.tuplet_metadata.has(id):
        return rect
    var info: Dictionary = glyphs.tuplet_metadata[id]
    if info.get("note_ids",[]).size() != 1:
        return rect
    var y: float = rest_y(event,gap) if str(event.get("kind","")) == "rest" else event_y(event,gap)
    var unit: float = gap/250.0
    for kind in ["number","bracket"]:
        if info.get(kind) is Dictionary and not info[kind].is_empty():
            var box: Array = info[kind]["bounds"]
            rect = rect.merge(Rect2(float(box[0])*unit,y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit))
    return rect

func chord_dot_anchors(notes: Array, centers: Array, gap: float) -> Dictionary:
    # Every tone's dots clear the rightmost displaced head. Assign distinct
    # staff spaces from highest to lowest; a line tone can use the space
    # below when its preferred upper space belongs to its adjacent tone.
    var right := -INF
    for center in centers:
        right = maxf(right,center.x)
    var occupied: Dictionary = {}
    var result: Dictionary = {}
    for note in notes:
        if int(note.get("dots",0)) > 0:
            var staff: String = str(note.get("staff","right"))
            var step: int = Geometry.staff_step(note.get("spelling",{}),clef_for(staff,measure_for(note)))
            if posmod(step,2) == 1:
                occupied[step] = true
    for i in range(notes.size()-1,-1,-1):
        var note: Dictionary = notes[i]
        if int(note.get("dots",0)) == 0:
            continue
        var staff: String = str(note.get("staff","right"))
        var step: int = Geometry.staff_step(note.get("spelling",{}),clef_for(staff,measure_for(note)))
        var target: int = step if posmod(step,2) == 1 else step+1
        if posmod(step,2) == 0:
            if occupied.has(target):
                target = step-1
            while occupied.has(target):
                target -= 2
        occupied[target] = true
        result[str(note.get("id",""))] = Vector2(right,
            Geometry.note_y(target,staff_center(staff)+gap*2.0,gap)+gap*.24)
    return result

func staff_center(hand: String) -> float:
    return size.y*(.36 if hand == "right" else .69)

const BarlineLayout := preload("res://notation/native/barline_layout.gd")

func barline_geometry(measure: Dictionary, clock: float,
        playhead_x: float, gap: float, play_from_beat: float = 0.0) -> Dictionary:
    var info: Dictionary = BarlineLayout.boundary(timeline.measures, measure, timeline,
        clock, playhead_x, play_from_beat, gap,
        staff_center("right")-2.0*gap,
        staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = barline_segments(str(info.get("style","regular")),gap)
    return info

func terminal_barline_geometry(clock: float,
        playhead_x: float, gap: float, play_from_beat: float = 0.0) -> Dictionary:
    var info: Dictionary = BarlineLayout.terminal(timeline.measures, timeline,
        clock, playhead_x, play_from_beat, gap,
        staff_center("right")-2.0*gap,
        staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = barline_segments(str(info.get("style","regular")),gap)
    return info

func barline_segments(style: String, gap: float) -> Array:
    if style in ["tick","short"]:
        var segments: Array = []
        for staff in ["right","left"]:
            var center: float = staff_center(staff)
            segments.append({
                "top":center-gap*(2.5 if style == "tick" else 1.0),
                "bottom":center-gap*1.5 if style == "tick" else center+gap})
        return segments
    return [{"top":staff_center("right")-2.0*gap,
        "bottom":staff_center("left")+2.0*gap}]

func barline_strokes(style: String, gap: float) -> Array:
    return BarlineLayout.strokes(style, gap)
