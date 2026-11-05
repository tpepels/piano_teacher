extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation is rejected; production reports a preparation error.
const Geometry := preload("res://notation/native/geometry.gd")
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

signal fingering_change_requested(source_id: String, finger: Variant)
signal retained_ink_compiled

# Annotation cells live on the same immutable score axis as the note ink.
# Cache once per score/vertical size; scrolling only translates their X.
var transport_overlay_enabled := true
var runway_overlay := false
var runway_origin_beat := 0.0
var runway_cutoff_beat := INF
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
const EventWindow := preload("res://notation/native/event_window.gd")
var annotations = FingeringAnnotations.new(layout,connector_geometry)
const RenderPass := preload("res://notation/native/render_pass.gd")
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")
const ContextPainter := preload("res://notation/native/context_painter.gd")
const RetainedSegment := preload("res://notation/native/retained_segment.gd")
const RetainedNoteProjection := preload("res://notation/native/retained_note_projection.gd")
const StreamAdmission := preload("res://score_stream_admission.gd")
const SourcePassPainter := preload("res://notation/native/source_pass_painter.gd")
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
var external_backdrop := false
var compact_inactive_staff := false
# One infinite front-of-house camera. Grading never reads this axis.
var stream_enabled := false
var stream_world_beat := 0.0
var stream_passes: Array = []
var _stream_last_take := ""
var _stream_was_paused := false
var _stream_paused_source := 0.0
var _stream_live_serial := -1
var _stream_armed_serial := -1
var _stream_serial := 0
# Pure presentation clock for empty idle/paused staves. Never fed into
# MIDI grading, transport projection or recorded source events.

func _focused_staff_for_score() -> String:
    if not compact_inactive_staff or active_hand not in ["right","left"]:
        return ""
    # Preserve the grand staff whenever the performing hand has authentic
    # cross-staff notes. Only an entirely unused opposite staff is collapsed.
    for event in timeline.model.get("notation_events",[]):
        if not event is Dictionary or str(event.get("kind","")) != "note":
            continue
        var owner := str(event.get("hand",event.get("staff","")))
        if owner == active_hand and str(event.get("staff","")) != active_hand:
            return ""
    return active_hand

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
var retained_first_once
var retained_repeat_segments: Array = []
var retained_all_segments: Array = []
var retained_annotations: Node2D
var retained_ink_published := false
# Repeat copies are sized to the visible musical horizon, never a fixed five.

func _init() -> void:
    resized.connect(func():
        layout.set_viewport(size)
        if native_ready and size.y >= 100.0:
            _prepare_static_geometry()
            _resize_retained_pool()
            _invalidate_retained_segments()
    )
    annotations.fingering_change_requested.connect(func(source_id, finger):
        fingering_change_requested.emit(source_id,finger))
    mouse_filter = Control.MOUSE_FILTER_PASS
    tooltip_text = "Right-click a note or tap a finger number to change its fingering"

func clear_score() -> void:
    runway_origin_beat = 0.0
    runway_cutoff_beat = INF
    runway_overlay = false
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
        # Horizontal density changes how many source copies fit onscreen.
        _prepare_static_geometry()
        _resize_retained_pool()
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
    layout.set_focused_staff(_focused_staff_for_score())
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
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
        var first_note_beat: float = INF
        for event in layout.ordered_events:
            if str(event.get("kind", "")) == "note" and not bool(event.get("chord", false)):
                first_note_beat = minf(first_note_beat,float(event.get("beat",0.0)))
        print("NATIVE_SCORE_SPACING:", JSON.stringify({
            "revision":timeline.revision,
            "duration_beats":timeline.duration_beats,
            "first_note_beat":first_note_beat if is_finite(first_note_beat) else null,
            "pixels_per_beat":ink_density,
            "staff_gap":staff_gap_limit,
            "lookahead_beats":size.x*(1.0-PLAYHEAD_FRACTION)/ink_density,
            "density_witness":selected_density_witness
        }))
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

