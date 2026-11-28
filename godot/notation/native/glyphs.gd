extends RefCounted
# Canvas composition for authenticated Verovio artwork. GlyphAssets is the
# sole asset/mask store; these established public catalog ports are read-only.
const StatusInk := preload("res://note_status_ink.gd")
const Assets := preload("res://notation/native/glyph_assets.gd")
const REQUIRED = Assets.REQUIRED
const NOTE_TEMPLATES = Assets.NOTE_TEMPLATES
const RASTER_SCALE = Assets.RASTER_SCALE
# One prepared set per head and screen scale. The worker owns its images
# through upload. Only the main thread attaches them to their source texture.
static var _last_head_sizes: Dictionary = {}
static var _head_size_lock := Mutex.new()

static var _display_cache: Dictionary = {}
var textures: Dictionary:
    get: return _assets.textures
var bounds: Dictionary:
    get: return _assets.bounds
var font_name: String:
    get: return _assets.font_name
var note_textures: Dictionary:
    get: return _assets.note_textures
var note_bounds: Dictionary:
    get: return _assets.note_bounds
var note_stem_textures: Dictionary:
    get: return _assets.note_stem_textures
var note_stem_bounds: Dictionary:
    get: return _assets.note_stem_bounds
var tie_textures: Dictionary:
    get: return _assets.tie_textures
var tie_metadata: Dictionary:
    get: return _assets.tie_metadata
var chord_textures: Dictionary:
    get: return _assets.chord_textures
var chord_metadata: Dictionary:
    get: return _assets.chord_metadata
var chord_heads_textures: Dictionary:
    get: return _assets.chord_heads_textures
var chord_heads_bounds: Dictionary:
    get: return _assets.chord_heads_bounds
var chord_stem_textures: Dictionary:
    get: return _assets.chord_stem_textures
var chord_stem_bounds: Dictionary:
    get: return _assets.chord_stem_bounds
var chord_instances: Dictionary:
    get: return _assets.chord_instances
var beam_textures: Dictionary:
    get: return _assets.beam_textures
var beam_metadata: Dictionary:
    get: return _assets.beam_metadata
var tuplet_textures: Dictionary:
    get: return _assets.tuplet_textures
var tuplet_metadata: Dictionary:
    get: return _assets.tuplet_metadata
var grace_textures: Dictionary:
    get: return _assets.grace_textures
var slur_textures: Dictionary:
    get: return _assets.slur_textures
var slur_metadata: Dictionary:
    get: return _assets.slur_metadata
var error: String:
    get: return _assets.error
var head_images: Dictionary:
    get: return _assets.head_images
var template_images: Dictionary:
    get: return _assets.template_images

var _assets := Assets.new()
var _prepared_head_sizes: Dictionary = {}
var _prepared_derived_sizes: Dictionary = {}

func prepare_head_interiors() -> void:
    _assets.prepare_head_interiors()

# Prepare only actual source note kinds and actual compound member indices.
# Both full and heads-only variants are needed because hand focus can
# choose a different representation of the same chord.
func prepare_source_cutouts(layout) -> void:
    var by_id: Dictionary = {}
    var kinds: Dictionary = {}
    for event in layout.ordered_events:
        if str(event.get("kind","")) != "note":
            continue
        by_id[str(event["id"])] = event
        kinds[str(event.get("note_type","quarter"))] = true
    for kind in kinds:
        if kind == "whole":
            continue
        var head: String = "head_half" if kind == "half" else "head_black"
        for up in [true,false]:
            var key: String = note_template_name(kind,up)
            if note_textures.has(key):
                _assets.prepare_cutout("note",key,0,head)
    for leader in chord_instances:
        var instance: Dictionary = chord_instances[leader]
        var key: String = str(instance.get("key",""))
        var members: Array = instance.get("heads",[])
        for index in range(members.size()):
            var event: Dictionary = by_id.get(str(members[index]),{})
            if event.is_empty():
                continue
            var kind: String = str(event.get("note_type","quarter"))
            var head: String = "head_whole" if kind == "whole" else ("head_half" if kind == "half" else "head_black")
            if chord_textures.has(key):
                _assets.prepare_cutout("chord",key,index,head)
            if chord_heads_textures.has(key):
                _assets.prepare_cutout("chord_heads",key,index,head)


