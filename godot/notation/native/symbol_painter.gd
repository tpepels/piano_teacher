extends RefCounted
## Explicit-canvas native ink; source geometry stays in ScoreLayout.
## Paint APIs prepend (canvas, frame) to the original view method arguments.
const Geometry := preload("res://notation/native/geometry.gd")
const Design := preload("res://practice_theme.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")
const NOTE_INK := Design.SCORE_INK
const DIM_INK := Design.STAFF_MUTED

var score_layout
var connector_geometry

func _init(layout, connectors) -> void:
    score_layout = layout
    connector_geometry = connectors


func paint_ledger(canvas, frame: RenderPass, x: float, y: float, step: int,
        bottom: float, gap: float, ink: Color) -> void:
    # At this staff score_layout.size a fixed ±14 px rule almost disappears under
    # real Verovio notehead ink. Let each ledger line extend clearly.
    var half_width: float = maxf(18.0,gap*.95)
    var weight: float = maxf(1.6,gap*.075)
    if step < 0:
        var line_step: int = -2
        while line_step >= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            canvas.draw_line(Vector2(x-half_width,line_y),
                Vector2(x+half_width,line_y), Color(ink,.94), weight,true)
            line_step -= 2
    elif step > 8:
        var line_step: int = 10
        while line_step <= step:
            var line_y: float = Geometry.note_y(line_step, bottom, gap)
            canvas.draw_line(Vector2(x-half_width,line_y),
                Vector2(x+half_width,line_y), Color(ink,.94), weight,true)
            line_step += 2


func paint_accidental(canvas, frame: RenderPass, x: float, y: float,
        value: String, ink: Color, gap: float,
        head_offset: float = INF) -> void:
    var name: String = str(Geometry.ACCIDENTAL_GLYPHS.get(value, ""))
    if not name.is_empty():
        var offset: float = head_offset if is_finite(head_offset) else -gap*1.15
        score_layout.glyphs.paint(canvas, name, x+offset, y, gap, ink, true)


func paint_note_accidental(canvas, frame: RenderPass, event: Dictionary, x: float, y: float,
        ink: Color, gap: float) -> void:
    var accidental: String = str(event.get("accidental",""))
    if not accidental.is_empty() and accidental != "null":
        paint_accidental(canvas,frame,x,y,accidental,ink,gap,
            float(score_layout.cached_accidental_offsets.get(str(event.get("id","")),-gap*1.15)))


func paint_rhythm_dots(canvas, frame: RenderPass, x: float, y: float, dots: int,
        ink: Color, gap: float) -> void:
    for index in range(dots):
        score_layout.glyphs.paint(canvas, "augmentation_dot",
            x+gap*1.05+float(index)*gap*.63, y-gap*.24,
            gap, ink, true)


func paint_tuplet_brackets(canvas, frame: RenderPass, clock: float, playhead_x: float,
        gap: float) -> void:
    # Authentic separated Verovio number/bracket masks only. Every group
    # was validated on lesson load; no Godot-drawn ratio, digit or hook.
    for group in score_layout.notation_tuplets:
        if tuplet_hidden(group):
            continue
        var events: Array = group.get("events",[])
        if events.is_empty():
            continue
        var ids := PackedStringArray()
        for event in events:
            ids.append(str(event.get("id","")))
        var first: Dictionary = events[0]
        var last: Dictionary = events[-1]
        if not frame.span_visible(first,last):
            continue
        var x0: float = score_layout.timeline.screen_x(
            float(first.get("beat",0.0)),clock,playhead_x,frame.play_from_beat)
        var x1: float = score_layout.timeline.screen_x(
            float(last.get("beat",0.0)),clock,playhead_x,frame.play_from_beat)
        if str(first.get("kind","")) == "note":
            x0 += score_layout.voice_column_offset(first,gap,score_layout.cached_head_offsets)
        if str(last.get("kind","")) == "note":
            x1 += score_layout.voice_column_offset(last,gap,score_layout.cached_head_offsets)
        if x1 < -50.0 or x0 > score_layout.size.x+50.0:
            continue
        score_layout.glyphs.paint_tuplet(canvas,"|".join(ids),x0,x1,
            score_layout.rest_y(first,gap) if str(first.get("kind","")) == "rest" else score_layout.event_y(first,gap),gap,
            frame.event_ink(score_layout,first))


