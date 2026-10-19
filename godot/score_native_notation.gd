extends "res://score_timeline_preview.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation falls back to the existing Verovio score as a whole.
const Geometry := preload("res://score_notation_geometry.gd")
const VerovioGlyphs := preload("res://score_verovio_glyphs.gd")
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT

var glyphs = VerovioGlyphs.new()
var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var selected_density := 0.0
var beam_groups: Array = []
var beamed_note_ids: Dictionary = {}
var chord_members: Dictionary = {}
var notation_tuplets: Array = []
# Immutable musical structure is indexed ONCE when a passage changes.
# Each frame then visits only visible onsets, beams and ties.
var measure_by_number: Dictionary = {}
var ordered_events: Array = []
var tie_pairs: Array = []
var previous_attack_before_measure: Dictionary = {}
var cached_staff_gap := -1.0
var cached_gap_height := -1.0
var cached_head_offsets: Dictionary = {}
var cached_offsets_gap := -1.0
var frame_scanned_events := 0
var frame_visible_beam_groups := 0

func clear_score() -> void:
    super.clear_score()
    native_ready = false
    failure_reason = ""
    visible_symbols = 0
    drawn_noteheads.clear()
    beam_groups.clear()
    beamed_note_ids.clear()
    chord_members.clear()
    notation_tuplets.clear()
    measure_by_number.clear()
    ordered_events.clear()
    tie_pairs.clear()
    previous_attack_before_measure.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_offsets_gap = -1.0

func set_verovio_glyphs(items: Dictionary, note_items: Dictionary = {},
        tie_items: Dictionary = {}, chord_items: Dictionary = {},
        beam_items: Dictionary = {},
        tuplet_items: Dictionary = {}) -> bool:
    if not glyphs.load_font(items):
        failure_reason = glyphs.error
        return false
    if not glyphs.load_note_templates(note_items):
        failure_reason = glyphs.error
        return false
    if not glyphs.load_tie_templates(tie_items):
        failure_reason = glyphs.error
        return false
    if not glyphs.load_chord_templates(chord_items):
        failure_reason = glyphs.error
        return false
    if not glyphs.load_beam_fragments(beam_items):
        failure_reason = glyphs.error
        return false
    if not glyphs.load_tuplet_fragments(tuplet_items):
        failure_reason = glyphs.error
        return false
    failure_reason = ""
    return true


func load_score(candidate: Dictionary) -> bool:
    native_ready = false
    if not glyphs.ready() or not glyphs.note_ready() or not glyphs.ties_ready():
        failure_reason = "Authentic Verovio symbol, note or tie atlas is not loaded"
        notice = failure_reason
        return false
    failure_reason = Geometry.supported(candidate)
    if not failure_reason.is_empty():
        notice = failure_reason
        return false
    if not super.load_score(candidate):
        failure_reason = notice
        return false
    var density: float = Geometry.required_density(
        timeline.model.get("notation_events", []), timeline.pixels_per_beat)
    if density <= 0.0:
        failure_reason = "Rhythm too dense for one fixed native horizontal scale"
        notice = failure_reason
        return false
    if not timeline.set_density(density):
        failure_reason = timeline.last_error
        notice = failure_reason
        return false
    selected_density = density
    beam_groups = Geometry.beam_groups(timeline.model)
    beamed_note_ids = Geometry.beamed_ids(beam_groups)
    notation_tuplets = Geometry.tuplet_groups(timeline.model)
    measure_by_number.clear()
    for measure in timeline.measures:
        measure_by_number[int(measure.get("number", -1))] = measure
    ordered_events = timeline.model.get("notation_events", []).duplicate()
    ordered_events.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a.get("beat", 0.0)) < float(b.get("beat", 0.0)))
    chord_members = Geometry.chord_members(ordered_events)
    # Cache the preceding attack for every measure once. Tight meter
    # changes must be relocated out of the ink; no per-frame note scan.
    previous_attack_before_measure.clear()
    var scan := 0
    var last_attack := -INF
    for measure in timeline.measures:
        var boundary: float = float(measure.get("start_beat", 0.0))
        while scan < ordered_events.size() and \
                float(ordered_events[scan].get("beat",0.0)) < boundary-.0001:
            if str(ordered_events[scan].get("kind","")) == "note":
                last_attack = float(ordered_events[scan].get("beat",0.0))
            scan += 1
        previous_attack_before_measure[int(measure.get("number",0))] = last_attack
    tie_pairs.clear()
    var unfinished: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind", "")) != "note":
            continue
        var source_id: String = str(event.get("source_id", ""))
        if bool(event.get("tie_stop", false)) and unfinished.has(source_id):
            tie_pairs.append({"first": unfinished[source_id], "last": event})
        if bool(event.get("tie_start", false)):
            unfinished[source_id] = event
        else:
            unfinished.erase(source_id)
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_offsets_gap = -1.0
    cached_head_offsets.clear()
    failure_reason = ""
    native_ready = true
    queue_redraw()
    return true

