extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation falls back to the existing Verovio score as a whole.
const Geometry := preload("res://notation/native/geometry.gd")
const SpacingLayout := preload("res://notation/native/spacing_layout.gd")
const ScoreIndex := preload("res://notation/native/score_index.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
const AnnotationPainter := preload("res://notation/native/annotations.gd")
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT
const MAX_STAFF_GAP := 22.0

var glyphs = VerovioGlyphs.new()
var annotation_painter = AnnotationPainter.new()
var annotation_fragments: Dictionary = {}
var annotation_error := ""
var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var selected_density := 0.0
var staff_gap_limit := MAX_STAFF_GAP
var configured_density: float = Timeline.DEFAULT_PIXELS_PER_BEAT
var beam_groups: Array = []
var beamed_note_ids: Dictionary = {}
var beam_stem_up_by_note: Dictionary = {}
var chord_members: Dictionary = {}
var chord_leader_by_note: Dictionary = {}
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
var spacing_layout = SpacingLayout.new()
# Public cached anchors for expression/feedback painters; values are pixels.
var cached_rest_y: Dictionary = {}
var cached_group_offsets: Dictionary = {}
var layout_head_spaces: Dictionary = {}
var layout_group_spaces: Dictionary = {}
var layout_rest_spaces: Dictionary = {}
var layout_accidental_spaces: Dictionary = {}
var layout_note_components: Array = []
var layout_source_heads: Dictionary = {}
var layout_source_columns: Dictionary = {}
var layout_components: Array = []
var layout_ink_reach := 0.0
var cached_head_offsets: Dictionary = {}
var cached_accidental_offsets: Dictionary = {}
var cached_offsets_gap := -1.0
var fragment_indices: Dictionary = {}
var previous_measure_by_number: Dictionary = {}
var barline_context_by_number: Dictionary = {}
var staff_pitch_factors: Dictionary = {}
var frame_scanned_events := 0
var frame_visible_beam_groups := 0

func clear_score() -> void:
    super.clear_score()
    timeline.set_density(configured_density)
    staff_gap_limit = MAX_STAFF_GAP
    native_ready = false
    failure_reason = ""
    visible_symbols = 0
    drawn_noteheads.clear()
    beam_groups.clear()
    beamed_note_ids.clear()
    beam_stem_up_by_note.clear()
    chord_members.clear()
    chord_leader_by_note.clear()
    notation_tuplets.clear()
    measure_by_number.clear()
    ordered_events.clear()
    tie_pairs.clear()
    slur_pairs.clear()
    previous_attack_before_measure.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_rest_y.clear()
    cached_group_offsets.clear()
    layout_head_spaces.clear()
    layout_group_spaces.clear()
    layout_rest_spaces.clear()
    layout_accidental_spaces.clear()
    layout_note_components.clear()
    layout_source_heads.clear()
    layout_source_columns.clear()
    layout_components.clear()
    fragment_indices.clear()
    previous_measure_by_number.clear()
    barline_context_by_number.clear()
    staff_pitch_factors.clear()
    cached_accidental_offsets.clear()
    cached_offsets_gap = -1.0


func set_density(value: float) -> bool:
    if not super.set_density(value):
        return false
    configured_density = value
    return true


func set_density_from_env() -> bool:
    if not super.set_density_from_env():
        return false
    configured_density = timeline.pixels_per_beat
    return true


func set_annotation_fragments(items: Dictionary, error: String = "") -> void:
    annotation_fragments = items
    annotation_error = error


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
    # The rhythmic preference remains one linear clock. Actual source ink
    # feasibility is established by bounded engraving below, before playback.
    var density: float = minf(480.0,Geometry.required_density(
        timeline.model.get("notation_events", []), configured_density,INF))
    var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)
    beam_groups = index["beam_groups"]
    beamed_note_ids = index["beamed_note_ids"]
    beam_stem_up_by_note = index["beam_stem_up_by_note"]
    notation_tuplets = index["notation_tuplets"]
    measure_by_number = index["measure_by_number"]
    ordered_events = index["ordered_events"]
    chord_members = index["chord_members"]
    chord_leader_by_note = index["chord_leader_by_note"]
    previous_attack_before_measure = index["previous_attack_before_measure"]
    tie_pairs = index["tie_pairs"]
    slur_pairs = index["slur_pairs"]
    _index_fragments()
    failure_reason = _missing_source_engraving()
    if not failure_reason.is_empty():
        notice = failure_reason
        return false
    staff_gap_limit = MAX_STAFF_GAP
    var layout: Dictionary = _prepare_spacing(density,staff_gap_limit)
    if not bool(layout.get("ok",false)):
        staff_gap_limit = 17.0
        layout = _prepare_spacing(density,staff_gap_limit)
    if not bool(layout.get("ok",false)):
        failure_reason = str(layout.get("reason","Source ink cannot fit bounded engraving"))
        notice = failure_reason
        return false
    selected_density = float(layout["density"])
    if not timeline.set_score_density(selected_density):
        failure_reason = timeline.last_error
        notice = failure_reason
        return false
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_offsets_gap = -1.0
    if not _cache_spacing(_gap()):
        notice = failure_reason
        return false
    if not annotation_error.is_empty():
        failure_reason = "Source annotation extraction failed: " + annotation_error
        notice = failure_reason
        return false
    if not annotation_painter.bind({"annotation_fragments":annotation_fragments}, candidate, self):
        failure_reason = annotation_painter.error
        notice = failure_reason
        return false
    failure_reason = ""
    native_ready = true
    queue_redraw()
    return true

