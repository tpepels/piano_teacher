extends RefCounted
# Authenticated Verovio Leipzig / Bravura font artwork, drawn by Godot.
#
# This class deliberately does NOT generate SVG, music glyph paths, fonts or
# score pages. The Python engine exports each *single glyph* from Verovio's
# installed font resources, including precise origin and bounds. Godot
# imports it once as a cached ImageTexture and composes/scrolls the score
# natively using ScoreTimeline. No rendered page is moved or sliced here.

const REQUIRED := [
    "brace",
    "clef_g", "clef_f", "clef_c",
    "clef_g_8vb", "clef_g_8va", "clef_g_15mb", "clef_g_15ma",
    "clef_f_8vb", "clef_f_8va", "clef_f_15mb", "clef_f_15ma",
    "clef_c_8vb",
    "head_whole", "head_half", "head_black", "augmentation_dot",
    "repeat_dot",
    "dynamic_p", "dynamic_pp", "dynamic_ppp", "dynamic_mp", "dynamic_mf",
    "dynamic_f", "dynamic_ff", "dynamic_fff",
    "artic_staccato_above", "artic_staccato_below",
    "artic_tenuto_above", "artic_tenuto_below",
    "artic_accent_above", "artic_accent_below",
    "pedal_start", "pedal_stop",
    "rest_whole", "rest_half", "rest_quarter", "rest_eighth",
    "rest_16th", "rest_32nd", "rest_64th", "rest_128th",
    "acc_flat", "acc_natural", "acc_sharp",
    "acc_double_sharp", "acc_double_flat",
    "flag_up_1", "flag_down_1", "flag_up_2", "flag_down_2",
    "flag_up_3", "flag_down_3", "flag_up_4", "flag_down_4", "flag_up_5", "flag_down_5",
    "time_0", "time_1", "time_2", "time_3", "time_4",
    "time_5", "time_6", "time_7", "time_8", "time_9",
]
const RASTER_SCALE := 1.75
# Noteheads, stems and flags rendered together by Verovio, not assembled
# from native primitives at draw time. Beamed/chorded groups remain structural.
const NOTE_TEMPLATES := [
    "whole", "half_up", "half_down",
    "quarter_up", "quarter_down",
    "eighth_up", "eighth_down",
    "16th_up", "16th_down",
    "32nd_up", "32nd_down",
    "64th_up", "64th_down", "128th_up", "128th_down",
]

var textures: Dictionary = {}
var bounds: Dictionary = {}
var font_name := ""
var note_textures: Dictionary = {}
var note_bounds: Dictionary = {}
var note_stem_textures: Dictionary = {}
var note_stem_bounds: Dictionary = {}
var tie_textures: Dictionary = {}
var tie_metadata: Dictionary = {}
var chord_textures: Dictionary = {}
var chord_metadata: Dictionary = {}
var chord_heads_textures: Dictionary = {}
var chord_heads_bounds: Dictionary = {}
var chord_stem_textures: Dictionary = {}
var chord_stem_bounds: Dictionary = {}
# Leader id -> {"key", "heads" (member ids in template note order), "stem"}.
# An instance template engraves exactly one source chord shape; its heads
# bind to events by Verovio note element order, never by re-sorting.
var chord_instances: Dictionary = {}
var beam_textures: Dictionary = {}
var beam_metadata: Dictionary = {}
var tuplet_textures: Dictionary = {}
var tuplet_metadata: Dictionary = {}
var slur_textures: Dictionary = {}
var slur_metadata: Dictionary = {}
var error := ""
# CPU copies of the authentic artwork that status ink must reproduce exactly:
# the three notehead glyphs and every composite note/chord template.
var head_images: Dictionary = {}
var template_images: Dictionary = {}
var _head_cutouts: Dictionary = {}
var _head_interiors: Dictionary = {}
# A cutout keeps the template's own texels within this distance (font units,
# 250 per staff space) of the notehead outline: the full antialiased head,
# never more than ~0.05 space of an attached stem.
const HEAD_CUTOUT_MARGIN := 12.0

# name|svg hash|scale -> [Image, ImageTexture]: shared by every renderer.
static var _font_raster_cache: Dictionary = {}

func ready() -> bool:
    return textures.size() == REQUIRED.size()

