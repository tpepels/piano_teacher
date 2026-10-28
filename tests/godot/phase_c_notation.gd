extends SceneTree

var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        print("PHASE_C_FAIL: ", message)

func approx(a: float, b: float, tolerance: float = .0001) -> bool:
    return absf(a - b) <= tolerance

func _initialize() -> void:
    call_deferred("run")

func _score() -> Dictionary:
    var right_clef := {"sign":"G", "line":2, "octave_change":0}
    var left_clef := {"sign":"F", "line":4, "octave_change":0}
    var measures := [
        {"number":1, "start_beat":0.0, "end_beat":3.0,
            "meter":[3,4], "keys":{"right":0,"left":-1},
            "clefs":{"right":right_clef,"left":left_clef}},
        {"number":2, "start_beat":3.0, "end_beat":7.0,
            "meter":[4,4], "keys":{"right":0,"left":-1},
            "clefs":{"right":right_clef,"left":left_clef}}]
    var symbols: Array = []
    var attack_specs := [
        ["n1", 0.0, 1.0, "right", "E", 4, "quarter", false, false, false, ""],
        ["n2", .25, .25, "right", "G", 5, "16th", false, false, false, "sharp"],
        ["n3", 1.0, .5, "right", "C", 6, "eighth", false, false, false, ""],
        ["n4", 2.5, .5, "left", "G", 2, "eighth", true, false, false, ""],
        ["n5", 3.0, 1.0, "left", "G", 2, "quarter", false, true, false, ""],
        ["n6", 4.0, 1.0, "right", "C", 4, "quarter", false, false, false, ""],
        ["n7", 4.0, 1.0, "right", "E", 4, "quarter", false, false, true, ""],
        ["n8", 5.0, 2.0, "left", "C", 3, "half", false, false, false, ""]]
    for row in attack_specs:
        var source: String = str(row[0])
        if source == "n5":
            source = "n4"
        symbols.append({"id":str(row[0]), "source_id":source,
            "kind":"note","staff":str(row[3]),"voice":"1",
            "measure":1 if float(row[1]) < 3.0 else 2,
            "beat":float(row[1]),"duration_beats":float(row[2]),
            "note_type":str(row[6]),"dots":0, "chord":bool(row[9]),
            "tie_start":bool(row[7]),"tie_stop":bool(row[8]),
            "is_attack":source==str(row[0]),
            "accidental":str(row[10]),
            "time_modification":null,
            "spelling":{"step":str(row[4]),"octave":int(row[5]),"alter":0}})
    symbols.append({"id":"rest:RH:1","source_id":null,
        "kind":"rest","staff":"right","voice":"2","measure":1,
        "beat":1.5,"duration_beats":.5, "note_type":"eighth",
        "dots":0,"chord":false,"tie_start":false,"tie_stop":false,
        "is_attack":false,"accidental":null,"time_modification":null,
        "spelling":null})
    var notes: Array = []
    for symbol in symbols:
        if symbol.kind == "note" and bool(symbol.is_attack):
            notes.append({"id":symbol.source_id,
                "onset_beats":symbol.beat,
                "duration_beats":symbol.duration_beats,
                "hand":symbol.staff,
                "midi_pitch":64})
    return {"schema":"piano-teacher-score-model-v1",
        "revision":17,"beat_unit":"quarter","duration_beats":7.0,
        "measures":measures,"notes":notes,
        "notation_events":symbols, "active_hand":"both",
        "active_note_ids":notes.map(func(n):return n.id)}