# Only native compositor fragments with unambiguous original Verovio ink.
# Missing engraving falls back to the existing full Verovio score, rather than
# drawing approximate beams, stems, chord shapes, tuplets or omitted slurs.
func _missing_source_engraving() -> String:
    for measure in timeline.measures:
        for staff in ["right","left"]:
            var clef: Dictionary = _clef_for(staff,measure)
            var octave: int = int(clef.get("octave_change",0))
            var suffix: String = {1:"_8va",-1:"_8vb",2:"_15ma",-2:"_15mb"}.get(octave,"")
            var name: String = "clef_"+str(clef.get("sign","G")).to_lower()+suffix
            if not glyphs.textures.has(name):
                return "Missing original Verovio clef variant: "+name
    if not beam_extraction_complete:
        return "Source Verovio beam extraction failed"
    for key in expected_beam_groups:
        if not glyphs.beam_textures.has(str(key)):
            return "Missing original Verovio beam: "+str(key)
    if not slur_extraction_complete:
        return "Source Verovio slur extraction failed"
    for group in notation_tuplets:
        if group.has("key"):
            if not glyphs.has_tuplet(str(group["key"]),str(group.get("bracket","yes")) == "yes",
                    str(group.get("show_number","actual")) != "none"):
                return "Missing original source tuplet group: "+str(group["key"])
            continue
        var ids := PackedStringArray()
        for event in group.get("events",[]):
            if str(event.get("kind","")) in ["note","rest"]:
                ids.append(str(event.get("id","")))
        # Some imported MIDI notes carry a one-event start/stop marker.
        # Those do not have a multi-note Verovio number/bracket fragment:
        # their actual beat duration remains intact; invent no symbol.
        if ids.size() < 2:
            continue
        if not glyphs.has_tuplet("|".join(ids),false,
                str(group.get("show_number","actual")) != "none"):
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
    return size.y * (.36 if hand == "right" else .69)

func _gap() -> float:
    if cached_staff_gap > 0.0 and absf(cached_gap_height - size.y) < .001:
        return cached_staff_gap
    # Reserve actual room for ledger notes ABOVE and BELOW both staves.
    # The former raster crop clipped high notes because it only knew staff
    # rails, not the extreme noteheads. Fit the full semantic pitch range
    # once per frame/viewport, uniformly for both hands.
    var gap: float = clampf(size.y * .042, 8.5, staff_gap_limit)
    if timeline.model.is_empty():
        return gap
    for staff in staff_pitch_factors:
        var center: float = _staff_center(str(staff))
        var factors: Array = staff_pitch_factors[staff]
        if float(factors[0]) < -.001:
            gap = minf(gap,(center-32.0)/-float(factors[0]))
        if float(factors[1]) > .001:
            gap = minf(gap,(size.y-32.0-center)/float(factors[1]))
    # Reserve the interstaff region as well as the canvas edges. The cached
    # factors include actual flag, stem, ledger, accidental and rest ink.
    if staff_pitch_factors.has("right") and staff_pitch_factors.has("left"):
        var shared: float = float(staff_pitch_factors["right"][1])-float(staff_pitch_factors["left"][0])
        if shared > .001:
            gap = minf(gap,(_staff_center("left")-_staff_center("right")-12.0)/shared)
    cached_staff_gap = gap
    cached_gap_height = size.y
    return cached_staff_gap

func _index_fragments() -> void:
    previous_measure_by_number.clear()
    barline_context_by_number.clear()
    var previous: Dictionary = {}
    for measure in timeline.measures:
        var number: int = int(measure.get("number",0))
        previous_measure_by_number[number] = previous
        barline_context_by_number[number] = [measure] if previous.is_empty() else [previous,measure]
        previous = measure
    fragment_indices = {
        "beams":ScoreIndex.interval_index(beam_groups,
            func(group: Array) -> float: return float(group[0].get("beat",0.0)),
            func(group: Array) -> float: return float(group[-1].get("beat",0.0))),
        "ties":ScoreIndex.interval_index(tie_pairs,
            func(pair: Dictionary) -> float: return float(pair["first"].get("beat",0.0)),
            func(pair: Dictionary) -> float: return float(pair["last"].get("beat",0.0))),
        "slurs":ScoreIndex.interval_index(slur_pairs,
            func(pair: Dictionary) -> float: return float(pair["first"].get("beat",0.0)),
            func(pair: Dictionary) -> float: return float(pair["last"].get("beat",0.0))),
        "tuplets":ScoreIndex.interval_index(notation_tuplets,
            func(group: Dictionary) -> float: return float(group["events"][0].get("beat",0.0)),
            func(group: Dictionary) -> float: return float(group["events"][-1].get("beat",0.0))),
        "measures":ScoreIndex.interval_index(timeline.measures,
            func(measure: Dictionary) -> float: return float(measure.get("start_beat",0.0)),
            func(measure: Dictionary) -> float: return float(measure.get("end_beat",0.0))) }
    staff_pitch_factors = {"right":[2.0,2.0],"left":[2.0,2.0]}
    for event in ordered_events:
        if str(event.get("kind","")) != "note":
            continue
        var staff: String = str(event.get("staff","right"))
        var step: int = Geometry.staff_step(event.get("spelling",{}),_clef_for(staff,_measure_for(event)))
        var factor: float = 2.0-float(step)*.5
        staff_pitch_factors[staff][0] = minf(float(staff_pitch_factors[staff][0]),factor)
        staff_pitch_factors[staff][1] = maxf(float(staff_pitch_factors[staff][1]),factor)