func load_font(items: Dictionary) -> bool:
    if ready():
        return true
    # head_images is replaced below; cutouts derived from the old ones are stale.
    _head_cutouts.clear()
    _head_interiors.clear()
    var loaded_textures: Dictionary = {}
    var loaded_bounds: Dictionary = {}
    var common_font := ""
    for name in REQUIRED:
        var entry: Dictionary = items.get(name, {})
        if str(entry.get("source", "")) != "verovio":
            error = "Missing authentic Verovio glyph: " + name
            return false
        if int(entry.get("units_per_space", 0)) != 250:
            error = "Incorrect Verovio staff-scale for " + name
            return false
        var source_font: String = str(entry.get("font", ""))
        if source_font.is_empty() or (not common_font.is_empty() and common_font != source_font):
            error = "Mixed or unknown Verovio fonts"
            return false
        common_font = source_font
        var geometry: Array = entry.get("bounds", [])
        if geometry.size() != 4 or float(geometry[2]) <= 0.0 or float(geometry[3]) <= 0.0:
            error = "Invalid engraved glyph bounds for " + name
            return false
        var svg: String = str(entry.get("svg", ""))
        if not svg.contains("<svg") or not svg.contains("<path"):
            error = "Missing original font outline for " + name
            return false
        # Every stage engraves the same font: a symbol rasterized once is
        # shared (immutable Image and texture) by every later renderer. A
        # stage handoff built a new renderer inside the next take's count-in,
        # and re-rasterizing all ~67 SVG symbols cost ~130 ms on the main
        # thread there (F1 round 4, handoff stalls).
        var cache_key: String = "%s|%d|%s" % [name,hash(svg),str(RASTER_SCALE)]
        var cached: Array = _font_raster_cache.get(cache_key,[])
        var image: Image
        if cached.size() == 2:
            image = cached[0]
            loaded_textures[name] = cached[1]
        else:
            image = Image.new()
            if image.load_svg_from_buffer(svg.to_utf8_buffer(), RASTER_SCALE) != OK:
                error = "Godot cannot rasterize Verovio symbol " + name
                return false
            if image.is_empty():
                error = "Empty Verovio symbol " + name
                return false
            if name == "brace":
                # The font's E000 outline is a hairline once stretched over a
                # grand staff. Verovio itself engraves the system brace as one
                # bold FILLED curve, so build that shape (see brace_image).
                image = brace_image()
            loaded_textures[name] = ImageTexture.create_from_image(image)
            _font_raster_cache[cache_key] = [image,loaded_textures[name]]
        loaded_bounds[name] = geometry.duplicate()
        if name.begins_with("head_"):
            head_images[name] = image
    textures = loaded_textures
    bounds = loaded_bounds
    font_name = common_font
    error = ""
    return true

## Bold filled grand-staff brace, like Verovio's own: a tip at each end on the
## right, the widest strokes in the outer quarters and the cusp on the left in
## the middle. Drawn into a tall image (the view stretches it over the system);
## rows are antialiased by supersampling, the shape is symmetric about the
## middle row.
const BRACE_SIZE := Vector2i(96,1024)
const BRACE_OVERSAMPLE := 4

static func brace_profile(t: float, width: float) -> Vector2:
    var u: float = 2.0*minf(t,1.0-t)  # 0 at the tips, 1 at the cusp
    var centre: float
    if u < 0.38:
        centre = 0.90-0.26*(1.0-pow(1.0-u/0.38,2.0))
    elif u < 0.78:
        centre = 0.64-0.06*(u-0.38)/0.40
    else:
        centre = 0.58*(1.0-pow((u-0.78)/0.22,1.7))
    var thick: float = 0.05+0.40*pow(sin(PI*clampf(u/0.95,0.0,1.0)),1.0)
    return Vector2((centre-thick*.5)*width,(centre+thick*.5)*width)

static func brace_image() -> Image:
    var w: int = BRACE_SIZE.x
    var h: int = BRACE_SIZE.y
    var coverage := PackedFloat32Array()
    coverage.resize(w)
    var image := Image.create_empty(w,h,false,Image.FORMAT_RGBA8)
    for y in range(h):
        coverage.fill(0.0)
        for sub in range(BRACE_OVERSAMPLE):
            var span: Vector2 = brace_profile(
                (float(y)+(float(sub)+.5)/float(BRACE_OVERSAMPLE))/float(h),float(w))
            for x in range(maxi(0,floori(span.x)),mini(w,ceili(span.y))):
                var covered: float = minf(float(x+1),span.y)-maxf(float(x),span.x)
                coverage[x] += maxf(0.0,covered)/float(BRACE_OVERSAMPLE)
        for x in range(w):
            if coverage[x] > 0.0:
                image.set_pixel(x,y,Color(1,1,1,minf(1.0,coverage[x])))
    return image


