extends "res://score_timeline_preview.gd"
# Phase C: directly draw source MusicXML-derived symbols as Godot vector ink.
# No Verovio PNG/SVG, cropped staves, external font assets, extra clock,
# special short-note camera easing or per-event position corrections.
# Incomplete notation falls back to the existing Verovio score as a whole.
const Geometry := preload("res://score_notation_geometry.gd")
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT

var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var selected_density := 0.0
var beam_groups: Array = []
var beamed_note_ids: Dictionary = {}

func clear_score() -> void:
    super.clear_score()
    native_ready = false
    failure_reason = ""
    visible_symbols = 0
    drawn_noteheads.clear()
    beam_groups.clear()
    beamed_note_ids.clear()

func load_score(candidate: Dictionary) -> bool:
    native_ready = false
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
    failure_reason = ""
    native_ready = true
    queue_redraw()
    return true

func _staff_center(hand: String) -> float:
    return size.y * (.34 if hand == "right" else .69)

func _gap() -> float:
    # Reserve actual room for ledger notes ABOVE and BELOW both staves.
    # The former raster crop clipped high notes because it only knew staff
    # rails, not the extreme noteheads. Fit the full semantic pitch range
    # once per frame/viewport, uniformly for both hands.
    var gap: float = clampf(size.y * .034, 8.5, 17.0)
    if timeline.model.is_empty():
        return gap
    for event in timeline.model.get("notation_events", []):
        if not event is Dictionary or str(event.get("kind", "")) != "note":
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
    return maxf(5.0, gap)

func _clef_for(staff: String, measure: Dictionary) -> Dictionary:
    var clefs: Dictionary = measure.get("clefs", {})
    return clefs.get(staff, {
        "sign":"G" if staff == "right" else "F",
        "line":2 if staff == "right" else 4, "octave_change":0})

func _measure_for(event: Dictionary) -> Dictionary:
    var number: int = int(event.get("measure", -1))
    for measure in timeline.measures:
        if int(measure.get("number", -1)) == number:
            return measure
    return timeline.measures[0]

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

func _paint_ellipse(center: Vector2, rx: float, ry: float,
        fill: Color, solid: bool, rotation: float = -.27) -> void:
    var shape := PackedVector2Array()
    for i in range(33):
        var theta: float = TAU * float(i)/32.0
        var xx: float = cos(theta)*rx
        var yy: float = sin(theta)*ry
        shape.append(center + Vector2(xx*cos(rotation)-yy*sin(rotation),
            xx*sin(rotation)+yy*cos(rotation)))
    if solid:
        var polygon: PackedVector2Array = shape
        polygon.resize(32)
        draw_colored_polygon(polygon, fill)
    else:
        draw_polyline(shape, fill, 2.0, true)

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
    # Accidentals are vector strokes, not text glyphs from Verovio.
    var left: float = x - 19.0
    var width: float = 7.0
    match value:
        "sharp", "double-sharp":
            draw_line(Vector2(left, y-gap*1.0), Vector2(left, y+gap*.9),
                ink, 1.6, true)
            draw_line(Vector2(left+width, y-gap*1.1),
                Vector2(left+width, y+gap*.8), ink, 1.6, true)
            for offset in [-.32, .30]:
                draw_line(Vector2(left-3.0, y+offset*gap+2.0),
                    Vector2(left+width+3.0, y+offset*gap-2.0),
                    ink, 2.0, true)
            if value == "double-sharp":
                draw_line(Vector2(left+11.0, y-5.0),
                    Vector2(left+18.0, y+5.0), ink, 1.4)
                draw_line(Vector2(left+18.0, y-5.0),
                    Vector2(left+11.0, y+5.0), ink, 1.4)
        "flat", "flat-flat":
            draw_line(Vector2(left, y-gap*1.4), Vector2(left, y+gap*.55),
                ink, 1.7, true)
            draw_arc(Vector2(left+2.0, y+gap*.21), gap*.32,
                -.65*PI, .65*PI, 15, ink, 1.8, true)
            if value == "flat-flat":
                draw_line(Vector2(left-7, y-gap*1.4),
                    Vector2(left-7, y+gap*.55), ink, 1.7, true)
        "natural":
            draw_line(Vector2(left, y-gap*1.1),
                Vector2(left, y+gap*.55), ink, 1.6, true)
            draw_line(Vector2(left+width, y-gap*.55),
                Vector2(left+width, y+gap*1.05), ink, 1.6, true)
            draw_line(Vector2(left, y-gap*.25),
                Vector2(left+width, y-gap*.43), ink, 2.2, true)
            draw_line(Vector2(left, y+gap*.55),
                Vector2(left+width, y+gap*.36), ink, 2.2, true)

