extends RefCounted
## Dynamic native presentation and retained-ink composition. Its state is
## display-only; score mutation and take admission stay in their owners.
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const RenderPass := preload("res://notation/native/render_pass.gd")
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
const SourcePassPainter := preload("res://notation/native/source_pass_painter.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")
const RetainedNoteProjection := preload("res://notation/native/retained_note_projection.gd")
const CursorInkClearance := preload("res://notation/native/cursor_ink_clearance.gd")
const AmbientMeterGeometry := preload("res://notation/native/ambient_meter_geometry.gd")
var engraving
var layout:
    get: return engraving.layout
var timeline:
    get: return engraving.timeline
var glyphs:
    get: return engraving.glyphs
var annotations:
    get: return engraving.annotations
var context_painter:
    get: return engraving.context_painter
var size := Vector2.ZERO
var play_from_beat := 0.0
var active_hand := "both"
var clock_beat := 0.0
var stream_world_beat := 0.0
var bpm := 60.0
var running := false
var paused := false
var native_ready := false
var practice_timeline: Dictionary = {}
var transport_overlay_enabled := true
var runway_overlay := false
var external_backdrop := false
var note_status_source = null
var note_status_visible := true
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var drawn_note_instances: Array = []
var frame_scanned_events := 0
var frame_visible_beam_groups := 0
var fingering_pass_clocks: Array = []
var _ambient_anchor_world := 0.0

func _init(source) -> void:
    engraving = source

func update(viewport: Vector2, opening: float, hand: String, clock: float,
        world: float, tempo: float, playing: bool, stopped: bool,
        ready: bool, preparation: Dictionary) -> void:
    size = viewport
    play_from_beat = opening
    active_hand = hand
    clock_beat = clock
    stream_world_beat = world
    bpm = tempo
    running = playing
    paused = stopped
    native_ready = ready
    practice_timeline = preparation
    engraving.set_viewport(size)

func staff_gap() -> float:
    return engraving.gap()

func new_paint_frame(clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0) -> RenderPass:
    return engraving.new_frame(clock,playhead_x,gap,play_from_beat,
        active_hand,pass_index,pass_start)

func paint_retained_source(canvas: CanvasItem) -> RenderPass:
    return SourcePassPainter.paint(engraving,canvas,size,play_from_beat,active_hand)

func paint_retained_rest(canvas: CanvasItem) -> void:
    if practice_timeline.is_empty() or timeline.measures.is_empty():
        return
    var gap: float = staff_gap()
    var silence: Dictionary = practice_timeline["gap"].duplicate(true)
    silence["left_barline"] = timeline.measures[-1].get("right_barline",{})
    var incoming: Variant = timeline.measures[0].get("left_barline")
    if incoming is Dictionary:
        silence["right_barline"] = incoming
    var frame: RenderPass = new_paint_frame(0.0,0.0,gap,0,0.0)
    frame.visual_scroll_beat = float(silence["start_beat"])
    context_painter.paint_preparation_measure(canvas,frame,
        silence,timeline.measures[-1],gap,0.0,false)

func paint_retained_annotations(canvas: CanvasItem) -> void:
    if not native_ready:
        return
    var gap: float = staff_gap()
    var playhead_x: float = size.x*PLAYHEAD_FRACTION
    for annotation_pass in fingering_pass_clocks:
        var context := {
            "active_hand":active_hand,"play_from_beat":play_from_beat}
        if annotation_pass.has("stream_floor"):
            context["stream_floor"] = annotation_pass["stream_floor"]
            context["stream_ceiling"] = annotation_pass["stream_ceiling"]
        annotations.paint(canvas,float(annotation_pass["clock"]),playhead_x,gap,
            int(annotation_pass["pass_index"]),
            float(annotation_pass["pass_start"]),context)
    if runway_overlay:
        # The future overlay reuses the same fixed staff, brace and playhead
        # drawn by the current primary renderer. Only its notes scroll in.
        return
    # The genuine Verovio brace belongs ABOVE scrolling source ink at the
    # fixed left-hand edge, not inside the translated source segments.
    var staff_top: float = layout.barline_top(gap)
    var staff_bottom: float = layout.barline_bottom(gap)
    if not layout.focused_staff.is_empty():
        # One practiced staff has no grand-staff brace. Keep a thin source
        # system boundary without inventing or transposing notation.
        canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
            Color(NOTE_INK,.48),1.0,true)
        return
    # No backing panel: strips clip themselves at the gutter
    # (StreamLifecycle.LEFT_GUTTER_PX), so the brace sits on the backdrop.
    if glyphs.textures.has("brace"):
        VerovioGlyphs.draw_fit(canvas,glyphs.textures["brace"],
            Rect2(6,staff_top-2,18,staff_bottom-staff_top+4),false,NOTE_INK)
    canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)