func _staff_center(hand: String) -> float:
    return size.y * (.34 if hand == "right" else .69)

func _gap() -> float:
    if cached_staff_gap > 0.0 and absf(cached_gap_height - size.y) < .001:
        return cached_staff_gap
    # Reserve actual room for ledger notes ABOVE and BELOW both staves.
    # The former raster crop clipped high notes because it only knew staff
    # rails, not the extreme noteheads. Fit the full semantic pitch range
    # once per frame/viewport, uniformly for both hands.
    var gap: float = clampf(size.y * .034, 8.5, 17.0)
    if timeline.model.is_empty():
        return gap
    for event in ordered_events:
        if str(event.get("kind", "")) != "note":
            continue
        var staff: String = str(event.get("staff", "right"))
        var clef: Dictionary = _clef_for(staff, _measure_for(event))
        var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
        var factor: float = 2.0 - float(step)*.5
        var center: float = _staff_center(staff)
        if factor < -.001:
            gap = minf(gap, (center-32.0) / -factor)
        elif factor > .001:
            gap = minf(gap, (size.y-32.0-center) / factor)
    # A note that truly cannot fit is still drawn deterministically; the
    # score is not cropped, and no horizontal position can change.
    cached_staff_gap = maxf(5.0, gap)
    cached_gap_height = size.y
    return cached_staff_gap

func _clef_for(staff: String, measure: Dictionary) -> Dictionary:
    var clefs: Dictionary = measure.get("clefs", {})
    return clefs.get(staff, {
        "sign":"G" if staff == "right" else "F",
        "line":2 if staff == "right" else 4, "octave_change":0})

func _measure_for(event: Dictionary) -> Dictionary:
    var number: int = int(event.get("measure", -1))
    return measure_by_number.get(number, timeline.measures[0])

func _event_y(event: Dictionary, gap: float) -> float:
    var staff: String = str(event.get("staff", "right"))
    var measure: Dictionary = _measure_for(event)
    var clef: Dictionary = _clef_for(staff, measure)
    var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
    var bottom: float = _staff_center(staff) + 2.0 * gap
    return Geometry.note_y(step, bottom, gap)

func _ink(staff: String) -> Color:
    var selected: bool = active_hand == "both" or active_hand == staff
    return NOTE_INK if selected else Color(DIM_INK, .46)



