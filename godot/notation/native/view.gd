extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation is rejected; production reports a preparation error.
const Geometry := preload("res://notation/native/geometry.gd")
const ViewportFit := preload("res://notation/native/viewport_fit.gd")
const MAX_STAFF_GAP := ViewportFit.MAX_STAFF_GAP
# A piano learner needs upcoming notation in view. Preserve the largest
# authentic staff that leaves at least this many beats to the right of the
# fixed playhead. No temporal warping, font imitation or overlap is allowed.

signal fingering_change_requested(source_id: String, finger: Variant)
signal retained_ink_compiled

# Annotation cells live on the same immutable score axis as the note ink.
# Cache once per score/vertical size; scrolling only translates their X.
var transport_overlay_enabled: bool:
    get: return painter.transport_overlay_enabled
    set(value): painter.transport_overlay_enabled = value
var runway_overlay: bool:
    get: return painter.runway_overlay
    set(value): painter.runway_overlay = value
var runway_origin_beat := 0.0
var runway_cutoff_beat := INF
var fingering_pass_clocks: Array:
    get: return painter.fingering_pass_clocks

func set_transport_overlay_enabled(enabled: bool) -> void:
    transport_overlay_enabled = enabled
    queue_redraw()

func set_fingering_annotations_enabled(enabled: bool) -> void:
    annotations.set_enabled(enabled)
    queue_redraw()

const ScoreEngraving := preload("res://notation/native/score_engraving.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")
const StreamAdmissionExecutor := preload("res://notation/native/stream_admission_executor.gd")
const ScoreStreamController := preload("res://notation/native/score_stream_controller.gd")
const RetainedNotationPool := preload("res://notation/native/retained_notation_pool.gd")
var engraving = ScoreEngraving.new(timeline)
const ScorePainter := preload("res://notation/native/score_painter.gd")
var painter = ScorePainter.new(engraving)
var glyphs:
    get: return engraving.glyphs
    set(value): engraving.glyphs = value
var layout:
    get: return engraving.layout
    set(value): engraving.layout = value
var ink_geometry:
    get: return engraving.ink_geometry
var connector_geometry:
    get: return engraving.connector_geometry
var annotations:
    get: return engraving.annotations
var symbols:
    get: return engraving.symbols
var context_painter:
    get: return engraving.context_painter

var native_ready := false
var failure_reason := ""
var visible_symbols: int:
    get: return painter.visible_symbols
var drawn_noteheads: Dictionary:
    get: return painter.drawn_noteheads
var drawn_note_instances: Array:
    get: return painter.drawn_note_instances
# Read-only view of the note-status ledger (NativeScoreFeedback). Each source
# strip paints its own status ink from it; the renderer never grades.
var note_status_source:
    get: return painter.note_status_source
    set(value): painter.note_status_source = value
var note_status_visible: bool:
    get: return painter.note_status_visible
    set(value): painter.note_status_visible = value
var selected_density: float:
    get: return engraving.selected_density
var external_backdrop: bool:
    get: return painter.external_backdrop
    set(value): painter.external_backdrop = value
var compact_inactive_staff := false
# One infinite front-of-house camera. Grading never reads this axis.
var stream_world_beat := 0.0
var _stream_controller = ScoreStreamController.new()

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
    var facts: Dictionary = _stream_controller.preflight_facts(
        maxf(world,stream_world_beat),opening,
        has_source_windows_at(opening),_stream_right_beats(),
        _stream_header_beats(opening),
        maxf(1.0,timeline.pixels_per_beat),staff_gap(),
        timeline.duration_beats,size.x,size.x*PLAYHEAD_FRACTION)
    facts.merge({"ready":native_ready and retained_ready(),
        "duration":timeline.duration_beats,"density":timeline.pixels_per_beat,
        "gap":staff_gap(),"width":size.x,"playhead":size.x*PLAYHEAD_FRACTION,
        "rest_gap":float(practice_timeline.get("gap",{}).get("duration_beats",0.0)),
        "bpm":bpm})
    return facts

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

# Public diagnostics are snapshots; the controller retains the live FIFO.
var stream_passes: Array:
    get:
        # Diagnostics/test snapshot only. No rendering or per-frame path may
        # read this: it copies the whole online queue.
        return _stream_controller.online_snapshot()

func stream_pass_count() -> int:
    return _stream_controller.online_size()

## Take keys of every source strip in the online queue, without copying it.
func visible_take_keys() -> Array:
    return _stream_controller.visible_take_keys()

func first_strip_origin_after(from_world: float) -> float:
    return _stream_controller.first_strip_origin_after(from_world)

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
        return _stream_controller.offline_snapshot()
# Immutable source event index for cursor ink clearance. The painter may
# temporarily suppress one glyph for framebuffer controls; that must not
# change the fixed timing line or alter unrelated image pixels.