func begin_upload() -> void:
    _assets.begin_upload()
    # The worker's derived head sizes participate in the same bounded
    # upload as the original glyphs. Do not re-rasterize or draw a second
    # batch of warmup nodes during score-ready publication.
    for catalog in [_prepared_head_sizes,_prepared_derived_sizes]:
        for key in catalog:
            _assets.append_upload_catalog(catalog[key])

func rewind_upload() -> void:
    _assets.rewind_upload()

static func _status_sizes(image: Image, base_size: Vector2, scales: Array) -> Dictionary:
    var sizes: Dictionary = {}
    for scale: float in scales:
        var size := Vector2i((base_size * scale).round()).clamp(Vector2i.ONE,image.get_size())
        if not sizes.has(size) and size != image.get_size():
            sizes[size] = _resample(image,size)
    return sizes

func prepare_status_sizes(gap: float, screen_scale: Vector2) -> void:
    _prepared_head_sizes.clear()
    _prepared_derived_sizes.clear()
    var scales: Array = [1.0,StatusInk.CORE_INNER[0]]
    for ring in StatusInk.BLEED:
        scales.append(ring[0])
    for head in head_images:
        var image: Image = head_images[head]
        var box: Array = bounds[head]
        var base_size := Vector2(box[2],box[3]) * (gap / 250.0) * screen_scale
        _head_size_lock.lock()
        var known: Dictionary = _last_head_sizes.get(head,{})
        _head_size_lock.unlock()
        if known.get("image") == image and known.get("size") == base_size:
            _prepared_head_sizes[head] = known["sizes"].duplicate()
            continue
        var sizes: Dictionary = _status_sizes(image,base_size,scales)
        _head_size_lock.lock()
        _last_head_sizes[head] = {"image":image,"size":base_size,"sizes":sizes}
        _head_size_lock.unlock()
        _prepared_head_sizes[head] = sizes.duplicate()
    var derived: Dictionary = _assets.derived_status_images()
    # Identical aliases share CPU images, not the mutable upload catalog.
    var prepared: Dictionary = {}
    for key in derived:
        var image: Image = derived[key][0]
        var box: Array = derived[key][1]
        var base_size := Vector2(box[2],box[3]) * (gap / 250.0) * screen_scale
        var status: bool = str(key).begins_with("cutout:") or key == "note:whole"
        var identity: String = "%d|%s|%s" % [image.get_instance_id(),str(base_size),str(status)]
        if not prepared.has(identity):
            prepared[identity] = _status_sizes(image,base_size,scales if status else [1.0])
        _prepared_derived_sizes[key] = prepared[identity].duplicate()

func _publish_status_sizes(original: Texture2D, sizes: Dictionary) -> void:
    if original == null:
        return
    for size in sizes:
        _display_cache[_display_key(original,size)] = [weakref(original),sizes[size]]

func upload_step(budget_usec: int = 2000) -> bool:
    if not _assets.upload_step(budget_usec):
        return false
    prune_display_cache()
    for head in _prepared_head_sizes:
        _publish_status_sizes(textures[head],_prepared_head_sizes[head])
    for key in _prepared_derived_sizes:
        _publish_status_sizes(_assets.derived_status_texture(key),_prepared_derived_sizes[key])
    _prepared_head_sizes.clear()
    _prepared_derived_sizes.clear()
    return true

func source_image(art) -> Image:
    return _assets.source_image(art)

func ready() -> bool:
    return _assets.ready()

func load_font(items: Dictionary, octave_clefs: Array = Assets.OCTAVE_CLEFS) -> bool:
    return _assets.load_font(items,octave_clefs)