func note_ready() -> bool:
    return note_textures.size() == NOTE_TEMPLATES.size() and \
        note_stem_textures.size() == NOTE_TEMPLATES.size()-1


func load_note_templates(items: Dictionary) -> bool:
    if note_ready():
        return true
    var new_textures: Dictionary = {}
    var new_bounds: Dictionary = {}
    var stems: Dictionary = {}
    var stem_boxes: Dictionary = {}
    _forget_template_images("note:")
    for name in NOTE_TEMPLATES:
        var item: Dictionary = items.get(name, {})
        if str(item.get("source", "")) != "verovio-engraved-note" or \
                int(item.get("units_per_space", 0)) != 250:
            error = "Missing Verovio-engraved complete note " + name
            return false
        var coordinates: Array = item.get("bounds", [])
        if coordinates.size() != 4 or float(coordinates[2]) <= 0.0 or \
                float(coordinates[3]) <= 0.0:
            error = "Invalid Verovio note dimensions: " + name
            return false
        var encoded: String = str(item.get("png_base64", ""))
        if encoded.is_empty():
            error = "Missing Verovio note image: " + name
            return false
        var bytes: PackedByteArray = Marshalls.base64_to_raw(encoded)
        var note := Image.new()
        if note.load_png_from_buffer(bytes) != OK or note.is_empty():
            error = "Invalid authentic Verovio note image: " + name
            return false
        new_textures[name] = ImageTexture.create_from_image(note)
        new_bounds[name] = coordinates.duplicate()
        template_images["note:"+name] = note
        if name != "whole":
            var stem: Dictionary = item.get("stem_only",{})
            var box: Array = stem.get("bounds",[])
            if str(stem.get("source","")) != "verovio-engraved-note-stem" or \
                    int(stem.get("units_per_space",0)) != 250 or \
                    box.size() != 4 or float(box[2]) <= 0.0 or \
                    float(box[3]) <= 0.0:
                error = "Missing original Verovio stem for "+name
                return false
            var stem_image := Image.new()
            if stem_image.load_png_from_buffer(Marshalls.base64_to_raw(
                    str(stem.get("png_base64","")))) != OK or \
                    stem_image.is_empty():
                error = "Invalid original Verovio stem for "+name
                return false
            stems[name] = ImageTexture.create_from_image(stem_image)
            stem_boxes[name] = box.duplicate()
    note_textures = new_textures
    note_bounds = new_bounds
    note_stem_textures = stems
    note_stem_bounds = stem_boxes
    error = ""
    return true


func ties_ready() -> bool:
    return tie_textures.has("up") and tie_textures.has("down")


func load_tie_templates(items: Dictionary) -> bool:
    if ties_ready() and tie_textures.size()==items.size():
        return true
    if not items.has("up") or not items.has("down"):
        error = "Missing genuine Verovio tie contours"
        return false
    var atlas := {}
    var metrics := {}
    for direction in items:
        var item: Dictionary = items.get(direction,{})
        var dimensions: Array = item.get("bounds",[])
        if str(item.get("source","")) != "verovio-engraved-tie" or \
                int(item.get("units_per_space",0)) != 250 or \
                dimensions.size() != 4 or float(item.get("span",0.0)) <= 0.0:
            error = "Missing genuine Verovio tie contour: " + direction
            return false
        var img := Image.new()
        if img.load_png_from_buffer(Marshalls.base64_to_raw(
                str(item.get("png_base64","")))) != OK or img.is_empty():
            error = "Invalid genuine Verovio tie image: " + direction
            return false
        atlas[direction] = ImageTexture.create_from_image(img)
        metrics[direction] = {"bounds":dimensions.duplicate(),
            "span":float(item["span"])}
        for field in ["head_centers","head_widths"]:
            if item.has(field):
                var values: Variant = item[field]
                if not values is Array or values.size()!=2:
                    error = "Invalid source tie head metrics: "+str(direction)
                    return false
                for value in values:
                    if typeof(value) not in [TYPE_INT,TYPE_FLOAT] or not is_finite(float(value)) or \
                            (field=="head_widths" and float(value)<=0.0):
                        error = "Invalid source tie head metrics: "+str(direction)
                        return false
                metrics[direction][field] = values.duplicate()
    tie_textures = atlas
    tie_metadata = metrics
    return true


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
    canvas.draw_texture_rect(texture,dest,false,ink)
    return true


