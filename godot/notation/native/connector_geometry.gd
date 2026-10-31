extends RefCounted
## Source-bound connector plans, independent of paint and transport ownership.
## Owns only authentic tie/flag contour cache; event geometry belongs to ScoreLayout.
var score
var flag_clearances: Dictionary = {}
var prepared_ties: Dictionary = {}
var prepared_beams: Dictionary = {}

func _init(score_layout) -> void:
    score = score_layout

func clear_cache() -> void:
    flag_clearances.clear()
    prepared_ties.clear()
    prepared_beams.clear()

# Flag/tie intersection uses CPU pixel scans and texture.get_image().
# Every tie has a camera-invariant head-to-head distance, so calculate its
# clearance once when the score is installed, before playback can start.
# Painting a later measure may only look up the existing result.
func prewarm_tie_clearances(gap: float) -> void:
    prepared_ties.clear()
    for pair in score.tie_pairs:
        var first: Dictionary = pair["first"]
        var last: Dictionary = pair["last"]
        var first_x: float = score.timeline.x_at_beat(float(first.get("beat", 0.0)))
        var last_x: float = score.timeline.x_at_beat(float(last.get("beat", 0.0)))
        var placement: Dictionary = tie_placement(first, last, first_x, last_x, gap)
        if not placement.is_empty():
            var rect: Rect2 = tie_contour_rect(first, last, placement, gap)
            if rect.has_area():
                var key: String = str(first.get("id",""))+"|"+str(last.get("id",""))
                prepared_ties[key] = {
                    "direction":tie_template_key(first,last,placement,gap),
                    "rect":rect}

func prepared_tie(first: Dictionary, last: Dictionary, shift_x: float) -> Dictionary:
    var key: String = str(first.get("id",""))+"|"+str(last.get("id",""))
    if not prepared_ties.has(key):
        return {}
    var cached: Dictionary = prepared_ties[key]
    var base: Rect2 = cached["rect"]
    return {"direction":cached["direction"],
        "rect":Rect2(base.position+Vector2(shift_x,0.0),base.size)}

func prewarm_beam_layout(gap: float, head_offsets: Dictionary) -> void:
    # Build every beam with source X coordinates once, without viewport
    # clipping. Playback only translates those prebuilt members.
    prepared_beams.clear()
    var all: Dictionary = beam_layout(
        gap,0.0,0.0,head_offsets,0.0,score.beam_groups,true)
    for item in all["groups"]:
        prepared_beams[str(item["art_key"])] = item

func tie_placement(first: Dictionary, last: Dictionary,
        x0: float, x1: float, gap: float) -> Dictionary:
    var left: float = x0+float(score.cached_head_offsets.get(
        str(first.get("id","")),0.0))
    var right: float = x1+float(score.cached_head_offsets.get(
        str(last.get("id","")),0.0))
    if right-left <= gap*1.2:
        return {}
    return {"x0":left, "x1":right, "y":score.event_y(first,gap),
        "down":tie_bow_down(first,last,gap)}

func tie_chord_leader(event: Dictionary) -> Dictionary:
    if bool(event.get("chord",false)):
        # Locate only simultaneous events, including a child's real leader.
        # Do not scan the full performance's chord dictionary per frame.
        var beat: float = float(event.get("beat",0.0))
        var begin := 0
        var end: int = score.ordered_events.size()
        while begin < end:
            var middle: int = (begin+end) >> 1
            if float(score.ordered_events[middle].get("beat",0.0)) < beat-.000001:
                begin = middle+1
            else:
                end = middle
        for index in range(begin,score.ordered_events.size()):
            var candidate: Dictionary = score.ordered_events[index]
            if float(candidate.get("beat",0.0)) > beat+.000001:
                break
            if not bool(candidate.get("chord",false)) and \
                    str(candidate.get("kind","")) == "note" and \
                    candidate.get("staff") == event.get("staff") and \
                    candidate.get("voice") == event.get("voice") and \
                    candidate.get("measure") == event.get("measure"):
                return candidate
    return event

func tie_bow_down(first: Dictionary, last: Dictionary, gap: float) -> bool:
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
    var leader: Dictionary = tie_chord_leader(first)
    var extents: Dictionary = score.chord_extents(leader,gap)
    var y: float = score.event_y(first,gap)
    var middle_y: float = (float(extents["top_y"])+float(extents["bottom_y"]))* .5
    # Original chord ties face away from the chord interior, independently
    # of the shared stem. The middle note of an odd chord keeps its stem rule.
    if absf(y-middle_y) > .001:
        return y > middle_y
    return bool(score.beam_stem_up_by_note.get(str(leader.get("id","")),extents["up"]))

