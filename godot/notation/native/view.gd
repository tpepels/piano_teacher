extends "res://notation/shared/view_base.gd"
# Native Godot compositor for authentic individually extracted Verovio glyphs.
# The score's continuous time axis, staff geometry, ledger rules, stems, beams
# and ties are native Godot primitives. Musical glyph CONTOURS come ONLY from
# the installed Verovio font, cached as individual Godot ImageTextures.
# There is no full-page SVG bitmap or custom imitation of a music glyph.
# Incomplete notation is rejected; production reports a preparation error.
const Geometry := preload("res://notation/native/geometry.gd")
const ScoreIndex := preload("res://notation/native/score_index.gd")
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
const VoiceLayout := preload("res://notation/native/voice_layout.gd")
const RestLaneLayout := preload("res://notation/native/rest_lane_layout.gd")
const BarlineLayout := preload("res://notation/native/barline_layout.gd")
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
var fingering_layout: Array:
    get: return annotations.fingering_layout
    set(value): annotations.fingering_layout = value
var drawn_fingerings: Array:
    get: return annotations.drawn_fingerings
    set(value): annotations.drawn_fingerings = value
var fingering_layout_gap: float:
    get: return annotations.fingering_layout_gap
    set(value): annotations.fingering_layout_gap = value
var fingering_layout_height: float:
    get: return annotations.fingering_layout_height
    set(value): annotations.fingering_layout_height = value
var fingering_popup: PopupMenu:
    get: return annotations.fingering_popup
    set(value): annotations.fingering_popup = value
var fingering_annotations_enabled: bool:
    get: return annotations.fingering_annotations_enabled
    set(value): annotations.fingering_annotations_enabled = value
var fingering_placement_issues: Array:
    get: return annotations.fingering_placement_issues
    set(value): annotations.fingering_placement_issues = value
var fingering_metrics_cache: Dictionary:
    get: return annotations.fingering_metrics_cache
    set(value): annotations.fingering_metrics_cache = value
var fingering_staff_lines: Array:
    get: return annotations.obstacles.staff_lines
    set(value): annotations.obstacles.staff_lines = value
var fingering_sprite_envelopes: Dictionary:
    get: return annotations.obstacles.sprite_envelopes
    set(value): annotations.obstacles.sprite_envelopes = value
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
var annotations = FingeringAnnotations.new(layout,connector_geometry)
const RenderPass := preload("res://notation/native/render_pass.gd")
const SymbolPainter := preload("res://notation/native/symbol_painter.gd")
const ContextPainter := preload("res://notation/native/context_painter.gd")
var symbols = SymbolPainter.new(layout,connector_geometry)
var context_painter = ContextPainter.new(layout,symbols)
var painting_pass: RenderPass

var native_ready := false
var failure_reason := ""
var visible_symbols := 0
var drawn_noteheads: Dictionary = {}
var pass_noteheads: Dictionary = {}
var drawn_note_instances: Array = []
var preparation_history: Dictionary = {}
var current_preparation: Dictionary = {}
var paint_pass_index := 0
var paint_pass_start := 0.0
var selected_density := 0.0
var staff_gap_limit := MAX_STAFF_GAP
var configured_density: float = Timeline.DEFAULT_PIXELS_PER_BEAT
var beam_groups: Array:
    get: return layout.beam_groups
    set(value): layout.beam_groups = value
var beamed_note_ids: Dictionary:
    get: return layout.beamed_note_ids
    set(value): layout.beamed_note_ids = value
var beam_stem_up_by_note: Dictionary:
    get: return layout.beam_stem_up_by_note
    set(value): layout.beam_stem_up_by_note = value
var voice_stem_up_by_note: Dictionary:
    get: return layout.voice_stem_up_by_note
    set(value): layout.voice_stem_up_by_note = value
var chord_members: Dictionary:
    get: return layout.chord_members
    set(value): layout.chord_members = value
var notation_tuplets: Array:
    get: return layout.notation_tuplets
    set(value): layout.notation_tuplets = value
# Immutable musical structure is indexed ONCE when a passage changes.
# Each frame then visits only visible onsets, beams and ties.
var measure_by_number: Dictionary:
    get: return layout.measure_by_number
    set(value): layout.measure_by_number = value
var ordered_events: Array:
    get: return layout.ordered_events
    set(value): layout.ordered_events = value
var ink_density_witness: Dictionary = {}
var selected_density_witness: Dictionary = {}
var attached_grace_notes: Array:
    get: return layout.attached_grace_notes
    set(value): layout.attached_grace_notes = value
var source_expressions: Array:
    get: return layout.source_expressions
    set(value): layout.source_expressions = value
var expression_note_index: Dictionary:
    get: return layout.expression_note_index
    set(value): layout.expression_note_index = value