func _visible_fragments(kind: String, clock: float, playhead_x: float) -> Array:
    var current: float = timeline.musical_beat(clock,play_from_beat)
    var margin: float = maxf(100.0,staff_gap_limit*5.0)
    return ScoreIndex.visible_intervals(fragment_indices.get(kind,{}),
        current-(playhead_x+margin)/timeline.pixels_per_beat,
        current+(size.x-playhead_x+margin)/timeline.pixels_per_beat)


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
    var context: Array = barline_context_by_number.get(int(measure.get("number",0)),[])
    var info: Dictionary = BarlineLayout.boundary(context, measure, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = _barline_segments(str(info.get("style","regular")),gap)
    return info


func _terminal_barline_geometry(clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    var info: Dictionary = BarlineLayout.terminal(timeline.measures, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = _barline_segments(str(info.get("style","regular")),gap)
    return info


func _barline_segments(style: String, gap: float) -> Array:
    if style in ["tick","short"]:
        var segments: Array = []
        for staff in ["right","left"]:
            var center: float = _staff_center(staff)
            segments.append({
                "top":center-gap*(2.5 if style == "tick" else 1.0),
                "bottom":center-gap*1.5 if style == "tick" else center+gap})
        return segments
    return [{"top":_staff_center("right")-2.0*gap,
        "bottom":_staff_center("left")+2.0*gap}]


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
    var ink: Color = Color(DIM_INK,.76)
    for stroke in bars:
        var sx: float = x+float(stroke["offset"])
        var width: float = float(stroke["width"])
        for segment in info.get("segments",_barline_segments(style,gap)):
            var top: float = float(segment["top"])
            var bottom: float = float(segment["bottom"])
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
            draw_line(Vector2(x-gap*.82, line_y),
                Vector2(x+gap*.82, line_y), Color(ink, .70), 1.35, true)
            line_step -= 2
    elif step > 8:
        var line_step: int = 10
        while line_step <= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            draw_line(Vector2(x-gap*.82, line_y),
                Vector2(x+gap*.82, line_y), Color(ink, .70), 1.35, true)
            line_step += 2

func _paint_accidental(x: float, y: float,
        value: String, ink: Color, gap: float,
        head_offset: float = INF) -> void:
    var name: String = str(Geometry.ACCIDENTAL_GLYPHS.get(value, ""))
    if not name.is_empty():
        var offset: float = head_offset if is_finite(head_offset) else -gap*1.15
        glyphs.paint(self, name, x+offset, y, gap, ink, true)


func _paint_note_accidental(event: Dictionary, x: float, y: float,
        ink: Color, gap: float) -> void:
    var accidental: String = str(event.get("accidental",""))
    if not accidental.is_empty() and accidental != "null":
        _paint_accidental(x,y,accidental,ink,gap,
            float(cached_accidental_offsets.get(str(event.get("id","")),-gap*1.15)))


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
    for group in _visible_fragments("tuplets",clock,playhead_x):
        var events: Array = group.get("events",[])
        if events.size() < 2:
            continue
        var ids := PackedStringArray()
        var note_events: Array = []
        for event in events:
            if str(event.get("kind","")) in ["note","rest"]:
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
        x0 += float((cached_group_offsets if str(first.get("kind","")) == "rest" else cached_head_offsets).get(str(first.get("id","")),0.0))
        x1 += float((cached_group_offsets if str(last.get("kind","")) == "rest" else cached_head_offsets).get(str(last.get("id","")),0.0))
        if x1 < -50.0 or x0 > size.x+50.0:
            continue
        var origin_y: float = float(cached_rest_y.get(str(first.get("id","")),_staff_center(str(first.get("staff","right"))))) if str(first.get("kind","")) == "rest" else _event_y(first,gap)
        glyphs.paint_tuplet(self,str(group.get("key","|".join(ids))),x0,x1,
            origin_y,gap,
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
    if not variant.is_empty():
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


func _source_stem_bounds(event: Dictionary, up: bool) -> Array:
    if chord_members.has(str(event.get("id",""))):
        return glyphs.chord_stem_bounds.get(_chord_template_key(event),[])
    var key: String = str(event.get("note_type","eighth"))+(
        "_up" if up else "_down")
    return glyphs.note_stem_bounds.get(key,[])


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
    # A source beam can force a chord opposite to its isolated pitch rule.
    # Its direction selects BOTH displaced heads and the stem-side mask,
    # including during load validation, before a frame has been painted.
    var up: bool = bool(beam_stem_up_by_note.get(
        str(event.get("id","")),extents["up"]))
    var direction: String = "up" if up else "down"
    return "%s|%s|%s" % [
        str(event.get("note_type","quarter")),direction,",".join(names)]


func _engraved_head_offsets(gap: float) -> Dictionary:
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
        var positions: Array = glyphs.chord_heads(_chord_template_key(leader))
        if positions.size() != members.size():
            continue
        members.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < \
                Geometry.diatonic_index(b.get("spelling",{})))
        for i in range(members.size()):
            offsets[str(members[i].get("id",""))] = \
                float(positions[i][0])*gap/250.0
    return offsets


func _symbol_parts(name: String, offset: Vector2) -> Array:
    return SpacingLayout.translated(spacing_layout.components(
        glyphs.textures[name],glyphs.bounds[name],true),offset)


func _prepare_spacing(preferred: float, gap: float) -> Dictionary:
    var source_heads: Dictionary = _engraved_head_offsets(1.0)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        ordered_events,1.0,source_heads,glyphs.bounds)
    var groups: Array = []
    var children: Dictionary = {}
    var beam_tips: Dictionary = {}
    for beam in beam_groups:
        var ids := PackedStringArray()
        for event in beam:
            ids.append(str(event.get("id","")))
        var tips: Array = glyphs.beam_tips("|".join(ids))
        for i in range(beam.size()):
            beam_tips[str(beam[i].get("id",""))] = float(tips[i])/250.0
    for event in ordered_events:
        var id: String = str(event.get("id",""))
        if children.has(id):
            continue
        var staff: String = str(event.get("staff","right"))
        var kind: String = str(event.get("note_type","quarter"))
        var members: Array = chord_members.get(id,[event])
        var parts: Array = []
        var ledgers: Array = []
        var minimum := 0.0
        var maximum := 0.0
        var has_accidental := false
        var source_accidentals: Array = []
        var rest: bool = str(event.get("kind","")) == "rest"
        var origin_y: float = _event_y(event,1.0)-_staff_center(staff) if not rest else 0.0
        if rest:
            parts = _symbol_parts("rest_"+kind,Vector2.ZERO)
        elif chord_members.has(id):
            var key: String = _chord_template_key(event)
            if beamed_note_ids.has(id):
                parts = SpacingLayout.translated(spacing_layout.components(
                    glyphs.chord_heads_textures[key],glyphs.chord_heads_bounds[key]),Vector2(0,origin_y))
            else:
                parts = SpacingLayout.translated(spacing_layout.components(
                    glyphs.chord_textures[key],glyphs.chord_metadata[key]["bounds"]),Vector2(0,origin_y))
        elif beamed_note_ids.has(id):
            parts = _symbol_parts("head_"+(kind if kind in ["whole","half"] else "black"),Vector2(0,origin_y))
        else:
            var up: bool = bool(_chord_extents(event,1.0)["up"])
            var key: String = "whole" if kind == "whole" else kind+("_up" if up else "_down")
            parts = SpacingLayout.translated(spacing_layout.components(
                glyphs.note_textures[key],glyphs.note_bounds[key]),Vector2(0,origin_y))
        if not rest and beamed_note_ids.has(id):
            var up: bool = bool(beam_stem_up_by_note[id])
            var extrema: Dictionary = _chord_extents(event,1.0)
            var from_y: float = float(extrema["bottom_y" if up else "top_y"])-_staff_center(staff)
            var tip_y: float = from_y+float(beam_tips[id])
            var stem_box: Array = _source_stem_bounds(event,up)
            # This is the exact destination of the source stem alpha mask.
            parts.append(Rect2(float(stem_box[0])/250.0,minf(from_y,tip_y),
                float(stem_box[2])/250.0,absf(tip_y-from_y)))
        for member in members:
            var member_id: String = str(member.get("id",""))
            if member_id != id:
                children[member_id] = true
            var head_x: float = float(source_heads.get(member_id,0.0))
            minimum = minf(minimum,head_x)
            maximum = maxf(maximum,head_x)
            var y: float = _event_y(member,1.0)-_staff_center(staff) if not rest else 0.0
            var dots: int = int(member.get("dots",0))
            for dot in range(dots):
                parts.append_array(_symbol_parts("augmentation_dot",Vector2(
                    head_x+1.05+float(dot)*.63,y-.24)))
            if rest:
                continue
            if accidentals.has(member_id):
                has_accidental = true
                var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(member["accidental"])])
                source_accidentals.append_array(_symbol_parts(name,Vector2(head_x+float(accidentals[member_id]),y)))
            var step: int = Geometry.staff_step(member.get("spelling",{}),
                _clef_for(staff,_measure_for(member)))
            if step <= -2 or step >= 10:
                var ledger: int = -2 if step <= -2 else 10
                while (ledger >= step if step <= -2 else ledger <= step):
                    ledgers.append(Rect2(head_x-.82,Geometry.note_y(ledger,2.0,1.0)-.04,1.64,.08))
                    ledger += -2 if step <= -2 else 2
        groups.append({"id":id,"members":members,"staff":staff,
            "beat":float(event.get("beat",0.0)),"parts":parts,"box":SpacingLayout.footprint(parts),
            "ledgers":ledgers,"rest":rest,
            "min_head":minimum,"max_head":maximum,"has_accidental":has_accidental,
            "source_accidentals":source_accidentals})
    # A rest has no pitch. Place its original source glyph in a clear voice
    # lane before solving horizontal constraints; its clock remains exact.
    var rest_spaces: Dictionary = {}
    for group in groups:
        if not bool(group["rest"]):
            continue
        var base_parts: Array = group["parts"]
        var placed := false
        for candidate in range(41):
            var y: float = 0.0 if candidate == 0 else \
                float((candidate+1)/2)*(1.0 if candidate%2 == 0 else -1.0)
            var trial: Array = SpacingLayout.translated(base_parts,Vector2(0,y))
            var clear := true
            for other in groups:
                if other == group or str(other["staff"]) != str(group["staff"]):
                    continue
                if bool(other["rest"]) and not rest_spaces.has(str(other["id"])):
                    continue
                # Reserve the whole horizontal translation budget so later
                # head packing never moves ink through this independent rest.
                var distance: float = (float(other["beat"])-float(group["beat"]))*preferred/gap
                var reserve: float = 0.0 if bool(other["rest"]) else 4.0
                var trial_box: Rect2 = SpacingLayout.footprint(trial).grow(.12)
                var other_box: Rect2 = Rect2(other["box"].position+Vector2(distance-reserve,0),
                    other["box"].size+Vector2(reserve*2.0,0)).grow(.12)
                if not trial_box.intersects(other_box):
                    continue
                for a in trial:
                    for b in other["parts"]:
                        if a.grow(.12).intersects(Rect2(b.position+Vector2(distance-reserve,0),b.size+Vector2(reserve*2.0,0)).grow(.12)):
                            clear = false
                            break
                    if not clear:
                        break
                if not clear:
                    break
            if clear:
                group["parts"] = trial
                group["box"] = SpacingLayout.footprint(trial)
                rest_spaces[str(group["id"])] = y
                placed = true
                break
        if not placed:
            return {"ok":false,"reason":"No clear original rest lane: "+str(group["id"])}
    # Independent simultaneous voices are not a chord and retain all their
    # identities. Put their source stem sides in the least crowded order;
    # their common musical onset is unchanged.
    groups.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        if float(a["beat"]) != float(b["beat"]):
            return float(a["beat"]) < float(b["beat"])
        if a["staff"] != b["staff"]:
            return str(a["staff"]) < str(b["staff"])
        var ab: float = SpacingLayout.separation(a["parts"],b["parts"])
        var ba: float = SpacingLayout.separation(b["parts"],a["parts"])
        if is_finite(ab) and is_finite(ba) and absf(ab-ba) > .0001:
            return ab < ba
        return str(a["id"]) < str(b["id"]))
    var left := 0.0
    var right := 0.0
    for group in groups:
        for part in group["parts"]:
            left = minf(left,part.position.x)
            right = maxf(right,part.end.x)
    for group in groups:
        group["left"] = left
        group["sweep_reach"] = right-left+4.0+SpacingLayout.CLEARANCE
    # At ordinary rhythmic intervals reserve the complete accidental column
    # before the attack. This is a reading preference, bounded by the practical
    # scale; the component solver still proves every dense source collision.
    var density: float = preferred
    for j in range(groups.size()):
        if not bool(groups[j]["has_accidental"]):
            continue
        var current_left := INF
        var current_box := Rect2()
        var reading_parts: Array = groups[j]["parts"].duplicate()
        reading_parts.append_array(groups[j]["source_accidentals"])
        for part in reading_parts:
            current_left = minf(current_left,part.position.x)
            current_box = part if not current_box.has_area() else current_box.merge(part)
        for i in range(j-1,-1,-1):
            var distance: float = float(groups[j]["beat"])-float(groups[i]["beat"])
            if distance > 2.0:
                break
            if distance < .125 or groups[i]["staff"] != groups[j]["staff"]:
                continue
            var previous_box := Rect2()
            for part in groups[i]["parts"]:
                previous_box = part if not previous_box.has_area() else previous_box.merge(part)
            if current_box.position.y >= previous_box.end.y or previous_box.position.y >= current_box.end.y:
                continue
            density = maxf(density,minf(480.0,(previous_box.end.x-current_left+.3)*gap/distance))
    var result: Dictionary = SpacingLayout.solve(groups,gap,density)
    while not bool(result.get("ok",false)) and density < 480.0:
        density = minf(480.0,density*1.25)
        result = SpacingLayout.solve(groups,gap,density)
    if not bool(result.get("ok",false)):
        return result
    var placed_accidentals: Dictionary = _place_accidentals(groups,result["shifts"],
        source_heads,accidentals,density,gap)
    if not bool(placed_accidentals.get("ok",false)):
        return placed_accidentals
    layout_accidental_spaces = placed_accidentals["relative"]
    layout_note_components = groups.duplicate()
    layout_source_heads = source_heads.duplicate()
    layout_source_columns = accidentals.duplicate()
    groups.append_array(placed_accidentals["groups"])
    # Keep the occupancy audit and visibility sweep ordered by exact onset.
    groups.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return float(a["beat"]) < float(b["beat"]))
    layout_head_spaces = source_heads.duplicate()
    layout_group_spaces = result["shifts"]
    layout_group_spaces.merge(placed_accidentals["shifts"])
    layout_rest_spaces = rest_spaces
    layout_components = groups
    layout_ink_reach = 0.0
    staff_pitch_factors = {"right":[0.0,0.0],"left":[0.0,0.0]}
    for group in groups:
        var staff: String = str(group["staff"])
        var ink_parts: Array = group["parts"].duplicate()
        ink_parts.append_array(group["ledgers"])
        for part in ink_parts:
            staff_pitch_factors[staff][0] = minf(float(staff_pitch_factors[staff][0]),part.position.y)
            staff_pitch_factors[staff][1] = maxf(float(staff_pitch_factors[staff][1]),part.end.y)
            layout_ink_reach = maxf(layout_ink_reach,maxf(absf(part.position.x),absf(part.end.x))+2.0)
    for group in groups:
        var shift: float = float(layout_group_spaces[str(group["id"])])
        for member in group["members"]:
            var id: String = str(member.get("id",""))
            layout_head_spaces[id] = shift+float(source_heads.get(id,0.0))
    return {"ok":true,"density":density}


