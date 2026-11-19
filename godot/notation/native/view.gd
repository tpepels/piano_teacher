extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation is rejected; production reports a preparation error.
const Geometry := preload("res://notation/native/geometry.gd")
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
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
const ScoreStreamWindowCuts := preload("res://score_stream_window_cuts.gd")
const NotationClipPlanner := preload("res://notation/native/notation_clip_planner.gd")
const TransportReservation := preload("res://score_transport_reservation.gd")
const StreamAdmissionExecutor := preload("res://notation/native/stream_admission_executor.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
const ScoreStreamController := preload("res://notation/native/score_stream_controller.gd")
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
var _stream_controller = ScoreStreamController.new()
var _stream_queue:
    get: return _stream_controller.queue

func register_stream_predecessor(previous) -> void:
    _stream_controller.register_predecessor(previous)

func stream_preflight_snapshot() -> Array:
    return _stream_controller.online_snapshot()

func online_stream_count() -> int:
    return _stream_controller.online_size()

## Read-only public peer clearance port.  Other score layers never inspect
## the renderer's private queue or its live retained CanvasItems.
func stream_peer_clearance_facts() -> Dictionary:
    return _stream_controller.peer_clearance_facts(
        maxf(1.0,float(timeline.pixels_per_beat)),float(staff_gap()),
        float(timeline.duration_beats),size.x*PLAYHEAD_FRACTION)

func transport_preflight_facts(world: float, opening: float) -> Dictionary:
    # The transport policy receives an immutable score-geometry/read
    # snapshot. The live queue, peer registry and paused take identity
    # remain owned by this renderer revision; no policy may mutate them.
    var density: float = timeline.pixels_per_beat
    var width: float = size.x
    var gap: float = staff_gap()
    var at_world: float = maxf(world,stream_world_beat)
    var preview: Dictionary = _stream_queue.preview_tail_withdrawal(
        at_world,density,gap,timeline.duration_beats,
        width,width*PLAYHEAD_FRACTION)
    return {
        "source_exists": has_source_windows_at(opening),
        "online": _stream_controller.online_snapshot(),
        "withdrawn": preview.duplicate(true),
        "peer_floor": _stream_queue.minimum_peer_opening(
            density,width,width*PLAYHEAD_FRACTION),
        "right": _stream_right_beats(),
        "header": _stream_header_beats(opening),
        "preview_world": at_world,
        "was_paused": _stream_controller.was_paused,
        "paused_source": _stream_controller.paused_source,
        "paused_owner": _stream_controller.paused_owner,
        "last_take": _stream_controller.last_take
    }

func record_withdrawn_stream_suffix(previous: Array) -> void:
    _stream_controller.remember_withdrawn_suffix(previous)

func enable_retry_placement(enabled: bool) -> void:
    _stream_controller.retry_placement_enabled(enabled)

func restore_withdrawn_stream_suffix(previous: Array, at_world: float) -> bool:
    return _restore_future_suffix(previous,at_world)

func build_admission_receipt(planned: Dictionary, admitted: Dictionary,
        world: float, opening: float) -> Dictionary:
    return _transport_admission_receipt(planned,admitted,world,opening)

# Precomputed genuine horizontal glyph/connector ink; cut decisions are
# source-revision geometry, never recalculated during the animation loop.
var _source_ink_intervals: Array[Vector2] = []

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
var _stream_last_take: String:
    get: return _stream_controller.last_take
    set(value): _stream_controller.last_take = value
var _stream_was_paused: bool:
    get: return _stream_controller.was_paused
    set(value): _stream_controller.was_paused = value
var _stream_paused_source: float:
    get: return _stream_controller.paused_source
    set(value): _stream_controller.paused_source = value
var _stream_paused_owner: int:
    get: return _stream_controller.paused_owner
    set(value): _stream_controller.paused_owner = value
var _stream_live_serial: int:
    get: return _stream_controller.live_serial
    set(value): _stream_controller.live_serial = value
# The last playing take reported without a bound source (reported once).
var _unscored_take := ""
var _stream_armed_serial: int:
    get: return _stream_controller.armed_serial
    set(value): _stream_controller.armed_serial = value
var _stream_armed_segment_id: String:
    get: return _stream_controller.armed_segment_id
    set(value): _stream_controller.armed_segment_id = value
var _stream_live_segment_id: String:
    get: return _stream_controller.live_segment_id
    set(value): _stream_controller.live_segment_id = value
var _stream_arm_rollback: Dictionary:
    get: return _stream_controller.arm_rollback
    set(value): _stream_controller.arm_rollback = value
var _stream_arm_acknowledged: bool:
    get: return _stream_controller.arm_acknowledged
    set(value): _stream_controller.arm_acknowledged = value
var _stream_serial: int:
    get: return _stream_controller.serial
    set(value): _stream_controller.serial = value
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
    # A pre-engraved READY strip can be admitted while transport is idle.
    # The base view's transport-only density lock does not cover that state.
    # Reflowing an already admitted source would silently mutate its printed
    # coordinates and invalidate the queue's density/clearance assertions.
    # A new density may take effect only before ANY strip is committed,
    # including a still-hidden READY source or a written rest.
    if not _stream_queue.online.is_empty():
        if not is_finite(value) or absf(value-timeline.pixels_per_beat) > .000001:
            notice = "The horizontal scale is fixed while score ink is reserved"
            return false
        return true
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
    # The actual native glyph solver below is the only authority for
    # readable note spacing. A separate rhythm-only estimate used to be
    # computed and then discarded, while its extreme-density failure gate
    # remained in effect. Keep only the meaningful source safety check:
    # distinct attacks in the SAME voice closer than the minimum physical
    # separation even at maximum density cannot be represented without
    # distorting authored time. Readability is chosen by InkSpacing itself.
    if not InkSpacing.source_attack_intervals_fit(
            timeline.model.get("notation_events", []),
            timeline.MAX_SCORE_PIXELS_PER_BEAT):
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
    _source_ink_intervals = NotationClipPlanner.ink_safe_boundaries(
        layout,timeline,prepared_gap)



func _stream_release_all() -> void:
    _stream_controller.reset(self)


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
    var windows: Array[Vector2] = NotationClipPlanner.source_windows(timeline,
        maxf(0.0,play_from_beat),_source_ink_intervals)
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
    # No backing panel: strips clip themselves at the gutter
    # (StreamLifecycle.LEFT_GUTTER_PX), so the brace sits on the backdrop.
    if glyphs.textures.has("brace"):
        VerovioGlyphs._draw_fit(canvas,glyphs.textures["brace"],
            Rect2(6,staff_top-2,18,staff_bottom-staff_top+4),false,NOTE_INK)
    canvas.draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)