func _stream_release_all() -> void:
    for item in stream_passes:
        var segment = item.get("segment")
        var clip = item.get("clip")
        if segment != null and is_instance_valid(segment) and clip != null and is_instance_valid(clip):
            segment.reparent(self,false)
            clip.queue_free()
    stream_passes.clear()
    _stream_last_take = ""
    _stream_was_paused = false
    _stream_paused_source = 0.0
    _stream_live_serial = -1
    _stream_armed_serial = -1


func _clear_retained_segments() -> void:
    _stream_release_all()
    for segment in [retained_first_once,retained_annotations]:
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    for segment in retained_repeat_segments:
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    retained_first_once = null
    retained_annotations = null
    retained_ink_published = false
    retained_repeat_segments.clear()
    retained_all_segments.clear()

func _new_retained_segment(kind: String, variant: String,
        context: Dictionary = {}):
    var segment = RetainedSegment.new()
    add_child(segment)
    retained_all_segments.append(segment)
    segment.call("configure",self,kind,variant,context)
    return segment

func _install_retained_segments() -> void:
    _clear_retained_segments()
    clip_contents = true
    retained_ink_published = false
    retained_first_once = _new_retained_segment("source","once")
    _resize_retained_pool()
    retained_annotations = RetainedAnnotationOverlay.new()
    retained_annotations.set("owner_view",self)
    retained_annotations.z_index = 5
    add_child(retained_annotations)
    _hide_retained_segments()

func _resize_retained_pool() -> void:
    if retained_first_once == null:
        return
    # Single authentic source model and reusable offscreen copies.
    while retained_repeat_segments.size() < 4:
        retained_repeat_segments.append(_new_retained_segment("source","once"))


func retained_ready() -> bool:
    if not native_ready or size.x < 100.0 or size.y < 100.0 or \
            retained_first_once == null or retained_annotations == null:
        return false
    for segment in [retained_first_once]:
        if not segment.compiled:
            return false
    for segment in retained_repeat_segments:
        if not segment.compiled:
            return false
    return true

func retained_segment_compiled() -> void:
    if retained_ready() and not retained_ink_published:
        retained_ink_published = true
        # Do not re-enter score publication or the UI hierarchy from
        # inside a CanvasItem draw notification.
        call_deferred("emit_signal","retained_ink_compiled")

func _hide_retained_segments() -> void:
    # Newly installed segments compile before first entering the viewport.
    for segment in retained_all_segments:
        if segment.visible != not segment.compiled:
            segment.visible = not segment.compiled
        if not segment.compiled:
            segment.position = Vector2(-1000000.0,0.0)

func _invalidate_retained_segments() -> void:
    retained_ink_published = false
    # Structural changes invalidate cached ink. Unused pool entries recompile
    # offscreen now rather than when a later measure comes into view.
    for segment in [retained_first_once]:
        if segment != null:
            segment.compiled = false
            segment.queue_redraw()
    for segment in retained_repeat_segments:
        segment.compiled = false
        segment.queue_redraw()
    _hide_retained_segments()

func paint_retained_source(canvas: CanvasItem, variant: String,
        context: Dictionary = {}) -> RenderPass:
    return SourcePassPainter.paint(self,canvas,variant,context)

func paint_retained_rest(canvas: CanvasItem, context: Dictionary = {}) -> void:
    if practice_timeline.is_empty() or timeline.measures.is_empty():
        return
    var gap: float = staff_gap()
    var silence: Dictionary = (context["measure"].duplicate(true)
        if context.has("measure") else practice_timeline["gap"].duplicate(true))
    if context.is_empty():
        # Only ordinary between-take silence inherits the previous source
        # ending. Recovery rest descriptors carry their own authored context.
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
        var context := {
            "active_hand":active_hand,"play_from_beat":play_from_beat,
            "score_loop_enabled":score_loop_enabled,
            "preparation_history":preparation_history}
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
    canvas.draw_rect(Rect2(0,staff_top-gap,29,
        staff_bottom-staff_top+gap*2),Design.STAGE)
    if glyphs.textures.has("brace"):
        canvas.draw_texture_rect(glyphs.textures["brace"],
            Rect2(6,staff_top-2,18,staff_bottom-staff_top+4),false,NOTE_INK)
    canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)

