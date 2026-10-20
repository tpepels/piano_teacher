extends RefCounted
# Immutable event and compound index: no CanvasItem, clock, paint or GPU.
const Geometry := preload("res://notation/native/geometry.gd")

static func build(model: Dictionary, glyphs) -> Dictionary:
    # Source-Verovio beam groups are authoritative. Inferring meter-based
    # beams here incorrectly connected separately flagged Chopin notes.
    var source_beams: Dictionary = source_beam_groups(model, glyphs)
    var beam_groups: Array = source_beams.get("groups",[])
    var beamed_note_ids: Dictionary = Geometry.beamed_ids(beam_groups)
    var beam_stem_up_by_note: Dictionary = source_beams.get("stem_up_by_note",{})
    var notation_tuplets: Array = Geometry.tuplet_groups(model)
    var measure_by_number: Dictionary = {}
    for measure in model.get("measures",[]):
        measure_by_number[int(measure.get("number", -1))] = measure
    var ordered_events: Array = model.get("notation_events", []).duplicate()
    ordered_events.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        var beat_a: float = float(a.get("beat", 0.0))
        var beat_b: float = float(b.get("beat", 0.0))
        if absf(beat_a-beat_b) > .000001:
            return beat_a < beat_b
        # A chord leader MUST be painted before any child at this beat.
        # sort_custom does not promise stable ordering of equal keys.
        var lane_a: String = str(a.get("staff",""))+"|"+ \
            str(a.get("voice","1"))+"|"+str(a.get("measure",0))
        var lane_b: String = str(b.get("staff",""))+"|"+ \
            str(b.get("voice","1"))+"|"+str(b.get("measure",0))
        if lane_a != lane_b:
            return lane_a < lane_b
        var child_a: bool = bool(a.get("chord",false))
        var child_b: bool = bool(b.get("chord",false))
        if child_a != child_b:
            return not child_a
        return str(a.get("id","")) < str(b.get("id","")))
    var chord_members: Dictionary = Geometry.chord_members(ordered_events)
    # Cache the preceding attack for every measure once. Tight meter
    # changes must be relocated out of the ink; no per-frame note scan.
    var previous_attack_before_measure: Dictionary = {}
    var scan := 0
    var last_attack := -INF
    for measure in model.get("measures",[]):
        var boundary: float = float(measure.get("start_beat", 0.0))
        while scan < ordered_events.size() and \
                float(ordered_events[scan].get("beat",0.0)) < boundary-.0001:
            if str(ordered_events[scan].get("kind","")) == "note":
                last_attack = float(ordered_events[scan].get("beat",0.0))
            scan += 1
        previous_attack_before_measure[int(measure.get("number",0))] = last_attack
    var tie_pairs: Array = []
    var unfinished: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind", "")) != "note":
            continue
        var source_id: String = str(event.get("source_id", ""))
        if bool(event.get("tie_stop", false)) and unfinished.has(source_id):
            tie_pairs.append({"first": unfinished[source_id], "last": event})
        if bool(event.get("tie_start", false)):
            unfinished[source_id] = event
        else:
            unfinished.erase(source_id)
    var slur_pairs: Array = []
    var by_id: Dictionary = {}
    for event in ordered_events:
        if str(event.get("kind","")) == "note":
            by_id[str(event.get("id",""))] = event
    for key in glyphs.slur_keys():
        var ids: Array = glyphs.slur_note_ids(str(key))
        if ids.size() == 2 and by_id.has(str(ids[0])) and by_id.has(str(ids[1])):
            var first: Dictionary = by_id[str(ids[0])]
            var last: Dictionary = by_id[str(ids[1])]
            if float(first.get("beat",0.0)) < float(last.get("beat",0.0)):
                slur_pairs.append({"key":str(key),"first":first,"last":last})

    return {"beam_groups":beam_groups,"beamed_note_ids":beamed_note_ids,
        "beam_stem_up_by_note":beam_stem_up_by_note,
        "notation_tuplets":notation_tuplets,"measure_by_number":measure_by_number,
        "ordered_events":ordered_events,"chord_members":chord_members,
        "previous_attack_before_measure":previous_attack_before_measure,
        "tie_pairs":tie_pairs,"slur_pairs":slur_pairs}


static func source_beam_groups(model: Dictionary, glyphs) -> Dictionary:
    var notes: Dictionary = {}
    for event in model.get("notation_events",[]):
        if str(event.get("kind","")) == "note" and \
                not bool(event.get("chord",false)):
            notes[str(event.get("id",""))] = event
    var output: Array = []
    var directions: Dictionary = {}
    # Metadata is extracted from each original Verovio SVG beam group.
    for key in glyphs.beam_metadata:
        var data: Dictionary = glyphs.beam_metadata[key]
        var ids: Array = data.get("note_ids",[])
        var attacks: Array = []
        for identifier in ids:
            if notes.has(str(identifier)):
                attacks.append(notes[str(identifier)])
        if attacks.size() != ids.size() or attacks.size() < 2:
            continue
        var valid: bool = true
        for index in range(1,attacks.size()):
            if float(attacks[index]["beat"]) <= \
                    float(attacks[index-1]["beat"]) or \
                    str(attacks[index]["staff"]) != \
                    str(attacks[0]["staff"]) or \
                    str(attacks[index]["voice"]) != \
                    str(attacks[0]["voice"]):
                valid = false
                break
        if valid:
            output.append(attacks)
            for event in attacks:
                directions[str(event.get("id",""))] = bool(data["stem_up"])
    output.sort_custom(func(a: Array,b: Array) -> bool:
        return float(a[0].get("beat",0.0)) < \
            float(b[0].get("beat",0.0)))
    return {"groups":output,"stem_up_by_note":directions}