func note_ready() -> bool:
    return _assets.note_ready()

func load_note_templates(items: Dictionary) -> bool:
    return _assets.load_note_templates(items)

func ties_ready() -> bool:
    return _assets.ties_ready()

func load_tie_templates(items: Dictionary) -> bool:
    return _assets.load_tie_templates(items)

func load_chord_templates(items: Dictionary) -> bool:
    return _assets.load_chord_templates(items)

func load_beam_fragments(items: Dictionary) -> bool:
    return _assets.load_beam_fragments(items)

func load_tuplet_fragments(items: Dictionary) -> bool:
    return _assets.load_tuplet_fragments(items)

func load_grace_fragments(items: Dictionary) -> bool:
    return _assets.load_grace_fragments(items)

func grace_group_rect(anchor: String, head: Vector2, gap: float) -> Rect2:
    var bounds: Rect2 = _assets.grace_bounds.get(anchor, Rect2())
    return Rect2(head + bounds.position * gap / 250.0, bounds.size * gap / 250.0)

func load_slur_fragments(items: Dictionary) -> bool:
    return _assets.load_slur_fragments(items)

func _template_box(source: String, key: String) -> Array:
    return _assets.template_box(source, key)

func head_cutout(source: String, key: String, index: int, head: String) -> Texture2D:
    return _assets.head_cutout(source, key, index, head)

func install_head_interior(head: String, texture: Texture2D) -> bool:
    return _assets.install_head_interior(head, texture)

func head_interior(head: String) -> Texture2D:
    return _assets.head_interior(head)

func has_chord(key: String) -> bool:
    return chord_textures.has(key)

func paint_chord(canvas: CanvasItem, key: String,
        x: float, y: float, gap: float, ink: Color) -> bool:
    var texture: Texture2D = chord_textures.get(key)
    if texture == null:
        return false
    var box: Array = chord_metadata[key]["bounds"]
    draw_fit(canvas,texture,
        Rect2(x+float(box[0])*gap/250.0,
            y+float(box[1])*gap/250.0,
            float(box[2])*gap/250.0,
            float(box[3])*gap/250.0),false,ink)
    return true

func has_chord_heads(key: String) -> bool:
    return chord_heads_textures.has(key)

func paint_chord_heads(canvas: CanvasItem,key: String,
        x: float,y: float,gap: float,ink: Color) -> bool:
    var sprite: Texture2D = chord_heads_textures.get(key)
    if sprite == null:
        return false
    var b: Array = chord_heads_bounds[key]
    draw_fit(canvas,sprite,
        Rect2(x+float(b[0])*gap/250.0,y+float(b[1])*gap/250.0,
              float(b[2])*gap/250.0,float(b[3])*gap/250.0),false,ink)
    return true

func has_chord_stem(key: String) -> bool:
    return chord_stem_textures.has(key)

func paint_chord_stem(canvas: CanvasItem,key: String,
        x: float,anchor_y: float,tip_y: float,gap: float,ink: Color) -> bool:
    var source: Texture2D = chord_stem_textures.get(key)
    if source == null or absf(anchor_y-tip_y)<1.0:
        return false
    var bounds: Array = chord_stem_bounds[key]
    var unit: float = gap/250.0
    # Keep Verovio's ORIGINAL stem width/caps/shape; change ONLY its
    # longitudinal distance to the endpoint measured on the source beam.
    draw_fit(canvas,source,Rect2(
        x+float(bounds[0])*unit,minf(anchor_y,tip_y),
        float(bounds[2])*unit,absf(anchor_y-tip_y)),false,ink)
    return true

func chord_heads(key: String) -> Array:
    if not chord_metadata.has(key):
        return []
    return chord_metadata[key]["head_positions"]

func beam_tips(name: String) -> Array:
    return beam_metadata[name]["tip_offsets"] if beam_metadata.has(name) else []

