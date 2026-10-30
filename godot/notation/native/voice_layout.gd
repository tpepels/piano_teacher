extends RefCounted
# Pure multi-voice engraving layout. Source voice order, explicit source stems
# and authentic Verovio notehead bounds remain authoritative. This component
# computes no score clock positions and never paints on the CanvasItem.

static func stem_directions(ordered_events: Array, chord_members: Dictionary,
        event_y_by_id: Dictionary) -> Dictionary:
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
        if leaders.size() < 2:
            continue
        var distinct_voices: Dictionary = {}
        for leader in leaders:
            distinct_voices[str(leader.get("voice","1"))] = true
        if distinct_voices.size() != leaders.size():
            # There is no unambiguous voice-level stem decision here.
            # Existing source stems and beam directions retain priority.
            continue
        leaders.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return str(a.get("voice","1")).naturalnocasecmp_to(str(b.get("voice","1"))) < 0)
        var ranges: Array = []
        for leader in leaders:
            var low := INF
            var high := -INF
            var members: Array = chord_members.get(str(leader.get("id","")),[leader])
            for member in members:
                var y: float = float(event_y_by_id[str(member.get("id",""))])
                low = minf(low,y)
                high = maxf(high,y)
            ranges.append(Vector2(low,high))
        if leaders.size() > 2:
            # Previously this entire onset silently fell back to single-
            # voice defaults. Order the actual source voice ranges top to
            # bottom (smaller screen Y means higher pitch), breaking exact
            # pitch ties by source voice order. Assign both directions and
            # leave same-direction unisons to column_offsets() to separate.
            var by_height: Array[int] = []
            for index in range(leaders.size()):
                by_height.append(index)
            by_height.sort_custom(func(a: int, b: int) -> bool:
                var first: float = (ranges[a].x+ranges[a].y)*.5
                var second: float = (ranges[b].x+ranges[b].y)*.5
                if absf(first-second) < .001:
                    return a < b
                return first < second)
            var upper_count: int = ceili(float(by_height.size())/2.0)
            for rank in range(by_height.size()):
                var leader_index: int = by_height[rank]
                var members: Array = chord_members.get(
                    str(leaders[leader_index].get("id","")),[leaders[leader_index]])
                for member in members:
                    directions[str(member.get("id",""))] = rank < upper_count
            continue
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

static func head_family(event: Dictionary) -> String:
    var kind: String = str(event.get("note_type","quarter"))
    return "head_"+(kind if kind in ["whole","half"] else "black")

static func column_offsets(ordered_events: Array, chord_members: Dictionary,
        stem_up_by_id: Dictionary, glyph_bounds: Dictionary,
        heads: Dictionary, event_y_by_id: Dictionary, gap: float) -> Dictionary:
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
            var a_up: bool = bool(stem_up_by_id.get(str(a.get("id","")), false))
            var b_up: bool = bool(stem_up_by_id.get(str(b.get("id","")), false))
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
            var up: bool = bool(stem_up_by_id.get(str(leader.get("id","")), false))
            var shift := 0.0
            for previous in placed:
                if str(previous["leader"].get("voice","1")) == str(leader.get("voice","1")):
                    continue
                for member in members:
                    for other in previous["members"]:
                        if absf(float(event_y_by_id[str(member.get("id",""))])-float(event_y_by_id[str(other.get("id",""))])) > gap*.51:
                            continue
                        var same_pitch: bool = absf(float(event_y_by_id[str(member.get("id",""))])-float(event_y_by_id[str(other.get("id",""))])) < .001
                        if same_pitch and head_family(member) == head_family(other) and up != bool(previous["up"]):
                            continue
                        if not int(previous["index"]) in links[index]:
                            links[index].append(int(previous["index"]))
                            links[int(previous["index"])].append(index)
                        var box: Array = glyph_bounds[head_family(member)]
                        var other_box: Array = glyph_bounds[head_family(other)]
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