# Pure presentation clock for empty idle/paused staves. Never fed into
# MIDI grading, transport projection or recorded source events.

var configured_density: float = Timeline.DEFAULT_PIXELS_PER_BEAT
var staff_gap_limit: float:
    get: return engraving.staff_gap_limit
var ink_density_witness: Dictionary:
    get: return engraving.ink_density_witness
var selected_density_witness: Dictionary:
    get: return engraving.selected_density_witness
var expected_slur_pairs: Array:
    get: return engraving.expected_slur_pairs
var slur_extraction_complete: bool:
    get: return engraving.slur_extraction_complete
var expected_beam_groups: Array:
    get: return engraving.expected_beam_groups
var beam_extraction_complete: bool:
    get: return engraving.beam_extraction_complete
# Per-rest displacements measured in staff spaces; fixed for one score revision.
var frame_scanned_events: int:
    get: return painter.frame_scanned_events
    set(value): painter.frame_scanned_events = value
var frame_visible_beam_groups: int:
    get: return painter.frame_visible_beam_groups
    set(value): painter.frame_visible_beam_groups = value
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
    _stream_controller.bind_surface(self,_retained_pool,engraving.source_windows)
    _retained_pool.bind_painter(painter,retained_segment_compiled)
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

func clear_score() -> bool:
    if not _clear_retained_segments():
        return false
    runway_origin_beat = 0.0
    runway_cutoff_beat = INF
    runway_overlay = false
    annotations.clear()
    super.clear_score()
    engraving.clear(timeline)
    timeline.set_density(configured_density)
    native_ready = false
    failure_reason = ""
    return true

func set_density(value: float) -> bool:
    # A pre-engraved READY strip can be admitted while transport is idle.
    # The base view's transport-only density lock does not cover that state.
    # Reflowing an already admitted source would silently mutate its printed
    # coordinates and invalidate the queue's density/clearance assertions.
    # A new density may take effect only before ANY strip is committed,
    # including a still-hidden READY source or a written rest.
    if not (_stream_controller.online_size() == 0):
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
    if not _clear_retained_segments():
        return false
    native_ready = false
    var ok: bool = engraving.load_assets(items,note_items,tie_items,chord_items,
        beam_items,tuplet_items,slur_items,required_slurs,slurs_complete,
        required_beams,beams_complete)
    failure_reason = engraving.failure_reason
    return ok

func load_score(candidate: Dictionary) -> bool:
    if not _clear_retained_segments():
        return false
    connector_geometry.clear_cache()
    annotations.clear()
    drawn_note_instances.clear()
    native_ready = false
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
    if not _stream_controller.bind_source(candidate):
        failure_reason = "Cannot recover offline score material: " + \
            _stream_controller.source_identity_error()
        notice = failure_reason
        return false
    if not engraving.prepare(configured_density,size,active_hand,
            compact_inactive_staff,PLAYHEAD_FRACTION):
        failure_reason = engraving.failure_reason
        notice = failure_reason
        return false
    failure_reason = ""
    if not _install_retained_segments():
        return false
    native_ready = true
    queue_redraw()
    return true

# No provider-specific state reaches this view. Invalid and genuinely unknown
# assignments produce no number; the source attack remains editable.
func _open_fingering_editor(point: Vector2) -> bool:
    return annotations.open_editor(self,point,staff_gap(),drawn_note_instances)

func _gui_input(event: InputEvent) -> void:
    if native_ready:
        annotations.handle_input(self,event,staff_gap(),drawn_note_instances)

func staff_gap() -> float:
    engraving.set_viewport(size)
    return engraving.gap()

func _prepare_static_geometry() -> void:
    engraving.set_viewport(size)
    engraving.prepare_geometry()

func _stream_release_all() -> bool:
    return _stream_controller.reset()

func _clear_retained_segments() -> bool:
    if not _stream_release_all():
        failure_reason = "Cannot preserve score ink: " +             _stream_controller.source_identity_error()
        notice = failure_reason
        queue_redraw()
        return false
    _retained_pool.clear(self)
    return true

func _install_retained_segments() -> bool:
    if not _clear_retained_segments():
        return false
    _resize_retained_pool(true)
    return true

func _resize_retained_pool(install: bool = false) -> void:
    var windows: Array[Vector2] = engraving.source_windows(maxf(0.0,play_from_beat))
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
    _stream_controller.invalidate_retained()

func paint_retained_source(canvas: CanvasItem) -> RenderPass:
    _sync_painter()
    return painter.paint_retained_source(canvas)

func paint_retained_rest(canvas: CanvasItem) -> void:
    _sync_painter()
    painter.paint_retained_rest(canvas)