func project_stream(online: Array, retained_all_segments: Array, playhead_x: float) -> void:
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var gap: float = staff_gap()
    var used: Dictionary = {}
    # The immutable online queue is chronologically ordered by printed
    # left edge; once one source/rest clip is entirely to the right of the
    # viewport, every later clip is too. Long pieces therefore do not
    # project thousands of offscreen measures on every animation frame.
    for item in online:
        var bounds: Vector2 = StreamLifecycle.screen_bounds(
            item,density,gap,timeline.sounding_duration_beats)
        var screen_left: float = playhead_x + (
            float(item["world_origin"])-stream_world_beat)*density+bounds.x
        if screen_left > size.x+1.0:
            break
        var segment = item.get("segment")
        var clip = item.get("clip")
        # Invalid records are retired by present_flow(), never mutated or
        # removed during CanvasItem._draw().
        if segment == null or not is_instance_valid(segment) or \
                clip == null or not is_instance_valid(clip):
            continue
        if not StreamLifecycle.project(item,stream_world_beat,playhead_x,
                density,gap,size,timeline.sounding_duration_beats):
            continue
        used[segment] = true
        if str(item.get("kind","source")) == "rest":
            continue
        var position: float = playhead_x + \
            (float(item["world_origin"])-stream_world_beat)*density
        var take_key: String = str(item.get("take_key",""))
        # Status ink is a child of this strip: it inherits the strip's exact
        # transform and clip window. Repaints only when its take changes.
        segment.sync_note_status(take_key,note_status_source,note_status_visible,
            bounds/maxf(1.0,density))
        var clip_bounds: Vector2 = bounds
        # Register every head the strip actually shows, including heads a
        # voice column displaced left of its source floor into the clip's
        # leading margin: they are painted, so they must stay interactive.
        # The same window the strip clips to: nothing behind the gutter.
        var window_left: float = maxf(position+clip_bounds.x,
            StreamLifecycle.LEFT_GUTTER_PX)
        var count: int = RetainedNoteProjection.append_visible(
            segment.note_instances,position,size.x,playhead_x,
            int(item["serial"]),drawn_note_instances,drawn_noteheads,
            window_left-position,clip_bounds.y,take_key,
            Vector2(window_left,position+clip_bounds.y))
        visible_symbols += count
        frame_scanned_events += count
        fingering_pass_clocks.append({
            "clock":stream_world_beat-float(item["world_origin"])-play_from_beat,
            "pass_index":0,"pass_start":0.0,
            "stream_floor":float(item.get("clip_floor",item["source_floor"])),
            "stream_ceiling":float(item.get("clip_ceiling",item["source_ceiling"]))})
    StreamLifecycle.present_pool(retained_all_segments,used)

func playhead_region() -> Rect2:
    # The bloom and precise timing line share these exact native coordinates.
    var gap: float = staff_gap()
    var top: float = layout.staff_center("right")-gap*3.8
    var bottom: float = layout.staff_center("left")+gap*3.7
    if not layout.focused_staff.is_empty():
        var center: float = layout.staff_center(layout.focused_staff)
        top = center-maxf(gap*8.0,size.y*.31)
        bottom = center+maxf(gap*9.0,size.y*.37)
    return Rect2(Vector2(size.x*PLAYHEAD_FRACTION,top),
        Vector2(1.0,maxf(1.0,bottom-top)))

