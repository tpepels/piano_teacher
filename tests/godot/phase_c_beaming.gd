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
    check(absf(Geometry.beat_group_length([3,8])-1.5) < .0001,
        "3/8 uses a single dotted-quarter group")
    check(absf(Geometry.beat_group_length([2,2])-2.0) < .0001,
        "2/2 uses half-note pulse instead of quarter group")
    check(absf(Geometry.beat_group_length([4,16])-.5) < .0001,
        "4/16 retains eighth-note grouping")
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
    check(groups.size() == 5, "Three groups in 4/4 and two in compound 6/8")
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
    check(Geometry.signature_steps(clefs["right"],3).size() == 3,
        "Three-sharp key signature produces three individually positioned signs")
    check(Geometry.signature_steps(clefs["right"],-2) == [4,7],
        "B-flat and E-flat have real diatonic staff positions")
    check(Geometry.signature_steps(clefs["left"],-2) != [4,7],
        "Bass clef key signature is not copied from the treble staff")
    var close_chord: Array = [
        note("c4", 0.0, 1.0, "right", "1", 1, "quarter"),
        note("d4", 0.0, 1.0, "right", "1", 1, "quarter",true)]
    close_chord[0]["spelling"] = {"step":"C","octave":4}
    close_chord[1]["spelling"] = {"step":"D","octave":4}
    var shifts: Dictionary = Geometry.chord_offsets(close_chord,12.0)
    check(shifts.has("c4") and shifts.has("d4"),
        "Adjacent chord seconds gain local collision-free glyph positions")
    check(absf(float(shifts["c4"])-float(shifts["d4"])) >= 17.0,
        "Adjacent noteheads must not visually overlap at ordinary scale")
    var renderer = Native.new()
    get_root().add_child(renderer)
    renderer.size = Vector2(1360, 460)
    check(renderer.set_verovio_glyphs(
        load("res://tests/native_glyph_fixture.gd").catalogue()),
        "Unit test has Verovio-shaped placeholder textures")
    check(renderer.load_score(score), "Native loads grouped rhythms")
    check(renderer.beam_groups.size() == groups.size(),
        "Native renderer caches semantic beam plan per lesson")
    var all_chord_heads: Dictionary = score.duplicate(true)
    for item in all_chord_heads["notation_events"]:
        if str(item.get("id","")) == "chord_c":
            item["spelling"] = {"step":"C","octave":5}
    check(renderer.load_score(all_chord_heads),"Beamed chord notation is supported")
    var beamed_gap: float = renderer._gap()
    var compound: Dictionary = renderer._beam_layout(beamed_gap,.25,580.0)
    var beam_tip: float = float(compound["stems"]["c"]["tip_y"])
    var lower_bound: float = renderer._event_y(
        all_chord_heads["notation_events"][3],beamed_gap) - beamed_gap*3.25
    check(beam_tip <= lower_bound + .01,
        "Beam stems clear highest member of a chord, not only its leader")
    check(renderer.load_score(score),"Restore baseline beam notation")
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
    # Engraving regression: non-flat melodic contours need sloped native
    # beams, with secondary layers and every stem attached to the beam.
    # This changes only Y geometry, never the musical X coordinate.
    var contour: Dictionary = score.duplicate(true)
    for event in contour["notation_events"]:
        match str(event.get("id", "")):
            "a":
                event["spelling"] = {"step":"E","octave":4}
            "b":
                event["spelling"] = {"step":"G","octave":4}
            "c":
                event["spelling"] = {"step":"B","octave":4}
    check(renderer.load_score(contour), "Native loads melodic beam contours")
    var gap: float = renderer._gap()
    var tilted: Dictionary = renderer._beam_layout(gap, .25, 580.0)
    var first_beam: Dictionary = tilted["groups"][0]
    var members: Array = first_beam["members"]
    check(members.size() == 3, "Three noteheads share a contoured beam")
    check(float(members[0]["tip_y"]) > float(members[-1]["tip_y"]),
        "Ascending melody raises native beam towards the last note")
    check(absf(float(members[0]["tip_y"])-float(members[-1]["tip_y"])) <=
        gap*.75+.001, "Beam angle is capped to three-quarter staff space")
    for event in renderer.beam_groups[0]:
        var stem: Dictionary = tilted["stems"][str(event["id"])]
        var extent: float = absf(renderer._event_y(event,gap)-float(stem["tip_y"]))
        check(extent >= gap*3.25-.01,
            "Every tilted stem retains the minimum clearance")
    var moved: Dictionary = renderer._beam_layout(gap, .75, 580.0)
    var shifted: Array = moved["groups"][0]["members"]
    for i in range(members.size()):
        check(absf(float(shifted[i]["tip_y"])-float(members[i]["tip_y"])) < .001,
            "Scrolling moves beams horizontally without vertical wobble")
        check(absf(float(shifted[i]["x"])-float(members[i]["x"]) +
            .5*renderer.timeline.pixels_per_beat) < .001,
            "Stem anchors track the original beat at constant speed")
    for event in contour["notation_events"]:
        match str(event.get("id", "")):
            "a":
                event["spelling"] = {"step":"B","octave":4}
            "c":
                event["spelling"] = {"step":"E","octave":4}
    check(renderer.load_score(contour), "Reversed contour remains supported")
    var descending: Dictionary = renderer._beam_layout(renderer._gap(),.25,580.0)
    check(float(descending["groups"][0]["members"][0]["tip_y"]) <
        float(descending["groups"][0]["members"][-1]["tip_y"]),
        "Descending melody lowers the native beam")

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
    # Regression: 32nd/64th events must remain native and use 3/4 beams.
    var tiny: Dictionary = score.duplicate(true)
    tiny["notation_events"] = [
        note("s0",0.0,.125,"right","1",1,"32nd"),
        note("s1",.125,.125,"right","1",1,"32nd"),
        note("s2",.25,.25,"right","1",1,"16th"),
        note("s3",.5,.5,"right","1",1,"eighth"),
        note("t0",1.0,.0625,"right","1",1,"64th"),
        note("t1",1.0625,.0625,"right","1",1,"64th"),
        note("t2",1.125,.125,"right","1",1,"32nd"),
        note("t3",1.25,.25,"right","1",1,"16th"),
        note("t4",1.5,.5,"right","1",1,"eighth")]
    tiny["notes"] = []
    for event in tiny["notation_events"]:
        tiny["notes"].append({"id":event["id"],"onset_beats":event["beat"],
            "duration_beats":event["duration_beats"],
            "midi_pitch":67,"hand":"right"})
    check(Geometry.beam_level("32nd") == 3 and Geometry.beam_level("64th") == 4,
        "Three-level 32nd and four-level 64th notation values")
    check(Geometry.supported(tiny).is_empty(),
        "Ordinary 32nd/64th notes no longer trigger native fallback")
    var tiny_groups: Array = Geometry.beam_groups(tiny)
    check(tiny_groups.size() == 2 and tiny_groups[0].size() == 4
        and tiny_groups[1].size() == 5,
        "Short note groups retain exact quarter-beat boundaries")
    check(renderer.load_score(tiny), "Load 32nd and 64th lesson natively")
    check(absf(renderer.timeline.pixels_per_beat-400.0) < .01,
        "Dense sixteenth-of-a-beat onsets select one scale before playback")
    var fixed: float = renderer.timeline.pixels_per_beat
    for tempo in [40.0, 80.0, 120.0]:
        renderer.present({"bpm":tempo,"running":true,"paused":false,
            "count_in_beats":4.0,"play_from_beat":0.0,
            "transport_id":9,"hand":"right"},-.25)
        check(absf(renderer.timeline.screen_x(.0625,-.25,580.0,0.0)
            -renderer.timeline.screen_x(0.0,-.25,580.0,0.0)
            -.0625*fixed) < .001,
            "32nd/64th timing remains fixed at %.0f BPM" % tempo)
    var still_unsupported: Dictionary = tiny.duplicate(true)
    still_unsupported["notation_events"][0]["note_type"] = "128th"
    check(not renderer.load_score(still_unsupported),
        "Truly unsupported rhythmic values still trigger fallback")
    renderer.clear_score()
    check(renderer.beam_groups.is_empty() and renderer.beamed_note_ids.is_empty(),
        "Changing lessons discards previously cached beams")
    print("PHASE_C2_BEAM_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