# Last actual source origin anchors the empty moving bar after its
# clips have expired. New copies reanchor only at an authored source entry.
var _ambient_anchor_world := 0.0

var _stream_last_admitted: int:
    get: return _stream_controller.last_admitted
    set(value): _stream_controller.last_admitted = value
# Owner decision (round 4, 2026-11-11): a written rest bar (the practice
# timeline's gap, always one full measure) follows every take, and it IS
# the count-in bar of the next take: the next source is admitted straight
# after it (empty_strip_start) and its one count-in is spoken over the
# rest, so rest plus count-in stays short (P5).
# Each backend decision has a stable identity. Repeated state polls cannot
# enqueue another copy after the first source has already been activated
# or has passed off the left edge.
var _scheduled_score_plan_ids: Dictionary:
    get: return _stream_controller.planned_ids
    set(value): _stream_controller.planned_ids = value
# World beat at which each admitted plan's source opening reaches the
# playhead (it can be later than the engine deadline for untimed Learn).
var scheduled_plan_openings: Dictionary:
    get: return _stream_controller.planned_openings
    set(value): _stream_controller.planned_openings = value


func has_source_windows_at(opening: float) -> bool:
    # Public immutable source-window existence query for the pure
    # transport preflight. No external component inspects private
    # clipping intervals or renderer-owned source-window caches.
    return not NotationClipPlanner.source_windows(
        timeline,opening,_source_ink_intervals).is_empty()