func _place_accidentals(groups: Array, shifts: Dictionary, source_heads: Dictionary,
        source_columns: Dictionary, density: float, gap: float) -> Dictionary:
    # Accidentals belong to a written pitch, not to a rigid stem/flag sprite.
    # Pack their original masks against the final heads of ALL voices, while
    # leaving every source head and musical beat fixed.
    var added: Array = []
    var added_shifts: Dictionary = {}
    var relative: Dictionary = {}
    var scale: float = density/gap
    for group in groups:
        for event in group["members"]:
            var id: String = str(event.get("id",""))
            if not source_columns.has(id):
                continue
            var staff: String = str(group["staff"])
            var beat: float = float(group["beat"])
            var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])])
            var y: float = _event_y(event,1.0)-_staff_center(staff)
            var parts: Array = _symbol_parts(name,Vector2(0,y))
            var box: Rect2 = SpacingLayout.footprint(parts)
            var head: float = float(shifts[group["id"]])+float(source_heads.get(id,0.0))
            var center: float = head+float(source_columns[id])
            var placed := false
            for attempt in range(401):
                var clear := true
                for other in groups+added:
                    if str(other["staff"]) != staff:
                        continue
                    var delta: float = (float(other["beat"])-beat)*scale
                    var other_shift: float = float(added_shifts.get(other["id"],shifts.get(other["id"],0.0)))
                    var first_box := Rect2(box.position+Vector2(center,0),box.size).grow(.04)
                    var last_box := Rect2(other["box"].position+Vector2(delta+other_shift,0),other["box"].size).grow(.04)
                    if not first_box.intersects(last_box):
                        continue
                    for a in parts:
                        for b in other["parts"]:
                            var first: Rect2 = Rect2(a.position+Vector2(center,0),a.size).grow(.04)
                            var last: Rect2 = Rect2(b.position+Vector2(delta+other_shift,0),b.size).grow(.04)
                            if first.intersects(last):
                                clear = false
                                break
                        if not clear:
                            break
                    if not clear:
                        break
                if clear:
                    placed = true
                    break
                center -= .10
            if not placed:
                return {"ok":false,"reason":"No clear authentic accidental column: "+id}
            var acc_id: String = "accidental:"+id
            relative[id] = center-head
            added_shifts[acc_id] = center
            added.append({"id":acc_id,"members":[],"staff":staff,"beat":beat,
                "parts":parts,"box":box,"ledgers":[],"rest":false,"min_head":0.0,"max_head":0.0,
                "left":-44.0,"sweep_reach":88.0})
    var reach: float = 0.0
    for group in added:
        reach = maxf(reach,absf(float(added_shifts[group["id"]]))+8.0)
    for group in groups+added:
        group["sweep_reach"] = maxf(float(group["sweep_reach"]),reach)
    return {"ok":true,"relative":relative,"groups":added,"shifts":added_shifts}


