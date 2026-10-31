extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation is rejected; production reports a preparation error.
const Geometry := preload("res://notation/native/geometry.gd")
const ScoreIndex := preload("res://notation/native/score_index.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
const EngravingReadiness := preload("res://notation/native/engraving_readiness.gd")
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT
const ViewportFit := preload("res://notation/native/viewport_fit.gd")
const MAX_STAFF_GAP := ViewportFit.MAX_STAFF_GAP
# A piano learner needs upcoming notation in view. Preserve the largest
# authentic staff that leaves at least this many beats to the right of the
# fixed playhead. No temporal warping, font imitation or overlap is allowed.
const FingeringPlacement := preload("res://notation/native/fingering_placement.gd")

signal fingering_change_requested(source_id: String, finger: Variant)

# Annotation cells live on the same immutable score axis as the note ink.
# Cache once per score/vertical size; scrolling only translates their X.
var transport_overlay_enabled := true
var fingering_pass_clocks: Array = []

func set_transport_overlay_enabled(enabled: bool) -> void:
    transport_overlay_enabled = enabled
    queue_redraw()

func set_fingering_annotations_enabled(enabled: bool) -> void:
    annotations.set_enabled(enabled)
    queue_redraw()

const ScoreLayout := preload("res://notation/native/score_layout.gd")
var glyphs = VerovioGlyphs.new():
    set(value):
        glyphs = value
        if layout != null:
            layout.glyphs = value
var layout = ScoreLayout.new(timeline,glyphs):
    set(value):
        layout = value
        layout.set_viewport(size)
        if ink_geometry != null:
            ink_geometry.score = value
            ink_geometry.clear_cache()
        if connector_geometry != null:
            connector_geometry.score = value
            connector_geometry.clear_cache()
        if annotations != null:
            annotations.score_layout = value
            annotations.obstacles.score_layout = value
            annotations.clear()
        if symbols != null:
            symbols.score_layout = value
        if context_painter != null:
            context_painter.score_layout = value
const InkGeometry := preload("res://notation/native/ink_geometry.gd")
var ink_geometry = InkGeometry.new(layout)
const ConnectorGeometry := preload("res://notation/native/connector_geometry.gd")
var connector_geometry = ConnectorGeometry.new(layout)
const FingeringAnnotations := preload("res://notation/native/fingering_annotations.gd")
const SourceVisibility := preload("res://notation/native/source_visibility.gd")
const EventWindow := preload("res://notation/native/event_window.gd")
var annotations = FingeringAnnotations.new(layout,connector_geometry)
const RenderPass := preload("res://notation/native/render_pass.gd")
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")
const ContextPainter := preload("res://notation/native/context_painter.gd")
const RetainedSegment := preload("res://notation/native/retained_segment.gd")
const RetainedAnnotationOverlay := preload("res://notation/native/retained_annotation_overlay.gd")
var symbols = SymbolPainter.new(layout,connector_geometry)
var context_painter = ContextPainter.new(layout,symbols)

var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var drawn_note_instances: Array = []
var preparation_history: Dictionary = {}
var selected_density := 0.0
var staff_gap_limit := MAX_STAFF_GAP
var configured_density: float = Timeline.DEFAULT_PIXELS_PER_BEAT
# Immutable musical structure is indexed ONCE when a passage changes.
# Each frame then visits only visible onsets, beams and ties.
var ink_density_witness: Dictionary = {}
var selected_density_witness: Dictionary = {}
var expected_slur_pairs: Array = []
var slur_extraction_complete := true
var expected_beam_groups: Array = []
var beam_extraction_complete := true
# Per-rest displacements measured in staff spaces; fixed for one score revision.
var frame_scanned_events := 0
var frame_visible_beam_groups := 0
# The small reusable source/silence CanvasItems retain Godot's actual
# draw command buffers. A transport frame translates them; it never repaints
# MusicXML structures.
var retained_first_once: Node2D
var retained_first_loop: Node2D
var retained_repeat_segments: Array = []
var retained_rest_segments: Array = []
var retained_recovery_sources: Dictionary = {}
var retained_recovery_rests: Dictionary = {}
var retained_annotations: Node2D
const RETAINED_POOL_SIZE := 5

func _init() -> void:
    resized.connect(func():
        layout.set_viewport(size)
        if native_ready and size.y >= 100.0:
            _prepare_static_geometry()
            _invalidate_retained_segments()
    )
    annotations.fingering_change_requested.connect(func(source_id, finger):
        fingering_change_requested.emit(source_id,finger))
    mouse_filter = Control.MOUSE_FILTER_PASS
    tooltip_text = "Right-click a note or tap a finger number to change its fingering"

func clear_score() -> void:
    annotations.clear()
    super.clear_score()
    layout.timeline = timeline
    timeline.set_density(configured_density)
    staff_gap_limit = MAX_STAFF_GAP
    native_ready = false
    failure_reason = ""
    _clear_retained_segments()
    layout.clear()

func set_density(value: float) -> bool:
    if not super.set_density(value):
        return false
    configured_density = value
    if native_ready:
        # Source-space X changed; both geometry and CanvasItem ink are stale.
        _prepare_static_geometry()
        _invalidate_retained_segments()
    return true

func set_density_from_env() -> bool:
    if not super.set_density_from_env():
        return false
    configured_density = timeline.pixels_per_beat
    return true

func set_verovio_glyphs(items: Dictionary, note_items: Dictionary = {},
        tie_items: Dictionary = {}, chord_items: Dictionary = {},
        beam_items: Dictionary = {},
        tuplet_items: Dictionary = {},
        slur_items: Dictionary = {},
        required_slurs: Array = [], slurs_complete: bool = true,
        required_beams: Array = [], beams_complete: bool = true) -> bool:
    annotations.obstacles.clear()
    connector_geometry.clear_cache()
    ink_geometry.clear_cache()
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
    connector_geometry.clear_cache()
    annotations.clear()
    preparation_history.clear()
    drawn_note_instances.clear()
    native_ready = false
    _clear_retained_segments()
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
    # The older rhythm-only heuristic reserved >=25 px for *every* short
    # source interval, even if those notes are in different registers or
    # independent voices and their actual Verovio glyphs cannot collide.
    # This made one .0625-beat attack impose 400+ px/beat on an entire 4/4
    # measure. Start at the selected density and let the full authentic
    # ink rectangles below determine the minimum safe whole-score scale.
    # Onset positions remain perfectly linear; no note is shifted in time.
    # Retain the original hard rejection for pathological near-coincident
    # distinct attacks (<~.003 beats): no compositor may pretend that an
    # unrenderable source has enough clearance simply because registers differ.
    if Geometry.required_density(
            timeline.model.get("notation_events", []), configured_density,
            timeline.MAX_SCORE_PIXELS_PER_BEAT) < 0.0:
        failure_reason = "Rhythm too dense for one fixed native horizontal scale"
        notice = failure_reason
        return false
    var density: float = configured_density
    if not timeline.set_score_density(density):
        failure_reason = timeline.last_error
        notice = failure_reason
        return false
    selected_density = density
    layout.set_viewport(size)
    layout.rebuild_index()
    failure_reason = _missing_source_engraving()
    if not failure_reason.is_empty():
        notice = failure_reason
        return false
    # Genuine adjacent 32nd-triplet notes before a printed accidental can
    # force very wide beat spacing. A full 22px staff previously won the
    # first-feasible test even when only ~1.4 future beats fit on-screen.
    # Evaluate smaller *authentic* Verovio glyph scales before choosing;
    # use the largest staff that preserves reading context. Crucially each
    # candidate recomputes true ink collision clearance; never just cap BPM
    # distance or hide/shift a source accidental.
    var fitted: Dictionary = ViewportFit.choose(layout,ink_geometry,density,PLAYHEAD_FRACTION)
    if not fitted["ok"]:
        failure_reason = fitted["error"]
        notice = failure_reason
        return false
    var ink_density: float = fitted["density"]
    staff_gap_limit = fitted["staff_gap"]
    selected_density_witness = fitted["witness"]
    ink_density_witness = fitted["last_witness"]
    if not timeline.set_score_density(ink_density):
        failure_reason = timeline.last_error
        notice = failure_reason
        return false
    selected_density = ink_density
    layout.cached_staff_gap = -1.0
    layout.cached_gap_height = -1.0
    layout.cached_offsets_gap = -1.0
    layout.cached_head_offsets.clear()
    layout.cached_accidental_offsets.clear()
    # No source connector or chord geometry may first be prepared when its
    # measure scrolls into view. All immutable structures use source-space X.
    _prepare_static_geometry()
    failure_reason = ""
    native_ready = true
    _install_retained_segments()
    queue_redraw()
    return true

# No provider-specific state reaches this view. Invalid and genuinely unknown
# assignments produce no number; the source attack remains editable.
func _open_fingering_editor(point: Vector2) -> bool:
    return annotations.open_editor(self,point,staff_gap(),drawn_note_instances)

func _gui_input(event: InputEvent) -> void:
    layout.set_viewport(size)
    if not native_ready:
        return
    if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
        if _open_fingering_editor(event.position):
            accept_event()
    elif event is InputEventScreenTouch and event.pressed:
        if _open_fingering_editor(event.position):
            accept_event()
    elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
        for item in annotations.drawn_fingerings:
            if item["rect"].grow(5.0).has_point(event.position):
                if _open_fingering_editor(event.position):
                    accept_event()
                break

# Only native compositor fragments with unambiguous original Verovio ink.
# Reject incomplete engraving before playback can become ready.
func _missing_source_engraving() -> String:
    return EngravingReadiness.missing(
        layout, glyphs, connector_geometry, expected_beam_groups,
        beam_extraction_complete, expected_slur_pairs,
        slur_extraction_complete)


func staff_gap() -> float:
    layout.set_viewport(size)
    return layout.staff_gap(staff_gap_limit)

func _prepare_static_geometry() -> void:
    var prepared_gap: float = staff_gap()
    layout.cached_head_offsets = layout.engraved_head_offsets(prepared_gap)
    layout.cached_accidental_offsets = Geometry.accidental_offsets(
        layout.ordered_events, prepared_gap, layout.cached_head_offsets,
        glyphs.bounds)
    layout.cached_offsets_gap = prepared_gap
    layout.prepare_event_positions(prepared_gap)
    connector_geometry.clear_cache()
    connector_geometry.prewarm_tie_clearances(prepared_gap)
    connector_geometry.prewarm_beam_layout(prepared_gap,layout.cached_head_offsets)
    connector_geometry.prewarm_slur_geometry(prepared_gap)

func _clear_retained_segments() -> void:
    for segment in [retained_first_once,retained_first_loop,retained_annotations]:
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    for segment in retained_repeat_segments + retained_rest_segments:
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    retained_first_once = null
    retained_first_loop = null
    retained_annotations = null
    retained_repeat_segments.clear()
    retained_rest_segments.clear()
    for segment in retained_recovery_sources.values()+retained_recovery_rests.values():
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    retained_recovery_sources.clear()
    retained_recovery_rests.clear()

func _new_retained_segment(kind: String, variant: String,
        context: Dictionary = {}) -> Node2D:
    var segment: Node2D = RetainedSegment.new()
    add_child(segment)
    segment.configure(self,kind,variant,context)
    return segment

func _install_retained_segments() -> void:
    _clear_retained_segments()
    clip_contents = true
    retained_first_once = _new_retained_segment("source","once")
    retained_first_loop = _new_retained_segment("source","first")
    for i in range(RETAINED_POOL_SIZE):
        retained_repeat_segments.append(_new_retained_segment("source","repeat"))
        retained_rest_segments.append(_new_retained_segment("rest","normal"))
    retained_annotations = RetainedAnnotationOverlay.new()
    retained_annotations.owner_view = self
    retained_annotations.z_index = 5
    add_child(retained_annotations)
    _hide_retained_segments()

func _hide_retained_segments() -> void:
    # Newly installed segments compile their draw-command buffers offscreen
    # before their first appearance in a scrolling measure. Once compiled,
    # normal visibility culling no longer causes source reconstruction.
    for segment in [retained_first_once,retained_first_loop]:
        if segment != null:
            segment.visible = not segment.compiled
            if not segment.compiled:
                segment.position = Vector2(-1000000.0,0.0)
    for segment in retained_repeat_segments + retained_rest_segments:
        segment.visible = not segment.compiled
        if not segment.compiled:
            segment.position = Vector2(-1000000.0,0.0)
    for segment in retained_recovery_sources.values()+retained_recovery_rests.values():
        segment.visible = not segment.compiled
        if not segment.compiled:
            segment.position = Vector2(-1000000.0,0.0)

func _invalidate_retained_segments() -> void:
    # Structural changes invalidate cached ink. Unused pool entries recompile
    # offscreen now rather than when a later measure comes into view.
    for segment in [retained_first_once,retained_first_loop]:
        if segment != null:
            segment.compiled = false
            segment.queue_redraw()
    for segment in retained_repeat_segments + retained_rest_segments:
        segment.compiled = false
        segment.queue_redraw()
    for segment in retained_recovery_sources.values()+retained_recovery_rests.values():
        segment.compiled = false
        segment.queue_redraw()
    _hide_retained_segments()

func paint_retained_source(canvas: CanvasItem, variant: String,
        context: Dictionary = {}) -> RenderPass:
    var gap: float = staff_gap()
    var stride: float = float(practice_timeline.get("stride_beats",0.0))
    var repeated: bool = variant == "repeat"
    var pass_index: int = int(context.get("pass_index",1 if repeated else 0))
    var pass_start: float = float(context.get("pass_start",stride if repeated else 0.0))
    var width: float = maxf(size.x,
        (timeline.duration_beats+1.0)*timeline.pixels_per_beat+size.x)
    # camera_clock cancels play_from_beat so every source note uses
    # x=source_beat*pixels_per_beat, independent of playback or seeking.
    return _paint_source_pass(-play_from_beat,0.0,gap,
        pass_index,pass_start,canvas,width,variant)

func paint_retained_rest(canvas: CanvasItem, context: Dictionary = {}) -> void:
    if practice_timeline.is_empty() or timeline.measures.is_empty():
        return
    var gap: float = staff_gap()
    var silence: Dictionary = (context["measure"].duplicate(true)
        if context.has("measure") else practice_timeline["gap"].duplicate(true))
    silence["left_barline"] = timeline.measures[-1].get("right_barline",{})
    var incoming: Variant = timeline.measures[0].get("left_barline")
    if incoming is Dictionary:
        silence["right_barline"] = incoming
    var frame: RenderPass = _new_paint_frame(0.0,0.0,gap,0,0.0)
    frame.visual_scroll_beat = float(silence["start_beat"])
    var previous: Dictionary = context.get("previous",timeline.measures[-1])
    context_painter.paint_preparation_measure(canvas,frame,
        silence,previous,gap,0.0,previous.is_empty())

func paint_retained_annotations(canvas: CanvasItem) -> void:
    if not native_ready:
        return
    var gap: float = staff_gap()
    var playhead_x: float = size.x*PLAYHEAD_FRACTION
    for annotation_pass in fingering_pass_clocks:
        annotations.paint(canvas,float(annotation_pass["clock"]),playhead_x,gap,
            int(annotation_pass["pass_index"]),float(annotation_pass["pass_start"]),{
                "active_hand":active_hand,"play_from_beat":play_from_beat,
                "score_loop_enabled":score_loop_enabled,
                "preparation_history":preparation_history})
    # The genuine Verovio brace belongs ABOVE scrolling source ink at the
    # fixed left-hand edge, not inside the translated source segments.
    var staff_top: float = layout.staff_center("right")-2.0*gap
    var staff_bottom: float = layout.staff_center("left")+2.0*gap
    canvas.draw_rect(Rect2(0,staff_top-gap,29,
        staff_bottom-staff_top+gap*2),Design.STAGE)
    if glyphs.textures.has("brace"):
        canvas.draw_texture_rect(glyphs.textures["brace"],
            Rect2(6,staff_top-2,18,staff_bottom-staff_top+4),false,NOTE_INK)
    canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)

