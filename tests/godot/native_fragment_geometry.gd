extends SceneTree

var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("NATIVE_FRAGMENT_FAIL: ", label)

func _initialize() -> void:
    call_deferred("run")

func note(id: String, beat: float, step: String, chord: bool = false) -> Dictionary:
    return {"id":id,"source_id":id,"kind":"note","staff":"right",
        "voice":"1","measure":9,"beat":beat,"duration_beats":.5,
        "note_type":"eighth","dots":0,"chord":chord,
        "spelling":{"step":step,"octave":4,"alter":0}}

func run() -> void:
    check(OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1",
        "Regression must explicitly select the native notation engine")
    var Fixture = load("res://tests/native_glyph_fixture.gd")
    var renderer = load("res://notation/native/view.gd").new()
    get_root().add_child(renderer)
    renderer.size = Vector2(1200,440)
    var chord_atlas: Dictionary = Fixture.chord_catalogue()
    # The first attack's MusicXML leader is the HIGHER pitch. Beam bounds
    # remain relative to that leader, while stem tips use the outer pitch.
    chord_atlas["eighth|up|-2,0"] = chord_atlas["eighth|up|0,2"].duplicate(true)
    chord_atlas["eighth|up|-2,0"]["head_positions"] = [[0.0,250.0],[0.0,0.0]]
    var beam_atlas: Dictionary = Fixture.beam_catalogue()
    beam_atlas = {"a|b|c":beam_atlas["a|b|c"]}
    var events: Array = [note("a",0.0,"E"),note("low",0.0,"C",true),
        note("b",.5,"G"),note("c",1.0,"A")]
    var model := {"schema":"piano-teacher-score-model-v1","revision":9,
        "beat_unit":"quarter","duration_beats":4.0,"notes":[],
        "measures":[{"number":9,"start_beat":0.0,"end_beat":4.0,
            "meter":[4,4],"keys":{"right":0,"left":0},
            "clefs":{"right":{"sign":"G","line":2},
                     "left":{"sign":"F","line":4}}}],
        "notation_events":events}
    var symbols: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_SYMBOL_FIXTURE")))
    check(renderer.set_verovio_glyphs(symbols,
        Fixture.note_catalogue(),Fixture.tie_catalogue(),chord_atlas,beam_atlas),
        "Fixture pipeline loads the native fragment catalogues")
    check(renderer.load_score(model) and renderer.native_ready,
        "Source-matched fragment lesson is native with no fallback")
    var gap: float = renderer._gap()
    var beam: Dictionary = renderer._beam_layout(gap,0.0,500.0)
    check(beam["groups"].size() == 1,"Original beam keeps every attack")
    if not beam["groups"].is_empty():
        var group: Dictionary = beam["groups"][0]
        var anchor_y: float = float(group.get("anchor_y",group["members"][0]["head_y"]))
        check(absf(anchor_y-renderer._event_y(events[0],gap)) < .001,
            "Beam texture origin uses source leader, not outer chord tone")
    # A second has asymmetric original Verovio head displacement. Estimated
    # +/- .75-space placement cannot be reused for ties, slurs or beams.
    var seconds: Dictionary = model.duplicate(true)
    seconds["notation_events"] = [note("lead",0.0,"C"),note("second",0.0,"D",true)]
    renderer.glyphs.chord_textures["eighth|up|0,1"] = renderer.glyphs.chord_textures["eighth|up|0,2"]
    renderer.glyphs.chord_metadata["eighth|up|0,1"] = {
        "bounds":[-20.0,-200.0,400.0,300.0],
        "head_positions":[[0.0,0.0],[300.0,-125.0]]}
    check(renderer.load_score(seconds) and renderer.native_ready,
        "Displaced second stays native")
    # Force the normal draw path, including its cached head offsets.
    renderer.queue_redraw()
    await process_frame
    await process_frame
    check(absf(float(renderer.cached_head_offsets.get("lead",0.0))) < .001 and
        absf(float(renderer.cached_head_offsets.get("second",0.0))-gap*1.2) < .001,
        "Cached attachment anchors match engraved heads exactly")
    var tied: Dictionary = renderer._tie_placement(
        seconds["notation_events"][1],seconds["notation_events"][1],100.0,250.0,gap)
    check(not tied.is_empty() and absf(float(tied["x0"])-(100.0+gap*1.2)) < .001,
        "Tie attaches to displaced source head without changing beat spacing")
    var accidentals: Dictionary = seconds.duplicate(true)
    accidentals["notation_events"] = [note("sharp_c",0.0,"C"),
        note("sharp_e",0.0,"E",true)]
    for event in accidentals["notation_events"]:
        event["accidental"] = "sharp"
    check(renderer.load_score(accidentals) and renderer.native_ready,
        "Closely spaced chord accidentals remain native")
    await process_frame
    await process_frame
    var accidental_offsets: Variant = renderer.get("cached_accidental_offsets")
    var boxes: Array[Rect2] = []
    var sharp_box: Array = renderer.glyphs.bounds["acc_sharp"]
    for event in accidentals["notation_events"]:
        var id: String = str(event["id"])
        var x: float = float(renderer.cached_head_offsets.get(id,0.0))-gap*1.15
        if accidental_offsets is Dictionary:
            x = float(renderer.cached_head_offsets.get(id,0.0))+float(
                accidental_offsets.get(id,-gap*1.15))
        var y: float = renderer._event_y(event,gap)
        boxes.append(Rect2(x-float(sharp_box[2])*gap/500.0,
            y+float(sharp_box[1])*gap/250.0,
            float(sharp_box[2])*gap/250.0,float(sharp_box[3])*gap/250.0))
    check(not boxes[0].intersects(boxes[1]),
        "Original Verovio accidentals on a close chord occupy separate clear columns")
    for style in ["tick","short"]:
        var partial: Dictionary = model.duplicate(true)
        partial["measures"][0]["right_barline"] = {"style":style,"repeat":""}
        check(renderer.load_score(partial) and renderer.native_ready,
            "Legal %s barline must remain native without fallback" % style)
        var info: Dictionary = renderer._terminal_barline_geometry(0.0,500.0,gap)
        var segments: Array = info.get("segments",[])
        check(segments.size() == 2,
            "%s barline has one partial rule on each piano staff" % style)
        if segments.size() == 2:
            for i in range(2):
                var center: float = renderer._staff_center("right" if i == 0 else "left")
                var expected_top: float = center-gap*(2.5 if style == "tick" else 1.0)
                var expected_bottom: float = center-gap*1.5 if style == "tick" else center+gap
                check(absf(float(segments[i]["top"])-expected_top) < .001 and
                    absf(float(segments[i]["bottom"])-expected_bottom) < .001,
                    "%s keeps its source staff extent and leaves the interstaff gap clear" % style)
        check(renderer._barline_strokes(style,gap).size() == 1,
            "%s uses a single authentic structural barline stroke" % style)
    # Peace Piece measures 57/58: a real ten-to-one 64th starts just
    # .00625 quarter beats before its tied continuation. Preserve both
    # original onsets, even though one fixed scale must exceed 480 px/beat.
    var tiny: Dictionary = model.duplicate(true)
    tiny["duration_beats"] = 8.0
    tiny["measures"][0]["number"] = 57
    tiny["measures"][0]["end_beat"] = 4.0
    tiny["measures"].append(tiny["measures"][0].duplicate(true))
    tiny["measures"][1]["number"] = 58
    tiny["measures"][1]["start_beat"] = 4.0
    tiny["measures"][1]["end_beat"] = 8.0
    var attack: Dictionary = note("midi-t0-e2015s0",3.99375,"B")
    attack.merge({"source_id":"midi-t0-e2015","note_type":"64th",
        "duration_beats":.00625,"measure":57,"tie_start":true,
        "time_modification":{"actual":10,"normal":1}},true)
    var continuation: Dictionary = note("midi-t0-e2015s1",4.0,"B")
    continuation.merge({"source_id":"midi-t0-e2015","note_type":"quarter",
        "duration_beats":1.0,"measure":58,"tie_stop":true},true)
    tiny["notation_events"] = [attack,continuation]
    tiny["notes"] = [{"id":"midi-t0-e2015","onset_beats":3.99375,
        "duration_beats":1.00625,"midi_pitch":59,"hand":"right"}]
    var Geometry = load("res://notation/native/geometry.gd")
    check(Geometry.required_density(tiny["notation_events"],96.0,480.0) < 0.0,
        "Caller-specified 480 density limit still rejects an over-dense source")
    check(renderer.load_score(tiny) and renderer.native_ready,
        "Actual Peace Piece ten-to-one 64th stays native at one larger global scale")
    if renderer.native_ready:
        var tiny_density: float = renderer.timeline.pixels_per_beat
        # The staff now scales down when 22px glyphs would show almost no
        # forward music. A fixed 25px gap was an artificial pixel policy;
        # the safety invariant is actual source-Verovio ink separation.
        check(tiny_density > 96.0 and tiny_density <= 8192.0,
            "Near-coincident source events require an explicit global scale")
        var tiny_gap: float = renderer._gap()
        var tiny_heads: Dictionary = renderer._engraved_head_offsets(tiny_gap)
        var tiny_accidentals: Dictionary = Geometry.accidental_offsets(
            renderer.ordered_events,tiny_gap,tiny_heads,
            renderer.glyphs.bounds)
        var left_ink: Rect2 = renderer._event_ink_rect(
            attack,tiny_gap,tiny_heads,tiny_accidentals)
        var right_ink: Rect2 = renderer._event_ink_rect(
            continuation,tiny_gap,tiny_heads,tiny_accidentals)
        left_ink.position.x += 3.99375*tiny_density
        right_ink.position.x += 4.0*tiny_density
        check(not left_ink.intersects(right_ink.grow(tiny_gap*.06)),
            "Two close tied source notes retain genuine visible ink clearance")
        check(renderer.tie_pairs.size() == 1 and renderer.ordered_events == [attack,continuation],
            "Tiny attack, original source identity and tied continuation all survive")
        var x0: float = renderer.timeline.screen_x(3.99375,4.0,500.0)
        var x1: float = renderer.timeline.screen_x(4.0,4.0,500.0)
        check(absf(x1-x0-tiny_density*.00625) < .001,
            "Dense source intervals use the same exact linear timeline")
        for clock in [-3.0,0.0,3.99375,4.0]:
            var before: float = renderer.timeline.screen_x(4.0,float(clock),500.0)
            var after: float = renderer.timeline.screen_x(4.0,float(clock)+.001,500.0)
            check(absf(before-after-tiny_density*.001) < .001,
                "High-density count-in and tied continuation keep one fixed camera speed")
        check(renderer._visible_events(3.98,4.01).size() == 2,
            "High density still culls to the original visible source events")
    check(not renderer.set_density(800.0),
        "Automatic score scale does not expand the user configuration range")
    check(renderer.load_score(model) and renderer.timeline.pixels_per_beat < 480.0,
        "A new ordinary lesson restores the configured preference after automatic expansion")
    print("NATIVE_FRAGMENT_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
