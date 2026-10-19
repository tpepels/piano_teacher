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
var notation_tuplets: Array = []
# Immutable musical structure is indexed ONCE when a passage changes.
# Each frame then visits only visible onsets, beams and ties.
var measure_by_number: Dictionary = {}
var ordered_events: Array = []
var tie_pairs: Array = []
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
    notation_tuplets.clear()
    measure_by_number.clear()
    ordered_events.clear()
    tie_pairs.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_offsets_gap = -1.0

func set_verovio_glyphs(items: Dictionary) -> bool:
    var success: bool = glyphs.load_font(items)
    if not success:
        failure_reason = glyphs.error
    return success


func load_score(candidate: Dictionary) -> bool:
    native_ready = false
    if not glyphs.ready():
        failure_reason = "Authentic Verovio font atlas is not loaded"
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
    var stem_up: bool = bool(beam_stem.get("up", step < 4))
    var ink_center := Vector2(x,y)
    _paint_ledger(x, y, step, bottom, gap, ink)
    var solid: bool = kind not in ["half","whole"]
    glyphs.paint(self, "head_black" if solid else (
        "head_whole" if kind == "whole" else "head_half"),
        x, y, gap, ink, true)
    # Multiple chord pitches have distinct noteheads but one common stem.
    if kind != "whole" and not bool(event.get("chord", false)):
        var stem_x: float = x+(gap*.61 if stem_up else -gap*.61)
        var tip_y: float = float(beam_stem.get("tip_y",
            y+(-gap*3.25 if stem_up else gap*3.25)))
        draw_line(Vector2(stem_x,y), Vector2(stem_x,tip_y), ink, 1.65, true)
        if Geometry.beam_level(kind) > 0 and beam_stem.is_empty():
            _paint_flag(stem_x, tip_y, stem_up,
                Geometry.beam_level(kind), ink, gap)
    _paint_rhythm_dots(x,y,int(event.get("dots",0)),ink,gap)
    var accidental: String = str(event.get("accidental", ""))
    if not accidental.is_empty() and accidental != "null":
        _paint_accidental(x,y,accidental,ink,gap)
    drawn_noteheads[str(event.get("id", ""))] = Vector2(x,y)

func _beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    # Build one set of stem tips and polygons for the complete score.
    # Their screen X changes only through the common, linear timeline.
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
        var up: bool = Geometry.stem_up(group, timeline.model)
        var y_min := INF
        var y_max := -INF
        for event in group:
            var y: float = _event_y(event, gap)
            y_min = minf(y_min, y)
            y_max = maxf(y_max, y)
        var tip: float = (y_min - gap*3.25 if up else y_max + gap*3.25)
        var members: Array = []
        for event in group:
            var x: float = timeline.screen_x(float(event.get("beat", 0.0)),
                clock, playhead_x, play_from_beat)
            var stem_x: float = x + float(head_offsets.get(
                str(event.get("id", "")), 0.0)) + \
                (gap*.61 if up else -gap*.61)
            var id: String = str(event.get("id", ""))
            stems[id] = {"up":up, "tip_y":tip}
            members.append({"x":stem_x, "tip_y":tip,
                "note_type":str(event.get("note_type", "eighth"))})
        drawn_groups.append({"members":members,
            "staff":str(group[0].get("staff", "right")),
            "up":up, "tip_y":tip})
    return {"stems":stems, "groups":drawn_groups}


func _beam_rectangle(a: float, b: float, y: float,
        thickness: float, ink: Color) -> void:
    if b <= a:
        return
    draw_colored_polygon(PackedVector2Array([
        Vector2(a, y), Vector2(b, y),
        Vector2(b, y+thickness), Vector2(a, y+thickness)]), ink)


func _paint_beams(data: Dictionary, gap: float) -> void:
    # The first beam joins the entire group. Additional beams at levels
    # 2/3/4 respectively encode 16th/32nd/64th values. Each level either
    # joins adjacent eligible notes or paints a short isolated hook.
    # All layers use the exact same source-beat positions and stem tips.
    for group in data.get("groups", []):
        var members: Array = group.get("members", [])
        if members.size() < 2:
            continue
        var first: Dictionary = members[0]
        var last: Dictionary = members[-1]
        if float(last["x"]) < -40.0 or float(first["x"]) > size.x+40.0:
            continue
        var ink: Color = _ink(str(group.get("staff", "right")))
        var up: bool = bool(group.get("up", true))
        var first_y: float = float(group.get("tip_y", 0.0))
        var sign: float = 1.0 if up else -1.0
        var thick: float = gap*.39
        _beam_rectangle(float(first["x"]), float(last["x"]),
            first_y, sign*thick, ink)
        for level in range(2, 5):
            var beam_y: float = first_y + sign*gap*.65*float(level-1)
            for i in range(members.size()):
                var amount: int = Geometry.beam_level(
                    str(members[i].get("note_type", "")))
                if amount < level:
                    continue
                var x0: float = float(members[i]["x"])
                var prior: bool = i > 0 and Geometry.beam_level(
                    str(members[i-1].get("note_type", ""))) >= level
                var following: bool = i+1 < members.size() and \
                    Geometry.beam_level(
                    str(members[i+1].get("note_type", ""))) >= level
                if following:
                    _beam_rectangle(x0, float(members[i+1]["x"]),
                        beam_y, sign*thick, ink)
                elif not prior:
                    var left_hook: bool = i == members.size()-1
                    var nearby: float = (x0-float(members[i-1]["x"])
                        if left_hook else float(members[i+1]["x"])-x0)
                    var hook: float = minf(gap*1.3, nearby*.50)
                    if left_hook:
                        _beam_rectangle(x0-hook, x0, beam_y, sign*thick, ink)
                    else:
                        _beam_rectangle(x0, x0+hook, beam_y, sign*thick, ink)