func present(state: Dictionary, transport_beat: float, visual_beat: float = NAN) -> void:
    if state.get("phase","") == "ready" and state.get("practice_preparation") == null and \
            absf(float(state.get("visual_offset_beats",0.0)))<.00001:
        if not preparation_history.is_empty():
            preparation_history.clear()
            _clear_recovery_ink()
    var old_hand: String = active_hand
    super.present(state,transport_beat,visual_beat)
    if old_hand != active_hand:
        _invalidate_retained_segments()
    if score_loop_enabled:
        _remember_preparation()

# MusicXML determines each boundary's structure. The first measure has
# no moving barline unless it explicitly opens with a repeat sign. At later
# boundaries an explicit left barline overrides the previous default regular
# right line. A closing double/repeat line belongs to the previous measure.
func beam_plan(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}, frame: RenderPass = null) -> Dictionary:
    if frame == null:
        frame = _new_paint_frame(clock,playhead_x,gap,0,0.0)
    frame.clock = clock
    frame.playhead_x = playhead_x
    var groups: Array = []
    for group in layout.beam_groups:
        if group.size() >= 2 and frame.span_visible(group[0],group[-1]):
            groups.append(group)
    var result: Dictionary = symbols.beam_layout(frame,head_offsets,groups)
    frame_visible_beam_groups = frame.visible_beam_groups
    return result

