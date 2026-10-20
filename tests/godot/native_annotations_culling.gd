extends SceneTree

const NativeView := preload("res://notation/native/view.gd")
var failures := 0

class CullingCanvas extends Node2D:
    var painter
    var reference_texture: Texture2D
    var reference_rect := Rect2()
    func _draw() -> void:
        if reference_texture != null:
            draw_texture_rect(reference_texture,reference_rect,false,Color.WHITE)
        else:
            painter.paint(self,20000.0,300.0,18.0)

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        print("NATIVE_ANNOTATION_CULL_FAIL: ", description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_ANNOTATIONS_FIXTURE")))
    var model := {"annotations":[], "visual_events":[], "notation_events":[], "staff_order":["right"]}
    var atlas := {}
    # Reverse insertion order proves bind constructs an ordered index. One
    # passage-long span must not pin the start of a linear prefix scan at zero.
    for i in range(9999, -1, -1):
        var id := "point-"+str(i)
        var event := {"id":id,"kind":"dynamic","beat":float(i)*4.0,
            "staff":"right","voice":"1","event_ids":[],"attributes":{}}
        model["annotations"].append(event)
        var art: Dictionary = source["annotation_fragments"]["a-dynamic"].duplicate()
        art.merge(event, true)
        art["group_ids"] = [id]
        atlas[id] = art
    var span := {"id":"long-span","kind":"hairpin","beat":0.0,"end_beat":40000.0,
        "staff":"right","voice":"1","event_ids":[],"attributes":{}}
    var art: Dictionary = source["annotation_fragments"]["a-hairpin"].duplicate()
    art.merge(span, true)
    art["group_ids"] = ["long-span"]
    model["annotations"].append(span)
    atlas["long-span"] = art
    var renderer = NativeView.new()
    renderer.size = Vector2(1000,700)
    var painter = load("res://notation/native/annotations.gd").new()
    # Warm the shared authentic texture so this isolates query complexity,
    # rather than timing 10,000 identical SVG-derived texture imports.
    var warm: Dictionary = model.duplicate()
    warm["annotations"] = [model["annotations"][0]]
    var warm_id: String = warm["annotations"][0]["id"]
    check(painter.bind({"native_annotation_fragments":{warm_id:atlas[warm_id]}}, warm, renderer), "warm source texture")
    check(painter.bind({"native_annotation_fragments":atlas}, model, renderer), "bind authentic art index")
    for clock in [20000.0, 39000.0, 16000.0]:
        var placements: Array = painter.placements(clock,300.0,18.0)
        check(placements.size() < 16, "offscreen placement allocations bounded: "+str(placements.size()))
        var visited: Variant = painter.get("frame_scanned_entries")
        check(visited != null and int(visited) < 16, "visited annotation count bounded")
        var probes: Variant = painter.get("frame_index_visits")
        check(probes != null and int(probes) < 160, "interval traversal bounded despite long span")
        check(placements.any(func(p): return p["id"] == "long-span"), "offscreen-start long span retained")
        var middle := "point-"+str(int(clock/4.0))
        check(placements.any(func(p): return p["id"] == middle), "visible point retained after seek")
        check(not placements.any(func(p): return p["id"] == "point-0"), "expired point culled")
        print("NATIVE_ANNOTATION_CULL_STATS:", clock, ":entries=",visited,
            ":index=",probes, ":placements=",placements.size())
    # Compare actual paint() ink against the original source span stretched
    # over its exact model beats. The sampled strip excludes point glyphs.
    var part: Dictionary = atlas["long-span"]["parts"][0]
    var image := Image.new()
    image.load_png_from_buffer(Marshalls.base64_to_raw(part["png_base64"]))
    var texture := ImageTexture.create_from_image(image)
    var b: Array = part["bounds"]
    var factor: float = 40000.0*96.0/(float(art["span"])*18.0/250.0)
    var expected_rect := Rect2(300.0-20000.0*96.0+float(b[0])*18.0/250.0*factor,
        renderer._staff_center("right")-36.0+float(b[1])*18.0/250.0,
        float(b[2])*18.0/250.0*factor,float(b[3])*18.0/250.0)
    var views: Array[SubViewport] = []
    for reference in [false,true]:
        var view := SubViewport.new()
        view.size = Vector2i(1000,700)
        view.transparent_bg = true
        view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        get_root().add_child(view)
        var canvas := CullingCanvas.new()
        canvas.painter = painter
        if reference:
            canvas.reference_texture = texture
            canvas.reference_rect = expected_rect
        canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
        view.add_child(canvas)
        views.append(view)
    await process_frame
    await RenderingServer.frame_post_draw
    var actual: Image = views[0].get_texture().get_image()
    var expected: Image = views[1].get_texture().get_image()
    var ink := 0
    var mismatch := 0
    for y in range(700):
        for x in range(130,250):
            var alpha: float = expected.get_pixel(x,y).a
            if alpha > .1:
                ink += 1
            if absf(alpha-actual.get_pixel(x,y).a) > .1:
                mismatch += 1
    check(ink > 20 and mismatch <= ink*.02, "offscreen-start span paints original pixels")
    for view in views:
        view.queue_free()
    renderer.play_from_beat = 20000.0
    check(painter.placements(0.0,300.0,18.0).any(func(p): return p["id"] == "point-5000"),
        "seek offset shares timeline visibility window")
    check(painter.placements(100000.0,300.0,18.0).is_empty(), "empty distant window")
    var empty_visits: Variant = painter.get("frame_scanned_entries")
    check(empty_visits != null and int(empty_visits) == 0, "empty window visits no annotations")
    check(not painter.bind({}, model, renderer), "failed rebind")
    check(painter.placements(0.0,300.0,18.0).is_empty(), "failed bind clears interval index")
    renderer.free()
    print("NATIVE_ANNOTATION_CULL_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