func _stream_add_take(source_beat: float, start_world: float,
        from_beat: float, through_beat: float, take_key: String) -> void:
    var used: Dictionary = {}
    for item in stream_passes:
        used[item["segment"]] = true
    var choice = null
    for segment in [retained_first_once] + retained_repeat_segments:
        if segment != null and is_instance_valid(segment) and not used.has(segment):
            choice = segment
            break
    if choice == null:
        # Very rapid manual retries can overlap more than the precompiled
        # visible copies. Compile one more source ONCE, then reuse its ink.
        choice = _new_retained_segment("source","once")
        retained_repeat_segments.append(choice)
    var clip := Control.new()
    clip.name = "StreamPassWindow"
    clip.clip_contents = true
    clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
    clip.focus_mode = Control.FOCUS_NONE
    add_child(clip)
    choice.reparent(clip,false)
    _stream_serial += 1
    _stream_live_serial = _stream_serial
    stream_passes.append({
        "segment":choice,
        "clip":clip,
        "world_origin":start_world-source_beat,
        "source_floor":maxf(0.0,from_beat),
        "source_ceiling":through_beat,
        "take_key":take_key,
        "pending":take_key == "prepared",
        "serial":_stream_serial,
    })


func _stream_right_beats() -> float:
    return size.x*(1.0-PLAYHEAD_FRACTION)/maxf(1.0,timeline.pixels_per_beat)


func _stream_header_beats(opening: float) -> float:
    return (15.0 if opening <= .0001 else 1.6)*staff_gap()/ \
        maxf(1.0,timeline.pixels_per_beat)


func _stream_complete_measure(requested: float) -> float:
    var extent: float = minf(timeline.duration_beats,requested)
    for measure in timeline.measures:
        var ending: float = float(measure.get("end_beat",0.0))
        if ending >= extent-.0001:
            return minf(timeline.duration_beats,ending)
    return timeline.duration_beats


func _stream_reserve_ready(world: float, opening: float) -> int:
    if not native_ready or not retained_ready() or \
            opening >= timeline.duration_beats:
        return -1
    var index: int = StreamAdmission.pending_index(
        stream_passes,opening,world)
    if index >= 0:
        return int(stream_passes[index]["serial"])
    var onset: float = StreamAdmission.future_start(
        stream_passes,world,_stream_right_beats(),_stream_header_beats(opening))
    _stream_add_take(opening,onset,opening,_stream_complete_measure(
        opening+_stream_right_beats()+1.0),"prepared")
    _stream_live_serial = -1
    return _stream_serial


func arm_stream_take(world: float, opening: float) -> Dictionary:
    # Bound before the in-process command: only previously placed note ink
    # may become the next graded take, and its world_origin never changes.
    if not stream_enabled or not native_ready or not retained_ready():
        return {}
    stream_world_beat = maxf(stream_world_beat,world)
    var serial: int = _stream_reserve_ready(stream_world_beat,opening)
    for item in stream_passes:
        if serial >= 0 and int(item["serial"]) == serial:
            item["pending"] = false
            item["armed"] = true
            _stream_armed_serial = serial
            return {"start_world":float(item["world_origin"])+opening,
                "opening":opening}
    return {}


func _stream_extend_offscreen(item: Dictionary) -> void:
    # The cached score never repaints. The clip widens only beyond the
    # viewport's right edge, not at the moving timing line.
    var horizon: float = stream_world_beat - \
        float(item["world_origin"])+_stream_right_beats()+1.0
    item["source_ceiling"] = maxf(float(item["source_ceiling"]),
        _stream_complete_measure(horizon))


