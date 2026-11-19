extends RefCounted
## Owns the reusable glyph-interior cache and pre-play GPU warmup policy.
## The Main scene never reads this cache or creates temporary draw layers.
const NoteStatusInk := preload("res://note_status_ink.gd")
const StatusInkWarmup := preload("res://status_ink_warmup.gd")

var _head_interiors: Dictionary = {}

func warm(renderer) -> void:
    # Round 4 (I5): the first coloured head of a score built its head
    # interior masks (the status "fill" pass) inside the first take, a
    # 110+ ms CPU stall at the first graded attack. Build them now, while
    # the score loads, before any Play.
    if renderer == null or not is_instance_valid(renderer) or \
            renderer.get("glyphs") == null:
        return
    var glyphs = renderer.glyphs
    if not glyphs.has_method("head_interior"):
        return
    var started: int = Time.get_ticks_usec()
    # Every stage engraves the same head glyphs: an interior built for one
    # renderer is reused (same image bytes) by the next, so a stage handoff
    # promoted inside a count-in does not rebuild them there.
    var reused := 0
    for head in glyphs.head_images.keys():
        var image: Image = glyphs.head_images[head]
        var key: String = "%s|%s|%d" % [str(head),str(image.get_size()),
            hash(image.get_data())]
        if _head_interiors.has(key) and "_head_interiors" in glyphs:
            glyphs._head_interiors[str(head)] = _head_interiors[key]
            reused += 1
        else:
            _head_interiors[key] = glyphs.head_interior(str(head))
    if reused == glyphs.head_images.size():
        return
    # Then draw every status pass once, near-transparent, so its blend
    # pipeline, the interior textures' upload and the glow sizes' glyph
    # rasterization also happen now (GL Compatibility does them lazily).
    var gap: float = float(renderer.staff_gap()) if renderer.has_method("staff_gap") else 10.0
    var warm := StatusInkWarmup.new()
    warm.name = "StatusInkWarmup"
    renderer.add_child(warm)
    for pass_name in NoteStatusInk.PASSES:
        var layer := Node2D.new()
        layer.material = NoteStatusInk.material_for(pass_name)
        layer.draw.connect(func() -> void:
            var faint := Color(1,1,1,0.004)
            for head in glyphs.head_images.keys():
                var interior: Texture2D = glyphs.head_interior(str(head))
                if interior != null:
                    layer.draw_texture_rect(interior,Rect2(2,2,4,4),false,faint)
                for scale in [1.0,NoteStatusInk.INNER_SCALE,NoteStatusInk.OUTER_SCALE]:
                    glyphs.paint(layer,str(head),4.0,4.0,gap*scale,faint,true))
        warm.add_child(layer)
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
        print("STATUS_HEADS_WARMED: ",glyphs.head_images.size()," ms=",
            (Time.get_ticks_usec()-started)/1000)