func _visible_events(left: float, right: float, frame: RenderPass = null) -> Array:
    if frame == null:
        frame = _new_paint_frame(clock_beat,size.x*PLAYHEAD_FRACTION,staff_gap(),0,0.0)
    var results: Array = EventWindow.visible(layout.ordered_events,left,right,frame)
    frame_scanned_events = results.size()
    frame.scanned_events = frame_scanned_events
    return results

func _clear_recovery_ink() -> void:
    for segment in retained_recovery_sources.values()+retained_recovery_rests.values():
        if is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    retained_recovery_sources.clear()
    retained_recovery_rests.clear()

func _rebuild_recovery_ink() -> void:
    _clear_recovery_ink()
    if retained_first_loop == null or practice_timeline.is_empty():
        return
    var stride: float = float(practice_timeline["stride_beats"])
    for owner in preparation_history:
        var item: Dictionary = preparation_history[owner]
        var measure: Dictionary = item["measure"]
        var previous: Dictionary = _practice_context_before(
            float(measure["start_beat"]),stride)
        var rest: Node2D = _new_retained_segment("rest","recovery",{
            "measure":measure,"previous":previous})
        retained_recovery_rests[owner] = rest
        var first_index: int = maxi(0,floori(float(measure["start_beat"])/stride)-1)
        var last_index: int = maxi(first_index,
            ceili(float(measure["end_beat"])/stride)+1)
        for index in range(first_index,last_index+1):
            var start: float = float(index)*stride
            if _source_overlaps_preparation(start) and \
                    not retained_recovery_sources.has(start):
                retained_recovery_sources[start] = _new_retained_segment(
                    "source","recovery",{"pass_index":index,"pass_start":start})
    _hide_retained_segments()