func tie_template_key(first: Dictionary, last: Dictionary, place: Dictionary, gap: float) -> String:
    var down: bool = bool(place["down"])
    var ordinary: String = "up" if down else "down"
    var endpoint: Dictionary = last if down else first
    var leader: Dictionary = tie_chord_leader(endpoint)
    var kind: String = str(leader.get("note_type","quarter"))
    if kind not in ["eighth","16th","32nd","64th","128th"]:
        return ordinary
    var id: String = str(leader.get("id",""))
    # Written beams own the shaft: a short duration does not imply a flag.
    if score.beamed_note_ids.has(id) or score.beam_stem_up_by_note.has(id):
        return ordinary
    var up: bool = bool(score.chord_extents(leader,gap)["up"])
    if up==down:
        return ordinary
    return ("end_"+kind+"_below") if down else ("start_"+kind+"_above")

func tie_contour_rect(first: Dictionary, last: Dictionary,
        place: Dictionary, gap: float) -> Rect2:
    var direction: String = tie_template_key(first,last,place,gap)
    var data: Dictionary = score.glyphs.tie_metadata[direction]
    var box: Array = data["bounds"]
    var source_head: Array = score.glyphs.bounds["head_half"]
    var source_center: float = float(source_head[0])+float(source_head[2])*.5
    var source_centers: Array = data.get("head_centers",[source_center,source_center])
    var source_widths: Array = data.get("head_widths",[source_head[2],source_head[2]])
    var widths: Array[float] = []
    for event in [first,last]:
        var kind: String = str(event.get("note_type","quarter"))
        var name: String = "head_"+(kind if kind in ["whole","half"] else "black")
        widths.append(float(score.glyphs.bounds[name][2]))
    var unit: float = gap/250.0
    # Each template records its actual endpoint head families; native
    # musical X is the centre of each displayed head. Keep Verovio's
    # head-edge clearances in staff units, including a wider whole head.
    # Stretch the contour itself, never the empty endpoint margins.
    var left_inset: float = (float(box[0])-float(source_centers[0])+
        (widths[0]-float(source_widths[0]))*.5)*unit
    var right_inset: float = (float(box[0])+float(box[2])-
        float(data["span"])-float(source_centers[1])-
        (widths[1]-float(source_widths[1]))*.5)*unit
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
    # A chord's authentic flag can sit lower than the single-note flag
    # used to engrave the tie atlas. Preserve that curve, but clear the
    # actual endpoint sprite, including its displaced chord head origin.
    if direction.begins_with("start_"):
        left = tie_clear_flag(first,direction,left,right,
            Vector2(float(place["x0"]),float(place["y"])),gap)
    elif direction.begins_with("end_"):
        right = tie_clear_flag(last,direction,left,right,
            Vector2(float(place["x1"]),float(place["y"])),gap)
    if right <= left:
        return Rect2()
    return Rect2(left,
        float(place["y"])+float(box[1])*unit,
        right-left,float(box[3])*unit)

func tie_clear_flag(event: Dictionary, direction: String, left: float,
        right: float, origin: Vector2, gap: float) -> float:
    var start: bool = direction.begins_with("start_")
    var unit: float = gap/250.0
    var lo: float = (left-origin.x)/unit
    var hi: float = (right-origin.x)/unit
    var leader: Dictionary = tie_chord_leader(event)
    var chord: String = score.chord_template_key(leader)
    # Single-note flags already have matching endpoint-specific tie artwork.
    # Only compound sprites introduce the different stem length at issue.
    if chord.is_empty():
        return left if start else right
    var texture: Texture2D = score.glyphs.chord_textures[chord]
    var bounds: Array = score.glyphs.chord_metadata[chord]["bounds"]
    var shift := Vector2((float(score.cached_head_offsets.get(str(leader.get("id","")),0.0))-
        float(score.cached_head_offsets.get(str(event.get("id","")),0.0)))/unit,
        (score.event_y(leader,gap)-origin.y)/unit)
    var key: String = "%s|%s|%.4f|%.4f|%.4f|%.4f" % [direction,chord,lo,hi,shift.x,shift.y]
    if flag_clearances.has(key):
        return origin.x+float(flag_clearances[key])*unit
    var flag: Image = texture.get_image()
    var curve: Image = score.glyphs.tie_textures[direction].get_image()
    var box: Array = score.glyphs.tie_metadata[direction]["bounds"]
    var cell := Vector2(float(bounds[2])/flag.get_width(),float(bounds[3])/flag.get_height())
    var edge: float = lo if start else hi
    # Solve each authentic curve row against the endpoint's photographed
    # flag silhouette. A whole enclosing flag rectangle would needlessly
    # detach the tip from its head. Keep a small ink-to-ink staff-space gap.
    var clearance := 20.0  # .08 staff spaces, independent of screen scale.
    var head_half: float = float(score.glyphs.bounds["head_black"][2])*.5
    for row in range(curve.get_height()):
        var column := 0 if start else curve.get_width()-1
        var advance := 1 if start else -1
        while column >= 0 and column < curve.get_width() and curve.get_pixel(column,row).a == 0.0:
            column += advance
        if column < 0 or column >= curve.get_width():
            continue
        var fraction: float = float(column if start else column+1)/curve.get_width()
        var top: float = float(box[1])+float(row)*float(box[3])/curve.get_height()
        var bottom: float = top+float(box[3])/curve.get_height()
        var first_row: int = maxi(0,floori((top-clearance-shift.y-float(bounds[1]))/cell.y))
        var last_row: int = mini(flag.get_height()-1,floori((bottom+clearance-shift.y-float(bounds[1]))/cell.y))
        for y in range(first_row,last_row+1):
            for x in range(flag.get_width()):
                if flag.get_pixel(x,y).a == 0.0:
                    continue
                var ink_x: float = float(bounds[0])+shift.x+float(x+(1 if start else 0))*cell.x
                if (start and ink_x <= head_half) or (not start and ink_x >= -head_half):
                    continue  # The head and shaft have their own attachment.
                if start and fraction < 1.0:
                    edge = maxf(edge,(ink_x+clearance-fraction*hi)/(1.0-fraction))
                elif not start and fraction > 0.0:
                    edge = minf(edge,(ink_x-clearance-(1.0-fraction)*lo)/fraction)
    # In an impossibly tight interval keep visible ink and its original
    # bow height; never omit the tie to conceal a remaining collision.
    var minimum: float = minf(hi-lo,float(box[3]))
    edge = minf(edge,hi-minimum) if start else maxf(edge,lo+minimum)
    flag_clearances[key] = edge
    return origin.x+edge*unit