func has_tuplet(name: String, requires_bracket: bool) -> bool:
    return tuplet_textures.has(name) and (not requires_bracket or \
        tuplet_textures[name].has("bracket"))

func paint_tuplet(canvas: CanvasItem, name: String, x0: float, x1: float,
        y0: float, gap: float, ink: Color) -> bool:
    if not tuplet_textures.has(name):
        return false
    var info: Dictionary = tuplet_metadata[name]
    var textures: Dictionary = tuplet_textures[name]
    var number: Dictionary = info["number"]
    var nb: Array = number["bounds"]
    var unit: float = gap/250.0
    if info.get("note_ids",[]).size() == 1:
        # One genuine source anchor has no endpoint interval to stretch.
        # Retain both masks' original offsets and staff-space scale.
        for kind in ["number","bracket"]:
            if textures.has(kind):
                var box: Array = info[kind]["bounds"]
                draw_fit(canvas,textures[kind],Rect2(
                    x0+float(box[0])*unit,y0+float(box[1])*unit,
                    float(box[2])*unit,float(box[3])*unit),false,ink)
        return true
    if x1 <= x0:
        return false
    var center: float = (x0+x1)*.5
    draw_fit(canvas,textures["number"],
        Rect2(center-float(nb[2])*unit*.5, y0+float(nb[1])*unit,
            float(nb[2])*unit,float(nb[3])*unit),false,ink)
    if textures.has("bracket"):
        var bracket: Dictionary = info["bracket"]
        var box: Array = bracket["bounds"]
        var source: Texture2D = textures["bracket"]
        var img_width: float = float(source.get_width())
        var img_height: float = float(source.get_height())
        # The bracket is cut at the ACTUAL source numeral centre, not at
        # half the note-attack span. Verovio can offset the numeral relative
        # to those endpoints (especially nested/uneven tuplets). Splitting at
        # span/2 cuts through a genuine bracket arm and stretches a missing
        # segment around the visible number.
        var midpoint: float = float(nb[0])+float(nb[2])*.5
        var left_pixel: float = clampf(
            (midpoint-float(box[0]))/float(box[2])*img_width,
            0.0,img_width)
        if left_pixel > .1 and left_pixel < img_width-.1:
            var left_x: float = x0+float(box[0])*unit
            var right_x: float = x1+(
                float(box[0])+float(box[2])-float(info["span"]))*unit
            var top_y: float = y0+float(box[1])*unit
            var height: float = float(box[3])*unit
            if center > left_x and right_x > center:
                draw_fit_region(canvas,source,
                    Rect2(left_x,top_y,center-left_x,height),
                    Rect2(0.0,0.0,left_pixel,img_height),ink)
                draw_fit_region(canvas,source,
                    Rect2(center,top_y,right_x-center,height),
                    Rect2(left_pixel,0.0,img_width-left_pixel,img_height),ink)
    return true

func slur_keys() -> Array:
    return slur_metadata.keys()

func slur_note_ids(name: String) -> Array:
    return slur_metadata[name].get("note_ids",[]) if \
        slur_metadata.has(name) else []

func paint_note_stem(canvas: CanvasItem, kind: String, up: bool,
        x: float, head_y: float, tip_y: float, gap: float,
        ink: Color) -> bool:
    var name: String = kind + ("_up" if up else "_down")
    var sprite: Texture2D = note_stem_textures.get(name)
    if sprite == null or absf(head_y-tip_y) <= 1.0:
        return false
    var box: Array = note_stem_bounds[name]
    var unit: float = gap/250.0
    # Verovio supplies stroke thickness, engraving caps and the X anchor.
    # Only the longitudinal distance changes to meet the real source beam.
    draw_fit(canvas,sprite,Rect2(
        x+float(box[0])*unit,minf(head_y,tip_y),
        float(box[2])*unit,absf(head_y-tip_y)),false,ink)
    return true