func _remember_preparation() -> void:
    if practice_preparation.is_empty():
        return
    var owner: float = float(practice_preparation["pass_start_beat"])
    if preparation_history.get(owner,{}) == practice_preparation:
        return
    # A new recovery may cross its source-copy boundary. All affected
    # CanvasItems are compiled once from the updated visibility contract.
    for previous in preparation_history.keys():
        if float(previous)!=owner and SourceVisibility.intervals_overlap(
                preparation_history[previous]["measure"],practice_preparation["measure"]):
            preparation_history.erase(previous)
    preparation_history[owner] = practice_preparation.duplicate(true)
    _rebuild_recovery_ink()

func _practice_context_before(at: float, stride: float) -> Dictionary:
    return SourceVisibility.practice_context_before(
        at, stride, timeline.measures, practice_timeline["gap"])

func _paint_source_pass(camera_clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0,
        canvas: CanvasItem = null, retained_width: float = 0.0,
        retained_variant: String = "") -> RenderPass:
    var target: CanvasItem = canvas if canvas != null else self
    var frame: RenderPass = _new_paint_frame(camera_clock,playhead_x,gap,pass_index,pass_start)
    if not retained_variant.is_empty():
        # A recovery variant captures the changed source visibility once;
        # ordinary copies retain the same command buffer across attempts.
        frame.score_loop_enabled = retained_variant != "once"
        if retained_variant == "recovery":
            frame.preparation_history = preparation_history.duplicate(true)
            frame.current_preparation = frame.preparation_history.get(pass_start,{})
        else:
            frame.preparation_history = {}
            frame.current_preparation = {}
        layout.set_viewport(Vector2(retained_width,size.y))
    var current_preparation: Dictionary = frame.current_preparation
    var font: Font = ThemeDB.fallback_font
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+(retained_width if retained_width>0.0 else size.x)/timeline.pixels_per_beat
    var previous_measure: Dictionary = {}
    if pass_index>0:
        previous_measure = _practice_context_before(pass_start,float(practice_timeline["stride_beats"]))
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
            if not barline.is_empty() and float(barline["x"])>=-gap*2.0 and float(barline["x"])<=(retained_width if retained_width>0.0 else size.x)+gap*2.0:
                context_painter.paint_barline(target,frame,barline,gap)
        var meter_right_limit := INF
        if target_boundary or (first and pass_index>0):
            var incoming: Variant = current_preparation["measure"].get("right_barline") if target_boundary else measure.get("left_barline")
            var mark: Dictionary = incoming if incoming is Dictionary else {"style":"regular","repeat":""}
            meter_right_limit = context_painter.barline_left_limit(
                BarlineLayout.project(at,timeline,camera_clock,playhead_x,play_from_beat,gap),mark,gap)
        var crowded_meter: bool = context_painter.paint_context(target,frame,measure,previous_measure,x,gap,opening,meter_right_limit)
        if not first and not crowded_meter and x>=0.0 and x<=(retained_width if retained_width>0.0 else size.x):
            target.draw_string(font,Vector2(x+gap*.4,layout.staff_center("right")-gap*4.3),
                str(int(measure.get("number",0))),HORIZONTAL_ALIGNMENT_LEFT,-1,11,DIM_INK)
        previous_measure = measure
    # The actual ending of the last measure has its own terminal barline.
    # It must not disappear simply because no following measure exists.
    var terminal: Dictionary = layout.terminal_barline_geometry(
        camera_clock,playhead_x,gap,play_from_beat)
    if not frame.score_loop_enabled and not terminal.is_empty() and float(terminal["x"]) >= -gap*2.0 and \
            float(terminal["x"]) <= (retained_width if retained_width>0.0 else size.x)+gap*2.0:
        context_painter.paint_barline(target,frame,terminal,gap)
    context_painter.paint_volta_endings(target,frame,left,right,camera_clock,playhead_x,gap)
    # Source geometry must already exist before this frame. Rebuilding
    # glyph spacing during a scroll is forbidden: it stalls the musical UI.
    if layout.cached_offsets_gap < 0.0 or absf(layout.cached_offsets_gap-gap) > .001:
        push_error("Static engraving cache is stale; reprepare before playback")
        layout.set_viewport(size)
        return frame
    var head_offsets: Dictionary = layout.cached_head_offsets
    var beam_data: Dictionary = beam_plan(gap, camera_clock,
        playhead_x, head_offsets,frame)
    var beam_stems: Dictionary = beam_data.get("stems", {})
    var compound_ids: Dictionary = {}
    for event in _visible_events(left, right,frame):
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
    if not retained_variant.is_empty():
        layout.set_viewport(size)
        return frame
    drawn_note_instances.append_array(frame.drawn_note_instances)
    # Across repeated source copies, feedback follows the nearest painted
    # instance of each source identity. Per-copy heads stay in RenderPass.
    for id in frame.drawn_noteheads:
        var point: Vector2 = frame.drawn_noteheads[id]
        if not drawn_noteheads.has(id) or absf(point.x-size.x*PLAYHEAD_FRACTION)<absf(drawn_noteheads[id].x-size.x*PLAYHEAD_FRACTION):
            drawn_noteheads[id] = point
    visible_symbols += frame.visible_symbols
    frame_scanned_events = frame.scanned_events
    frame_visible_beam_groups = frame.visible_beam_groups
    fingering_pass_clocks.append({"clock":camera_clock,"pass_index":pass_index,"pass_start":pass_start})
    return frame

