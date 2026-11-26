extends RefCounted
# Derives status-ink masks from explicit original Verovio images/geometry.
# Owns only derived mask caches, with invalidation at catalog replacement.
const HEAD_CUTOUT_MARGIN := 12.0
var _head_cutouts: Dictionary = {}
var _head_interiors: Dictionary = {}

func clear_heads() -> void:
    _head_cutouts.clear()
    _head_interiors.clear()

func clear_templates() -> void:
    _head_cutouts.clear()

func cutout(source: String, key: String, index: int, head: String,
        template: Image, glyph: Image, box: Array, glyph_box: Array,
        positions: Array) -> Texture2D:
    var cache_key: String = "%s|%s|%d|%s" % [source,key,index,head]
    if _head_cutouts.has(cache_key):
        return _head_cutouts[cache_key]
    var cutout: Texture2D = null
    var offset := Vector2.ZERO
    if source != "note":
        if index >= 0 and index < positions.size():
            offset = Vector2(float(positions[index][0]),float(positions[index][1]))
        else:
            template = null
    if template != null and glyph != null and box.size() == 4 and glyph_box.size() == 4:
        var sx: float = template.get_width()/float(box[2])
        var sy: float = template.get_height()/float(box[3])
        # Head glyph rectangle in template texels (heads are drawn centred).
        var gw: int = maxi(1,roundi(float(glyph_box[2])*sx))
        var gh: int = maxi(1,roundi(float(glyph_box[3])*sy))
        var origin := Vector2i(
            roundi((offset.x-float(glyph_box[2])*.5-float(box[0]))*sx),
            roundi((offset.y+float(glyph_box[1])-float(box[1]))*sy))
        var stamp: Image = glyph.duplicate()
        stamp.convert(Image.FORMAT_RGBA8)
        stamp.resize(gw,gh,Image.INTERPOLATE_BILINEAR)
        var mask := Image.create_empty(template.get_width(),template.get_height(),
            false,Image.FORMAT_RGBA8)
        var radius: int = maxi(1,ceili(HEAD_CUTOUT_MARGIN*maxf(sx,sy)))
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                if dx*dx+dy*dy <= radius*radius:
                    mask.blend_rect(stamp,Rect2i(Vector2i.ZERO,stamp.get_size()),
                        origin+Vector2i(dx,dy))
        if source != "note":
            # Chord members touch. Partition the artwork at the mid-line to
            # each neighbour (the same rounded line from both sides), so every
            # texel belongs to exactly one head and is never recolored twice.
            var transparent := Color(0,0,0,0)
            var w: int = template.get_width()
            var h: int = template.get_height()
            for other in range(positions.size()):
                if other == index:
                    continue
                var dx_units: float = float(positions[other][0])-offset.x
                var dy_units: float = float(positions[other][1])-offset.y
                if absf(dy_units) >= absf(dx_units):
                    var mid: int = roundi(((offset.y+float(positions[other][1]))*.5-
                        float(box[1]))*sy)
                    if dy_units > 0.0:
                        mask.fill_rect(Rect2i(0,mid,w,maxi(0,h-mid)),transparent)
                    else:
                        mask.fill_rect(Rect2i(0,0,w,clampi(mid,0,h)),transparent)
                else:
                    var mid_x: int = roundi(((offset.x+float(positions[other][0]))*.5-
                        float(box[0]))*sx)
                    if dx_units > 0.0:
                        mask.fill_rect(Rect2i(mid_x,0,maxi(0,w-mid_x),h),transparent)
                    else:
                        mask.fill_rect(Rect2i(0,0,clampi(mid_x,0,w),h),transparent)
        var head_only := Image.create_empty(template.get_width(),
            template.get_height(),false,template.get_format())
        head_only.blit_rect_mask(template,mask,
            Rect2i(Vector2i.ZERO,template.get_size()),Vector2i.ZERO)
        cutout = ImageTexture.create_from_image(head_only)
        cutout.set_meta("verovio_cpu_image",head_only)
    _head_cutouts[cache_key] = cutout
    return cutout

func install_interior(head: String, texture: Texture2D) -> bool:
    # Null is the valid computed result for a solid head.
    _head_interiors[head] = texture
    return true

func interior(head: String, glyph: Image) -> Texture2D:
    if not _head_interiors.has(head):
        var image: Image = interior_image(glyph)
        _head_interiors[head] = ImageTexture.create_from_image(image) if image != null else null
    return _head_interiors[head]

static func interior_image(glyph: Image) -> Image:
    if glyph != null and not glyph.is_empty():
        var image: Image = glyph.duplicate()
        image.convert(Image.FORMAT_RGBA8)
        var w: int = image.get_width()
        var h: int = image.get_height()
        var outside := PackedByteArray()
        outside.resize(w*h)
        var stack: Array[Vector2i] = []
        for x in range(w):
            stack.append(Vector2i(x,0))
            stack.append(Vector2i(x,h-1))
        for y in range(h):
            stack.append(Vector2i(0,y))
            stack.append(Vector2i(w-1,y))
        while not stack.is_empty():
            var at: Vector2i = stack.pop_back()
            if at.x < 0 or at.y < 0 or at.x >= w or at.y >= h or \
                    outside[at.y*w+at.x] != 0 or image.get_pixel(at.x,at.y).a >= .5:
                continue
            outside[at.y*w+at.x] = 1
            stack.append(Vector2i(at.x+1,at.y))
            stack.append(Vector2i(at.x-1,at.y))
            stack.append(Vector2i(at.x,at.y+1))
            stack.append(Vector2i(at.x,at.y-1))
        var interior := Image.create_empty(w,h,false,Image.FORMAT_RGBA8)
        var enclosed := 0
        for y in range(h):
            for x in range(w):
                var a: float = image.get_pixel(x,y).a
                if outside[y*w+x] == 0 and a < .5:
                    interior.set_pixel(x,y,Color(1,1,1,1.0-a))
                    enclosed += 1
        if enclosed > 0:
            return interior
    return null
