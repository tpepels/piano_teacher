extends SceneTree
# Real native renderer, genuine Leipzig/Verovio ink, off-screen viewport pixels.
# Compares a score with rests against the exact same staff without rests.
var failures: Array[String] = []

func check(ok: bool, why: String) -> void:
    if not ok:
        failures.append(why)
        print("NATIVE_REST_FAIL: ", why)

func _initialize() -> void:
    call_deferred("run")

func _model(events: Array) -> Dictionary:
    return {"schema":"piano-teacher-score-model-v1",
        "revision":17,"beat_unit":"quarter","duration_beats":8.0,
        "measures":[{"number":1,"start_beat":0.0,"end_beat":8.0,
            "meter":[4,4],"keys":{"right":0,"left":0},
            "clefs":{"right":{"sign":"G","line":2,"octave_change":0},
                "left":{"sign":"F","line":4,"octave_change":0}}}],
        "notes":[],"notation_events":events,"active_hand":"both",
        "active_note_ids":[]}

func _rest(staff: String, kind: String, beat: float,
        dots: int = 0, voice: String = "1") -> Dictionary:
    return {"id":"rest:"+staff+":"+kind+":"+voice,
        "source_id":null,"kind":"rest","staff":staff,"voice":voice,
        "measure":1,"beat":beat,"duration_beats":1.0,
        "note_type":kind,"dots":dots,"chord":false,
        "spelling":null,"time_modification":null}

func _difference(before: Image, after: Image,
        x0: int, x1: int, y0: int, y1: int) -> Dictionary:
    var count := 0
    var sum_y := 0.0
    var minimum := 99999
    var maximum := -1
    for y in range(maxi(0,y0),mini(after.get_height(),y1)):
        for x in range(maxi(0,x0),mini(after.get_width(),x1)):
            var a: Color = before.get_pixel(x,y)
            var b: Color = after.get_pixel(x,y)
            if absf(a.r-b.r)+absf(a.g-b.g)+absf(a.b-b.b)+absf(a.a-b.a) > .18:
                count += 1
                sum_y += y
                minimum = mini(minimum,y)
                maximum = maxi(maximum,y)
    return {"count":count,"average":sum_y/maxf(1.0,float(count)),
        "minimum":minimum,"maximum":maximum}

func _image(view: SubViewport) -> Image:
    await process_frame
    await process_frame
    await RenderingServer.frame_post_draw
    return view.get_texture().get_image()

