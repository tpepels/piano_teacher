extends SceneTree
const NativeView := preload("res://notation/native/view.gd")
const Painter := preload("res://notation/native/annotations.gd")
var failures := 0

class GraceCanvas extends Node2D:
    var painter
    var reference: Array = []
    var direct := false
    func _draw() -> void:
        if direct:
            for part in reference:
                draw_texture_rect(part["texture"],part["rect"],false,Color.WHITE)
        else:
            painter.paint(self,0.0,180.0,18.0,Color.WHITE)

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        print("NATIVE_AFTER_GRACE_FAIL:",description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_AFTER_GRACE_FIXTURE")))
    var model: Dictionary = fixture["model"]
    var grace: Dictionary = model["visual_events"][0]
    var ident: String = str(grace["id"])
    var anchor: String = str(grace["anchor_id"])
    var item: Dictionary = fixture["native_annotation_fragments"][ident]
    check(float(grace["beat"]) == 1.0 and float(grace["layout_beat"]) == 0.0,
        "source after-grace matching beat and principal layout origin stay distinct")
    var renderer = NativeView.new()
    renderer.size = Vector2(640,700)
    renderer.cached_head_offsets[anchor] = 13.0
    renderer.cached_group_offsets[anchor] = 29.0
    var painter = Painter.new()
    check(painter.bind(fixture,model,renderer),"bind actual projected Verovio after-grace: "+painter.error)
    var bad: Dictionary = fixture.duplicate(true)
    var bad_model: Dictionary = model.duplicate(true)
    bad_model["visual_events"][0]["layout_beat"] = .5
    bad["native_annotation_fragments"][ident]["layout_beat"] = .5
    check(not Painter.new().bind(bad,bad_model,renderer),"reject layout origin detached from principal")
    var density: float = float(fixture["source_density"])
    check(renderer.timeline.set_score_density(density),"source density")
    var placements: Array = painter.placements(0.0,180.0,18.0)
    check(placements.size() == item["parts"].size(),"every after-grace part is visible")
    var reference: Array = []
    for i in range(item["parts"].size()):
        var part: Dictionary = item["parts"][i]
        var box: Array = part["bounds"]
        var image := Image.new()
        check(image.load_png_from_buffer(Marshalls.base64_to_raw(part["png_base64"])) == OK,"original grace mask")
        var rect := Rect2(193.0+float(box[0])*18.0/250.0,
            renderer._staff_center("right")-36.0+float(box[1])*18.0/250.0,
            float(box[2])*18.0/250.0,float(box[3])*18.0/250.0)
        reference.append({"texture":ImageTexture.create_from_image(image),"rect":rect})
        if i < placements.size():
            check(placements[i]["rect"].is_equal_approx(rect),"original anchor-relative art must not receive another beat of translation")
            check(placements[i]["rect"].position.x < 193.0+density,
                "after-grace remains before following principal at source density")
    var shifted: Array = painter.placements(.25,180.0,18.0)
    for i in range(mini(placements.size(),shifted.size())):
        check(absf(placements[i]["rect"].position.x-shifted[i]["rect"].position.x-density*.25)<.001,
            "grace scroll shares exact timeline")
    renderer.play_from_beat = .25
    var seeked: Array = painter.placements(0.0,180.0,18.0)
    check(seeked.size() == shifted.size(),"seek keeps layout interval visible")
    for i in range(mini(seeked.size(),shifted.size())):
        check(seeked[i]["rect"].is_equal_approx(shifted[i]["rect"]),"seek uses the same layout clock")
    renderer.play_from_beat = 0.0
    renderer.size.x = 400.0
    renderer.timeline.set_score_density(480.0)
    check(not painter.placements(0.0,180.0,18.0).is_empty(),
        "culling follows layout beat while matching beat and following attack are offscreen")
    renderer.size.x = 640.0
    renderer.timeline.set_score_density(density)
    if OS.get_environment("PIANO_TEACHER_AFTER_GRACE_PIXELS") == "1":
        var views: Array[SubViewport] = []
        for direct in [false,true]:
            var view := SubViewport.new()
            view.size = Vector2i(640,700)
            view.transparent_bg = true
            view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
            get_root().add_child(view)
            var canvas := GraceCanvas.new()
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
        for y in range(700):
            for x in range(640):
                var alpha: float = expected.get_pixel(x,y).a
                if alpha > .1:
                    ink += 1
                if absf(alpha-actual.get_pixel(x,y).a) > .1:
                    mismatch += 1
        check(ink>10 and mismatch<=ink*.02,"actual native after-grace alpha pixels match original placement: ink="+str(ink)+" mismatch="+str(mismatch))
        print("NATIVE_AFTER_GRACE_PIXELS:",ink,":mismatch=",mismatch)
        for view in views:
            view.queue_free()
    renderer.free()
    print("NATIVE_AFTER_GRACE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