func _paint_flag(stem_x: float, tip_y: float,
        up: bool, count: int, ink: Color, gap: float) -> void:
    var direction: float = 1.0 if up else -1.0
    for index in range(count):
        var origin: float = tip_y + direction * float(index) * gap*.57
        var points := PackedVector2Array()
        points.append(Vector2(stem_x, origin))
        points.append(Vector2(stem_x+direction*5.0, origin+direction*gap*.10))
        points.append(Vector2(stem_x+direction*11.0, origin+direction*gap*.58))
        points.append(Vector2(stem_x+direction*10.0, origin+direction*gap*1.0))
        draw_polyline(points, ink, 2.2, true)

func _paint_rest(x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    match note_type:
        "whole", "half":
            var bar_y: float = y - (gap*.6 if note_type == "whole" else gap*.15)
            draw_rect(Rect2(x-7.0, bar_y, 14.0, gap*.33), ink, true)
        "quarter":
            var points := PackedVector2Array([
                Vector2(x-3.0,y-gap*1.1), Vector2(x+4.0,y-gap*.55),
                Vector2(x-2.0,y-gap*.18), Vector2(x+4.0,y+gap*.30),
                Vector2(x-4.0,y+gap*.88), Vector2(x+2.0,y+gap*.70)])
            draw_polyline(points, ink, 2.9, true)
        _:
            var flags: int = 2 if note_type == "16th" else 1
            draw_line(Vector2(x+3.0, y-gap*.85),
                Vector2(x-4.0, y+gap*.86), ink, 2.0, true)
            for index in range(flags):
                draw_circle(Vector2(x+3.0, y-gap*(.7-index*.5)), 3.0, ink)
    if dots > 0:
        draw_circle(Vector2(x+13.0,y-gap*.12), 2.3, ink)

func _paint_clef(x: float, center: float, sign: String,
        gap: float, ink: Color) -> void:
    # Simple directly drawn vector clefs. Real font replacement can follow
    # without changing time or y-coordinate math.
    if sign == "G":
        var path := PackedVector2Array()
        for i in range(57):
            var t: float = float(i)/56.0
            var radius: float = lerpf(gap*.8, gap*.18, t)
            var angle: float = -PI*.65 + t*TAU*1.7
            path.append(Vector2(x+cos(angle)*radius,
                center+sin(angle)*radius*1.3))
        draw_polyline(path, ink, 1.9, true)
        draw_line(Vector2(x+gap*.08,center-gap*2.5),
            Vector2(x+gap*.08,center+gap*3.0), ink, 1.7, true)
        draw_arc(Vector2(x+gap*.22,center+gap*2.8),gap*.5,
            .2, PI*1.55, 23, ink, 1.7, true)
    elif sign == "F":
        draw_arc(Vector2(x-gap*.16, center-gap*.56), gap*.90,
            -PI*.56, PI*.69, 35, ink, 2.7, true)
        draw_circle(Vector2(x-gap*.20, center-gap*.70), gap*.18, ink)
        draw_circle(Vector2(x+gap*.60,center-gap*.85), 2.0, ink)
        draw_circle(Vector2(x+gap*.60,center-gap*.31), 2.0, ink)
    else:
        draw_line(Vector2(x-gap*.20,center-gap*1.65),
            Vector2(x-gap*.20,center+gap*1.65), ink, 2.3, true)
        for offset in [-.8,.8]:
            draw_arc(Vector2(x+gap*.20,center+offset*gap),gap*.65,
                -PI*.64, PI*.64, 16, ink, 2.1, true)

func _paint_note(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {}) -> void:
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
    _paint_ellipse(ink_center, gap*.66, gap*.44, ink, solid)
    # Multiple chord pitches have distinct noteheads but one common stem.
    if kind != "whole" and not bool(event.get("chord", false)):
        var stem_x: float = x+(gap*.61 if stem_up else -gap*.61)
        var tip_y: float = float(beam_stem.get("tip_y",
            y+(-gap*3.25 if stem_up else gap*3.25)))
        draw_line(Vector2(stem_x,y), Vector2(stem_x,tip_y), ink, 1.65, true)
        if kind in ["eighth","16th"] and beam_stem.is_empty():
            _paint_flag(stem_x,tip_y,stem_up,2 if kind=="16th" else 1,ink,gap)
    if int(event.get("dots", 0)) > 0:
        draw_circle(Vector2(x+gap*.93, y-gap*.3), 2.4, ink)
    var accidental: String = str(event.get("accidental", ""))
    if not accidental.is_empty() and accidental != "null":
        _paint_accidental(x,y,accidental,ink,gap)
    drawn_noteheads[str(event.get("id", ""))] = Vector2(x,y)

func _beam_layout(gap: float, clock: float, playhead_x: float) -> Dictionary:
    # Build one set of stem tips and polygons for the complete score.
    # Their screen X changes only through the common, linear timeline.
    var stems: Dictionary = {}
    var drawn_groups: Array = []
    for group in beam_groups:
        if group.size() < 2:
            continue
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
            var stem_x: float = x+(gap*.61 if up else -gap*.61)
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
    # Main bar always joins every member in a group. Sixteenth notes get
    # secondary bars; an isolated sixteenth gets a short hook, never a flag
    # laid on top of an existing beam.
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
        var second_y: float = first_y+sign*gap*.65
        for i in range(members.size()):
            if str(members[i].get("note_type", "")) != "16th":
                continue
            var x0: float = float(members[i]["x"])
            if i+1 < members.size() and \
                    str(members[i+1].get("note_type", "")) == "16th":
                _beam_rectangle(x0, float(members[i+1]["x"]),
                    second_y, sign*thick, ink)
            elif i == 0 or str(members[i-1].get("note_type", "")) != "16th":
                var hook_dir: float = -1.0 if i == members.size()-1 else 1.0
                var available: float = (x0-float(members[i-1]["x"])
                    if hook_dir < 0.0 else float(members[i+1]["x"])-x0)
                var width: float = minf(gap*1.3, available*.5)
                if hook_dir < 0.0:
                    _beam_rectangle(x0-width, x0,second_y,sign*thick,ink)
                else:
                    _beam_rectangle(x0,x0+width,second_y,sign*thick,ink)


func _paint_ties(visible_events: Array, playhead_x: float,
        clock: float, gap: float) -> void:
    var waiting: Dictionary = {}
    for event in timeline.model.get("notation_events", []):
        if not event is Dictionary or str(event.get("kind", "")) != "note":
            continue
        var source: String = str(event.get("source_id", ""))
        if bool(event.get("tie_stop", false)) and waiting.has(source):
            var previous: Dictionary = waiting[source]
            var x0: float = timeline.screen_x(float(previous.get("beat", 0.0)),
                clock,playhead_x,play_from_beat)
            var x1: float = timeline.screen_x(float(event.get("beat", 0.0)),
                clock,playhead_x,play_from_beat)
            if x1 >= -20.0 and x0 <= size.x+20.0 and x1 > x0+3.0:
                var baseline: float = _event_y(event,gap)+gap*.55
                var points := PackedVector2Array()
                for step in range(21):
                    var t: float = float(step)/20.0
                    points.append(Vector2(lerpf(x0+6.0,x1-6.0,t),
                        baseline+sin(t*PI)*gap*.62))
                draw_polyline(points,_ink(str(event.get("staff", "right"))),1.4,true)
        if bool(event.get("tie_start", false)):
            waiting[source] = event
        else:
            waiting.erase(source)

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
            if previous_measure.is_empty() or _clef_for(staff,previous_measure) != clef:
                _paint_clef(x-53.0,center,str(clef.get("sign","G")),gap,_ink(staff))
            if previous_measure.is_empty() or previous_measure.get("meter",[]) != measure.get("meter",[]):
                var meter: Array = measure.get("meter",[4,4])
                if meter.size() >= 2:
                    draw_string(font,Vector2(x-30.0,center-2.0),str(meter[0]),
                        HORIZONTAL_ALIGNMENT_LEFT,-1,14,_ink(staff))
                    draw_string(font,Vector2(x-30.0,center+gap*1.2),str(meter[1]),
                        HORIZONTAL_ALIGNMENT_LEFT,-1,14,_ink(staff))
            var signatures: Dictionary = measure.get("keys",{})
            var signature: int = int(signatures.get(staff,0))
            var previous_keys: Dictionary = previous_measure.get("keys",{})
            if signature != int(previous_keys.get(staff,999)):
                if signature != 0:
                    var symbol: String = "♯" if signature > 0 else "♭"
                    draw_string(font,Vector2(x-42.0,center-gap*.38),
                        symbol.repeat(absi(signature)),
                        HORIZONTAL_ALIGNMENT_LEFT,-1,15,_ink(staff))
        if x >= 0.0 and x <= size.x:
            draw_string(font,Vector2(x+5.0,_staff_center("right")-gap*3.0),
                str(measure.get("number","")),
                HORIZONTAL_ALIGNMENT_LEFT,-1,11,DIM_INK)
        previous_measure = measure
    # All symbols carry their original source onset; NO separate horizontal
    # layout pass or per-note acceleration, including chord tones and rests.
    visible_symbols = 0
    drawn_noteheads.clear()
    var beam_data: Dictionary = _beam_layout(gap, camera_clock, playhead_x)
    var beam_stems: Dictionary = beam_data.get("stems", {})
    var visible_events: Array = []
    for event in timeline.model.get("notation_events",[]):
        if not event is Dictionary:
            continue
        var at: float = float(event.get("beat",0.0))
        if at < left-.25 or at > right+.25:
            continue
        visible_events.append(event)
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var staff: String = str(event.get("staff","right"))
        var ink: Color = _ink(staff)
        if str(event.get("kind","")) == "note":
            _paint_note(event,x,gap,ink,
                beam_stems.get(str(event.get("id", "")), {}))
        else:
            var voice: String = str(event.get("voice","1"))
            var rest_y: float = _staff_center(staff)+(
                -gap*.3 if voice == "1" else gap*.6)
            _paint_rest(x,rest_y,str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        visible_symbols += 1
    _paint_beams(beam_data, gap)
    _paint_ties(visible_events,playhead_x,camera_clock,gap)
    draw_line(Vector2(playhead_x,_staff_center("right")-gap*3.8),
        Vector2(playhead_x,_staff_center("left")+gap*3.7),
        PREVIEW_LIGHT,2.0,true)
    # The diagnostic may be enabled alongside feedback for comparison.
    var phase: String = "COUNT-IN" if camera_clock < 0.0 and running else \
        "PAUSED" if paused else "PLAYING" if running else "READY"
    draw_string(font,Vector2(14.0,22.0),
        "NATIVE SCORE · %s · %.0f px/beat · %.0f BPM" % [
            phase,timeline.pixels_per_beat,bpm],
        HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)
