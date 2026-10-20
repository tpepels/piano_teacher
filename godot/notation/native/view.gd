extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation falls back to the existing Verovio score as a whole.
const Geometry := preload("res://notation/native/geometry.gd")
const ScoreIndex := preload("res://notation/native/score_index.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
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
var slur_pairs: Array = []
var expected_slur_pairs: Array = []
var slur_extraction_complete := true
var expected_beam_groups: Array = []
var beam_extraction_complete := true
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
    slur_pairs.clear()
    previous_attack_before_measure.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_offsets_gap = -1.0

func set_verovio_glyphs(items: Dictionary, note_items: Dictionary = {},
        tie_items: Dictionary = {}, chord_items: Dictionary = {},
        beam_items: Dictionary = {},
        tuplet_items: Dictionary = {},
        slur_items: Dictionary = {},
        required_slurs: Array = [], slurs_complete: bool = true,
        required_beams: Array = [], beams_complete: bool = true) -> bool:
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
    if not glyphs.load_slur_fragments(slur_items):
        failure_reason = glyphs.error
        return false
    expected_slur_pairs = required_slurs.duplicate(true)
    slur_extraction_complete = slurs_complete
    expected_beam_groups = required_beams.duplicate(true)
    beam_extraction_complete = beams_complete
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
    var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)
    beam_groups = index["beam_groups"]
    beamed_note_ids = index["beamed_note_ids"]
    notation_tuplets = index["notation_tuplets"]
    measure_by_number = index["measure_by_number"]
    ordered_events = index["ordered_events"]
    chord_members = index["chord_members"]
    previous_attack_before_measure = index["previous_attack_before_measure"]
    tie_pairs = index["tie_pairs"]
    slur_pairs = index["slur_pairs"]
    failure_reason = _missing_source_engraving()
    if not failure_reason.is_empty():
        notice = failure_reason
        return false
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_offsets_gap = -1.0
    cached_head_offsets.clear()
    failure_reason = ""
    native_ready = true
    queue_redraw()
    return true

# Only native compositor fragments with unambiguous original Verovio ink.
# Missing engraving falls back to the existing full Verovio score, rather than
# drawing approximate beams, stems, chord shapes, tuplets or omitted slurs.
func _missing_source_engraving() -> String:
    if not beam_extraction_complete:
        return "Source Verovio beam extraction failed"
    for key in expected_beam_groups:
        if not glyphs.beam_textures.has(str(key)):
            return "Missing original Verovio beam: "+str(key)
    if not slur_extraction_complete:
        return "Source Verovio slur extraction failed"
    for group in notation_tuplets:
        var ids := PackedStringArray()
        for event in group.get("events",[]):
            if str(event.get("kind","")) == "note":
                ids.append(str(event.get("id","")))
        # Some imported MIDI notes carry a one-event start/stop marker.
        # Those do not have a multi-note Verovio number/bracket fragment:
        # their actual beat duration remains intact; invent no symbol.
        if ids.size() < 2:
            continue
        if not glyphs.has_tuplet("|".join(ids),false):
            return "Missing engraved Verovio tuplet: "+("|".join(ids))
    for leader_id in chord_members:
        var event: Dictionary = {}
        for candidate in chord_members[leader_id]:
            if str(candidate.get("id","")) == str(leader_id):
                event = candidate
                break
        if event.is_empty():
            return "Missing original chord leader: "+str(leader_id)
        var key: String = _chord_template_key(event)
        if key.is_empty() or not glyphs.has_chord(key):
            return "Missing engraved Verovio chord: "+str(leader_id)+ \
                " (pattern="+key+", atlas="+ \
                str(glyphs.chord_textures.size())+" templates)"
        if beamed_note_ids.has(str(leader_id)) and ( \
                not glyphs.has_chord_heads(key) or \
                not glyphs.has_chord_stem(key)):
            return "Missing Verovio beamed chord components: "+str(leader_id)
    for pair in expected_slur_pairs:
        if not pair is Array or pair.size() != 2:
            return "Invalid original Verovio slur identity"
        var key: String = str(pair[0])+"|"+str(pair[1])
        if not glyphs.slur_metadata.has(key) or \
                glyphs.slur_note_ids(key) != pair:
            return "Missing original Verovio slur: "+key
    return ""


