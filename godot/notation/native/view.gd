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
const MeasureLight := preload("res://notation/native/measure_light.gd")
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
var _ready_preview_key: Array = []
var _ready_preview_beat := 0.0

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
        _ready_preview_key.clear()
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
const RetainedNoteProjection := preload("res://notation/native/retained_note_projection.gd")
const IdlePreview := preload("res://notation/native/idle_preview.gd")
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
var _stream_resume_floor := 0.0
var _stream_serial := 0
# Pure presentation clock for empty idle/paused staves. Never fed into
# MIDI grading, transport projection or recorded source events.
var ambient_blank := false
var ambient_scroll_beat := 0.0
var ambient_last_ms := 0

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
var retained_first_loop
var retained_repeat_segments: Array = []
var retained_rest_segments: Array = []
var retained_all_segments: Array = []
var retained_recovery_sources: Dictionary = {}
var retained_recovery_rests: Dictionary = {}
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
    ambient_blank = false
    ambient_last_ms = 0
    _ready_preview_key.clear()
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
    _ready_preview_key.clear()
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
    _stream_resume_floor = 0.0


func _clear_retained_segments() -> void:
    _stream_release_all()
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
    retained_ink_published = false
    retained_repeat_segments.clear()
    retained_rest_segments.clear()
    for segment in retained_recovery_sources.values()+retained_recovery_rests.values():
        if segment != null and is_instance_valid(segment):
            remove_child(segment)
            segment.queue_free()
    retained_recovery_sources.clear()
    retained_recovery_rests.clear()
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
    retained_first_loop = _new_retained_segment("source","first")
    _resize_retained_pool()
    retained_annotations = RetainedAnnotationOverlay.new()
    retained_annotations.set("owner_view",self)
    retained_annotations.z_index = 5
    add_child(retained_annotations)
    _hide_retained_segments()

func _required_repeat_copies() -> int:
    # At most ceil(viewport/stride) source copies intersect the screen
    # plus two possible partially visible neighbours and a boundary margin.
    # A fixed pool wasted 5 full-score command buffers on long excerpts
    # while silently dropping copies for very short passages.
    var stride: float = float(practice_timeline.get("stride_beats",0.0))
    if stride <= 0.0 or timeline.pixels_per_beat <= 0.0:
        return 1
    return maxi(1,ceili(size.x/(timeline.pixels_per_beat*stride))+3)

func _resize_retained_pool() -> void:
    if retained_first_loop == null:
        return
    var required: int = maxi(4,_required_repeat_copies()) if stream_enabled else _required_repeat_copies()
    while retained_repeat_segments.size() < required:
        retained_repeat_segments.append(_new_retained_segment("source",
            "once" if stream_enabled else "repeat"))
        if not stream_enabled:
            retained_rest_segments.append(_new_retained_segment("rest","normal"))
    while retained_repeat_segments.size() > required:
        var last_source = retained_repeat_segments.pop_back()
        retained_all_segments.erase(last_source)
        last_source.queue_free()
        if not retained_rest_segments.is_empty():
            var last_rest = retained_rest_segments.pop_back()
            retained_all_segments.erase(last_rest)
            last_rest.queue_free()

func retained_ready() -> bool:
    if not native_ready or size.x < 100.0 or size.y < 100.0 or \
            retained_first_once == null or retained_first_loop == null or \
            retained_annotations == null:
        return false
    for segment in [retained_first_once,retained_first_loop]:
        if not segment.compiled:
            return false
    for segment in retained_repeat_segments + retained_rest_segments:
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

func _sync_retained_visibility(active: Dictionary) -> void:
    # Active lookups are O(1) and the stable pool list is never constructed
    # inside the animation loop. Transform-only motion retains draw commands.
    for segment in retained_all_segments:
        var warming: bool = not segment.compiled
        var selected: bool = active.has(segment)
        var should_show: bool = selected or warming
        if segment.visible != should_show:
            segment.visible = should_show
        if warming and not selected:
            segment.position = Vector2(-1000000.0,0.0)

