extends SceneTree
## Every stage engraves the same Verovio font: a second renderer (a stage
## handoff, built inside the next take's count-in) reuses the rasterized
## symbols instead of re-rasterizing ~67 SVGs on the main thread.
func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var layout: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var failures := 0
    var first = load("res://notation/native/view.gd").new()
    root.add_child(first)
    if not first.glyphs.load_font(layout["native_glyphs"]):
        print("GLYPH_CACHE_FAIL:first load ",first.glyphs.error)
        failures += 1
    var second = load("res://notation/native/view.gd").new()
    root.add_child(second)
    var started: int = Time.get_ticks_usec()
    if not second.glyphs.load_font(layout["native_glyphs"]):
        print("GLYPH_CACHE_FAIL:second load ",second.glyphs.error)
        failures += 1
    var elapsed_ms: float = float(Time.get_ticks_usec()-started)/1000.0
    for name in first.glyphs.textures:
        if second.glyphs.textures.get(name) != first.glyphs.textures[name]:
            print("GLYPH_CACHE_FAIL:texture not shared ",name)
            failures += 1
            break
    if first.glyphs.head_images.size() != second.glyphs.head_images.size():
        failures += 1
    if elapsed_ms > 20.0:
        print("GLYPH_CACHE_FAIL:second load took %.1f ms" % elapsed_ms)
        failures += 1
    print("GLYPH_CACHE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
