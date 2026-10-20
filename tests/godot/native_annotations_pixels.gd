extends SceneTree

const NativeView := preload("res://notation/native/view.gd")
var failures := 0

class AnnotationCanvas extends Node2D:
    var painter
    var reference: Array = []
    var direct := false
    func _draw() -> void:
        if direct:
            for entry in reference:
                draw_texture_rect(entry["texture"], entry["rect"], false, Color.WHITE)
        else:
            painter.paint(self, 0.0, 180.0, 18.0, Color.WHITE)

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        print("NATIVE_ANNOTATION_FAIL: ", description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    check(OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") == "1", "native opt in")
    var source: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_ANNOTATIONS_FIXTURE")))
    var script = load("res://notation/native/annotations.gd")
    if script == null:
        check(false, "annotation painter is not implemented")
        quit(1)
        return
    var renderer = NativeView.new()
    renderer.size = Vector2(1100,700)
    var rejected = script.new()
    check(not rejected.bind({}, source["model"], renderer), "missing atlas must fail")
    var broken: Dictionary = source.duplicate(true)
    var first_id: String = str(source["model"]["annotations"][0]["id"])
    broken["annotation_fragments"][first_id]["beat"] = 1.0
    check(not rejected.bind(broken, source["model"], renderer), "incorrect source beat must fail")
    broken = source.duplicate(true)
    broken["annotation_fragments"][first_id]["parts"][0]["png_base64"] = "corrupt"
    check(not rejected.bind(broken, source["model"], renderer), "corrupt art must fail")
    var projected: Dictionary = source.duplicate(true)
    var aliases := {"dynamic":"dynamics", "hairpin":"wedge", "articulation":"articulations", "ornament":"ornaments"}
    for event in projected["model"]["annotations"]:
        event["kind"] = aliases.get(event["kind"], event["kind"])
        projected["annotation_fragments"][event["id"]]["kind"] = event["kind"]
    projected["model"]["annotations"].append({"id":"separate-slur", "kind":"slur"})
    check(rejected.bind(projected, projected["model"], renderer), "projection aliases and separate slur ownership")
    for ident in source["annotation_fragments"]:
        if source["annotation_fragments"][ident]["group_ids"][0] != ident:
            continue
        var model: Dictionary = source["model"].duplicate(true)
        model["annotations"] = model["annotations"].filter(func(e): return e["id"] == ident)
        var ids: Array = source["annotation_fragments"][ident]["group_ids"]
        model["visual_events"] = model["visual_events"].filter(func(e): return e["id"] in ids)
        var atlas := {}
        for member in ids:
            atlas[member] = source["annotation_fragments"][member]
        var item: Dictionary = atlas[ident]
        var density := 96.0
        if item.has("end_beat"):
            density = float(item["span"])*18.0/250.0 / float(item["end_beat"])
        check(renderer.timeline.set_score_density(density), "source density")
        var painter = script.new()
        check(painter.bind({"native_annotation_fragments":atlas}, model, renderer), "bind production layout key " + ident)
        if not painter.error.is_empty():
            print(painter.error)
            continue
        var placements: Array = painter.placements(0.0, 180.0, 18.0)
        check(placements.size() == item["parts"].size(), "grace art drawn once: " + ident)
        var shifted: Array = painter.placements(1.0, 180.0, 18.0)
        for i in range(placements.size()):
            check(absf(placements[i]["rect"].position.x - shifted[i]["rect"].position.x - density) < .001,
                "linear clock translation: " + ident)
        var attachment: String = str(item.get("anchor_id", ""))
        if attachment.is_empty() and not item.has("end_beat") and not item.get("event_ids", []).is_empty():
            attachment = str(item["event_ids"][0])
        if not attachment.is_empty():
            renderer.cached_group_offsets[attachment] = 29.0
            renderer.cached_head_offsets[attachment] = 13.0
            var attached: Array = painter.placements(0.0, 180.0, 18.0)
            for i in range(placements.size()):
                check(absf(attached[i]["rect"].position.x-placements[i]["rect"].position.x-13.0) < .001,
                    "point/grace follows native head offset: " + ident)
            renderer.cached_head_offsets.erase(attachment)
            attached = painter.placements(0.0, 180.0, 18.0)
            for i in range(placements.size()):
                check(absf(attached[i]["rect"].position.x-placements[i]["rect"].position.x-29.0) < .001,
                    "point/grace group offset fallback: " + ident)
            renderer.cached_group_offsets.erase(attachment)
        renderer.timeline.set_score_density(density*2.0)
        var doubled: Array = painter.placements(0.0, 180.0, 18.0)
        for i in range(placements.size()):
            var expected: float = placements[i]["rect"].size.x * (
                2.0 if placements[i]["role"] == "span" else 1.0)
            check(absf(doubled[i]["rect"].size.x-expected) < .001,
                "span stretches independently of fixed glyphs: " + ident)
        renderer.play_from_beat = 1.0
        var seeked: Array = painter.placements(0.0, 180.0, 18.0)
        for i in range(placements.size()):
            check(absf(doubled[i]["rect"].position.x-seeked[i]["rect"].position.x-density*2.0) < .001,
                "seek stays on the linear axis: " + ident)
        renderer.play_from_beat = 0.0
        renderer.timeline.set_score_density(density)
        var reference := []
        for part in item["parts"]:
            var image := Image.new()
            image.load_png_from_buffer(Marshalls.base64_to_raw(part["png_base64"]))
            var b: Array = part["bounds"]
            var top: float = renderer._staff_center(str(item["staff"]))-36.0
            reference.append({"texture":ImageTexture.create_from_image(image),
                "rect":Rect2(180.0+float(b[0])*18.0/250.0, top+float(b[1])*18.0/250.0,
                    float(b[2])*18.0/250.0, float(b[3])*18.0/250.0)})
        var views: Array[SubViewport] = []
        for direct in [false, true]:
            var view := SubViewport.new()
            view.size = Vector2i(1100,700)
            view.transparent_bg = true
            view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
            get_root().add_child(view)
            var canvas := AnnotationCanvas.new()
            canvas.painter = painter
            canvas.direct = direct
            canvas.reference = reference
            canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
            view.add_child(canvas)
            views.append(view)
        await process_frame
        await RenderingServer.frame_post_draw
        var actual: Image = views[0].get_texture().get_image()
        var expected: Image = views[1].get_texture().get_image()
        var ink := 0
        var mismatch := 0
        for y in range(expected.get_height()):
            for x in range(expected.get_width()):
                var alpha: float = expected.get_pixel(x,y).a
                if alpha > .1:
                    ink += 1
                if absf(alpha-actual.get_pixel(x,y).a) > .1:
                    mismatch += 1
        check(ink > 1 and mismatch <= ink*.02, "original alpha pixels: " + ident + " ink=" + str(ink) + " mismatch=" + str(mismatch))
        for view in views:
            view.queue_free()
    renderer.free()
    print("NATIVE_ANNOTATION_PIXEL_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