func _stream_prune_expired() -> void:
    # Scene-tree mutations belong to the frame coordinator, never _draw().
    # The GPU command-list pass only translates retained CanvasItems.
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var playhead_x: float = size.x*PLAYHEAD_FRACTION
    for index in range(stream_passes.size()-1,-1,-1):
        var item: Dictionary = stream_passes[index]
        var segment = item["segment"]
        var clip = item["clip"]
        if segment == null or not is_instance_valid(segment) or \
                clip == null or not is_instance_valid(clip):
            stream_passes.remove_at(index)
            continue
        var source_left: float = playhead_x + (
            float(item["world_origin"])-stream_world_beat)*density
        if source_left + float(item.get("source_ceiling",
                timeline.duration_beats))*density < -60.0:
            segment.reparent(self,false)
            clip.queue_free()
            stream_passes.remove_at(index)


func present_flow(world_beat: float, state: Dictionary,
        graded_beat: float, allow_admission: bool = true) -> void:
    if not stream_enabled:
        return
    stream_world_beat = maxf(stream_world_beat,world_beat)
    _stream_prune_expired()
    if not native_ready or not retained_ready():
        queue_redraw()
        return
    var phase: String = str(state.get("phase",""))
    var mode: String = str(state.get("mode","practice"))
    var opening: float = maxf(0.0,float(state.get("play_from_beat",0.0)))
    var key: String = "%s|%d|%d|%s" % [
        str(state.get("piece_fingerprint","")),
        int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),mode]
    var paused_now: bool = bool(state.get("paused",false))
    var running_now: bool = bool(state.get("running",false)) and not paused_now
    if allow_admission and phase == "ready" and not running_now and \
            not paused_now and mode in ["practice","perform"]:
        # Prepare outside the visible viewport, long before the Play button.
        _stream_reserve_ready(stream_world_beat,opening)
    if paused_now:
        if not _stream_was_paused:
            _stream_paused_source = maxf(opening,opening+graded_beat)
        _stream_was_paused = true
        _stream_live_serial = -1
    elif allow_admission and running_now and phase in [
            "count_in","playing","guided_wait"]:
        if key != _stream_last_take or _stream_was_paused:
            _stream_live_serial = -1
            if _stream_armed_serial >= 0:
                for item in stream_passes:
                    if int(item["serial"]) == _stream_armed_serial:
                        item["take_key"] = key
                        item["armed"] = false
                        item["pending"] = false
                        _stream_live_serial = _stream_armed_serial
                        _stream_last_take = key
                        break
                _stream_armed_serial = -1
            elif key == _stream_last_take and not _stream_was_paused:
                for item in stream_passes:
                    if str(item.get("take_key","")) == key:
                        _stream_live_serial = int(item["serial"])
                        break
        if _stream_live_serial >= 0:
            for item in stream_passes:
                if int(item["serial"]) == _stream_live_serial:
                    _stream_extend_offscreen(item)
                    break
        # An unreserved start CANNOT create note ink in the current frame.
        # This fails closed rather than silently taking the old camera path.
        _stream_was_paused = false
    elif not paused_now:
        _stream_live_serial = -1
    queue_redraw()