var tie_pairs: Array:
    get: return layout.tie_pairs
    set(value): layout.tie_pairs = value
var slur_pairs: Array:
    get: return layout.slur_pairs
    set(value): layout.slur_pairs = value
var expected_slur_pairs: Array = []
var slur_extraction_complete := true
var expected_beam_groups: Array = []
var beam_extraction_complete := true
var previous_attack_before_measure: Dictionary:
    get: return layout.previous_attack_before_measure
    set(value): layout.previous_attack_before_measure = value
var cached_staff_gap: float:
    get: return layout.cached_staff_gap
    set(value): layout.cached_staff_gap = value
var cached_gap_height: float:
    get: return layout.cached_gap_height
    set(value): layout.cached_gap_height = value
var cached_head_offsets: Dictionary:
    get: return layout.cached_head_offsets
    set(value): layout.cached_head_offsets = value
var cached_accidental_offsets: Dictionary:
    get: return layout.cached_accidental_offsets
    set(value): layout.cached_accidental_offsets = value
# Per-rest displacements measured in staff spaces; fixed for one score revision.
var rest_lane_offsets: Dictionary:
    get: return layout.rest_lane_offsets
    set(value): layout.rest_lane_offsets = value
var unavoidable_rest_overlaps: int:
    get: return layout.unavoidable_rest_overlaps
    set(value): layout.unavoidable_rest_overlaps = value
var cached_offsets_gap: float:
    get: return layout.cached_offsets_gap
    set(value): layout.cached_offsets_gap = value
var frame_scanned_events := 0
var frame_visible_beam_groups := 0

func _init() -> void:
    resized.connect(func(): layout.set_viewport(size))
    annotations.fingering_change_requested.connect(func(source_id, finger):
        fingering_change_requested.emit(source_id,finger))
    mouse_filter = Control.MOUSE_FILTER_PASS
    tooltip_text = "Right-click a note or tap a finger number to change its fingering"


func _reset_fingering() -> void:
    annotations.clear()

func clear_score() -> void:
    _reset_fingering()
    super.clear_score()
    layout.timeline = timeline
    timeline.set_density(configured_density)
    staff_gap_limit = MAX_STAFF_GAP
    native_ready = false
    failure_reason = ""
    layout.clear()


func set_density(value: float) -> bool:
    if not super.set_density(value):
        return false
    configured_density = value
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
    _reset_fingering()
    preparation_history.clear()
    current_preparation.clear()
    pass_noteheads.clear()
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
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_offsets_gap = -1.0
    cached_head_offsets.clear()
    cached_accidental_offsets.clear()
    failure_reason = ""
    native_ready = true
    queue_redraw()
    return true

# No provider-specific state reaches this view. Invalid and genuinely unknown
# assignments produce no number; the source attack remains editable.
func _fingering_assignment(event: Dictionary) -> Dictionary:
    return FingeringPlacement.assignment(event)

func _fingering_source(event: Dictionary) -> String:
    return FingeringPlacement.source(event)

func _fingering_block(rect: Rect2, bins: Dictionary, cell: float) -> void:
    annotations.obstacles.block(rect,bins,cell)

func _fingering_clear(rect: Rect2, bins: Dictionary, cell: float) -> bool:
    return annotations.obstacles.is_clear(rect,bins,cell)

func _fingering_obstacles(gap: float, bins: Dictionary, cell: float) -> void:
    annotations.obstacles.build(gap,bins,cell,play_from_beat)

func _fingering_event_obstacles(event: Dictionary, gap: float, bins: Dictionary, cell: float) -> void:
    annotations.obstacles.event_obstacles(event,gap,bins,cell)

func _fingering_nonhead_envelope(kind: String, up: bool, chord_key: String = "") -> Rect2:
    return annotations.obstacles.nonhead_envelope(kind,up,chord_key)

func _layout_fingerings(gap: float) -> void:
    layout.set_viewport(size)
    annotations.layout_fingerings(gap,play_from_beat)

func _fingering_metrics(font_size: int) -> Dictionary:
    return annotations.metrics(font_size)

func _paint_fingerings(clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0) -> void:
    paint_pass_index = pass_index
    paint_pass_start = pass_start
    current_preparation = preparation_history.get(pass_start,{}) if score_loop_enabled else {}
    annotations.paint(self,clock,playhead_x,gap,pass_index,pass_start,{
        "active_hand":active_hand,"play_from_beat":play_from_beat,
        "score_loop_enabled":score_loop_enabled,"preparation_history":preparation_history})

func _fill_fingering_menu(menu: PopupMenu, event: Dictionary) -> void:
    annotations.fill_menu(menu,event)

func _open_fingering_editor(point: Vector2) -> bool:
    return annotations.open_editor(self,point,_gap(),drawn_note_instances)

