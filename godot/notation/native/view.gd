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
const VerovioGlyphs := preload("res://notation/native/glyphs.gd")
const Design := preload("res://practice_theme.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED
const PREVIEW_LIGHT := Design.MINT
const MAX_STAFF_GAP := 22.0
# A piano learner needs upcoming notation in view. Preserve the largest
# authentic staff that leaves at least this many beats to the right of the
# fixed playhead. No temporal warping, font imitation or overlap is allowed.
const MIN_LOOKAHEAD_BEATS := 1.75
const MIN_READABLE_STAFF_GAP := 14.0
const FINGERING_FONT_SIZE := 16
const FingeringPlacement := preload("res://notation/native/fingering_placement.gd")

signal fingering_change_requested(source_id: String, finger: Variant)

# Annotation cells live on the same immutable score axis as the note ink.
# Cache once per score/vertical size; scrolling only translates their X.
var fingering_layout: Array = []
var drawn_fingerings: Array = []
var fingering_layout_gap := -1.0
var fingering_layout_height := -1.0
var fingering_popup: PopupMenu
var fingering_annotations_enabled := true
var fingering_placement_issues: Array = []
var fingering_metrics_cache: Dictionary = {}
var fingering_staff_lines: Array = []
var fingering_sprite_envelopes: Dictionary = {}
var transport_overlay_enabled := true
var fingering_pass_clocks: Array = []

func set_transport_overlay_enabled(enabled: bool) -> void:
    transport_overlay_enabled = enabled
    queue_redraw()

func set_fingering_annotations_enabled(enabled: bool) -> void:
    fingering_annotations_enabled = enabled
    drawn_fingerings.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = -1.0
    if not enabled and fingering_popup != null:
        fingering_popup.hide()
    queue_redraw()

var glyphs = VerovioGlyphs.new()
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
var beam_groups: Array = []
var beamed_note_ids: Dictionary = {}
var beam_stem_up_by_note: Dictionary = {}
var voice_stem_up_by_note: Dictionary = {}
var chord_members: Dictionary = {}
var notation_tuplets: Array = []
# Immutable musical structure is indexed ONCE when a passage changes.
# Each frame then visits only visible onsets, beams and ties.
var measure_by_number: Dictionary = {}
var ordered_events: Array = []
var ink_density_witness: Dictionary = {}
var selected_density_witness: Dictionary = {}
var attached_grace_notes: Array = []
var source_expressions: Array = []
var expression_note_index: Dictionary = {}
var tie_pairs: Array = []
var slur_pairs: Array = []
var expected_slur_pairs: Array = []
var slur_extraction_complete := true
var expected_beam_groups: Array = []
var beam_extraction_complete := true
var previous_attack_before_measure: Dictionary = {}
var cached_staff_gap := -1.0
var cached_gap_height := -1.0
var cached_head_offsets: Dictionary = {}
var cached_accidental_offsets: Dictionary = {}
# Per-rest displacements measured in staff spaces; fixed for one score revision.
var rest_lane_offsets: Dictionary = {}
var unavoidable_rest_overlaps := 0
var cached_offsets_gap := -1.0
var frame_scanned_events := 0
var frame_visible_beam_groups := 0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_PASS
    tooltip_text = "Right-click a note or tap a finger number to change its fingering"


func _reset_fingering() -> void:
    fingering_layout.clear()
    drawn_fingerings.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = -1.0
    if fingering_popup != null:
        fingering_popup.hide()


func clear_score() -> void:
    _reset_fingering()
    super.clear_score()
    timeline.set_density(configured_density)
    staff_gap_limit = MAX_STAFF_GAP
    native_ready = false
    failure_reason = ""
    beam_groups.clear()
    beamed_note_ids.clear()
    beam_stem_up_by_note.clear()
    voice_stem_up_by_note.clear()
    chord_members.clear()
    notation_tuplets.clear()
    measure_by_number.clear()
    ordered_events.clear()
    ink_density_witness.clear()
    selected_density_witness.clear()
    attached_grace_notes.clear()
    source_expressions.clear()
    expression_note_index.clear()
    tie_pairs.clear()
    slur_pairs.clear()
    previous_attack_before_measure.clear()
    cached_staff_gap = -1.0
    cached_gap_height = -1.0
    cached_head_offsets.clear()
    cached_accidental_offsets.clear()
    rest_lane_offsets.clear()
    unavoidable_rest_overlaps = 0
    cached_offsets_gap = -1.0


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
    fingering_sprite_envelopes.clear()
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
    var index: Dictionary = ScoreIndex.build(timeline.model, glyphs)
    beam_groups = index["beam_groups"]
    beamed_note_ids = index["beamed_note_ids"]
    beam_stem_up_by_note = index["beam_stem_up_by_note"]
    notation_tuplets = index["notation_tuplets"]
    measure_by_number = index["measure_by_number"]
    ordered_events = index["ordered_events"]
    attached_grace_notes = timeline.model.get("grace_notes", []).duplicate(true)
    source_expressions = timeline.model.get("expressions", []).duplicate(true)
    expression_note_index.clear()
    for source_event in ordered_events:
        if str(source_event.get("kind", "")) == "note":
            expression_note_index[str(source_event.get("id", ""))] = source_event
    chord_members = index["chord_members"]
    voice_stem_up_by_note = _polyphonic_stem_directions()
    previous_attack_before_measure = index["previous_attack_before_measure"]
    tie_pairs = index["tie_pairs"]
    slur_pairs = index["slur_pairs"]
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
    var ink_density: float = density
    var fits_density := false
    # The hidden Practice canvas is sometimes loaded before Godot assigns
    # its first Control width. A zero-width value must not force every
    # passage through five extremely expensive candidate engravings.
    # Use the standard desktop viewport for that brief pre-layout state.
    var viewport_width: float = size.x if size.x >= 640.0 else 1536.0
    var max_usable_density: float = (
        viewport_width*(1.0-PLAYHEAD_FRACTION)/MIN_LOOKAHEAD_BEATS)
    var fallbacks: Array = []
    for candidate_gap in [MAX_STAFF_GAP,17.0,14.0,11.0,8.5]:
        var tested_gap: float = float(candidate_gap)
        _layout_rest_lanes(tested_gap,density)
        var trial: float = _required_ink_density(density,tested_gap)
        var first_witness: Dictionary = ink_density_witness.duplicate(true)
        _layout_rest_lanes(tested_gap,trial)
        var second_trial: float = _required_ink_density(trial,tested_gap)
        var second_witness: Dictionary = ink_density_witness.duplicate(true)
        var final_witness: Dictionary = second_witness if second_trial > trial else first_witness
        trial = maxf(trial,second_trial)
        if not is_finite(trial) or trial > timeline.MAX_SCORE_PIXELS_PER_BEAT:
            continue
        var fit_option: Dictionary = {
            "gap":tested_gap, "density":trial, "witness":final_witness}
        fallbacks.append(fit_option)
        if tested_gap >= MIN_READABLE_STAFF_GAP and trial > max_usable_density:
            continue
        staff_gap_limit = tested_gap
        ink_density = trial
        selected_density_witness = final_witness.duplicate(true)
        fits_density = true
        break
    if not fits_density and not fallbacks.is_empty():
        # An exceptionally dense score may not permit the target lookahead
        # at a legible staff size. Prefer the smallest scale still >=14px.
        # Never select an arbitrary sub-legible size solely to pass a metric.
        var alternate: Dictionary = fallbacks[-1]
        for option in fallbacks:
            if float(option["gap"]) >= MIN_READABLE_STAFF_GAP:
                alternate = option
        staff_gap_limit = float(alternate["gap"])
        ink_density = float(alternate["density"])
        selected_density_witness = alternate["witness"].duplicate(true)
        fits_density = true
    if fits_density:
        selected_density_witness["staff_gap"] = staff_gap_limit
        selected_density_witness["selected_density"] = ink_density
        selected_density_witness["available_lookahead_beats"] = (
            size.x*(1.0-PLAYHEAD_FRACTION)/ink_density)
        # The accepted scale can be different from the last trial; use the
        # corresponding rest lanes instead of stale rejected-candidate lanes.
        _layout_rest_lanes(staff_gap_limit,ink_density)
    if not fits_density:
        failure_reason = "Source glyph ink cannot fit within the fixed musical timeline"
        notice = failure_reason
        return false
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
    if str(event.get("kind", "")) != "note" or not bool(event.get("is_attack", false)):
        return {}
    var value: Variant = event.get("fingering")
    if not value is Dictionary:
        return {}
    var finger: Variant = value.get("finger")
    if typeof(finger) not in [TYPE_INT, TYPE_FLOAT] or \
            not is_finite(float(finger)) or float(finger) != floorf(float(finger)) or \
            int(finger) < 1 or int(finger) > 5:
        return {}
    if value.get("hand") not in ["left", "right"] or \
            not value.get("source_id") is String or str(value["source_id"]).is_empty() or \
            value.get("origin") not in ["manual", "authored", "automatic"]:
        return {}
    return value


func _fingering_source(event: Dictionary) -> String:
    var assignment: Variant = event.get("fingering")
    if assignment is Dictionary and assignment.get("source_id") is String:
        return assignment["source_id"]
    var source: Variant = event.get("source_id")
    return source if source is String else ""


func _fingering_block(rect: Rect2, bins: Dictionary, cell: float) -> void:
    for column in range(floori(rect.position.x/cell), floori(rect.end.x/cell)+1):
        if not bins.has(column):
            bins[column] = []
        bins[column].append(rect)


func _fingering_clear(rect: Rect2, bins: Dictionary, cell: float) -> bool:
    if rect.position.y < 4.0 or rect.end.y > size.y-4.0:
        return false
    for line in fingering_staff_lines:
        if rect.grow(.5).intersects(line):
            return false
    for column in range(floori((rect.position.x-3.0)/cell), floori((rect.end.x+3.0)/cell)+1):
        for other in bins.get(column, []):
            if rect.grow(3.0).intersects(other):
                return false
    return true


func _fingering_obstacles(gap: float, bins: Dictionary, cell: float) -> void:
    var density: float = timeline.pixels_per_beat
    var unit: float = gap/250.0
    var span: float = maxf(size.x,float(ordered_events[-1].get("beat",0.0))*density+gap*12.0) if not ordered_events.is_empty() else size.x
    fingering_staff_lines.clear()
    for hand in ["right","left"]:
        for line in range(-2,3):
            fingering_staff_lines.append(Rect2(-gap*12.0,_staff_center(hand)+float(line)*gap-.5,span+gap*12.0,1.0))
    for event in ordered_events:
        _fingering_event_obstacles(event,gap,bins,cell)
    # Source beam masks and their stretched native stems, including chords.
    for group in beam_groups:
        var ids := PackedStringArray()
        for event in group:
            ids.append(str(event.get("id","")))
        var key: String = "|".join(ids)
        if not glyphs.beam_metadata.has(key):
            continue
        var info: Dictionary = glyphs.beam_metadata[key]
        var box: Array = info["bounds"]
        var first: Dictionary = group[0]
        var last: Dictionary = group[-1]
        var x0: float = float(first["beat"])*density+_voice_column_offset(first,gap,cached_head_offsets)
        var x1: float = float(last["beat"])*density+_voice_column_offset(last,gap,cached_head_offsets)
        var source_offsets: Array = info["head_offsets"]
        _fingering_block(Rect2(x0+(float(box[0])-float(source_offsets[0]))*unit,
            _event_y(first,gap)+float(box[1])*unit,
            x1-x0+(float(box[2])-float(source_offsets[-1])+float(source_offsets[0]))*unit,
            float(box[3])*unit),bins,cell)
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var extents: Dictionary = _chord_extents(event,gap,cached_head_offsets)
            var head_y: float = float(extents["bottom_y" if info["stem_up"] else "top_y"])
            var tip_y: float = head_y+float(info["tip_offsets"][index])*unit
            var x: float = float(event["beat"])*density+_voice_column_offset(event,gap,cached_head_offsets)
            var stem: Array = _source_stem_bounds(event,bool(info["stem_up"]))
            if stem.size() == 4:
                _fingering_block(Rect2(x+float(stem[0])*unit,minf(head_y,tip_y),
                    float(stem[2])*unit,absf(head_y-tip_y)),bins,cell)
    for pair in tie_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var place: Dictionary = _tie_placement(first,last,float(first["beat"])*density,
            float(last["beat"])*density,gap)
        if place.is_empty():
            continue
        var info: Dictionary = glyphs.tie_metadata["up" if place["down"] else "down"]
        var box: Array = info["bounds"]
        var scale: float = (float(place["x1"])-float(place["x0"]))/float(info["span"])
        _fingering_block(Rect2(float(place["x0"])+float(box[0])*scale,
            float(place["y"])+float(box[1])*unit,float(box[2])*scale,float(box[3])*unit),bins,cell)
    for pair in slur_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var info: Dictionary = glyphs.slur_metadata[pair["key"]]
        var box: Array = info["bounds"]
        var x0: float = float(first["beat"])*density+float(cached_head_offsets.get(str(first["id"]),0.0))
        var x1: float = float(last["beat"])*density+float(cached_head_offsets.get(str(last["id"]),0.0))
        var change: float = _event_y(last,gap)-_event_y(first,gap)-float(info.get("original_end_y",0.0))*unit
        var a: float = change*float(box[0])/float(info["span"])
        var b: float = change*(float(box[0])+float(box[2]))/float(info["span"])
        _fingering_block(Rect2(x0+float(box[0])*(x1-x0)/float(info["span"]),
            _event_y(first,gap)+float(box[1])*unit+minf(a,b),
            float(box[2])*(x1-x0)/float(info["span"]),float(box[3])*unit+absf(b-a)),bins,cell)
    for group in notation_tuplets:
        var events: Array = group.get("events",[])
        if events.is_empty() or _tuplet_hidden(group):
            continue
        var ids := PackedStringArray()
        for event in events:
            ids.append(str(event["id"]))
        var info: Dictionary = glyphs.tuplet_metadata.get("|".join(ids),{})
        var first: Dictionary = events[0]
        var x0: float = float(first["beat"])*density+_voice_column_offset(first,gap,cached_head_offsets)
        var x1: float = float(events[-1]["beat"])*density+_voice_column_offset(events[-1],gap,cached_head_offsets)
        var y: float = _rest_y(first,gap) if first["kind"] == "rest" else _event_y(first,gap)
        for kind in ["number","bracket"]:
            if not info.get(kind) is Dictionary or info[kind].is_empty():
                continue
            var box: Array = info[kind]["bounds"]
            var left: float = (x0+x1)*.5-float(box[2])*unit*.5 if kind == "number" and events.size() > 1 else x0+float(box[0])*unit
            var width: float = float(box[2])*unit if kind == "number" or events.size() == 1 else x1-x0+(float(box[2])-float(info["span"]))*unit
            _fingering_block(Rect2(left,y+float(box[1])*unit,width,float(box[3])*unit),bins,cell)
    for mark in source_expressions:
        var hand: String = _display_staff(mark)
        var kind: String = str(mark.get("kind",""))
        var value: String = str(mark.get("value",""))
        var x: float = float(mark.get("beat",0.0))*density
        var y: float = _staff_center(hand)+gap*(3.0 if kind == "dynamic" else 3.55)
        var name := ""
        if kind == "dynamic":
            name = "dynamic_"+value
        elif kind == "pedal":
            name = "pedal_start" if value == "start" else "pedal_stop"
        elif kind == "articulation":
            var event: Dictionary = expression_note_index.get(str(mark.get("note_id","")),{})
            if event.is_empty():
                continue
            var step: int = Geometry.staff_step(event.get("spelling",{}),_clef_for(hand,_measure_for(event)))
            var below: bool = step < 4
            y = maxf(_event_y(event,gap)+gap*1.05,_staff_center(hand)+gap*2.9) if below else minf(_event_y(event,gap)-gap*1.05,_staff_center(hand)-gap*2.9)
            x = float(event["beat"])*density+float(cached_head_offsets.get(str(event["id"]),0.0))
            name = "artic_"+value+("_below" if below else "_above")
        if glyphs.bounds.has(name):
            var box: Array = glyphs.bounds[name]
            var scale: float = unit*.9
            _fingering_block(Rect2(x-float(box[2])*scale*.5,y+float(box[1])*scale,
                float(box[2])*scale,float(box[3])*scale),bins,cell)
    var translation: float = timeline.screen_x(0.0,0.0,0.0,play_from_beat)
    var boundaries: Array = []
    for measure in timeline.measures:
        boundaries.append(_barline_geometry(measure,0.0,0.0,gap))
    boundaries.append(_terminal_barline_geometry(0.0,0.0,gap))
    for boundary in boundaries:
        if boundary.is_empty():
            continue
        var x: float = float(boundary["x"])-translation
        var strokes: Array = _barline_strokes(str(boundary.get("style","regular")),gap)
        if strokes.is_empty():
            continue
        for stroke in strokes:
            var width: float = float(stroke["width"])
            var stroke_x: float = x+float(stroke["offset"])
            for segment in boundary.get("segments",[]):
                _fingering_block(Rect2(stroke_x-width*.5,float(segment["top"]),width,
                    float(segment["bottom"])-float(segment["top"])),bins,cell)
        var repetition: String = str(boundary.get("repeat",""))
        var positions: Array = []
        if repetition in ["backward","both"]:
            positions.append(x-gap*.92)
        if repetition in ["forward","both"]:
            positions.append(x+gap*.56)
        var dot: Array = glyphs.bounds.get("repeat_dot",[])
        if dot.size()==4:
            for dot_x in positions:
                for hand in ["right","left"]:
                    for dot_y in [_staff_center(hand)-gap*.5,_staff_center(hand)+gap*.5]:
                        _fingering_block(Rect2(float(dot_x)-float(dot[2])*unit*.5,
                            float(dot_y)-float(dot[3])*unit*.5,
                            float(dot[2])*unit,float(dot[3])*unit),bins,cell)
    for grace in attached_grace_notes:
        var target: Dictionary = expression_note_index.get(str(grace.get("before_note_id","")),{})
        if target.is_empty():
            continue
        var hand: String = _display_staff(grace)
        var step: int = Geometry.staff_step(grace.get("spelling",{}),_clef_for(hand,_measure_for(grace)))
        var y: float = Geometry.note_y(step,_staff_center(hand)+gap*2.0,gap)
        var kind: String = str(grace.get("note_type","eighth"))
        var box: Array = glyphs.note_bounds.get(kind+("_up" if step<4 else "_down"),[])
        if box.size() == 4:
            var scale: float = unit*.66
            var x: float = float(target["beat"])*density+float(cached_head_offsets.get(str(target["id"]),0.0))-gap*1.4
            _fingering_block(Rect2(x+float(box[0])*scale,y+float(box[1])*scale,
                float(box[2])*scale,float(box[3])*scale),bins,cell)
    var pending: Dictionary = {}
    for mark in source_expressions:
        if str(mark.get("kind","")) != "hairpin":
            continue
        var hand: String = _display_staff(mark)
        var key: String = hand+"|"+str(mark.get("number","1"))
        if str(mark.get("value","")) in ["crescendo","diminuendo"]:
            pending[key] = mark
        elif str(mark.get("value","")) == "stop" and pending.has(key):
            var start: Dictionary = pending[key]
            pending.erase(key)
            var x0: float = float(start.get("beat",0.0))*density+gap*.48
            var x1: float = float(mark.get("beat",0.0))*density-gap*.25
            if x1>x0:
                _fingering_block(Rect2(x0,_staff_center(hand)+gap*3.55-gap*.3,x1-x0,gap*.6),bins,cell)


func _fingering_event_obstacles(event: Dictionary, gap: float, bins: Dictionary, cell: float) -> void:
    var id: String = str(event["id"])
    var kind: String = str(event.get("note_type","quarter"))
    var unit: float = gap/250.0
    var anchor: float = float(event["beat"])*timeline.pixels_per_beat
    var x: float = anchor+float(cached_head_offsets.get(id,0.0))
    var y: float = _rest_y(event,gap) if event["kind"] == "rest" else _event_y(event,gap)
    var box: Array
    if event["kind"] == "rest":
        box = glyphs.bounds["rest_"+kind]
        _fingering_block(Rect2(anchor-float(box[2])*unit*.5,y+float(box[1])*unit,
            float(box[2])*unit,float(box[3])*unit),bins,cell)
    else:
        box = glyphs.bounds["head_"+(kind if kind in ["whole","half"] else "black")]
        _fingering_block(Rect2(x-float(box[2])*unit*.5,y+float(box[1])*unit,
            float(box[2])*unit,float(box[3])*unit),bins,cell)
        var step: int = Geometry.staff_step(event.get("spelling",{}),_clef_for(str(event["staff"]),_measure_for(event)))
        var bottom: float = _staff_center(str(event["staff"]))+gap*2.0
        var line_step: int = -2 if step<0 else 10
        while line_step>=step if step<0 else line_step<=step:
            var line_y: float = Geometry.note_y(line_step,bottom,gap)
            var half: float = maxf(18.0,gap*.95)
            var weight: float = maxf(1.6,gap*.075)
            _fingering_block(Rect2(x-half,line_y-weight*.5,half*2.0,weight),bins,cell)
            line_step += -2 if step<0 else 2
        if not bool(event.get("chord",false)) and not beamed_note_ids.has(id) and kind != "whole":
            var up: bool = bool(_chord_extents(event,gap,cached_head_offsets)["up"])
            var stem: Array = _source_stem_bounds(event,up)
            if stem.size()==4:
                var stem_x: float = anchor+_voice_column_offset(event,gap,cached_head_offsets)
                _fingering_block(Rect2(stem_x+float(stem[0])*unit,y+float(stem[1])*unit,
                    float(stem[2])*unit,float(stem[3])*unit),bins,cell)
            if kind not in ["quarter","half"]:
                # A flagged sprite's enclosing note/stem rectangle contains
                # empty space beside the shaft. Ledger/accidental unions make
                # that empty region even larger. Reserve the authentic flag
                # side of the sprite; heads, ledgers and shaft are separate.
                var chord_key: String = _chord_template_key(event) if chord_members.has(id) else ""
                var envelope: Rect2 = _fingering_nonhead_envelope(kind,up,chord_key)
                var origin: float = anchor+_voice_column_offset(event,gap,cached_head_offsets) if chord_members.has(id) else x
                _fingering_block(Rect2(Vector2(origin,y)+envelope.position*unit,envelope.size*unit),bins,cell)
        if cached_accidental_offsets.has(id):
            var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])])
            box = glyphs.bounds[name]
            var center: float = x+float(cached_accidental_offsets[id])
            _fingering_block(Rect2(center-float(box[2])*unit*.5,y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit),bins,cell)
    box = glyphs.bounds["augmentation_dot"]
    # Chord dots share the painter's rightmost head and distinct staff spaces.
    # The leader reserves the complete group once; other tones keep their
    # independent head/ledger/accidental reservations above.
    if bool(event.get("chord",false)):
        return
    var dot_events: Array = chord_members.get(id,[event]).duplicate()
    var dot_anchors: Dictionary = {}
    if chord_members.has(id):
        dot_events.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        var centers: Array = []
        for member in dot_events:
            centers.append(Vector2(anchor+float(cached_head_offsets.get(str(member["id"]),0.0)),
                _event_y(member,gap)))
        dot_anchors = _chord_dot_anchors(dot_events,centers,gap)
    for member in dot_events:
        var dot_anchor: Vector2 = dot_anchors.get(str(member["id"]),
            Vector2(x,y+(Geometry.rest_dot_offset(kind)*gap if event["kind"] == "rest" else 0.0)))
        var dot_y: float = dot_anchor.y-gap*.24
        for index in range(int(member.get("dots",0))):
            var dot_x: float = dot_anchor.x+gap*(1.05+float(index)*.63)
            _fingering_block(Rect2(dot_x-float(box[2])*unit*.5,dot_y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit),bins,cell)