# One continuous grand-staff barline, displaced slightly left of the
# next measure's attack. This is engraving clearance, not a new time axis.
# The opening header is not preceded by an invented moving barline.
func _barline_geometry(measure: Dictionary, clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    if timeline.measures.is_empty() or \
            int(measure.get("number", -1)) == \
            int(timeline.measures[0].get("number", -2)):
        return {}
    var x: float = timeline.screen_x(float(measure.get("start_beat", 0.0)),
        clock, playhead_x, play_from_beat) - gap*1.35
    return {"x":x, "top":_staff_center("right")-2.0*gap,
        "bottom":_staff_center("left")+2.0*gap}


# Meter changes need room to the LEFT of the next attack. A short
# pickup (e.g. Chopin 1/8 -> 12/8) has no such room on a fixed beat grid.
# Keep the music clock immutable and engrave that exceptional meter in an
# upper annotation lane instead of stacking numbers over the noteheads.
func _meter_is_crowded(measure: Dictionary, previous: Dictionary,
        gap: float) -> bool:
    if previous.is_empty() or previous.get("meter", []) == measure.get("meter", []):
        return false
    var at: float = float(measure.get("start_beat", 0.0))
    var previous_start: float = float(previous.get("start_beat", 0.0))
    var advance: float = timeline.pixels_per_beat
    if (at-previous_start)*advance < gap*7.0:
        return true
    var last_attack: float = float(previous_attack_before_measure.get(
        int(measure.get("number", 0)), -INF))
    return is_finite(last_attack) and \
        (at-last_attack)*advance < gap*6.0


func _paint_meter_above_staff(measure: Dictionary, x: float,
        gap: float) -> void:
    var meter: Array = measure.get("meter", [4,4])
    if meter.size() < 2:
        return
    # Actual Verovio time-signature digit textures, scaled together and
    # arranged ABOVE the upper five lines, not GUI text or invented glyphs.
    var center: float = _staff_center("right")
    var origin: float = x-gap*1.75
    var space: float = gap*.72
    # Meter applies to BOTH staves and must remain readable while one
    # of the hands is dimmed for separate-handed practice.
    _paint_meter_number(int(meter[0]),origin,center-gap*4.50,
        NOTE_INK,space)
    _paint_meter_number(int(meter[1]),origin,center-gap*3.05,
        NOTE_INK,space)


func _paint_ledger(x: float, y: float, step: int,
        bottom: float, gap: float, ink: Color) -> void:
    if step < 0:
        var line_step: int = -2
        while line_step >= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            draw_line(Vector2(x-14.0, line_y),
                Vector2(x+14.0, line_y), Color(ink, .70), 1.35, true)
            line_step -= 2
    elif step > 8:
        var line_step: int = 10
        while line_step <= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            draw_line(Vector2(x-14.0, line_y),
                Vector2(x+14.0, line_y), Color(ink, .70), 1.35, true)
            line_step += 2

func _paint_accidental(x: float, y: float,
        value: String, ink: Color, gap: float) -> void:
    var names := {
        "sharp": "acc_sharp", "flat": "acc_flat",
        "natural": "acc_natural", "double-sharp": "acc_double_sharp",
        "double-flat": "acc_double_flat", "flat-flat": "acc_double_flat"
    }
    var name: String = str(names.get(value, ""))
    if not name.is_empty():
        glyphs.paint(self, name, x - gap*1.15, y, gap, ink, true)


func _paint_flag(stem_x: float, tip_y: float,
        up: bool, count: int, ink: Color, gap: float) -> void:
    var name: String = "flag_%s_%d" % ["up" if up else "down", count]
    glyphs.paint(self, name, stem_x, tip_y, gap, ink)


func _paint_rhythm_dots(x: float, y: float, dots: int,
        ink: Color, gap: float) -> void:
    for index in range(dots):
        glyphs.paint(self, "augmentation_dot",
            x+gap*1.05+float(index)*gap*.63, y-gap*.24,
            gap, ink, true)


func _paint_tuplet_brackets(clock: float, playhead_x: float,
        gap: float) -> void:
    var font: Font = ThemeDB.fallback_font
    for group in notation_tuplets:
        var events: Array = group.get("events", [])
        if events.is_empty():
            continue
        var first: Dictionary = events[0]
        var last: Dictionary = events[-1]
        var source_note_ids := PackedStringArray()
        for event in events:
            if str(event.get("kind","")) == "note":
                source_note_ids.append(str(event.get("id","")))
        var label_key: String = "|".join(source_note_ids)
        var first_x: float = timeline.screen_x(
            float(first.get("beat",0.0)),clock,playhead_x,play_from_beat)
        var last_x: float = timeline.screen_x(
            float(last.get("beat",0.0)),clock,playhead_x,play_from_beat)
        var source_bracket: bool = str(group.get("bracket","yes")) != "no" or \
            events.size() == 1
        if source_note_ids.size() > 1 and \
                glyphs.has_tuplet(label_key,source_bracket):
            if glyphs.paint_tuplet(self,label_key,first_x,last_x,
                    _event_y(first,gap),gap,
                    _ink(str(group.get("staff","right")))):
                continue
        var x0: float = timeline.screen_x(float(first.get("beat", 0.0)),
            clock,playhead_x,play_from_beat)-gap*.8
        var x1: float = timeline.screen_x(float(last.get("beat", 0.0)),
            clock,playhead_x,play_from_beat)+gap*1.25
        if x1 < -50.0 or x0 > size.x+50.0:
            continue
        # A single irregular event still shows its ACTUAL duration ratio.
        if x1-x0 < gap*4.0:
            var middle: float = (x0+x1)*.5
            x0 = middle-gap*2.0
            x1 = middle+gap*2.0
        var staff: String = str(group.get("staff", "right"))
        var up: bool = staff == "right"
        var y: float = _staff_center(staff)-gap*3.4 if up else \
            _staff_center(staff)+gap*3.4
        for event in events:
            if str(event.get("kind", "")) == "note":
                var head_y: float = _event_y(event,gap)
                if up:
                    y = minf(y,head_y-gap*3.0)
                else:
                    y = maxf(y,head_y+gap*3.0)
        y = clampf(y, 22.0, size.y-22.0)
        var label: String = Geometry.tuplet_label(group)
        var font_size := 13
        var middle: float = (x0+x1)*.5
        var half_label: float = font.get_string_size(label,
            HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x*.5
        var ink: Color = _ink(staff)
        var gap_to_label: float = half_label+5.0
        var line_y: float = y+3.0 if up else y-5.0
        var bracket: bool = str(group.get("bracket","yes")) != "no" or \
            events.size() == 1
        if bracket:
            if middle-gap_to_label > x0:
                draw_line(Vector2(x0,line_y),Vector2(middle-gap_to_label,line_y),
                    ink,1.3,true)
            if x1 > middle+gap_to_label:
                draw_line(Vector2(middle+gap_to_label,line_y),
                    Vector2(x1,line_y),ink,1.3,true)
            var drop: float = gap*.42 if up else -gap*.42
            draw_line(Vector2(x0,line_y),Vector2(x0,line_y+drop),ink,1.3,true)
            draw_line(Vector2(x1,line_y),Vector2(x1,line_y+drop),ink,1.3,true)
        if label.is_valid_int() and label.length() <= 2:
            # Tuplet number glyphs use the same real Verovio font atlas as
            # the time signature, at a smaller local visual size.
            var tuplet_space: float = gap*.54
            var digit_step: float = tuplet_space*1.15
            for index in range(label.length()):
                glyphs.paint(self, "time_" + label[index],
                    middle + (float(index) - float(label.length()-1)*.5)*digit_step,
                    y+gap*.18, tuplet_space, ink, true)
        else:
            # Irregular explicit ratios such as 7:5 contain punctuation,
            # which is typographic text, not a custom-drawn music glyph.
            draw_string(font,Vector2(middle-half_label,y+4.0),
                label,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)


func _paint_rest(x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    glyphs.paint(self, "rest_" + note_type, x, y, gap, ink, true)
    _paint_rhythm_dots(x, y, dots, ink, gap)


func _paint_clef(x: float, center: float, sign: String,
        gap: float, ink: Color) -> void:
    var name: String = {"G":"clef_g", "F":"clef_f", "C":"clef_c"}.get(sign, "")
    if name.is_empty():
        return
    # SMuFL origin marks the clef's reference staff line.
    var origin_y: float = center + gap if sign == "G" else (
        center - gap if sign == "F" else center)
    glyphs.paint(self, name, x, origin_y, gap, ink, true)


func _paint_meter_number(value: int, x: float, y: float,
        ink: Color, gap: float) -> void:
    # Real Verovio time-signature digits rather than generic GUI text.
    var digits: String = str(value)
    var advance: float = gap*1.10
    var start: float = x - float(digits.length()-1)*advance*.5
    for digit in range(digits.length()):
        glyphs.paint(self, "time_" + digits[ digit ],
            start + float(digit)*advance, y, gap, ink, true)


func _stem_attachment(note_type: String, gap: float, up: bool) -> float:
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


# Pitch extrema determine a whole chord's stem, not the arbitrarily
# first note in MusicXML. The head artwork/width still comes from Verovio.
func _chord_extents(event: Dictionary, gap: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    var members: Array = chord_members.get(str(event.get("id", "")), [event])
    var top_y := INF
    var bottom_y := -INF
    var top_offset := 0.0
    var bottom_offset := 0.0
    var sum_step := 0.0
    for member in members:
        var head_y: float = _event_y(member, gap)
        var offset: float = float(head_offsets.get(str(member.get("id", "")), 0.0))
        if head_y < top_y:
            top_y = head_y
            top_offset = offset
        if head_y > bottom_y:
            bottom_y = head_y
            bottom_offset = offset
        var clef: Dictionary = _clef_for(
            str(member.get("staff", "right")), _measure_for(member))
        sum_step += float(Geometry.staff_step(
            member.get("spelling", {}),clef))
    return {"top_y":top_y,"bottom_y":bottom_y,
        "top_offset":top_offset,"bottom_offset":bottom_offset,
        "up":sum_step/float(maxi(1,members.size())) < 4.0}


# Chord sprites are keyed by their diatonic interval signature, which is
# invariant under octave transposition. Godot places only Verovio ink.
func _chord_template_key(event: Dictionary) -> String:
    var notes: Array = chord_members.get(str(event.get("id","")),[])
    if notes.size() < 2 or notes.size() > 5:
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
    var names: PackedStringArray = []
    for value in differences:
        names.append(str(value))
    var extents: Dictionary = _chord_extents(event,1.0)
    var direction: String = "up" if bool(extents["up"]) else "down"
    return "%s|%s|%s" % [
        str(event.get("note_type","quarter")),direction,",".join(names)]


func _paint_engraved_chord(event: Dictionary, x: float,
        gap: float, ink: Color) -> Array:
    var key: String = _chord_template_key(event)
    if key.is_empty() or not glyphs.has_chord(key):
        return []
    var beamed: bool = beamed_note_ids.has(str(event.get("id","")))
    if beamed and not glyphs.has_chord_heads(key):
        return []
    var group: Array = chord_members.get(str(event.get("id","")),[])
    var heads: Array = glyphs.chord_heads(key)
    if heads.size() != group.size():
        return []
    var sorted_heads: Array = group.duplicate()
    sorted_heads.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return Geometry.diatonic_index(a.get("spelling",{})) < \
            Geometry.diatonic_index(b.get("spelling",{})))
    var anchor: float = _event_y(event,gap)
    var head_centres: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var offset: Array = heads[i]
        var head_x: float = x+float(offset[0])*gap/250.0
        var head_y: float = anchor+float(offset[1])*gap/250.0
        var staff: String = str(current.get("staff","right"))
        var clef: Dictionary = _clef_for(staff,_measure_for(current))
        var step: int = Geometry.staff_step(
            current.get("spelling",{}),clef)
        head_centres.append(Vector2(head_x,head_y))
        # Ledger rules must be UNDER the authentic filled noteheads.
        _paint_ledger(head_x,head_y,step,_staff_center(staff)+gap*2.0,
            gap,ink)
    var painted_ok: bool = (glyphs.paint_chord_heads(
        self,key,x,anchor,gap,ink) if beamed else
        glyphs.paint_chord(self,key,x,anchor,gap,ink))
    if not painted_ok:
        return []
    var painted: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var center: Vector2 = head_centres[i]
        _paint_rhythm_dots(center.x,center.y,
            int(current.get("dots",0)),ink,gap)
        var accidental: String = str(current.get("accidental",""))
        if not accidental.is_empty() and accidental != "null":
            _paint_accidental(center.x,center.y,accidental,ink,gap)
        var id: String = str(current.get("id",""))
        drawn_noteheads[id] = center
        painted.append(id)
    return painted


func _paint_note(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {},
        head_offset: float = 0.0) -> void:
    # Only local glyph separation: the source beat is unchanged.
    x += head_offset
    var staff: String = str(event.get("staff", "right"))
    var measure: Dictionary = _measure_for(event)
    var clef: Dictionary = _clef_for(staff, measure)
    var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
    var bottom: float = _staff_center(staff) + gap*2.0
    var y: float = Geometry.note_y(step, bottom, gap)
    var kind: String = str(event.get("note_type", "quarter"))
    _paint_ledger(x, y, step, bottom, gap, ink)
    # Simple notes are complete Verovio-engraved sprites: no Godot stem,
    # flag or notehead assembly. Composite chords and beam groups have
    # variable geometry and are handled separately below.
    var isolated: bool = not bool(event.get("chord", false)) and \
        beam_stem.is_empty() and \
        chord_members.get(str(event.get("id", "")), [event]).size() == 1
    if isolated:
        var normal_up: bool = step < 4
        if not glyphs.paint_note(self, kind, normal_up, x, y, gap, ink):
            # Atlas validation happens on load; missing artwork must never
            # silently revert to imitated musical ink.
            push_warning("Missing authentic Verovio note template: " + kind)
            return
        _paint_rhythm_dots(x,y,int(event.get("dots",0)),ink,gap)
        var accidental_name: String = str(event.get("accidental", ""))
        if not accidental_name.is_empty() and accidental_name != "null":
            _paint_accidental(x,y,accidental_name,ink,gap)
        drawn_noteheads[str(event.get("id", ""))] = Vector2(x,y)
        return
    var solid: bool = kind not in ["half","whole"]
    glyphs.paint(self, "head_black" if solid else (
        "head_whole" if kind == "whole" else "head_half"),
        x, y, gap, ink, true)
    # MusicXML chord members keep their separate real glyphs, but only
    # the leading event gets a stem spanning the COMPLETE chord pitch range.
    if kind != "whole" and not bool(event.get("chord", false)):
        var chord: Dictionary = _chord_extents(event,gap,cached_head_offsets)
        var stem_up: bool = bool(beam_stem.get("up",chord["up"]))
        var anchor_y: float = float(chord["bottom_y"] if stem_up else chord["top_y"])
        var anchor_offset: float = float(chord[
            "bottom_offset" if stem_up else "top_offset"])
        var stem_x: float = x-head_offset+anchor_offset+ \
            _stem_attachment(kind,gap,stem_up)
        var tip_y: float = (float(chord["top_y"])-gap*3.25 if stem_up else
            float(chord["bottom_y"])+gap*3.25)
        if not beam_stem.is_empty():
            stem_x = float(beam_stem.get("x",stem_x))
            tip_y = float(beam_stem.get("tip_y",tip_y))
        draw_line(Vector2(stem_x,anchor_y),Vector2(stem_x,tip_y),
            ink,1.65,true)
        if Geometry.beam_level(kind) > 0 and beam_stem.is_empty():
            _paint_flag(stem_x,tip_y,stem_up,
                Geometry.beam_level(kind),ink,gap)
    _paint_rhythm_dots(x,y,int(event.get("dots",0)),ink,gap)
    var accidental: String = str(event.get("accidental", ""))
    if not accidental.is_empty() and accidental != "null":
        _paint_accidental(x,y,accidental,ink,gap)
    drawn_noteheads[str(event.get("id", ""))] = Vector2(x,y)

func _beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    # Beam position is derived from the real notehead Y coordinates.
    # All horizontal positions still come from the one musical-time axis.
    var stems: Dictionary = {}
    var drawn_groups: Array = []
    frame_visible_beam_groups = 0
    for group in beam_groups:
        if group.size() < 2:
            continue
        var first_x: float = timeline.screen_x(
            float(group[0].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        var last_x: float = timeline.screen_x(
            float(group[-1].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        if last_x < -60.0 or first_x > size.x + 60.0:
            continue
        frame_visible_beam_groups += 1
        # The overall stem direction includes ALL chord tones, even when
        # the beam grouping indexes only the chord leaders.
        var sum_steps := 0.0
        var counted := 0
        for event in group:
            var all_heads: Array = chord_members.get(
                str(event.get("id", "")), [event])
            for head in all_heads:
                var clef: Dictionary = _clef_for(
                    str(head.get("staff", "right")), _measure_for(head))
                sum_steps += float(Geometry.staff_step(
                    head.get("spelling", {}),clef))
                counted += 1
        var up: bool = sum_steps/float(maxi(1,counted)) < 4.0
        var members: Array = []
        for event in group:
            var x: float = timeline.screen_x(float(event.get("beat", 0.0)),
                clock, playhead_x, play_from_beat)
            var chord: Dictionary = _chord_extents(event,gap,head_offsets)
            var anchor_offset: float = float(chord[
                "bottom_offset" if up else "top_offset"])
            var stem_x: float = x+anchor_offset+ \
                _stem_attachment(str(event.get("note_type", "eighth")),gap,up)
            members.append({
                "id":str(event.get("id", "")), "x":stem_x,
                "head_x":x+float(head_offsets.get(str(event.get("id","")),0.0)),
                "head_y":float(chord["bottom_y"] if up else chord["top_y"]),
                "top_y":float(chord["top_y"]),
                "bottom_y":float(chord["bottom_y"]),
                "note_type":str(event.get("note_type", "eighth"))
            })
        # Conventional beams follow the overall melodic contour, but a
        # shallow cap prevents steep diagonals on wide intervals.
        var left_x: float = float(members[0]["x"])
        var right_x: float = float(members[-1]["x"])
        var width: float = right_x-left_x
        var rise: float = clampf(
            float(members[-1]["head_y"])-float(members[0]["head_y"]),
            -gap*.75, gap*.75) if width > .01 else 0.0
        # Move the complete tilted beam clear of EVERY notehead, not only
        # the endpoints. Every stem retains at least 3.25 staff spaces.
        var origin: float = INF if up else -INF
        for member in members:
            var t: float = (float(member["x"])-left_x)/width if width > .01 else 0.0
            var required: float = (float(member["top_y"])-gap*3.25
                if up else float(member["bottom_y"])+gap*3.25)
            var candidate: float = required-rise*t
            origin = minf(origin, candidate) if up else maxf(origin, candidate)
        # Every note has an independent native-time X anchor. The genuine
        # Verovio beam image is cut into intervals at those anchors, so no
        # interior note drifts when BPM or screen density changes.
        var art_key: String = ""
        var art_tips: Array = []
        var identifiers := PackedStringArray()
        for member in members:
            identifiers.append(str(member["id"]))
        var candidate: String = "|".join(identifiers)
        if glyphs.has_beam(candidate,up):
            var offsets: Array = glyphs.beam_tips(candidate)
            if offsets.size() == members.size():
                art_key = candidate
                art_tips = offsets
        for index in range(members.size()):
            var member: Dictionary = members[index]
            var t: float = (float(member["x"])-left_x)/width if width > .01 else 0.0
            var tip: float = origin+rise*t
            if art_tips.size() == members.size():
                tip = float(member["head_y"])+float(art_tips[index])*gap/250.0
            member["tip_y"] = tip
            members[index] = member
            stems[str(member["id"])] = {"up":up, "tip_y":tip,
                "x":float(member["x"])}
        drawn_groups.append({"members":members,
            "staff":str(group[0].get("staff", "right")),
            "up":up, "tip_y":origin,"art_key":art_key})
    return {"stems":stems, "groups":drawn_groups}


func _beam_segment(x0: float, y0: float, x1: float, y1: float,
        thickness: float, ink: Color) -> void:
    if x1 <= x0:
        return
    draw_colored_polygon(PackedVector2Array([
        Vector2(x0, y0), Vector2(x1, y1),
        Vector2(x1, y1+thickness), Vector2(x0, y0+thickness)]), ink)


func _paint_beams(data: Dictionary, gap: float) -> void:
    # Main and secondary beams follow exactly the same capped slope;
    # short hooks also follow that line rather than floating horizontally.
    for group in data.get("groups", []):
        var members: Array = group.get("members", [])
        if members.size() < 2:
            continue
        var first: Dictionary = members[0]
        var last: Dictionary = members[-1]
        var left_x: float = float(first["x"])
        var right_x: float = float(last["x"])
        if right_x < -40.0 or left_x > size.x+40.0 or right_x <= left_x:
            continue
        var ink: Color = _ink(str(group.get("staff", "right")))
        var up: bool = bool(group.get("up", true))
        var art_key: String = str(group.get("art_key",""))
        if not art_key.is_empty():
            var anchors: Array = []
            for member in members:
                anchors.append(float(member["head_x"]))
            if glyphs.paint_beam(self,art_key,anchors,
                    float(first["head_y"]),gap,ink):
                continue
        var sign: float = 1.0 if up else -1.0
        var thick: float = gap*.39
        var slope: float = (float(last["tip_y"])-float(first["tip_y"])) / \
            (right_x-left_x)
        _beam_segment(left_x,float(first["tip_y"]),right_x,
            float(last["tip_y"]),sign*thick,ink)
        for level in range(2, 5):
            var offset: float = sign*gap*.65*float(level-1)
            for i in range(members.size()):
                var amount: int = Geometry.beam_level(
                    str(members[i].get("note_type", "")))
                if amount < level:
                    continue
                var x0: float = float(members[i]["x"])
                var y0: float = float(members[i]["tip_y"])+offset
                var prior: bool = i > 0 and Geometry.beam_level(
                    str(members[i-1].get("note_type", ""))) >= level
                var following: bool = i+1 < members.size() and \
                    Geometry.beam_level(
                    str(members[i+1].get("note_type", ""))) >= level
                if following:
                    _beam_segment(x0,y0,float(members[i+1]["x"]),
                        float(members[i+1]["tip_y"])+offset,sign*thick,ink)
                elif not prior:
                    var left_hook: bool = i == members.size()-1
                    var nearby: float = (x0-float(members[i-1]["x"])
                        if left_hook else float(members[i+1]["x"])-x0)
                    var hook: float = minf(gap*1.3, nearby*.50)
                    if left_hook:
                        _beam_segment(x0-hook,y0-slope*hook,x0,y0,
                            sign*thick,ink)
                    else:
                        _beam_segment(x0,y0,x0+hook,y0+slope*hook,
                            sign*thick,ink)

# Only the original Verovio-rendered tie contours are permitted.
# The source noteheads determine the start, end and staff-space vertical
# position. Godot never produces its own bow paths or tapered polygons.
func _tie_placement(first: Dictionary, last: Dictionary,
        x0: float, x1: float, gap: float) -> Dictionary:
    var left: float = x0+float(cached_head_offsets.get(
        str(first.get("id","")),0.0))
    var right: float = x1+float(cached_head_offsets.get(
        str(last.get("id","")),0.0))
    if right-left <= gap*1.2:
        return {}
    var upward_stem: bool = bool(_chord_extents(first,gap)["up"])
    return {"x0":left, "x1":right, "y":_event_y(first,gap),
        "down":upward_stem}


func _paint_ties(playhead_x: float, clock: float, gap: float) -> void:
    for pair in tie_pairs:
        var previous: Dictionary = pair["first"]
        var event: Dictionary = pair["last"]
        var x0: float = timeline.screen_x(float(previous.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(event.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        if x1 < -20.0 or x0 > size.x+20.0:
            continue
        var place: Dictionary = _tie_placement(previous,event,x0,x1,gap)
        if not place.is_empty():
            glyphs.paint_tie(self,float(place["x0"]),float(place["x1"]),
                float(place["y"]),gap,bool(place["down"]),
                _ink(str(event.get("staff","right"))))


# Binary-search into pre-sorted MusicXML events. Work is proportional
# to what the pianist can actually see, not to the whole imported MIDI.
func _visible_events(left: float, right: float) -> Array:
    var begin := 0
    var end := ordered_events.size()
    while begin < end:
        var middle: int = (begin + end) >> 1
        if float(ordered_events[middle].get("beat", 0.0)) < left-.25:
            begin = middle + 1
        else:
            end = middle
    var results: Array = []
    for index in range(begin, ordered_events.size()):
        var event: Dictionary = ordered_events[index]
        if float(event.get("beat", 0.0)) > right+.25:
            break
        results.append(event)
    frame_scanned_events = results.size()
    return results


func _draw() -> void:
    if size.x < 100.0 or size.y < 100.0:
        return
    draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
    var font: Font = ThemeDB.fallback_font
    if not native_ready or not timeline.has_score():
        draw_string(font,Vector2(20.0,size.y*.5),
            notice if not notice.is_empty() else "Loading native score",
            HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
        return
    var gap: float = _gap()
    var playhead_x: float = size.x * PLAYHEAD_FRACTION
    var camera_clock: float = clock_beat if running or paused else 0.0
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+size.x/timeline.pixels_per_beat
    # Always draw ten native rules; no copied or stitched raster systems.
    for staff in ["right","left"]:
        var center: float = _staff_center(staff)
        var ink: Color = _ink(staff)
        for line_index in range(5):
            var y: float = center+(float(line_index)-2.0)*gap
            draw_line(Vector2(0,y),Vector2(size.x,y),
                Color(ink,.34),1.3,true)
    # The count-in runs on the same clock, but its leading boundary is
    # intentionally NOT a printed barline: it sits before the clef/header
    # and used to look like an orphaned vertical rule in the score.
    var previous_measure: Dictionary = {}
    for measure in timeline.measures:
        var at: float = float(measure.get("start_beat",0.0))
        if at < left-.7 or at > right+.7:
            previous_measure = measure
            continue
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var boundary_tint: Color = Color(DIM_INK,.70)
        # Opening Verovio glyphs occupy PRE-ROLL space. Moving those
        # ornaments left leaves note beat 0 exactly on the time grid.
        var opening: bool = not timeline.measures.is_empty() and \
            int(measure.get("number", -1)) == \
            int(timeline.measures[0].get("number", -2))
        var header_shift: float = 50.0 if opening else 0.0
        var crowded_meter: bool = _meter_is_crowded(
            measure, previous_measure, gap)
        var barline: Dictionary = _barline_geometry(measure,
            camera_clock, playhead_x, gap)
        if not barline.is_empty() and float(barline["x"]) >= -2.0 and \
                float(barline["x"]) <= size.x+2.0:
            draw_line(Vector2(float(barline["x"]),float(barline["top"])),
                Vector2(float(barline["x"]),float(barline["bottom"])),
                boundary_tint,1.3,true)
        for staff in ["right","left"]:
            var center: float = _staff_center(staff)
            var clef: Dictionary = _clef_for(staff,measure)
            var signatures: Dictionary = measure.get("keys",{})
            var signature: int = int(signatures.get(staff,0))
            var previous_keys: Dictionary = previous_measure.get("keys",{})
            var key_changed: bool = signature != int(previous_keys.get(staff,999))
            if opening or _clef_for(staff,previous_measure) != clef:
                _paint_clef(x-86.0-header_shift-float(absi(signature))*14.0,
                    center,str(clef.get("sign","G")),gap,_ink(staff))
            if key_changed and signature != 0:
                var steps: Array = Geometry.signature_steps(clef, signature)
                for i in range(steps.size()):
                    var glyph_x: float = x-39.0-header_shift-float(steps.size()-i)*14.0
                    var glyph_y: float = Geometry.note_y(int(steps[i]),
                        center+2.0*gap,gap)
                    _paint_accidental(glyph_x,glyph_y,
                        "sharp" if signature > 0 else "flat",
                        _ink(staff),gap)
            if (opening or previous_measure.get("meter",[]) !=
                    measure.get("meter",[])) and not crowded_meter:
                var meter: Array = measure.get("meter",[4,4])
                if meter.size() >= 2:
                    _paint_meter_number(int(meter[0]), x-gap*1.6-header_shift,
                        center-gap*.95, _ink(staff), gap)
                    _paint_meter_number(int(meter[1]), x-gap*1.6-header_shift,
                        center+gap*.8, _ink(staff), gap)
        if crowded_meter:
            _paint_meter_above_staff(measure,x,gap)
        # Bar numbers are small annotations, never part of the notehead
        # stream. No redundant opening number or number beside a floated
        # meter change (both collide with ledger notes in Chopin).
        if not opening and not crowded_meter and x >= 0.0 and x <= size.x:
            draw_string(font,Vector2(x+gap*.4,
                _staff_center("right")-gap*4.3),
                str(int(measure.get("number", 0))),
                HORIZONTAL_ALIGNMENT_LEFT,-1,11,DIM_INK)
        previous_measure = measure
    # All symbols carry their original source onset; NO separate horizontal
    # layout pass or per-note acceleration, including chord tones and rests.
    visible_symbols = 0
    drawn_noteheads.clear()
    if cached_offsets_gap < 0.0 or absf(cached_offsets_gap-gap) > .001:
        cached_head_offsets = Geometry.chord_offsets(ordered_events, gap)
        cached_offsets_gap = gap
    var head_offsets: Dictionary = cached_head_offsets
    var beam_data: Dictionary = _beam_layout(gap, camera_clock,
        playhead_x, head_offsets)
    var beam_stems: Dictionary = beam_data.get("stems", {})
    var compound_ids: Dictionary = {}
    for event in _visible_events(left, right):
        if compound_ids.has(str(event.get("id",""))):
            continue
        var at: float = float(event.get("beat", 0.0))
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var staff: String = str(event.get("staff","right"))
        var ink: Color = _ink(staff)
        if str(event.get("kind","")) == "note":
            var members: Array = _paint_engraved_chord(event,x,gap,ink)
            if not members.is_empty():
                for id in members:
                    compound_ids[id] = true
                visible_symbols += members.size()
                continue
            _paint_note(event,x,gap,ink,
                beam_stems.get(str(event.get("id", "")), {}),
                float(head_offsets.get(str(event.get("id", "")), 0.0)))
        else:
            var voice: String = str(event.get("voice","1"))
            var rest_y: float = _staff_center(staff)+(
                -gap*.3 if voice == "1" else gap*.6)
            _paint_rest(x,rest_y,str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        visible_symbols += 1
    _paint_beams(beam_data, gap)
    _paint_ties(playhead_x,camera_clock,gap)
    _paint_tuplet_brackets(camera_clock,playhead_x,gap)
    draw_line(Vector2(playhead_x,_staff_center("right")-gap*3.8),
        Vector2(playhead_x,_staff_center("left")+gap*3.7),
        PREVIEW_LIGHT,2.0,true)
    # Never put engineering telemetry on top of the actual lesson.
    if OS.get_environment("PIANO_TEACHER_NATIVE_DIAGNOSTICS") == "1":
        var phase: String = "COUNT-IN" if camera_clock < 0.0 and running else \
            "PAUSED" if paused else "PLAYING" if running else "READY"
        draw_string(font,Vector2(14.0,22.0),
            "NATIVE · %s · %.0f px/beat · %.0f BPM · %d events" % [
                phase,timeline.pixels_per_beat,bpm,frame_scanned_events],
            HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)