func _project_retained_source(segment: Node2D, shift_x: float,
        camera_clock: float, pass_index: int, pass_start: float) -> void:
    segment.position = Vector2(shift_x,0.0)
    segment.visible = true
    if not segment.compiled:
        return
    visible_symbols += segment.symbols_drawn
    frame_visible_beam_groups += segment.beam_groups_drawn
    fingering_pass_clocks.append({"clock":camera_clock,
        "pass_index":pass_index,"pass_start":pass_start})
    var playhead_x: float = size.x*PLAYHEAD_FRACTION
    for source_note in segment.note_instances:
        var screen: Vector2 = source_note["position"]+Vector2(shift_x,0.0)
        if screen.x < -60.0 or screen.x > size.x+60.0:
            continue
        var current: Dictionary = source_note.duplicate(false)
        var ident: String = str(source_note["event_id"])
        current["position"] = screen
        current["pass_index"] = pass_index
        current["instance_id"] = "%d:%s" % [pass_index,ident]
        drawn_note_instances.append(current)
        if not drawn_noteheads.has(ident) or \
                absf(screen.x-playhead_x)<absf(drawn_noteheads[ident].x-playhead_x):
            drawn_noteheads[ident] = screen

func _source_overlaps_preparation(pass_start: float) -> bool:
    var interval := {"start_beat":pass_start,
        "end_beat":pass_start+timeline.duration_beats}
    for item in preparation_history.values():
        if absf(float(item.get("pass_start_beat",-INF))-pass_start)<.00001 or \
                SourceVisibility.intervals_overlap(interval,item["measure"]):
            return true
    return false