func _fingering_nonhead_envelope(kind: String, up: bool, chord_key: String = "") -> Rect2:
    # Read the authentic sprite once per template, including faint edge ink.
    # Excluding only its separately reserved head rectangles leaves an exact
    # conservative shaft/flag envelope without a guessed flag-side cutoff.
    var key: String = kind+("_up" if up else "_down")
    var cache_key: String = "note|"+key if chord_key.is_empty() else "chord|"+chord_key
    if fingering_sprite_envelopes.has(cache_key):
        return fingering_sprite_envelopes[cache_key]
    var box: Array = glyphs.note_bounds[key] if chord_key.is_empty() else glyphs.chord_metadata[chord_key]["bounds"]
    var texture: Texture2D = glyphs.note_textures[key] if chord_key.is_empty() else glyphs.chord_textures[chord_key]
    var picture: Image = texture.get_image()
    var pixel := Vector2(float(box[2])/picture.get_width(),float(box[3])/picture.get_height())
    var head_box: Array = glyphs.bounds["head_"+(kind if kind in ["half","whole"] else "black")]
    var positions: Array = [[0.0,0.0]] if chord_key.is_empty() else glyphs.chord_metadata[chord_key]["head_positions"]
    var heads: Array = []
    for position in positions:
        heads.append(Rect2(float(position[0])-float(head_box[2])*.5,
            float(position[1])+float(head_box[1]),float(head_box[2]),float(head_box[3])))
    var envelope := Rect2()
    var found := false
    for row in range(picture.get_height()):
        for column in range(picture.get_width()):
            if picture.get_pixel(column,row).a == 0.0:
                continue
            var point := Vector2(float(box[0]),float(box[1]))+Vector2(column+.5,row+.5)*pixel
            var in_head := false
            for head in heads:
                if head.has_point(point):
                    in_head = true
                    break
            if in_head:
                continue
            var cell := Rect2(point-pixel*.5,pixel)
            envelope = envelope.merge(cell) if found else cell
            found = true
    fingering_sprite_envelopes[cache_key] = envelope
    return envelope