func _gui_input(event: InputEvent) -> void:
    if not native_ready:
        return
    if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_RIGHT:
        if _open_fingering_editor(event.position):
            accept_event()
    elif event is InputEventScreenTouch and event.pressed:
        if _open_fingering_editor(event.position):
            accept_event()
    elif event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
        for item in drawn_fingerings:
            if item["rect"].grow(5.0).has_point(event.position):
                if _open_fingering_editor(event.position):
                    accept_event()
                break

# Only native compositor fragments with unambiguous original Verovio ink.
# Reject incomplete engraving before playback can become ready.
func _missing_source_engraving() -> String:
    if not beam_extraction_complete:
        return "Source Verovio beam extraction failed"
    for key in expected_beam_groups:
        if not glyphs.beam_textures.has(str(key)):
            return "Missing original Verovio beam: "+str(key)
    if not slur_extraction_complete:
        return "Source Verovio slur extraction failed"
    for group in notation_tuplets:
        if _tuplet_hidden(group):
            continue
        var ids := PackedStringArray()
        for event in group.get("events",[]):
            ids.append(str(event.get("id","")))
        if ids.is_empty() or not glyphs.has_tuplet("|".join(ids),
                str(group.get("bracket","yes")) == "yes"):
            return "Missing engraved Verovio tuplet: "+("|".join(ids))
    for leader_id in chord_members:
        var event: Dictionary = {}
        for candidate in chord_members[leader_id]:
            if str(candidate.get("id","")) == str(leader_id):
                event = candidate
                break
        if event.is_empty():
            return "Missing original chord leader: "+str(leader_id)
        var key: String = _chord_template_key(event)
        if key.is_empty() or not glyphs.has_chord(key):
            return "Missing engraved Verovio chord: "+str(leader_id)+ \
                " (pattern="+key+", atlas="+ \
                str(glyphs.chord_textures.size())+" templates)"
        if beamed_note_ids.has(str(leader_id)) and ( \
                not glyphs.has_chord_heads(key) or \
                not glyphs.has_chord_stem(key)):
            return "Missing Verovio beamed chord components: "+str(leader_id)
    for pair in expected_slur_pairs:
        if not pair is Array or pair.size() != 2:
            return "Invalid original Verovio slur identity"
        var key: String = str(pair[0])+"|"+str(pair[1])
        if not glyphs.slur_metadata.has(key) or \
                glyphs.slur_note_ids(key) != pair:
            return "Missing original Verovio slur: "+key
    for pair in tie_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var key: String = _tie_template_key(first,last,{"down":_tie_bow_down(first,last,1.0)},1.0)
        if not glyphs.tie_metadata.has(key):
            return "Missing authentic flag-aware tie contour: "+key
    return ""


func _engraved_beam_groups(model: Dictionary) -> Dictionary:
    return ScoreIndex.source_beam_groups(model, glyphs)


func _staff_center(hand: String) -> float:
    layout.set_viewport(size)
    return layout.staff_center(hand)

func _gap() -> float:
    layout.set_viewport(size)
    return layout.staff_gap(staff_gap_limit)

func _fit_vertical_ink_gap(limit: float, staff: String, unit_ink: Rect2) -> float:
    return layout.fit_vertical_ink_gap(limit,staff,unit_ink)

func _clef_for(staff: String, measure: Dictionary) -> Dictionary:
    return layout.clef_for(staff,measure)

func _measure_for(event: Dictionary) -> Dictionary:
    return layout.measure_for(event)

func _event_y(event: Dictionary, gap: float) -> float:
    layout.set_viewport(size)
    return layout.event_y(event,gap)

func _performing_hand(event: Dictionary) -> String:
    return layout.performing_hand(event)

func _display_staff(event: Dictionary) -> String:
    return layout.display_staff(event)

func _event_ink(event: Dictionary) -> Color:
    return _ink(_performing_hand(event))


func _ink(hand: String) -> Color:
    var selected: bool = active_hand == "both" or active_hand == hand
    return NOTE_INK if selected else Color(DIM_INK, .46)


func present(state: Dictionary, transport_beat: float, visual_beat: float = NAN) -> void:
    if state.get("phase","") == "ready" and state.get("practice_preparation") == null and \
            absf(float(state.get("visual_offset_beats",0.0)))<.00001:
        preparation_history.clear()
    super.present(state,transport_beat,visual_beat)