func cursor_ink_clearances(gap: float, online: Array) -> Array:
    return CursorInkClearance.exclusions(
        stream_world_beat,gap,maxf(1.0,timeline.pixels_per_beat),
        engraving.cursor_engraved_events,online,
        layout,active_hand)

func paint_cursor_behind_ink(canvas: CanvasItem, online: Array, x: float, top: float, bottom: float,
        gap: float) -> void:
    # A bright cursor directly through a rest/note at its exact onset
    # creates an illegible composite and fails source-rest isolation.
    # Keep the fixed timing axis but leave only local vertical notches
    # where genuine glyph ink is crossing it; the mint halo stays behind.
    var cursor_y: float = top
    for interval in cursor_ink_clearances(gap,online):
        var start_y: float = clampf(float(interval.x),top,bottom)
        var end_y: float = clampf(float(interval.y),top,bottom)
        if start_y > cursor_y:
            canvas.draw_line(Vector2(x,cursor_y),Vector2(x,start_y),
                Design.HIGHLIGHT,2.4,true)
            canvas.draw_line(Vector2(x,cursor_y),Vector2(x,start_y),
                Color(Design.STONE,.62),.9,true)
        cursor_y = maxf(cursor_y,end_y)
    if cursor_y < bottom:
        canvas.draw_line(Vector2(x,cursor_y),Vector2(x,bottom),
            Design.HIGHLIGHT,2.4,true)
        canvas.draw_line(Vector2(x,cursor_y),Vector2(x,bottom),
            Color(Design.STONE,.62),.9,true)

func paint_empty_moving_staff(canvas: CanvasItem) -> void:
    # An unprepared or unloaded score still has the SAME world axis.
    # Never draw a static loading card in place of the moving bar.
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var line_gap: float = clampf(size.y/23.0,13.0,25.0)
    var centers: Array[float] = [size.y*.40,size.y*.70]
    for center in centers:
        for rule in range(5):
            var y: float = center+(float(rule)-2.0)*line_gap
            canvas.draw_line(Vector2(0.0,y),Vector2(size.x,y),
                Color(NOTE_INK,.43),SymbolPainter.STAFF_LINE_WIDTH,true)
    var ph: float = size.x*PLAYHEAD_FRACTION
    var pulse_width: float = 4.0*density
    var phase: float = fposmod(stream_world_beat*density,pulse_width)
    for index in range(-2,ceili(size.x/pulse_width)+3):
        var x: float = ph-phase+float(index)*pulse_width
        if x >= 0.0 and x <= size.x:
            canvas.draw_line(Vector2(x,centers[0]-line_gap*2.0),
                Vector2(x,centers[1]+line_gap*2.0),
                Color(NOTE_INK,.22),1.0,true)
    canvas.draw_line(Vector2(ph,centers[0]-line_gap*2.9),
        Vector2(ph,centers[1]+line_gap*2.9),
        Color(Design.MINT,.72),2.4,true)