func _layout_fingerings(gap: float) -> void:
    fingering_layout.clear()
    fingering_placement_issues.clear()
    fingering_layout_gap = gap
    fingering_layout_height = size.y
    var cell: float = maxf(64.0,timeline.pixels_per_beat)
    var bins: Dictionary = {}
    _fingering_obstacles(gap,bins,cell)
    var candidates: Array = []
    var physical_keys: Dictionary = {}
    for event in ordered_events:
        var assignment: Dictionary = _fingering_assignment(event)
        if assignment.is_empty():
            continue
        var key: String = "%.8f|%s|%s|%d" % [float(event["beat"]),assignment["hand"],
            str(event.get("midi_pitch",event.get("spelling",{}))),int(assignment["finger"])]
        if physical_keys.has(key):
            physical_keys[key]["event_ids"].append(str(event["id"]))
            continue
        var item: Dictionary = {"event":event,"assignment":assignment,"event_ids":[str(event["id"])]}
        physical_keys[key] = item
        candidates.append(item)
    candidates.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        var ea: Dictionary = a["event"]
        var eb: Dictionary = b["event"]
        if absf(float(ea["beat"])-float(eb["beat"])) > .000001:
            return float(ea["beat"]) < float(eb["beat"])
        if a["assignment"]["hand"] != b["assignment"]["hand"]:
            return a["assignment"]["hand"] < b["assignment"]["hand"]
        var ya: float = _event_y(ea,gap)
        var yb: float = _event_y(eb,gap)
        if absf(ya-yb)<.001:
            return str(ea.get("source_id",ea["id"]))<str(eb.get("source_id",eb["id"]))
        return ya > yb if a["assignment"]["hand"] == "right" else ya < yb)
    var font_size: int = clampi(roundi(gap*.75),11,FINGERING_FONT_SIZE)
    var metrics: Dictionary = _fingering_metrics(font_size)
    var extent: Vector2 = metrics["cell"]
    var ink_offset: Vector2 = metrics["ink_offset"]
    var ink_size: Vector2 = metrics["ink_size"]
    for item in candidates:
        var event: Dictionary = item["event"]
        var assignment: Dictionary = item["assignment"]
        var hand: String = assignment["hand"]
        var head := Vector2(float(event["beat"])*timeline.pixels_per_beat+float(cached_head_offsets.get(str(event["id"]),0.0)),_event_y(event,gap))
        var direction := -1.0 if hand == "right" else 1.0
        var id: String = str(event["id"])
        var up: bool = bool(_chord_extents(event,gap,cached_head_offsets)["up"])
        if voice_stem_up_by_note.has(id):
            direction = -1.0 if up else 1.0
        var chord: bool = bool(event.get("chord",false)) or chord_members.has(id)
        var hint: Dictionary = assignment.get("placement",{}) if assignment.get("placement") is Dictionary else {}
        var placed := false
        for local_search in [false,true]:
            if placed:
                break
            var positions: Array = FingeringPlacement.fallback_candidates(head,ink_size,gap,direction,up) if local_search else \
                FingeringPlacement.candidates(head,ink_size,gap,direction,chord,up,_staff_center(str(event["staff"])),hint)
            for candidate in positions:
                var ink_rect := Rect2(candidate["position"],ink_size)
                var rect := Rect2(ink_rect.position-ink_offset,extent)
                if rect.position.y < 0.0 or rect.end.y > size.y or not _fingering_clear(ink_rect,bins,cell):
                    continue
                fingering_layout.append({"rect":rect,"ink_rect":ink_rect,"head":head,"finger":int(assignment["finger"]),
                    "hand":hand,"event_ids":item["event_ids"],"orientation":candidate["orientation"],
                    "font_size":font_size,"text_offset_x":1.0})
                _fingering_block(ink_rect,bins,cell)
                placed = true
                break
        if not placed:
            fingering_placement_issues.append({"source_id":str(assignment["source_id"]),
                "event_ids":item["event_ids"],"reason":"No local fingering position clears the musical ink"})


