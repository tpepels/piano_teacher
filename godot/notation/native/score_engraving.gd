extends RefCounted
## Owns one revision's authentic engraving assets, source geometry and fit.
## No transport, stream ledger or scene-tree state is retained here.
const Geometry := preload("res://notation/native/geometry.gd")
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
const EngravingReadiness := preload("res://notation/native/engraving_readiness.gd")
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
const ViewportFit := preload("res://notation/native/viewport_fit.gd")
const ScoreLayout := preload("res://notation/native/score_layout.gd")
const InkGeometry := preload("res://notation/native/ink_geometry.gd")
const ConnectorGeometry := preload("res://notation/native/connector_geometry.gd")
const FingeringAnnotations := preload("res://notation/native/fingering_annotations.gd")
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")
const ContextPainter := preload("res://notation/native/context_painter.gd")
const NotationClipPlanner := preload("res://notation/native/notation_clip_planner.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")
const MAX_STAFF_GAP := ViewportFit.MAX_STAFF_GAP
var timeline
var glyphs = VerovioGlyphs.new():
    set(value):
        glyphs = value
        if layout != null:
            layout.glyphs = value
var layout:
    set(value):
        layout = value
        if ink_geometry != null:
            ink_geometry.score = value
            ink_geometry.clear_cache()
            connector_geometry.score = value
            connector_geometry.clear_cache()
            annotations.score_layout = value
            annotations.obstacles.score_layout = value
            annotations.clear()
            symbols.score_layout = value
            context_painter.score_layout = value
var ink_geometry
var connector_geometry
var annotations
var symbols
var context_painter
var staff_gap_limit := MAX_STAFF_GAP
var selected_density := 0.0
var ink_density_witness: Dictionary = {}
var selected_density_witness: Dictionary = {}
var expected_slur_pairs: Array = []
var slur_extraction_complete := true
var expected_beam_groups: Array = []
var beam_extraction_complete := true
var source_ink_intervals: Array[Vector2] = []
var cursor_engraved_events: Array = []
var failure_reason := ""
var incomplete_assets := false
var _committed_gap := 0.0

func _init(axis) -> void:
    timeline = axis
    layout = ScoreLayout.new(axis,glyphs)
    ink_geometry = InkGeometry.new(layout)
    connector_geometry = ConnectorGeometry.new(layout)
    annotations = FingeringAnnotations.new(layout,connector_geometry)
    symbols = SymbolPainter.new(layout,connector_geometry)
    context_painter = ContextPainter.new(layout,symbols)

func clear(axis) -> void:
    timeline = axis
    layout.timeline = axis
    annotations.clear()
    cursor_engraved_events.clear()
    source_ink_intervals.clear()
    staff_gap_limit = MAX_STAFF_GAP
    _committed_gap = 0.0
    failure_reason = ""
    layout.clear()

func set_viewport(viewport: Vector2) -> void:
    layout.set_viewport(viewport)

func gap() -> float:
    return _committed_gap if _committed_gap > 0.0 else layout.staff_gap(staff_gap_limit)

func preserve_spacing() -> void:
    # Horizontal glyph offsets and safe crop edges belong to this source
    # revision once exposed. A taller/shorter viewport may move staff centres
    # vertically but cannot change these printed widths under the ledger.
    if _committed_gap <= 0.0:
        _committed_gap = gap()

func load_assets(items: Dictionary, note_items: Dictionary = {},
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

func missing_engraving() -> String:
    return EngravingReadiness.missing(
        layout, glyphs, connector_geometry, expected_beam_groups,
        beam_extraction_complete, expected_slur_pairs,
        slur_extraction_complete)

func prepare_geometry() -> void:
    var prepared_gap: float = gap()
    layout.cached_head_offsets = layout.engraved_head_offsets(prepared_gap)
    layout.cached_accidental_offsets = Geometry.accidental_offsets(
        layout.ordered_events, prepared_gap, layout.cached_head_offsets,
        glyphs.bounds)
    layout.cached_offsets_gap = prepared_gap
    layout.prepare_event_positions(prepared_gap)
    cursor_engraved_events = layout.ordered_events.duplicate(true)
    connector_geometry.clear_cache()
    connector_geometry.prewarm_tie_clearances(prepared_gap)
    connector_geometry.prewarm_beam_layout(prepared_gap,layout.cached_head_offsets)
    connector_geometry.prewarm_slur_geometry(prepared_gap)
    if _committed_gap <= 0.0:
        source_ink_intervals = NotationClipPlanner.ink_safe_boundaries(
            layout,timeline,prepared_gap)

func first_header_spaces() -> float:
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

func prepare(configured_density: float, viewport: Vector2,
        playhead_fraction: float) -> bool:
    incomplete_assets = false
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
        return false
    var density: float = configured_density
    if not timeline.set_score_density(density):
        failure_reason = timeline.last_error
        return false
    selected_density = density
    layout.set_viewport(viewport)
    layout.rebuild_index()
    layout.set_focused_staff("")
    failure_reason = missing_engraving()
    if not failure_reason.is_empty():
        incomplete_assets = true
        return false
    # Genuine adjacent 32nd-triplet notes before a printed accidental can
    # force very wide beat spacing. A full 22px staff previously won the
    # first-feasible test even when only ~1.4 future beats fit on-screen.
    # Evaluate smaller *authentic* Verovio glyph scales before choosing;
    # use the largest staff that preserves reading context. Crucially each
    # candidate recomputes true ink collision clearance; never just cap BPM
    # distance or hide/shift a source accidental.
    var fitted: Dictionary = ViewportFit.choose(layout,ink_geometry,density,playhead_fraction)
    if not fitted["ok"]:
        failure_reason = fitted["error"]
        return false
    var ink_density: float = fitted["density"]
    staff_gap_limit = fitted["staff_gap"]
    selected_density_witness = fitted["witness"]
    ink_density_witness = fitted["last_witness"]
    if not timeline.set_score_density(ink_density):
        failure_reason = timeline.last_error
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
            "lookahead_beats":viewport.x*(1.0-playhead_fraction)/ink_density,
            "density_witness":selected_density_witness
        }))
    layout.cached_staff_gap = -1.0
    layout.cached_gap_height = -1.0
    layout.cached_offsets_gap = -1.0
    layout.cached_head_offsets.clear()
    layout.cached_accidental_offsets.clear()
    # No source connector or chord geometry may first be prepared when its
    # measure scrolls into view. All immutable structures use source-space X.
    prepare_geometry()
    failure_reason = ""
    return true

func source_windows(opening: float) -> Array[Vector2]:
    return NotationClipPlanner.source_windows(timeline,opening,source_ink_intervals)

func new_frame(clock: float, playhead_x: float, gap_value: float,
        play_from_beat: float, active_hand: String,
        pass_index: int = 0, pass_start: float = 0.0) -> RenderPass:
    return RenderPass.new({"clock":clock,"playhead_x":playhead_x,"gap":gap_value,
        "play_from_beat":play_from_beat,"active_hand":active_hand,
        "focused_staff":layout.focused_staff,"pass_index":pass_index,
        "pass_start":pass_start,"visual_scroll_beat":0.0})

func beam_plan(frame: RenderPass, head_offsets: Dictionary = {}) -> Dictionary:
    var groups: Array = []
    for group in layout.visible_source_spans(
            "beams",frame.source_floor-.25,frame.source_ceiling+.25):
        if group.size() >= 2 and frame.span_visible(group[0],group[-1]):
            groups.append(group)
    return symbols.beam_layout(frame,head_offsets,groups)
