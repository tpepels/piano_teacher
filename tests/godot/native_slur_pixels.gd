extends SceneTree

class SlurCanvas extends Node2D:
    var glyphs
    var reference := false
    func _draw() -> void:
        var data: Dictionary = glyphs.slur_metadata["s1|s2"]
        var b: Array = data["bounds"]
        var gap := 18.0
        var unit: float = gap/250.0
        var x := 25.0
        var y := 100.0
        if reference:
            draw_texture_rect(glyphs.slur_textures["s1|s2"],
                Rect2(x+float(b[0])*unit,y+float(b[1])*unit,
                    float(b[2])*unit,float(b[3])*unit),false,Color.WHITE)
        else:
            glyphs.paint_slur(self,"s1|s2",x,y,
                x+float(data["span"])*unit,
                y+float(data["original_end_y"])*unit,gap,Color.WHITE)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var glyphs = load("res://notation/native/glyphs.gd").new()
    var atlas: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_environment("PIANO_TEACHER_SLUR_FIXTURE")))
    var failures := 0
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1" or \
            not glyphs.load_slur_fragments(atlas):
        print("NATIVE_SLUR_FAIL: Native source slur atlas failed to load")
        quit(1)
        return
    var views: Array[SubViewport] = []
    for reference in [false,true]:
        var view := SubViewport.new()
        view.size = Vector2i(500,180)
        view.transparent_bg = true
        view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        get_root().add_child(view)
        var canvas := SlurCanvas.new()
        canvas.glyphs = glyphs
        canvas.reference = reference
        canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
        view.add_child(canvas)
        views.append(view)
    await process_frame
    await RenderingServer.frame_post_draw
    var actual: Image = views[0].get_texture().get_image()
    var reference: Image = views[1].get_texture().get_image()
    var mismatch := 0
    var expected_ink := 0
    var actual_ink := 0
    for y in range(reference.get_height()):
        for x in range(reference.get_width()):
            var ink: float = reference.get_pixel(x,y).a
            var drawn: float = actual.get_pixel(x,y).a
            if ink > .1:
                expected_ink += 1
            if drawn > .1:
                actual_ink += 1
            if absf(ink-drawn) > .1:
                mismatch += 1
    if expected_ink < 20 or mismatch > expected_ink*.12:
        failures += 1
        print("NATIVE_SLUR_FAIL: Authentic source alpha differs: ",
            mismatch," pixels, expected ink ",expected_ink," actual ink ",actual_ink)
    print("NATIVE_SLUR_PIXEL_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