func _paint_ties(playhead_x: float, clock: float, gap: float) -> void:
    # Build tie connectivity once on load, not O(all notes) every frame.
    for pair in tie_pairs:
        var previous: Dictionary = pair["first"]
        var event: Dictionary = pair["last"]
        var x0: float = timeline.screen_x(float(previous.get("beat", 0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(event.get("beat", 0.0)),
            clock,playhead_x,play_from_beat)
        if x1 < -20.0 or x0 > size.x+20.0 or x1 <= x0+3.0:
            continue
        var baseline: float = _event_y(event,gap)+gap*.55
        var points := PackedVector2Array()
        for step in range(21):
            var t: float = float(step)/20.0
            points.append(Vector2(lerpf(x0+6.0,x1-6.0,t),
                baseline+sin(t*PI)*gap*.62))
        draw_polyline(points,_ink(str(event.get("staff", "right"))),1.4,true)

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
    # Negative-count measure shares the same timeline and boundary at 0.
    if count_in_beats > 0.0:
        var first: float = timeline.count_in_start(play_from_beat,count_in_beats)
        var x: float = timeline.screen_x(first,camera_clock,
            playhead_x,play_from_beat)
        if x >= 0.0 and x <= size.x:
            for staff in ["right","left"]:
                var center: float = _staff_center(staff)
                draw_line(Vector2(x,center-2*gap),Vector2(x,center+2*gap),
                    Color(DIM_INK,.72),1.25,true)
    var previous_measure: Dictionary = {}
    for measure in timeline.measures:
        var at: float = float(measure.get("start_beat",0.0))
        if at < left-.7 or at > right+.7:
            previous_measure = measure
            continue
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var boundary_tint: Color = Color(DIM_INK,.70)
        for staff in ["right","left"]:
            var center: float = _staff_center(staff)
            draw_line(Vector2(x,center-2*gap),Vector2(x,center+2*gap),
                boundary_tint,1.3,true)
            var clef: Dictionary = _clef_for(staff,measure)
            var signatures: Dictionary = measure.get("keys",{})
            var signature: int = int(signatures.get(staff,0))
            var previous_keys: Dictionary = previous_measure.get("keys",{})
            var key_changed: bool = signature != int(previous_keys.get(staff,999))
            if previous_measure.is_empty() or _clef_for(staff,previous_measure) != clef:
                _paint_clef(x-86.0-float(absi(signature))*14.0,
                    center,str(clef.get("sign","G")),gap,_ink(staff))
            if key_changed and signature != 0:
                var steps: Array = Geometry.signature_steps(clef, signature)
                for i in range(steps.size()):
                    var glyph_x: float = x-39.0-float(steps.size()-i)*14.0
                    var glyph_y: float = Geometry.note_y(int(steps[i]),
                        center+2.0*gap,gap)
                    _paint_accidental(glyph_x,glyph_y,
                        "sharp" if signature > 0 else "flat",
                        _ink(staff),gap)
            if previous_measure.is_empty() or previous_measure.get("meter",[]) != measure.get("meter",[]):
                var meter: Array = measure.get("meter",[4,4])
                if meter.size() >= 2:
                    _paint_meter_number(int(meter[0]), x-gap*1.6,
                        center-gap*.95, _ink(staff), gap)
                    _paint_meter_number(int(meter[1]), x-gap*1.6,
                        center+gap*.8, _ink(staff), gap)
        if x >= 0.0 and x <= size.x:
            draw_string(font,Vector2(x+5.0,_staff_center("right")-gap*3.0),
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
    for event in _visible_events(left, right):
        var at: float = float(event.get("beat", 0.0))
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var staff: String = str(event.get("staff","right"))
        var ink: Color = _ink(staff)
        if str(event.get("kind","")) == "note":
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