func _project_stream(playhead_x: float) -> void:
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var used: Dictionary = {}
    for index in range(stream_passes.size()-1,-1,-1):
        var item: Dictionary = stream_passes[index]
        var segment = item["segment"]
        var clip: Control = item["clip"]
        if not is_instance_valid(segment) or not is_instance_valid(clip):
            stream_passes.remove_at(index)
            continue
        var position: float = playhead_x + (
            float(item["world_origin"])-stream_world_beat)*density
        var floor_x: float = float(item["source_floor"])*density
        var ceiling_x: float = float(item["source_ceiling"])*density
        var bounds: Vector2 = StreamAdmission.engraved_clip_bounds(
            float(item["source_floor"]),float(item["source_ceiling"]),
            density,staff_gap(),timeline.duration_beats)
        # Physical crop extends beyond semantic attacks. The extra prefix
        # contains the real initial clef/key/meter; the extra suffix contains
        # full noteheads and barline ink. Grading and hit-tests stay bounded
        # by source_floor/source_ceiling, never by the padding.
        clip.position = Vector2(position+bounds.x,0.0)
        clip.size = Vector2(maxf(1.0,bounds.y-bounds.x),size.y)
        segment.position = Vector2(-bounds.x,0.0)
        if segment.compiled:
            used[segment] = true
            var count: int = RetainedNoteProjection.append_visible(
                segment.note_instances,position,size.x,playhead_x,
                int(item["serial"]),drawn_note_instances,drawn_noteheads,
                floor_x,ceiling_x)
            visible_symbols += count
            frame_scanned_events += count
            fingering_pass_clocks.append({
                "clock":stream_world_beat-float(item["world_origin"])-play_from_beat,
                "pass_index":0,"pass_start":0.0,
                "stream_floor":float(item["source_floor"]),
                "stream_ceiling":float(item["source_ceiling"])})
    # The source geometry is in immutable local source coordinates. Only
    # the clip windows and Node2D transforms change on every render frame.
    for item in stream_passes:
        var segment = item["segment"]
        segment.visible = used.has(segment)
    for segment in retained_all_segments:
        if not used.has(segment) and segment.visible:
            segment.visible = not segment.compiled


func present(state: Dictionary, transport_beat: float, visual_beat: float = NAN) -> void:
    var old_hand: String = active_hand
    var old_transport: int = transport_id
    var old_bpm: float = bpm
    super.present(state,transport_beat,visual_beat)
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1" and \
            (old_transport != transport_id or absf(old_bpm-bpm) > .001):
        print("NATIVE_SCORE_MOTION:", JSON.stringify({
            "revision":timeline.revision,
            "transport_id":transport_id,
            "bpm":bpm,
            "effective_bpm":float(state.get("effective_bpm",bpm)),
            "pixels_per_beat":timeline.pixels_per_beat,
            "pixels_per_second":timeline.pixels_per_second(
                float(state.get("effective_bpm",bpm))),
            "running":running,
            "paused":paused,
            "phase":str(state.get("phase",""))
        }))
    var focus_changed := layout.set_focused_staff(_focused_staff_for_score())
    if old_hand != active_hand or focus_changed:
        _invalidate_retained_segments()
        queue_redraw()

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


