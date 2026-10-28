extends RefCounted
## Explicit-canvas native ink; source geometry stays in ScoreLayout.
## Paint APIs prepend (canvas, frame) to the original view method arguments.
const Geometry := preload("res://notation/native/geometry.gd")
const Design := preload("res://practice_theme.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const BarlineLayout := preload("res://notation/native/barline_layout.gd")

var score_layout
var symbol_painter

func _init(layout, symbols) -> void:
    score_layout = layout
    symbol_painter = symbols


func paint_barline(canvas, frame: RenderPass, info: Dictionary, gap: float) -> void:
    if info.is_empty():
        return
    var style: String = str(info.get("style","regular"))
    var bars: Array = score_layout.barline_strokes(style,gap)
    if bars.is_empty():
        return
    var x: float = float(info["x"])
    var ink: Color = Color(DIM_INK,.76)
    for stroke in bars:
        var sx: float = x+float(stroke["offset"])
        var width: float = float(stroke["width"])
        for segment in info.get("segments",score_layout.barline_segments(style,gap)):
            var top: float = float(segment["top"])
            var bottom: float = float(segment["bottom"])
            if style in ["dashed","dotted"]:
                var length: float = gap*(.65 if style=="dashed" else .13)
                var skip: float = gap*(.35 if style=="dashed" else .27)
                var at: float = top
                while at < bottom:
                    canvas.draw_line(Vector2(sx,at),Vector2(sx,minf(bottom,at+length)),
                        ink,width,true)
                    at += length+skip
            else:
                canvas.draw_line(Vector2(sx,top),Vector2(sx,bottom),ink,width,true)
    var repetition: String = str(info.get("repeat",""))
    if repetition not in ["forward","backward","both"]:
        return
    var positions: Array = []
    if repetition in ["backward","both"]:
        positions.append(x-gap*.92)
    if repetition in ["forward","both"]:
        positions.append(x+gap*.56)
    var box: Array = score_layout.glyphs.bounds.get("repeat_dot",[])
    if box.size()!=4:
        return
    var unit: float = gap/250.0
    var center_offset: float = (float(box[1])+float(box[3])*.5)*unit
    for dot_x in positions:
        for staff in ["right","left"]:
            var middle: float = score_layout.staff_center(staff)
            for dot_y in [middle-gap*.5,middle+gap*.5]:
                score_layout.glyphs.paint(canvas,"repeat_dot",float(dot_x),
                    dot_y-center_offset,gap,ink,true)


func meter_is_crowded(measure: Dictionary, previous: Dictionary,
        gap: float) -> bool:
    if previous.is_empty() or previous.get("meter", []) == measure.get("meter", []):
        return false
    var at: float = float(measure.get("start_beat", 0.0))
    var previous_start: float = float(previous.get("start_beat", 0.0))
    var advance: float = score_layout.timeline.pixels_per_beat
    if (at-previous_start)*advance < gap*7.0:
        return true
    var last_attack: float = float(score_layout.previous_attack_before_measure.get(
        int(measure.get("number", 0)), -INF))
    return is_finite(last_attack) and \
        (at-last_attack)*advance < gap*6.0


func paint_meter_above_staff(canvas, frame: RenderPass, measure: Dictionary, x: float,
        gap: float) -> void:
    var meter: Array = measure.get("meter", [4,4])
    if meter.size() < 2:
        return
    # Actual Verovio time-signature digit textures, scaled together and
    # arranged ABOVE the upper five lines, not GUI text or invented score_layout.glyphs.
    var center: float = score_layout.staff_center("right")
    var origin: float = x-gap*1.75
    var space: float = gap*.72
    # Meter applies to BOTH staves and must remain readable while one
    # of the hands is dimmed for separate-handed practice.
    paint_meter_number(canvas,frame,int(meter[0]),origin,center-gap*4.50,
        NOTE_INK,space)
    paint_meter_number(canvas,frame,int(meter[1]),origin,center-gap*3.05,
        NOTE_INK,space)


func paint_clef(canvas, frame: RenderPass, x: float, center: float, clef: Dictionary,
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
    if not variant.is_empty() and score_layout.glyphs.textures.has(variant):
        name = variant
    score_layout.glyphs.paint(canvas,name,x,origin_y,gap,ink,true)
    # No separate clef numeral is available in installed Leipzig. Any
    # unsupported combined variant must be rejected by Geometry.supported.


func paint_meter_number(canvas, frame: RenderPass, value: int, x: float, y: float,
        ink: Color, gap: float) -> void:
    # Real Verovio time-signature digits rather than generic GUI text.
    var digits: String = str(value)
    var advance: float = gap*1.10
    var start: float = x - float(digits.length()-1)*advance*.5
    for digit in range(digits.length()):
        score_layout.glyphs.paint(canvas, "time_" + digits[ digit ],
            start + float(digit)*advance, y, gap, ink, true)


func paint_expressions(canvas, frame: RenderPass, left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # The notation model is the *only* source. These marks never alter the
    # clock, create MIDI attacks, or participate in lesson mastery.
    var pedal_starts: Dictionary = {}
    for mark in score_layout.source_expressions:
        var at: float = float(mark.get("beat", -1.0))
        if not frame.event_visible(mark):
            continue
        var hand: String = score_layout.display_staff(mark)
        var ink: Color = frame.event_ink(score_layout,mark)
        var kind: String = str(mark.get("kind", ""))
        var value: String = str(mark.get("value", ""))
        var x: float = score_layout.timeline.screen_x(at, clock, playhead_x, frame.play_from_beat)
        if kind == "pedal":
            var y: float = score_layout.staff_center(hand) + gap*3.55
            if value == "start":
                pedal_starts[hand] = mark
            elif value == "stop" and pedal_starts.has(hand):
                var start_mark: Dictionary = pedal_starts[hand]
                var begin: float = float(start_mark.get("beat", 0.0))
                if frame.span_visible(start_mark,mark) and bool(start_mark.get("line", false)) and begin < at and \
                        at >= left-.5 and begin <= right+.5:
                    var start_x: float = score_layout.timeline.screen_x(
                        begin, clock, playhead_x, frame.play_from_beat)
                    var x0: float = maxf(-gap, start_x+gap*.65)
                    var x1: float = minf(score_layout.size.x+gap, x-gap*.3)
                    if x1 > x0:
                        canvas.draw_line(Vector2(x0,y), Vector2(x1,y), ink, 1.3,true)
                        canvas.draw_line(Vector2(x1,y), Vector2(x1,y-gap*.55),ink,1.3,true)
                pedal_starts.erase(hand)
            if at >= left-.5 and at <= right+.5 and bool(mark.get("sign", true)):
                score_layout.glyphs.paint(canvas, "pedal_start" if value == "start" else "pedal_stop",
                    x,y,gap*.9,ink,true)
            continue
        if at < left-.5 or at > right+.5:
            continue
        if kind == "dynamic":
            score_layout.glyphs.paint(canvas, "dynamic_"+value, x,
                score_layout.staff_center(hand)+gap*3.0, gap*.9, ink, true)
        elif kind == "articulation":
            var note_id: String = str(mark.get("note_id", ""))
            if not frame.pass_noteheads.has(note_id) or not score_layout.expression_note_index.has(note_id):
                continue
            var source_event: Dictionary = score_layout.expression_note_index[note_id]
            var center: float = score_layout.staff_center(hand)
            var head: Vector2 = frame.pass_noteheads[note_id]
            var clef: Dictionary = score_layout.clef_for(hand, score_layout.measure_for(source_event))
            var step: int = Geometry.staff_step(source_event.get("spelling", {}),clef)
            var below: bool = step < 4
            var y: float = maxf(head.y+gap*1.05,center+gap*2.9) if below \
                else minf(head.y-gap*1.05,center-gap*2.9)
            score_layout.glyphs.paint(canvas, "artic_"+value+("_below" if below else "_above"),
                head.x,y,gap*.9,ink,true)


func paint_hairpins(canvas, frame: RenderPass, left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # Wedge lines are structural ink, like pedal lines and volta brackets.
    # Original endpoints stay on the score's fixed beat score_layout.timeline, and a
    # clipped screen viewport displays the exact same interpolated slope.
    var pending: Dictionary = {}
    for mark in score_layout.source_expressions:
        if str(mark.get("kind", "")) != "hairpin":
            continue
        var hand: String = score_layout.display_staff(mark)
        var key: String = hand+"|"+str(mark.get("number", "1"))
        var kind: String = str(mark.get("value", ""))
        if kind in ["crescendo", "diminuendo"]:
            pending[key] = mark
            continue
        if kind != "stop" or not pending.has(key):
            continue
        var start: Dictionary = pending[key]
        pending.erase(key)
        if not frame.span_visible(start,mark):
            continue
        var begin: float = float(start.get("beat", 0.0))
        var end: float = float(mark.get("beat", 0.0))
        if end <= begin or begin > right+.5 or end < left-.5:
            continue
        var first_x: float = score_layout.timeline.screen_x(
            begin, clock, playhead_x, frame.play_from_beat)+gap*.48
        var last_x: float = score_layout.timeline.screen_x(
            end, clock, playhead_x, frame.play_from_beat)-gap*.25
        if last_x <= first_x:
            continue
        var x0: float = maxf(-gap, first_x)
        var x1: float = minf(score_layout.size.x+gap, last_x)
        if x1 <= x0:
            continue
        var open_start: float = gap*.06 if str(start.get("value")) == "crescendo" else gap*.47
        var open_end: float = gap*.47 if str(start.get("value")) == "crescendo" else gap*.06
        var t0: float = clampf((x0-first_x)/(last_x-first_x), 0.0, 1.0)
        var t1: float = clampf((x1-first_x)/(last_x-first_x), 0.0, 1.0)
        var half0: float = lerpf(open_start,open_end,t0)*.5
        var half1: float = lerpf(open_start,open_end,t1)*.5
        var y: float = score_layout.staff_center(hand)+gap*3.55
        var ink: Color = frame.event_ink(score_layout,start)
        canvas.draw_line(Vector2(x0,y-half0),Vector2(x1,y-half1),ink,1.3,true)
        canvas.draw_line(Vector2(x0,y+half0),Vector2(x1,y+half1),ink,1.3,true)


func paint_volta_endings(canvas, frame: RenderPass, left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # Volta brackets are structural rule lines with an engraved text label;
    # neither the repeat marks nor the transport clock causes an auto-repeat.
    var pending: Dictionary = {}
    var ends: Array = []
    for measure in score_layout.timeline.measures:
        for location in ["left", "right"]:
            var mark: Variant = measure.get(location+"_barline")
            if not mark is Dictionary:
                continue
            var ending: Variant = mark.get("ending")
            if not ending is Dictionary:
                continue
            var number: String = str(ending.get("number", ""))
            var kind: String = str(ending.get("type", ""))
            var beat: float = float(measure.get(
                "start_beat" if location == "left" else "end_beat", 0.0))
            if kind == "start":
                pending[number] = beat
            elif kind in ["stop", "discontinue"] and pending.has(number):
                ends.append({"start": float(pending[number]), "end": beat,
                    "number": number, "closed": kind == "stop"})
                pending.erase(number)
    # A source excerpt may end inside an open volta. Never silently lose it.
    for number in pending:
        ends.append({"start": float(pending[number]),
            "end": score_layout.timeline.duration_beats, "number": str(number), "closed": false})
    var y: float = score_layout.staff_center("right")-gap*5.05
    for ending in ends:
        var first: float = float(ending["start"])
        var last: float = float(ending["end"])
        if first > right+.5 or last < left-.5 or last <= first:
            continue
        var replaced := false
        if frame.score_loop_enabled:
            var interval := {"start_beat":frame.pass_start+first,"end_beat":frame.pass_start+last}
            for preparation in frame.preparation_history.values():
                if frame.intervals_overlap(interval,preparation["measure"]):
                    replaced = true
                    break
        if replaced:
            continue
        var x0: float = score_layout.timeline.screen_x(first,clock,playhead_x,frame.play_from_beat)
        var x1: float = score_layout.timeline.screen_x(last,clock,playhead_x,frame.play_from_beat)
        var start_x: float = maxf(-gap,x0)
        var end_x: float = minf(score_layout.size.x+gap,x1)
        if end_x <= start_x:
            continue
        canvas.draw_line(Vector2(start_x,y),Vector2(end_x,y),NOTE_INK,1.3,true)
        if x0 >= -gap and x0 <= score_layout.size.x+gap:
            canvas.draw_line(Vector2(x0,y),Vector2(x0,y+gap*.85),NOTE_INK,1.3,true)
            canvas.draw_string(ThemeDB.fallback_font,Vector2(x0+gap*.35,y-gap*.3),
                str(ending["number"])+"." if not str(ending["number"]).ends_with(".")
                else str(ending["number"]),
                HORIZONTAL_ALIGNMENT_LEFT,-1,roundi(gap*.92),NOTE_INK)
        if bool(ending["closed"]) and x1 >= -gap and x1 <= score_layout.size.x+gap:
            canvas.draw_line(Vector2(x1,y),Vector2(x1,y+gap*.85),NOTE_INK,1.3,true)


func practice_barline(canvas, frame: RenderPass, x: float, mark: Dictionary, gap: float) -> void:
    paint_barline(canvas,frame,{"x":x,"style":mark.get("style","regular"),"repeat":mark.get("repeat",""),
        "segments":[{"top":score_layout.staff_center("right")-gap*2.0,"bottom":score_layout.staff_center("left")+gap*2.0}]},gap)


func barline_left_limit(x: float, mark: Dictionary, gap: float) -> float:
    var limit := INF
    for stroke in score_layout.barline_strokes(str(mark.get("style","regular")),gap):
        limit = minf(limit,x+float(stroke["offset"])-float(stroke["width"])*.5)
    if str(mark.get("repeat","")) in ["backward","both"] and is_finite(limit):
        limit = minf(limit,x-gap*.92-float(score_layout.glyphs.bounds["repeat_dot"][2])*gap/500.0)
    return limit


func context_meter_x(measure: Dictionary, x: float, gap: float,
        opening: bool, right_limit: float = INF) -> float:
    var center: float = x-gap*1.6-(76.0*gap/17.0 if opening else 0.0)
    if not is_finite(right_limit):
        return center
    var half_width := 0.0
    for value in measure.get("meter",[4,4]):
        var text: String = str(int(value))
        var widest := 0.0
        for digit in text:
            widest = maxf(widest,float(score_layout.glyphs.bounds["time_"+digit][2])*gap/500.0)
        half_width = maxf(half_width,float(text.length()-1)*gap*1.10*.5+widest)
    return minf(center,right_limit-half_width-3.0)


func paint_context(canvas, frame: RenderPass, measure: Dictionary, previous_measure: Dictionary, x: float,
        gap: float, opening: bool, meter_right_limit: float = INF) -> bool:
    var header_scale: float = gap/17.0
    var header_shift: float = 76.0*header_scale if opening else 0.0
    var crowded_meter: bool = meter_is_crowded(measure,previous_measure,gap)
    for staff in ["right","left"]:
        var center: float = score_layout.staff_center(staff)
        var clef: Dictionary = score_layout.clef_for(staff,measure)
        var signatures: Dictionary = measure.get("keys",{})
        var signature: int = int(signatures.get(staff,0))
        var previous_keys: Dictionary = previous_measure.get("keys",{})
        var key_changed: bool = signature != int(previous_keys.get(staff,999))
        var change_marks: Array = []
        if key_changed:
            # Cancelling an old signature requires visible naturals,
            # even when the new signature is C major (zero accidentals).
            var previous_fifths: int = int(previous_keys.get(staff,0))
            var cancelled: Array = ([] if opening else
                Geometry.key_cancellation_steps(clef,previous_fifths,signature))
            var incoming: Array = Geometry.signature_steps(clef,signature)
            for step in cancelled:
                change_marks.append({"step":step,"accidental":"natural"})
            for step in incoming:
                change_marks.append({"step":step,"accidental":
                    "sharp" if signature > 0 else "flat"})
        if opening or score_layout.clef_for(staff,previous_measure) != clef:
            # Cancellation naturals occupy the same signature block as the
            # incoming accidentals. Reserve the complete block before placing
            # a clef, including when the destination signature is empty.
            var key_columns: int = maxi(absi(signature),change_marks.size())
            paint_clef(canvas,frame,x-(86.0+float(key_columns)*14.0)*header_scale-header_shift,
                center,clef,gap,frame.ink(staff))
        if key_changed:
            for i in range(change_marks.size()):
                var mark: Dictionary = change_marks[i]
                var glyph_x: float = x-(39.0+float(change_marks.size()-i)*14.0)*header_scale-header_shift
                var glyph_y: float = Geometry.note_y(int(mark["step"]),
                    center+2.0*gap,gap)
                symbol_painter.paint_accidental(canvas,frame,glyph_x,glyph_y,
                    str(mark["accidental"]),frame.ink(staff),gap)
        if (opening or previous_measure.get("meter",[]) !=
                measure.get("meter",[])) and not crowded_meter:
            var meter: Array = measure.get("meter",[4,4])
            if meter.size() >= 2:
                var meter_x: float = context_meter_x(measure,x,gap,opening,meter_right_limit)
                paint_meter_number(canvas,frame,int(meter[0]), meter_x,
                    center-gap*.95, frame.ink(staff), gap)
                paint_meter_number(canvas,frame,int(meter[1]), meter_x,
                    center+gap*.8, frame.ink(staff), gap)
    if crowded_meter:
        paint_meter_above_staff(canvas,frame,measure,x,gap)
    return crowded_meter


func paint_preparation_measure(canvas, frame: RenderPass, measure: Dictionary, previous: Dictionary,
        gap: float, playhead_x: float, opening: bool = false) -> void:
    var first: float = float(measure["start_beat"])
    var last: float = float(measure["end_beat"])
    var x0: float = playhead_x+(first-frame.visual_scroll_beat)*score_layout.timeline.pixels_per_beat
    var x1: float = playhead_x+(last-frame.visual_scroll_beat)*score_layout.timeline.pixels_per_beat
    if x1<-gap*16.0 or x0>score_layout.size.x+gap*16.0:
        return
    # Source and practice measures share exactly the same boundary transform.
    # Move context score_layout.glyphs for clearance; never shorten the silent measure.
    var left_rule: float = BarlineLayout.project(first,score_layout.timeline,frame.visual_scroll_beat,playhead_x,0.0,gap)
    var right_rule: float = BarlineLayout.project(last,score_layout.timeline,frame.visual_scroll_beat,playhead_x,0.0,gap)
    paint_context(canvas,frame,measure,previous,x0,gap,opening,
        barline_left_limit(left_rule,measure.get("left_barline",{}),gap))
    practice_barline(canvas,frame,left_rule,measure.get("left_barline",{}),gap)
    practice_barline(canvas,frame,right_rule,measure.get("right_barline",{}),gap)
    for event in measure["events"]:
        # Semantic full-measure silence uses the authentic hanging rest,
        # irrespective of its meter-dependent duration. It is not a note.
        var staff: String = str(event["staff"])
        symbol_painter.paint_rest(canvas,frame,(left_rule+right_rule)*.5,score_layout.staff_center(staff)+Geometry.rest_staff_offset("whole")*gap,
            "whole",0,frame.ink(staff),gap)