func _fingering_metrics(font_size: int) -> Dictionary:
    if fingering_metrics_cache.has(font_size):
        return fingering_metrics_cache[font_size]
    var font: Font = ThemeDB.fallback_font
    var server := TextServerManager.get_primary_interface()
    var ink := Rect2()
    var width := 0.0
    for digit in range(1,6):
        width = maxf(width,font.get_string_size(str(digit),HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x)
        var rid: RID = font.get_rids()[0]
        var glyph: int = server.font_get_glyph_index(rid,font_size,str(digit).unicode_at(0),0)
        var box := Rect2(server.font_get_glyph_offset(rid,Vector2i(font_size,0),glyph),
            server.font_get_glyph_size(rid,Vector2i(font_size,0),glyph))
        ink = box if digit == 1 else ink.merge(box)
    var value := {"cell":Vector2(ceilf(width)+2.0,ceilf(font.get_height(font_size))),
        "ink_offset":Vector2(1.0,font.get_ascent(font_size))+ink.position,"ink_size":ink.size}
    fingering_metrics_cache[font_size] = value
    return value


func _paint_fingerings(clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0) -> void:
    if not fingering_annotations_enabled:
        return
    if absf(fingering_layout_gap-gap) > .001 or absf(fingering_layout_height-size.y) > .001:
        _layout_fingerings(gap)
    var translation := Vector2(timeline.screen_x(0.0,clock,playhead_x,play_from_beat),0.0)
    paint_pass_index = pass_index
    paint_pass_start = pass_start
    current_preparation = preparation_history.get(pass_start,{}) if score_loop_enabled else {}
    for item in fingering_layout:
        if not _practice_event_visible(expression_note_index.get(str(item["event_ids"][0]),{})):
            continue
        var rect: Rect2 = item["rect"]
        rect.position += translation
        # A partial numeral can look like a different finger. Keep annotation
        # cells whole at the brace and viewport edges, without reflowing them.
        if rect.position.x < 30.0 or rect.end.x > size.x:
            continue
        var ink: Color = _ink(str(item["hand"]))
        if item["hand"] == "left":
            ink = ink.lerp(Design.BLUE,.32)
        var font_size: int = int(item["font_size"])
        draw_string(ThemeDB.fallback_font,rect.position+Vector2(1.0,ThemeDB.fallback_font.get_ascent(font_size)),
            str(item["finger"]),HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
        var shown: Dictionary = item.duplicate()
        shown["pass_index"] = pass_index
        shown["rect"] = rect
        shown["head"] = item["head"]+translation
        shown["ink_rect"] = Rect2(item["ink_rect"].position+translation,item["ink_rect"].size)
        drawn_fingerings.append(shown)


func _fill_fingering_menu(menu: PopupMenu, event: Dictionary) -> void:
    var assignment: Dictionary = _fingering_assignment(event)
    menu.add_item(_performing_hand(event).capitalize()+" hand · fingering", 100)
    menu.set_item_disabled(0,true)
    for finger in range(1,6):
        menu.add_radio_check_item(str(finger),finger)
        menu.set_item_checked(menu.item_count-1,int(assignment.get("finger",0)) == finger)
    menu.add_separator()
    menu.add_item("Use original / automatic",0)
    menu.id_pressed.connect(func(finger: int):
        fingering_change_requested.emit(_fingering_source(event),null if finger == 0 else finger)
        fingering_popup.hide())


func _open_fingering_editor(point: Vector2) -> bool:
    if not fingering_annotations_enabled:
        return false
    var selected: Dictionary = {}
    var radius: float = maxf(12.0,_gap()*.8)
    for item in drawn_fingerings:
        if item["rect"].grow(5.0).has_point(point):
            for id in item["event_ids"]:
                selected[id] = true
    for instance in drawn_note_instances:
        if instance["position"].distance_to(point) <= radius:
            selected[instance["event_id"]] = true
    var targets: Array = []
    var sources: Dictionary = {}
    for id in selected:
        var event: Dictionary = expression_note_index.get(str(id),{})
        var source: String = _fingering_source(event)
        if not bool(event.get("is_attack",false)) or source.is_empty() or sources.has(source):
            continue
        sources[source] = true
        targets.append(event)
    if targets.is_empty():
        return false
    if fingering_popup != null:
        remove_child(fingering_popup)
        fingering_popup.queue_free()
    fingering_popup = PopupMenu.new()
    add_child(fingering_popup)
    if targets.size() == 1:
        _fill_fingering_menu(fingering_popup,targets[0])
    else:
        for i in range(targets.size()):
            var event: Dictionary = targets[i]
            var submenu := PopupMenu.new()
            submenu.name = "Note%d" % i
            fingering_popup.add_child(submenu)
            _fill_fingering_menu(submenu,event)
            var pitch: Dictionary = event.get("spelling",{})
            fingering_popup.add_submenu_item("%s · voice %s · %s%s" % [
                _performing_hand(event).capitalize(),str(event.get("voice","1")),
                str(pitch.get("step","")),str(pitch.get("octave",""))],submenu.name)
    var screen: Vector2 = get_screen_transform()*point
    fingering_popup.popup(Rect2i(Vector2i(screen),Vector2i.ZERO))
    return true


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
    return ""


func _engraved_beam_groups(model: Dictionary) -> Dictionary:
    return ScoreIndex.source_beam_groups(model, glyphs)


func _staff_center(hand: String) -> float:
    return size.y * (.36 if hand == "right" else .69)

func _gap() -> float:
    if cached_staff_gap > 0.0 and absf(cached_gap_height - size.y) < .001:
        return cached_staff_gap
    # Reserve actual room for ledger notes ABOVE and BELOW both staves.
    # The former raster crop clipped high notes because it only knew staff
    # rails, not the extreme noteheads. Fit the full semantic pitch range
    # once per frame/viewport, uniformly for both hands.
    var gap: float = clampf(size.y * .042, 8.5, staff_gap_limit)
    if timeline.model.is_empty():
        return gap
    var onset_ink: Dictionary = {}
    for event in ordered_events:
        var staff: String = str(event.get("staff", "right"))
        var center: float = _staff_center(staff)
        var accidentals: Dictionary = {}
        if str(event.get("accidental","")) in Geometry.ACCIDENTAL_GLYPHS:
            accidentals[str(event["id"])] = 0.0
        var unit_ink: Rect2 = _event_ink_rect(event,1.0,{},accidentals)
        var at: float = float(event["beat"])
        if not onset_ink.has(at):
            onset_ink[at] = {}
        var hull: Vector2 = onset_ink[at].get(staff,Vector2(INF,-INF))
        onset_ink[at][staff] = Vector2(minf(hull.x,unit_ink.position.y-center),
            maxf(hull.y,unit_ink.end.y-center))
        if str(event.get("kind", "")) != "note":
            continue
        var clef: Dictionary = _clef_for(staff, _measure_for(event))
        var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
        var factor: float = 2.0 - float(step)*.5
        var assignment: Dictionary = _fingering_assignment(event)
        var above: float = 45.0 if not assignment.is_empty() and assignment["hand"] == "right" else 32.0
        var below: float = 45.0 if not assignment.is_empty() and assignment["hand"] == "left" else 32.0
        if factor < -.001:
            gap = minf(gap, (center-above) / -factor)
        elif factor > .001:
            gap = minf(gap, (size.y-below-center) / factor)
        # Ink coordinates at unit staff spacing scale linearly around the
        # display staff's fixed centre. Empty horizontal-offset maps avoid
        # invoking the offset/density layout while this gap is being fitted.
        # The complete authentic sprite includes its shaft/flag and cap;
        # a fixed notehead margin alone cannot contain a low down-stem note.
        gap = _fit_vertical_ink_gap(gap,staff,unit_ink)
    # Beamed shafts can be stretched beyond an isolated note template.
    # Reserve the same source fragment and endpoint extents as the painter.
    for group in beam_groups:
        var ids := PackedStringArray()
        for event in group:
            ids.append(str(event["id"]))
        var info: Dictionary = glyphs.beam_metadata.get("|".join(ids),{})
        if info.is_empty():
            continue
        var first: Dictionary = group[0]
        var box: Array = info["bounds"]
        gap = _fit_vertical_ink_gap(gap,str(first["staff"]),Rect2(0.0,
            _event_y(first,1.0)+float(box[1])/250.0,1.0,float(box[3])/250.0))
        var tips: Array = info["tip_offsets"]
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var extents: Dictionary = _chord_extents(event,1.0)
            var head: float = float(extents["bottom_y" if info["stem_up"] else "top_y"])
            var tip: float = head+float(tips[index])/250.0
            gap = _fit_vertical_ink_gap(gap,str(event["staff"]),Rect2(0.0,minf(head,tip),1.0,absf(head-tip)))
    # Simultaneous ink must also fit BETWEEN the fixed staff centres. Source
    # shafts/chord sprites stay authentic; scale the entire score uniformly.
    var staff_distance: float = _staff_center("left")-_staff_center("right")
    for lanes in onset_ink.values():
        if not lanes.has("right") or not lanes.has("left"):
            continue
        var difference: float = lanes["right"].y-lanes["left"].x
        if difference>0.0:
            gap = minf(gap,(staff_distance-3.0)/difference)
    # A note that truly cannot fit is still drawn deterministically; the
    # score is not cropped, and no horizontal position can change.
    cached_staff_gap = maxf(5.0, gap)
    cached_gap_height = size.y
    return cached_staff_gap


func _fit_vertical_ink_gap(limit: float, staff: String, unit_ink: Rect2) -> float:
    var center: float = _staff_center(staff)
    var top: float = unit_ink.position.y-center
    var bottom: float = unit_ink.end.y-center
    if top<-.001:
        limit = minf(limit,(center-3.0)/-top)
    if bottom>.001:
        limit = minf(limit,(size.y-3.0-center)/bottom)
    return limit


func _clef_for(staff: String, measure: Dictionary) -> Dictionary:
    var clefs: Dictionary = measure.get("clefs", {})
    return clefs.get(staff, {
        "sign":"G" if staff == "right" else "F",
        "line":2 if staff == "right" else 4, "octave_change":0})

func _measure_for(event: Dictionary) -> Dictionary:
    var number: int = int(event.get("measure", -1))
    return measure_by_number.get(number, timeline.measures[0])

func _event_y(event: Dictionary, gap: float) -> float:
    var staff: String = str(event.get("staff", "right"))
    var measure: Dictionary = _measure_for(event)
    var clef: Dictionary = _clef_for(staff, measure)
    var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
    var bottom: float = _staff_center(staff) + 2.0 * gap
    return Geometry.note_y(step, bottom, gap)

func _performing_hand(event: Dictionary) -> String:
    # The source performer is independent of the staff chosen for engraving.
    # Note-linked marks inherit that performer, including older expression
    # payloads whose `hand` field described only their display lane.
    var linked: String = str(event.get("note_id",event.get("before_note_id","")))
    var owner: Dictionary = expression_note_index.get(linked,event)
    return str(owner.get("hand",owner.get("staff","right")))


func _display_staff(event: Dictionary) -> String:
    var linked: String = str(event.get("note_id",event.get("before_note_id","")))
    var owner: Dictionary = expression_note_index.get(linked,event)
    return str(owner.get("staff",owner.get("hand","right")))


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
    var info: Dictionary = BarlineLayout.boundary(timeline.measures, measure, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = _barline_segments(str(info.get("style","regular")),gap)
    return info


func _terminal_barline_geometry(clock: float,
        playhead_x: float, gap: float) -> Dictionary:
    var info: Dictionary = BarlineLayout.terminal(timeline.measures, timeline,
        clock, playhead_x, play_from_beat, gap,
        _staff_center("right")-2.0*gap,
        _staff_center("left")+2.0*gap)
    if not info.is_empty():
        info["segments"] = _barline_segments(str(info.get("style","regular")),gap)
    return info


func _barline_segments(style: String, gap: float) -> Array:
    if style in ["tick","short"]:
        var segments: Array = []
        for staff in ["right","left"]:
            var center: float = _staff_center(staff)
            segments.append({
                "top":center-gap*(2.5 if style == "tick" else 1.0),
                "bottom":center-gap*1.5 if style == "tick" else center+gap})
        return segments
    return [{"top":_staff_center("right")-2.0*gap,
        "bottom":_staff_center("left")+2.0*gap}]


func _barline_strokes(style: String, gap: float) -> Array:
    return BarlineLayout.strokes(style, gap)


func _paint_barline(info: Dictionary, gap: float) -> void:
    if info.is_empty():
        return
    var style: String = str(info.get("style","regular"))
    var bars: Array = _barline_strokes(style,gap)
    if bars.is_empty():
        return
    var x: float = float(info["x"])
    var ink: Color = Color(DIM_INK,.76)
    for stroke in bars:
        var sx: float = x+float(stroke["offset"])
        var width: float = float(stroke["width"])
        for segment in info.get("segments",_barline_segments(style,gap)):
            var top: float = float(segment["top"])
            var bottom: float = float(segment["bottom"])
            if style in ["dashed","dotted"]:
                var length: float = gap*(.65 if style=="dashed" else .13)
                var skip: float = gap*(.35 if style=="dashed" else .27)
                var at: float = top
                while at < bottom:
                    draw_line(Vector2(sx,at),Vector2(sx,minf(bottom,at+length)),
                        ink,width,true)
                    at += length+skip
            else:
                draw_line(Vector2(sx,top),Vector2(sx,bottom),ink,width,true)
    var repetition: String = str(info.get("repeat",""))
    if repetition not in ["forward","backward","both"]:
        return
    var positions: Array = []
    if repetition in ["backward","both"]:
        positions.append(x-gap*.92)
    if repetition in ["forward","both"]:
        positions.append(x+gap*.56)
    var box: Array = glyphs.bounds.get("repeat_dot",[])
    if box.size()!=4:
        return
    var unit: float = gap/250.0
    var center_offset: float = (float(box[1])+float(box[3])*.5)*unit
    for dot_x in positions:
        for staff in ["right","left"]:
            var middle: float = _staff_center(staff)
            for dot_y in [middle-gap*.5,middle+gap*.5]:
                glyphs.paint(self,"repeat_dot",float(dot_x),
                    dot_y-center_offset,gap,ink,true)


# Meter changes need room to the LEFT of the next attack. A short
# pickup (e.g. Chopin 1/8 -> 12/8) has no such room on a fixed beat grid.
# Keep the music clock immutable and engrave that exceptional meter in an
# upper annotation lane instead of stacking numbers over the noteheads.
func _meter_is_crowded(measure: Dictionary, previous: Dictionary,
        gap: float) -> bool:
    if previous.is_empty() or previous.get("meter", []) == measure.get("meter", []):
        return false
    var at: float = float(measure.get("start_beat", 0.0))
    var previous_start: float = float(previous.get("start_beat", 0.0))
    var advance: float = timeline.pixels_per_beat
    if (at-previous_start)*advance < gap*7.0:
        return true
    var last_attack: float = float(previous_attack_before_measure.get(
        int(measure.get("number", 0)), -INF))
    return is_finite(last_attack) and \
        (at-last_attack)*advance < gap*6.0


func _paint_meter_above_staff(measure: Dictionary, x: float,
        gap: float) -> void:
    var meter: Array = measure.get("meter", [4,4])
    if meter.size() < 2:
        return
    # Actual Verovio time-signature digit textures, scaled together and
    # arranged ABOVE the upper five lines, not GUI text or invented glyphs.
    var center: float = _staff_center("right")
    var origin: float = x-gap*1.75
    var space: float = gap*.72
    # Meter applies to BOTH staves and must remain readable while one
    # of the hands is dimmed for separate-handed practice.
    _paint_meter_number(int(meter[0]),origin,center-gap*4.50,
        NOTE_INK,space)
    _paint_meter_number(int(meter[1]),origin,center-gap*3.05,
        NOTE_INK,space)


func _paint_ledger(x: float, y: float, step: int,
        bottom: float, gap: float, ink: Color) -> void:
    # At this staff size a fixed ±14 px rule almost disappears under
    # real Verovio notehead ink. Let each ledger line extend clearly.
    var half_width: float = maxf(18.0,gap*.95)
    var weight: float = maxf(1.6,gap*.075)
    if step < 0:
        var line_step: int = -2
        while line_step >= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            draw_line(Vector2(x-half_width,line_y),
                Vector2(x+half_width,line_y), Color(ink,.94), weight,true)
            line_step -= 2
    elif step > 8:
        var line_step: int = 10
        while line_step <= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            draw_line(Vector2(x-half_width,line_y),
                Vector2(x+half_width,line_y), Color(ink,.94), weight,true)
            line_step += 2

func _paint_accidental(x: float, y: float,
        value: String, ink: Color, gap: float,
        head_offset: float = INF) -> void:
    var name: String = str(Geometry.ACCIDENTAL_GLYPHS.get(value, ""))
    if not name.is_empty():
        var offset: float = head_offset if is_finite(head_offset) else -gap*1.15
        glyphs.paint(self, name, x+offset, y, gap, ink, true)


func _paint_note_accidental(event: Dictionary, x: float, y: float,
        ink: Color, gap: float) -> void:
    var accidental: String = str(event.get("accidental",""))
    if not accidental.is_empty() and accidental != "null":
        _paint_accidental(x,y,accidental,ink,gap,
            float(cached_accidental_offsets.get(str(event.get("id","")),-gap*1.15)))


func _paint_rhythm_dots(x: float, y: float, dots: int,
        ink: Color, gap: float) -> void:
    for index in range(dots):
        glyphs.paint(self, "augmentation_dot",
            x+gap*1.05+float(index)*gap*.63, y-gap*.24,
            gap, ink, true)


func _paint_tuplet_brackets(clock: float, playhead_x: float,
        gap: float) -> void:
    # Authentic separated Verovio number/bracket masks only. Every group
    # was validated on lesson load; no Godot-drawn ratio, digit or hook.
    for group in notation_tuplets:
        if _tuplet_hidden(group):
            continue
        var events: Array = group.get("events",[])
        if events.is_empty():
            continue
        var ids := PackedStringArray()
        for event in events:
            ids.append(str(event.get("id","")))
        var first: Dictionary = events[0]
        var last: Dictionary = events[-1]
        if not _practice_span_visible(first,last):
            continue
        var x0: float = timeline.screen_x(
            float(first.get("beat",0.0)),clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(
            float(last.get("beat",0.0)),clock,playhead_x,play_from_beat)
        if str(first.get("kind","")) == "note":
            x0 += _voice_column_offset(first,gap,cached_head_offsets)
        if str(last.get("kind","")) == "note":
            x1 += _voice_column_offset(last,gap,cached_head_offsets)
        if x1 < -50.0 or x0 > size.x+50.0:
            continue
        glyphs.paint_tuplet(self,"|".join(ids),x0,x1,
            _rest_y(first,gap) if str(first.get("kind","")) == "rest" else _event_y(first,gap),gap,
            _event_ink(first))


func _tuplet_hidden(group: Dictionary) -> bool:
    return str(group.get("show_number","actual")) == "none" and \
        str(group.get("bracket","yes")) == "no"


func _paint_rest(x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    glyphs.paint(self, "rest_" + note_type, x, y, gap, ink, true)
    _paint_rhythm_dots(x, y+Geometry.rest_dot_offset(note_type)*gap,
        dots, ink, gap)


func _rest_y(event: Dictionary, gap: float) -> float:
    # The Verovio source glyph is positioned by its staff-line origin.
    # Multi-voice offsets are extra staff spaces, never arbitrary pixels.
    return _staff_center(str(event.get("staff","right"))) + gap * (
        Geometry.rest_staff_offset(str(event.get("note_type","quarter"))) +
        float(rest_lane_offsets.get(str(event.get("id","")),0.0)))


func _layout_rest_lanes(gap: float, density: float) -> void:
    rest_lane_offsets.clear()
    unavoidable_rest_overlaps = 0
    var heads: Dictionary = _engraved_head_offsets(gap)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        ordered_events,gap,heads,glyphs.bounds)
    var voices_by_measure: Dictionary = {}
    var obstacles: Dictionary = {}
    for event in ordered_events:
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        if not voices_by_measure.has(lane_key):
            voices_by_measure[lane_key] = {}
            obstacles[lane_key] = []
        var voice: String = str(event.get("voice","1"))
        voices_by_measure[lane_key][voice] = true
        if str(event.get("kind","")) != "note":
            continue
        var ink: Rect2 = _event_ink_rect(event,gap,heads,accidentals)
        ink.position.x += float(event.get("beat",0.0))*density
        obstacles[lane_key].append({"voice":voice,"ink":ink})
    # Placing rests after source note ink means their voice-lane choice
    # is deterministic and cannot move MIDI attacks, beams or noteheads.
    for event in ordered_events:
        if str(event.get("kind","")) != "rest":
            continue
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        var voice: String = str(event.get("voice","1"))
        var voices: Array = voices_by_measure[lane_key].keys()
        voices.sort()
        var voice_index: int = voices.find(voice)
        var preferred := 0.0
        var direction := -1.0
        if voices.size() > 1:
            direction = -1.0 if voice_index % 2 == 0 else 1.0
            preferred = direction*(1.0+floorf(float(voice_index)/2.0))
        var candidates: Array = [preferred]
        # Half/whole rectangles derive their value from sitting on or
        # hanging below a staff line. A half-space displacement exchanges
        # those two meanings even though the same texture is painted.
        var lane_step: float = (1.0 if str(event.get("note_type","")) in
            ["whole","half"] else .5)
        for step in range(1,15):
            candidates.append(preferred+direction*float(step)*lane_step)
            candidates.append(preferred-direction*float(step)*lane_step)
        var placed := false
        var best_score := INF
        var best_shift: float = preferred
        var best_rect := Rect2()
        for shift in candidates:
            rest_lane_offsets[str(event.get("id",""))] = shift
            var rect: Rect2 = _event_ink_rect(event,gap,heads,accidentals)
            rect.position.x += float(event.get("beat",0.0))*density
            var overlap_area := 0.0
            for blocker in obstacles[lane_key]:
                if str(blocker["voice"]) == voice:
                    continue
                var other: Rect2 = blocker["ink"]
                if rect.intersects(other.grow(gap*.06)):
                    var overlap: Rect2 = rect.intersection(other.grow(gap*.06))
                    overlap_area += overlap.size.x*overlap.size.y
            var score: float = overlap_area+absf(float(shift)-preferred)*gap*gap*.02
            if score < best_score:
                best_score = score
                best_shift = float(shift)
                best_rect = rect
            if overlap_area <= .00001:
                obstacles[lane_key].append({"voice":voice,"ink":rect})
                placed = true
                break
        if not placed:
            # A score can contain an unavoidable collision among polyphonic
            # voices with huge ledger notes. Do not discard every source
            # attack or fall back solely for a rest: use minimum overlap.
            rest_lane_offsets[str(event.get("id",""))] = best_shift
            obstacles[lane_key].append({"voice":voice,"ink":best_rect})
            unavoidable_rest_overlaps += 1


func _paint_clef(x: float, center: float, clef: Dictionary,
        gap: float, ink: Color) -> void:
    var sign: String = str(clef.get("sign","G"))
    var line: int = int(clef.get("line", 2 if sign == "G" else 4 if sign == "F" else 3))
    var octave: int = int(clef.get("octave_change",0))
    var name: String = {"G":"clef_g", "F":"clef_f", "C":"clef_c"}.get(sign, "")
    if name.is_empty() or line < 1 or line > 5:
        return
    # The reference mark is exactly MusicXML's numbered staff line:
    # 1 is bottom, 5 is top. Changing it must NOT transpose note time.
    var origin_y: float = center+(3.0-float(line))*gap
    var variant: String = ""
    if octave == -1:
        variant = name+"_8vb"
    elif octave == 1:
        variant = name+"_8va"
    elif octave == -2:
        variant = name+"_15mb"
    elif octave == 2:
        variant = name+"_15ma"
    if not variant.is_empty() and glyphs.textures.has(variant):
        name = variant
    glyphs.paint(self,name,x,origin_y,gap,ink,true)
    # No separate clef numeral is available in installed Leipzig. Any
    # unsupported combined variant must be rejected by Geometry.supported.


func _paint_meter_number(value: int, x: float, y: float,
        ink: Color, gap: float) -> void:
    # Real Verovio time-signature digits rather than generic GUI text.
    var digits: String = str(value)
    var advance: float = gap*1.10
    var start: float = x - float(digits.length()-1)*advance*.5
    for digit in range(digits.length()):
        glyphs.paint(self, "time_" + digits[ digit ],
            start + float(digit)*advance, y, gap, ink, true)


func _stem_attachment(note_type: String, gap: float, up: bool) -> float:
    # The musical anchor is the centred original Verovio notehead. Derive
    # its edge from that glyph's actual metrics rather than a hand-estimated
    # constant. The font asset includes 12 units of transparent padding.
    var name: String = ("head_whole" if note_type == "whole" else
        "head_half" if note_type == "half" else "head_black")
    var box: Array = glyphs.bounds.get(name, [])
    var half_width: float = gap*.61
    if box.size() == 4 and float(box[2]) > 24.0:
        half_width = (float(box[2])*.5-12.0)*gap/250.0
    return half_width if up else -half_width


func _source_stem_bounds(event: Dictionary, up: bool) -> Array:
    if chord_members.has(str(event.get("id",""))):
        return glyphs.chord_stem_bounds.get(_chord_template_key(event),[])
    var key: String = str(event.get("note_type","eighth"))+(
        "_up" if up else "_down")
    return glyphs.note_stem_bounds.get(key,[])


# Two independent simultaneous voices need separate shafts even when both
# lie on the same side of the staff. Index once per score, never per frame.
# Source beam and explicit stem directions remain authoritative.
func _polyphonic_stem_directions() -> Dictionary:
    var onsets: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) != "note" or \
                bool(event.get("chord",false)) or \
                str(event.get("note_type","")) in ["whole","breve","long","maxima"]:
            continue
        var key: String = "%s|%s|%.8f" % [event.get("staff","right"),
            event.get("measure",0),float(event.get("beat",0.0))]
        if not onsets.has(key):
            onsets[key] = []
        onsets[key].append(event)
    var directions: Dictionary = {}
    for leaders in onsets.values():
        if leaders.size() != 2 or \
                str(leaders[0].get("voice","1")) == str(leaders[1].get("voice","1")):
            continue
        leaders.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return str(a.get("voice","1")).naturalnocasecmp_to(str(b.get("voice","1"))) < 0)
        var ranges: Array = []
        for leader in leaders:
            var low := INF
            var high := -INF
            var members: Array = chord_members.get(str(leader.get("id","")),[leader])
            for member in members:
                var y: float = _event_y(member,1.0)
                low = minf(low,y)
                high = maxf(high,y)
            ranges.append(Vector2(low,high))
        var upper: int = -1
        if ranges[0].y < ranges[1].x:
            upper = 0
        elif ranges[1].y < ranges[0].x:
            upper = 1
        if upper < 0:
            # Overlapping voices still require independent shafts. Use the
            # source voice order when pitch ranges cannot choose the upper
            # voice; explicit stems and source beams override this default.
            upper = 0
        for i in range(2):
            var members: Array = chord_members.get(str(leaders[i].get("id","")),[leaders[i]])
            for member in members:
                directions[str(member.get("id",""))] = i == upper
    return directions


# Pitch extrema determine an isolated chord's default stem, not the arbitrary
# first note in MusicXML. Polyphonic voices use the indexed separate shafts.
# The complete head/stem artwork still comes from Verovio.
func _chord_extents(event: Dictionary, gap: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    var members: Array = chord_members.get(str(event.get("id", "")), [event])
    var top_y := INF
    var bottom_y := -INF
    var top_offset := 0.0
    var bottom_offset := 0.0
    var sum_step := 0.0
    var explicit_stem := ""
    for member in members:
        if str(member.get("stem","")) in ["up","down"]:
            explicit_stem = str(member["stem"])
        var head_y: float = _event_y(member, gap)
        var offset: float = float(head_offsets.get(str(member.get("id", "")), 0.0))
        if head_y < top_y:
            top_y = head_y
            top_offset = offset
        if head_y > bottom_y:
            bottom_y = head_y
            bottom_offset = offset
        var clef: Dictionary = _clef_for(
            str(member.get("staff", "right")), _measure_for(member))
        sum_step += float(Geometry.staff_step(
            member.get("spelling", {}),clef))
    return {"top_y":top_y,"bottom_y":bottom_y,
        "top_offset":top_offset,"bottom_offset":bottom_offset,
        "up":explicit_stem == "up" if not explicit_stem.is_empty() else
            bool(voice_stem_up_by_note.get(str(event.get("id","")),
                sum_step/float(maxi(1,members.size())) < 4.0))}


# Chord sprites are keyed by their diatonic interval signature, which is
# invariant under octave transposition. Godot places only Verovio ink.
func _chord_template_key(event: Dictionary) -> String:
    var notes: Array = chord_members.get(str(event.get("id","")),[])
    if notes.size() < 2 or notes.size() > 10:
        return ""
    var leader: int = Geometry.diatonic_index(event.get("spelling",{}))
    if leader < 0:
        return ""
    var differences: Array[int] = []
    for head in notes:
        if str(head.get("note_type","")) != str(event.get("note_type","")):
            return ""
        differences.append(Geometry.diatonic_index(
            head.get("spelling",{}))-leader)
    differences.sort()
    if differences.size() < 2 or differences[-1]-differences[0] > 28:
        return ""
    for i in range(1,differences.size()):
        if differences[i] == differences[i-1]:
            return ""
    var names: PackedStringArray = []
    for value in differences:
        names.append(str(value))
    var extents: Dictionary = _chord_extents(event,1.0)
    # A source beam can force a chord opposite to its isolated pitch rule.
    # Its direction selects BOTH displaced heads and the stem-side mask,
    # including during load validation, before a frame has been painted.
    var up: bool = bool(beam_stem_up_by_note.get(
        str(event.get("id","")),extents["up"]))
    var direction: String = "up" if up else "down"
    return "%s|%s|%s" % [
        str(event.get("note_type","quarter")),direction,",".join(names)]


func _engraved_head_offsets(gap: float) -> Dictionary:
    # All attachments use the SAME original head centres as the compound
    # sprite. Estimated second/unison spacing moves ties and slurs away
    # from the ink even though the musical beat itself is unchanged.
    var offsets: Dictionary = {}
    for leader_id in chord_members:
        var members: Array = chord_members[leader_id].duplicate()
        var leader: Dictionary = {}
        for member in members:
            if str(member.get("id","")) == str(leader_id):
                leader = member
                break
        var positions: Array = glyphs.chord_heads(_chord_template_key(leader))
        if positions.size() != members.size():
            continue
        members.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < \
                Geometry.diatonic_index(b.get("spelling",{})))
        for i in range(members.size()):
            offsets[str(members[i].get("id",""))] = \
                float(positions[i][0])*gap/250.0
    var columns: Dictionary = _polyphonic_column_offsets(gap,offsets)
    for id in columns:
        offsets[id] = float(offsets.get(id,0.0))+float(columns[id])
    return offsets


func _head_family(event: Dictionary) -> String:
    var kind: String = str(event.get("note_type","quarter"))
    return "head_"+(kind if kind in ["whole","half"] else "black")


func _polyphonic_column_offsets(gap: float, heads: Dictionary) -> Dictionary:
    # Translate complete source voice columns, never individual chord tones.
    # A filled head cannot cover a hollow unison. Equal heads may share only
    # with opposing stems; equal-direction shafts need separate columns too.
    var onsets: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) != "note" or bool(event.get("chord",false)):
            continue
        var key: String = "%s|%s|%.8f" % [event.get("staff","right"),
            event.get("measure",0),float(event.get("beat",0.0))]
        if not onsets.has(key):
            onsets[key] = []
        onsets[key].append(event)
    var result: Dictionary = {}
    for leaders in onsets.values():
        if leaders.size() < 2:
            continue
        leaders.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            var a_up: bool = bool(beam_stem_up_by_note.get(str(a.get("id","")),_chord_extents(a,gap)["up"]))
            var b_up: bool = bool(beam_stem_up_by_note.get(str(b.get("id","")),_chord_extents(b,gap)["up"]))
            if a_up != b_up:
                return not a_up
            return str(a.get("voice","1")).naturalnocasecmp_to(str(b.get("voice","1"))) < 0)
        var placed: Array = []
        var shifts: Array[float] = []
        var links: Dictionary = {}
        for leader in leaders:
            var index: int = placed.size()
            links[index] = []
            var members: Array = chord_members.get(str(leader.get("id","")),[leader])
            var up: bool = bool(beam_stem_up_by_note.get(str(leader.get("id","")),_chord_extents(leader,gap)["up"]))
            var shift := 0.0
            for previous in placed:
                if str(previous["leader"].get("voice","1")) == str(leader.get("voice","1")):
                    continue
                for member in members:
                    for other in previous["members"]:
                        if absf(_event_y(member,gap)-_event_y(other,gap)) > gap*.51:
                            continue
                        var same_pitch: bool = absf(_event_y(member,gap)-_event_y(other,gap)) < .001
                        if same_pitch and _head_family(member) == _head_family(other) and up != bool(previous["up"]):
                            continue
                        if not int(previous["index"]) in links[index]:
                            links[index].append(int(previous["index"]))
                            links[int(previous["index"])].append(index)
                        var box: Array = glyphs.bounds[_head_family(member)]
                        var other_box: Array = glyphs.bounds[_head_family(other)]
                        var left: float = float(heads.get(str(member.get("id","")),0.0))-float(box[2])*gap/500.0
                        var right: float = float(heads.get(str(other.get("id","")),0.0))+float(other_box[2])*gap/500.0
                        shift = maxf(shift,right+float(previous["shift"])+gap*.20-left)
            placed.append({"leader":leader,"members":members,"up":up,"shift":shift,"index":index})
            shifts.append(shift)
        var centers: Dictionary = {}
        for i in range(placed.size()):
            if centers.has(i):
                continue
            var pending: Array = [i]
            var component: Dictionary = {}
            var minimum := INF
            var maximum := -INF
            while not pending.is_empty():
                var index: int = int(pending.pop_back())
                if component.has(index):
                    continue
                component[index] = true
                minimum = minf(minimum,shifts[index])
                maximum = maxf(maximum,shifts[index])
                pending.append_array(links[index])
            for index in component:
                centers[index] = (minimum+maximum)*.5
        for i in range(placed.size()):
            for member in placed[i]["members"]:
                result[str(member.get("id",""))] = shifts[i]-float(centers[i])
    return result


