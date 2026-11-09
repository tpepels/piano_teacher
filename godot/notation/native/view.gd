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
const MovingMeterGrid := preload("res://moving_meter_grid.gd")
const TransportReservation := preload("res://score_transport_reservation.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
const SourcePassPainter := preload("res://notation/native/source_pass_painter.gd")
const RetainedAnnotationOverlay := preload("res://notation/native/retained_annotation_overlay.gd")
var symbols = SymbolPainter.new(layout,connector_geometry)
var context_painter = ContextPainter.new(layout,symbols)

var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var drawn_note_instances: Array = []
# Read-only view of the note-status ledger (NativeScoreFeedback). Each source
# strip paints its own status ink from it; the renderer never grades.
var note_status_source = null
var note_status_visible := true
var selected_density := 0.0
var external_backdrop := false
var compact_inactive_staff := false
# One infinite front-of-house camera. Grading never reads this axis.
var stream_world_beat := 0.0
var _stream_queue = StreamQueue.new()
# Compatibility getter for the read-only renderer/test interface. Only
# StreamQueue may structurally mutate the underlying online FIFO.
# External UI, HUD and diagnostics receive a snapshot. They cannot
# mutate the actual online queue or an admitted note's immutable geometry.
# All internal rendering/transport code uses _stream_queue.online directly.
var stream_passes: Array:
    get:
        # Diagnostics/test snapshot only. No rendering or per-frame path may
        # read this: it copies the whole online queue.
        return _stream_queue.online.duplicate(true)

func stream_pass_count() -> int:
    return _stream_queue.online.size()

## Take keys of every source strip in the online queue, without copying it.
func visible_take_keys() -> Array:
    var keys: Array = []
    for item in _stream_queue.online:
        if str(item.get("kind","source")) == "source":
            keys.append(str(item.get("take_key","")))
    return keys

## Earliest admitted strip (source or rest) world origin at or after ``from_world``.
func first_strip_origin_after(from_world: float) -> float:
    var result := INF
    for item in _stream_queue.online:
        var origin: float = float(item["world_origin"])
        if origin >= from_world:
            result = minf(result,origin)
    return result

func set_note_status_source(source) -> void:
    note_status_source = source
    queue_redraw()

func set_note_status_visible(enabled: bool) -> void:
    if note_status_visible != enabled:
        note_status_visible = enabled
        queue_redraw()
var offline_stream_queue: Array:
    get:
        return _stream_queue.offline
# Immutable source event index for cursor ink clearance. The painter may
# temporarily suppress one glyph for framebuffer controls; that must not
# change the fixed timing line or alter unrelated image pixels.
var _cursor_engraved_events: Array = []
var _stream_last_take := ""
var _stream_was_paused := false
var _stream_paused_source := 0.0
var _stream_paused_owner := -1
var _stream_live_serial := -1
var _stream_armed_serial := -1
var _stream_arm_rollback: Dictionary = {}
var _stream_arm_acknowledged := false
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
var retained_rest_segments: Array = []
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
    _cursor_engraved_events.clear()
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

func _archive_source_identity(candidate: Dictionary) -> String:
    # The journal is keyed by immutable MUSICAL SOURCE, not transient
    # backend revision or transport ID. Reopening the same actual score
    # can therefore recover its withdrawn material without mixing songs.
    var source: Dictionary = {}
    for key in ["schema","duration_beats","notes","notation_events",
            "measures","time_signatures","key_signatures","clefs",
            "beam_groups","tie_groups","slur_pairs","tuplets",
            "tempo_changes","hand"]:
        if candidate.has(key):
            source[key] = candidate[key]
    return JSON.stringify(source).sha256_text()


func load_score(candidate: Dictionary) -> bool:
    connector_geometry.clear_cache()
    annotations.clear()
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
    if not _stream_queue.bind_score(_archive_source_identity(candidate)):
        failure_reason = "Cannot recover offline score material: " + \
            _stream_queue.last_error
        notice = failure_reason
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
    _cursor_engraved_events = layout.ordered_events.duplicate(true)
    connector_geometry.clear_cache()
    connector_geometry.prewarm_tie_clearances(prepared_gap)
    connector_geometry.prewarm_beam_layout(prepared_gap,layout.cached_head_offsets)
    connector_geometry.prewarm_slur_geometry(prepared_gap)

func _stream_release_all() -> void:
    _stream_queue.reset(self)
    _scheduled_score_plan_ids.clear()
    _stream_last_take = ""
    _stream_was_paused = false
    _stream_paused_source = 0.0
    _stream_paused_owner = -1
    _stream_live_serial = -1
    _stream_armed_serial = -1
    _stream_arm_rollback.clear()
    _stream_arm_acknowledged = false

func _clear_retained_segments() -> void:
    _stream_release_all()
    for segment in [retained_first_once,retained_annotations] + \
            retained_repeat_segments + retained_rest_segments:
        if segment != null and is_instance_valid(segment):
            if segment.get_parent() == self:
                remove_child(segment)
            segment.queue_free()
    retained_first_once = null
    retained_annotations = null
    retained_ink_published = false
    retained_repeat_segments.clear()
    retained_rest_segments.clear()
    retained_all_segments.clear()

func _new_retained_segment(kind: String):
    var segment = RetainedSegment.new()
    add_child(segment)
    retained_all_segments.append(segment)
    segment.configure(self,kind)
    return segment

func _install_retained_segments() -> void:
    _clear_retained_segments()
    clip_contents = true
    retained_ink_published = false
    retained_first_once = _new_retained_segment("source")
    _resize_retained_pool()
    retained_annotations = RetainedAnnotationOverlay.new()
    retained_annotations.set("owner_view",self)
    retained_annotations.z_index = 5
    add_child(retained_annotations)
    StreamLifecycle.present_pool(retained_all_segments)

func _resize_retained_pool() -> void:
    if retained_first_once == null:
        return
    # Precompile one bounded authored interval per score measure, not one
    # WHOLE-PIECE buffer per measure. Initial admission can now attach
    # already engraved measure strips without consuming a frame to rebuild.
    # Extra reusable buffers are available for future overlapping takes.
    var windows: Array[Vector2] = _stream_source_windows(
        maxf(0.0,play_from_beat))
    if not windows.is_empty():
        retained_first_once.set_source_window(windows[0].x,windows[0].y)
    var required: int = maxi(4,windows.size()-1)
    while retained_repeat_segments.size() < required:
        retained_repeat_segments.append(_new_retained_segment("source"))
    for index in range(1,windows.size()):
        retained_repeat_segments[index-1].set_source_window(
            windows[index].x,windows[index].y)
    while retained_rest_segments.size() < 5:
        retained_rest_segments.append(_new_retained_segment("rest"))

func retained_ready() -> bool:
    if not native_ready or size.x < 100.0 or size.y < 100.0 or \
            retained_first_once == null or retained_annotations == null:
        return false
    for segment in [retained_first_once]:
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

func _invalidate_retained_segments() -> void:
    retained_ink_published = false
    # Every source/rest pass is owned by StreamLifecycle, including those
    # currently clipped. Unstage BEFORE invalidation: a CanvasItem cannot
    # rebuild its command buffer under an invisible clipping parent.
    StreamLifecycle.prepare_recompile(self,_stream_queue.online)
    for segment in [retained_first_once] + \
            retained_repeat_segments + retained_rest_segments:
        if segment != null and is_instance_valid(segment):
            segment.compiled = false
            segment.queue_redraw()
    StreamLifecycle.present_pool(retained_all_segments)

func paint_retained_source(canvas: CanvasItem) -> RenderPass:
    return SourcePassPainter.paint(self,canvas)

func paint_retained_rest(canvas: CanvasItem) -> void:
    if practice_timeline.is_empty() or timeline.measures.is_empty():
        return
    var gap: float = staff_gap()
    var silence: Dictionary = practice_timeline["gap"].duplicate(true)
    silence["left_barline"] = timeline.measures[-1].get("right_barline",{})
    var incoming: Variant = timeline.measures[0].get("left_barline")
    if incoming is Dictionary:
        silence["right_barline"] = incoming
    var frame: RenderPass = _new_paint_frame(0.0,0.0,gap,0,0.0)
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
    canvas.draw_rect(Rect2(0,staff_top-gap,29,
        staff_bottom-staff_top+gap*2),Design.STAGE)
    if glyphs.textures.has("brace"):
        canvas.draw_texture_rect(glyphs.textures["brace"],
            Rect2(6,staff_top-2,18,staff_bottom-staff_top+4),false,NOTE_INK)
    canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)

