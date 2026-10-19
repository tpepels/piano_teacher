extends SceneTree
# Phase C3: explicit MusicXML grouping, double dots and one shared time axis.
var failures: Array[String] = []

func check(ok: bool, reason: String) -> void:
    if not ok:
        failures.append(reason)
        print("PHASE_C3_FAIL: ", reason)

func n(id: String, onset: float, duration: float, named: String,
        modification: Variant = null, marks: Array = [], dots: int = 0,
        kind: String = "note") -> Dictionary:
    return {"id":id, "source_id":id if kind == "note" else null,
        "staff":"right", "voice":"1", "measure":1,
        "beat":onset, "duration_beats":duration,
        "kind":kind, "note_type":named, "dots":dots, "chord":false,
        "is_attack":kind == "note", "accidental":null,
        "tie_start":false,"tie_stop":false,
        "time_modification":modification, "tuplet_marks":marks,
        "spelling":{"step":"C","octave":5,"alter":0} if kind == "note" else null}

func mark(kind: String, number: String = "1") -> Dictionary:
    return {"type":kind,"number":number,"bracket":"yes",
        "show_number":"actual"}

func score() -> Dictionary:
    var events: Array = []
    # Five eighth notes in the time of four, crossing the quarter boundary.
    for i in range(5):
        var markers: Array = []
        if i == 0:
            markers.append(mark("start"))
        if i == 4:
            markers.append(mark("stop"))
        events.append(n("five"+str(i), i*.4, .4, "eighth",
            {"actual":5,"normal":4},markers))
    # Triplet eighths: exactly one quarter of total time.
    for i in range(3):
        var markers: Array = []
        if i == 0:
            markers.append(mark("start","2"))
        if i == 2:
            markers.append(mark("stop","2"))
        events.append(n("three"+str(i),2.0+i/3.0,1.0/3.0,
            "eighth",{"actual":3,"normal":2},markers))
    events.append(n("double_dotted",3.0,1.75,"quarter",null,[],2))
    events.append(n("double_rest",4.75,.875,"eighth",null,[],2,"rest"))
    var notes: Array = []
    for event in events:
        if event.kind == "note":
            notes.append({"id":event.id,"onset_beats":event.beat,
                "duration_beats":event.duration_beats,"midi_pitch":72,
                "hand":"right"})
    return {"schema":"piano-teacher-score-model-v1",
        "beat_unit":"quarter","revision":7,"duration_beats":6.0,
        "measures":[{"number":1,"start_beat":0.0,"end_beat":6.0,
            "meter":[6,4],"keys":{"right":0,"left":0},
            "clefs":{"right":{"sign":"G","line":2},
                     "left":{"sign":"F","line":4}}}],
        "notes":notes,"notation_events":events,"active_hand":"right"}

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Geometry = load("res://score_notation_geometry.gd")
    var Renderer = load("res://score_native_notation.gd")
    if Geometry == null or Renderer == null:
        check(false, "Scripts parse successfully")
        quit(1)
        return
    var model: Dictionary = score()
    check(Geometry.supported(model) == "",
        "Supported tuplets and double dots must not fall back")
    check(absf(Geometry.dotted_multiplier(2)-1.75) < .000001,
        "Double dot adds 1/2 then 1/4 of written duration")
    var tuplets: Array = Geometry.tuplet_groups(model)
    check(tuplets.size() == 2, "A five-over-four and one triplet bracket")
    if tuplets.size() == 2:
        check(tuplets[0]["events"].size() == 5,
            "Keep all five events under one explicit bracket")
        check(tuplets[1]["events"].size() == 3,
            "Keep all three notes under a single triplet")
        check(Geometry.tuplet_label(tuplets[0]) == "5",
            "Conventional quintuplet labels actual count")
        check(Geometry.tuplet_label(tuplets[1]) == "3",
            "Conventional triplet labels actual count")
    var beams: Array = Geometry.beam_groups(model)
    check(beams.size() == 2, "Explicit tuplets are grouped, not split on beats")
    if beams.size() == 2:
        check(beams[0].size() == 5 and beams[1].size() == 3,
            "Tuplet beams match exactly their semantic groups")
    var player = Renderer.new()
    get_root().add_child(player)
    player.size = Vector2(1280,470)
    check(player.set_verovio_glyphs(
        load("res://tests/native_glyph_fixture.gd").catalogue(),
        load("res://tests/native_glyph_fixture.gd").note_catalogue()),
        "Unit test has Verovio-shaped placeholder textures")
    check(player.load_score(model),"Native renderer accepts 5:4, 3:2, double dots")
    check(player.native_ready and player.notation_tuplets.size() == 2,
        "Tuples are cached as semantic groups, never SVG locations")
    var density: float = player.timeline.pixels_per_beat
    for bpm in [40.0,80.0,120.0]:
        player.present({"bpm":bpm,"running":true,"paused":false,
            "count_in_beats":4.0,"play_from_beat":0.0,
            "transport_id":4,"hand":"right"},-.5)
        check(absf(player.timeline.pixels_per_beat-density) < .001,
            "Tuplets never alter horizontal spacing based on BPM")
        var first_x: float = player.timeline.screen_x(2.0,-.5,500.0,0.0)
        var zero_x: float = player.timeline.screen_x(0.0,-.5,500.0,0.0)
        check(absf(first_x-zero_x-2.0*density) < .001,
            "Triplet grouping never changes the musical time axis")
    var arbitrary: Dictionary = model.duplicate(true)
    arbitrary["notation_events"][0]["time_modification"] = {
        "actual":7,"normal":5}
    arbitrary["notation_events"][0]["duration_beats"] = 5.0/14.0
    check(Geometry.tuplet_label({
        "actual":7,"normal":5,"show_number":"none"}) == "7:5",
        "Irregular durations must display full ratio")
    var impossible: Dictionary = model.duplicate(true)
    impossible["notation_events"][0]["time_modification"] = {
        "actual":0,"normal":2}
    check(not player.load_score(impossible),
        "Invalid time modification correctly preserves Verovio fallback")
    var over_dotted: Dictionary = model.duplicate(true)
    over_dotted["notation_events"][8]["dots"] = 3
    check(not player.load_score(over_dotted),
        "Triple dot keeps safe fallback until supported")
    check(player.load_score(model),"Valid tuplets recover after fallback")
    player.clear_score()
    check(player.notation_tuplets.is_empty(),
        "Changing lessons drops earlier tuplet brackets")
    print("PHASE_C3_TUPLET_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