# Binary-search into pre-sorted MusicXML events. Work is proportional
# to what the pianist can actually see, not to the whole imported MIDI.

func beam_layout(gap: float, clock: float, playhead_x: float,
        head_offsets: Dictionary, play_from_beat: float, visible_groups: Array,
        include_offscreen: bool = false) -> Dictionary:
    # Beam position is derived from the real notehead Y coordinates.
    # All horizontal positions still come from the one musical-time axis.
    var stems: Dictionary = {}
    var drawn_groups: Array = []
    var visible_count := 0
    for group in visible_groups:
        if group.size() < 2:
            continue
        var first_x: float = score.timeline.screen_x(
            float(group[0].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        var last_x: float = score.timeline.screen_x(
            float(group[-1].get("beat", 0.0)), clock, playhead_x, play_from_beat)
        if not include_offscreen and (last_x < -60.0 or first_x > score.size.x + 60.0):
            continue
        visible_count += 1
        var up: bool = bool(score.beam_stem_up_by_note[str(group[0].get("id",""))])
        var group_ids := PackedStringArray()
        for event in group:
            group_ids.append(str(event.get("id","")))
        var source_key: String = "|".join(group_ids)
        if not include_offscreen and prepared_beams.has(source_key):
            var canonical: Dictionary = prepared_beams[source_key]
            var shift_x: float = playhead_x-(
                clock+play_from_beat)*score.timeline.pixels_per_beat
            var projected_members: Array = []
            for source_member in canonical["members"]:
                var shifted: Dictionary = source_member.duplicate(false)
                shifted["x"] = float(source_member["x"])+shift_x
                shifted["head_x"] = float(source_member["head_x"])+shift_x
                projected_members.append(shifted)
                stems[str(shifted["id"])] = {"up":canonical["up"],
                    "tip_y":shifted["tip_y"],"x":shifted["x"]}
            var painted: Dictionary = canonical.duplicate(false)
            painted["members"] = projected_members
            drawn_groups.append(painted)
            continue
        var members: Array = []
        var source_stems: Array = []
        var source_heads: Array = score.glyphs.beam_metadata[source_key]["head_offsets"]
        var head_box: Array = score.glyphs.bounds["head_black"]
        var origin_to_center: float = float(head_box[0])+float(head_box[2])*.5
        for index in range(group.size()):
            var event: Dictionary = group[index]
            var x: float = score.timeline.screen_x(float(event.get("beat", 0.0)),
                clock, playhead_x, play_from_beat)
            var chord: Dictionary = score.chord_extents(event,gap,head_offsets)
            var stem_box: Array = score.source_stem_bounds(event,up)
            var attachment: float = float(stem_box[0])+float(stem_box[2])*.5
            var stem_x: float = x+score.voice_column_offset(event,gap,head_offsets)+attachment*gap/250.0
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
        var art_tips: Array = score.glyphs.beam_tips(art_key)
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
            "hand":score.performing_hand(group[0]),
            "up":up, "art_key":art_key,
            "source_stem_offsets":source_stems,
            # Beam bounds are exported relative to the first source ID,
            # which may be an inner/higher chord tone. Stem tip offsets
            # deliberately use the outer tone and have a different origin.
            "anchor_y":score.event_y(group[0],gap)})
    return {"stems":stems, "groups":drawn_groups, "visible_count":visible_count}
