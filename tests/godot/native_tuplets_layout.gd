extends SceneTree

var failures: Array[String] = []
var draws := 0

class OriginalTuplets extends Node2D:
    var layout
    var glyphs
    var timeline
    var groups: Array = []
    var suite
    func _draw() -> void:
        var event_y := func(event: Dictionary,_gap: float) -> float:
            return 300.0 if event["kind"] == "rest" else 250.0
        for group in groups:
            var p: Dictionary = layout.placement(group,timeline,0.0,70.0,0.0,20.0,{},event_y)
            suite.check(not p.is_empty(),"Place complete original compound")
            if p.is_empty():
                continue
            suite.check(glyphs.paint_tuplet(self,p["key"],p["x0"],p["x1"],p["y"],20.0,Color.WHITE),
                "Paint projected source compound with semantic key")
            suite.draws += 1

func check(ok: bool,label: String) -> void:
    if not ok:
        failures.append(label)
        print("NATIVE_TUPLETS_LAYOUT_FAIL: ",label)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    check(OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1","Native flag")
    if not ResourceLoader.exists("res://notation/native/tuplets_layout.gd"):
        check(false,"Missing stable semantic tuplet adapter")
        print("NATIVE_TUPLETS_LAYOUT_FAILURES:",failures.size())
        quit(1)
        return
    var Layout = load("res://notation/native/tuplets_layout.gd")
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_TUPLETS_FIXTURE")))
    var model: Dictionary = data["model"]
    var atlas = load("res://notation/native/glyphs.gd").new()
    check(atlas.load_tuplet_fragments(data["tuplets"]),"Load original compounds")
    var groups: Array = Layout.groups(model)
    check(groups.size() == 2,"Both projected groups survive")
    check(Layout.missing(groups,atlas).is_empty(),"Stable IDs resolve genuine group textures")
    for group in groups:
        check(atlas.has_tuplet(Layout.key(group),true),"Lookup uses semantic group ID")
    var missing_number: Dictionary = data["tuplets"].duplicate(true)
    var source_group: Dictionary = groups[0].duplicate(true)
    var source_key: String = Layout.key(source_group)
    missing_number[source_key]["number"] = null
    var numberless = load("res://notation/native/glyphs.gd").new()
    check(numberless.load_tuplet_fragments(missing_number),
        "Optional numeral masks can load for genuinely hidden source labels")
    check(not numberless.has_tuplet(source_key,false),
        "Default readiness requires an original numeral")
    for presentation in ["actual","both"]:
        source_group["show_number"] = presentation
        check(not Layout.missing([source_group],numberless).is_empty(),
            "Visible source label cannot pass helper readiness without numeral: "+presentation)
    var hidden_model: Dictionary = model.duplicate(true)
    for source in hidden_model["groups"]:
        source["attributes"]["show-number"] = "none"
    var hidden_groups: Array = Layout.groups(hidden_model)
    check(str(hidden_groups[0]["show_number"]) == "none",
        "Explicit source hidden-number metadata survives group normalization")
    source_group["show_number"] = "none"
    check(Layout.missing([source_group],numberless).is_empty(),
        "Source-hidden label does not require a numeral")
    var renderer = load("res://notation/native/view.gd").new()
    renderer.glyphs = numberless
    source_group["show_number"] = "actual"
    renderer.notation_tuplets = [source_group]
    check(not renderer._missing_source_engraving().is_empty(),
        "Production view readiness rejects a missing requested numeral")
    source_group["show_number"] = "none"
    renderer.notation_tuplets = [source_group]
    check(renderer._missing_source_engraving().is_empty(),
        "Production view accepts an explicitly hidden source numeral")
    renderer.free()
    var empty := model.duplicate(true)
    empty["groups"] = []
    check(Layout.groups(empty).is_empty(),"Explicit-empty groups disable legacy guessing")
    var legacy := model.duplicate(true)
    legacy.erase("groups")
    var old: Array = Layout.groups(legacy)
    check(old.size() == 2,"Absent groups use marks across measures")
    var rest_count := 0
    for group in old:
        for event in group["events"]:
            if event["kind"] == "rest":
                rest_count += 1
    check(rest_count == int(data["expected_rest_members"]),"Legacy membership retains every original rest")
    var same := model.duplicate(true)
    same["groups"] = same["groups"].filter(func(g: Dictionary) -> bool:
        return g.get("event_ids",[]).size() > 1)
    same["groups"][1]["event_ids"] = same["groups"][0]["event_ids"].duplicate()
    var same_groups: Array = Layout.groups(same)
    check(same_groups.size() == 2 and Layout.key(same_groups[0]) != Layout.key(same_groups[1]),
        "Same endpoints still have distinct semantic group keys")
    var rest := {"id":"rest-start","kind":"rest","beat":1.0,"staff":"right","voice":"1"}
    var note := {"id":"last","kind":"note","beat":3.0,"staff":"right","voice":"1"}
    var rest_model := {"notation_events":[rest,note],"groups":[{
        "id":"rest-group","kind":"tuplet","event_ids":["rest-start","last"],
        "staff":"right","voice":"1","attributes":{"actual":3,"normal":2}}]}
    var rest_group: Dictionary = Layout.groups(rest_model)[0]
    var timeline = load("res://notation/shared/timeline.gd").new()
    timeline.set_density(96.0)
    var event_y := func(event: Dictionary,_gap: float) -> float:
        return 300.0 if event["kind"] == "rest" else 250.0
    for clock in [-3.0,0.0,2.0]:
        var p: Dictionary = Layout.placement(rest_group,timeline,float(clock),500.0,0.0,
            20.0,{"rest-start":9999.0,"last":7.0},event_y)
        check(absf(float(p["x0"])-(596.0-float(clock)*96.0)) < .001,
            "Rest endpoint stays on its original linear beat")
        check(absf(float(p["x1"])-(795.0-float(clock)*96.0)) < .001,
            "Note endpoint retains the original displaced head")
        check(float(p["y"]) == 300.0,"Rest source origin reaches its actual staff anchor")
    var viewport := SubViewport.new()
    viewport.size = Vector2i(640,520)
    viewport.transparent_bg = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    get_root().add_child(viewport)
    var canvas := OriginalTuplets.new()
    canvas.layout = Layout
    canvas.glyphs = atlas
    canvas.timeline = timeline
    canvas.groups = groups
    canvas.suite = self
    viewport.add_child(canvas)
    await process_frame
    await process_frame
    check(draws == 2,"Both original nested/cross-measure compounds reach the native draw method")
    if OS.get_environment("PIANO_TEACHER_TUPLETS_PIXELS") == "1":
        await RenderingServer.frame_post_draw
        var image := viewport.get_texture().get_image()
        var ink := 0
        for y in range(image.get_height()):
            for x in range(image.get_width()):
                if image.get_pixel(x,y).a > .1:
                    ink += 1
        check(ink > 100,"Actual projected compounds produce original visible Verovio pixels")
    print("NATIVE_TUPLETS_LAYOUT_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