func _stream_add_take(source_beat: float, start_world: float,
        from_beat: float, take_key: String, empty_strip: bool = false) -> void:
    # Score preparation stays in the renderer. The authoritative queue
    # transaction and take serial assignment belong to the stream controller.
    var windows: Array[Vector2] = NotationClipPlanner.source_windows(
        timeline,maxf(0.0,from_beat),_source_ink_intervals)
    _stream_controller.append_take(self,windows,source_beat,start_world,
        take_key,empty_strip,_first_source_header_spaces(),
        float(practice_timeline.get("gap",{}).get("duration_beats",0.0)))


func _stream_right_beats() -> float:
    return size.x*(1.0-PLAYHEAD_FRACTION)/maxf(1.0,timeline.pixels_per_beat)


func _first_source_header_spaces() -> float:
    # The actual opening's authentic Verovio glyphs are positioned by
    # ContextPainter in a compact sequence before source beat 0. Compute
    # their leftmost clef edge from its source key and font box; this same
    # conservative physical margin owns admission, clipping and retirement.
    # There is never a fake/suppressed clef or a squeezed musical beat.
    if timeline.measures.is_empty() or not glyphs.ready():
        return 15.0
    var opening: Dictionary = timeline.measures[0]
    var keys: Dictionary = opening.get("keys",{})
    var margin := 1.6
    for staff in layout.visible_staves():
        var clef: Dictionary = layout.clef_for(staff,opening)
        var sign: String = str(clef.get("sign","G"))
        var name: String = {"G":"clef_g","F":"clef_f","C":"clef_c"}.get(sign,"")
        var box: Array = glyphs.bounds.get(name,[])
        if box.size() != 4:
            return 15.0
        var key_count: int = absi(int(keys.get(staff,0)))
        # The first clef anchor and every key column use the same physical
        # header spacing rule as ContextPainter's actual glyph placement.
        # paint_clef() is centered in X, so the raster's left edge is
        # another half glyph width left. A full extra space covers the
        # thin barline, antialias and raster/viewport tolerances.
        margin = maxf(margin,ContextPainter.clef_lead_pixels(key_count,1.0)+
            float(box[2])/500.0+1.0)
    return margin


func _stream_header_beats(opening: float) -> float:
    return (_first_source_header_spaces() if opening <= .0001 else 1.6)* \
        staff_gap()/maxf(1.0,timeline.pixels_per_beat)


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
    var entry_beats: float = float(reserved["start_world"])-opening+ \
        StreamAdmission.clip_bounds({
            "kind":"source","source_floor":opening,
            "source_ceiling":timeline.duration_beats,
            "clip_floor":opening,
            "clip_ceiling":timeline.duration_beats,
            "clip_leading_spaces":_first_source_header_spaces() if opening <= .0001 else 1.6
        },timeline.pixels_per_beat,staff_gap(),
            timeline.duration_beats).x/maxf(1.0,timeline.pixels_per_beat) - \
        stream_world_beat-_stream_right_beats()
    var entry_seconds: float = StreamAdmission.lead_seconds(entry_beats,0.0,bpm)
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
    return StreamAdmissionExecutor.reserve_action(
        self,action,world,opening,count_in_beats)


