extends RefCounted
# Semantic tuplet adapter shared by source validation and native painting.
# Every X still belongs to the transport's single quarter-beat timeline.
# This class creates no glyphs, paths, numbers, brackets or alternate clock.

static func groups(model: Dictionary) -> Array:
    var by_id: Dictionary = {}
    for event in model.get("notation_events",[]):
        if str(event.get("kind","")) in ["note","rest"]:
            by_id[str(event.get("id",""))] = event
    if not model.has("groups"):
        return _legacy(by_id)
    var result: Array = []
    var supplied: Variant = model["groups"]
    if supplied is Dictionary:
        supplied = supplied.values()
    if not supplied is Array:
        return result
    for source in supplied:
        if str(source.get("kind","")) != "tuplet":
            continue
        var identifier: String = str(source.get("id",""))
        if identifier.is_empty():
            continue
        var members: Array = []
        var seen: Dictionary = {}
        var valid := true
        for value in source.get("event_ids",[]):
            var event_id: String = str(value)
            if not by_id.has(event_id) or seen.has(event_id):
                valid = false
                break
            seen[event_id] = true
            if not bool(by_id[event_id].get("chord",false)):
                members.append(by_id[event_id])
        if valid and members.size() >= 2:
            result.append(_record(source,members,identifier))
    return result


static func _record(source: Dictionary,members: Array,asset_key: String) -> Dictionary:
    var attributes: Dictionary = source.get("attributes",{})
    var ratio: Variant = members[0].get("time_modification")
    if not ratio is Dictionary:
        ratio = {}
    return {"id":str(source.get("id",asset_key)),"key":asset_key,
        "events":members,"event_ids":_ids(members),
        "staff":source.get("staff",members[0].get("staff","right")),
        "voice":source.get("voice",members[0].get("voice","1")),
        "start_beat":source.get("start_beat",members[0].get("beat",0.0)),
        "end_beat":source.get("end_beat",members[-1].get("beat",0.0)),
        "actual":int(attributes.get("actual",ratio.get("actual",1))),
        "normal":int(attributes.get("normal",ratio.get("normal",1))),
        "bracket":str(attributes.get("bracket","no")),
        "show_number":str(attributes.get("show-number",attributes.get("show_number","actual"))),
        "attributes":attributes.duplicate()}


static func _ids(events: Array) -> PackedStringArray:
    var ids := PackedStringArray()
    for event in events:
        ids.append(str(event.get("id","")))
    return ids


static func _legacy(by_id: Dictionary) -> Array:
    var lanes: Dictionary = {}
    for event in by_id.values():
        if bool(event.get("chord",false)):
            continue
        var lane: String = str(event.get("staff","right"))+"|"+str(event.get("voice","1"))
        if not lanes.has(lane):
            lanes[lane] = []
        lanes[lane].append(event)
    var result: Array = []
    var counts: Dictionary = {}
    for lane in lanes.values():
        lane.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
            return float(a["beat"]) < float(b["beat"]))
        var opened: Dictionary = {}
        for event in lane:
            for mark in event.get("tuplet_marks",[]):
                if str(mark.get("type","")) == "start":
                    opened[str(mark.get("number","1"))] = {"events":[],"attributes":mark}
            for group in opened.values():
                group["events"].append(event)
            for mark in event.get("tuplet_marks",[]):
                var number: String = str(mark.get("number","1"))
                if str(mark.get("type","")) != "stop" or not opened.has(number):
                    continue
                var source: Dictionary = opened[number]
                opened.erase(number)
                var members: Array = source["events"]
                if members.size() < 2:
                    continue
                var ids: PackedStringArray = _ids(members)
                var attributes: Dictionary = source["attributes"]
                var identifier: String = str(attributes.get("source_id",attributes.get("id","")))
                if identifier.is_empty():
                    identifier = "tuplet:%s:%s:%s:%s:%s" % [
                        members[0].get("staff","right"),members[0].get("voice","1"),
                        number,ids[0],ids[-1]]
                source["id"] = identifier
                var asset_key: String = "|".join(ids)
                result.append(_record(source,members,asset_key))
                counts[asset_key] = int(counts.get(asset_key,0))+1
    for group in result:
        if int(counts[group["key"]]) > 1:
            group["key"] = group["id"]
    return result


static func key(group: Dictionary) -> String:
    return str(group.get("key",group.get("id","")))


static func missing(tuplets: Array,glyphs) -> String:
    for group in tuplets:
        if group.get("events",[]).size() < 2:
            continue
        var asset_key: String = key(group)
        if not glyphs.has_tuplet(asset_key,str(group.get("bracket","no")) == "yes",
                str(group.get("show_number","actual")) != "none"):
            return "Missing engraved Verovio tuplet: "+asset_key
    return ""


static func placement(group: Dictionary,timeline,clock: float,playhead_x: float,
        play_from_beat: float,gap: float,head_offsets: Dictionary,
        event_y: Callable) -> Dictionary:
    var events: Array = group.get("events",[])
    if events.size() < 2:
        return {}
    # Rest endpoints are genuine SVG anchors too. Apply chord displacement
    # only to pitched heads, never to a rest or to a musical onset itself.
    var first: Dictionary = events[0]
    var last: Dictionary = events[-1]
    var x0: float = timeline.screen_x(float(first["beat"]),clock,playhead_x,play_from_beat)
    var x1: float = timeline.screen_x(float(last["beat"]),clock,playhead_x,play_from_beat)
    if str(first.get("kind","")) == "note":
        x0 += float(head_offsets.get(str(first["id"]),0.0))
    if str(last.get("kind","")) == "note":
        x1 += float(head_offsets.get(str(last["id"]),0.0))
    if x1 <= x0:
        return {}
    return {"key":key(group),"x0":x0,"x1":x1,
        "y":float(event_y.call(first,gap)),"staff":group.get("staff","right")}
