extends RefCounted
## Pure native notation cut planner: authored source glyph envelopes,
## connected tie/slur/beam units, barline headers and retractable safe seams.
## No renderer state, playback clock or admission transaction is mutated.
const ContextPainter := preload("res://notation/native/context_painter.gd")
const ScoreStreamWindowCuts := preload("res://score_stream_window_cuts.gd")

static func ink_safe_boundaries(layout, timeline, gap: float) -> Array[Vector2]:
    # Pixel-accurate authored note/rest envelopes and exact source-connected
    # Verovio groups. None depends on Play/Pause/Retry or world position.
    var intervals: Array[Vector2] = []
    var density: float = maxf(1.0,timeline.pixels_per_beat)
    var pad: float = 1.5/density
    for event in layout.ordered_events:
        var kind: String = str(event.get("kind",""))
        if kind not in ["note","rest"]:
            continue
        var envelope: Rect2 = layout.event_ink_rect(
            event,gap,layout.cached_head_offsets,
            layout.cached_accidental_offsets)
        var beat: float = float(event.get("beat",0.0))
        if envelope.size.x > 0.0:
            intervals.append(Vector2(
                beat+envelope.position.x/density-pad,
                beat+envelope.end.x/density+pad))
    for group in layout.beam_groups:
        if group.size() >= 2:
            _add_interval(intervals,float(group[0]["beat"]),
                float(group[-1]["beat"]),pad)
    for group in layout.notation_tuplets:
        var events: Array = group.get("events",[])
        if events.size() >= 2:
            _add_interval(intervals,float(events[0]["beat"]),
                float(events[-1]["beat"]),pad)
    for pairs in [layout.tie_pairs,layout.slur_pairs]:
        for pair in pairs:
            _add_interval(intervals,
                float(pair["first"]["beat"]),float(pair["last"]["beat"]),pad)
    for hairpin in layout.prepared_hairpins:
        _add_interval(intervals,float(hairpin["begin"]),
            float(hairpin["end"]),pad)
    for volta in layout.prepared_voltas:
        _add_interval(intervals,float(volta["start"]),
            float(volta["end"]),pad)
    # A genuine expression can have a single graphic larger than one note
    # (e.g. rehearsal marks or multi-word tempo text); keep its authored
    # source context together when an otherwise movable seam crosses it.
    for expression in layout.source_expressions:
        var at: float = float(expression.get("beat",0.0))
        _add_interval(intervals,at,at,maxf(pad,gap*2.5/density))
    # A measure's clef/key/meter is engraved BEFORE its nominal barline
    # in source X. Two measure clips with a seam exactly at that barline
    # would silently sever its header. The same applies to the regular
    # barline stroke itself. Preserve connected context as indivisible ink.
    var previous: Dictionary = {}
    for i in range(timeline.measures.size()):
        var measure: Dictionary = timeline.measures[i]
        var at: float = float(measure.get("start_beat",0.0))
        if i == 0:
            previous = measure
            continue
        # Every regular barline has finite thickness around its beat;
        # move the retractable seam a few pixels left of the stroke.
        _add_interval(intervals,at,at,maxf(pad,2.0/density))
        var context_changed: bool = (
            measure.get("meter",[]) != previous.get("meter",[]) or
            measure.get("keys",{}) != previous.get("keys",{}))
        var key_columns := 0
        for staff in layout.visible_staves():
            if layout.clef_for(staff,measure) != \
                    layout.clef_for(staff,previous):
                context_changed = true
            var new_key: int = int(measure.get("keys",{}).get(staff,0))
            var old_key: int = int(previous.get("keys",{}).get(staff,0))
            if new_key != old_key:
                # The original cancellation naturals occupy additional
                # columns BEFORE the incoming signature.
                key_columns = maxi(key_columns,
                    absi(new_key)+absi(old_key))
            else:
                key_columns = maxi(key_columns,absi(new_key))
        if context_changed:
            var header_left_px: float = ContextPainter.clef_lead_pixels(
                key_columns,gap)+gap*2.5
            # A context change belongs semantically to its NEW measure.
            # If its leftward header is too wide to move the clip seam
            # before all that ink, do not move the seam slightly RIGHT and
            # keep the entire new header attached to the old measure.
            # Reserve beyond the allowable right-shift solely to force an
            # indivisible two-measure visual group in that case.
            intervals.append(Vector2(
                at-header_left_px/density-pad,
                at+ScoreStreamWindowCuts.MAX_SHIFT_BEATS+pad))
        previous = measure
    return intervals


static func _add_interval(intervals: Array[Vector2],first: float,
        last: float,margin: float) -> void:
    if is_finite(first) and is_finite(last) and last >= first:
        intervals.append(Vector2(first-margin,last+margin))

static func source_windows(timeline, opening: float, intervals: Array[Vector2]) -> Array[Vector2]:
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
    # Shift retractable seams into genuine source-ink whitespace. If a
    # slur/tie/beam spans a measure boundary, merge that visual unit rather
    # than let Pause remove half of a source glyph. World-note deadlines and
    # authored measure positions do not change.
    return ScoreStreamWindowCuts.safe_windows(
        opening,timeline.duration_beats,timeline.measures,
        intervals)
