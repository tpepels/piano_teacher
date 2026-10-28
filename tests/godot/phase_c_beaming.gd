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
    var Geometry = load("res://notation/native/geometry.gd")
    var Native = load("res://notation/native/view.gd")
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
    events[3]["spelling"] = {"step":"B","octave":4,"alter":0}
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
        load("res://tests/native_glyph_fixture.gd").catalogue(),
        load("res://tests/native_glyph_fixture.gd").note_catalogue(),
        load("res://tests/native_glyph_fixture.gd").tie_catalogue(),
        load("res://tests/native_glyph_fixture.gd").chord_catalogue(),
        load("res://tests/native_glyph_fixture.gd").beam_catalogue()),
        "Unit test has all source-matched Verovio beam textures")
    check(renderer.load_score(score), "Native loads grouped rhythms")
    var expected_groups: Dictionary = {
        "a":["a","b","c"], "d":["d","e"], "f":["f","g"],
        "i":["i","j","k"], "l":["l","m","n"]}
    var by_first: Dictionary = {}
    for group in renderer.layout.beam_groups:
        by_first[str(group[0]["id"])] = group.map(func(e):return e["id"])
    check(renderer.layout.beam_groups.size() == expected_groups.size()
        and by_first == expected_groups,
        "Native renderer retains every source beam identity and boundary")
    check(not renderer.layout.beamed_note_ids.has("other_voice"),
        "Single independent voice remains flagged, not accidentally beamed")
    check(renderer.layout.beamed_note_ids.has("a") and renderer.layout.beamed_note_ids.has("c")
        and not renderer.layout.beamed_note_ids.has("chord_c"),
        "Chord tone shares source leader's beam without a duplicate stem")
    check(renderer.glyphs.has_beam("d|e",true),
        "Two-note Verovio beam fragment is loaded by original note identities")
    var beam_ink: Dictionary = renderer.beam_plan(renderer.staff_gap(),0.0,580.0)
    var genuine: Dictionary = {}
    for compound_group in beam_ink["groups"]:
        if str(compound_group.get("art_key","")) == "d|e":
            genuine = compound_group
    check(not genuine.is_empty(),
        "Native engine prefers actual Verovio beam ink over hand-built beams")
    if not genuine.is_empty():
        var pair: Array = genuine["members"]
        var note_tip: float = float(pair[0]["head_y"])-860.0*renderer.staff_gap()/250.0
        check(absf(float(pair[0]["tip_y"])-note_tip) < .01,
            "Stem tip aligns to original Verovio beam contour measurement")
        check(absf(float(pair[1]["head_x"])-float(pair[0]["head_x"])-
            (float(pair[1]["x"])-float(pair[0]["x"]))) < .01,
            "Beam spacing tracks exact source beats, not Verovio page X")
    var all_chord_heads: Dictionary = score.duplicate(true)
    for item in all_chord_heads["notation_events"]:
        if str(item.get("id","")) == "chord_c":
            item["spelling"] = {"step":"C","octave":5}
    check(renderer.load_score(all_chord_heads),"Beamed chord notation is supported")
    var beamed_gap: float = renderer.staff_gap()
    var compound: Dictionary = renderer.beam_plan(beamed_gap,.25,580.0)
    var beam_tip: float = float(compound["stems"]["c"]["tip_y"])
    var lower_bound: float = renderer.layout.event_y(
        all_chord_heads["notation_events"][3],beamed_gap) - beamed_gap*3.25
    check(beam_tip <= lower_bound + .01,
        "Beam stems clear highest member of a chord, not only its leader")
    check(renderer.load_score(score),"Restore baseline beam notation")
    var source_chord: Dictionary = score.duplicate(true)
    for attack in source_chord["notation_events"]:
        if str(attack.get("id",""))=="chord_c":
            attack["spelling"]={"step":"B","octave":4}
    check(renderer.load_score(source_chord),
        "Native accepts a shared-beam Verovio chord interval signature")
    var original_key: String = renderer.layout.chord_template_key(
        source_chord["notation_events"][2])
    check(original_key=="eighth|up|0,2" and
        renderer.glyphs.has_chord_heads(original_key) and
        renderer.glyphs.has_chord_stem(original_key),
        "A beamed chord has separate authentic Verovio head and stem ink")
    check(renderer.beam_plan(renderer.staff_gap(),0.0,580.0)["stems"].has("c"),
        "Beamed Verovio chord keeps its single native musical attack")
    check(renderer.load_score(score),"Restore baseline after chord compound")
    check(renderer.set_density(112.0),"Density remains configurable")
    var clock := .75
    var offset := 0.0
    var beam_before: Dictionary = renderer.beam_plan(renderer.staff_gap(),clock,580.0)
    renderer.present({"bpm":40,"running":true,"paused":false,
        "count_in_beats":4,"play_from_beat":offset,
        "transport_id":7,"hand":"right"},clock)
    var beam_after: Dictionary = renderer.beam_plan(renderer.staff_gap(),clock,580.0)
    check(beam_before["stems"].size() == beam_after["stems"].size(),
        "All cached beam stems independent of BPM")
    for identifier in beam_before["stems"]:
        check(beam_before["stems"][identifier] == beam_after["stems"][identifier],
            "All grouped noteheads share exactly the same time axis")
    # Ink follows original Verovio offsets rather than fabricating a slope.
    # Altering the pitches may change the Y positions, but the extracted
    # tip offset at each attack remains exactly the one in the source atlas.
    var contour: Dictionary = score.duplicate(true)
    for event in contour["notation_events"]:
        if str(event.get("id","")) == "a":
            event["spelling"] = {"step":"E","octave":4}
    check(renderer.load_score(contour),"Native loads source-engraved beam contours")
    var gap: float = renderer.staff_gap()
    var tilted: Dictionary = renderer.beam_plan(gap,.25,580.0)
    var first_beam: Dictionary = tilted["groups"][0]
    var members: Array = first_beam["members"]
    check(members.size() == 3,"Every source group retains its three beats")
    var original_tips: Array = renderer.glyphs.beam_tips("a|b|c")
    for i in range(members.size()):
        var member: Dictionary = members[i]
        check(absf(float(member["tip_y"])-float(member["head_y"])-
            float(original_tips[i])*gap/250.0) < .01,
            "Source Verovio stem tip is preserved without custom beam slope")
    var moved: Dictionary = renderer.beam_plan(gap,.75,580.0)
    var shifted: Array = moved["groups"][0]["members"]
    for i in range(members.size()):
        check(absf(float(shifted[i]["tip_y"])-float(members[i]["tip_y"])) < .001,
            "Scrolling moves source beam horizontally without vertical wobble")
        check(absf(float(shifted[i]["x"])-float(members[i]["x"]) +
            .5*renderer.timeline.pixels_per_beat) < .001,
            "Stem anchors track the original beat at constant speed")
    var irregular: Dictionary = score.duplicate(true)
    irregular["measures"][1]["meter"] = [7,8]
    check(renderer.load_score(irregular), "Load source beams in irregular meter")
    var irregular_groups: Dictionary = {}
    for group in renderer.layout.beam_groups:
        irregular_groups[str(group[0]["id"])] = group.map(func(e):return e["id"])
    check(renderer.layout.beam_groups.size() == expected_groups.size()
        and irregular_groups == expected_groups,
        "Source beam boundaries survive meter changes without new inference")
    var metadata: Dictionary = renderer.glyphs.beam_metadata.duplicate(true)
    renderer.glyphs.beam_metadata.clear()
    check(renderer.load_score(score), "Source without beam metadata remains flagged")
    check(renderer.layout.beam_groups.is_empty() and renderer.layout.beamed_note_ids.is_empty(),
        "Adjacent short notes must not invent beams when source groups are absent")
    renderer.glyphs.beam_metadata = metadata
    # Regression: 32nd/64th events must remain native with their source beams.
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
    check(Geometry.supported(tiny).is_empty(),
        "Ordinary 32nd/64th notes no longer trigger native fallback")
    check(renderer.load_score(tiny), "Load 32nd and 64th lesson natively")
    var tiny_groups: Array = []
    for group in renderer.layout.beam_groups:
        tiny_groups.append(group.map(func(e):return e["id"]))
    check(tiny_groups == [["s0","s1","s2","s3"],
        ["t0","t1","t2","t3","t4"]],
        "Short notes retain every source beam identity and boundary")
    check(renderer.timeline.pixels_per_beat >= 112.0
        and renderer.timeline.pixels_per_beat <= 400.0,
        "Native score fits genuine glyph ink at one fixed scale, without duration-only inflation")
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
    still_unsupported["notation_events"][0]["note_type"] = "256th"
    check(not renderer.load_score(still_unsupported),
        "Truly unsupported rhythmic values still trigger fallback")
    renderer.clear_score()
    check(renderer.layout.beam_groups.is_empty() and renderer.layout.beamed_note_ids.is_empty(),
        "Changing lessons discards previously cached beams")
    print("PHASE_C2_BEAM_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