static func note_template_name(kind: String, up: bool) -> String:
    return "whole" if kind == "whole" else kind + ("_up" if up else "_down")

func paint_note(canvas: CanvasItem, kind: String, up: bool,
        x: float, y: float, gap: float, ink: Color) -> bool:
    var name: String = note_template_name(kind,up)
    var texture: Texture2D = note_textures.get(name)
    if texture == null:
        return false
    var box: Array = note_bounds[name]
    draw_fit(canvas,texture,
        Rect2(x+float(box[0])*gap/250.0,
            y+float(box[1])*gap/250.0,
            float(box[2])*gap/250.0,
            float(box[3])*gap/250.0), false, ink)
    return true

func paint(canvas: CanvasItem, name: String, x: float, y: float,
        space_px: float, color: Color,
        centered_x: bool = false) -> bool:
    var glyph: Texture2D = textures.get(name)
    if glyph == null:
        return false
    var box: Array = bounds[name]
    var unit: float = space_px / 250.0
    var shift_x: float = (float(box[0]) + float(box[2]) * .5) if centered_x else 0.0
    var rect := Rect2(
        x + (float(box[0]) - shift_x) * unit,
        y + float(box[1]) * unit,
        float(box[2]) * unit, float(box[3]) * unit
    )
    draw_fit(canvas,glyph, rect, false, color)
    return true

func paint_head_interior(canvas: CanvasItem, instance: Dictionary,
        color: Color) -> bool:
    var head: String = str(instance["head"])
    var texture: Texture2D = head_interior(head)
    if texture == null or not bounds.has(head):
        return false
    var box: Array = bounds[head]
    var point: Vector2 = instance["position"]
    var unit: float = float(instance["gap"])/250.0
    draw_fit(canvas,texture,Rect2(
        point.x+(float(box[0])-(float(box[0])+float(box[2])*.5))*unit,
        point.y+float(box[1])*unit,float(box[2])*unit,float(box[3])*unit),false,color)
    return true

func paint_head(canvas: CanvasItem, instance: Dictionary, color: Color,
        scale: float = 1.0) -> bool:
    var gap: float = float(instance["gap"])
    var head: String = str(instance["head"])
    var point: Vector2 = instance["position"]
    var source: String = str(instance.get("source","glyph"))
    if source == "glyph":
        return paint(canvas,head,point.x,point.y,gap*scale,color,true)
    var key: String = str(instance.get("template",""))
    # Erase, core and glow must sample the SAME original Verovio texture.
    # Using the generic head glyph for scale != 1.0 gave composite half/whole
    # notes an unrelated outline and a detached glow. The first two passes
    # remain at exactly their source rectangle; only the glow expands around
    # the actual engraved head centre without shifting its source anchor.
    var texture: Texture2D = null
    var box: Array = _template_box(source,key)
    if source == "note" and head == "head_whole" and key == "whole":
        if scale == 1.0:
            return paint_note(canvas,"whole",true,point.x,point.y,gap,color)
        texture = note_textures.get("whole")
    else:
        texture = head_cutout(source,key,int(instance.get("head_index",0)),head)
    if texture == null or box.size() != 4:
        return paint(canvas,head,point.x,point.y,gap*scale,color,true)
    var anchor: Vector2 = instance["anchor"]
    var unit: float = gap/250.0
    var top_left: Vector2 = anchor + Vector2(
        float(box[0])*unit,float(box[1])*unit)
    var original_size: Vector2 = Vector2(
        float(box[2])*unit,float(box[3])*unit)
    draw_fit(canvas,texture,Rect2(
        point + (top_left-point)*scale,original_size*scale),false,color)
    return true

static func prune_display_cache() -> void:
    for key in _display_cache.keys():
        var entry: Array = _display_cache[key]
        if entry.size() != 2 or (entry[0] as WeakRef).get_ref() == null:
            _display_cache.erase(key)

