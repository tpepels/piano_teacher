extends SceneTree
var failures: Array[String] = []
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("FIDELITY_CLEF_FAIL:",message)
func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1200,600)
    var args := OS.get_cmdline_user_args()
    var symbols: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var script = load("res://score_overlay.gd")
    var normal = script.new()
    var changed = script.new()
    var has_metadata := false
    for property in normal.get_property_list():
        if property.name == "preparation_clefs": has_metadata = true
    check(has_metadata,"Preparation must accept the active engraved clefs")
    if not has_metadata:
        quit(1)
        return
    for overlay in [normal,changed]:
        root.add_child(overlay)
        overlay.size = Vector2(600,600)
        overlay.image_size = overlay.size
        overlay.load_symbols(symbols)
        overlay.lead_first = {"x":.85,"top":.1,"bottom":.9}
        overlay.lead_width_px = 300
        overlay.lead_beats = 4
        overlay.showing = true
        overlay.lead_meter = [4,4]
        overlay.lead_staff_lines = [.20,.22,.24,.26,.28,.62,.64,.66,.68,.70]
    changed.position.x = 600
    changed.preparation_clefs = {"right":{"sign":"F","line":4,"octave_change":0},"left":{"sign":"G","line":2,"octave_change":0}}
    normal.queue_redraw()
    changed.queue_redraw()
    await process_frame
    await RenderingServer.frame_post_draw
    var picture := root.get_texture().get_image()
    picture.save_png(args[1])
    for bounds in [Rect2i(90,80,80,120),Rect2i(90,325,80,130)]:
        var different := 0
        for y in range(bounds.position.y,bounds.end.y):
            for x in range(bounds.position.x,bounds.end.x):
                var a: Color = picture.get_pixel(x,y)
                var b: Color = picture.get_pixel(x+600,y)
                if Vector3(a.r-b.r,a.g-b.g,a.b-b.b).length() > .15:
                    different += 1
        check(different > 30,"Actual preparation clef pixels change on each intended staff")
    print("FIDELITY_CLEF_FAILURES:",failures.size())
    quit(1 if failures.size() else 0)
