extends SceneTree
# Exercise the production view's contour painter at a compressed head span.
# The Python test measures the framebuffer; no reported geometry proves ink.
class TieView extends "res://notation/native/view.gd":
    var last_kind := "whole"
    func _draw() -> void:
        var first := {"note_type":"eighth","staff":"right"}
        var last := {"note_type":last_kind,"staff":"right"}
        _paint_tie_contour(first,last,
            {"x0":80.0,"x1":118.0,"y":80.0,"down":true},21.875)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var viewport := SubViewport.new()
    viewport.size = Vector2i(220,160)
    viewport.transparent_bg = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var view := TieView.new()
    view.last_kind = str(fixture.get("last_kind","whole"))
    view.size = Vector2(220,160)
    viewport.add_child(view)
    if not view.glyphs.load_font(fixture["glyphs"]) or not \
            view.glyphs.load_tie_templates(fixture["ties"]):
        push_error("Original Verovio tie assets unavailable")
        quit(1)
        return
    view.queue_redraw()
    await process_frame
    await RenderingServer.frame_post_draw
    var image := viewport.get_texture().get_image()
    if image.is_empty() or image.save_png(args[1]) != OK:
        quit(1)
        return
    quit(0)