func load_chord_templates(items: Dictionary) -> bool:
    # One Verovio instance template per chord shape of the score. Positions
    # and bounds are relative to the lowest head (template note 0); each
    # chord is re-anchored here on its leader, the event the painter places.
    # Never substitute fake sprite ink.
    _forget_template_images("chord")
    var loaded := {}
    var metrics := {}
    var loaded_heads: Dictionary = {}
    var heads_dimensions: Dictionary = {}
    var loaded_stems: Dictionary = {}
    var stem_dimensions: Dictionary = {}
    var instances: Dictionary = {}
    for key in items:
        var item: Dictionary = items[key]
        var bounds: Array = item.get("bounds",[])
        var positions: Array = item.get("head_positions",[])
        if str(item.get("source","")) != "verovio-engraved-chord" or \
                int(item.get("units_per_space",0)) != 250 or \
                bounds.size() != 4 or positions.size() < 2:
            error = "Invalid Verovio chord sprite: " + str(key)
            return false
        if not item.get("leaders",{}) is Dictionary:
            error = "Invalid Verovio chord leaders: " + str(key)
            return false
        # The stem Verovio engraved the chord with; a whole chord's virtual one.
        if str(item.get("stem","")) not in ["up","down"]:
            error = "Verovio chord template has no stem direction: " + str(key)
            return false
        var img := Image.new()
        if img.load_png_from_buffer(Marshalls.base64_to_raw(
                str(item.get("png_base64","")))) != OK or img.is_empty():
            error = "Unreadable Verovio chord sprite: " + str(key)
            return false
        loaded[str(key)] = ImageTexture.create_from_image(img)
        template_images["chord:"+str(key)] = img
        metrics[str(key)] = {
            "bounds":bounds.duplicate(), "head_positions":positions.duplicate(true)}
        var heads: Dictionary = item.get("heads_only",{})
        if str(heads.get("source","")) == "verovio-engraved-chord-heads" and \
                heads.get("bounds",[]).size() == 4:
            var heads_image := Image.new()
            if heads_image.load_png_from_buffer(Marshalls.base64_to_raw(
                    str(heads.get("png_base64","")))) != OK or \
                    heads_image.is_empty():
                error = "Invalid Verovio compound heads: "+str(key)
                return false
            loaded_heads[str(key)] = ImageTexture.create_from_image(heads_image)
            heads_dimensions[str(key)] = heads["bounds"]
            template_images["chord_heads:"+str(key)] = heads_image
        var stem: Dictionary = item.get("stem_only",{})
        if str(stem.get("source","")) == "verovio-engraved-chord-stem" and \
                stem.get("bounds",[]).size() == 4:
            var stem_image := Image.new()
            if stem_image.load_png_from_buffer(Marshalls.base64_to_raw(
                    str(stem.get("png_base64","")))) != OK or \
                    stem_image.is_empty():
                error = "Invalid original Verovio compound stem: "+str(key)
                return false
            loaded_stems[str(key)] = ImageTexture.create_from_image(stem_image)
            stem_dimensions[str(key)] = stem["bounds"]
    for key in items:
        var positions: Array = metrics[str(key)]["head_positions"]
        var leaders: Dictionary = items[key].get("leaders",{})
        for leader in leaders:
            var heads: Variant = leaders[leader]
            if not heads is Array or heads.size() != positions.size():
                error = "Verovio chord heads do not match its template: " + str(key)
                return false
            var ids: Array = []
            for id in heads:
                ids.append(str(id))
            var anchor: int = ids.find(str(leader))
            if anchor < 0:
                error = "Verovio chord leader is not one of its heads: " + str(leader)
                return false
            var used: String = str(key)
            if anchor > 0:
                used = "%s|a%d" % [key, anchor]
                if not metrics.has(used):
                    var origin := Vector2(float(positions[anchor][0]),float(positions[anchor][1]))
                    var shifted: Array = []
                    for position in positions:
                        shifted.append([float(position[0])-origin.x,float(position[1])-origin.y])
                    metrics[used] = {"bounds":_shifted(metrics[str(key)]["bounds"],origin),
                        "head_positions":shifted}
                    loaded[used] = loaded[str(key)]
                    template_images["chord:"+used] = template_images["chord:"+str(key)]
                    if loaded_heads.has(str(key)):
                        loaded_heads[used] = loaded_heads[str(key)]
                        heads_dimensions[used] = _shifted(heads_dimensions[str(key)],origin)
                        template_images["chord_heads:"+used] = template_images["chord_heads:"+str(key)]
                    if loaded_stems.has(str(key)):
                        loaded_stems[used] = loaded_stems[str(key)]
                        stem_dimensions[used] = _shifted(stem_dimensions[str(key)],origin)
            instances[str(leader)] = {"key":used, "heads":ids,
                "stem":str(items[key]["stem"])}
    chord_textures = loaded
    chord_metadata = metrics
    chord_heads_textures = loaded_heads
    chord_heads_bounds = heads_dimensions
    chord_stem_textures = loaded_stems
    chord_stem_bounds = stem_dimensions
    chord_instances = instances
    return true