func _invalidate_retained_segments() -> void:
    retained_ink_published = false
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
        annotations.paint(canvas,float(annotation_pass["clock"]),playhead_x,gap,
            int(annotation_pass["pass_index"]),float(annotation_pass["pass_start"]),{
                "active_hand":active_hand,"play_from_beat":play_from_beat,
                "score_loop_enabled":score_loop_enabled,
                "preparation_history":preparation_history})
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
        from_beat: float) -> void:
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
    stream_passes.append({
        "segment":choice,
        "clip":clip,
        "world_origin":start_world-source_beat,
        "source_floor":maxf(0.0,from_beat),
        "serial":_stream_serial,
    })


func present_flow(world_beat: float, state: Dictionary,
        graded_beat: float, allow_admission: bool = true) -> void:
    if not stream_enabled:
        return
    stream_world_beat = maxf(stream_world_beat,world_beat)
    if not native_ready or not retained_ready():
        queue_redraw()
        return
    var phase: String = str(state.get("phase",""))
    var mode: String = str(state.get("mode","practice"))
    var source: float = float(state.get("play_from_beat",0.0)) + graded_beat
    var key: String = "%s|%d|%d|%s" % [
        str(state.get("piece_fingerprint","")),
        int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),mode]
    var paused_now: bool = bool(state.get("paused",false))
    var running_now: bool = bool(state.get("running",false)) and not paused_now
    if paused_now and not _stream_was_paused:
        _stream_resume_floor = maxf(0.0,source)
        _stream_was_paused = true
    if allow_admission and running_now and phase in ["count_in","playing",
            "guided_wait"] and (key != _stream_last_take or _stream_was_paused):
        _stream_add_take(source,stream_world_beat,
            _stream_resume_floor if _stream_was_paused and key == _stream_last_take else 0.0)
        _stream_last_take = key
        _stream_was_paused = false
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
        var trailing_end: float = position+timeline.duration_beats*density
        if trailing_end < -60.0:
            segment.reparent(self,false)
            clip.queue_free()
            stream_passes.remove_at(index)
            continue
        var clip_x: float = position+floor_x
        clip.position = Vector2(clip_x,0.0)
        clip.size = Vector2(maxf(1.0,
            (timeline.duration_beats+2.0)*density-floor_x+size.x),size.y)
        segment.position = Vector2(-floor_x,0.0)
        if segment.compiled:
            used[segment] = true
            var count: int = RetainedNoteProjection.append_visible(
                segment.note_instances,position,size.x,playhead_x,
                int(item["serial"]),drawn_note_instances,drawn_noteheads,
                floor_x)
            visible_symbols += count
            frame_scanned_events += count
            fingering_pass_clocks.append({
                "clock":stream_world_beat-float(item["world_origin"])-play_from_beat,
                "pass_index":0,"pass_start":0.0})
    # The source geometry is in immutable local source coordinates. Only
    # the clip windows and Node2D transforms change on every render frame.
    for item in stream_passes:
        var segment = item["segment"]
        segment.visible = used.has(segment)
    for segment in retained_all_segments:
        if not used.has(segment) and segment.visible:
            segment.visible = not segment.compiled


func present_ambient(blank: bool, ticks: int) -> void:
    if not native_ready or runway_overlay:
        return
    if blank:
        if not ambient_blank:
            ambient_blank = true
            ambient_scroll_beat = visual_scroll_beat
            _hide_retained_segments()
            if retained_annotations != null:
                retained_annotations.visible = false
        elif ambient_last_ms > 0:
            # The empty canvas can move while the authoritative clock is
            # stopped; it never moves graded noteheads or affects playback.
            ambient_scroll_beat += maxf(0.0,float(ticks-ambient_last_ms)) * bpm / 60000.0
        ambient_last_ms = ticks
        queue_redraw()
    elif ambient_blank:
        ambient_blank = false
        ambient_last_ms = 0
        if retained_annotations != null:
            retained_annotations.visible = true
        queue_redraw()


func present_clock(transport_beat: float, visual_beat: float = NAN) -> void:
    super.present_clock(transport_beat,visual_beat)
    if score_loop_enabled and not preparation_history.is_empty():
        _prune_preparation_history()

func present(state: Dictionary, transport_beat: float, visual_beat: float = NAN) -> void:
    if state.get("phase","") == "ready" and state.get("practice_preparation") == null and \
            absf(float(state.get("visual_offset_beats",0.0)))<.00001:
        if not preparation_history.is_empty():
            preparation_history.clear()
            _clear_recovery_ink()
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
    if score_loop_enabled:
        _prune_preparation_history()
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
            retained_all_segments.erase(segment)
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