func run() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    if args.size() < 2:
        check(false,"Missing Verovio asset fixture or screenshot folder")
        quit(1)
        return
    var assets: Variant = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    if not assets is Dictionary:
        check(false,"Invalid authentic glyph fixture")
        quit(1)
        return
    var Geometry = load("res://notation/native/geometry.gd")
    var view := SubViewport.new()
    view.size = Vector2i(1600,480)
    view.transparent_bg = true
    view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(view)
    var renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(1600,480)
    view.add_child(renderer)
    if not renderer.set_verovio_glyphs(assets["glyphs"],assets["notes"],
            assets["ties"]):
        check(false,"Cannot load original Verovio glyphs: "+renderer.failure_reason)
        quit(1)
        return
    var baseline: Dictionary = _model([])
    check(renderer.load_score(baseline),"Empty but valid native grand staff")
    var empty_ink: Image = await _image(view)
    var kinds: Array = ["whole","half","quarter","eighth","16th","32nd","64th"]
    var events: Array = []
    for staff in ["right","left"]:
        for i in range(kinds.size()):
            events.append(_rest(staff,kinds[i],float(i)))
    check(renderer.load_score(_model(events)),
        "Original whole through 64th rests stay on the native renderer")
    var with_rests: Image = await _image(view)
    var gap: float = renderer._gap()
    var density: float = renderer.timeline.pixels_per_beat
    for event in events:
        var kind: String = str(event["note_type"])
        var staff: String = str(event["staff"])
        var center: float = renderer._staff_center(staff)
        var expected_origin: float = center+Geometry.rest_staff_offset(kind)*gap
        var font_box: Array = renderer.glyphs.bounds["rest_"+kind]
        var x: int = roundi(renderer.size.x*.42+
            float(event["beat"])*density)
        var unit: float = gap/250.0
        var metrics: Dictionary = _difference(empty_ink,with_rests,
            x-35,x+36,
            floori(expected_origin+float(font_box[1])*unit-3.0),
            ceili(expected_origin+float(font_box[1]+font_box[3])*unit+4.0))
        check(int(metrics["count"]) >= 8,
            "Actual Verovio "+staff+" "+kind+" rest has ink at its staff-line origin")
        # The test detects rendered *pixels*, not just expected geometry.
        if int(metrics["count"]) > 8 and kind in ["whole","half"]:
            var top_ink: float = expected_origin+(
                float(font_box[1])+12.0)*unit
            var bottom_ink: float = expected_origin+(
                float(font_box[1]+font_box[3])-12.0)*unit
            check(float(metrics["average"]) >= top_ink-3.0 and
                float(metrics["average"]) <= bottom_ink+3.0,
                "Whole/half "+staff+" rest has the correct detected pixel height")
    var folder: String = args[1]
    DirAccess.make_dir_recursive_absolute(folder)
    with_rests.save_png(folder.path_join("native-rests-both-staves.png"))
    # Dots are genuine Verovio glyphs; compare an otherwise identical
    # native render to confirm their displayed Y and right-side placement.
    var dotted: Array = events.duplicate(true)
    for event in dotted:
        event["dots"] = 2
    check(renderer.load_score(_model(dotted)),
        "Double-dotted rests keep authentic native rendering")
    var dotted_image: Image = await _image(view)
    for event in dotted:
        var kind: String = str(event["note_type"])
        var staff: String = str(event["staff"])
        var origin_y: float = renderer._staff_center(staff)+(
            Geometry.rest_staff_offset(kind)+Geometry.rest_dot_offset(kind))*gap
        var x: int = roundi(renderer.size.x*.42+
            float(event["beat"])*renderer.timeline.pixels_per_beat)
        var pixels: Dictionary = _difference(with_rests,dotted_image,
            x+roundi(gap*.75),x+roundi(gap*2.35),
            floori(origin_y-gap*.6),ceili(origin_y+gap*.45))
        check(int(pixels["count"]) >= 4,
            "Native "+staff+" "+kind+" double dots appear beside the rest")
    dotted_image.save_png(folder.path_join("native-double-dotted-rests.png"))
    # Same staff, simultaneous independent voices. A rest is not allowed
    # to intersect another voice's notehead, stem, accidental or rest.
    var voices: Array = [
        _rest("right","quarter",0.0,0,"1"),
        _rest("right","quarter",0.0,0,"3"),
        _rest("right","eighth",0.0,1,"4"),
        _rest("left","half",0.0,0,"1"),
        _rest("left","half",0.0,0,"2")]
    voices.append({"id":"upper-note","source_id":"upper-note",
        "kind":"note","staff":"right","voice":"2","measure":1,
        "beat":0.0,"duration_beats":1.0,"note_type":"quarter",
        "dots":0,"chord":false,"spelling":{"step":"B",
            "octave":4,"alter":0},"time_modification":null})
    var poly: Dictionary = _model(voices)
    poly["notes"] = [{"id":"upper-note","onset_beats":0.0,
        "duration_beats":1.0,"midi_pitch":71,"hand":"right"}]
    check(renderer.load_score(poly),
        "Independent voices remain on native renderer without collisions")
    check(renderer.unavoidable_rest_overlaps == 0,
        "Ordinary polyphonic fixtures must not require compromised rest positions")
    var heads: Dictionary = renderer._engraved_head_offsets(gap)
    var accidentals: Dictionary = Geometry.accidental_offsets(
        renderer.ordered_events,gap,heads,renderer.glyphs.bounds)
    for i in range(voices.size()):
        for j in range(i+1,voices.size()):
            var first: Dictionary = voices[i]
            var second: Dictionary = voices[j]
            if first["staff"] != second["staff"] or first["voice"] == second["voice"]:
                continue
            var a: Rect2 = renderer._event_ink_rect(first,gap,heads,accidentals)
            var b: Rect2 = renderer._event_ink_rect(second,gap,heads,accidentals)
            check(not a.intersects(b.grow(gap*.05)),
                "Cross-voice glyph collision: "+str(first["id"])+" / "+str(second["id"]))
    var poly_image: Image = await _image(view)
    poly_image.save_png(folder.path_join("native-polyphonic-rests.png"))
    # The screenshot observation: treble notes far above the stave had
    # too-short, translucent ledger extensions hidden by authentic heads.
    # Capture actual pixels in the extended portion of a C6 ledger rule.
    var high: Dictionary = _model([{
        "id":"high-c6","source_id":"high-c6","kind":"note",
        "staff":"right","voice":"1","measure":1,"beat":1.0,
        "duration_beats":1.0,"note_type":"quarter","dots":0,
        "chord":false,"spelling":{"step":"C","octave":6,"alter":0},
        "time_modification":null}])
    high["notes"] = [{"id":"high-c6","onset_beats":1.0,
        "duration_beats":1.0,"midi_pitch":84,"hand":"right"}]
    check(renderer.load_score(high),"High C6 native Verovio note supported")
    var ledger_image: Image = await _image(view)
    var ledger_gap: float = renderer._gap()
    var high_center: float = renderer._staff_center("right")
    var c6_y: float = high_center-4.0*ledger_gap
    var note_x: int = roundi(renderer.size.x*.42+
        renderer.timeline.pixels_per_beat)
    var rail: Dictionary = _difference(empty_ink,ledger_image,
        note_x+roundi(ledger_gap*.75), note_x+roundi(ledger_gap*.98)+1,
        roundi(c6_y)-2,roundi(c6_y)+3)
    check(int(rail["count"]) >= 3,
        "Visible high-ledger extensions survive beyond original notehead ink")
    ledger_image.save_png(folder.path_join("native-extended-ledger.png"))
    print("NATIVE_REST_PIXEL_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