func paint_rest(canvas, frame: RenderPass, x: float, y: float,
        note_type: String, dots: int, ink: Color, gap: float) -> void:
    score_layout.glyphs.paint(canvas, "rest_" + note_type, x, y, gap, ink, true)
    paint_rhythm_dots(canvas,frame,x, y+Geometry.rest_dot_offset(note_type)*gap,
        dots, ink, gap)


func paint_engraved_chord(canvas, frame: RenderPass, event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {}) -> Array:
    var key: String = score_layout.chord_template_key(event)
    if key.is_empty() or not score_layout.glyphs.has_chord(key):
        return []
    var beamed: bool = score_layout.beamed_note_ids.has(str(event.get("id","")))
    if beamed and (beam_stem.is_empty() or \
            not score_layout.glyphs.has_chord_heads(key) or \
            not score_layout.glyphs.has_chord_stem(key)):
        return []
    var group: Array = score_layout.chord_members.get(str(event.get("id","")),[])
    var heads: Array = score_layout.glyphs.chord_heads(key)
    if heads.size() != group.size():
        return []
    x += score_layout.voice_column_offset(event,gap,score_layout.cached_head_offsets)
    var sorted_heads: Array = score_layout.sorted_chord_members.get(
        str(event.get("id","")),[])
    if sorted_heads.is_empty():
        sorted_heads = group.duplicate()
        sorted_heads.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return Geometry.diatonic_index(a.get("spelling",{})) < \
                Geometry.diatonic_index(b.get("spelling",{})))
    var anchor: float = score_layout.event_y(event,gap)
    var head_centres: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var offset: Array = heads[i]
        var head_x: float = x+float(offset[0])*gap/250.0
        var head_y: float = anchor+float(offset[1])*gap/250.0
        var staff: String = str(current.get("staff","right"))
        var step: int = score_layout.prepared_step(current,gap)
        head_centres.append(Vector2(head_x,head_y))
        # Ledger rules must be UNDER the authentic filled noteheads.
        paint_ledger(canvas,frame,head_x,head_y,step,score_layout.staff_center(staff)+gap*2.0,
            gap,ink)
    if beamed:
        var extrema: Dictionary = score_layout.chord_extents(event,gap,score_layout.cached_head_offsets)
        var stem_up: bool = bool(beam_stem.get("up",true))
        var from_y: float = float(extrema[
            "bottom_y" if stem_up else "top_y"])
        if not score_layout.glyphs.paint_chord_stem(canvas,key,x,from_y,
                float(beam_stem["tip_y"]),gap,ink):
            return []
    var painted_ok: bool = (score_layout.glyphs.paint_chord_heads(
        canvas,key,x,anchor,gap,ink) if beamed else
        score_layout.glyphs.paint_chord(canvas,key,x,anchor,gap,ink))
    if not painted_ok:
        return []
    var dot_anchors: Dictionary = score_layout.chord_dot_anchors(sorted_heads,head_centres,gap)
    var painted: Array = []
    for i in range(sorted_heads.size()):
        var current: Dictionary = sorted_heads[i]
        var center: Vector2 = head_centres[i]
        var dot_anchor: Vector2 = dot_anchors.get(str(current.get("id","")),center)
        paint_rhythm_dots(canvas,frame,dot_anchor.x,dot_anchor.y,
            int(current.get("dots",0)),ink,gap)
        paint_note_accidental(canvas,frame,current,center.x,center.y,ink,gap)
        var id: String = str(current.get("id",""))
        frame.record_notehead(current,center,score_layout.size.x)
        painted.append(id)
    return painted