func _prune_preparation_history() -> void:
    if preparation_history.is_empty() or practice_timeline.is_empty():
        return
    var stride: float = float(practice_timeline["stride_beats"])
    var left: float = visual_scroll_beat-size.x*PLAYHEAD_FRACTION/\
        timeline.pixels_per_beat
    var changed := false
    for owner in preparation_history.keys():
        if float(owner)+2.0*stride < left:
            preparation_history.erase(owner)
            changed = true
    if changed:
        _rebuild_recovery_ink()

func _remember_preparation() -> void:
    if practice_preparation.is_empty():
        return
    if not practice_timeline.is_empty():
        var stride: float = float(practice_timeline["stride_beats"])
        var left: float = visual_scroll_beat-size.x*PLAYHEAD_FRACTION/\
            timeline.pixels_per_beat
        if float(practice_preparation["measure"]["end_beat"])+stride < left:
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


func _project_retained_source(segment, shift_x: float,
        camera_clock: float, pass_index: int, pass_start: float) -> void:
    segment.position = Vector2(shift_x,0.0)
    if not segment.compiled:
        return
    frame_visible_beam_groups += segment.beam_groups_drawn
    fingering_pass_clocks.append({"clock":camera_clock,
        "pass_index":pass_index,"pass_start":pass_start})
    var playhead_x: float = size.x*PLAYHEAD_FRACTION
    var count: int = RetainedNoteProjection.append_visible(
        segment.note_instances,shift_x,size.x,playhead_x,pass_index,
        drawn_note_instances,drawn_noteheads)
    visible_symbols += count
    frame_scanned_events += count

func _source_overlaps_preparation(pass_start: float) -> bool:
    var interval := {"start_beat":pass_start,
        "end_beat":pass_start+timeline.duration_beats}
    for item in preparation_history.values():
        if absf(float(item.get("pass_start_beat",-INF))-pass_start)<.00001 or \
                SourceVisibility.intervals_overlap(interval,item["measure"]):
            return true
    return false

func _place_retained_score(playhead_x: float, camera_clock: float,
        ready_preview_beat: float = NAN) -> void:
    if retained_first_once == null:
        return
    var active_segments: Dictionary = {}
    var density: float = timeline.pixels_per_beat
    var scroll_beat: float = ready_preview_beat if is_finite(ready_preview_beat) else visual_scroll_beat
    if not score_loop_enabled:
        var shift: float = playhead_x-(camera_clock+play_from_beat)*density
        _project_retained_source(retained_first_once,shift,camera_clock,0,0.0)
        active_segments[retained_first_once] = true
        _sync_retained_visibility(active_segments)
        return
    var stride: float = float(practice_timeline["stride_beats"])
    var virtual_left: float = scroll_beat-playhead_x/density
    var virtual_right: float = virtual_left+size.x/density
    var first_pass: int = maxi(0,floori(virtual_left/stride)-1)
    var last_pass: int = maxi(first_pass,ceili(virtual_right/stride)+1)
    var source_slot := 0
    var rest_slot := 0
    for pass_index in range(first_pass,last_pass+1):
        var pass_start: float = pass_index*stride
        if pass_start >= runway_cutoff_beat - .0001:
            continue
        if pass_start>virtual_right+.7 or pass_start+stride<virtual_left-.7:
            continue
        var source_clock: float = scroll_beat-pass_start-play_from_beat
        var source_shift: float = playhead_x+(pass_start-scroll_beat)*density
        var segment
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
        active_segments[segment] = true
        var silence_start: float = pass_start+timeline.duration_beats
        var silence_end: float = pass_start+stride
        # An acknowledged next step replaces the repeat-rest area: its
        # different music is already present on the same horizontal axis.
        if silence_end > runway_cutoff_beat - .0001:
            continue
        if silence_start > virtual_right+.7 or silence_end < virtual_left-.7:
            continue
        var replaced := false
        for item in preparation_history.values():
            var measure: Dictionary = item["measure"]
            if silence_start < float(measure["end_beat"])-.00001 and \
                    float(measure["start_beat"]) < silence_end-.00001:
                replaced = true
                break
        if not replaced and rest_slot < retained_rest_segments.size():
            var rest: Node2D = retained_rest_segments[rest_slot]
            rest_slot += 1
            rest.position = Vector2(playhead_x+(
                pass_start+timeline.duration_beats-scroll_beat)*density,0.0)
            active_segments[rest] = true
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
            float(replaced_rest["start_beat"])-scroll_beat)*density,0.0)
        active_segments[recovery_rest] = true
    _sync_retained_visibility(active_segments)

