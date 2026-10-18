extends SceneTree

var failures: Array[String] = []
func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("PHASE_C2_FAIL: ", label)

func note(identifier: String, beat: float, duration: float,
        hand: String = "right", voice: String = "1",
        measure: int = 1, kind: String = "eighth",
        chord: bool = false) -> Dictionary:
    return {"id":identifier, "source_id":identifier,
        "kind":"note", "beat":beat, "duration_beats":duration,
        "staff":hand, "voice":voice, "measure":measure,
        "note_type":kind, "dots":0, "chord":chord,
        "is_attack":true, "accidental":null, "time_modification":null,
        "spelling":{"step":"G", "octave":4 if hand == "right" else 2,
                    "alter":0}}

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Geometry = load("res://score_notation_geometry.gd")
    var Native = load("res://score_native_notation.gd")
    check(Geometry != null and Native != null, "Phase C2 modules parse")
    if Geometry == null or Native == null:
        quit(1)
        return
    var clefs := {"right":{"sign":"G","line":2},
                   "left":{"sign":"F","line":4}}
    var events: Array = [
        note("a", 0.0,.25, "right","1",1,"16th"),
        note("b", .25,.25, "right","1",1,"16th"),
        note("c", .50,.50),
        note("chord_c",.50,.50,"right","1",1,"eighth",true),
        note("d", 1.0,.50),
        note("e", 1.5,.50),
        note("f", 2.0,.50),
        note("g", 2.5,.50),
        note("h", 3.0,.5),
        note("other_voice", 2.0,.5, "right","2"),
        note("i", 4.0,.50,"right","1",2),
        note("j", 4.5,.50,"right","1",2),
        note("k", 5.0,.50,"right","1",2),
        note("l", 5.5,.50,"right","1",2),
        note("m", 6.0,.50,"right","1",2),
        note("n", 6.5,.50,"right","1",2)]
    var measures := [
        {"number":1,"start_beat":0.0,"end_beat":4.0,
            "meter":[4,4],"clefs":clefs,"keys":{"right":0,"left":0}},
        {"number":2,"start_beat":4.0,"end_beat":7.0,
            "meter":[6,8],"clefs":clefs,"keys":{"right":0,"left":0}}]
    var score := {"schema":"piano-teacher-score-model-v1",
        "revision":55,"duration_beats":7.0,"beat_unit":"quarter",
        "measures":measures,"active_hand":"right",
        "notes":[],"notation_events":events}
    for event in events:
        if not bool(event["chord"]):
            score["notes"].append({
                "id":event["id"],"onset_beats":event["beat"],
                "duration_beats":event["duration_beats"],
                "midi_pitch":67,"hand":event["staff"]})
    var groups: Array = Geometry.beam_groups(score)
    check(groups.size() == 6, "Two groups in 4/4, two in 6/8, plus isolated voices")
    var by_first: Dictionary = {}
    for group in groups:
        by_first[str(group[0]["id"])] = group.map(func(e):return e["id"])
    check(by_first.get("a",[]) == ["a","b","c"],
        "Two sixteenths + eighth join inside one quarter group")
    check(by_first.get("d",[]) == ["d","e"],
        "Eighths join on the following quarter beat")
    check(by_first.get("f",[]) == ["f","g"],
        "Same-staff second voice must not steal beams")
    check(by_first.get("i",[]) == ["i","j","k"],
        "6/8 groups into three eighths, not a 4/4 pattern")
    check(by_first.get("l",[]) == ["l","m","n"],
        "Compound-beat boundary starts the next group")
    check(not by_first.has("other_voice"),
        "Single independent voice remains flagged, not accidentally beamed")
    var lookup: Dictionary = Geometry.beamed_ids(groups)
    check(lookup.has("a") and lookup.has("c") and not lookup.has("chord_c"),
        "Chord tone shares leader's beam without a duplicate stem")
    var renderer = Native.new()
    get_root().add_child(renderer)
    renderer.size = Vector2(1360, 460)
    check(renderer.load_score(score), "Native loads grouped rhythms")
    check(renderer.beam_groups.size() == groups.size(),
        "Native renderer caches semantic beam plan per lesson")
    check(renderer.set_density(112.0),"Density remains configurable")
    var clock := .75
    var offset := 0.0
    var beam_before: Dictionary = renderer._beam_layout(renderer._gap(),clock,580.0)
    renderer.present({"bpm":40,"running":true,"paused":false,
        "count_in_beats":4,"play_from_beat":offset,
        "transport_id":7,"hand":"right"},clock)
    var beam_after: Dictionary = renderer._beam_layout(renderer._gap(),clock,580.0)
    check(beam_before["stems"].size() == beam_after["stems"].size(),
        "All cached beam stems independent of BPM")
    for identifier in beam_before["stems"]:
        check(beam_before["stems"][identifier] == beam_after["stems"][identifier],
            "All grouped noteheads share exactly the same time axis")
    var rest_score: Dictionary = score.duplicate(true)
    rest_score["notation_events"].insert(1, {
        "id":"rest1","kind":"rest","staff":"right","voice":"1",
        "measure":1,"beat":.25,"duration_beats":.25,
        "note_type":"16th","chord":false})
    rest_score["notation_events"][2]["beat"] = .50
    # A rest interrupts: no beams should span it.
    var broken: Array = Geometry.beam_groups(rest_score)
    var broken_lookup: Dictionary = Geometry.beamed_ids(broken)
    check(not broken_lookup.has("a"),"Rest splits a beam group")
    var unsupported: Dictionary = score.duplicate(true)
    unsupported["measures"][1]["meter"] = [7,8]
    check(Geometry.beam_groups(unsupported).size() < groups.size(),
        "Irregular grouping is not guessed")
    renderer.clear_score()
    check(renderer.beam_groups.is_empty() and renderer.beamed_note_ids.is_empty(),
        "Changing lessons discards previously cached beams")
    print("PHASE_C2_BEAM_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
