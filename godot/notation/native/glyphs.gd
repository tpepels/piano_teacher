extends RefCounted
# Canvas composition for authenticated Verovio artwork. GlyphAssets is the
# sole asset/mask store; these established public catalog ports are read-only.
const Assets := preload("res://notation/native/glyph_assets.gd")
const REQUIRED = Assets.REQUIRED
const NOTE_TEMPLATES = Assets.NOTE_TEMPLATES
const RASTER_SCALE = Assets.RASTER_SCALE
var _assets := Assets.new()
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

func ready() -> bool:
    return _assets.ready()

func load_font(items: Dictionary) -> bool:
    return _assets.load_font(items)

static func brace_profile(t: float, width: float) -> Vector2:
    return Assets.brace_profile(t, width)

static func brace_image() -> Image:
    return Assets.brace_image()

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

func paint_tie(canvas: CanvasItem, x0: float, x1: float, y: float,
        gap: float, down: bool, ink: Color) -> bool:
    # Stretch only Verovio's original tie contour, never any notehead or
    # other notation. The endpoints remain locked to the native beat grid.
    # The requested bow faces DOWN when the note's stem points UP.
    # Atlas keys denote the SOURCE stem direction, not the bow side.
    var direction: String = "up" if down else "down"
    var texture: Texture2D = tie_textures.get(direction)
    if texture == null:
        return false
    var item: Dictionary = tie_metadata[direction]
    var span_px: float = float(item["span"])*gap/250.0
    if span_px < .001 or x1 <= x0:
        return false
    var factor: float = (x1-x0)/span_px
    var box: Array = item["bounds"]
    var dest := Rect2(x0+float(box[0])*gap/250.0*factor,
        y+float(box[1])*gap/250.0,
        float(box[2])*gap/250.0*factor,
        float(box[3])*gap/250.0)
    draw_fit(canvas,texture,dest,false,ink)
    return true

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

func has_beam(name: String, up: bool) -> bool:
    return beam_textures.has(name) and \
        bool(beam_metadata[name]["stem_up"]) == up

func beam_tips(name: String) -> Array:
    return beam_metadata[name]["tip_offsets"] if beam_metadata.has(name) else []

func paint_beam(canvas: CanvasItem, name: String,
        heads: Array, y0: float, gap: float, ink: Color,
        source_offsets: Array = []) -> bool:
    var texture: Texture2D = beam_textures.get(name)
    if texture == null or heads.size() < 2:
        return false
    var data: Dictionary = beam_metadata[name]
    var offsets: Array = source_offsets if not source_offsets.is_empty() else data["head_offsets"]
    if offsets.size() != heads.size():
        return false
    var box: Array = data["bounds"]
    var width: float = float(box[2])
    if width <= 0.0:
        return false
    var texture_width: float = float(texture.get_width())
    var texture_height: float = float(texture.get_height())
    var pixel_per_unit: float = texture_width/width
    var base_y: float = y0+float(box[1])*gap/250.0
    var ink_height: float = float(box[3])*gap/250.0
    # Piecewise affine X mapping between measured source/native stem
    # attachments, not the bounding box or just the first/last notehead.
    # The original beam contours and their vertical thickness stay intact.
    var anchors_px: Array = []
    for offset in offsets:
        anchors_px.append((float(offset)-float(box[0]))*pixel_per_unit)
    for i in range(heads.size()-1):
        var original_a: float = float(anchors_px[i])
        var original_b: float = float(anchors_px[i+1])
        if original_b <= original_a+.01 or \
                float(heads[i+1]) <= float(heads[i]):
            return false
        var src_a: float = clampf(original_a,0.0,texture_width)
        var src_b: float = clampf(original_b,0.0,texture_width)
        if src_b <= src_a:
            continue
        var t0: float = (src_a-original_a)/(original_b-original_a)
        var t1: float = (src_b-original_a)/(original_b-original_a)
        var dst_a: float = lerpf(float(heads[i]),float(heads[i+1]),t0)
        var dst_b: float = lerpf(float(heads[i]),float(heads[i+1]),t1)
        draw_fit_region(canvas,texture,
            Rect2(dst_a,base_y,dst_b-dst_a,ink_height),
            Rect2(src_a,0.0,src_b-src_a,texture_height),ink)
    # End caps are fixed-size Verovio artwork, not stretched with tempo.
    var left_width: float = clampf(float(anchors_px[0]),0.0,texture_width)
    if left_width > .01:
        var left_dst: float = left_width*gap*width/(250.0*texture_width)
        draw_fit_region(canvas,texture,
            Rect2(float(heads[0])-left_dst,base_y,left_dst,ink_height),
            Rect2(0.0,0.0,left_width,texture_height),ink)
    var last_px: float = clampf(float(anchors_px[-1]),0.0,texture_width)
    if last_px < texture_width-.01:
        var last_dst: float = (texture_width-last_px)*gap*width/ \
            (250.0*texture_width)
        draw_fit_region(canvas,texture,
            Rect2(float(heads[-1]),base_y,last_dst,ink_height),
            Rect2(last_px,0.0,texture_width-last_px,texture_height),ink)
    return true

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