static func _display_key(texture: Texture2D, size: Vector2i) -> String:
    return "%d|%d|%d" % [texture.get_instance_id(),size.x,size.y]

static func _display_texture(texture: Texture2D, wanted: Vector2) -> Texture2D:
    var source := Vector2i(texture.get_width(),texture.get_height())
    var width: int = clampi(roundi(wanted.x),1,source.x)
    var height: int = clampi(roundi(wanted.y),1,source.y)
    if width >= source.x and height >= source.y:
        return texture
    # Instance ids are never reused while the object lives; the weak
    # reference rejects an entry whose source texture has been freed.
    var key: String = _display_key(texture,Vector2i(width,height))
    var cached: Array = _display_cache.get(key,[])
    if cached.size() == 2 and (cached[0] as WeakRef).get_ref() == texture:
        return cached[1]
    var profile: bool = OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
    var began: int = Time.get_ticks_usec() if profile else 0
    var size := Vector2i(width,height)
    var source_image: Image = texture.get_meta("verovio_cpu_image") if \
        texture.has_meta("verovio_cpu_image") else texture.get_image()
    if source_image == null or source_image.is_empty():
        return texture
    var pixels: Image = _resample(source_image,size)
    var sized := ImageTexture.create_from_image(pixels)
    _display_cache[key] = [weakref(texture),sized]
    if profile and Time.get_ticks_usec()-began >= 1000:
        print("GLYPH_DISPLAY_CACHE_MISS:",JSON.stringify({"at_ms":float(began)*.001,
            "elapsed_ms":float(Time.get_ticks_usec()-began)*.001,
            "original":[source.x,source.y],"target":[size.x,size.y]}))
    return sized

static func _resample(image: Image, size: Vector2i) -> Image:
    image = image.duplicate()
    if image.is_compressed():
        image.decompress()
    image.convert(Image.FORMAT_RGBA8)
    image.premultiply_alpha()
    image.resize(size.x,size.y,Image.INTERPOLATE_TRILINEAR)
    var data: PackedByteArray = image.get_data()
    for index in range(0,data.size(),4):
        var alpha: int = data[index+3]
        if alpha > 0 and alpha < 255:
            data[index] = mini(255,roundi(data[index]*255.0/alpha))
            data[index+1] = mini(255,roundi(data[index+1]*255.0/alpha))
            data[index+2] = mini(255,roundi(data[index+2]*255.0/alpha))
    return Image.create_from_data(size.x,size.y,false,Image.FORMAT_RGBA8,data)

static func screen_scale_for(canvas) -> Vector2:
    if not (canvas is CanvasItem) or not canvas.is_inside_tree():
        return Vector2.ONE
    var local: Vector2 = canvas.get_global_transform_with_canvas().get_scale().abs()
    var window: Vector2 = canvas.get_viewport().get_final_transform().get_scale().abs()
    var scale := local*window
    if scale.x <= 0.0 or scale.y <= 0.0 or not scale.is_finite():
        return Vector2.ONE
    return scale

static func draw_fit(canvas, texture: Texture2D, rect: Rect2,
        tile: bool, modulate: Color = Color.WHITE) -> void:
    canvas.draw_texture_rect(_display_texture(texture,
        rect.size.abs()*screen_scale_for(canvas)),rect,tile,modulate)

static func draw_fit_region(canvas, texture: Texture2D, rect: Rect2,
        source: Rect2, modulate: Color = Color.WHITE) -> void:
    if source.size.x <= 0.0 or source.size.y <= 0.0:
        canvas.draw_texture_rect_region(texture,rect,source,modulate)
        return
    var full := Vector2(texture.get_width(),texture.get_height())
    var sized: Texture2D = _display_texture(texture,
        full*(rect.size.abs()*screen_scale_for(canvas)/source.size))
    var ratio := Vector2(sized.get_width(),sized.get_height())/full
    canvas.draw_texture_rect_region(sized,rect,
        Rect2(source.position*ratio,source.size*ratio),modulate)
