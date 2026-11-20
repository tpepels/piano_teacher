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
const RetainedNotationPool := preload("res://notation/native/retained_notation_pool.gd")
const RetainedNoteProjection := preload("res://notation/native/retained_note_projection.gd")
const StreamAdmission := preload("res://score_stream_admission.gd")
const AmbientMeterGeometry := preload("res://notation/native/ambient_meter_geometry.gd")
const CursorInkClearance := preload("res://notation/native/cursor_ink_clearance.gd")
const ScoreStreamWindowCuts := preload("res://score_stream_window_cuts.gd")
const NotationClipPlanner := preload("res://notation/native/notation_clip_planner.gd")
const TransportReservation := preload("res://score_transport_reservation.gd")
const StreamAdmissionExecutor := preload("res://notation/native/stream_admission_executor.gd")
const StreamLifecycle := preload("res://notation/native/stream_lifecycle.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
const ScoreStreamController := preload("res://notation/native/score_stream_controller.gd")
const SourcePassPainter := preload("res://notation/native/source_pass_painter.gd")
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
    return _stream_controller.preflight_facts(
        maxf(world,stream_world_beat),opening,
        has_source_windows_at(opening),_stream_right_beats(),
        _stream_header_beats(opening),
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION)


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
        # Public diagnostic snapshot. The authoritative offline history can
        # be changed only by ScoreStreamQueue retirement/withdrawal.
        return _stream_queue.offline.duplicate(true)
# Immutable source event index for cursor ink clearance. The painter may
# temporarily suppress one glyph for framebuffer controls; that must not
# change the fixed timing line or alter unrelated image pixels.
var _cursor_engraved_events: Array = []
# One-shot defect marker is view diagnostics, never part of stream ownership.
var _unscored_take := ""
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
var _retained_pool = RetainedNotationPool.new()
var retained_first_once:
    get: return _retained_pool.first_once
var retained_repeat_segments: Array:
    get: return _retained_pool.repeat_segments
var retained_rest_segments: Array:
    get: return _retained_pool.rest_segments
var retained_all_segments: Array:
    get: return _retained_pool.all_segments
var retained_annotations: Node2D:
    get: return _retained_pool.annotations
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
    _retained_pool.clear(self)

func _install_retained_segments() -> void:
    _clear_retained_segments()
    _resize_retained_pool(true)

func _resize_retained_pool(install: bool = false) -> void:
    var windows: Array[Vector2] = NotationClipPlanner.source_windows(
        timeline,maxf(0.0,play_from_beat),_source_ink_intervals)
    if install:
        _retained_pool.install(self,windows)
    else:
        _retained_pool.resize(self,windows)

func retained_ready() -> bool:
    return _retained_pool.ready(native_ready,size)

func retained_segment_compiled() -> void:
    if _retained_pool.mark_published(retained_ready()):
        # The score-ready signal must never re-enter layout publication
        # from inside a CanvasItem's draw notification.
        call_deferred("emit_signal","retained_ink_compiled")

func _invalidate_retained_segments() -> void:
    _retained_pool.invalidate(self,_stream_queue.online)

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

# Owner decision (round 4, 2026-11-11): a written rest bar (the practice
# timeline's gap, always one full measure) follows every take, and it IS
# the count-in bar of the next take: the next source is admitted straight
# after it (empty_strip_start) and its one count-in is spoken over the
# rest, so rest plus count-in stays short (P5).
# Each backend decision has a stable identity. Repeated state polls cannot
# enqueue another copy after the first source has already been activated
# or has passed off the left edge.
# World beat at which each admitted plan's source opening reaches the
# playhead (it can be later than the engine deadline for untimed Learn).


func has_source_windows_at(opening: float) -> bool:
    # Public immutable source-window existence query for the pure
    # transport preflight. No external component inspects private
    # clipping intervals or renderer-owned source-window caches.
    return not NotationClipPlanner.source_windows(
        timeline,opening,_source_ink_intervals).is_empty()


func append_source_take(source_beat: float, start_world: float,
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


func _transport_admission_receipt(planned: Dictionary,
        admitted: Dictionary, world: float, opening: float) -> Dictionary:
    return _stream_controller.receipt(
        planned,admitted,world,opening,
        _first_source_header_spaces() if opening <= .0001 else 1.6,
        timeline.pixels_per_beat,staff_gap(),timeline.duration_beats,
        stream_world_beat,_stream_right_beats(),bpm)


func reserve_transport_action(action: String, world: float,
        opening: float, count_in_beats: float) -> Dictionary:
    return StreamAdmissionExecutor.reserve_action(
        self,action,world,opening,count_in_beats)


func earliest_continuation_world(world: float, opening: float,
        count_in_beats: float = 0.0) -> float:
    if not native_ready or not retained_ready():
        return NAN
    return _stream_controller.earliest_continuation(
        maxf(world,stream_world_beat),count_in_beats,
        _stream_right_beats(),_stream_header_beats(opening),
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION)


func empty_strip_onset(passes: Array, world: float, count_in_beats: float,
        header: float) -> float:
    return _stream_controller.empty_strip_onset(
        passes,world,count_in_beats,header,
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION)


func short_rest_geometry() -> Dictionary:
    return _stream_controller.rest_geometry(
        float(practice_timeline.get("gap",{}).get("duration_beats",0.0)),
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        _stream_header_beats(0.0))


func announced_copy_onset(world: float) -> float:
    return _stream_controller.announced_copy_onset(
        maxf(world,stream_world_beat))


func arm_stream_take(world: float, opening: float,
        planned_start_world: float = NAN,
        resuming_paused: bool = false, retrying: bool = false,
        empty_strip_count_in: float = 0.0) -> Dictionary:
    return _stream_controller.arm_take(self,world,opening,
        _stream_right_beats(),_stream_header_beats(opening),
        planned_start_world,resuming_paused,retrying,empty_strip_count_in)


func stream_owner_status() -> Dictionary:
    # Stable diagnostic snapshot; no external component may mutate the
    # live serial, armed state or queue through renderer properties.
    return _stream_controller.owner_status()


func stream_has_take(owner_serial: int) -> bool:
    return _stream_controller.has_take(owner_serial)


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
    return _stream_controller.schedule_recovery(
        self,world,source_opening,graded_deadline_world,
        _stream_right_beats(),_stream_header_beats(source_opening),
        plan_id,allow_count_in,count_in_beats,deadline_at_or_after,untimed)


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
                 _stream_controller.live_segment_id != expected_segment):
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
    return CursorInkClearance.exclusions(
        stream_world_beat,gap,maxf(1.0,timeline.pixels_per_beat),
        _cursor_engraved_events,_stream_controller.online_snapshot(),
        layout,active_hand)


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
        var barline_top_y: float = layout.barline_top(gap)
        var barline_bottom_y: float = layout.barline_bottom(gap)
        var exposed: Dictionary = AmbientMeterGeometry.exposed_lines(
            stream_world_beat,size.x,playhead_x,density,gap,
            timeline.duration_beats,timeline.measures,_ambient_anchor_world,
            _stream_controller.online_snapshot())
        _ambient_anchor_world = float(exposed["anchor"])
        for x in exposed["positions"]:
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