func _place_retained_score(playhead_x: float, camera_clock: float, gap: float) -> void:
    if retained_first_once == null:
        return
    _hide_retained_segments()
    var density: float = timeline.pixels_per_beat
    if not score_loop_enabled:
        var shift: float = playhead_x-(camera_clock+play_from_beat)*density
        _project_retained_source(retained_first_once,shift,camera_clock,0,0.0)
        return
    _remember_preparation()
    var stride: float = float(practice_timeline["stride_beats"])
    var virtual_left: float = visual_scroll_beat-playhead_x/density
    var virtual_right: float = virtual_left+size.x/density
    var first_pass: int = maxi(0,floori(virtual_left/stride)-1)
    var last_pass: int = maxi(first_pass,ceili(virtual_right/stride)+1)
    var source_slot := 0
    var rest_slot := 0
    for pass_index in range(first_pass,last_pass+1):
        var pass_start: float = pass_index*stride
        if pass_start>virtual_right+.7 or pass_start+stride<virtual_left-.7:
            continue
        var source_clock: float = visual_scroll_beat-pass_start-play_from_beat
        var source_shift: float = playhead_x+(pass_start-visual_scroll_beat)*density
        var segment: Node2D
        if _source_overlaps_preparation(pass_start):
            segment = retained_recovery_sources.get(pass_start)
            if segment == null:
                push_error("Recovery source cache was not prepared")
                continue
        elif pass_index == 0:
            segment = retained_first_loop
        elif source_slot < retained_repeat_segments.size():
            segment = retained_repeat_segments[source_slot]
            source_slot += 1
        else:
            push_error("Retained source segment pool exhausted")
            continue
        _project_retained_source(segment,source_shift,source_clock,
            pass_index,pass_start)
        var silence: Dictionary = practice_timeline["gap"].duplicate(true)
        silence["start_beat"] = pass_start+float(silence["start_beat"])
        silence["end_beat"] = pass_start+float(silence["end_beat"])
        var replaced := false
        for item in preparation_history.values():
            if SourceVisibility.intervals_overlap(silence,item["measure"]):
                replaced = true
                break
        if not replaced and rest_slot < retained_rest_segments.size():
            var rest: Node2D = retained_rest_segments[rest_slot]
            rest_slot += 1
            rest.position = Vector2(playhead_x+(
                pass_start+timeline.duration_beats-visual_scroll_beat)*density,0.0)
            rest.visible = true
    # Exceptional recovery measures are retained too; their visibility
    # variant is built when the backend publishes the preparation.
    for owner in preparation_history:
        var item: Dictionary = preparation_history[owner]
        var replaced_rest: Dictionary = item["measure"]
        if float(replaced_rest["end_beat"])<virtual_left-.7 or \
                float(replaced_rest["start_beat"])>virtual_right+.7:
            continue
        var recovery_rest: Node2D = retained_recovery_rests.get(owner)
        if recovery_rest == null:
            continue
        recovery_rest.position = Vector2(playhead_x+(
            float(replaced_rest["start_beat"])-visual_scroll_beat)*density,0.0)
        recovery_rest.visible = true