func paint_slur(canvas: CanvasItem, name: String,
        x0: float, y0: float, x1: float, y1: float,
        gap: float, ink: Color) -> bool:
    var tex: Texture2D = slur_textures.get(name)
    if tex == null or x1<=x0:
        return false
    var data: Dictionary = slur_metadata[name]
    var span: float = float(data["span"])
    if span <= 0.0:
        return false
    var b: Array = data["bounds"]
    var units: float = gap/250.0
    var change: float = (y1-y0)-float(data.get("original_end_y",0.0))*units
    var xx0: float = x0+float(b[0])*(x1-x0)/span
    var xx1: float = x0+(float(b[0])+float(b[2]))*(x1-x0)/span
    var top: float = y0+float(b[1])*units
    var bottom: float = top+float(b[3])*units
    var left_shift: float = change*float(b[0])/span
    var right_shift: float = change*(float(b[0])+float(b[2]))/span
    # Apply an affine transform to Verovio's ORIGINAL slur texture:
    # x is anchored to the two musical beats, y slopes towards each
    # actual pitch. No polygonal approximation of a music symbol occurs.
    canvas.draw_polygon(PackedVector2Array([
        Vector2(xx0,top+left_shift),
        Vector2(xx1,top+right_shift),
        Vector2(xx1,bottom+right_shift),
        Vector2(xx0,bottom+left_shift)]),
        PackedColorArray([ink,ink,ink,ink]),
        PackedVector2Array([Vector2.ZERO,Vector2(1.0,0.0),
            Vector2.ONE,Vector2(0.0,1.0)]),tex)
    return true

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

static var _display_cache: Dictionary = {}

static func _display_texture(texture: Texture2D, wanted: Vector2) -> Texture2D:
    var source := Vector2i(texture.get_width(),texture.get_height())
    var width: int = clampi(roundi(wanted.x),1,source.x)
    var height: int = clampi(roundi(wanted.y),1,source.y)
    if width >= source.x and height >= source.y:
        return texture
    # Instance ids are never reused while the object lives; the weak
    # reference rejects an entry whose source texture has been freed.
    var key: String = "%d|%d|%d" % [texture.get_instance_id(),width,height]
    var cached: Array = _display_cache.get(key,[])
    if cached.size() == 2 and (cached[0] as WeakRef).get_ref() == texture:
        return cached[1]
    var image: Image = texture.get_image()
    if image == null or image.is_empty():
        return texture
    image = image.duplicate()
    if image.is_compressed():
        image.decompress()
    image.convert(Image.FORMAT_RGBA8)
    image.premultiply_alpha()
    image.resize(width,height,Image.INTERPOLATE_TRILINEAR)
    var data: PackedByteArray = image.get_data()
    for index in range(0,data.size(),4):
        var alpha: int = data[index+3]
        if alpha > 0 and alpha < 255:
            data[index] = mini(255,roundi(data[index]*255.0/alpha))
            data[index+1] = mini(255,roundi(data[index+1]*255.0/alpha))
            data[index+2] = mini(255,roundi(data[index+2]*255.0/alpha))
    var sized := ImageTexture.create_from_image(
        Image.create_from_data(width,height,false,Image.FORMAT_RGBA8,data))
    _display_cache[key] = [weakref(texture),sized]
    return sized

static func _screen_scale(canvas) -> Vector2:
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
        rect.size.abs()*_screen_scale(canvas)),rect,tile,modulate)

static func draw_fit_region(canvas, texture: Texture2D, rect: Rect2,
        source: Rect2, modulate: Color = Color.WHITE) -> void:
    if source.size.x <= 0.0 or source.size.y <= 0.0:
        canvas.draw_texture_rect_region(texture,rect,source,modulate)
        return
    var full := Vector2(texture.get_width(),texture.get_height())
    var sized: Texture2D = _display_texture(texture,
        full*(rect.size.abs()*_screen_scale(canvas)/source.size))
    var ratio := Vector2(sized.get_width(),sized.get_height())/full
    canvas.draw_texture_rect_region(sized,rect,
        Rect2(source.position*ratio,source.size*ratio),modulate)
