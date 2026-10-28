extends SceneTree

class BeamCanvas extends "res://notation/native/view.gd":
    var beam_data: Dictionary = {}
    func _draw() -> void:
        layout.set_viewport(size)
        if not beam_data.is_empty():
            symbols.paint_beams(self,RenderPass.new(),beam_data,17.0)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var renderer = load("res://notation/native/view.gd").new()
    root.add_child(renderer)
    renderer.size = Vector2(1200,560)
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1" or not \
            renderer.set_verovio_glyphs(data["glyphs"],data["notes"],data["ties"],
                data["chords"],data["beams"]) or not renderer.load_score(data["model"]):
        print("NATIVE_BEAM_CONTACT_FAIL: Authentic native fixture did not load")
        quit(1)
        return
    var failures := 0
    var views: Array = []
    var samples: Array = []
    var offsets: Dictionary = renderer.layout.engraved_head_offsets(17.0)
    for density in [96.0,156.0,320.0]:
        renderer.set_density(density)
        for beat in [0.0,4.0]:
            var layout: Dictionary = renderer.beam_plan(17.0,beat,120.0,offsets)
            var key: String = "a|b" if beat == 0.0 else "c|d"
            var view := SubViewport.new()
            view.size = Vector2i(800,560)
            view.transparent_bg = true
            view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
            root.add_child(view)
            var canvas := BeamCanvas.new()
            canvas.size = Vector2(800,560)
            canvas.glyphs = renderer.glyphs
            canvas.beam_data = layout
            canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
            view.add_child(canvas)
            views.append(view)
            for group in layout["groups"]:
                if str(group["art_key"]) != key:
                    continue
                for member in group["members"]:
                    samples.append({"view":view,"density":density,
                        "id":member["id"],"x":member["x"],"y":member["tip_y"]})
    await process_frame
    await RenderingServer.frame_post_draw
    for sample in samples:
        var image: Image = sample["view"].get_texture().get_image()
        var contact := false
        for dy in range(-2,3):
            for dx in range(-2,3):
                var x: int = roundi(float(sample["x"]))+dx
                var y: int = roundi(float(sample["y"]))+dy
                if image.get_pixel(x,y).a > .15:
                    contact = true
        if not contact:
            failures += 1
            print("NATIVE_BEAM_CONTACT_FAIL: ",sample["id"],
                " at ",sample["density"]," px/beat does not touch its measured stem")
    if samples.size() != 12:
        failures += 1
        print("NATIVE_BEAM_CONTACT_FAIL: Missing source stem samples: ",samples.size())
    print("NATIVE_BEAM_CONTACT_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