func _cache_spacing(gap: float) -> bool:
    # Repacking on a viewport resize uses the actual canvas scale. It is
    # cached here, never recomputed while the unchanged viewport scrolls.
    var placed: Dictionary = _place_accidentals(layout_note_components,layout_group_spaces,
        layout_source_heads,layout_source_columns,selected_density,gap)
    if not bool(placed.get("ok",false)):
        failure_reason = str(placed.get("reason","Accidental layout failed"))
        return false
    layout_accidental_spaces = placed["relative"]
    layout_components = layout_note_components.duplicate()
    layout_components.append_array(placed["groups"])
    layout_components.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return float(a["beat"]) < float(b["beat"]))
    layout_group_spaces.merge(placed["shifts"],true)
    layout_ink_reach = 0.0
    for group in layout_components:
        var shift: float = float(layout_group_spaces[str(group["id"])])
        for part in group["parts"]+group["ledgers"]:
            layout_ink_reach = maxf(layout_ink_reach,maxf(absf(part.position.x+shift),absf(part.end.x+shift)))
    cached_head_offsets.clear()
    cached_group_offsets.clear()
    cached_rest_y.clear()
    for id in layout_head_spaces:
        cached_head_offsets[id] = float(layout_head_spaces[id])*gap
    for id in layout_group_spaces:
        cached_group_offsets[id] = float(layout_group_spaces[id])*gap
    for group in layout_components:
        var id: String = str(group["id"])
        if bool(group["rest"]):
            cached_rest_y[id] = _staff_center(str(group["staff"]))+float(layout_rest_spaces[id])*gap
    # Painter offsets are relative to each actual source head, regardless of
    # the independently packed accidental column.
    cached_accidental_offsets.clear()
    for id in layout_accidental_spaces:
        cached_accidental_offsets[id] = float(layout_accidental_spaces[id])*gap
    cached_offsets_gap = gap
    return true


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
    x += float(cached_group_offsets.get(str(event.get("id","")),0.0))
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
        _paint_note_accidental(current,center.x,center.y,ink,gap)
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
        _paint_note_accidental(event,x,y,ink,gap)
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
    _paint_note_accidental(event,x,y,ink,gap)
    drawn_noteheads[str(event.get("id", ""))] = Vector2(x,y)