func displayed_scroll_beat() -> float:
    # READY may expose an attack beyond a long opening rest. All overlays
    # must share this display-only camera while source transport stays put.
    if running or paused:
        return visual_scroll_beat
    var key: Array = [active_hand,play_from_beat,size.x,timeline.pixels_per_beat]
    if key != _ready_preview_key:
        _ready_preview_beat = IdlePreview.beat_for_ready(
            layout.ordered_events,active_hand,play_from_beat,
            size.x,timeline.pixels_per_beat,PLAYHEAD_FRACTION)
        _ready_preview_key = key
    return _ready_preview_beat

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
    var ready_preview_beat: float = NAN
    if not running and not paused:
        ready_preview_beat = displayed_scroll_beat()
    var camera_clock: float = (clock_beat if running or paused else
        ready_preview_beat-play_from_beat)
    # The precise line and GPU halo use one geometry contract.
    var line_region: Rect2 = playhead_region()
    var top: float = line_region.position.y
    var bottom: float = line_region.end.y
    if transport_overlay_enabled and not runway_overlay and not ambient_blank and not stream_enabled:
        var displayed_beat := displayed_scroll_beat() if score_loop_enabled else camera_clock+play_from_beat
        # Illuminate the selected measure in READY as well as PLAYING and
        # PAUSED. The first playable note owns the idle camera, not wall time.
        var light_beat := maxf(0.0,displayed_beat) if not running and not paused else displayed_beat
        var bounds := MeasureLight.interval(timeline.measures,light_beat,
            practice_timeline if score_loop_enabled else {},
            preparation_history if score_loop_enabled else {},runway_cutoff_beat)
        MeasureLight.paint(self,timeline,displayed_beat,bounds,gap,top,bottom,playhead_x)
        # The soft halo is now a GPU additive Gaussian in MintGlow,
        # below the engraved source. Do not paint thick rectangular bands.
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
    if (ambient_blank or stream_enabled) and not runway_overlay:
        var measure_beats: float = 4.0
        if not timeline.measures.is_empty():
            var opening: Dictionary = timeline.measures[0]
            measure_beats = maxf(.25, float(opening.get("end_beat",4.0)) -
                float(opening.get("start_beat",0.0)))
        var bar_width: float = maxf(64.0,measure_beats*timeline.pixels_per_beat)
        var offset: float = fposmod((
            stream_world_beat if stream_enabled else ambient_scroll_beat) *
            timeline.pixels_per_beat,bar_width)
        var barline_top_y: float = layout.barline_top(gap)
        var barline_bottom_y: float = layout.barline_bottom(gap)
        for index in range(-1,ceili(size.x/bar_width)+3):
            var x: float = playhead_x-offset+float(index)*bar_width
            if x >= 0.0 and x <= size.x:
                draw_line(Vector2(x,barline_top_y),
                    Vector2(x,barline_bottom_y),
                    Color(NOTE_INK,.20 if stream_enabled else .33),1.0,true)
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
        var rhythmic: bool = (running and not paused) or (
            score_loop_enabled and not practice_preparation.is_empty() and not paused)
        if rhythmic:
            var beat_axis := (stream_world_beat if stream_enabled else
                visual_scroll_beat if score_loop_enabled else clock_beat)
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
    if score_loop_enabled and not stream_enabled and not practice_contract_error.is_empty():
        draw_string(font,Vector2(20,size.y*.5),practice_contract_error,
            HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
        _hide_retained_segments()
        return
    if stream_enabled:
        _project_stream(playhead_x)
    elif ambient_blank and not runway_overlay:
        return
    else:
        _place_retained_score(playhead_x,camera_clock,ready_preview_beat)
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
        "focused_staff":layout.focused_staff,
        "score_loop_enabled":score_loop_enabled,"pass_index":pass_index,
        "pass_start":pass_start,"preparation_history":preparation_history,
        "visual_scroll_beat":visual_scroll_beat})