func earliest_continuation_world(world: float, opening: float,
        count_in_beats: float = 0.0) -> float:
    # Pure: the earliest world position where an automatic continuation's
    # source can still be admitted once every unseen strip is withdrawn
    # (exposed ink stays): offscreen, or on an empty strip one count-in bar
    # ahead (P5). Resume in a rest sends this as its lead so the engine
    # re-announces a deadline that fits.
    if not native_ready or not retained_ready():
        return NAN
    world = maxf(world,stream_world_beat)
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var preview: Dictionary = _stream_queue.preview_tail_withdrawal(
        world,density,staff_gap(),timeline.duration_beats,size.x,
        size.x*PLAYHEAD_FRACTION)
    var header: float = _stream_header_beats(opening)
    var start: float = StreamAdmission.position(preview["remaining"],world,
        _stream_right_beats(),header,NAN,0.0,density,staff_gap(),
        timeline.duration_beats)
    var peer: float = _stream_queue.minimum_peer_opening(
        density,size.x,size.x*PLAYHEAD_FRACTION)
    if is_finite(peer):
        start = maxf(start,peer+header)
    if count_in_beats > 0.0:
        var empty: float = _empty_strip_onset(
            preview["remaining"],world,count_in_beats,header)
        if is_finite(empty) and (not is_finite(start) or empty < start):
            start = empty
    return start


func _empty_strip_onset(passes: Array, world: float, count_in_beats: float,
        header: float) -> float:
    # The one empty-strip slot (StreamAdmission.empty_strip_start): live
    # peer SOURCE ink blocks it; a peer's written rest bar only moves the
    # opening past that rest, by the same pop-in rule (owner, round 4).
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var playhead: float = size.x*PLAYHEAD_FRACTION
    return StreamAdmission.empty_strip_start(passes,world,count_in_beats,
        header,_stream_queue.minimum_peer_opening(density,size.x,playhead,
            true,"source"),density,staff_gap(),timeline.duration_beats,
        _stream_queue.minimum_peer_opening(density,size.x,playhead,true,"rest"))


func short_rest_geometry() -> Dictionary:
    # What the engine needs to time the take after a written rest bar
    # (owner, round 4): clear = that rest bar (it starts at the take's last
    # source beat) plus the pop-in margin a peer layer keeps from it;
    # header = the next opening's header plus a frame margin. The next
    # source opens straight after the rest (empty_strip_start).
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    # The timeline's gap is always one full measure (practice_timeline
    # raises otherwise). Its source strip's final barline margin can reach
    # past it when the last window ends in a short measure: then that margin
    # plus the usual rest gap is what the next opening must clear.
    var rest: float = float(practice_timeline.get("gap",{}).get(
        "duration_beats",0.0))
    var trailing: float = 2.2*staff_gap()/density
    var after: float = rest if rest >= trailing else \
        trailing+StreamAdmission.REST_GAP_BEATS
    # A complete rest already separates the score copies. Its final barline
    # needs only the small raster clearance used by live peer admission.
    # A source whose final glyph extends beyond the rest retains 60 px.
    var margin: float = (StreamQueue.PEER_REST_MARGIN_PX if rest >= trailing
        else StreamQueue.PEER_MARGIN_PX)
    return {"continuation_clear_beats":
            after+margin/density+
            StreamAdmission.OFFSCREEN_MARGIN_BEATS,
        "continuation_header_beats":
            _stream_header_beats(0.0)+StreamAdmission.OFFSCREEN_MARGIN_BEATS}


func announced_copy_onset(world: float) -> float:
    # The world onset of the most recently announced continuation's
    # admitted, still unbound copy if it is still ahead of the playhead (a
    # Resume in the rest reuses it, like a paused take); otherwise NAN.
    var newest := -1
    for owner_serial in _scheduled_score_plan_ids.values():
        newest = maxi(newest,int(owner_serial))
    for item in _stream_queue.online:
        if str(item.get("kind","")) == "source" and \
                int(item.get("take_owner",-1)) == newest and \
                str(item.get("take_key","")) == "autopending":
            var onset: float = float(item["world_origin"])+ \
                float(item.get("source_floor",0.0))
            return onset if onset > maxf(world,stream_world_beat)+ \
                StreamAdmission.PAUSED_REUSE_EPSILON_BEATS else NAN
    return NAN