func _voice_column_offset(event: Dictionary, gap: float, heads: Dictionary) -> float:
    var id: String = str(event.get("id",""))
    var intrinsic := 0.0
    var members: Array = chord_members.get(id,[]).duplicate()
    var positions: Array = glyphs.chord_heads(_chord_template_key(event))
    if positions.size() == members.size():
        members.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        for i in range(members.size()):
            if str(members[i].get("id","")) == id:
                intrinsic = float(positions[i][0])*gap/250.0
    return float(heads.get(id,0.0))-intrinsic


func _event_ink_rect(event: Dictionary, gap: float,
        heads: Dictionary, accidentals: Dictionary) -> Rect2:
    var unit: float = gap/250.0
    var id: String = str(event.get("id",""))
    var kind: String = str(event.get("note_type","quarter"))
    var head_x: float = float(heads.get(id,0.0))
    var box: Array = []
    if str(event.get("kind","")) == "rest":
        box = glyphs.bounds["rest_"+kind]
        var y: float = _rest_y(event,gap)
        var left := -float(box[2])*unit*.5
        var right := float(box[2])*unit*.5
        var top := y+float(box[1])*unit
        var bottom := top+float(box[3])*unit
        var dots: int = int(event.get("dots",0))
        if dots > 0:
            var dot: Array = glyphs.bounds["augmentation_dot"]
            var dot_y: float = y+gap*(
                Geometry.rest_dot_offset(kind)-.24)
            top = minf(top,dot_y+float(dot[1])*unit)
            bottom = maxf(bottom,dot_y+float(dot[1]+dot[3])*unit)
            right = maxf(right,gap*(1.05+float(dots-1)*.63)+
                float(dot[2])*unit*.5)
        return _with_single_tuplet_ink(event,Rect2(left,top,right-left,bottom-top),gap)
    if chord_members.has(id):
        var key: String = _chord_template_key(event)
        box = glyphs.chord_heads_bounds[key] if beamed_note_ids.has(id) else \
            glyphs.chord_metadata[key]["bounds"]
    elif not bool(event.get("chord",false)) and not beamed_note_ids.has(id):
        var up: bool = bool(_chord_extents(event,gap)["up"])
        var key: String = "whole" if kind == "whole" else kind+(
            "_up" if up else "_down")
        box = glyphs.note_bounds[key]
    var head_box: Array = glyphs.bounds["head_"+(
        kind if kind in ["whole","half"] else "black")]
    var left: float = head_x-float(head_box[2])*unit*.5
    var right: float = head_x+float(head_box[2])*unit*.5
    var y: float = _event_y(event,gap)
    var top: float = y+float(head_box[1])*unit
    var bottom: float = y+(float(head_box[1])+float(head_box[3]))*unit
    var sprite_x: float = _voice_column_offset(event,gap,heads) if chord_members.has(id) else head_x
    if box.size() == 4:
        left = minf(left,sprite_x+float(box[0])*unit)
        right = maxf(right,sprite_x+(float(box[0])+float(box[2]))*unit)
        top = minf(top,y+float(box[1])*unit)
        bottom = maxf(bottom,y+(float(box[1])+float(box[3]))*unit)
    if beamed_note_ids.has(id):
        var stem: Array = _source_stem_bounds(event,bool(beam_stem_up_by_note[id]))
        left = minf(left,sprite_x+float(stem[0])*unit)
        right = maxf(right,sprite_x+(float(stem[0])+float(stem[2]))*unit)
        top = minf(top,y+float(stem[1])*unit)
        bottom = maxf(bottom,y+(float(stem[1])+float(stem[3]))*unit)
    var step: int = Geometry.staff_step(event.get("spelling",{}),
        _clef_for(str(event.get("staff","right")),_measure_for(event)))
    if step <= -2 or step >= 10:
        left = minf(left,head_x-maxf(18.0,gap*.95))
        right = maxf(right,head_x+maxf(18.0,gap*.95))
        var staff_bottom: float = _staff_center(str(event.get("staff","right")))+2.0*gap
        if step <= -2:
            top = minf(top,Geometry.note_y(-2,staff_bottom,gap)-.675)
        else:
            bottom = maxf(bottom,Geometry.note_y(10,staff_bottom,gap)+.675)
    if accidentals.has(id):
        var name: String = str(Geometry.ACCIDENTAL_GLYPHS[str(event["accidental"])])
        var width: float = float(glyphs.bounds[name][2])*unit
        var center: float = head_x+float(accidentals[id])
        left = minf(left,center-width*.5)
        right = maxf(right,center+width*.5)
        top = minf(top,y+float(glyphs.bounds[name][1])*unit)
        bottom = maxf(bottom,y+(float(glyphs.bounds[name][1])+ \
            float(glyphs.bounds[name][3]))*unit)
    var dots: int = int(event.get("dots",0))
    if dots > 0:
        right = maxf(right,head_x+gap*(1.05+float(dots-1)*.63)+ \
            float(glyphs.bounds["augmentation_dot"][2])*unit*.5)
    var rect := Rect2(left,top,right-left,bottom-top)
    if chord_members.has(id):
        var group: Array = chord_members[id].duplicate()
        group.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < Geometry.diatonic_index(b.get("spelling",{})))
        var centers: Array = []
        for member in group:
            centers.append(Vector2(float(heads.get(str(member.get("id","")),0.0)),_event_y(member,gap)))
        var anchors: Dictionary = _chord_dot_anchors(group,centers,gap)
        var dot: Array = glyphs.bounds["augmentation_dot"]
        for member in group:
            var member_id: String = str(member.get("id",""))
            if anchors.has(member_id):
                var anchor: Vector2 = anchors[member_id]
                var count: int = int(member.get("dots",0))
                rect = rect.merge(Rect2(anchor.x+gap*1.05-float(dot[2])*unit*.5,
                    anchor.y-gap*.24+float(dot[1])*unit,
                    float(dot[2])*unit+float(count-1)*gap*.63,float(dot[3])*unit))
    return _with_single_tuplet_ink(event,rect,gap)