# Last actual source origin anchors the empty moving bar after its
# clips have expired. New copies reanchor only at an authored source entry.
var _ambient_anchor_world := 0.0

var _stream_last_admitted := -1
# Each backend decision has a stable identity. Repeated state polls cannot
# enqueue another copy after the first source has already been activated
# or has passed off the left edge.
var _scheduled_score_plan_ids: Dictionary = {}

func _stream_source_windows(opening: float) -> Array[Vector2]:
    # A passage is prepared once, but admitted as immutable adjoining
    # measure strips. Visible strips lock; untouched future strips remain
    # retractable without rewriting a previously rendered CanvasItem.
    var edges: Array[float] = [opening]
    for measure in timeline.measures:
        var beat: float = float(measure.get("start_beat",-1.0))
        if beat > opening+.00001 and \
                beat < timeline.duration_beats-.00001:
            edges.append(beat)
    edges.append(timeline.duration_beats)
    edges.sort()
    var strips: Array[Vector2] = []
    for i in range(1,edges.size()):
        if edges[i] > edges[i-1]+.00001:
            strips.append(Vector2(edges[i-1],edges[i]))
    return strips


func _stream_add_take(source_beat: float, start_world: float,
        from_beat: float, take_key: String, empty_strip: bool = false) -> void:
    _stream_last_admitted = -1
    var first_serial: int = _stream_serial+1
    var original_origin: float = start_world-source_beat
    var hidden: bool = take_key == "prepared"
    var windows: Array[Vector2] = _stream_source_windows(maxf(0.0,from_beat))
    if windows.is_empty():
        return
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var gap_pixels: float = staff_gap()
    var gap: float = float(practice_timeline.get("gap",{}).get(
        "duration_beats",0.0))
    var added := 0
    for index in range(windows.size()):
        var bounds: Vector2 = windows[index]
        var is_first: bool = index == 0
        var is_last: bool = index == windows.size()-1
        var serial: int = first_serial+index
        # The cut points are musical beats. Extra contextual ink is
        # measured in staff spaces at projection time, so resizing cannot
        # shift a committed source boundary or crop the initial clef.
        var clip_floor: float = bounds.x
        var clip_ceiling: float = bounds.y
        var leading_spaces: float = (
            15.0 if bounds.x <= .0001 else 1.6) if is_first else 0.0
        var trailing_spaces: float = 2.2 if is_last else 0.0
        var specs: Array = [{
            "kind":"source","owner_serial":serial,
            "take_owner":first_serial,
            "world_origin":original_origin,
            "source_floor":bounds.x,"source_ceiling":bounds.y,
            "clip_floor":clip_floor,"clip_ceiling":clip_ceiling,
            "clip_leading_spaces":leading_spaces,
            "clip_trailing_spaces":trailing_spaces,
            "piece_duration":timeline.duration_beats,"take_key":take_key,
            "pending":take_key in ["prepared","autopending"],
            "hidden_until_armed":hidden}]
        if is_last and gap > .0001:
            specs.append({
                "kind":"rest","owner_serial":serial,
                "take_owner":first_serial,
                "world_origin":original_origin+timeline.duration_beats,
                "source_floor":0.0,"source_ceiling":gap,
                "take_key":"rest","pending":false,
                "hidden_until_armed":hidden})
        if not _stream_queue.enqueue(self,specs,
                retained_repeat_segments,retained_rest_segments,
                retained_first_once,stream_world_beat,size.x,
                size.x*PLAYHEAD_FRACTION,timeline.pixels_per_beat,
                gap_pixels,timeline.duration_beats,empty_strip):
            # If admission fails partway through the immutable take,
            # unwind ONLY the new right-hand strip suffix, preserving the
            # old on-screen prefix and archiving every removed owner.
            if added > 0:
                _stream_queue.withdraw_take_tail(self,first_serial,
                    stream_world_beat,density,gap_pixels,
                    timeline.duration_beats,size.x,
                    size.x*PLAYHEAD_FRACTION,"failed_take_batch")
                if _stream_queue.has_take(first_serial):
                    push_error("Cannot safely roll back incomplete streamed take")
            push_error("Refused immutable score strip admission %d" % serial)
            return
        added += 1
    _stream_serial = first_serial+windows.size()-1
    _stream_live_serial = first_serial
    _stream_last_admitted = first_serial

