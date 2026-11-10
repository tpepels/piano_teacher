extends RefCounted
## Compile the sole canonical source into one retained CanvasItem command list.
## This is invoked only when the source score or engraving context changes; it owns
## authored engraving composition, not transport, animation or hit testing.
const RenderPass := preload("res://notation/native/render_pass.gd")
const EventWindow := preload("res://notation/native/event_window.gd")
const Design := preload("res://practice_theme.gd")

static func _measure_index_at_or_after(measures: Array, beat: float) -> int:
    # Per-measure retained canvases must not re-scan the whole original
    # composition just to locate their own one measure of barline/context.
    var lo := 0
    var hi: int = measures.size()
    while lo < hi:
        var mid: int = (lo+hi)>>1
        if float(measures[mid].get("start_beat",0.0)) < beat:
            lo = mid+1
        else:
            hi = mid
    return lo


static func paint(view, canvas: CanvasItem) -> RenderPass:
    # Every source copy is identical immutable native score ink. Source
    # context is not rebuilt on Play, Retry, Pause or the arrival of a note.
    var target: CanvasItem = canvas
    var layout = view.layout
    var timeline = view.timeline
    var context_painter = view.context_painter
    var symbols = view.symbols
    var play_from_beat: float = view.play_from_beat
    var gap: float = view.staff_gap()
    var camera_clock: float = -play_from_beat
    var playhead_x := 0.0
    var first_value: Variant = canvas.get("source_floor")
    var last_value: Variant = canvas.get("source_ceiling")
    var source_first: float = (
        float(first_value) if first_value is float or first_value is int
        else 0.0)
    var source_last: float = (
        float(last_value) if last_value is float or last_value is int
        else timeline.duration_beats)
    source_first = clampf(source_first,0.0,timeline.duration_beats)
    source_last = clampf(source_last,source_first,timeline.duration_beats)
    # Each CanvasItem compiles only its own measure (plus a small connector
    # margin). This bounds total drawing work to O(source length), rather
    # than one entire-piece command list for EVERY measure strip.
    var left: float = maxf(0.0,source_first-.25)
    var right: float = minf(timeline.duration_beats,source_last+.25)
    var retained_width: float = maxf(view.size.x,
        (right+1.0)*timeline.pixels_per_beat+view.size.x)
    var frame: RenderPass = view._new_paint_frame(
        camera_clock,playhead_x,gap,0,0.0)
    frame.source_floor = source_first
    frame.source_ceiling = source_last
    layout.set_viewport(Vector2(retained_width,view.size.y))
    var font: Font = ThemeDB.fallback_font
    var measure_index: int = _measure_index_at_or_after(
        timeline.measures,left-.00001)
    var previous_measure: Dictionary = (
        timeline.measures[measure_index-1] if measure_index > 0 else {})
    for index in range(measure_index,timeline.measures.size()):
        var measure: Dictionary = timeline.measures[index]
        var at: float = float(measure.get("start_beat",0.0))
        var first: bool = index == 0
        if at > right+.00001:
            break
        if not frame.event_visible(measure):
            previous_measure = measure
            continue
        var x: float = timeline.screen_x(at,camera_clock,playhead_x,play_from_beat)
        var barline: Dictionary = layout.barline_geometry(
            measure,camera_clock,playhead_x,gap,play_from_beat)
        if not barline.is_empty() and float(barline["x"])>=-gap*2.0 and \
                float(barline["x"])<=retained_width+gap*2.0:
            context_painter.paint_barline(target,frame,barline,gap)
        var crowded_meter: bool = context_painter.paint_context(
            target,frame,measure,previous_measure,x,gap,first)
        if not first and not crowded_meter and x>=0.0 and x<=retained_width:
            target.draw_string(font,Vector2(x+gap*.4,
                layout.staff_center("right")-gap*4.3),
                str(int(measure.get("number",0))),
                HORIZONTAL_ALIGNMENT_LEFT,-1,11,Design.STAFF_MUTED)
        previous_measure = measure
    # The actual ending of the last measure has its own terminal barline.
    # It must not disappear simply because no following measure exists.
    var terminal: Dictionary = (
        layout.terminal_barline_geometry(
            camera_clock,playhead_x,gap,play_from_beat)
        if source_last >= timeline.duration_beats-.00001 else {})
    if not terminal.is_empty() and float(terminal["x"]) >= -gap*2.0 and \
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