func run() -> void:
    var Geometry = load("res://notation/native/geometry.gd")
    var Renderer = load("res://notation/native/view.gd")
    var Timeline = load("res://notation/shared/timeline.gd")
    check(Geometry != null and Renderer != null and Timeline != null,
        "All Phase C scripts parse")
    if Geometry == null or Renderer == null or Timeline == null:
        quit(1)
        return
    check_barline_source_clock()
    var model: Dictionary = _score()
    check(Geometry.supported(model).is_empty(),
        "Ordinary notes, chords, stems, ties and eighth rests are supported")
    check(Geometry.staff_step({"step":"E","octave":4},{"sign":"G","line":2}) == 0,
        "Treble E4 is bottom line")
    check(Geometry.staff_step({"step":"G","octave":4},{"sign":"G","line":2}) == 2,
        "Treble G4 is second line")
    check(Geometry.staff_step({"step":"G","octave":2},{"sign":"F","line":4}) == 0,
        "Bass G2 is bottom line")
    check(Geometry.staff_step({"step":"C","octave":4},{"sign":"C","line":3}) == 4,
        "Alto clef C4 is third line")
    check(approx(Geometry.note_y(0,160.0,12.0),160.0),
        "Correct bottom-line note height")
    var spacing_eighth := [
        {"kind":"note","staff":"right","voice":"1","beat":0.0},
        {"kind":"note","staff":"right","voice":"1","beat":.5},
        {"kind":"note","staff":"right","voice":"1","beat":1.0}]
    check(Geometry.required_density(spacing_eighth,96.0) >= 155.0,
        "Readability: consecutive eighth-note attacks get at least 78 px")
    var spacing_16th := [
        {"kind":"note","staff":"right","voice":"1","beat":0.0},
        {"kind":"note","staff":"right","voice":"1","beat":.25}]
    check(Geometry.required_density(spacing_16th,96.0) >= 215.0,
        "Readability: sixteenths widen through one global density")
    var spacing_64th := [
        {"kind":"note","staff":"right","voice":"1","beat":0.0},
        {"kind":"note","staff":"right","voice":"1","beat":.0625}]
    check(approx(Geometry.required_density(spacing_64th,96.0),400.0),
        "Fast 64th-note grouping preserves its previous fixed 400 px/beat")
    check(approx(Geometry.required_density(spacing_eighth,96.0)*.5,
        Geometry.required_density(spacing_eighth,96.0)*1.0/2.0),
        "A larger density never introduces beat-dependent non-linear X")

    var renderer = Renderer.new()
    get_root().add_child(renderer)
    renderer.size = Vector2(1150,440)
    check(not renderer.load_score(model),
        "Native notes never render without an authenticated Verovio glyph atlas")
    # Synthetic 2x2 SVG paths below are a UNIT-TEST DOUBLE for placement and
    # transport math; real MIDI desktop tests require actual installed
    # Verovio glyphs from Python's notation.assets.glyphs.native_glyphs().
    var atlas_script = load("res://notation/native/glyphs.gd")
    var sample_glyphs: Dictionary = {}
    for name in atlas_script.REQUIRED:
        sample_glyphs[name] = {
            "source": "verovio", "font": "TestOnly", "units_per_space": 250,
            "bounds": [0.0,0.0,2.0,2.0],
            "svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2" width="2" height="2"><path d="M0 0L2 0L2 2L0 2Z" fill="white"/></svg>'
        }
    check(renderer.set_verovio_glyphs(sample_glyphs,
        load("res://tests/native_glyph_fixture.gd").note_catalogue(),
        load("res://tests/native_glyph_fixture.gd").tie_catalogue(),
        load("res://tests/native_glyph_fixture.gd").chord_catalogue(),
        {},{},load("res://tests/native_glyph_fixture.gd").slur_catalogue()),
        "Load SVG glyphs into cached Godot ImageTextures")
    check(renderer.glyphs.ready(), "Native glyph assets are resident")
    check(renderer.set_density(96.0), "User density accepted")
    check(renderer.load_score(model), "Native renderer accepts complete symbolic model")
    check(renderer.native_ready, "No raster or SVG is necessary")
    check(renderer.layout.slur_pairs.size()==1 and
        renderer.glyphs.slur_note_ids("n1|n3")==["n1","n3"],
        "An original Verovio slur binds to its two music-source note IDs")
    # Actual piano barlines span both staves and clear the following notehead.
    # The first visible source measure must never produce a fake barline.
    var staff_gap: float = renderer.staff_gap()
    check(renderer.layout.barline_geometry(model["measures"][0], 0.0, 480.0,
        staff_gap).is_empty(), "Opening clef/meter has no invented barline")
    var joined: Dictionary = renderer.layout.barline_geometry(
        model["measures"][1], 0.0, 480.0, staff_gap)
    check(not joined.is_empty(), "Later measure has a barline")
    if not joined.is_empty():
        check(approx(float(joined["top"]),renderer.layout.staff_center("right")-
            2.0*staff_gap) and
            approx(float(joined["bottom"]),renderer.layout.staff_center("left")+
            2.0*staff_gap), "Barline connects all ten piano staff rules")
        check(approx(float(joined["x"]),
            480.0+3.0*renderer.timeline.pixels_per_beat-staff_gap*1.35), "Barline clears first note without moving onset")
    # Terminal and incoming boundaries share one constant engraving lead.
    var ending: Dictionary = renderer.layout.terminal_barline_geometry(0.0,480.0,
        staff_gap)
    check(not ending.is_empty() and ending["style"] == "regular" and
        approx(float(ending["x"]),
            480.0+7.0*renderer.timeline.pixels_per_beat-staff_gap*1.35),
        "Terminal barline exists at exercise end without changing timing")
    check(renderer.layout.barline_strokes("regular",staff_gap).size()==1,
        "Single measure barline is one continuous thin stroke")
    var double_bar: Array = renderer.layout.barline_strokes("light-light",staff_gap)
    check(double_bar.size()==2 and
        approx(float(double_bar[0]["width"]),float(double_bar[1]["width"])),
        "Double measure barline has two thin equal-weight strokes")
    var final_bar: Array = renderer.layout.barline_strokes("light-heavy",staff_gap)
    check(final_bar.size()==2 and
        float(final_bar[1]["width"])>float(final_bar[0]["width"])*2.0,
        "Final measure barline has thick right stroke")
    var forward: Array = renderer.layout.barline_strokes("heavy-light",staff_gap)
    check(forward.size()==2 and
        float(forward[0]["width"])>float(forward[1]["width"]),
        "Forward repeat uses thick left stroke")
    check(renderer.glyphs.textures.has("repeat_dot"),
        "Repeat colon is genuine source Verovio repeat-dot music glyph")
    var clef_g: Dictionary = {"sign":"G","line":2,"octave_change":0}
    var new_clef: Dictionary = {"sign":"G","line":1,"octave_change":1}
    check(Geometry.key_cancellation_steps(clef_g, 3, 0).size() == 3,
        "Changing from three sharps to C major engraves three naturals")
    check(Geometry.key_cancellation_steps(clef_g, -4, -2).size() == 2,
        "Shrinking a flat signature cancels the two discarded flats")
    check(Geometry.key_cancellation_steps(clef_g, -2, 2).size() == 2,
        "Switching flats to sharps cancels the former key")
    check(Geometry.key_cancellation_steps(clef_g, 2, 3).is_empty(),
        "Increasing the same key signature adds sharps, not naturals")
    check(Geometry.staff_step({"step":"G","octave":4},new_clef) !=
        Geometry.staff_step({"step":"G","octave":4},clef_g),
        "Declared reference line and octave indication affect pitch placement")
    check(renderer.glyphs.textures.has("clef_g_8va") and
        renderer.glyphs.textures.has("clef_f_8vb") and
        renderer.glyphs.textures.has("clef_c_8vb"),
        "Original Verovio clef octave variants and numerals are cached")
    var styled: Dictionary = model.duplicate(true)
    styled["measures"][0]["right_barline"] = {
        "style":"light-heavy","repeat":"backward"}
    styled["measures"][1]["left_barline"] = {
        "style":"heavy-light","repeat":"forward"}
    styled["measures"][1]["right_barline"] = {
        "style":"light-light","repeat":""}
    check(renderer.load_score(styled),"Explicit double-repeat bars remain native")
    var shared: Dictionary = renderer.layout.barline_geometry(
        styled["measures"][1],0.0,480.0,staff_gap)
    check(shared["style"]=="heavy-heavy" and shared["repeat"]=="both",
        "Back-to-back backward/forward repeats share one correctly composed boundary")
    check(renderer.layout.terminal_barline_geometry(0.0,480.0,
        staff_gap)["style"] == "light-light",
        "Explicit right-hand ending style remains a double terminal bar")
    var contradiction: Dictionary = styled.duplicate(true)
    contradiction["measures"][1]["left_barline"] = {
        "style":"light-light","repeat":""}
    check(Geometry.supported(contradiction).contains("Conflicting"),
        "Incompatible barline styles on the same boundary trigger fallback")
    check(renderer.load_score(model),
        "Restore source model after barline style tests")
    check(renderer.layout.chord_members.has("n6") and
        renderer.layout.chord_members["n6"].size() == 2,
        "Two simultaneous right-hand notes use one MusicXML chord leader")
    var chord: Dictionary = renderer.layout.chord_extents(
        model["notation_events"][5],staff_gap)
    check(float(chord["top_y"]) < float(chord["bottom_y"]) and
        bool(chord["up"]), "Chord stem covers top and bottom real glyph heads")
    check(renderer.layout.chord_template_key(model["notation_events"][5]) ==
        "quarter|up|0,2", "Exact chord interval/clef signature matches backend")
    check(renderer.glyphs.has_chord("quarter|up|0,2"),
        "Completed original Verovio chord ink is resident and can be reused")
    check(renderer.glyphs.note_ready() and \
        renderer.glyphs.note_stem_textures.size() == 14,
        "Native beam stems are original Verovio sprites, never Godot lines")
    check(renderer.glyphs.chord_heads("quarter|up|0,2").size() == 2,
        "Each head keeps its exact original relative Verovio anchor")
    var unordered: Dictionary = model.duplicate(true)
    unordered["notation_events"].reverse()
    check(renderer.load_score(unordered),
        "Reversed equal-time MusicXML events can still be painted")
    var leader_pos := -1
    var follower_pos := -1
    for i in range(renderer.layout.ordered_events.size()):
        var identifier: String = str(renderer.layout.ordered_events[i].get("id",""))
        if identifier == "n6":
            leader_pos = i
        if identifier == "n7":
            follower_pos = i
    check(leader_pos >= 0 and follower_pos > leader_pos,
        "Verovio chord leader always precedes displaced child notes")
    check(renderer.load_score(model),
        "Restore notation after unstable chord ordering regression")
    var tie: Dictionary = renderer.connector_geometry.tie_placement(
        model["notation_events"][3],model["notation_events"][4],
        160.0,330.0,staff_gap)
    check(not tie.is_empty() and renderer.glyphs.ties_ready(),
        "Native ties require actual cached Verovio contour textures")
    if not tie.is_empty():
        check(approx(float(tie["x0"]),160.0) and
            approx(float(tie["x1"]),330.0),
            "Verovio contour anchors follow both original note onsets")
        check(bool(tie["down"]) and approx(float(tie["y"]),
            renderer.layout.event_y(model["notation_events"][3],staff_gap)),
            "Tie direction and staff height are semantically derived")
    # Chopin fixture has a very short 1/8 pickup directly before 12/8.
    # Both time signatures must remain legible without moving any note X.
    var pickup: Dictionary = model.duplicate(true)
    pickup["measures"][0]["end_beat"] = .5
    pickup["measures"][0]["meter"] = [1,8]
    pickup["measures"][1]["start_beat"] = .5
    pickup["measures"][1]["meter"] = [12,8]
    for event in pickup["notation_events"]:
        event["measure"] = 1 if float(event["beat"]) < .5 else 2
    check(renderer.load_score(pickup),
        "Native renderer accepts 1/8 pickup followed by 12/8")
    var pickup_gap: float = renderer.staff_gap()
    check(renderer.context_painter.meter_is_crowded(pickup["measures"][1],
        pickup["measures"][0],pickup_gap),
        "Close meter change uses a dedicated upper-staff annotation lane")
    check(not renderer.context_painter.meter_is_crowded(pickup["measures"][0],
        {},pickup_gap), "Opening meter stays in conventional staff position")
    check(approx(renderer.timeline.screen_x(.5,0.0,480.0,0.0)-
        renderer.timeline.screen_x(0.0,0.0,480.0,0.0),
        renderer.timeline.pixels_per_beat*.5),
        "Floating time signature never changes note position or speed")
    check(renderer.load_score(model),"Restore baseline notation after meter test")
    check(renderer.timeline.pixels_per_beat >= 96.0
        and renderer.timeline.pixels_per_beat <=
            Geometry.required_density(model["notation_events"],96.0),
        "Native whole-piece density follows actual glyph overlap, not duration alone")
    var density: float = renderer.timeline.pixels_per_beat
    check(approx(renderer.timeline.x_at_beat(.25),density*.25),
        "Source attacks retain quarter-beat geometry")
    check(approx(renderer.timeline.x_at_beat(7.0),density*7.0),
        "Measure lengths retain exact quarter units")
    # Phase 1 performance: one viewport scans only nearby onsets, and
    # immutable measure lookups and staff fitting survive unchanged frames.
    check(renderer.layout.measure_by_number.size() == model["measures"].size(),
        "Native measure geometry indexed once at lesson load")
    var first_gap: float = renderer.staff_gap()
    check(approx(renderer.staff_gap(),first_gap) and
        approx(renderer.layout.cached_staff_gap,first_gap),
        "Native grand-staff vertical fitting reused across frames")
    var nearby: Array = renderer._visible_events(0.0, 1.0)
    check(not nearby.is_empty() and nearby.size() < renderer.layout.ordered_events.size(),
        "Viewport culls off-screen native noteheads")
    check(renderer.frame_scanned_events == nearby.size(),
        "Viewport budget counts only notation actually scanned")
    var empty_view: Array = renderer._visible_events(100.0,101.0)
    check(empty_view.is_empty() and renderer.frame_scanned_events == 0,
        "Off-screen native passage performs no note rendering work")
    check(renderer.layout.measure_for(model["notation_events"][0]).get("number",0) == 1,
        "Source note measure lookup remains stable with cached dictionary")
    renderer.present({"bpm":40, "running":true,"paused":false,
        "count_in_beats":3.0,"play_from_beat":0.0,"hand":"both",
        "transport_id":4},-3.0)
    var anchor_x: float = renderer.timeline.screen_x(0.0,
        renderer.clock_beat,1150.0*.42,0.0)
    check(approx(anchor_x,1150.0*.42+3.0*density),
        "Count-in uses the same score camera as the first note")
    for tempo in [40.0,80.0,120.0]:
        renderer.present({"bpm":tempo,"running":true,"paused":false,
            "count_in_beats":3.0,"play_from_beat":0.0,
            "hand":"right","transport_id":5},-.15)
        var before: float = renderer.timeline.screen_x(1.0,
            renderer.clock_beat,1150.0*.42,0.0)
        renderer.present({"bpm":tempo,"running":true,"paused":false,
            "count_in_beats":3.0,"play_from_beat":0.0,
            "hand":"right","transport_id":5},.25)
        var after: float = renderer.timeline.screen_x(1.0,
            renderer.clock_beat,1150.0*.42,0.0)
        check(approx(before-after,.4*density),
            "No tempo change at first note, %.0f BPM" % tempo)
        check(approx(renderer.timeline.pixels_per_beat,density),
            "BPM never changes selected glyph spacing")
    # Very high and low notes must fit in the ACTUAL native canvas.
    # Scaling changes only vertical glyph spacing, never the time axis.
    var extremes: Dictionary = model.duplicate(true)
    for symbol in extremes["notation_events"]:
        if str(symbol.get("id", "")) == "n3":
            symbol["spelling"] = {"step":"C","octave":8,"alter":0}
        if str(symbol.get("id", "")) == "n8":
            symbol["spelling"] = {"step":"C","octave":1,"alter":0}
    check(renderer.load_score(extremes),"Extreme ledger notes remain supported")
    var fitted_gap: float = renderer.staff_gap()
    var highest: float = INF
    var lowest: float = -INF
    for symbol in extremes["notation_events"]:
        if str(symbol.get("kind","")) == "note":
            var y: float = renderer.layout.event_y(symbol,fitted_gap)
            highest = minf(highest,y)
            lowest = maxf(lowest,y)
    check(highest >= 31.0 and lowest <= renderer.size.y-31.0,
        "Native resize keeps both very high and low ledger notes in view")
    check(approx(renderer.timeline.pixels_per_beat,density),
        "Vertical resizing cannot affect horizontal musical time")
    check(renderer.load_score(model),"Restore ordinary notation for fallback test")
    var missing_tuplet: Dictionary = {
        "events":[model["notation_events"][0],model["notation_events"][2]],
        "staff":"right"}
    renderer.layout.notation_tuplets = [missing_tuplet]
    check(renderer._missing_source_engraving().contains("tuplet"),
        "Unmatched source triplet must use original Verovio raster fallback")
    renderer.layout.notation_tuplets.clear()
    renderer.expected_slur_pairs = [["n1","n6"]]
    check(renderer._missing_source_engraving().contains("slur"),
        "Missing original MusicXML slur cannot silently vanish")
    renderer.expected_slur_pairs.clear()
    var old: Dictionary = model.duplicate(true)
    old["notation_events"][0]["time_modification"] = {"actual":3,"normal":2}
    check(not renderer.load_score(old),"Unimplemented tuplet rejects native renderer")
    check(not renderer.native_ready,
        "Rejecting a score cannot leave stale native noteheads")
    check(not renderer.failure_reason.is_empty(),
        "Fallback provides a concrete reason")
    var dense: Dictionary = model.duplicate(true)
    dense["notation_events"][1]["beat"] = .001
    check(not renderer.load_score(dense),
        "Impossible collision must request Verovio fallback, not per-note speedups")
    check(renderer.load_score(model), "Recovery after fallback is supported")
    renderer.clear_score()
    check(not renderer.native_ready and not renderer.timeline.has_score(),
        "New lesson clears the old native scene")
    print("PHASE_C_NOTATION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)


func check_barline_source_clock() -> void:
    var Timeline = load("res://notation/shared/timeline.gd")
    var Barline = load("res://notation/native/barline_layout.gd")
    var axis: RefCounted = Timeline.new()
    axis.pixels_per_beat = 100.0
    axis.duration_beats = 7.0
    var measures: Array = [{"start_beat":0.0,"end_beat":3.0},
        {"start_beat":3.0,"end_beat":7.0}]
    # Independently calculated pixels: 480+(beat-clock-play_from)*100-1.35*gap.
    # Literal expectations catch ignored/doubled clock or play-from values and
    # an end-only engraving lead without comparing geometry to its own helper.
    var incoming: Dictionary = Barline.boundary(measures,measures[1],axis,
        .75,480.0,1.5,20.0,100.0,300.0)
    check(approx(float(incoming["x"]),528.0),
        "Incoming barline uses explicit source beat, clock and play-from once")
    for sample in [[.75,1.5,20.0,928.0],[1.25,1.5,20.0,878.0],
            [.75,2.5,20.0,828.0],[.75,1.5,40.0,901.0]]:
        var terminal: Dictionary = Barline.terminal(measures,axis,
            float(sample[0]),480.0,float(sample[1]),float(sample[2]),100.0,300.0)
        check(not terminal.is_empty() and terminal["style"] == "regular" and
            approx(float(terminal["x"]),float(sample[3])),
            "Terminal barline preserves source clock and common engraving lead: "+str(sample))