func paint_staff(canvas: CanvasItem, online: Array) -> bool:
    if layout.size != size:
        layout.set_viewport(size)
    drawn_noteheads.clear()
    drawn_note_instances.clear()
    visible_symbols = 0
    frame_scanned_events = 0
    frame_visible_beam_groups = 0
    annotations.begin_frame()
    fingering_pass_clocks.clear()
    if size.x < 100.0 or size.y < 100.0:
        return false
    # The Practice stage supplies its vignette; stand-alone notation tests
    # and other native score consumers still receive the original dark ink.
    if not runway_overlay and not external_backdrop:
        canvas.draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
    var font: Font = ThemeDB.fallback_font
    if not native_ready or not timeline.has_score():
        if not runway_overlay:
            paint_empty_moving_staff(canvas)
        return false
    var gap: float = staff_gap()
    var playhead_x: float = size.x * PLAYHEAD_FRACTION
    # The precise line and GPU halo use one geometry contract.
    var line_region: Rect2 = playhead_region()
    var top: float = line_region.position.y
    var bottom: float = line_region.end.y
    # Always draw ten native rules; no copied or stitched raster systems.
    for staff in (layout.visible_staves() if not runway_overlay else []):
        var center: float = layout.staff_center(staff)
        var selected: bool = active_hand == "both" or active_hand == staff
        var ink: Color = NOTE_INK if selected else Color(DIM_INK,.46)
        for line_index in range(5):
            var y: float = center+(float(line_index)-2.0)*gap
            canvas.draw_line(Vector2(0,y),Vector2(size.x,y),
                Color(ink,SymbolPainter.STAFF_LINE_ALPHA if selected else .28),
                SymbolPainter.STAFF_LINE_WIDTH,true)
    # Empty idle and paused canvas: source ink is hidden while barlines
    # continue to move. Staff and playhead remain fixed and legible.
    if not runway_overlay:
        var density: float = maxf(1.0,timeline.pixels_per_beat)
        # Blank measures follow the actual MusicXML meter changes and the
        # same source world origin as the notation. The old fixed 4/4
        # modulo grid drifted through 3/4, 6/8 and pickup passages.
        var barline_top_y: float = layout.barline_top(gap)
        var barline_bottom_y: float = layout.barline_bottom(gap)
        var exposed: Dictionary = AmbientMeterGeometry.exposed_lines(
            stream_world_beat,size.x,playhead_x,density,gap,
            timeline.sounding_duration_beats,timeline.measures,_ambient_anchor_world,
            online)
        _ambient_anchor_world = float(exposed["anchor"])
        for x in exposed["positions"]:
            canvas.draw_line(Vector2(x,barline_top_y),
                Vector2(x,barline_bottom_y),
                Color(NOTE_INK,.20),1.0,true)
    # Keep the fixed playhead visible but BEHIND source ink. At exact
    # onset a foreground cursor previously covered small eighth-rest dots,
    # flagged stems and noteheads, preventing independent contour recovery.
    # Engraving is always painted later; the transport clock is unchanged.
    if transport_overlay_enabled and not runway_overlay:
        paint_cursor_behind_ink(canvas,online,playhead_x,top,bottom,gap)
        canvas.draw_circle(Vector2(playhead_x,top),9.0,Color(Design.MINT,.16))
        canvas.draw_circle(Vector2(playhead_x,top),3.7,Design.STONE)
        # Beat breathing is an accent on the fixed playhead, not a moving
        # alternate clock. Music, retry preparation and calibration each
        # retain the application's single beat axis.
        var fraction := fposmod(stream_world_beat,1.0)
        var impulse := pow(1.0-fraction,2.4)
        var center := Vector2(playhead_x,top+gap*.22)
        canvas.draw_circle(center,5.0+10.0*impulse,
            Color(PREVIEW_LIGHT,.15+.12*impulse))
        canvas.draw_arc(center,7.0+10.0*impulse,0.0,TAU,40,
            Color(PREVIEW_LIGHT,.40+.50*impulse),2.4,true)
    # The count-in runs on the same clock, but its leading boundary is
    # intentionally NOT a printed barline: it sits before the clef/header
    # and used to look like an orphaned vertical rule in the score.
    # One semantic practice timeline owns both source-copy placement and
    # preparation silence. No independently inferred final-bar duration.
    # All phases use the exact same absolute world-axis projection.
    # Play/Pause/Retry cannot switch cameras or reconstruct source ink.
    return true

func paint_diagnostics(canvas: CanvasItem) -> void:
    var font: Font = ThemeDB.fallback_font
    if OS.get_environment("PIANO_TEACHER_NATIVE_DIAGNOSTICS") == "1":
        var phase: String = "PAUSED" if paused else \
            "COUNT-IN" if clock_beat < 0.0 and running else \
            "PLAYING" if running else "READY"
        canvas.draw_string(font,Vector2(14.0,22.0),
            "NATIVE · %s · %.0f px/beat · %.0f BPM · %d events" % [
                phase,timeline.pixels_per_beat,bpm,frame_scanned_events],
            HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)