func _draw() -> void:
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
        return
    # The Practice stage supplies its vignette; stand-alone notation tests
    # and other native score consumers still receive the original dark ink.
    if not runway_overlay and not external_backdrop:
        draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
    var font: Font = ThemeDB.fallback_font
    if not native_ready or not timeline.has_score():
        draw_string(font,Vector2(20.0,size.y*.5),
            notice if not notice.is_empty() else "Loading native score",
            HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
        return
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
            draw_line(Vector2(0,y),Vector2(size.x,y),
                Color(ink,.48 if selected else .28),1.15,true)
    # Empty idle and paused canvas: source ink is hidden while barlines
    # continue to move. Staff and playhead remain fixed and legible.
    if not runway_overlay:
        var measure_beats: float = 4.0
        if not timeline.measures.is_empty():
            var opening: Dictionary = timeline.measures[0]
            measure_beats = maxf(.25, float(opening.get("end_beat",4.0)) -
                float(opening.get("start_beat",0.0)))
        var bar_width: float = maxf(64.0,measure_beats*timeline.pixels_per_beat)
        var offset: float = fposmod(stream_world_beat*
            timeline.pixels_per_beat,bar_width)
        var barline_top_y: float = layout.barline_top(gap)
        var barline_bottom_y: float = layout.barline_bottom(gap)
        for index in range(-1,ceili(size.x/bar_width)+3):
            var x: float = playhead_x-offset+float(index)*bar_width
            if x >= 0.0 and x <= size.x:
                var inside_source := false
                var density: float = maxf(1.0,timeline.pixels_per_beat)
                for item in stream_passes:
                    var source_left: float = playhead_x + (
                        float(item["world_origin"])-stream_world_beat)*density
                    var bounds: Vector2 = StreamAdmission.engraved_clip_bounds(
                        float(item["source_floor"]),
                        float(item["source_ceiling"]),
                        density,gap,timeline.duration_beats)
                    if x >= source_left+bounds.x and x <= source_left+bounds.y:
                        inside_source = true
                        break
                if not inside_source:
                    draw_line(Vector2(x,barline_top_y),
                        Vector2(x,barline_bottom_y),
                        Color(NOTE_INK,.20),1.0,true)
    # Keep the fixed playhead visible but BEHIND source ink. At exact
    # onset a foreground cursor previously covered small eighth-rest dots,
    # flagged stems and noteheads, preventing independent contour recovery.
    # Engraving is always painted later; the transport clock is unchanged.
    if transport_overlay_enabled and not runway_overlay:
        draw_line(Vector2(playhead_x,top),Vector2(playhead_x,bottom),
            Design.HIGHLIGHT,2.4,true)
        draw_line(Vector2(playhead_x,top),Vector2(playhead_x,bottom),
            Color(Design.STONE,.62),.9,true)
        draw_circle(Vector2(playhead_x,top),9.0,Color(Design.MINT,.16))
        draw_circle(Vector2(playhead_x,top),3.7,Design.STONE)
        # Beat breathing is an accent on the fixed playhead, not a moving
        # alternate clock. Music, retry preparation and calibration each
        # retain the application's single beat axis.
        var fraction := fposmod(stream_world_beat,1.0)
        var impulse := pow(1.0-fraction,2.4)
        var center := Vector2(playhead_x,top+gap*.22)
        draw_circle(center,5.0+10.0*impulse,
            Color(PREVIEW_LIGHT,.15+.12*impulse))
        draw_arc(center,7.0+10.0*impulse,0.0,TAU,40,
            Color(PREVIEW_LIGHT,.40+.50*impulse),2.4,true)
    # The count-in runs on the same clock, but its leading boundary is
    # intentionally NOT a printed barline: it sits before the clef/header
    # and used to look like an orphaned vertical rule in the score.
    # One semantic practice timeline owns both source-copy placement and
    # preparation silence. No independently inferred final-bar duration.
    # All phases use the exact same absolute world-axis projection.
    # Play/Pause/Retry cannot switch cameras or reconstruct source ink.
    _project_stream(playhead_x)
    if retained_annotations != null:
        retained_annotations.queue_redraw()
    if OS.get_environment("PIANO_TEACHER_NATIVE_DIAGNOSTICS") == "1":
        var phase: String = "PAUSED" if paused else \
            "COUNT-IN" if clock_beat < 0.0 and running else \
            "PLAYING" if running else "READY"
        draw_string(font,Vector2(14.0,22.0),
            "NATIVE · %s · %.0f px/beat · %.0f BPM · %d events" % [
                phase,timeline.pixels_per_beat,bpm,frame_scanned_events],
            HORIZONTAL_ALIGNMENT_LEFT,-1,12,DIM_INK)

func _new_paint_frame(clock: float, playhead_x: float, gap: float,
        pass_index: int, pass_start: float) -> RenderPass:
    layout.set_viewport(size)
    return RenderPass.new({"clock":clock,"playhead_x":playhead_x,"gap":gap,
        "play_from_beat":play_from_beat,"active_hand":active_hand,
        "focused_staff":layout.focused_staff,
        "score_loop_enabled":score_loop_enabled,"pass_index":pass_index,
        "pass_start":pass_start,"preparation_history":preparation_history,
        "visual_scroll_beat":visual_scroll_beat})