func paint_retained_annotations(canvas: CanvasItem) -> void:
    _sync_painter()
    painter.paint_retained_annotations(canvas)

func has_source_windows_at(opening: float) -> bool:
    return not engraving.source_windows(opening).is_empty()

func append_source_take(source_beat: float, start_world: float,
        from_beat: float, take_key: String, empty_strip: bool = false) -> void:
    # Score preparation stays in the renderer. The authoritative queue
    # transaction and take serial assignment belong to the stream controller.
    var windows: Array[Vector2] = engraving.source_windows(maxf(0.0,from_beat))
    _stream_controller.append_take(_stream_facts(stream_world_beat),windows,source_beat,start_world,
        take_key,empty_strip,_first_source_header_spaces(),
        float(practice_timeline.get("gap",{}).get("duration_beats",0.0)))

func _stream_right_beats() -> float:
    return size.x*(1.0-PLAYHEAD_FRACTION)/maxf(1.0,timeline.pixels_per_beat)

func _first_source_header_spaces() -> float:
    return engraving.first_header_spaces()

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
    stream_world_beat = maxf(stream_world_beat,world)
    return StreamAdmissionExecutor.reserve_action(_stream_controller,
        _stream_facts(stream_world_beat),transport_preflight_facts(world,opening),
        action,world,opening,count_in_beats,_stream_right_beats(),
        _stream_header_beats(opening),bpm)

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

func arm_stream_take(world: float, opening: float,
        planned_start_world: float = NAN,
        resuming_paused: bool = false, retrying: bool = false,
        empty_strip_count_in: float = 0.0) -> Dictionary:
    stream_world_beat = maxf(stream_world_beat,world)
    return _stream_controller.arm_take(_stream_facts(maxf(world,stream_world_beat)),world,opening,
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
    return _stream_controller.unscored_take_status()

func bound_segment_id() -> String:
    return _stream_controller.bound_segment()

func has_armed_reservation() -> bool:
    return _stream_controller.has_armed_reservation()

func bind_stream_segment(segment_id: String) -> bool:
    return _stream_controller.bind_segment(segment_id)

func acknowledge_stream_arm() -> bool:
    return _stream_controller.acknowledge_arm()

func cancel_stream_arm() -> bool:
    return _stream_controller.cancel_arm(_stream_facts(stream_world_beat),stream_world_beat)

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
    return _stream_controller.restore_future_suffix(_stream_facts(world),saved,world)

func enqueue_recovery_queue(world: float, source_opening: float,
        graded_deadline_world: float, plan_id: String = "",
        allow_count_in: bool = false, count_in_beats: float = 0.0,
        deadline_at_or_after: bool = false, untimed: bool = false) -> bool:
    stream_world_beat = maxf(stream_world_beat,world)
    return _stream_controller.schedule_recovery(
        _stream_facts(maxf(world,stream_world_beat)),world,source_opening,graded_deadline_world,
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
    _stream_controller.observe_state(_stream_facts(stream_world_beat),
        state,graded_beat,allow_admission)
    # Retained compilation may have finished since the previous frame.
    # Clip attachment happens here, before CanvasItem._draw() projects
    # positions. No scene-tree modification is permitted in _draw().
    _stream_controller.attach_compiled()
    queue_redraw()

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
    var focus_changed: bool = layout.set_focused_staff(engraving.focused_staff(active_hand,compact_inactive_staff))
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
    var result: Dictionary = engraving.beam_plan(frame,head_offsets)
    frame_visible_beam_groups = frame.visible_beam_groups
    return result

func playhead_region() -> Rect2:
    _sync_painter()
    return painter.playhead_region()

func _draw() -> void:
    _sync_painter()
    _stream_controller.paint(painter,self,_retained_pool)

func _sync_painter() -> void:
    painter.update(size,play_from_beat,active_hand,clock_beat,
        stream_world_beat,bpm,running,paused,native_ready,practice_timeline)

func _new_paint_frame(clock: float, playhead_x: float, gap: float,
        pass_index: int, pass_start: float) -> RenderPass:
    engraving.set_viewport(size)
    return engraving.new_frame(clock,playhead_x,gap,play_from_beat,
        active_hand,pass_index,pass_start)

const StreamGeometry := preload("res://notation/native/stream_geometry.gd")
func _stream_facts(world: float):
    return StreamGeometry.new(native_ready and retained_ready(),world,
        timeline.pixels_per_beat,staff_gap(),timeline.duration_beats,
        size.x,size.x*PLAYHEAD_FRACTION,
        float(practice_timeline.get("gap",{}).get("duration_beats",0.0)),
        engraving.first_header_spaces())

## Exact admitted world position of a coordinator-authored guided target.
func scheduled_plan_opening(identity: String) -> float:
    return _stream_controller.scheduled_plan_opening(identity)