func _stream_right_beats() -> float:
    return size.x*(1.0-PLAYHEAD_FRACTION)/maxf(1.0,timeline.pixels_per_beat)


func _stream_header_beats(opening: float) -> float:
    return (15.0 if opening <= .0001 else 1.6)*staff_gap()/ \
        maxf(1.0,timeline.pixels_per_beat)


func _stream_reserve_ready(world: float, opening: float) -> int:
    if not native_ready or not retained_ready() or \
            opening >= timeline.duration_beats:
        return -1
    var right: float = _stream_right_beats()
    var header: float = _stream_header_beats(opening)
    var index: int = StreamAdmission.select(
        _stream_queue.online,"ready",opening,world,right,header)
    if index >= 0:
        return int(_stream_queue.online[index]["serial"])
    # READY never edits an existing placement. If its hidden source has
    # approached the display, withdraw the still-unexposed tail into the
    # offline queue, then append a fresh immutable future reservation.
    var stale: int = StreamAdmission.select(
        _stream_queue.online,"idle",opening,world)
    if stale >= 0:
        var stale_serial: int = int(_stream_queue.online[stale]["serial"])
        var removed: Array[int] = _stream_queue.withdraw_tail(
            self,world,timeline.pixels_per_beat,staff_gap(),
            timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION,
            "idle_expired")
        if not removed.has(stale_serial):
            # The old reservation has crossed its immutable exposure
            # boundary. Retain it and append beyond its printed end.
            # Returning -1 here strands Pause -> Resume at low BPM.
            pass
    var onset: float = StreamAdmission.position(_stream_queue.online,world,right,
        header,NAN,StreamAdmission.READY_TRAVEL_BEATS,
        timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
    # A new stage may be ready while prior lesson ink is still moving.
    # Choose a later offscreen origin instead of repeatedly rejecting Play.
    var peer_floor: float = _stream_queue.minimum_peer_opening(
        timeline.pixels_per_beat,size.x,size.x*PLAYHEAD_FRACTION)
    if is_finite(peer_floor):
        onset = maxf(onset,peer_floor+header+
            StreamAdmission.REST_GAP_BEATS)
    if not is_finite(onset):
        return -1
    var old_serial := _stream_serial
    _stream_add_take(opening,onset,opening,"prepared")
    if _stream_serial == old_serial:
        return -1
    _stream_live_serial = -1
    return _stream_last_admitted


func _stream_claim_pending_auto(world: float, opening: float) -> int:
    var index: int = StreamAdmission.select(_stream_queue.online,"automatic",
        opening,world,_stream_right_beats(),_stream_header_beats(opening))
    return int(_stream_queue.online[index].get("take_owner",
        _stream_queue.online[index]["serial"])) if index >= 0 else -1


func _reject_stream_candidate(owner_serial: int, before_serial: int,
        old_live_serial: int, snapshot: Dictionary) -> void:
    # A failed pre-commit reservation must not leave a speculative future
    # source/rest pair occupying the musical axis.
    if owner_serial > before_serial:
        _stream_queue.withdraw_take_tail(self,owner_serial,stream_world_beat,
            timeline.pixels_per_beat,staff_gap(),timeline.duration_beats,
            size.x,size.x*PLAYHEAD_FRACTION,"rejected_admission")
    elif not snapshot.is_empty():
        StreamLifecycle.restore_owner(_stream_queue.online,owner_serial,snapshot)
    _stream_live_serial = old_live_serial


func _transport_admission_receipt(planned: Dictionary,
        reserved: Dictionary, world: float, opening: float) -> Dictionary:
    if reserved.is_empty():
        return {}
    # A bounded, externally inspectable receipt for every accepted user
    # transport. This is the SAME deadline later sent to the backend.
    var entry_seconds: float = maxf(0.0,
        (float(reserved["start_world"])-opening+
            StreamAdmission.clip_bounds({
                "kind":"source","source_floor":opening,
                "source_ceiling":timeline.duration_beats,
                "clip_floor":opening,
                "clip_ceiling":timeline.duration_beats,
                "clip_leading_spaces":15.0 if opening <= .0001 else 1.6
            },timeline.pixels_per_beat,staff_gap(),
                timeline.duration_beats).x/
                    maxf(1.0,timeline.pixels_per_beat) -
            stream_world_beat-_stream_right_beats()) *
            60.0/maxf(1.0,bpm))
    var receipt: Dictionary = {"action":str(planned["action"]),
        "mode":str(planned["mode"]),
        "start_world":float(reserved["start_world"]),
        "source_opening":opening,"at_world":world,
        "lead_seconds":StreamAdmission.lead_seconds(
            float(reserved["start_world"]),world,bpm),
        "first_ink_delay_seconds":entry_seconds,
        "online_strips":_stream_queue.online.size()}
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
        print("SCORE_TRANSPORT_RECEIPT:",JSON.stringify(receipt))
    reserved["admission_receipt"] = receipt
    return reserved


func reserve_transport_action(action: String, world: float,
        opening: float, count_in_beats: float) -> Dictionary:
    # The ONLY user-command route. First compute both the future slot and
    # safe suffix on immutable previews; failed preflight cannot withdraw
    # any source or start the backend transport. count_in_beats is the
    # engine's next_count_in_beats (one count-in bar).
    var planned: Dictionary = TransportReservation.plan(
        self,action,world,opening,count_in_beats)
    if not bool(planned.get("ok",false)):
        push_error("SCORE_TRANSPORT_PREFLIGHT: %s action=%s opening=%.3f" % [
            str(planned.get("reason","unknown")),action,opening])
        return {}
    stream_world_beat = maxf(stream_world_beat,world)
    var mode: String = str(planned["mode"])
    if mode == "reuse":
        if action == "resume":
            # The SAME preflight that chose this source identifies the
            # protected owner. Never run a second, independent selection
            # procedure against a partially modified queue.
            trim_future_queue("resume_reuse",int(planned["protected_take"]))
        var existing: Dictionary = arm_stream_take(
            world,opening,NAN,action == "resume",false)
        if existing.is_empty():
            push_error("SCORE_TRANSPORT_COMMIT: preflight reusable owner vanished")
        return _transport_admission_receipt(planned,existing,world,opening)
    # The preflight and actual withdrawal share Queue.preview_tail_withdrawal
    # and the SAME world coordinate. Do not recalculate a different
    # placement after removing the unseen suffix.
    var intended: float = float(planned["start_world"])
    trim_future_queue("user_"+action+"_replace_unseen")
    if _stream_queue.online.size() != int(planned["remaining_count"]):
        push_error("SCORE_TRANSPORT_COMMIT: online queue changed during preflight")
        return {}
    var admitted: Dictionary = arm_stream_take(
        world,opening,intended,false,false,
        count_in_beats if bool(planned.get("empty_strip",false)) else 0.0)
    if admitted.is_empty():
        push_error("SCORE_TRANSPORT_COMMIT: preflighted future take was not admitted")
        return {}
    if absf(float(admitted.get("start_world",NAN))-intended) > .0001:
        push_error("SCORE_TRANSPORT_COMMIT: grading and score deadlines diverged")
        cancel_stream_arm()
        return {}
    return _transport_admission_receipt(planned,admitted,world,opening)


func arm_stream_take(world: float, opening: float,
        planned_start_world: float = NAN,
        resuming_paused: bool = false, retrying: bool = false,
        empty_strip_count_in: float = 0.0) -> Dictionary:
    # The common future-only admission route owns a rollback snapshot until
    # the backend confirms the newly armed transport. Failure returns all
    # source/rest clip roles to their exact original state.
    if not native_ready or not retained_ready():
        return {}
    stream_world_beat = maxf(stream_world_beat,world)
    var old_live: int = _stream_live_serial
    var serial_before: int = _stream_serial
    var serial := -1
    var reused := false
    var reused_auto := false
    var reused_unplayed := false
    if resuming_paused and _stream_was_paused and \
            absf(opening-_stream_paused_source) < .0001:
        var paused_index: int = StreamAdmission.select(_stream_queue.online,"paused",
            opening,stream_world_beat,0.0,0.0,_stream_last_take)
        if paused_index < 0 and _stream_paused_owner >= 0:
            # Pause can precede the preceding Play's transport ACK. In that
            # race the armed owner's key is provisional, but its immutable
            # source and future location are already authoritative.
            for index in range(_stream_queue.online.size()):
                var candidate: Dictionary = _stream_queue.online[index]
                if str(candidate.get("kind","")) != "source" or \
                        int(candidate.get("take_owner",-1)) != _stream_paused_owner:
                    continue
                if str(candidate.get("take_key","")).begins_with("armed:") and \
                        absf(float(candidate.get("source_floor",-1))-opening) < .00001 and \
                        float(candidate["world_origin"])+opening >= \
                            stream_world_beat+StreamAdmission.PAUSED_REUSE_EPSILON_BEATS:
                    paused_index = index
                    break
        if paused_index >= 0:
            serial = int(_stream_queue.online[paused_index].get("take_owner",
                _stream_queue.online[paused_index]["serial"]))
            reused = true
            reused_unplayed = true
    if serial < 0 and (resuming_paused or retrying):
        serial = _stream_claim_pending_auto(stream_world_beat,opening)
        reused_auto = serial >= 0
        reused = reused_auto
    if serial < 0 and is_finite(planned_start_world):
        var checked: float = StreamAdmission.position(_stream_queue.online,
            stream_world_beat,_stream_right_beats(),
            _stream_header_beats(opening),planned_start_world,0.0,
            timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
        var onto_empty_strip := false
        if not is_finite(checked) and empty_strip_count_in > 0.0:
            # The preflight chose the empty-strip count-in bar slot; the
            # live queue must still permit exactly that deadline.
            var earliest: float = StreamAdmission.empty_strip_start(
                _stream_queue.online,stream_world_beat,empty_strip_count_in,
                _stream_header_beats(opening),
                _stream_queue.minimum_peer_opening(timeline.pixels_per_beat,
                    size.x,size.x*PLAYHEAD_FRACTION),
                timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
            onto_empty_strip = is_finite(earliest) and \
                planned_start_world >= earliest-.0001
            checked = planned_start_world if onto_empty_strip else NAN
        if not is_finite(checked):
            return {}
        var previous_serial := _stream_serial
        _stream_add_take(opening,checked,opening,"prepared",onto_empty_strip)
        if _stream_serial == previous_serial:
            return {}
        serial = _stream_last_admitted
    elif serial < 0:
        serial = _stream_reserve_ready(stream_world_beat,opening)
    if serial < 0:
        return {}
    var snapshot: Dictionary = StreamLifecycle.snapshot_owner(
        _stream_queue.online,serial)
    if snapshot.is_empty():
        _reject_stream_candidate(serial,serial_before,old_live,{})
        return {}
    # Every unacknowledged control has a unique owner-scoped identity.
    if not StreamLifecycle.activate(
            _stream_queue.online,serial,"armed:%d" % serial,true):
        _reject_stream_candidate(serial,serial_before,old_live,snapshot)
        return {}
    _stream_armed_serial = serial
    _stream_arm_acknowledged = false
    _stream_arm_rollback = {
        "owner_serial":serial,"source_snapshot":snapshot,
        "newly_allocated":_stream_serial > serial_before,
        "old_live_serial":old_live}
    for item in _stream_queue.online:
        if int(item.get("serial",-1)) == serial:
            return {"start_world":float(item["world_origin"])+opening,
                "opening":opening,"reused":reused,
                "reused_unplayed_count_in":reused_unplayed}
    cancel_stream_arm()
    return {}


func acknowledge_stream_arm() -> bool:
    # An asynchronous /state poll may still contain the OLD transport.
    # Only a successful control response or acknowledged stage promotion
    # can authorize binding its unique owner to a graded backend identity.
    if _stream_armed_serial < 0 or _stream_arm_rollback.is_empty():
        return false
    _stream_arm_acknowledged = true
    return true


func cancel_stream_arm() -> bool:
    # Only an unacknowledged reservation may be rolled back. Once published,
    # the world coordinates are immutable and its notes must exit normally.
    if _stream_arm_rollback.is_empty():
        return false
    var owner_serial: int = int(_stream_arm_rollback["owner_serial"])
    if _stream_armed_serial != owner_serial:
        _stream_arm_rollback.clear()
        return false
    var restored: bool = false
    if bool(_stream_arm_rollback.get("newly_allocated",false)):
        _stream_queue.withdraw_take_tail(
            self,owner_serial,stream_world_beat,timeline.pixels_per_beat,
            staff_gap(),timeline.duration_beats,size.x,
            size.x*PLAYHEAD_FRACTION,"failed_command")
        restored = not _stream_queue.has_take(owner_serial)
    else:
        restored = StreamLifecycle.restore_owner(_stream_queue.online,
            owner_serial,_stream_arm_rollback["source_snapshot"])
    _stream_live_serial = int(_stream_arm_rollback["old_live_serial"])
    _stream_armed_serial = -1
    _stream_arm_acknowledged = false
    _stream_arm_rollback.clear()
    queue_redraw()
    return restored


func _stream_transport_owner(opening: float,
        may_be_provisional: bool) -> int:
    # A backend Pause can arrive before its Play acknowledgement has been
    # projected into a running frame. The current musical take must therefore
    # be resolved from ALL transport identities, not just _stream_live_serial.
    # Losing that one transient field must never delete its unplayed music.
    for candidate in [
            _stream_paused_owner,_stream_live_serial,_stream_armed_serial]:
        var owner_serial: int = int(candidate)
        if owner_serial >= 0 and _stream_queue.has_take(owner_serial):
            return owner_serial
    if not _stream_last_take.is_empty():
        var bound_index: int = StreamAdmission.select(
            _stream_queue.online,"bound",opening,stream_world_beat,
            0.0,0.0,_stream_last_take)
        if bound_index >= 0:
            return int(_stream_queue.online[bound_index].get("take_owner",
                _stream_queue.online[bound_index]["serial"]))
    if may_be_provisional:
        # In-flight Play/Resume can leave only a prepared or armed source.
        # Prefer the oldest source take; autopending is a speculative
        # successor and must never impersonate the active attempt.
        for item in _stream_queue.online:
            if str(item.get("kind","source")) != "source":
                continue
            var key: String = str(item.get("take_key",""))
            if key == "prepared" or key.begins_with("armed:"):
                return int(item.get("take_owner",item["serial"]))
    return -1


func trim_future_queue(reason: String,
        protected_take: int = -1) -> Array[int]:
    # The moving staff has one exit policy. This is the ONLY retractable
    # operation: remove the maximum never-exposed pending suffix, newest
    # first, while preserving the irreversible older prefix.
    var removed: Array[int] = _stream_queue.withdraw_tail(
        self,stream_world_beat,timeline.pixels_per_beat,
        staff_gap(),timeline.duration_beats,size.x,
        size.x*PLAYHEAD_FRACTION,reason,false,protected_take)
    if not removed.is_empty():
        if _stream_live_serial >= 0 and \
                not _stream_queue.has_take(_stream_live_serial):
            _stream_live_serial = -1
        if _stream_armed_serial >= 0 and \
                not _stream_queue.has_take(_stream_armed_serial):
            _stream_armed_serial = -1
            _stream_arm_acknowledged = false
            _stream_arm_rollback.clear()
        if _stream_paused_owner >= 0 and \
                not _stream_queue.has_take(_stream_paused_owner):
            _stream_paused_owner = -1
        queue_redraw()
    return removed


func _restore_future_suffix(saved: Array, world: float) -> bool:
    # Compensation for a failed append after a validated preflight.
    # Re-enqueue the exact previously withdrawn source/rest batches in
    # chronological order; do not create any new world time or note content.
    var cursor := 0
    var restored := true
    while cursor < saved.size():
        var old: Dictionary = saved[cursor]
        var serial: int = int(old.get("owner_serial",-1))
        var batch: Array = []
        while cursor < saved.size() and \
                int(saved[cursor].get("owner_serial",-1)) == serial:
            var item: Dictionary = saved[cursor]
            var spec: Dictionary = _stream_queue._record(item)
            spec["pending"] = bool(item.get("pending",false))
            spec["hidden_until_armed"] = bool(item.get("hidden_until_armed",false))
            batch.append(spec)
            cursor += 1
        if not _stream_queue.enqueue(self,batch,
                retained_repeat_segments,retained_rest_segments,
                retained_first_once,world,size.x,size.x*PLAYHEAD_FRACTION,
                timeline.pixels_per_beat,staff_gap(),timeline.duration_beats):
            push_error("RECOVERY_TRANSACTION: rollback admission failed for "+str(serial))
            restored = false
            break
        for item in _stream_queue.online:
            if int(item.get("owner_serial",-1)) == serial:
                for original in saved:
                    if int(original.get("serial",0)) == int(item.get("serial",0)):
                        item["armed"] = bool(original.get("armed",false))
                        item["ever_visible"] = bool(original.get("ever_visible",false))
                        break
    return restored


func enqueue_recovery_queue(world: float, source_opening: float,
        graded_deadline_world: float, plan_id: String = "",
        allow_count_in: bool = false, count_in_beats: float = 0.0) -> bool:
    # Recovery decisions arrive from the engine with an absolute graded
    # deadline. Reuse a compatible offline-planned future if possible;
    # otherwise withdraw the maximal safe suffix, then APPEND new source
    # notation at that exact deadline. A late deadline must never cause
    # an onscreen pop or independent renderer camera adjustment.
    if not native_ready or not retained_ready() or \
            not is_finite(graded_deadline_world) or \
            source_opening < 0.0 or source_opening >= timeline.duration_beats:
        return false
    stream_world_beat = maxf(stream_world_beat,world)
    var identity: String = plan_id if not plan_id.is_empty() else \
        "%.6f:%.6f" % [source_opening,graded_deadline_world]
    if _scheduled_score_plan_ids.has(identity):
        var claimed: int = int(_scheduled_score_plan_ids[identity])
        # A tail withdrawal can invalidate an earlier speculative plan.
        # An identity ledger alone is never proof that notes still exist.
        for item in _stream_queue.online:
            if str(item.get("kind","")) == "source" and \
                    int(item.get("take_owner",-1)) == claimed and \
                    absf(float(item.get("source_floor",-INF))-source_opening) < .00001 and \
                    absf(float(item["world_origin"])+source_opening-
                        graded_deadline_world) <= StreamAdmission.AUTOMATIC_DUE_EPSILON_BEATS:
                return true
        _scheduled_score_plan_ids.erase(identity)
    # An already elapsed plan may no longer be reinserted: it would
    # introduce notes behind the real playhead.
    if graded_deadline_world <= stream_world_beat:
        return false
    var existing: int = StreamAdmission.select(_stream_queue.online,
        "automatic_due",source_opening,stream_world_beat,
        0.0,0.0,"",graded_deadline_world)
    if existing >= 0:
        _scheduled_score_plan_ids[identity] = int(
            _stream_queue.online[existing].get("take_owner",
                _stream_queue.online[existing]["serial"]))
        return true
    # PREPARE: check the actual exact deadline against the queue AFTER
    # maximal safe tail withdrawal, without mutating the live queue.
    # Previously this check ran AFTER trim_future_queue(), so a late or
    # impossible engine deadline deleted valid pending music first.
    var preview: Dictionary = _stream_queue.preview_tail_withdrawal(
        stream_world_beat,timeline.pixels_per_beat,staff_gap(),
        timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION)
    var remaining: Array = preview["remaining"]
    var checked: float = StreamAdmission.position(remaining,
        stream_world_beat,_stream_right_beats(),
        _stream_header_beats(source_opening),
        graded_deadline_world,0.0,timeline.pixels_per_beat,
        staff_gap(),timeline.duration_beats)
    var on_empty := false
    if not is_finite(checked) and allow_count_in:
        # Listen/Perform use the same engine-authored first note deadline.
        # The source can appear during ONE count-in on an entirely empty
        # staff; the existing source/rest/peer exposure rules still apply.
        var peer_floor: float = _stream_queue.minimum_peer_opening(
            timeline.pixels_per_beat,size.x,size.x*PLAYHEAD_FRACTION)
        var onset: float = StreamAdmission.empty_strip_start(
            remaining,stream_world_beat,count_in_beats,
            _stream_header_beats(source_opening),peer_floor,
            timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
        if is_finite(onset) and \
                absf(onset-graded_deadline_world) <= \
                    StreamAdmission.AUTOMATIC_DUE_EPSILON_BEATS:
            checked = graded_deadline_world
            on_empty = true
    if not is_finite(checked):
        return false
    var incoming_left: float = checked - _stream_header_beats(source_opening)
    if not _stream_queue._clears_prior_layers(incoming_left,
            timeline.pixels_per_beat,size.x,size.x*PLAYHEAD_FRACTION):
        return false
    # COMMIT: the exact same exposure snapshot and world coordinate must
    # still hold. No yield/poll/other input runs between preview and commit.
    var saved_suffix: Array = []
    for index in range(remaining.size(),_stream_queue.online.size()):
        saved_suffix.append(_stream_queue.online[index].duplicate())
    var prior_live: int = _stream_live_serial
    trim_future_queue("recovery_replan")
    if _stream_queue.online.size() != remaining.size():
        push_error("RECOVERY_TRANSACTION: tail was not safely withdrawn")
        _restore_future_suffix(saved_suffix,stream_world_beat)
        _stream_live_serial = prior_live
        return false
    var before: int = _stream_serial
    var original_live: int = _stream_live_serial
    _stream_add_take(source_opening,checked,source_opening,
        "autopending",on_empty)
    _stream_live_serial = original_live
    if _stream_serial > before:
        _scheduled_score_plan_ids[identity] = _stream_last_admitted
        return true
    # No committed replacement: restore exactly the withdrawn source/rest
    # metadata and immutable world positions through the journaled queue.
    _restore_future_suffix(saved_suffix,stream_world_beat)
    _stream_live_serial = prior_live
    return false


func _stream_prune_expired() -> void:
    # All retirement, invalid-record cleanup and CanvasItem reuse take the
    # same path. The renderer itself never reparents or frees a stream clip.
    var retired: Array[int] = _stream_queue.expire_front(
        self,stream_world_beat,maxf(1.0,timeline.pixels_per_beat),
        staff_gap(),timeline.duration_beats,size.x*PLAYHEAD_FRACTION)
    if retired.has(_stream_live_serial) and \
            not _stream_queue.has_take(_stream_live_serial):
        _stream_live_serial = -1
    if retired.has(_stream_armed_serial) and \
            not _stream_queue.has_take(_stream_armed_serial):
        _stream_armed_serial = -1
        _stream_arm_acknowledged = false
        _stream_arm_rollback.clear()

func present_flow(world_beat: float, state: Dictionary,
        graded_beat: float, allow_admission: bool = true) -> void:
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
        # READY frames can arrive after Play was armed but before the
        # backend confirms it. Only presentation frames skip admission;
        # explicit Retry still needs to reserve its own future score.
        if _stream_armed_serial < 0 and StreamAdmission.select(
                _stream_queue.online,"idle",opening,stream_world_beat) < 0:
            # Precompile one hidden immutable READY take. Once it moves too
            # close to the viewport, DO NOT re-enqueue it every few frames.
            # It stays unseen; Play alone refreshes its offscreen placement.
            # If its first source strip has fully expired, discard only the
            # safe hidden remainder before preparing a new one.
            trim_future_queue("ready_source_expired")
            _stream_reserve_ready(stream_world_beat,opening)
    if paused_now:
        if not _stream_was_paused:
            _stream_paused_source = maxf(opening,opening+graded_beat)
            _stream_paused_owner = _stream_transport_owner(
                opening,bool(state.get("running",false)))
        if allow_admission:
            # An in-flight Play/Resume may not have received its ACK yet.
            # Do not discard that provisional owner BEFORE the command
            # result determines whether it was ever authorized. On the
            # first paused frame AFTER ACK, retract the maximal unseen
            # suffix (even from the active take), leaving exposed ink.
            if not (_stream_armed_serial >= 0 and
                    not _stream_arm_acknowledged):
                trim_future_queue("pause")
        _stream_was_paused = true
        _stream_live_serial = -1
    elif allow_admission and not running_now and phase in [
            "feedback","recovering","preview_gap","review"]:
        # Stop speculative admission on feedback. Preserve an already
        # scheduled automatic retry ONLY if its unmodified source opening
        # matches the engine's declared next passage.
        var prep: Variant = state.get("practice_preparation")
        var next_opening: float = (
            float(prep.get("source_from_beat",0.0))
            if prep is Dictionary else 0.0)
        var keep_auto: bool = bool(state.get("auto",false)) or \
            bool(state.get("preview_only",false)) or prep is Dictionary
        if keep_auto and prep is Dictionary:
            for item in _stream_queue.online:
                if str(item.get("take_key","")) == "autopending" and \
                        absf(float(item.get("source_floor",-1.0))-
                            next_opening) > .00001:
                    keep_auto = false
                    break
        if not keep_auto:
            trim_future_queue("changed_practice_decision")
    elif allow_admission and running_now and phase in [
            "count_in","playing","guided_wait"]:
        if key != _stream_last_take or _stream_was_paused:
            _stream_live_serial = -1
            if _stream_armed_serial >= 0:
                # A stale polling snapshot must not claim an unacknowledged
                # Play/Resume/Retry. The source is already offscreen but its
                # transport identity remains provisional until control ACK.
                if _stream_arm_acknowledged:
                    if StreamLifecycle.activate(
                            _stream_queue.online,_stream_armed_serial,key,false):
                        _stream_live_serial = _stream_armed_serial
                        _stream_last_take = key
                        _stream_arm_rollback.clear()
                        _stream_arm_acknowledged = false
                        _stream_armed_serial = -1
                    else:
                        cancel_stream_arm()
            elif key != _stream_last_take and mode in [
                    "practice","perform","listen"]:
                # Polling can bind only an already-present automatic owner
                # whose world-time onset matches the graded backend deadline.
                var expected: float = stream_world_beat-graded_beat
                var candidate: int = StreamAdmission.select(_stream_queue.online,
                    "automatic_due",opening,stream_world_beat,
                    0.0,0.0,"",expected)
                if candidate >= 0:
                    var claimed: int = int(_stream_queue.online[candidate].get(
                        "take_owner",_stream_queue.online[candidate]["serial"]))
                    if StreamLifecycle.activate(
                            _stream_queue.online,claimed,key,false):
                        _stream_live_serial = claimed
                        _stream_last_take = key
            elif key == _stream_last_take and not _stream_was_paused:
                var owned: int = StreamAdmission.select(_stream_queue.online,
                    "bound",opening,stream_world_beat,0.0,0.0,key)
                if owned >= 0:
                    _stream_live_serial = int(_stream_queue.online[owned].get(
                        "take_owner",_stream_queue.online[owned]["serial"]))
        # Future music is enqueued only from an explicit Python practice
        # preparation with its authoritative graded deadline. The renderer
        # must never infer mastery, tempo or repeat policy from HUD state.
        # An unreserved start CANNOT create note ink in the current frame.
        # This fails closed rather than silently taking the old camera path.
        _stream_was_paused = false
        _stream_paused_owner = -1
    elif not paused_now:
        _stream_live_serial = -1
    # Retained compilation may have finished since the previous frame.
    # Clip attachment happens here, before CanvasItem._draw() projects
    # positions. No scene-tree modification is permitted in _draw().
    StreamLifecycle.attach_compiled(_stream_queue.online)
    queue_redraw()


func _project_stream(playhead_x: float) -> void:
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var used: Dictionary = {}
    for item in _stream_queue.online:
        var segment = item.get("segment")
        var clip = item.get("clip")
        # Invalid records are retired by present_flow(), never mutated or
        # removed during CanvasItem._draw().
        if segment == null or not is_instance_valid(segment) or \
                clip == null or not is_instance_valid(clip):
            continue
        if not StreamLifecycle.project(item,stream_world_beat,playhead_x,
                density,staff_gap(),size,timeline.duration_beats):
            continue
        used[segment] = true
        if str(item.get("kind","source")) == "rest":
            continue
        var position: float = playhead_x + \
            (float(item["world_origin"])-stream_world_beat)*density
        var take_key: String = str(item.get("take_key",""))
        # Status ink is a child of this strip: it inherits the strip's exact
        # transform and clip window. Repaints only when its take changes.
        segment.sync_note_status(take_key,note_status_source,note_status_visible)
        var clip_bounds: Vector2 = StreamLifecycle.screen_bounds(
            item,density,staff_gap(),timeline.duration_beats)
        # Register every head the strip actually shows, including heads a
        # voice column displaced left of its source floor into the clip's
        # leading margin: they are painted, so they must stay interactive.
        var count: int = RetainedNoteProjection.append_visible(
            segment.note_instances,position,size.x,playhead_x,
            int(item["serial"]),drawn_note_instances,drawn_noteheads,
            clip_bounds.x,clip_bounds.y,take_key,
            Vector2(position+clip_bounds.x,position+clip_bounds.y))
        visible_symbols += count
        frame_scanned_events += count
        fingering_pass_clocks.append({
            "clock":stream_world_beat-float(item["world_origin"])-play_from_beat,
            "pass_index":0,"pass_start":0.0,
            "stream_floor":float(item["source_floor"]),
            "stream_ceiling":float(item["source_ceiling"])})
    StreamLifecycle.present_pool(retained_all_segments,used)

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
    if focus_changed and native_ready and size.y >= 100.0:
        # Focusing a staff moves every note on it and drops the prepared
        # source geometry. Rebuild it now: painting must never meet a stale
        # cache, or the retained ink would never compile.
        _prepare_static_geometry()
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


func _cursor_ink_clearances(gap: float) -> Array:
    # Only a tiny beat window around the fixed cursor is inspected. The
    # already sorted canonical MusicXML event index is binary searched; no
    # full-score traversal, renderer variant, or new camera exists.
    var exclusions: Array = []
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var events: Array = _cursor_engraved_events
    if events.is_empty():
        return exclusions
    var guard: float = gap*1.7/density
    for item in _stream_queue.online:
        if str(item.get("kind","source")) != "source":
            continue
        var source_at_line: float = stream_world_beat - float(item["world_origin"])
        if source_at_line+guard < float(item["source_floor"]) or \
                source_at_line-guard > float(item["source_ceiling"]):
            continue
        var lo := 0
        var hi: int = events.size()
        while lo < hi:
            var mid: int = (lo+hi)>>1
            if float(events[mid].get("beat",0.0)) < source_at_line-guard:
                lo = mid+1
            else:
                hi = mid
        for idx in range(lo,events.size()):
            var event: Dictionary = events[idx]
            var at: float = float(event.get("beat",0.0))
            if at > source_at_line+guard:
                break
            if absf((at-source_at_line)*density) > gap*1.5:
                continue
            var kind: String = str(event.get("kind",""))
            if kind not in ["note","rest"]:
                continue
            var staff: String = str(event.get("staff","right"))
            if active_hand not in ["both",staff]:
                continue
            var y: float = (layout.rest_y(event,gap) if kind=="rest"
                else layout.event_y(event,gap))
            var half_height: float = gap*(1.8 if kind=="rest" else 1.1)
            exclusions.append(Vector2(y-half_height,y+half_height))
    exclusions.sort_custom(func(a: Vector2,b: Vector2) -> bool:
        return a.x < b.x)
    return exclusions


func _paint_cursor_behind_ink(x: float, top: float, bottom: float,
        gap: float) -> void:
    # A bright cursor directly through a rest/note at its exact onset
    # creates an illegible composite and fails source-rest isolation.
    # Keep the fixed timing axis but leave only local vertical notches
    # where genuine glyph ink is crossing it; the mint halo stays behind.
    var cursor_y: float = top
    for interval in _cursor_ink_clearances(gap):
        var start_y: float = clampf(float(interval.x),top,bottom)
        var end_y: float = clampf(float(interval.y),top,bottom)
        if start_y > cursor_y:
            draw_line(Vector2(x,cursor_y),Vector2(x,start_y),
                Design.HIGHLIGHT,2.4,true)
            draw_line(Vector2(x,cursor_y),Vector2(x,start_y),
                Color(Design.STONE,.62),.9,true)
        cursor_y = maxf(cursor_y,end_y)
    if cursor_y < bottom:
        draw_line(Vector2(x,cursor_y),Vector2(x,bottom),
            Design.HIGHLIGHT,2.4,true)
        draw_line(Vector2(x,cursor_y),Vector2(x,bottom),
            Color(Design.STONE,.62),.9,true)


func _paint_empty_moving_staff() -> void:
    # An unprepared or unloaded score still has the SAME world axis.
    # Never draw a static loading card in place of the moving bar.
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var line_gap: float = clampf(size.y/23.0,13.0,25.0)
    var centers: Array[float] = [size.y*.40,size.y*.70]
    for center in centers:
        for rule in range(5):
            var y: float = center+(float(rule)-2.0)*line_gap
            draw_line(Vector2(0.0,y),Vector2(size.x,y),
                Color(NOTE_INK,.43),1.15,true)
    var ph: float = size.x*PLAYHEAD_FRACTION
    var pulse_width: float = 4.0*density
    var phase: float = fposmod(stream_world_beat*density,pulse_width)
    for index in range(-2,ceili(size.x/pulse_width)+3):
        var x: float = ph-phase+float(index)*pulse_width
        if x >= 0.0 and x <= size.x:
            draw_line(Vector2(x,centers[0]-line_gap*2.0),
                Vector2(x,centers[1]+line_gap*2.0),
                Color(NOTE_INK,.22),1.0,true)
    draw_line(Vector2(ph,centers[0]-line_gap*2.9),
        Vector2(ph,centers[1]+line_gap*2.9),
        Color(Design.MINT,.72),2.4,true)


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
        _paint_empty_moving_staff()
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
        var density: float = maxf(1.0,timeline.pixels_per_beat)
        # Blank measures follow the actual MusicXML meter changes and the
        # same source world origin as the notation. The old fixed 4/4
        # modulo grid drifted through 3/4, 6/8 and pickup passages.
        for item in _stream_queue.online:
            if str(item.get("kind","")) == "source":
                _ambient_anchor_world = float(item["world_origin"])
                break
        var barline_top_y: float = layout.barline_top(gap)
        var barline_bottom_y: float = layout.barline_bottom(gap)
        var world_bars: Array[float] = MovingMeterGrid.visible_lines(
            stream_world_beat,size.x,playhead_x,density,
            _ambient_anchor_world,timeline.measures)
        for bar_world in world_bars:
            var x: float = playhead_x+(bar_world-stream_world_beat)*density
            var inside_printed_strip := false
            for item in _stream_queue.online:
                var source_left: float = playhead_x+(
                    float(item["world_origin"])-stream_world_beat)*density
                var bounds: Vector2 = StreamAdmission.clip_bounds(
                    item,density,gap,timeline.duration_beats)
                if x >= source_left+bounds.x-.01 and \
                        x <= source_left+bounds.y+.01:
                    inside_printed_strip = true
                    break
            if not inside_printed_strip:
                draw_line(Vector2(x,barline_top_y),
                    Vector2(x,barline_bottom_y),
                    Color(NOTE_INK,.20),1.0,true)
    # Keep the fixed playhead visible but BEHIND source ink. At exact
    # onset a foreground cursor previously covered small eighth-rest dots,
    # flagged stems and noteheads, preventing independent contour recovery.
    # Engraving is always painted later; the transport clock is unchanged.
    if transport_overlay_enabled and not runway_overlay:
        _paint_cursor_behind_ink(playhead_x,top,bottom,gap)
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
        "pass_start":pass_start,"preparation_history":{},
        "visual_scroll_beat":0.0})