func _with_single_tuplet_ink(event: Dictionary, rect: Rect2, gap: float) -> Rect2:
    var id: String = str(event.get("id",""))
    if not glyphs.tuplet_metadata.has(id):
        return rect
    var info: Dictionary = glyphs.tuplet_metadata[id]
    if info.get("note_ids",[]).size() != 1:
        return rect
    var y: float = _rest_y(event,gap) if str(event.get("kind","")) == "rest" else _event_y(event,gap)
    var unit: float = gap/250.0
    for kind in ["number","bracket"]:
        if info.get(kind) is Dictionary and not info[kind].is_empty():
            var box: Array = info[kind]["bounds"]
            rect = rect.merge(Rect2(float(box[0])*unit,y+float(box[1])*unit,
                float(box[2])*unit,float(box[3])*unit))
    return rect


func _required_ink_density(preferred: float, gap: float = MAX_STAFF_GAP) -> float:
    var heads: Dictionary = _engraved_head_offsets(gap)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        ordered_events,gap,heads,glyphs.bounds)
    var staves: Dictionary = {"right":{},"left":{}}
    var minimum_left := INF
    var maximum_right := -INF
    for event in ordered_events:
        var staff: String = str(event.get("staff","right"))
        var beat: float = float(event.get("beat",0.0))
        var ink: Rect2 = _event_ink_rect(event,gap,heads,accidentals)
        if not staves[staff].has(beat):
            staves[staff][beat] = []
        staves[staff][beat].append({"ink":ink, "event":event})
        minimum_left = minf(minimum_left,ink.position.x)
        maximum_right = maxf(maximum_right,ink.end.x)
    var density: float = preferred
    var witness: Dictionary = {"reason":"configured-density",
        "required_density":preferred,"staff_gap":gap}
    var reach: float = (maximum_right-minimum_left+gap*.2)/preferred
    for staff in staves:
        var onsets: Array = staves[staff].keys()
        onsets.sort()
        for i in range(1,onsets.size()):
            for j in range(i-1,-1,-1):
                var distance: float = float(onsets[i])-float(onsets[j])
                if distance > reach:
                    break
                for previous_item in staves[staff][onsets[j]]:
                    for current_item in staves[staff][onsets[i]]:
                        var previous: Rect2 = previous_item["ink"]
                        var current: Rect2 = current_item["ink"]
                        # Close clocks alone do not imply touching ink:
                        # separate voices/ledger registers may be clear in Y.
                        if current.position.y >= previous.end.y+gap*.1 or \
                                previous.position.y >= current.end.y+gap*.1:
                            continue
                        var necessary: float = (previous.end.x-current.position.x+
                            gap*.2)/distance
                        if necessary > density:
                            density = necessary
                            var prev_event: Dictionary = previous_item["event"]
                            var next_event: Dictionary = current_item["event"]
                            witness = {
                                "reason":"horizontal-ink-clearance",
                                "required_density":necessary,
                                "staff_gap":gap,
                                "previous_id":str(prev_event.get("id","")),
                                "next_id":str(next_event.get("id","")),
                                "previous_kind":str(prev_event.get("kind","")),
                                "next_kind":str(next_event.get("kind","")),
                                "previous_type":str(prev_event.get("note_type","")),
                                "next_type":str(next_event.get("note_type","")),
                                "previous_voice":str(prev_event.get("voice","")),
                                "next_voice":str(next_event.get("voice","")),
                                "previous_pitch":str(prev_event.get("spelling",{})),
                                "next_pitch":str(next_event.get("spelling",{})),
                                "previous_beat":float(onsets[j]),
                                "next_beat":float(onsets[i]),
                                "beat_separation":distance,
                                "previous_rect":[previous.position.x,
                                    previous.position.y,previous.size.x,previous.size.y],
                                "next_rect":[current.position.x,
                                    current.position.y,current.size.x,current.size.y]
                            }
    ink_density_witness = witness
    return density


func _paint_engraved_chord(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {}) -> Array:
    var key: String = _chord_template_key(event)
    if key.is_empty() or not glyphs.has_chord(key):
        return []
    var beamed: bool = beamed_note_ids.has(str(event.get("id","")))
    if beamed and (beam_stem.is_empty() or \
            not glyphs.has_chord_heads(key) or \
            not glyphs.has_chord_stem(key)):
        return []
    var group: Array = chord_members.get(str(event.get("id","")),[])
    var heads: Array = glyphs.chord_heads(key)
    if heads.size() != group.size():
        return []
    x += _voice_column_offset(event,gap,cached_head_offsets)
    var sorted_heads: Array = group.duplicate()
    sorted_heads.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return Geometry.diatonic_index(a.get("spelling",{})) < \
            Geometry.diatonic_index(b.get("spelling",{})))
    var anchor: float = _event_y(event,gap)
    var head_centres: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var offset: Array = heads[i]
        var head_x: float = x+float(offset[0])*gap/250.0
        var head_y: float = anchor+float(offset[1])*gap/250.0
        var staff: String = str(current.get("staff","right"))
        var clef: Dictionary = _clef_for(staff,_measure_for(current))
        var step: int = Geometry.staff_step(
            current.get("spelling",{}),clef)
        head_centres.append(Vector2(head_x,head_y))
        # Ledger rules must be UNDER the authentic filled noteheads.
        _paint_ledger(head_x,head_y,step,_staff_center(staff)+gap*2.0,
            gap,ink)
    if beamed:
        var extrema: Dictionary = _chord_extents(event,gap,cached_head_offsets)
        var stem_up: bool = bool(beam_stem.get("up",true))
        var from_y: float = float(extrema[
            "bottom_y" if stem_up else "top_y"])
        if not glyphs.paint_chord_stem(self,key,x,from_y,
                float(beam_stem["tip_y"]),gap,ink):
            return []
    var painted_ok: bool = (glyphs.paint_chord_heads(
        self,key,x,anchor,gap,ink) if beamed else
        glyphs.paint_chord(self,key,x,anchor,gap,ink))
    if not painted_ok:
        return []
    var dot_anchors: Dictionary = _chord_dot_anchors(sorted_heads,head_centres,gap)
    var painted: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var center: Vector2 = head_centres[i]
        var dot_anchor: Vector2 = dot_anchors.get(str(current.get("id","")),center)
        _paint_rhythm_dots(dot_anchor.x,dot_anchor.y,
            int(current.get("dots",0)),ink,gap)
        _paint_note_accidental(current,center.x,center.y,ink,gap)
        var id: String = str(current.get("id",""))
        _record_notehead(current,center)
        painted.append(id)
    return painted


func _chord_dot_anchors(notes: Array, centers: Array, gap: float) -> Dictionary:
    # Every tone's dots clear the rightmost displaced head. Assign distinct
    # staff spaces from highest to lowest; a line tone can use the space
    # below when its preferred upper space belongs to its adjacent tone.
    var right := -INF
    for center in centers:
        right = maxf(right,center.x)
    var occupied: Dictionary = {}
    var result: Dictionary = {}
    for note in notes:
        if int(note.get("dots",0)) > 0:
            var staff: String = str(note.get("staff","right"))
            var step: int = Geometry.staff_step(note.get("spelling",{}),_clef_for(staff,_measure_for(note)))
            if posmod(step,2) == 1:
                occupied[step] = true
    for i in range(notes.size()-1,-1,-1):
        var note: Dictionary = notes[i]
        if int(note.get("dots",0)) == 0:
            continue
        var staff: String = str(note.get("staff","right"))
        var step: int = Geometry.staff_step(note.get("spelling",{}),_clef_for(staff,_measure_for(note)))
        var target: int = step if posmod(step,2) == 1 else step+1
        if posmod(step,2) == 0:
            if occupied.has(target):
                target = step-1
            while occupied.has(target):
                target -= 2
        occupied[target] = true
        result[str(note.get("id",""))] = Vector2(right,
            Geometry.note_y(target,_staff_center(staff)+gap*2.0,gap)+gap*.24)
    return result


func _paint_note(event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {},
        head_offset: float = 0.0) -> void:
    # Only local glyph separation: the source beat is unchanged.
    x += head_offset
    var staff: String = str(event.get("staff", "right"))
    var measure: Dictionary = _measure_for(event)
    var clef: Dictionary = _clef_for(staff, measure)
    var step: int = Geometry.staff_step(event.get("spelling", {}), clef)
    var bottom: float = _staff_center(staff) + gap*2.0
    var y: float = Geometry.note_y(step, bottom, gap)
    var kind: String = str(event.get("note_type", "quarter"))
    _paint_ledger(x, y, step, bottom, gap, ink)
    # Simple notes are complete Verovio-engraved sprites: no Godot stem,
    # flag or notehead assembly. Composite chords and beam groups have
    # variable geometry and are handled separately below.
    var isolated: bool = not bool(event.get("chord", false)) and \
        beam_stem.is_empty() and \
        chord_members.get(str(event.get("id", "")), [event]).size() == 1
    if isolated:
        var normal_up: bool = bool(_chord_extents(event,gap)["up"])
        if not glyphs.paint_note(self, kind, normal_up, x, y, gap, ink):
            # Atlas validation happens on load; missing artwork must never
            # silently revert to imitated musical ink.
            push_warning("Missing authentic Verovio note template: " + kind)
            return
        _paint_rhythm_dots(x,y,int(event.get("dots",0)),ink,gap)
        _paint_note_accidental(event,x,y,ink,gap)
        _record_notehead(event,Vector2(x,y))
        return
    var solid: bool = kind not in ["half","whole"]
    glyphs.paint(self, "head_black" if solid else (
        "head_whole" if kind == "whole" else "head_half"),
        x, y, gap, ink, true)
    # Beamed single-note attacks use an actual Verovio stem alpha mask;
    # the separate source beam determines its endpoint and stem direction.
    if not beam_stem.is_empty() and not bool(event.get("chord",false)):
        glyphs.paint_note_stem(self,kind,bool(beam_stem["up"]),
            x,y,float(beam_stem["tip_y"]),gap,ink)
    _paint_rhythm_dots(x,y,int(event.get("dots",0)),ink,gap)
    _paint_note_accidental(event,x,y,ink,gap)
    _record_notehead(event,Vector2(x,y))