func _engraved_beam_groups(model: Dictionary) -> Dictionary:
    return ScoreIndex.source_beam_groups(model, glyphs)


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



# MusicXML determines each boundary's structure. The first measure has
# no moving barline unless it explicitly opens with a repeat sign. At later
# boundaries an explicit left barline overrides the previous default regular
# right line. A closing double/repeat line belongs to the previous measure.
func _barline_geometry(measure: Dictionary, clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    return BarlineLayout.boundary(timeline.measures, measure, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)


func _terminal_barline_geometry(clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    return BarlineLayout.terminal(timeline.measures, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)


func _barline_strokes(style: String, gap: float) -> Array:
    return BarlineLayout.strokes(style, gap)


func _paint_barline(info: Dictionary, gap: float) -> void:
    if info.is_empty():
        return
    var style: String = str(info.get("style","regular"))
    var bars: Array = _barline_strokes(style,gap)
    if bars.is_empty():
        return
    var x: float = float(info["x"])
    var top: float = float(info["top"])
    var bottom: float = float(info["bottom"])
    var ink: Color = Color(DIM_INK,.76)
    for stroke in bars:
        var sx: float = x+float(stroke["offset"])
        var width: float = float(stroke["width"])
        if style in ["dashed","dotted"]:
            var length: float = gap*(.65 if style=="dashed" else .13)
            var skip: float = gap*(.35 if style=="dashed" else .27)
            var at: float = top
            while at < bottom:
                draw_line(Vector2(sx,at),Vector2(sx,minf(bottom,at+length)),
                    ink,width,true)
                at += length+skip
        else:
            draw_line(Vector2(sx,top),Vector2(sx,bottom),ink,width,true)
    var repetition: String = str(info.get("repeat",""))
    if repetition not in ["forward","backward","both"]:
        return
    var positions: Array = []
    if repetition in ["backward","both"]:
        positions.append(x-gap*.92)
    if repetition in ["forward","both"]:
        positions.append(x+gap*.56)
    var box: Array = glyphs.bounds.get("repeat_dot",[])
    if box.size()!=4:
        return
    var unit: float = gap/250.0
    var center_offset: float = (float(box[1])+float(box[3])*.5)*unit
    for dot_x in positions:
        for staff in ["right","left"]:
            var middle: float = _staff_center(staff)
            for dot_y in [middle-gap*.5,middle+gap*.5]:
                glyphs.paint(self,"repeat_dot",float(dot_x),
                    dot_y-center_offset,gap,ink,true)


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


func _paint_rhythm_dots(x: float, y: float, dots: int,
        ink: Color, gap: float) -> void:
    for index in range(dots):
        glyphs.paint(self, "augmentation_dot",
            x+gap*1.05+float(index)*gap*.63, y-gap*.24,
            gap, ink, true)


func _paint_tuplet_brackets(clock: float, playhead_x: float,
        gap: float) -> void:
    # Authentic separated Verovio number/bracket masks only. Every group
    # was validated on lesson load; no Godot-drawn ratio, digit or hook.
    for group in notation_tuplets:
        var events: Array = group.get("events",[])
        if events.size() < 2:
            continue
        var ids := PackedStringArray()
        var note_events: Array = []
        for event in events:
            if str(event.get("kind","")) == "note":
                ids.append(str(event.get("id","")))
                note_events.append(event)
        if note_events.size() < 2:
            continue
        # Verovio's image is anchored to actual noteheads, not rests that
        # precede/follow them within the MusicXML tuplet.
        var first: Dictionary = note_events[0]
        var last: Dictionary = note_events[-1]
        var x0: float = timeline.screen_x(
            float(first.get("beat",0.0)),clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(
            float(last.get("beat",0.0)),clock,playhead_x,play_from_beat)
        if x1 < -50.0 or x0 > size.x+50.0:
            continue
        glyphs.paint_tuplet(self,"|".join(ids),x0,x1,
            _event_y(first,gap),gap,
            _ink(str(group.get("staff","right"))))


func _paint_rest(x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    glyphs.paint(self, "rest_" + note_type, x, y, gap, ink, true)
    _paint_rhythm_dots(x, y, dots, ink, gap)


func _paint_clef(x: float, center: float, clef: Dictionary,
        gap: float, ink: Color) -> void:
    var sign: String = str(clef.get("sign","G"))
    var line: int = int(clef.get("line", 2 if sign == "G" else 4 if sign == "F" else 3))
    var octave: int = int(clef.get("octave_change",0))
    var name: String = {"G":"clef_g", "F":"clef_f", "C":"clef_c"}.get(sign, "")
    if name.is_empty() or line < 1 or line > 5:
        return
    # The reference mark is exactly MusicXML's numbered staff line:
    # 1 is bottom, 5 is top. Changing it must NOT transpose note time.
    var origin_y: float = center+(3.0-float(line))*gap
    var variant: String = ""
    if octave == -1:
        variant = name+"_8vb"
    elif octave == 1:
        variant = name+"_8va"
    elif octave == -2:
        variant = name+"_15mb"
    elif octave == 2:
        variant = name+"_15ma"
    if not variant.is_empty() and glyphs.textures.has(variant):
        name = variant
    glyphs.paint(self,name,x,origin_y,gap,ink,true)
    # No separate clef numeral is available in installed Leipzig. Any
    # unsupported combined variant must be rejected by Geometry.supported.


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
    var extents: Dictionary = _chord_extents(event,1.0)
    var direction: String = "up" if bool(extents["up"]) else "down"
    return "%s|%s|%s" % [
        str(event.get("note_type","quarter")),direction,",".join(names)]


func _paint_engraved_chord(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {}) -> Array:
    var key: String = _chord_template_key(event)
    if key.is_empty() or not glyphs.has_chord(key):
        return []
    var beamed: bool = beamed_note_ids.has(str(event.get("id","")))
    if beamed and (beam_stem.is_empty() or \
            not glyphs.has_chord_heads(key) or \
            not glyphs.has_chord_stem(key)):
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
    if beamed:
        var extrema: Dictionary = _chord_extents(event,gap,cached_head_offsets)
        var stem_up: bool = bool(beam_stem.get("up",true))
        var from_y: float = float(extrema[
            "bottom_y" if stem_up else "top_y"])
        if not glyphs.paint_chord_stem(self,key,x,from_y,
                float(beam_stem["tip_y"]),gap,ink):
            return []
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
    # Beamed single-note attacks use an actual Verovio stem alpha mask;
    # the separate source beam determines its endpoint and stem direction.
    if not beam_stem.is_empty() and not bool(event.get("chord",false)):
        glyphs.paint_note_stem(self,kind,bool(beam_stem["up"]),
            x,y,float(beam_stem["tip_y"]),gap,ink)
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
        var group_ids := PackedStringArray()
        for event in group:
            group_ids.append(str(event.get("id","")))
        var source_key: String = "|".join(group_ids)
        if glyphs.beam_metadata.has(source_key):
            up = bool(glyphs.beam_metadata[source_key].get("stem_up",up))
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
        # The source image supplies the entire beam contour and each
        # measured stem tip. The compositor never estimates a slope.
        var art_key: String = source_key
        var art_tips: Array = glyphs.beam_tips(art_key)
        if art_tips.size() != members.size():
            continue
        for index in range(members.size()):
            var member: Dictionary = members[index]
            var tip: float = float(member["head_y"])+ \
                float(art_tips[index])*gap/250.0
            member["tip_y"] = tip
            members[index] = member
            stems[str(member["id"])] = {"up":up, "tip_y":tip,
                "x":float(member["x"])}
        drawn_groups.append({"members":members,
            "staff":str(group[0].get("staff", "right")),
            "up":up, "art_key":art_key})
    return {"stems":stems, "groups":drawn_groups}


func _paint_beams(data: Dictionary, gap: float) -> void:
    # There is no primitive-polygon fallback: load_score() already checked
    # that each expected multi-note group has genuine Verovio beam ink.
    for group in data.get("groups",[]):
        var members: Array = group.get("members",[])
        if members.size() < 2:
            continue
        var first: Dictionary = members[0]
        var last: Dictionary = members[-1]
        if float(last["head_x"]) < -40.0 or \
                float(first["head_x"]) > size.x+40.0:
            continue
        var anchors: Array = []
        for member in members:
            anchors.append(float(member["head_x"]))
        glyphs.paint_beam(self,str(group["art_key"]),anchors,
            float(first["head_y"]),gap,
            _ink(str(group.get("staff","right"))))


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
func _paint_slurs(playhead_x: float,clock: float,gap: float) -> void:
    for pair in slur_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var x0: float = timeline.screen_x(float(first.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(last.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        if x0 > size.x+50.0 or x1 < -50.0:
            continue
        x0 += float(cached_head_offsets.get(str(first.get("id","")),0.0))
        x1 += float(cached_head_offsets.get(str(last.get("id","")),0.0))
        if x1 <= x0:
            continue
        glyphs.paint_slur(self,str(pair["key"]),x0,_event_y(first,gap),
            x1,_event_y(last,gap),gap,
            _ink(str(first.get("staff","right"))))


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
         # Opening Verovio glyphs occupy PRE-ROLL space. Moving those
        # ornaments left leaves note beat 0 exactly on the time grid.
        var opening: bool = not timeline.measures.is_empty() and \
            int(measure.get("number", -1)) == \
            int(timeline.measures[0].get("number", -2))
        # Increase the pre-roll header-to-first-attack breathing room.
        # Move only the ornament group, never any note beat coordinate.
        var header_shift: float = 76.0 if opening else 0.0
        var crowded_meter: bool = _meter_is_crowded(
            measure, previous_measure, gap)
        var barline: Dictionary = _barline_geometry(measure,
            camera_clock, playhead_x, gap)
        if not barline.is_empty() and float(barline["x"]) >= -gap*2.0 and \
                float(barline["x"]) <= size.x+gap*2.0:
            _paint_barline(barline,gap)
        for staff in ["right","left"]:
            var center: float = _staff_center(staff)
            var clef: Dictionary = _clef_for(staff,measure)
            var signatures: Dictionary = measure.get("keys",{})
            var signature: int = int(signatures.get(staff,0))
            var previous_keys: Dictionary = previous_measure.get("keys",{})
            var key_changed: bool = signature != int(previous_keys.get(staff,999))
            if opening or _clef_for(staff,previous_measure) != clef:
                _paint_clef(x-86.0-header_shift-float(absi(signature))*14.0,
                    center,clef,gap,_ink(staff))
            if key_changed:
                # Cancelling an old signature requires visible naturals,
                # even when the new signature is C major (zero accidentals).
                var previous_fifths: int = int(previous_keys.get(staff,0))
                var cancelled: Array = ([] if opening else
                    Geometry.key_cancellation_steps(clef,previous_fifths,signature))
                var incoming: Array = Geometry.signature_steps(clef,signature)
                var change_marks: Array = []
                for step in cancelled:
                    change_marks.append({"step":step,"accidental":"natural"})
                for step in incoming:
                    change_marks.append({"step":step,"accidental":
                        "sharp" if signature > 0 else "flat"})
                for i in range(change_marks.size()):
                    var mark: Dictionary = change_marks[i]
                    var glyph_x: float = x-39.0-header_shift- \
                        float(change_marks.size()-i)*14.0
                    var glyph_y: float = Geometry.note_y(int(mark["step"]),
                        center+2.0*gap,gap)
                    _paint_accidental(glyph_x,glyph_y,
                        str(mark["accidental"]),_ink(staff),gap)
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
    # The actual ending of the last measure has its own terminal barline.
    # It must not disappear simply because no following measure exists.
    var terminal: Dictionary = _terminal_barline_geometry(
        camera_clock,playhead_x,gap)
    if not terminal.is_empty() and float(terminal["x"]) >= -gap*2.0 and \
            float(terminal["x"]) <= size.x+gap*2.0:
        _paint_barline(terminal,gap)
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
            var members: Array = _paint_engraved_chord(event,x,gap,ink,
                beam_stems.get(str(event.get("id","")), {}))
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
    _paint_slurs(playhead_x,camera_clock,gap)
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