static func _shifted(bounds: Array, origin: Vector2) -> Array:
    return [float(bounds[0])-origin.x,float(bounds[1])-origin.y,
        float(bounds[2]),float(bounds[3])]


func has_chord(key: String) -> bool:
    return chord_textures.has(key)


func paint_chord(canvas: CanvasItem, key: String,
        x: float, y: float, gap: float, ink: Color) -> bool:
    var texture: Texture2D = chord_textures.get(key)
    if texture == null:
        return false
    var box: Array = chord_metadata[key]["bounds"]
    canvas.draw_texture_rect(texture,
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
    canvas.draw_texture_rect(sprite,
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
    canvas.draw_texture_rect(source,Rect2(
        x+float(bounds[0])*unit,minf(anchor_y,tip_y),
        float(bounds[2])*unit,absf(anchor_y-tip_y)),false,ink)
    return true


func chord_heads(key: String) -> Array:
    if not chord_metadata.has(key):
        return []
    return chord_metadata[key]["head_positions"]


func load_beam_fragments(items: Dictionary) -> bool:
    # An optional atlas extracted from THIS LESSON's actual Verovio SVG,
    # keyed by the two original note IDs. Never accept invented artwork.
    var loaded: Dictionary = {}
    var metrics: Dictionary = {}
    for name in items:
        var item: Dictionary = items[name]
        var box: Array = item.get("bounds",[])
        var anchors: Array = item.get("note_ids",[])
        var tips: Array = item.get("tip_offsets",[])
        var offsets: Array = item.get("head_offsets",[])
        if str(item.get("source","")) != "verovio-engraved-beam" or \
                int(item.get("units_per_space",0)) != 250 or \
                box.size() != 4 or anchors.size() < 2 or \
                tips.size() != anchors.size() or \
                offsets.size() != anchors.size() or \
                float(item.get("span",0.0)) <= 0:
            error = "Invalid extracted Verovio beam: "+str(name)
            return false
        var image := Image.new()
        if image.load_png_from_buffer(Marshalls.base64_to_raw(
                str(item.get("png_base64","")))) != OK or image.is_empty():
            error = "Unreadable extracted Verovio beam: "+str(name)
            return false
        loaded[str(name)] = ImageTexture.create_from_image(image)
        metrics[str(name)] = {
            "bounds":box.duplicate(), "span":float(item["span"]),
            "note_ids":anchors.duplicate(),
            "tip_offsets":tips.duplicate(),
            "head_offsets":offsets.duplicate(),
            "stem_up":bool(item.get("stem_up",true))}
    beam_textures = loaded
    beam_metadata = metrics
    return true


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
        canvas.draw_texture_rect_region(texture,
            Rect2(dst_a,base_y,dst_b-dst_a,ink_height),
            Rect2(src_a,0.0,src_b-src_a,texture_height),ink)
    # End caps are fixed-size Verovio artwork, not stretched with tempo.
    var left_width: float = clampf(float(anchors_px[0]),0.0,texture_width)
    if left_width > .01:
        var left_dst: float = left_width*gap*width/(250.0*texture_width)
        canvas.draw_texture_rect_region(texture,
            Rect2(float(heads[0])-left_dst,base_y,left_dst,ink_height),
            Rect2(0.0,0.0,left_width,texture_height),ink)
    var last_px: float = clampf(float(anchors_px[-1]),0.0,texture_width)
    if last_px < texture_width-.01:
        var last_dst: float = (texture_width-last_px)*gap*width/ \
            (250.0*texture_width)
        canvas.draw_texture_rect_region(texture,
            Rect2(float(heads[-1]),base_y,last_dst,ink_height),
            Rect2(last_px,0.0,texture_width-last_px,texture_height),ink)
    return true


func load_tuplet_fragments(items: Dictionary) -> bool:
    var prepared: Dictionary = {}
    var descriptions: Dictionary = {}
    for key in items:
        var data: Dictionary = items[key]
        var numeral: Dictionary = data.get("number",{})
        if str(data.get("source","")) != "verovio-engraved-tuplet" or \
                float(data.get("span",0.0)) <= 0.0:
            error = "Invalid Verovio tuplet group "+str(key)
            return false
        var number_img := Image.new()
        if str(numeral.get("source","")) != "verovio-tuplet-number" or \
                numeral.get("bounds",[]).size() != 4 or \
                number_img.load_png_from_buffer(Marshalls.base64_to_raw(
                    str(numeral.get("png_base64","")))) != OK:
            error = "Missing original Verovio tuplet numeral "+str(key)
            return false
        var artwork: Dictionary = {
            "number":ImageTexture.create_from_image(number_img)}
        var bracket: Variant = data.get("bracket")
        if bracket is Dictionary and not bracket.is_empty():
            var bracket_image := Image.new()
            if str(bracket.get("source","")) != "verovio-tuplet-bracket" or \
                    bracket.get("bounds",[]).size() != 4 or \
                    bracket_image.load_png_from_buffer(Marshalls.base64_to_raw(
                        str(bracket.get("png_base64","")))) != OK:
                error = "Invalid original Verovio tuplet bracket "+str(key)
                return false
            artwork["bracket"] = ImageTexture.create_from_image(bracket_image)
        prepared[str(key)] = artwork
        descriptions[str(key)] = data
    tuplet_textures = prepared
    tuplet_metadata = descriptions
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
                canvas.draw_texture_rect(textures[kind],Rect2(
                    x0+float(box[0])*unit,y0+float(box[1])*unit,
                    float(box[2])*unit,float(box[3])*unit),false,ink)
        return true
    if x1 <= x0:
        return false
    var center: float = (x0+x1)*.5
    canvas.draw_texture_rect(textures["number"],
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
                canvas.draw_texture_rect_region(source,
                    Rect2(left_x,top_y,center-left_x,height),
                    Rect2(0.0,0.0,left_pixel,img_height),ink)
                canvas.draw_texture_rect_region(source,
                    Rect2(center,top_y,right_x-center,height),
                    Rect2(left_pixel,0.0,img_width-left_pixel,img_height),ink)
    return true


func load_slur_fragments(items: Dictionary) -> bool:
    var loaded: Dictionary = {}
    var metrics: Dictionary = {}
    for name in items:
        var item: Dictionary = items[name]
        var rect: Array = item.get("bounds",[])
        var note_ids: Array = item.get("note_ids",[])
        if str(item.get("source","")) != "verovio-engraved-slur" or \
                int(item.get("units_per_space",0)) != 250 or \
                rect.size() != 4 or note_ids.size() != 2 or \
                float(item.get("span",0.0)) <= 0:
            error = "Invalid original Verovio slur "+str(name)
            return false
        var img := Image.new()
        if img.load_png_from_buffer(Marshalls.base64_to_raw(
                str(item.get("png_base64","")))) != OK or img.is_empty():
            error = "Unreadable original Verovio slur "+str(name)
            return false
        loaded[str(name)] = ImageTexture.create_from_image(img)
        metrics[str(name)] = item.duplicate(true)
    slur_textures = loaded
    slur_metadata = metrics
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
    canvas.draw_texture_rect(sprite,Rect2(
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
    canvas.draw_texture_rect(texture,
        Rect2(x+float(box[0])*gap/250.0,
            y+float(box[1])*gap/250.0,
            float(box[2])*gap/250.0,
            float(box[3])*gap/250.0), false, ink)
    return true


# x,y are a glyph's musical anchor, not the top-left of a page.
# A font-space unit is 1/250 of the current staff-space (line-to-line gap).
# The graphics below do not adjust musical X or the transport clock.
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
    canvas.draw_texture_rect(glyph, rect, false, color)
    return true


## Font-unit box [x, y, w, h] of the artwork a head was engraved with,
## relative to its paint anchor; empty when unknown.
func _template_box(source: String, key: String) -> Array:
    match source:
        "note":
            return note_bounds.get(key,[])
        "chord":
            return chord_metadata.get(key,{}).get("bounds",[])
        "chord_heads":
            return chord_heads_bounds.get(key,[])
    return []


## The exact pixels of ONE notehead inside the composite Verovio artwork it
## was engraved with: the template's own texels, kept only within a small
## margin around that head's outline (stems, flags and other chord members
## are cleared). Same size, format and texels as the template, so drawing it
## with the template's rectangle samples bit-identically for every head
## pixel. Built once per (template, head) with native Image operations.
func head_cutout(source: String, key: String, index: int, head: String) -> Texture2D:
    var cache_key: String = "%s|%s|%d|%s" % [source,key,index,head]
    if _head_cutouts.has(cache_key):
        return _head_cutouts[cache_key]
    var cutout: Texture2D = null
    var template: Image = template_images.get(source+":"+key)
    var glyph: Image = head_images.get(head)
    var box: Array = _template_box(source,key)
    var glyph_box: Array = bounds.get(head,[])
    var offset := Vector2.ZERO
    if source != "note":
        var positions: Array = chord_heads(key)
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
            var positions: Array = chord_heads(key)
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
    _head_cutouts[cache_key] = cutout
    return cutout


## Soft "interior" artwork of a hollow head (half, whole): the pixels of the
## head's own glyph that are enclosed by its outline, with the glyph's own
## antialiasing (alpha 1-a). It lives in the head glyph's own rectangle, so it
## is positioned exactly like the head and can never leave its mask region.
## null for solid heads (no enclosed region).
func head_interior(head: String) -> Texture2D:
    if _head_interiors.has(head):
        return _head_interiors[head]
    var result: Texture2D = null
    var glyph: Image = head_images.get(head)
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
            result = ImageTexture.create_from_image(interior)
    _head_interiors[head] = result
    return result


## Tint the enclosed interior of a hollow head (C5). Returns false for solid
## heads. Same anchor and scale as the head itself; never a ring or halo.
func paint_head_interior(canvas: CanvasItem, instance: Dictionary,
        color: Color) -> bool:
    var head: String = str(instance["head"])
    var texture: Texture2D = head_interior(head)
    if texture == null or not bounds.has(head):
        return false
    var box: Array = bounds[head]
    var point: Vector2 = instance["position"]
    var unit: float = float(instance["gap"])/250.0
    canvas.draw_texture_rect(texture,Rect2(
        point.x+(float(box[0])-(float(box[0])+float(box[2])*.5))*unit,
        point.y+float(box[1])*unit,float(box[2])*unit,float(box[3])*unit),false,color)
    return true


## Repaint one engraved head with ``color``: the exact template head pixels
## for composite notes/chords, or the standalone authentic head glyph when
## that is what the strip drew. ``scale`` > 1 grows the same mask around the
## head centre (glow only).
func paint_head(canvas: CanvasItem, instance: Dictionary, color: Color,
        scale: float = 1.0) -> bool:
    var gap: float = float(instance["gap"])
    var head: String = str(instance["head"])
    var point: Vector2 = instance["position"]
    var source: String = str(instance.get("source","glyph"))
    if source == "glyph" or scale != 1.0:
        return paint(canvas,head,point.x,point.y,gap*scale,color,true)
    var key: String = str(instance.get("template",""))
    var texture: Texture2D = head_cutout(source,key,int(instance.get("head_index",0)),head)
    var box: Array = _template_box(source,key)
    if texture == null or box.size() != 4:
        return paint(canvas,head,point.x,point.y,gap,color,true)
    var anchor: Vector2 = instance["anchor"]
    var unit: float = gap/250.0
    canvas.draw_texture_rect(texture,Rect2(anchor.x+float(box[0])*unit,
        anchor.y+float(box[1])*unit,float(box[2])*unit,float(box[3])*unit),false,color)
    return true


func _forget_template_images(prefix: String) -> void:
    for key in template_images.keys():
        if str(key).begins_with(prefix):
            template_images.erase(key)
    _head_cutouts.clear()