func _beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary = {}) -> Dictionary:
    # Beam position is derived from the real notehead Y coordinates.
    # All horizontal positions still come from the one musical-time axis.
    var stems: Dictionary = {}
    var drawn_groups: Array = []
    frame_visible_beam_groups = 0
    for group in beam_groups:
        if group.size() < 2:
            continue
        if not _practice_span_visible(group[0],group[-1]):
            continue
        var first_x: float = timeline.screen_x(
            float(group[0].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        var last_x: float = timeline.screen_x(
            float(group[-1].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        if last_x < -60.0 or first_x > size.x + 60.0:
            continue
        frame_visible_beam_groups += 1
        var up: bool = bool(beam_stem_up_by_note[str(group[0].get("id",""))])
        var group_ids := PackedStringArray()
        for event in group:
            group_ids.append(str(event.get("id","")))
        var source_key: String = "|".join(group_ids)
        var members: Array = []
        var source_stems: Array = []
        var source_heads: Array = glyphs.beam_metadata[source_key]["head_offsets"]
        var head_box: Array = glyphs.bounds["head_black"]
        var origin_to_center: float = float(head_box[0])+float(head_box[2])*.5
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var x: float = timeline.screen_x(float(event.get("beat", 0.0)),
                clock, playhead_x, play_from_beat)
            var chord: Dictionary = _chord_extents(event,gap,head_offsets)
            var stem_box: Array = _source_stem_bounds(event,up)
            var attachment: float = float(stem_box[0])+float(stem_box[2])*.5
            var stem_x: float = x+_voice_column_offset(event,gap,head_offsets)+attachment*gap/250.0
            # The beam PNG uses source font origins, while stem masks use
            # centred heads. Map each measured stem centre in BOTH spaces;
            # mapping head centres stretches the first beam cap away from
            # its stem when the source spacing differs from the beat grid.
            source_stems.append(float(source_heads[index])+origin_to_center+attachment)
            members.append({
                "id":str(event.get("id", "")), "x":stem_x,
                "head_x":x+float(head_offsets.get(str(event.get("id","")),0.0)),
                "head_y":float(chord["bottom_y"] if up else chord["top_y"]),
                "top_y":float(chord["top_y"]),
                "bottom_y":float(chord["bottom_y"]),
                "note_type":str(event.get("note_type", "eighth"))
            })
        # The source image supplies the entire beam contour and each
        # measured stem tip. The compositor never estimates a slope.
        var art_key: String = source_key
        var art_tips: Array = glyphs.beam_tips(art_key)
        if art_tips.size() != members.size():
            continue
        for index in range(members.size()):
            var member: Dictionary = members[index]
            var tip: float = float(member["head_y"])+ \
                float(art_tips[index])*gap/250.0
            member["tip_y"] = tip
            members[index] = member
            stems[str(member["id"])] = {"up":up, "tip_y":tip,
                "x":float(member["x"])}
        drawn_groups.append({"members":members,
            "staff":str(group[0].get("staff", "right")),
            "hand":_performing_hand(group[0]),
            "up":up, "art_key":art_key,
            "source_stem_offsets":source_stems,
            # Beam bounds are exported relative to the first source ID,
            # which may be an inner/higher chord tone. Stem tip offsets
            # deliberately use the outer tone and have a different origin.
            "anchor_y":_event_y(group[0],gap)})
    return {"stems":stems, "groups":drawn_groups}


func _paint_beams(data: Dictionary, gap: float) -> void:
    # There is no primitive-polygon fallback: load_score() already checked
    # that each expected multi-note group has genuine Verovio beam ink.
    for group in data.get("groups",[]):
        var members: Array = group.get("members",[])
        if members.size() < 2:
            continue
        var first: Dictionary = members[0]
        var last: Dictionary = members[-1]
        if float(last["head_x"]) < -40.0 or \
                float(first["head_x"]) > size.x+40.0:
            continue
        var anchors: Array = []
        for member in members:
            anchors.append(float(member["x"]))
        glyphs.paint_beam(self,str(group["art_key"]),anchors,
            float(group["anchor_y"]),gap,
            _event_ink(group),group["source_stem_offsets"])


# Only the original Verovio-rendered tie contours are permitted.
# The source noteheads determine the start, end and staff-space vertical
# position. Godot never produces its own bow paths or tapered polygons.
func _tie_placement(first: Dictionary, last: Dictionary,
        x0: float, x1: float, gap: float) -> Dictionary:
    var left: float = x0+float(cached_head_offsets.get(
        str(first.get("id","")),0.0))
    var right: float = x1+float(cached_head_offsets.get(
        str(last.get("id","")),0.0))
    if right-left <= gap*1.2:
        return {}
    return {"x0":left, "x1":right, "y":_event_y(first,gap),
        "down":_tie_bow_down(first,last,gap)}


func _tie_bow_down(first: Dictionary, last: Dictionary, gap: float) -> bool:
    for i in range(2):
        var event: Dictionary = first if i == 0 else last
        for attributes in event.get("tied_marks",[]):
            var kind := ""
            var placement := ""
            for attribute in attributes:
                if attribute.size() == 2:
                    if str(attribute[0]) == "type":
                        kind = str(attribute[1])
                    elif str(attribute[0]) == "placement":
                        placement = str(attribute[1])
            if kind == ("start" if i == 0 else "stop") and \
                    placement in ["above","below"]:
                return placement == "below"
    var leader: Dictionary = first
    if bool(first.get("chord",false)):
        # Locate only simultaneous events, including a child's real leader.
        # Do not scan the full performance's chord dictionary per frame.
        var beat: float = float(first.get("beat",0.0))
        var begin := 0
        var end := ordered_events.size()
        while begin < end:
            var middle: int = (begin+end) >> 1
            if float(ordered_events[middle].get("beat",0.0)) < beat-.000001:
                begin = middle+1
            else:
                end = middle
        for index in range(begin,ordered_events.size()):
            var candidate: Dictionary = ordered_events[index]
            if float(candidate.get("beat",0.0)) > beat+.000001:
                break
            if not bool(candidate.get("chord",false)) and \
                    str(candidate.get("kind","")) == "note" and \
                    candidate.get("staff") == first.get("staff") and \
                    candidate.get("voice") == first.get("voice") and \
                    candidate.get("measure") == first.get("measure"):
                leader = candidate
                break
    var extents: Dictionary = _chord_extents(leader,gap)
    var y: float = _event_y(first,gap)
    var middle_y: float = (float(extents["top_y"])+float(extents["bottom_y"]))* .5
    # Original chord ties face away from the chord interior, independently
    # of the shared stem. The middle note of an odd chord keeps its stem rule.
    if absf(y-middle_y) > .001:
        return y > middle_y
    return bool(beam_stem_up_by_note.get(str(first.get("id","")),extents["up"]))


func _paint_ties(playhead_x: float, clock: float, gap: float) -> void:
    for pair in tie_pairs:
        var previous: Dictionary = pair["first"]
        var event: Dictionary = pair["last"]
        if not _practice_span_visible(previous,event):
            continue
        var x0: float = timeline.screen_x(float(previous.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(event.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        if x1 < -20.0 or x0 > size.x+20.0:
            continue
        var place: Dictionary = _tie_placement(previous,event,x0,x1,gap)
        if not place.is_empty():
            _paint_tie_contour(previous,event,place,gap)


func _paint_tie_contour(first: Dictionary, last: Dictionary,
        place: Dictionary, gap: float) -> void:
    var direction: String = "up" if bool(place["down"]) else "down"
    var texture: Texture2D = glyphs.tie_textures.get(direction)
    if texture == null:
        return
    var data: Dictionary = glyphs.tie_metadata[direction]
    var box: Array = data["bounds"]
    var source_head: Array = glyphs.bounds["head_half"]
    var source_center: float = float(source_head[0])+float(source_head[2])*.5
    var widths: Array[float] = []
    for event in [first,last]:
        var kind: String = str(event.get("note_type","quarter"))
        var name: String = "head_"+(kind if kind in ["whole","half"] else "black")
        widths.append(float(glyphs.bounds[name][2]))
    var unit: float = gap/250.0
    # The original template was engraved between HALF-note font origins;
    # native musical X is the centre of each actual head. Keep Verovio's
    # head-edge clearances in staff units, including a wider whole head.
    # Stretch the contour itself, never the empty endpoint margins.
    var left_inset: float = (float(box[0])-source_center+
        (widths[0]-float(source_head[2]))*.5)*unit
    var right_inset: float = (float(box[0])+float(box[2])-
        float(data["span"])-source_center-
        (widths[1]-float(source_head[2]))*.5)*unit
    var span: float = float(place["x1"])-float(place["x0"])
    if span-(left_inset-right_inset) < float(box[3])*unit:
        # Do not compress the ink to less than its original bow height:
        # that collapses a curve into a vertical mark. Map the original
        # contour affinely between head centres in this tight interval.
        # Any overlap remains visible to the independent pixel audit.
        var compression: float = span/(float(data["span"])*unit)
        left_inset *= compression
        right_inset *= compression
    var left: float = float(place["x0"])+left_inset
    var right: float = float(place["x1"])+right_inset
    if right <= left:
        return
    draw_texture_rect(texture,Rect2(left,
        float(place["y"])+float(box[1])*unit,
        right-left,float(box[3])*unit),false,
        _event_ink(last))


# Binary-search into pre-sorted MusicXML events. Work is proportional
# to what the pianist can actually see, not to the whole imported MIDI.
func _paint_slurs(playhead_x: float,clock: float,gap: float) -> void:
    for pair in slur_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        if not _practice_span_visible(first,last):
            continue
        var x0: float = timeline.screen_x(float(first.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(float(last.get("beat",0.0)),
            clock,playhead_x,play_from_beat)
        if x0 > size.x+50.0 or x1 < -50.0:
            continue
        x0 += float(cached_head_offsets.get(str(first.get("id","")),0.0))
        x1 += float(cached_head_offsets.get(str(last.get("id","")),0.0))
        if x1 <= x0:
            continue
        glyphs.paint_slur(self,str(pair["key"]),x0,_event_y(first,gap),
            x1,_event_y(last,gap),gap,
            _event_ink(first))


func _paint_expressions(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # The notation model is the *only* source. These marks never alter the
    # clock, create MIDI attacks, or participate in lesson mastery.
    var pedal_starts: Dictionary = {}
    for mark in source_expressions:
        var at: float = float(mark.get("beat", -1.0))
        if not _practice_event_visible(mark):
            continue
        var hand: String = _display_staff(mark)
        var ink: Color = _event_ink(mark)
        var kind: String = str(mark.get("kind", ""))
        var value: String = str(mark.get("value", ""))
        var x: float = timeline.screen_x(at, clock, playhead_x, play_from_beat)
        if kind == "pedal":
            var y: float = _staff_center(hand) + gap*3.55
            if value == "start":
                pedal_starts[hand] = mark
            elif value == "stop" and pedal_starts.has(hand):
                var start_mark: Dictionary = pedal_starts[hand]
                var begin: float = float(start_mark.get("beat", 0.0))
                if _practice_span_visible(start_mark,mark) and bool(start_mark.get("line", false)) and begin < at and \
                        at >= left-.5 and begin <= right+.5:
                    var start_x: float = timeline.screen_x(
                        begin, clock, playhead_x, play_from_beat)
                    var x0: float = maxf(-gap, start_x+gap*.65)
                    var x1: float = minf(size.x+gap, x-gap*.3)
                    if x1 > x0:
                        draw_line(Vector2(x0,y), Vector2(x1,y), ink, 1.3,true)
                        draw_line(Vector2(x1,y), Vector2(x1,y-gap*.55),ink,1.3,true)
                pedal_starts.erase(hand)
            if at >= left-.5 and at <= right+.5 and bool(mark.get("sign", true)):
                glyphs.paint(self, "pedal_start" if value == "start" else "pedal_stop",
                    x,y,gap*.9,ink,true)
            continue
        if at < left-.5 or at > right+.5:
            continue
        if kind == "dynamic":
            glyphs.paint(self, "dynamic_"+value, x,
                _staff_center(hand)+gap*3.0, gap*.9, ink, true)
        elif kind == "articulation":
            var note_id: String = str(mark.get("note_id", ""))
            if not pass_noteheads.has(note_id) or not expression_note_index.has(note_id):
                continue
            var source_event: Dictionary = expression_note_index[note_id]
            var center: float = _staff_center(hand)
            var head: Vector2 = pass_noteheads[note_id]
            var clef: Dictionary = _clef_for(hand, _measure_for(source_event))
            var step: int = Geometry.staff_step(source_event.get("spelling", {}),clef)
            var below: bool = step < 4
            var y: float = maxf(head.y+gap*1.05,center+gap*2.9) if below \
                else minf(head.y-gap*1.05,center-gap*2.9)
            glyphs.paint(self, "artic_"+value+("_below" if below else "_above"),
                head.x,y,gap*.9,ink,true)


func _paint_hairpins(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # Wedge lines are structural ink, like pedal lines and volta brackets.
    # Original endpoints stay on the score's fixed beat timeline, and a
    # clipped screen viewport displays the exact same interpolated slope.
    var pending: Dictionary = {}
    for mark in source_expressions:
        if str(mark.get("kind", "")) != "hairpin":
            continue
        var hand: String = _display_staff(mark)
        var key: String = hand+"|"+str(mark.get("number", "1"))
        var kind: String = str(mark.get("value", ""))
        if kind in ["crescendo", "diminuendo"]:
            pending[key] = mark
            continue
        if kind != "stop" or not pending.has(key):
            continue
        var start: Dictionary = pending[key]
        pending.erase(key)
        if not _practice_span_visible(start,mark):
            continue
        var begin: float = float(start.get("beat", 0.0))
        var end: float = float(mark.get("beat", 0.0))
        if end <= begin or begin > right+.5 or end < left-.5:
            continue
        var first_x: float = timeline.screen_x(
            begin, clock, playhead_x, play_from_beat)+gap*.48
        var last_x: float = timeline.screen_x(
            end, clock, playhead_x, play_from_beat)-gap*.25
        if last_x <= first_x:
            continue
        var x0: float = maxf(-gap, first_x)
        var x1: float = minf(size.x+gap, last_x)
        if x1 <= x0:
            continue
        var open_start: float = gap*.06 if str(start.get("value")) == "crescendo" else gap*.47
        var open_end: float = gap*.47 if str(start.get("value")) == "crescendo" else gap*.06
        var t0: float = clampf((x0-first_x)/(last_x-first_x), 0.0, 1.0)
        var t1: float = clampf((x1-first_x)/(last_x-first_x), 0.0, 1.0)
        var half0: float = lerpf(open_start,open_end,t0)*.5
        var half1: float = lerpf(open_start,open_end,t1)*.5
        var y: float = _staff_center(hand)+gap*3.55
        var ink: Color = _event_ink(start)
        draw_line(Vector2(x0,y-half0),Vector2(x1,y-half1),ink,1.3,true)
        draw_line(Vector2(x0,y+half0),Vector2(x1,y+half1),ink,1.3,true)


func _paint_volta_endings(left: float, right: float, clock: float,
        playhead_x: float, gap: float) -> void:
    # Volta brackets are structural rule lines with an engraved text label;
    # neither the repeat marks nor the transport clock causes an auto-repeat.
    var pending: Dictionary = {}
    var ends: Array = []
    for measure in timeline.measures:
        for location in ["left", "right"]:
            var mark: Variant = measure.get(location+"_barline")
            if not mark is Dictionary:
                continue
            var ending: Variant = mark.get("ending")
            if not ending is Dictionary:
                continue
            var number: String = str(ending.get("number", ""))
            var kind: String = str(ending.get("type", ""))
            var beat: float = float(measure.get(
                "start_beat" if location == "left" else "end_beat", 0.0))
            if kind == "start":
                pending[number] = beat
            elif kind in ["stop", "discontinue"] and pending.has(number):
                ends.append({"start": float(pending[number]), "end": beat,
                    "number": number, "closed": kind == "stop"})
                pending.erase(number)
    # A source excerpt may end inside an open volta. Never silently lose it.
    for number in pending:
        ends.append({"start": float(pending[number]),
            "end": timeline.duration_beats, "number": str(number), "closed": false})
    var y: float = _staff_center("right")-gap*5.05
    for ending in ends:
        var first: float = float(ending["start"])
        var last: float = float(ending["end"])
        if first > right+.5 or last < left-.5 or last <= first:
            continue
        var replaced := false
        if score_loop_enabled:
            var interval := {"start_beat":paint_pass_start+first,"end_beat":paint_pass_start+last}
            for preparation in preparation_history.values():
                if _practice_intervals_overlap(interval,preparation["measure"]):
                    replaced = true
                    break
        if replaced:
            continue
        var x0: float = timeline.screen_x(first,clock,playhead_x,play_from_beat)
        var x1: float = timeline.screen_x(last,clock,playhead_x,play_from_beat)
        var start_x: float = maxf(-gap,x0)
        var end_x: float = minf(size.x+gap,x1)
        if end_x <= start_x:
            continue
        draw_line(Vector2(start_x,y),Vector2(end_x,y),NOTE_INK,1.3,true)
        if x0 >= -gap and x0 <= size.x+gap:
            draw_line(Vector2(x0,y),Vector2(x0,y+gap*.85),NOTE_INK,1.3,true)
            draw_string(ThemeDB.fallback_font,Vector2(x0+gap*.35,y-gap*.3),
                str(ending["number"])+"." if not str(ending["number"]).ends_with(".")
                else str(ending["number"]),
                HORIZONTAL_ALIGNMENT_LEFT,-1,roundi(gap*.92),NOTE_INK)
        if bool(ending["closed"]) and x1 >= -gap and x1 <= size.x+gap:
            draw_line(Vector2(x1,y),Vector2(x1,y+gap*.85),NOTE_INK,1.3,true)


func _paint_grace_notes(gap: float) -> void:
    # Every grace mark is attached to a *visible* graded notehead. Its
    # authentic complete Verovio note template is merely reduced in size;
    # it has no playback clock event, scored attack or independent X motion.
    for grace in attached_grace_notes:
        var target: String = str(grace.get("before_note_id", ""))
        if not pass_noteheads.has(target):
            continue
        var hand: String = _display_staff(grace)
        var spelling: Dictionary = grace.get("spelling", {})
        var clef: Dictionary = _clef_for(hand, _measure_for(grace))
        var step: int = Geometry.staff_step(spelling, clef)
        var y: float = Geometry.note_y(step, _staff_center(hand)+gap*2.0,gap)
        var head: Vector2 = pass_noteheads[target]
        var kind: String = str(grace.get("note_type", "eighth"))
        glyphs.paint_note(self, kind, step < 4,
            head.x-gap*1.4, y, gap*.66, _event_ink(grace))


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
    return results


func _record_notehead(event: Dictionary, point: Vector2) -> void:
    var id: String = str(event["id"])
    pass_noteheads[id] = point
    drawn_note_instances.append({"event_id":id,"source_id":event.get("source_id"),
        "pass_index":paint_pass_index,"instance_id":"%d:%s" % [paint_pass_index,id],"position":point})
    if not drawn_noteheads.has(id) or absf(point.x-size.x*PLAYHEAD_FRACTION)<absf(drawn_noteheads[id].x-size.x*PLAYHEAD_FRACTION):
        drawn_noteheads[id] = point


func _practice_event_visible(event: Dictionary) -> bool:
    if not score_loop_enabled:
        return true
    var at: float = paint_pass_start+float(event.get("beat",event.get("start_beat",0.0)))
    for preparation in preparation_history.values():
        var silence: Dictionary = preparation["measure"]
        if at>=float(silence["start_beat"])-.00001 and at<float(silence["end_beat"])-.00001:
            return false
    return true


func _practice_span_visible(first: Dictionary, last: Dictionary) -> bool:
    if not score_loop_enabled:
        return true
    for preparation in preparation_history.values():
        var silence: Dictionary = preparation["measure"]
        if paint_pass_start+float(last["beat"])>=float(silence["start_beat"])-.00001 and \
                paint_pass_start+float(first["beat"])<float(silence["end_beat"])-.00001:
            return false
    return true


func _practice_intervals_overlap(first: Dictionary, second: Dictionary) -> bool:
    return float(first["start_beat"])<float(second["end_beat"])-.00001 and \
        float(second["start_beat"])<float(first["end_beat"])-.00001


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
    _paint_barline({"x":x,"style":mark.get("style","regular"),"repeat":mark.get("repeat",""),
        "segments":[{"top":_staff_center("right")-gap*2.0,"bottom":_staff_center("left")+gap*2.0}]},gap)


func _paint_preparation_measure(measure: Dictionary, previous: Dictionary,
        gap: float, playhead_x: float, opening: bool = false) -> void:
    var first: float = float(measure["start_beat"])
    var last: float = float(measure["end_beat"])
    var x0: float = playhead_x+(first-visual_scroll_beat)*timeline.pixels_per_beat
    var x1: float = playhead_x+(last-visual_scroll_beat)*timeline.pixels_per_beat
    if x1<-gap*16.0 or x0>size.x+gap*16.0:
        return
    _paint_context(measure,previous,x0,gap,opening)
    # The clock anchors attacks, not the edges of their glyphs. Reuse the
    # native terminal/incoming clearances so a barline cannot cut through
    # the next notehead. Center the rest between the actual engraved rules.
    var left_rule: float = x0-gap*.45
    var right_rule: float = x1-gap*1.35
    _practice_barline(left_rule,measure.get("left_barline",{}),gap)
    _practice_barline(right_rule,measure.get("right_barline",{}),gap)
    for event in measure["events"]:
        # Semantic full-measure silence uses the authentic hanging rest,
        # irrespective of its meter-dependent duration. It is not a note.
        var staff: String = str(event["staff"])
        _paint_rest((left_rule+right_rule)*.5,_staff_center(staff)+Geometry.rest_staff_offset("whole")*gap,
            "whole",0,_ink(staff),gap)


# Paint at most the source passages intersecting the viewport. There are
# no cloned notes or IDs in the semantic model, MIDI evaluator or glyph atlas.
# Offsetting the camera instead of the music preserves exact source timing,
# beam/tie geometry and existing per-viewport binary search.
func _context_meter_x(measure: Dictionary, x: float, gap: float,
        opening: bool, right_limit: float = INF) -> float:
    var center: float = x-gap*1.6-(76.0*gap/17.0 if opening else 0.0)
    if not is_finite(right_limit):
        return center
    var half_width := 0.0
    for value in measure.get("meter",[4,4]):
        var text: String = str(int(value))
        var widest := 0.0
        for digit in text:
            widest = maxf(widest,float(glyphs.bounds["time_"+digit][2])*gap/500.0)
        half_width = maxf(half_width,float(text.length()-1)*gap*1.10*.5+widest)
    return minf(center,right_limit-half_width-3.0)


func _paint_context(measure: Dictionary, previous_measure: Dictionary, x: float,
        gap: float, opening: bool, meter_right_limit: float = INF) -> bool:
    var header_scale: float = gap/17.0
    var header_shift: float = 76.0*header_scale if opening else 0.0
    var crowded_meter: bool = _meter_is_crowded(measure,previous_measure,gap)
    for staff in ["right","left"]:
        var center: float = _staff_center(staff)
        var clef: Dictionary = _clef_for(staff,measure)
        var signatures: Dictionary = measure.get("keys",{})
        var signature: int = int(signatures.get(staff,0))
        var previous_keys: Dictionary = previous_measure.get("keys",{})
        var key_changed: bool = signature != int(previous_keys.get(staff,999))
        var change_marks: Array = []
        if key_changed:
            # Cancelling an old signature requires visible naturals,
            # even when the new signature is C major (zero accidentals).
            var previous_fifths: int = int(previous_keys.get(staff,0))
            var cancelled: Array = ([] if opening else
                Geometry.key_cancellation_steps(clef,previous_fifths,signature))
            var incoming: Array = Geometry.signature_steps(clef,signature)
            for step in cancelled:
                change_marks.append({"step":step,"accidental":"natural"})
            for step in incoming:
                change_marks.append({"step":step,"accidental":
                    "sharp" if signature > 0 else "flat"})
        if opening or _clef_for(staff,previous_measure) != clef:
            # Cancellation naturals occupy the same signature block as the
            # incoming accidentals. Reserve the complete block before placing
            # a clef, including when the destination signature is empty.
            var key_columns: int = maxi(absi(signature),change_marks.size())
            _paint_clef(x-(86.0+float(key_columns)*14.0)*header_scale-header_shift,
                center,clef,gap,_ink(staff))
        if key_changed:
            for i in range(change_marks.size()):
                var mark: Dictionary = change_marks[i]
                var glyph_x: float = x-(39.0+float(change_marks.size()-i)*14.0)*header_scale-header_shift
                var glyph_y: float = Geometry.note_y(int(mark["step"]),
                    center+2.0*gap,gap)
                _paint_accidental(glyph_x,glyph_y,
                    str(mark["accidental"]),_ink(staff),gap)
        if (opening or previous_measure.get("meter",[]) !=
                measure.get("meter",[])) and not crowded_meter:
            var meter: Array = measure.get("meter",[4,4])
            if meter.size() >= 2:
                var meter_x: float = _context_meter_x(measure,x,gap,opening,meter_right_limit)
                _paint_meter_number(int(meter[0]), meter_x,
                    center-gap*.95, _ink(staff), gap)
                _paint_meter_number(int(meter[1]), meter_x,
                    center+gap*.8, _ink(staff), gap)
    if crowded_meter:
        _paint_meter_above_staff(measure,x,gap)
    return crowded_meter


func _paint_source_pass(camera_clock: float, playhead_x: float, gap: float,
        pass_index: int = 0, pass_start: float = 0.0) -> void:
    paint_pass_index = pass_index
    paint_pass_start = pass_start
    pass_noteheads.clear()
    current_preparation = preparation_history.get(pass_start,{}) if score_loop_enabled else {}
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
            for stroke in _barline_strokes(str(mark.get("style","regular")),gap):
                meter_right_limit = minf(meter_right_limit,x-gap*1.35+float(stroke["offset"])-float(stroke["width"])*.5)
            if str(mark.get("repeat","")) in ["backward","both"] and is_finite(meter_right_limit):
                meter_right_limit = minf(meter_right_limit,x-gap*(1.35+.92)-float(glyphs.bounds["repeat_dot"][2])*gap/500.0)
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
                visible_symbols += members.size()
                continue
            _paint_note(event,x,gap,ink,
                beam_stems.get(str(event.get("id", "")), {}),
                float(head_offsets.get(str(event.get("id", "")), 0.0)))
        else:
            _paint_rest(x,_rest_y(event,gap),
                str(event.get("note_type","quarter")),
                int(event.get("dots",0)),ink,gap)
        visible_symbols += 1
    _paint_beams(beam_data, gap)
    _paint_ties(playhead_x,camera_clock,gap)
    _paint_slurs(playhead_x,camera_clock,gap)
    _paint_tuplet_brackets(camera_clock,playhead_x,gap)
    _paint_expressions(left,right,camera_clock,playhead_x,gap)
    _paint_hairpins(left,right,camera_clock,playhead_x,gap)
    _paint_grace_notes(gap)
    fingering_pass_clocks.append({"clock":camera_clock,"pass_index":pass_index,"pass_start":pass_start})

func _draw() -> void:
    drawn_noteheads.clear()
    drawn_note_instances.clear()
    pass_noteheads.clear()
    visible_symbols = 0
    drawn_fingerings.clear()
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