# Set only around reserve_transport_action's commit of a Retry slot.
var _retry_placement: bool:
    get: return _stream_controller.retry_placement
    set(value): _stream_controller.retry_placement = value

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
        if not is_finite(checked) and _retry_placement:
            # A Retry is placed by StreamAdmission.retry_start (right edge at
            # once, after exposed ink, no REST_GAP/READY travel): the commit
            # accepts exactly that slot (the preflight's own rule).
            var retry_floor: float = StreamAdmission.retry_start(
                _stream_queue.online,stream_world_beat,_stream_right_beats(),
                _stream_header_beats(opening),float(practice_timeline.get(
                    "gap",{}).get("duration_beats",0.0)),
                timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
            if planned_start_world >= retry_floor-.0001:
                checked = planned_start_world
        if not is_finite(checked) and empty_strip_count_in > 0.0:
            # The preflight chose the empty-strip count-in bar slot; the
            # live queue must still permit exactly that deadline.
            var earliest: float = _empty_strip_onset(
                _stream_queue.online,stream_world_beat,empty_strip_count_in,
                _stream_header_beats(opening))
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
    _stream_armed_segment_id = ""
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


func admission_queue_generation() -> int:
    return _stream_controller.queue_generation()

func unscored_take_status() -> String:
    return _unscored_take

func bound_segment_id() -> String:
    return _stream_controller.bound_segment()

func has_armed_reservation() -> bool:
    return _stream_controller.has_armed_reservation()


func bind_stream_segment(segment_id: String) -> bool:
    return _stream_controller.bind_segment(segment_id)


func acknowledge_stream_arm() -> bool:
    return _stream_controller.acknowledge_arm()


func cancel_stream_arm() -> bool:
    return _stream_controller.cancel_arm(self,stream_world_beat)


func trim_future_queue(reason: String,
        protected_take: int = -1) -> Array[int]:
    var removed: Array[int] = _stream_controller.trim_future(
        self,reason,stream_world_beat,timeline.pixels_per_beat,
        staff_gap(),timeline.duration_beats,size.x,
        size.x*PLAYHEAD_FRACTION,protected_take)
    if not removed.is_empty():
        queue_redraw()
    return removed


func _restore_future_suffix(saved: Array, world: float) -> bool:
    return _stream_controller.restore_future_suffix(self,saved,world)


func enqueue_recovery_queue(world: float, source_opening: float,
        graded_deadline_world: float, plan_id: String = "",
        allow_count_in: bool = false, count_in_beats: float = 0.0,
        deadline_at_or_after: bool = false, untimed: bool = false) -> bool:
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
        # The plan identity names its source opening, graded take and exact
        # backend deadline: the owner admitted for it IS that take's ink.
        # A tail withdrawal can invalidate it; then admit it again.
        if _stream_queue.has_take(int(_scheduled_score_plan_ids[identity])):
            return true
        _scheduled_score_plan_ids.erase(identity)
    # An already elapsed plan may no longer be reinserted: it would
    # introduce notes behind the real playhead.
    if graded_deadline_world <= stream_world_beat:
        _diagnose_plan(identity,"elapsed",graded_deadline_world)
        return false
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
    if untimed:
        # Untimed guided Learn grades no deadline: the learner plays each
        # note when ready. Open the passage at the first append-only slot
        # that starts offscreen, never before the engine's announcement.
        var earliest: float = StreamAdmission.position(remaining,
            stream_world_beat,_stream_right_beats(),
            _stream_header_beats(source_opening),NAN,0.0,
            timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
        checked = maxf(graded_deadline_world,earliest) if is_finite(earliest) else NAN
    elif not is_finite(checked) and allow_count_in:
        # The initial command or an already announced backend continuation
        # may use the empty-staff slot; source/rest/peer physical clearance
        # remains mandatory. Practice plans have been announced BEFORE this
        # snapshot, so a partial count-in has already elapsed. The first
        # note still has a guaranteed future reading lead and retains its
        # exact original grading deadline.
        if deadline_at_or_after:
            var density: float = maxf(1.0,timeline.pixels_per_beat)
            var playhead: float = size.x*PLAYHEAD_FRACTION
            checked = StreamAdmission.announced_empty_strip_start(
                remaining,stream_world_beat,count_in_beats,
                _stream_header_beats(source_opening),graded_deadline_world,
                _stream_queue.minimum_peer_opening(
                    density,size.x,playhead,true,"source"),
                density,staff_gap(),timeline.duration_beats,
                _stream_queue.minimum_peer_opening(
                    density,size.x,playhead,true,"rest"))
            on_empty = is_finite(checked)
        else:
            # Listen/Perform/Learn use one initial full count-in slot, with
            # the original tight timestamp-to-slot equality requirement.
            var onset: float = _empty_strip_onset(
                remaining,stream_world_beat,count_in_beats,
                _stream_header_beats(source_opening))
            if is_finite(onset) and absf(onset-graded_deadline_world) <= \
                    StreamAdmission.EMPTY_STRIP_DEADLINE_EPSILON_BEATS:
                checked = graded_deadline_world
                on_empty = true
    if not is_finite(checked):
        var blocking: Array = []
        for item in remaining:
            var bounds: Vector2 = StreamAdmission.clip_bounds(item,
                timeline.pixels_per_beat,staff_gap(),timeline.duration_beats)
            var finish: float = float(item["world_origin"])+bounds.y/ \
                maxf(1.0,timeline.pixels_per_beat)
            if finish > stream_world_beat-1.0:
                blocking.append([str(item.get("kind","source")),
                    snappedf(finish,.001)])
        var detail: Dictionary = {"count_in":count_in_beats,
            "header":_stream_header_beats(source_opening),
            "deadline_lead":graded_deadline_world-stream_world_beat,
            "ink_ends":blocking}
        var diagnostic_density: float = maxf(1.0,timeline.pixels_per_beat)
        var diagnostic_playhead: float = size.x*PLAYHEAD_FRACTION
        var peer_source: float = _stream_queue.minimum_peer_opening(
            diagnostic_density,size.x,diagnostic_playhead,true,"source")
        var peer_rest: float = _stream_queue.minimum_peer_opening(
            diagnostic_density,size.x,diagnostic_playhead,true,"rest")
        if is_finite(peer_source):
            detail["peer_source_floor"] = peer_source
        if is_finite(peer_rest):
            detail["peer_rest_floor"] = peer_rest
        _diagnose_plan(identity,"refused_inside_or_overlap",
            graded_deadline_world,detail)
        return false
    var incoming_left: float = checked - _stream_header_beats(source_opening)
    if not _stream_queue._clears_prior_layers(incoming_left,
            timeline.pixels_per_beat,size.x,size.x*PLAYHEAD_FRACTION,on_empty):
        _diagnose_plan(identity,"refused_prior_layer",graded_deadline_world)
        return false
    # COMMIT: the exact same exposure snapshot and world coordinate must
    # still hold. No yield/poll/other input runs between preview and commit.
    var saved_suffix: Array = []
    for index in range(remaining.size(),_stream_queue.online.size()):
        saved_suffix.append(_stream_queue.online[index].duplicate())
    var prior_live: int = _stream_live_serial
    trim_future_queue("recovery_replan")
    if _stream_queue.online.size() != remaining.size():
        # The archive may refuse one of several suffix withdrawals after
        # earlier owners were already removed. Restore ONLY the missing
        # original tail; re-enqueueing the still-online survivors would
        # duplicate their immutable notes and fail recovery altogether.
        var still_present: int = maxi(0,
            _stream_queue.online.size()-remaining.size())
        push_error("RECOVERY_TRANSACTION: tail withdrawal incomplete")
        _restore_future_suffix(saved_suffix.slice(still_present),
            stream_world_beat)
        _stream_live_serial = prior_live
        return false
    var before: int = _stream_serial
    _stream_add_take(source_opening,checked,source_opening,
        "autopending",on_empty)
    _stream_live_serial = prior_live
    if _stream_serial > before:
        _scheduled_score_plan_ids[identity] = _stream_last_admitted
        scheduled_plan_openings[identity] = checked
        _diagnose_plan(identity,"admitted",checked,
            {"owner":_stream_last_admitted,"on_empty_strip":on_empty})
        return true
    # If a retained segment/asset failed halfway through its measure batch,
    # eliminate that exact unexposed newly allocated owner first. Its serial
    # was not committed by _stream_add_take; the pre-existing suffix retains
    # the only authoritatively valid music at its original world positions.
    var partial_owner: int = before+1
    if _stream_queue.has_take(partial_owner):
        _stream_queue.withdraw_take_tail(self,partial_owner,
            stream_world_beat,timeline.pixels_per_beat,staff_gap(),
            timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION,
            "recovery_incomplete_append")
    if _stream_queue.has_take(partial_owner):
        push_error("RECOVERY_TRANSACTION: incomplete take cannot be rolled back")
        return false
    _restore_future_suffix(saved_suffix,stream_world_beat)
    _stream_live_serial = prior_live
    return false


func _diagnose_plan(identity: String, outcome: String, deadline_world: float,
        extra: Dictionary = {}) -> void:
    _stream_controller.diagnose_plan(
        identity,outcome,deadline_world,stream_world_beat,extra)

func present_flow(world_beat: float, state: Dictionary,
        graded_beat: float, allow_admission: bool = true) -> void:
    stream_world_beat = maxf(stream_world_beat,world_beat)
    _stream_controller.prune_expired(self,stream_world_beat,
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        timeline.duration_beats,size.x*PLAYHEAD_FRACTION)
    if not native_ready or not retained_ready():
        queue_redraw()
        return
    var phase: String = str(state.get("phase",""))
    var mode: String = str(state.get("mode","practice"))
    var opening: float = maxf(0.0,float(state.get("play_from_beat",0.0)))
    var published_timeline: Variant = state.get("playback_timeline")
    var expected_segment: String = (
        str(published_timeline.get("segment_id",""))
        if published_timeline is Dictionary else "")
    var key: String = "%s|%d|%d|%s" % [
        str(state.get("piece_fingerprint","")),
        int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),mode]
    var paused_now: bool = bool(state.get("paused",false))
    var running_now: bool = bool(state.get("running",false)) and not paused_now
    _stream_controller.observe_transport(
        self,stream_world_beat,opening,graded_beat,key,phase,
        paused_now,running_now,bool(state.get("running",false)),
        expected_segment,allow_admission)
    # Invariant: a graded or audible take that is playing has its own source
    # bound on the staff. A take without one is a defect, never a state to
    # show silently as an empty staff (practice flow, 2026-11-18).
    if running_now and phase == "playing" and mode in ["practice","perform","listen"] \
            and (expected_segment.is_empty() or \
                 _stream_live_segment_id != expected_segment):
        if _unscored_take != key:
            _unscored_take = key
            push_error("TAKE_WITHOUT_SCORE: %s (queue=%s)" % [key,
                str(state.get("score_queue_next",{}).get("plan_id","none")
                    if state.get("score_queue_next") is Dictionary else "none")])
    # Retained compilation may have finished since the previous frame.
    # Clip attachment happens here, before CanvasItem._draw() projects
    # positions. No scene-tree modification is permitted in _draw().
    StreamLifecycle.attach_compiled(_stream_queue.online)
    queue_redraw()


func _project_stream(playhead_x: float) -> void:
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var gap: float = staff_gap()
    var used: Dictionary = {}
    # The immutable online queue is chronologically ordered by printed
    # left edge; once one source/rest clip is entirely to the right of the
    # viewport, every later clip is too. Long pieces therefore do not
    # project thousands of offscreen measures on every animation frame.
    for item in _stream_queue.online:
        var bounds: Vector2 = StreamLifecycle.screen_bounds(
            item,density,gap,timeline.duration_beats)
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
                density,gap,size,timeline.duration_beats):
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
    for group in layout.visible_source_spans(
            "beams",frame.source_floor-.25,frame.source_ceiling+.25):
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
                Color(NOTE_INK,.43),SymbolPainter.STAFF_LINE_WIDTH,true)
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
                Color(ink,SymbolPainter.STAFF_LINE_ALPHA if selected else .28),
                SymbolPainter.STAFF_LINE_WIDTH,true)
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
