extends RefCounted
# Authenticated Verovio font/template catalog and source raster lifecycle.
# This owner has no canvas or renderer reference; loading and derived masks
# always use the same source images and geometry.
#
# This class deliberately does NOT generate SVG, music glyph paths, fonts or
# score pages. The Python engine exports each *single glyph* from Verovio's
# installed font resources, including precise origin and bounds. Godot
# imports it once as a cached ImageTexture and composes/scrolls the score
# natively using ScoreTimeline. No rendered page is moved or sliced here.

const REQUIRED := [
    "brace",
    "clef_g", "clef_f", "clef_c",
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
    "time_0", "time_1", "time_2", "time_3", "time_4",
    "time_5", "time_6", "time_7", "time_8", "time_9",
]
const OCTAVE_CLEFS := [
    "clef_g_8vb", "clef_g_8va", "clef_g_15mb", "clef_g_15ma",
    "clef_f_8vb", "clef_f_8va", "clef_f_15mb", "clef_f_15ma",
    "clef_c_8vb",
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
const GRACE_TEMPLATES := [
    "grace_slash_eighth_up", "grace_slash_eighth_down",
    "grace_slash_16th_up", "grace_slash_16th_down",
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
var grace_textures: Dictionary = {}
var grace_bounds: Dictionary = {}
var slur_textures: Dictionary = {}
var slur_metadata: Dictionary = {}
var error := ""
# CPU copies of the authentic artwork that status ink must reproduce exactly:
# the three notehead glyphs and every composite note/chord template.
var head_images: Dictionary = {}
var template_images: Dictionary = {}
const HeadMasks := preload("res://notation/native/glyph_head_masks.gd")
var _head_masks := HeadMasks.new()

# name|svg hash|scale -> ImageTexture, shared by every renderer.
static var _font_raster_cache: Dictionary = {}
# Worker jobs share immutable CPU font images, never GPU resources.
static var _font_images: Dictionary = {}
static var _font_image_lock := Mutex.new()
var _font_keys: Dictionary = {}
var _upload_queue: Array = []
var _upload_index := 0
var _uploaded_images: Dictionary = {}
var _prepared_interiors: Dictionary = {}
# Identical font images are shared across jobs and immutable.
static var _interior_images: Dictionary = {}
static var _interior_image_lock := Mutex.new()

func prepare_head_interiors() -> void:
    _prepared_interiors.clear()
    for head in head_images:
        var image: Image = head_images[head]
        var key: String = _font_keys[head]
        _interior_image_lock.lock()
        var known: bool = _interior_images.has(key)
        var interior: Image = _interior_images.get(key)
        _interior_image_lock.unlock()
        if not known:
            interior = HeadMasks.interior_image(image)
            _interior_image_lock.lock()
            if _interior_images.has(key):
                interior = _interior_images[key]
            else:
                _interior_images[key] = interior
            _interior_image_lock.unlock()
        _prepared_interiors[head] = interior

func _remember_source(texture: Texture2D, image: Image) -> void:
    # No GPU readback is needed to resize or inspect authentic pixels.
    texture.set_meta("verovio_cpu_image",image)

func source_image(art) -> Image:
    if art is Image:
        return art
    return art.get_meta("verovio_cpu_image") if art.has_meta("verovio_cpu_image") else null

func rewind_upload() -> void:
    # A new viewport needs a different fit. Give the worker back only CPU
    # images. All of the original PNG/SVG rasterization remains reusable.
    for index in range(_upload_index):
        var item: Array = _upload_queue[index]
        var catalog: Dictionary = item[0]
        var key = item[1]
        catalog[key] = source_image(catalog[key])
    _upload_index = 0
    _uploaded_images.clear()

func begin_upload() -> void:
    # Collect CPU upload descriptors before giving ownership to the main thread.
    _upload_queue.clear()
    _upload_index = 0
    _uploaded_images.clear()
    for name in textures:
        _upload_queue.append([textures,name,_font_keys.get(name,"")])
    for head in _prepared_interiors:
        if _prepared_interiors[head] != null:
            _upload_queue.append([_prepared_interiors,head,"interior|"+str(_font_keys[head])])
    for catalog in [note_textures,note_stem_textures,tie_textures,
            chord_textures,chord_heads_textures,chord_stem_textures,
            beam_textures,slur_textures,grace_textures]:
        for key in catalog:
            _upload_queue.append([catalog,key,""])
    for key in tuplet_textures:
        var catalog: Dictionary = tuplet_textures[key]
        for part in catalog:
            _upload_queue.append([catalog,part,""])

func upload_step(budget_usec: int = 2000) -> bool:
    var deadline: int = Time.get_ticks_usec()+budget_usec
    while _upload_index < _upload_queue.size():
        var item: Array = _upload_queue[_upload_index]
        var catalog: Dictionary = item[0]
        var key = item[1]
        var font_key: String = item[2]
        var image: Image = catalog[key]
        var id: int = image.get_instance_id()
        var texture: Texture2D = _uploaded_images.get(id)
        if texture == null and not font_key.is_empty():
            texture = _font_raster_cache.get(font_key)
        if texture == null:
            texture = ImageTexture.create_from_image(image)
        if not font_key.is_empty():
            _font_raster_cache[font_key] = texture
        _uploaded_images[id] = texture
        _remember_source(texture,image)
        catalog[key] = texture
        _upload_index += 1
        if Time.get_ticks_usec() >= deadline:
            break
    if _upload_index < _upload_queue.size():
        return false
    _upload_queue.clear()
    _uploaded_images.clear()
    for head in _prepared_interiors:
        _head_masks.install_interior(str(head),_prepared_interiors[head])
    _prepared_interiors.clear()
    return true
const BRACE_SIZE := Vector2i(96,1024)
const BRACE_OVERSAMPLE := 4

func ready() -> bool:
    return not font_name.is_empty()

func load_font(items: Dictionary, octave_clefs: Array) -> bool:
    if ready() and textures.has_all(octave_clefs):
        return true
    # head_images is replaced below; cutouts derived from the old ones are stale.
    _head_masks.clear_heads()
    var loaded_textures: Dictionary = {}
    var loaded_bounds: Dictionary = {}
    var common_font := ""
    for name in REQUIRED + octave_clefs:
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
        _font_keys[name] = cache_key
        _font_image_lock.lock()
        var image: Image = _font_images.get(cache_key)
        _font_image_lock.unlock()
        if image == null:
            image = Image.new()
            if image.load_svg_from_buffer(svg.to_utf8_buffer(), RASTER_SCALE) != OK:
                error = "Godot cannot rasterize Verovio symbol " + name
                return false
            if image.is_empty():
                error = "Empty Verovio symbol " + name
                return false
            if name == "brace":
                image = brace_image()
            _font_image_lock.lock()
            if _font_images.has(cache_key):
                image = _font_images[cache_key]
            else:
                _font_images[cache_key] = image
            _font_image_lock.unlock()
        loaded_textures[name] = image
        loaded_bounds[name] = geometry.duplicate()
        if name.begins_with("head_"):
            head_images[name] = image
    textures = loaded_textures
    bounds = loaded_bounds
    font_name = common_font
    error = ""
    return true

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
    return note_textures.has_all(NOTE_TEMPLATES) and \
        note_stem_textures.size() == note_textures.size()-1

func load_note_templates(items: Dictionary) -> bool:
    var names := NOTE_TEMPLATES.duplicate()
    if items.has(GRACE_TEMPLATES[0]):
        names.append_array(GRACE_TEMPLATES)
    if note_ready() and note_textures.has_all(names):
        return true
    var new_textures: Dictionary = {}
    var new_bounds: Dictionary = {}
    var stems: Dictionary = {}
    var stem_boxes: Dictionary = {}
    _forget_template_images("note:")
    for name in names:
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
        new_textures[name] = note
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
            stems[name] = stem_image
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
        atlas[direction] = img
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
        loaded[str(key)] = img
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
            loaded_heads[str(key)] = heads_image
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
            loaded_stems[str(key)] = stem_image
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
        loaded[str(name)] = image
        metrics[str(name)] = {
            "bounds":box.duplicate(), "span":float(item["span"]),
            "note_ids":anchors.duplicate(),
            "tip_offsets":tips.duplicate(),
            "head_offsets":offsets.duplicate(),
            "stem_up":bool(item.get("stem_up",true))}
    beam_textures = loaded
    beam_metadata = metrics
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
            "number":number_img}
        var bracket: Variant = data.get("bracket")
        if bracket is Dictionary and not bracket.is_empty():
            var bracket_image := Image.new()
            if str(bracket.get("source","")) != "verovio-tuplet-bracket" or \
                    bracket.get("bounds",[]).size() != 4 or \
                    bracket_image.load_png_from_buffer(Marshalls.base64_to_raw(
                        str(bracket.get("png_base64","")))) != OK:
                error = "Invalid original Verovio tuplet bracket "+str(key)
                return false
            artwork["bracket"] = bracket_image
        prepared[str(key)] = artwork
        descriptions[str(key)] = data
    tuplet_textures = prepared
    tuplet_metadata = descriptions
    return true

func load_grace_fragments(items: Dictionary) -> bool:
    var loaded: Dictionary = {}
    var boxes: Dictionary = {}
    for anchor in items:
        var item: Dictionary = items[anchor]
        var box: Array = item.get("bounds", [])
        var image := Image.new()
        if item.get("source") != "verovio-engraved-graces" or \
                item.get("units_per_space") != 250 or box.size() != 4 or \
                image.load_png_from_buffer(Marshalls.base64_to_raw(item.get("png_base64", ""))) != OK:
            error = "Invalid Verovio grace group before " + str(anchor)
            return false
        loaded[anchor] = image
        boxes[anchor] = Rect2(box[0], box[1], box[2], box[3])
    grace_textures = loaded
    grace_bounds = boxes
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
        loaded[str(name)] = img
        metrics[str(name)] = item.duplicate(true)
    slur_textures = loaded
    slur_metadata = metrics
    return true

func template_box(source: String, key: String) -> Array:
    match source:
        "note":
            return note_bounds.get(key,[])
        "chord":
            return chord_metadata.get(key,{}).get("bounds",[])
        "chord_heads":
            return chord_heads_bounds.get(key,[])
    return []

func _forget_template_images(prefix: String) -> void:
    for key in template_images.keys():
        if str(key).begins_with(prefix):
            template_images.erase(key)
    _head_masks.clear_templates()

func chord_heads(key: String) -> Array:
    return chord_metadata.get(key,{}).get("head_positions",[])

func head_cutout(source: String, key: String, index: int, head: String) -> Texture2D:
    return _head_masks.cutout(source,key,index,head,
        template_images.get(source+":"+key),head_images.get(head),
        template_box(source,key),bounds.get(head,[]),chord_heads(key))

func install_head_interior(head: String, texture: Texture2D) -> bool:
    return head_images.has(head) and _head_masks.install_interior(head,texture)

func head_interior(head: String) -> Texture2D:
    return _head_masks.interior(head,head_images.get(head))