# MusicXML determines each boundary's structure. The first measure has
# no moving barline unless it explicitly opens with a repeat sign. At later
# boundaries an explicit left barline overrides the previous default regular
# right line. A closing double/repeat line belongs to the previous measure.
func _barline_geometry(measure: Dictionary, clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    return layout.barline_geometry(measure,clock,playhead_x,gap,play_from_beat)

func _terminal_barline_geometry(clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    return layout.terminal_barline_geometry(clock,playhead_x,gap,play_from_beat)

func _barline_segments(style: String, gap: float) -> Array:
    return layout.barline_segments(style,gap)

func _barline_strokes(style: String, gap: float) -> Array:
    return layout.barline_strokes(style,gap)

func _paint_barline(info: Dictionary, gap: float) -> void:
    context_painter.paint_barline(self,_painting_frame(gap),info,gap)

func _meter_is_crowded(measure: Dictionary, previous: Dictionary,
        gap: float) -> bool:
    return context_painter.meter_is_crowded(measure,previous,gap)

func _paint_meter_above_staff(measure: Dictionary, x: float,
        gap: float) -> void:
    context_painter.paint_meter_above_staff(self,_painting_frame(gap),measure,x,gap)

func _paint_ledger(x: float, y: float, step: int,
        bottom: float, gap: float, ink: Color) -> void:
    symbols.paint_ledger(self,_painting_frame(gap),x,y,step,bottom,gap,ink)

func _paint_accidental(x: float, y: float,
        value: String, ink: Color, gap: float,
        head_offset: float = INF) -> void:
    symbols.paint_accidental(self,_painting_frame(gap),x,y,value,ink,gap,head_offset)

func _paint_note_accidental(event: Dictionary, x: float, y: float,
        ink: Color, gap: float) -> void:
    symbols.paint_note_accidental(self,_painting_frame(gap),event,x,y,ink,gap)

func _paint_rhythm_dots(x: float, y: float, dots: int,
        ink: Color, gap: float) -> void:
    symbols.paint_rhythm_dots(self,_painting_frame(gap),x,y,dots,ink,gap)

func _paint_tuplet_brackets(clock: float, playhead_x: float,
        gap: float) -> void:
    symbols.paint_tuplet_brackets(self,_painting_frame(gap),clock,playhead_x,gap)

func _tuplet_hidden(group: Dictionary) -> bool:
    return str(group.get("show_number","actual")) == "none" and \
        str(group.get("bracket","yes")) == "no"


func _paint_rest(x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    symbols.paint_rest(self,_painting_frame(gap),x,y,note_type,dots,ink,gap)

func _rest_y(event: Dictionary, gap: float) -> float:
    layout.set_viewport(size)
    return layout.rest_y(event,gap)

func _layout_rest_lanes(gap: float, density: float) -> void:
    layout.layout_rest_lanes(gap,density)

func _paint_clef(x: float, center: float, clef: Dictionary,
        gap: float, ink: Color) -> void:
    context_painter.paint_clef(self,_painting_frame(gap),x,center,clef,gap,ink)

func _paint_meter_number(value: int, x: float, y: float,
        ink: Color, gap: float) -> void:
    context_painter.paint_meter_number(self,_painting_frame(gap),value,x,y,ink,gap)

func _stem_attachment(note_type: String, gap: float, up: bool) -> float:
    return layout.stem_attachment(note_type,gap,up)

func _source_stem_bounds(event: Dictionary, up: bool) -> Array:
    return layout.source_stem_bounds(event,up)

func _polyphonic_stem_directions() -> Dictionary:
    return layout.polyphonic_stem_directions()

func _chord_extents(event: Dictionary, gap: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    return layout.chord_extents(event,gap,head_offsets)

func _chord_template_key(event: Dictionary) -> String:
    return layout.chord_template_key(event)

func _engraved_head_offsets(gap: float) -> Dictionary:
    return layout.engraved_head_offsets(gap)

func _head_family(event: Dictionary) -> String:
    return layout.head_family(event)

func _polyphonic_column_offsets(gap: float, heads: Dictionary) -> Dictionary:
    return layout.polyphonic_column_offsets(gap,heads)

func _voice_column_offset(event: Dictionary, gap: float, heads: Dictionary) -> float:
    return layout.voice_column_offset(event,gap,heads)

func _event_ink_rect(event: Dictionary, gap: float,
        heads: Dictionary, accidentals: Dictionary) -> Rect2:
    return layout.event_ink_rect(event,gap,heads,accidentals)

func _with_single_tuplet_ink(event: Dictionary, rect: Rect2, gap: float) -> Rect2:
    return layout.with_single_tuplet_ink(event,rect,gap)

func _required_ink_density(preferred: float, gap: float = MAX_STAFF_GAP) -> float:
    layout.set_viewport(size)
    var result: Dictionary = ink_geometry.minimum_density(preferred,gap)
    ink_density_witness = result["witness"]
    return float(result["density"])

func _paint_engraved_chord(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {}) -> Array:
    return symbols.paint_engraved_chord(self,_painting_frame(gap),event,x,gap,ink,beam_stem)

func _chord_dot_anchors(notes: Array, centers: Array, gap: float) -> Dictionary:
    return layout.chord_dot_anchors(notes,centers,gap)

func _paint_note(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {},
        head_offset: float = 0.0) -> void:
    symbols.paint_note(self,_painting_frame(gap),event,x,gap,ink,beam_stem,head_offset)

func _beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    var frame: RenderPass = _painting_frame(gap)
    frame.clock = clock
    frame.playhead_x = playhead_x
    var groups: Array = []
    for group in beam_groups:
        if group.size() >= 2 and frame.span_visible(group[0],group[-1]):
            groups.append(group)
    var result: Dictionary = symbols.beam_layout(frame,head_offsets,groups)
    frame_visible_beam_groups = frame.visible_beam_groups
    return result


func _paint_beams(data: Dictionary, gap: float) -> void:
    symbols.paint_beams(self,_painting_frame(gap),data,gap)

func _tie_placement(first: Dictionary, last: Dictionary,
        x0: float, x1: float, gap: float) -> Dictionary:
    layout.set_viewport(size)
    return connector_geometry.tie_placement(first,last,x0,x1,gap)

func _tie_chord_leader(event: Dictionary) -> Dictionary:
    return connector_geometry.tie_chord_leader(event)

func _tie_bow_down(first: Dictionary, last: Dictionary, gap: float) -> bool:
    return connector_geometry.tie_bow_down(first,last,gap)

func _tie_template_key(first: Dictionary, last: Dictionary, place: Dictionary, gap: float) -> String:
    return connector_geometry.tie_template_key(first,last,place,gap)

func _paint_ties(playhead_x: float, clock: float, gap: float) -> void:
    symbols.paint_ties(self,_painting_frame(gap),playhead_x,clock,gap)

func _paint_tie_contour(first: Dictionary, last: Dictionary,
        place: Dictionary, gap: float) -> void:
    symbols.paint_tie_contour(self,_painting_frame(gap),first,last,place,gap)

func _tie_contour_rect(first: Dictionary, last: Dictionary,
        place: Dictionary, gap: float) -> Rect2:
    return connector_geometry.tie_contour_rect(first,last,place,gap)

func _tie_clear_flag(event: Dictionary, direction: String, left: float,
        right: float, origin: Vector2, gap: float) -> float:
    return connector_geometry.tie_clear_flag(event,direction,left,right,origin,gap)

func _paint_slurs(playhead_x: float,clock: float,gap: float) -> void:
    symbols.paint_slurs(self,_painting_frame(gap),playhead_x,clock,gap)

func _paint_expressions(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    context_painter.paint_expressions(self,_painting_frame(gap),left,right,clock,playhead_x,gap)

func _paint_hairpins(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    context_painter.paint_hairpins(self,_painting_frame(gap),left,right,clock,playhead_x,gap)

func _paint_volta_endings(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    context_painter.paint_volta_endings(self,_painting_frame(gap),left,right,clock,playhead_x,gap)

func _paint_grace_notes(gap: float) -> void:
    symbols.paint_grace_notes(self,_painting_frame(gap),gap)

func _visible_events(left: float, right: float) -> Array:
    var begin := 0
    var end := ordered_events.size()
    while begin < end:
        var middle: int = (begin + end) >> 1
        if float(ordered_events[middle].get("beat", 0.0)) < left-.25:
            begin = middle + 1
        else:
            end = middle
    var results: Array = []
    for index in range(begin, ordered_events.size()):
        var event: Dictionary = ordered_events[index]
        if float(event.get("beat", 0.0)) > right+.25:
            break
        if _practice_event_visible(event):
            results.append(event)
    frame_scanned_events = results.size()
    if painting_pass != null:
        painting_pass.scanned_events = frame_scanned_events
    return results


func _record_notehead(event: Dictionary, point: Vector2) -> void:
    var id: String = str(event["id"])
    pass_noteheads[id] = point
    drawn_note_instances.append({"event_id":id,"source_id":event.get("source_id"),
        "pass_index":paint_pass_index,"instance_id":"%d:%s" % [paint_pass_index,id],"position":point})
    if not drawn_noteheads.has(id) or absf(point.x-size.x*PLAYHEAD_FRACTION)<absf(drawn_noteheads[id].x-size.x*PLAYHEAD_FRACTION):
        drawn_noteheads[id] = point


func _practice_event_visible(event: Dictionary) -> bool:
    return SourceVisibility.event_visible(event,paint_pass_start,score_loop_enabled,preparation_history)

func _practice_span_visible(first: Dictionary, last: Dictionary) -> bool:
    return SourceVisibility.span_visible(first,last,paint_pass_start,score_loop_enabled,preparation_history)

func _practice_intervals_overlap(first: Dictionary, second: Dictionary) -> bool:
    return SourceVisibility.intervals_overlap(first,second)

func _remember_preparation() -> void:
    if practice_preparation.is_empty():
        return
    var owner: float = float(practice_preparation["pass_start_beat"])
    # A new recovery may cross its source-copy boundary. The latest full
    # preparation replaces any earlier intersecting preparation as a whole.
    for previous in preparation_history.keys():
        if float(previous)!=owner and _practice_intervals_overlap(
                preparation_history[previous]["measure"],practice_preparation["measure"]):
            preparation_history.erase(previous)
    preparation_history[owner] = practice_preparation.duplicate(true)


func _practice_context_before(at: float, stride: float) -> Dictionary:
    if at<=.00001:
        return {}
    var pass_start: float = maxf(0.0,floorf(at/stride))*stride
    var local: float = at-pass_start
    var previous: Dictionary = {}
    for measure in timeline.measures:
        # A header exactly at silence start is replaced too. Compare with
        # its predecessor so the necessary change is engraved on the rest.
        if float(measure["start_beat"])<local-.00001:
            previous = measure
    if previous.is_empty() and pass_start>0.0:
        # At a copy boundary the preceding intact ordinary gap has already
        # established its actual context. A pickup preparation can use 4/4
        # while the canonical source still opens in 1/8.
        var incoming: Dictionary = practice_timeline["gap"].duplicate(true)
        incoming["start_beat"] = pass_start-float(incoming["duration_beats"])
        incoming["end_beat"] = pass_start
        return incoming
    if previous.is_empty():
        return {}
    var result: Dictionary = previous.duplicate(true)
    result["start_beat"] = float(result["start_beat"])+pass_start
    result["end_beat"] = float(result["end_beat"])+pass_start
    return result


func _practice_barline(x: float, mark: Dictionary, gap: float) -> void:
    context_painter.practice_barline(self,_painting_frame(gap),x,mark,gap)

func _barline_left_limit(x: float, mark: Dictionary, gap: float) -> float:
    return context_painter.barline_left_limit(x,mark,gap)

func _paint_preparation_measure(measure: Dictionary, previous: Dictionary,
        gap: float, playhead_x: float, opening: bool = false) -> void:
    context_painter.paint_preparation_measure(self,_painting_frame(gap),measure,previous,gap,playhead_x,opening)

func _context_meter_x(measure: Dictionary, x: float, gap: float,
        opening: bool, right_limit: float = INF) -> float:
    return context_painter.context_meter_x(measure,x,gap,opening,right_limit)

func _paint_context(measure: Dictionary, previous_measure: Dictionary, x: float,
        gap: float, opening: bool, meter_right_limit: float = INF) -> bool:
    return context_painter.paint_context(self,_painting_frame(gap),measure,previous_measure,x,gap,opening,meter_right_limit)

func _paint_source_pass(camera_clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0) -> void:
    paint_pass_index = pass_index
    paint_pass_start = pass_start
    pass_noteheads.clear()
    current_preparation = preparation_history.get(pass_start,{}) if score_loop_enabled else {}
    painting_pass = _new_paint_frame(camera_clock,playhead_x,gap,pass_index,pass_start)
    var font: Font = ThemeDB.fallback_font
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+size.x/timeline.pixels_per_beat
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
        if not target_boundary and not _practice_event_visible(measure):
            continue
        if at<left-.7 or at>right+.7:
            previous_measure = measure
            continue
        var x: float = timeline.screen_x(at,camera_clock,playhead_x,play_from_beat)
        var opening: bool = first and pass_index==0 and current_preparation.is_empty()
        if not target_boundary and not (first and pass_index>0):
            var barline: Dictionary = _barline_geometry(measure,camera_clock,playhead_x,gap)
            if not barline.is_empty() and float(barline["x"])>=-gap*2.0 and float(barline["x"])<=size.x+gap*2.0:
                _paint_barline(barline,gap)
        var meter_right_limit := INF
        if target_boundary or (first and pass_index>0):
            var incoming: Variant = current_preparation["measure"].get("right_barline") if target_boundary else measure.get("left_barline")
            var mark: Dictionary = incoming if incoming is Dictionary else {"style":"regular","repeat":""}
            meter_right_limit = _barline_left_limit(
                BarlineLayout.project(at,timeline,camera_clock,playhead_x,play_from_beat,gap),mark,gap)
        var crowded_meter: bool = _paint_context(measure,previous_measure,x,gap,opening,meter_right_limit)
        if not first and not crowded_meter and x>=0.0 and x<=size.x:
            draw_string(font,Vector2(x+gap*.4,_staff_center("right")-gap*4.3),
                str(int(measure.get("number",0))),HORIZONTAL_ALIGNMENT_LEFT,-1,11,DIM_INK)
        previous_measure = measure
    # The actual ending of the last measure has its own terminal barline.
    # It must not disappear simply because no following measure exists.
    var terminal: Dictionary = _terminal_barline_geometry(
        camera_clock,playhead_x,gap)
    if not score_loop_enabled and not terminal.is_empty() and float(terminal["x"]) >= -gap*2.0 and \
            float(terminal["x"]) <= size.x+gap*2.0:
        _paint_barline(terminal,gap)
    _paint_volta_endings(left,right,camera_clock,playhead_x,gap)
    # All symbols carry their original source onset; NO separate horizontal
    # layout pass or per-note acceleration, including chord tones and rests.
    if cached_offsets_gap < 0.0 or absf(cached_offsets_gap-gap) > .001:
        cached_head_offsets = _engraved_head_offsets(gap)
        cached_accidental_offsets = Geometry.accidental_offsets(
            ordered_events,gap,cached_head_offsets,glyphs.bounds)
        cached_offsets_gap = gap
    var head_offsets: Dictionary = cached_head_offsets
    var beam_data: Dictionary = _beam_layout(gap, camera_clock,
        playhead_x, head_offsets)
    var beam_stems: Dictionary = beam_data.get("stems", {})
    var compound_ids: Dictionary = {}
    for event in _visible_events(left, right):
        if compound_ids.has(str(event.get("id",""))):
            continue
        var at: float = float(event.get("beat", 0.0))
        var x: float = timeline.screen_x(at,camera_clock,
            playhead_x,play_from_beat)
        var staff: String = str(event.get("staff","right"))
        var ink: Color = _event_ink(event)
        if str(event.get("kind","")) == "note":
            var members: Array = _paint_engraved_chord(event,x,gap,ink,
                beam_stems.get(str(event.get("id","")), {}))
            if not members.is_empty():
                for id in members:
                    compound_ids[id] = true
                painting_pass.visible_symbols += members.size()
                continue
            _paint_note(event,x,gap,ink,
                beam_stems.get(str(event.get("id", "")), {}),
                float(head_offsets.get(str(event.get("id", "")), 0.0)))
        else:
            _paint_rest(x,_rest_y(event,gap),
                str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        painting_pass.visible_symbols += 1
    _paint_beams(beam_data, gap)
    _paint_ties(playhead_x,camera_clock,gap)
    _paint_slurs(playhead_x,camera_clock,gap)
    _paint_tuplet_brackets(camera_clock,playhead_x,gap)
    _paint_expressions(left,right,camera_clock,playhead_x,gap)
    _paint_hairpins(left,right,camera_clock,playhead_x,gap)
    _paint_grace_notes(gap)
    for instance in painting_pass.drawn_note_instances:
        _record_notehead(expression_note_index[str(instance["event_id"])],instance["position"])
    pass_noteheads = painting_pass.pass_noteheads
    visible_symbols += painting_pass.visible_symbols
    frame_scanned_events = painting_pass.scanned_events
    frame_visible_beam_groups = painting_pass.visible_beam_groups
    painting_pass = null
    fingering_pass_clocks.append({"clock":camera_clock,"pass_index":pass_index,"pass_start":pass_start})

func _draw() -> void:
    painting_pass = null
    drawn_noteheads.clear()
    drawn_note_instances.clear()
    pass_noteheads.clear()
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
    var gap: float = _gap()
    var playhead_x: float = size.x * PLAYHEAD_FRACTION
    var camera_clock: float = clock_beat if running or paused else 0.0
    var current: float = timeline.musical_beat(camera_clock,play_from_beat)
    var left: float = current-playhead_x/timeline.pixels_per_beat
    var right: float = left+size.x/timeline.pixels_per_beat
    # A quiet pool of light marks the strike without hiding any engraved ink.
    var top: float = _staff_center("right")-gap*3.8
    var bottom: float = _staff_center("left")+gap*3.7
    var breath: float = .5+.5*cos(clock_beat*TAU) if running and not paused else 0.0
    if transport_overlay_enabled:
        for radius in [20.0, 10.0, 4.0]:
            draw_rect(Rect2(playhead_x-radius, top, radius*2.0, bottom-top),
                Color(PREVIEW_LIGHT, .012+breath*.004))
    # Always draw ten native rules; no copied or stitched raster systems.
    for staff in ["right","left"]:
        var center: float = _staff_center(staff)
        var ink: Color = _ink(staff)
        for line_index in range(5):
            var y: float = center+(float(line_index)-2.0)*gap
            draw_line(Vector2(0,y),Vector2(size.x,y),
                Color(ink,.34),1.3,true)
    # The count-in runs on the same clock, but its leading boundary is
    # intentionally NOT a printed barline: it sits before the clef/header
    # and used to look like an orphaned vertical rule in the score.
    # One semantic practice timeline owns both source-copy placement and
    # preparation silence. No independently inferred final-bar duration.
    if score_loop_enabled and not timeline.measures.is_empty():
        if not practice_contract_error.is_empty():
            draw_string(font,Vector2(20,size.y*.5),practice_contract_error,
                HORIZONTAL_ALIGNMENT_LEFT,-1,15,NOTE_INK)
            return
        _remember_preparation()
        var stride: float = float(practice_timeline["stride_beats"])
        var virtual_left: float = visual_scroll_beat-playhead_x/timeline.pixels_per_beat
        var virtual_right: float = virtual_left+size.x/timeline.pixels_per_beat
        var first_pass: int = maxi(0,floori(virtual_left/stride)-1)
        var last_pass: int = maxi(first_pass,ceili(virtual_right/stride)+1)
        var preparations: Dictionary = {}
        for pass_index in range(first_pass,last_pass+1):
            var pass_start: float = pass_index*stride
            if pass_start>virtual_right+.7 or pass_start+stride<virtual_left-.7:
                continue
            _paint_source_pass(visual_scroll_beat-pass_start-play_from_beat,
                playhead_x,gap,pass_index,pass_start)
            var silence: Dictionary = practice_timeline["gap"].duplicate(true)
            silence["start_beat"] = pass_start+float(silence["start_beat"])
            silence["end_beat"] = pass_start+float(silence["end_beat"])
            var replaced := false
            for preparation in preparation_history.values():
                if _practice_intervals_overlap(silence,preparation["measure"]):
                    replaced = true
                    break
            if replaced:
                continue
            silence["left_barline"] = timeline.measures[-1].get("right_barline",{})
            var incoming: Variant = timeline.measures[0].get("left_barline")
            if incoming is Dictionary:
                silence["right_barline"] = incoming
            var previous: Dictionary = timeline.measures[-1].duplicate(true)
            previous["start_beat"] = pass_start+float(previous["start_beat"])
            previous["end_beat"] = pass_start+float(previous["end_beat"])
            preparations[float(silence["start_beat"])] = {"measure":silence,"previous":previous,"opening":false}
        # Rewind preparation replaces only its declared practice interval.
        # Remember completed rests while that pass remains on screen; a later
        # source copy cannot make its past preparation disappear or flicker.
        for pass_start in preparation_history.keys():
            if float(pass_start)+stride<virtual_left-stride:
                preparation_history.erase(pass_start)
                continue
            var item: Dictionary = preparation_history[pass_start]
            var silence: Dictionary = item["measure"]
            var previous: Dictionary = _practice_context_before(float(silence["start_beat"]),stride)
            preparations[float(silence["start_beat"])] = {"measure":silence,"previous":previous,
                "opening":previous.is_empty()}
        var preparation_starts: Array = preparations.keys()
        preparation_starts.sort()
        for start in preparation_starts:
            var item: Dictionary = preparations[start]
            _paint_preparation_measure(item["measure"],item["previous"],gap,playhead_x,item["opening"])
    else:
        _paint_source_pass(camera_clock,playhead_x,gap)
    if transport_overlay_enabled:
        draw_line(Vector2(playhead_x,_staff_center("right")-gap*3.8),
            Vector2(playhead_x,_staff_center("left")+gap*3.7),
            PREVIEW_LIGHT,2.0,true)
    # Instructional ink has its own compositor phase. It cannot change
    # canonical music or be erased by the transport cursor during scrolling.
    for annotation_pass in fingering_pass_clocks:
        _paint_fingerings(float(annotation_pass["clock"]),playhead_x,gap,
            int(annotation_pass["pass_index"]),float(annotation_pass["pass_start"]))
    # A genuine font brace joins the two continuous staves at the screen's
    # edge. Stretch only this authentic brace, never the timed music stream.
    var staff_top: float = _staff_center("right")-2.0*gap
    var staff_bottom: float = _staff_center("left")+2.0*gap
    draw_rect(Rect2(0, staff_top-gap, 29, staff_bottom-staff_top+gap*2), Design.STAGE)
    if glyphs.textures.has("brace"):
        draw_texture_rect(glyphs.textures["brace"],
            Rect2(6, staff_top-2, 18, staff_bottom-staff_top+4), false,
            NOTE_INK)
    draw_line(Vector2(29,staff_top),Vector2(29,staff_bottom),
        Color(NOTE_INK,.50),1.2,true)
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
        "current_preparation":current_preparation,"visual_scroll_beat":visual_scroll_beat})

func _painting_frame(gap: float) -> RenderPass:
    if painting_pass != null:
        return painting_pass
    var frame := _new_paint_frame(clock_beat,size.x*PLAYHEAD_FRACTION,gap,
        paint_pass_index,paint_pass_start)
    frame.drawn_noteheads = drawn_noteheads
    frame.pass_noteheads = pass_noteheads
    frame.drawn_note_instances = drawn_note_instances
    return frame