func _beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    # Beam position is derived from the real notehead Y coordinates.
    # All horizontal positions still come from the one musical-time axis.
    var stems: Dictionary = {}
    var drawn_groups: Array = []
    frame_visible_beam_groups = 0
    for group in _visible_fragments("beams",clock,playhead_x):
        if group.size() < 2:
            continue
        var first_x: float = timeline.screen_x(
            float(group[0].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        var last_x: float = timeline.screen_x(
            float(group[-1].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        if last_x < -60.0 or first_x > size.x + 60.0:
            continue
        frame_visible_beam_groups += 1
        var up: bool = bool(beam_stem_up_by_note[str(group[0].get("id",""))])
        var group_ids := PackedStringArray()
        for event in group:
            group_ids.append(str(event.get("id","")))
        var source_key: String = "|".join(group_ids)
        var members: Array = []
        var source_stems: Array = []
        var source_heads: Array = glyphs.beam_metadata[source_key]["head_offsets"]
        var head_box: Array = glyphs.bounds["head_black"]
        var origin_to_center: float = float(head_box[0])+float(head_box[2])*.5
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var x: float = timeline.screen_x(float(event.get("beat", 0.0)),
                clock, playhead_x, play_from_beat)
            var chord: Dictionary = _chord_extents(event,gap,head_offsets)
            var stem_box: Array = _source_stem_bounds(event,up)
            var attachment: float = float(stem_box[0])+float(stem_box[2])*.5
            var stem_x: float = x+float(cached_group_offsets.get(
                str(event.get("id","")),0.0))+attachment*gap/250.0
            # The beam PNG uses source font origins, while stem masks use
            # centred heads. Map each measured stem centre in BOTH spaces;
            # mapping head centres stretches the first beam cap away from
            # its stem when the source spacing differs from the beat grid.
            source_stems.append(float(source_heads[index])+origin_to_center+attachment)
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
            "up":up, "art_key":art_key,
            "source_stem_offsets":source_stems,
            # Beam bounds are exported relative to the first source ID,
            # which may be an inner/higher chord tone. Stem tip offsets
            # deliberately use the outer tone and have a different origin.
            "anchor_y":_event_y(group[0],gap)})
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
        if float(last["head_x"]) < -gap*3.0 or \
                float(first["head_x"]) > size.x+gap*3.0:
            continue
        var anchors: Array = []
        for member in members:
            anchors.append(float(member["x"]))
        glyphs.paint_beam(self,str(group["art_key"]),anchors,
            float(group["anchor_y"]),gap,
            _ink(str(group.get("staff","right"))),group["source_stem_offsets"])


# Only the original Verovio-rendered tie contours are permitted.
# The source noteheads determine the start, end and staff-space vertical
# position. Godot never produces its own bow paths or tapered polygons.
func _tie_placement(first: Dictionary, last: Dictionary,
        x0: float, x1: float, gap: float) -> Dictionary:
    var left: float = x0+float(cached_head_offsets.get(
        str(first.get("id","")),0.0))
    var right: float = x1+float(cached_head_offsets.get(
        str(last.get("id","")),0.0))
    if right <= left:
        return {}
    var leader_id: String = str(chord_leader_by_note.get(
        str(first.get("id","")),str(first.get("id",""))))
    var leader: Dictionary = first
    for member in chord_members.get(leader_id,[]):
        if str(member.get("id","")) == leader_id:
            leader = member
            break
    var upward_stem: bool = bool(beam_stem_up_by_note.get(leader_id,
        _chord_extents(leader,gap)["up"]))
    return {"x0":left, "x1":right, "y":_event_y(first,gap),
        "down":upward_stem}


func _paint_ties(playhead_x: float, clock: float, gap: float) -> void:
    for pair in _visible_fragments("ties",clock,playhead_x):
        var previous: Dictionary = pair["first"]
        var event: Dictionary = pair["last"]
        var x0: float = timeline.screen_x(float(previous.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(event.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var place: Dictionary = _tie_placement(previous,event,x0,x1,gap)
        if not place.is_empty() and float(place["x1"]) >= -gap*2.0 and float(place["x0"]) <= size.x+gap*2.0:
            glyphs.paint_tie(self,float(place["x0"]),float(place["x1"]),
                float(place["y"]),gap,bool(place["down"]),
                _ink(str(event.get("staff","right"))))


# Binary-search into pre-sorted MusicXML events. Work is proportional
# to what the pianist can actually see, not to the whole imported MIDI.
func _paint_slurs(playhead_x: float,clock: float,gap: float) -> void:
    for pair in _visible_fragments("slurs",clock,playhead_x):
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
    var margin: float = maxf(.25,layout_ink_reach*staff_gap_limit/timeline.pixels_per_beat)
    var begin := 0
    var end := ordered_events.size()
    while begin < end:
        var middle: int = (begin + end) >> 1
        if float(ordered_events[middle].get("beat", 0.0)) < left-margin:
            begin = middle + 1
        else:
            end = middle
    var results: Array = []
    for index in range(begin, ordered_events.size()):
        var event: Dictionary = ordered_events[index]
        if float(event.get("beat", 0.0)) > right+margin:
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
    # A quiet pool of light marks the strike without hiding any engraved ink.
    var top: float = _staff_center("right")-gap*3.8
    var bottom: float = _staff_center("left")+gap*3.7
    var breath: float = .5+.5*cos(clock_beat*TAU) if running and not paused else 0.0
    for radius in [20.0, 10.0, 4.0]:
        draw_rect(Rect2(playhead_x-radius, top, radius*2.0, bottom-top),
            Color(PREVIEW_LIGHT, .012+breath*.004))
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
    for measure in _visible_fragments("measures",camera_clock,playhead_x):
        previous_measure = previous_measure_by_number.get(int(measure.get("number",0)),{})
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
        var header_scale: float = gap / 17.0
        var header_shift: float = 76.0*header_scale if opening else 0.0
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
                _paint_clef(x-(86.0+float(absi(signature))*14.0)*header_scale-header_shift,
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
                    var glyph_x: float = x-(39.0+float(change_marks.size()-i)*14.0)*header_scale-header_shift
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
    # Every symbol keeps its source onset on the single linear clock. The
    # precomputed local ink offsets do not depend on playback position.
    visible_symbols = 0
    drawn_noteheads.clear()
    if cached_offsets_gap < 0.0 or absf(cached_offsets_gap-gap) > .001:
        if not _cache_spacing(gap):
            native_ready = false
            notice = failure_reason
            return
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
            var id: String = str(event.get("id",""))
            x += float(cached_group_offsets.get(id,0.0))
            var rest_y: float = float(cached_rest_y.get(id,_staff_center(staff)))
            _paint_rest(x,rest_y,str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        visible_symbols += 1
    _paint_beams(beam_data, gap)
    _paint_ties(playhead_x,camera_clock,gap)
    _paint_slurs(playhead_x,camera_clock,gap)
    _paint_tuplet_brackets(camera_clock,playhead_x,gap)
    annotation_painter.paint(self,camera_clock,playhead_x,gap,NOTE_INK)
    draw_line(Vector2(playhead_x,_staff_center("right")-gap*3.8),
        Vector2(playhead_x,_staff_center("left")+gap*3.7),
        PREVIEW_LIGHT,2.0,true)
    # A genuine font brace joins the two continuous staves at the screen's
    # edge. Stretch only this authentic brace, never the timed music stream.
    var staff_top: float = _staff_center("right")-2.0*gap
    var staff_bottom: float = _staff_center("left")+2.0*gap
    draw_rect(Rect2(0, staff_top-gap, 29, staff_bottom-staff_top+gap*2), Design.STAGE)
    if glyphs.textures.has("brace"):
        draw_texture_rect(glyphs.textures["brace"],
            Rect2(6, staff_top-2, 18, staff_bottom-staff_top+4), false,
            NOTE_INK)
    draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)
    # Never put engineering telemetry on top of the actual lesson.
    if OS.get_environment("PIANO_TEACHER_NATIVE_DIAGNOSTICS") == "1":
        var phase: String = "COUNT-IN" if camera_clock < 0.0 and running else \
            "PAUSED" if paused else "PLAYING" if running else "READY"
        draw_string(font,Vector2(14.0,22.0),
            "NATIVE · %s · %.0f px/beat · %.0f BPM · %d events" % [
                phase,timeline.pixels_per_beat,bpm,frame_scanned_events],
            HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)
