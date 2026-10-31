extends RefCounted
## Compile one source or recovery copy into a retained CanvasItem command list.
## This is invoked only when the score or recovery context changes; it owns
## authored engraving composition, not transport, animation or hit testing.
const RenderPass := preload("res://notation/native/render_pass.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
const EventWindow := preload("res://notation/native/event_window.gd")
const Design := preload("res://practice_theme.gd")

static func paint(view, canvas: CanvasItem, variant: String,
        context: Dictionary = {}) -> RenderPass:
    # Only a retained CanvasItem may invoke authored source painting. No
    # frame-time source reconstruction route exists in the practice view.
    var target: CanvasItem = canvas
    var layout = view.layout
    var timeline = view.timeline
    var practice_timeline: Dictionary = view.practice_timeline
    var preparation_history: Dictionary = view.preparation_history
    var context_painter = view.context_painter
    var symbols = view.symbols
    var play_from_beat: float = view.play_from_beat
    var gap: float = view.staff_gap()
    var camera_clock: float = -play_from_beat
    var playhead_x := 0.0
    var stride: float = float(practice_timeline.get("stride_beats",0.0))
    var pass_index: int = int(context.get("pass_index",1 if variant == "repeat" else 0))
    var pass_start: float = float(context.get("pass_start",stride if variant == "repeat" else 0.0))
    var retained_width: float = maxf(view.size.x,
        (timeline.duration_beats+1.0)*timeline.pixels_per_beat+view.size.x)
    var frame: RenderPass = view._new_paint_frame(camera_clock,playhead_x,gap,pass_index,pass_start)
    frame.score_loop_enabled = variant != "once"
    if variant == "recovery":
        frame.preparation_history = preparation_history.duplicate(true)
        frame.current_preparation = frame.preparation_history.get(pass_start,{})
    else:
        frame.preparation_history = {}
        frame.current_preparation = {}
    layout.set_viewport(Vector2(retained_width,view.size.y))
    var current_preparation: Dictionary = frame.current_preparation
    var font: Font = ThemeDB.fallback_font
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+retained_width/timeline.pixels_per_beat
    var previous_measure: Dictionary = {}
    if pass_index>0:
        previous_measure = view._practice_context_before(pass_start,float(practice_timeline["stride_beats"]))
        previous_measure["start_beat"] = float(previous_measure["start_beat"])-pass_start
        previous_measure["end_beat"] = float(previous_measure["end_beat"])-pass_start
    for measure in timeline.measures:
        var at: float = float(measure.get("start_beat",0.0))
        var first: bool = measure == timeline.measures[0]
        var target_boundary := false
        if not current_preparation.is_empty():
            var silence: Dictionary = current_preparation["measure"]
            target_boundary = absf(at-float(current_preparation["source_from_beat"]))<.00001
            if target_boundary:
                previous_measure = silence.duplicate(true)
                previous_measure["start_beat"] = float(silence["start_beat"])-pass_start
                previous_measure["end_beat"] = float(silence["end_beat"])-pass_start
        if not target_boundary and not frame.event_visible(measure):
            continue
        if at<left-.7 or at>right+.7:
            previous_measure = measure
            continue
        var x: float = timeline.screen_x(at,camera_clock,playhead_x,play_from_beat)
        var opening: bool = first and pass_index==0 and current_preparation.is_empty()
        if not target_boundary and not (first and pass_index>0):
            var barline: Dictionary = layout.barline_geometry(measure,camera_clock,playhead_x,gap,play_from_beat)
            if not barline.is_empty() and float(barline["x"])>=-gap*2.0 and float(barline["x"])<=retained_width+gap*2.0:
                context_painter.paint_barline(target,frame,barline,gap)
        var meter_right_limit := INF
        if target_boundary or (first and pass_index>0):
            var incoming: Variant = current_preparation["measure"].get("right_barline") if target_boundary else measure.get("left_barline")
            var mark: Dictionary = incoming if incoming is Dictionary else {"style":"regular","repeat":""}
            meter_right_limit = context_painter.barline_left_limit(
                BarlineLayout.project(at,timeline,camera_clock,playhead_x,play_from_beat,gap),mark,gap)
        var crowded_meter: bool = context_painter.paint_context(target,frame,measure,previous_measure,x,gap,opening,meter_right_limit)
        if not first and not crowded_meter and x>=0.0 and x<=retained_width:
            target.draw_string(font,Vector2(x+gap*.4,layout.staff_center("right")-gap*4.3),
                str(int(measure.get("number",0))),HORIZONTAL_ALIGNMENT_LEFT,-1,11,Design.STAFF_MUTED)
        previous_measure = measure
    # The actual ending of the last measure has its own terminal barline.
    # It must not disappear simply because no following measure exists.
    var terminal: Dictionary = layout.terminal_barline_geometry(
        camera_clock,playhead_x,gap,play_from_beat)
    if not frame.score_loop_enabled and not terminal.is_empty() and float(terminal["x"]) >= -gap*2.0 and \
            float(terminal["x"]) <= retained_width+gap*2.0:
        context_painter.paint_barline(target,frame,terminal,gap)
    context_painter.paint_volta_endings(target,frame,left,right,camera_clock,playhead_x,gap)
    # Source geometry must already exist before this frame. Rebuilding
    # glyph spacing during a scroll is forbidden: it stalls the musical UI.
    if layout.cached_offsets_gap < 0.0 or absf(layout.cached_offsets_gap-gap) > .001:
        push_error("Static engraving cache is stale; reprepare before playback")
        layout.set_viewport(view.size)
        return frame
    var head_offsets: Dictionary = layout.cached_head_offsets
    var beam_data: Dictionary = view.beam_plan(gap, camera_clock,
        playhead_x, head_offsets,frame)
    var beam_stems: Dictionary = beam_data.get("stems", {})
    var compound_ids: Dictionary = {}
    for event in EventWindow.visible(layout.ordered_events,left,right,frame):
        if compound_ids.has(str(event.get("id",""))):
            continue
        var at: float = float(event.get("beat", 0.0))
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var staff: String = str(event.get("staff","right"))
        var ink: Color = frame.event_ink(layout,event)
        if str(event.get("kind","")) == "note":
            var members: Array = symbols.paint_engraved_chord(target,frame,event,x,gap,ink,
                beam_stems.get(str(event.get("id","")), {}))
            if not members.is_empty():
                for id in members:
                    compound_ids[id] = true
                frame.visible_symbols += members.size()
                continue
            symbols.paint_note(target,frame,event,x,gap,ink,
                beam_stems.get(str(event.get("id", "")), {}),
                float(head_offsets.get(str(event.get("id", "")), 0.0)))
        else:
            symbols.paint_rest(target,frame,x,layout.rest_y(event,gap),
                str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        frame.visible_symbols += 1
    symbols.paint_beams(target,frame,beam_data, gap)
    symbols.paint_ties(target,frame,playhead_x,camera_clock,gap)
    symbols.paint_slurs(target,frame,playhead_x,camera_clock,gap)
    symbols.paint_tuplet_brackets(target,frame,camera_clock,playhead_x,gap)
    context_painter.paint_expressions(target,frame,left,right,camera_clock,playhead_x,gap)
    context_painter.paint_hairpins(target,frame,left,right,camera_clock,playhead_x,gap)
    symbols.paint_grace_notes(target,frame,gap)
    layout.set_viewport(view.size)
    return frame