func _draw() -> void:
    layout.set_viewport(size)
    drawn_noteheads.clear()
    drawn_note_instances.clear()
    visible_symbols = 0
    annotations.begin_frame()
    fingering_pass_clocks.clear()
    if size.x < 100.0 or size.y < 100.0:
        return
    draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
    var font: Font = ThemeDB.fallback_font
    if not native_ready or not timeline.has_score():
        draw_string(font,Vector2(20.0,size.y*.5),
            notice if not notice.is_empty() else "Loading native score",
            HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
        return
    var gap: float = staff_gap()
    var playhead_x: float = size.x * PLAYHEAD_FRACTION
    var camera_clock: float = clock_beat if running or paused else 0.0
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+size.x/timeline.pixels_per_beat
    # A quiet pool of light marks the strike without hiding any engraved ink.
    var top: float = layout.staff_center("right")-gap*3.8
    var bottom: float = layout.staff_center("left")+gap*3.7
    var breath: float = .5+.5*cos(clock_beat*TAU) if running and not paused else 0.0
    if transport_overlay_enabled:
        for radius in [20.0, 10.0, 4.0]:
            draw_rect(Rect2(playhead_x-radius, top, radius*2.0, bottom-top),
                Color(PREVIEW_LIGHT, .012+breath*.004))
    # Always draw ten native rules; no copied or stitched raster systems.
    for staff in ["right","left"]:
        var center: float = layout.staff_center(staff)
        var ink: Color = RenderPass.new({"active_hand":active_hand}).ink(staff)
        for line_index in range(5):
            var y: float = center+(float(line_index)-2.0)*gap
            draw_line(Vector2(0,y),Vector2(size.x,y),
                Color(ink,.34),1.3,true)
    # Keep the fixed playhead visible but BEHIND source ink. At exact
    # onset a foreground cursor previously covered small eighth-rest dots,
    # flagged stems and noteheads, preventing independent contour recovery.
    # Engraving is always painted later; the transport clock is unchanged.
    if transport_overlay_enabled:
        draw_line(Vector2(playhead_x,layout.staff_center("right")-gap*3.8),
            Vector2(playhead_x,layout.staff_center("left")+gap*3.7),
            PREVIEW_LIGHT,2.0,true)
        # Beat breathing is an accent on the fixed playhead, not a moving
        # alternate clock. Music, retry preparation and calibration each
        # retain the application's single beat axis.
        var rhythmic: bool = (running and not paused) or (
            score_loop_enabled and not practice_preparation.is_empty() and not paused)
        if rhythmic:
            var beat_axis := visual_scroll_beat if score_loop_enabled else clock_beat
            var fraction := fposmod(beat_axis, 1.0)
            var impulse := pow(1.0-fraction, 2.4)
            var center := Vector2(playhead_x, top + gap*.22)
            draw_circle(center, 5.0 + 10.0*impulse,
                Color(PREVIEW_LIGHT, .15+.12*impulse))
            draw_arc(center, 7.0 + 10.0*impulse, 0.0, TAU, 40,
                Color(PREVIEW_LIGHT, .40+.50*impulse), 2.4, true)
    # The count-in runs on the same clock, but its leading boundary is
    # intentionally NOT a printed barline: it sits before the clef/header
    # and used to look like an orphaned vertical rule in the score.
    # One semantic practice timeline owns both source-copy placement and
    # preparation silence. No independently inferred final-bar duration.
    if score_loop_enabled and not practice_contract_error.is_empty():
        draw_string(font,Vector2(20,size.y*.5),practice_contract_error,
            HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
        _hide_retained_segments()
        return
    _place_retained_score(playhead_x,camera_clock,gap)
    if retained_annotations != null:
        retained_annotations.queue_redraw()
    # Never put engineering telemetry on top of the actual lesson.
    if OS.get_environment("PIANO_TEACHER_NATIVE_DIAGNOSTICS") == "1":
        var phase: String = "COUNT-IN" if camera_clock < 0.0 and running else \
            "PAUSED" if paused else "PLAYING" if running else "READY"
        draw_string(font,Vector2(14.0,22.0),
            "NATIVE · %s · %.0f px/beat · %.0f BPM · %d events" % [
                phase,timeline.pixels_per_beat,bpm,frame_scanned_events],
            HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)

func _new_paint_frame(clock: float, playhead_x: float, gap: float,
        pass_index: int, pass_start: float) -> RenderPass:
    layout.set_viewport(size)
    return RenderPass.new({"clock":clock,"playhead_x":playhead_x,"gap":gap,
        "play_from_beat":play_from_beat,"active_hand":active_hand,
        "score_loop_enabled":score_loop_enabled,"pass_index":pass_index,
        "pass_start":pass_start,"preparation_history":preparation_history,
        "visual_scroll_beat":visual_scroll_beat})