func paint_note(canvas, frame: RenderPass, event: Dictionary, x: float,
        gap: float, ink: Color, beam_stem: Dictionary = {},
        head_offset: float = 0.0) -> void:
    # Only local glyph separation: the source beat is unchanged.
    x += head_offset
    var staff: String = str(event.get("staff", "right"))
    var step: int = score_layout.prepared_step(event,gap)
    var bottom: float = score_layout.staff_center(staff) + gap*2.0
    var y: float = score_layout.event_y(event,gap)
    var kind: String = str(event.get("note_type", "quarter"))
    paint_ledger(canvas,frame,x, y, step, bottom, gap, ink)
    # Simple notes are complete Verovio-engraved sprites: no Godot stem,
    # flag or notehead assembly. Composite chords and beam groups have
    # variable geometry and are handled separately below.
    var isolated: bool = not bool(event.get("chord", false)) and \
        beam_stem.is_empty() and \
        score_layout.chord_members.get(str(event.get("id", "")), [event]).size() == 1
    if isolated:
        var normal_up: bool = bool(score_layout.chord_extents(event,gap)["up"])
        if not score_layout.glyphs.paint_note(canvas, kind, normal_up, x, y, gap, ink):
            # Atlas validation happens on load; missing artwork must never
            # silently revert to imitated musical ink.
            push_warning("Missing authentic Verovio note template: " + kind)
            return
        paint_rhythm_dots(canvas,frame,x,y,int(event.get("dots",0)),ink,gap)
        paint_note_accidental(canvas,frame,event,x,y,ink,gap)
        frame.record_notehead(event,Vector2(x,y),score_layout.size.x)
        return
    var solid: bool = kind not in ["half","whole"]
    score_layout.glyphs.paint(canvas, "head_black" if solid else (
        "head_whole" if kind == "whole" else "head_half"),
        x, y, gap, ink, true)
    # Beamed single-note attacks use an actual Verovio stem alpha mask;
    # the separate source beam determines its endpoint and stem direction.
    if not beam_stem.is_empty() and not bool(event.get("chord",false)):
        score_layout.glyphs.paint_note_stem(canvas,kind,bool(beam_stem["up"]),
            x,y,float(beam_stem["tip_y"]),gap,ink)
    paint_rhythm_dots(canvas,frame,x,y,int(event.get("dots",0)),ink,gap)
    paint_note_accidental(canvas,frame,event,x,y,ink,gap)
    frame.record_notehead(event,Vector2(x,y),score_layout.size.x)


func paint_beams(canvas, frame: RenderPass, data: Dictionary, gap: float) -> void:
    # There is no primitive-polygon fallback: load_score() already checked
    # that each expected multi-note group has genuine Verovio beam ink.
    for group in data.get("groups",[]):
        var members: Array = group.get("members",[])
        if members.size() < 2:
            continue
        var first: Dictionary = members[0]
        var last: Dictionary = members[-1]
        if float(last["head_x"]) < -40.0 or \
                float(first["head_x"]) > score_layout.size.x+40.0:
            continue
        # Regions were cut from the authentic Verovio beam at score load.
        # The frame path only changes one canvas translation and the hand ink.
        var regions: Array = group.get("regions",[])
        if regions.is_empty():
            continue
        var beam_texture: Texture2D = score_layout.glyphs.beam_textures.get(
            str(group["art_key"]))
        if beam_texture == null:
            continue
        canvas.draw_set_transform(Vector2(float(group.get("source_shift_x",0.0)),0.0))
        var ink: Color = frame.event_ink(score_layout,group)
        for region in regions:
            canvas.draw_texture_rect_region(beam_texture,region["dest"],
                region["source"],ink)
        canvas.draw_set_transform(Vector2.ZERO)


func paint_ties(canvas, frame: RenderPass, playhead_x: float, clock: float, gap: float) -> void:
    for pair in score_layout.tie_pairs:
        var previous: Dictionary = pair["first"]
        var event: Dictionary = pair["last"]
        if not frame.span_visible(previous,event):
            continue
        var x0: float = score_layout.timeline.screen_x(float(previous.get("beat",0.0)),
            clock,playhead_x,frame.play_from_beat)
        var x1: float = score_layout.timeline.screen_x(float(event.get("beat",0.0)),
            clock,playhead_x,frame.play_from_beat)
        if x1 < -20.0 or x0 > score_layout.size.x+20.0:
            continue
        # The tie's authentic shape and flagged-head clearance were
        # prepared when the score loaded. Only its translated X changes.
        var shift_x: float = playhead_x-(
            clock+frame.play_from_beat)*score_layout.timeline.pixels_per_beat
        var cached: Dictionary = connector_geometry.prepared_tie(previous,event,shift_x)
        if cached.is_empty():
            continue
        var texture: Texture2D = score_layout.glyphs.tie_textures.get(
            str(cached["direction"]))
        if texture != null:
            canvas.draw_texture_rect(texture,cached["rect"],false,
                frame.event_ink(score_layout,event))


