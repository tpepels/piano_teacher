extends RefCounted

# Pure rest placement on source ink envelopes supplied by the owning layout.
# The renderer keeps responsibility for glyphs, staff mapping and caching.
const RestLaneLayout := preload("res://notation/native/rest_lane_layout.gd")

static func plan(events: Array, gap: float, density: float,
        heads: Dictionary, accidentals: Dictionary, ink_rect: Callable) -> Dictionary:
    var offsets: Dictionary = {}
    var unavoidable := 0
    var voices_by_measure: Dictionary = {}
    var obstacles: Dictionary = {}
    for event in events:
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        if not voices_by_measure.has(lane_key):
            voices_by_measure[lane_key] = {}
            obstacles[lane_key] = []
        var voice: String = str(event.get("voice","1"))
        voices_by_measure[lane_key][voice] = true
        if str(event.get("kind","")) != "note":
            continue
        var ink: Rect2 = ink_rect.call(event,gap,heads,accidentals)
        ink.position.x += float(event.get("beat",0.0))*density
        obstacles[lane_key].append({"voice":voice,"ink":ink})
    for event in events:
        if str(event.get("kind","")) != "rest":
            continue
        var lane_key: String = str(event.get("staff","right"))+"|"+str(
            event.get("measure",-1))
        var id: String = str(event.get("id",""))
        var voice: String = str(event.get("voice","1"))
        var voices: Array = voices_by_measure[lane_key].keys()
        voices.sort()
        offsets[id] = 0.0
        var source_rect: Rect2 = ink_rect.call(event,gap,heads,accidentals)
        source_rect.position.x += float(event.get("beat",0.0))*density
        var placement: Dictionary = RestLaneLayout.place_rest(
            source_rect, voice, voices,
            str(event.get("note_type","quarter")),gap,obstacles[lane_key])
        offsets[id] = placement["shift"]
        obstacles[lane_key].append({"voice":voice,"ink":placement["ink"]})
        if not bool(placement["placed"]):
            unavoidable += 1
    return {"offsets":offsets,"unavoidable":unavoidable}