func paint_tie_contour(canvas, frame: RenderPass, first: Dictionary, last: Dictionary,
        place: Dictionary, gap: float) -> void:
    var direction: String = connector_geometry.tie_template_key(first,last,place,gap)
    var texture: Texture2D = score_layout.glyphs.tie_textures.get(direction)
    if texture == null:
        return
    var rect: Rect2 = connector_geometry.tie_contour_rect(first,last,place,gap)
    if rect.has_area():
        canvas.draw_texture_rect(texture,rect,false,frame.event_ink(score_layout,last))


func paint_slurs(canvas, frame: RenderPass, playhead_x: float,clock: float,gap: float) -> void:
    for pair in score_layout.slur_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        if not frame.span_visible(first,last):
            continue
        var x0: float = score_layout.timeline.screen_x(float(first.get("beat",0.0)),
            clock,playhead_x,frame.play_from_beat)
        var x1: float = score_layout.timeline.screen_x(float(last.get("beat",0.0)),
            clock,playhead_x,frame.play_from_beat)
        if x0 > score_layout.size.x+50.0 or x1 < -50.0:
            continue
        var identity: String = connector_geometry.slur_identity(pair)
        var vertices: PackedVector2Array = connector_geometry.prepared_slurs.get(
            identity,PackedVector2Array())
        var ink_texture: Texture2D = score_layout.glyphs.slur_textures.get(
            str(pair["key"]))
        if vertices.size()!=4 or ink_texture == null:
            continue
        var shift_x: float = playhead_x-(
            clock+frame.play_from_beat)*score_layout.timeline.pixels_per_beat
        var ink: Color = frame.event_ink(score_layout,first)
        canvas.draw_set_transform(Vector2(shift_x,0.0))
        canvas.draw_polygon(vertices,PackedColorArray([ink,ink,ink,ink]),
            PackedVector2Array([Vector2.ZERO,Vector2(1.0,0.0),
                Vector2.ONE,Vector2(0.0,1.0)]),ink_texture)
        canvas.draw_set_transform(Vector2.ZERO)


func paint_grace_notes(canvas, frame: RenderPass, gap: float) -> void:
    # Every grace mark is attached to a *visible* graded notehead. Its
    # authentic complete Verovio note template is merely reduced in score_layout.size;
    # it has no playback clock event, scored attack or independent X motion.
    for grace in score_layout.attached_grace_notes:
        var target: String = str(grace.get("before_note_id", ""))
        if not frame.pass_noteheads.has(target):
            continue
        var hand: String = score_layout.display_staff(grace)
        var spelling: Dictionary = grace.get("spelling", {})
        var clef: Dictionary = score_layout.clef_for(hand, score_layout.measure_for(grace))
        var step: int = Geometry.staff_step(spelling, clef)
        var y: float = Geometry.note_y(step, score_layout.staff_center(hand)+gap*2.0,gap)
        var head: Vector2 = frame.pass_noteheads[target]
        var kind: String = str(grace.get("note_type", "eighth"))
        score_layout.glyphs.paint_note(canvas, kind, step < 4,
            head.x-gap*1.4, y, gap*.66, frame.event_ink(score_layout,grace))


static func tuplet_hidden(group: Dictionary) -> bool:
    return str(group.get("show_number","actual")) == "none" and \
        str(group.get("bracket","yes")) == "no"


## Caller filters source beam groups for this pass; no source index is copied.
func beam_layout(frame: RenderPass, head_offsets: Dictionary, visible_groups: Array) -> Dictionary:
    var result: Dictionary = connector_geometry.beam_layout(frame.gap,frame.clock,frame.playhead_x,
        head_offsets,frame.play_from_beat,visible_groups)
    frame.visible_beam_groups = result["visible_count"]
    result.erase("visible_count")
    return result
