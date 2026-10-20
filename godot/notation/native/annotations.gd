extends RefCounted
# Only original, identity-bound Verovio masks. Fixed glyphs/numerals retain
# their scale; span art follows the same native timeline as every source note.
# Renderer contract: timeline, play_from_beat, _staff_center(staff),
# cached_head_offsets and cached_group_offsets (already populated for gap).
# layout["native_annotation_fragments"] is produced by assets/annotations.py.

const SOURCE := "verovio-annotation"
const KINDS := ["dynamic", "dynamics", "hairpin", "wedge", "articulation", "articulations", "ornament", "ornaments", "pedal", "volta", "ending", "grace"]
const INK_MARGIN_PX := 100.0
# The native spacing solver bounds source head centres to +/-2 spaces.
# Keep an extra two spaces for attachments at the edge of the visible window.
const ATTACHMENT_MARGIN_SPACES := 4.0
var error := ""
var entries: Array = []
var frame_scanned_entries := 0
var frame_index_visits := 0
var _textures: Dictionary = {}
var _renderer
var _bound := false
var _starts := PackedFloat64Array()
var _prefix_max_ends := PackedFloat64Array()
var _interval_root: Dictionary = {}
var _ink_margin_spaces := ATTACHMENT_MARGIN_SPACES

func _clear_index() -> void:
    _starts.clear()
    _prefix_max_ends.clear()
    _interval_root.clear()
    _ink_margin_spaces = ATTACHMENT_MARGIN_SPACES
    frame_scanned_entries = 0
    frame_index_visits = 0

func _fail(reason: String) -> bool:
    error = reason
    _bound = false
    entries.clear()
    _clear_index()
    return false


func bind(layout: Dictionary, model: Dictionary, renderer) -> bool:
    _bound = false
    entries.clear()
    _clear_index()
    error = ""
    if not str(layout.get("native_annotations_error", "")).is_empty():
        return _fail(str(layout["native_annotations_error"]))
    var required: Dictionary = {}
    var events: Dictionary = {}
    for event in model.get("notation_events", []):
        events[str(event.get("id", ""))] = event
    var requested: Array = model.get("annotations", []).filter(func(event):
        return str(event.get("kind", "")) not in ["slur", "slurs"])
    for event in model.get("visual_events", []):
        if str(event.get("kind", "")) == "grace":
            requested.append(event)
    for event in requested:
        if not event is Dictionary:
            return _fail("Invalid required annotation")
        var ident: String = str(event.get("id", ""))
        if ident.is_empty() or required.has(ident) or event.get("kind", "") not in KINDS:
            return _fail("Missing, duplicate or unsupported annotation ID: " + ident)
        required[ident] = event
    if renderer == null or not renderer.has_method("_staff_center") or renderer.timeline == null:
        return _fail("Annotation renderer has no native timeline/staff geometry")
    var atlas: Dictionary = layout.get("native_annotation_fragments", layout.get("annotation_fragments", {}))
    if atlas.size() != required.size():
        return _fail("Incomplete required Verovio annotation atlas")
    var loaded: Array = []
    var seen_groups: Dictionary = {}
    var textures: Dictionary = {}
    for ident in required:
        var requirement: Dictionary = required[ident]
        var item: Dictionary = atlas.get(ident, {})
        if str(item.get("source", "")) != SOURCE or int(item.get("units_per_space", 0)) != 250:
            return _fail("Missing original Verovio annotation: " + ident)
        for field in requirement:
            if item.get(field) != requirement[field]:
                return _fail("Verovio annotation changed source " + str(field) + ": " + ident)
        var beat: float = float(item.get("beat", NAN))
        if not is_finite(beat) or str(item.get("staff", "")) not in model.get("staff_order", ["right", "left"]):
            return _fail("Invalid annotation beat or staff: " + ident)
        for event_id in item.get("event_ids", []):
            if not events.has(event_id):
                return _fail("Unknown annotation source event: " + ident)
        var kind: String = str(item.get("kind", ""))
        var layout_beat: float = float(item.get("layout_beat", beat))
        if not is_finite(layout_beat):
            return _fail("Invalid annotation layout beat: " + ident)
        if kind == "grace":
            var anchor: Dictionary = events.get(str(item.get("anchor_id", "")), {})
            if anchor.is_empty() or anchor.get("staff") != item.get("staff") or str(
                    anchor.get("voice", "1")) != str(item.get("voice", "1")):
                return _fail("Unknown or incompatible grace anchor: " + ident)
            if absf(layout_beat-float(anchor.get("beat", NAN))) > .0000001:
                return _fail("Invalid grace layout beat for source anchor: " + ident)
        var span: float = float(item.get("span", 0.0))
        if item.has("end_beat") and (not is_finite(float(item["end_beat"])) or
                float(item["end_beat"]) <= beat or not is_finite(span) or span <= 0.0):
            return _fail("Invalid original annotation span: " + ident)
        if kind in ["hairpin", "wedge", "volta", "ending"] and not item.has("end_beat"):
            return _fail("Missing source annotation endpoint: " + ident)
        var parts: Array = item.get("parts", [])
        if parts.is_empty():
            return _fail("Empty original annotation: " + ident)
        var prepared: Array = []
        for part in parts:
            var box: Array = part.get("bounds", [])
            if box.size() != 4:
                return _fail("Missing annotation bounds: " + ident)
            for coordinate in box:
                if not is_finite(float(coordinate)):
                    return _fail("Nonfinite annotation bounds: " + ident)
            if float(box[2]) <= 0.0 or float(box[3]) <= 0.0:
                return _fail("Empty annotation bounds: " + ident)
            var role: String = str(part.get("role", ""))
            if role not in ["fixed", "span"] or (role == "span" and (span <= 0.0 or not item.has("end_beat"))):
                return _fail("Invalid fixed/span annotation art: " + ident)
            var svg: String = str(part.get("svg", ""))
            var encoded: String = str(part.get("png_base64", ""))
            if svg.is_empty() or encoded.is_empty():
                return _fail("Missing original annotation contours: " + ident)
            var key: String = encoded.sha256_text()
            var texture: Texture2D = textures.get(key, _textures.get(key))
            if texture == null:
                var image := Image.new()
                if image.load_png_from_buffer(Marshalls.base64_to_raw(encoded)) != OK or image.is_empty() or not image.get_used_rect().has_area():
                    return _fail("Unreadable original annotation: " + ident)
                texture = ImageTexture.create_from_image(image)
            textures[key] = texture
            prepared.append({"texture":texture, "bounds":box.duplicate(), "role":role,
                "anchor":float(part.get("anchor", 0.0))})
        var ids: Array = item.get("group_ids", [ident])
        if not ids.has(ident) or ids.is_empty():
            return _fail("Invalid annotation group identity: " + ident)
        for member in ids:
            if not required.has(member):
                return _fail("Incomplete required annotation group: " + ident)
            var peer: Dictionary = atlas.get(member, {})
            if peer.get("group_ids") != ids or peer.get("parts") != item.get("parts") or peer.get("anchor_id") != item.get("anchor_id"):
                return _fail("Inconsistent original annotation group: " + ident)
        var group_key: String = JSON.stringify(ids)
        if not seen_groups.has(group_key):
            var attachment: String = str(item.get("anchor_id", "")) if kind == "grace" else ""
            if attachment.is_empty() and not item.has("end_beat") and not item.get("event_ids", []).is_empty():
                attachment = str(item["event_ids"][0])
            # Matching time stays on the grace event. Original fragment
            # bounds are measured from the principal's engraved origin.
            var first: float = layout_beat
            var last: float = float(item.get("end_beat", layout_beat))
            for part in prepared:
                var box: Array = part["bounds"]
                if part["role"] == "span":
                    first = minf(first, layout_beat+float(box[0])/span*(float(item["end_beat"])-layout_beat))
                    last = maxf(last, layout_beat+(float(box[0])+float(box[2]))/span*(float(item["end_beat"])-layout_beat))
                else:
                    var offset: float = float(box[0])-span*float(part["anchor"])
                    _ink_margin_spaces = maxf(_ink_margin_spaces,
                        maxf(absf(offset), absf(offset+float(box[2])))/250.0+ATTACHMENT_MARGIN_SPACES)
            loaded.append({"id":ident, "group_ids":ids.duplicate(), "kind":kind,
                "beat":beat, "layout_beat":layout_beat,
                "end_beat":float(item.get("end_beat", layout_beat)),
                "staff":str(item["staff"]), "span":span, "parts":prepared, "attachment":attachment,
                "index_start":first, "index_end":last})
            seen_groups[group_key] = true
    entries = loaded
    entries.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        if float(a["index_start"]) != float(b["index_start"]):
            return float(a["index_start"]) < float(b["index_start"])
        return str(a["id"]) < str(b["id"]))
    var maximum := -INF
    for item in entries:
        _starts.append(float(item["index_start"]))
        maximum = maxf(maximum, float(item["index_end"]))
        _prefix_max_ends.append(maximum)
    _interval_root = _index_node(0, entries.size())
    _textures = textures
    _renderer = renderer
    _bound = true
    return true


func _index_node(begin: int, end: int) -> Dictionary:
    if begin >= end:
        return {}
    if end-begin == 1:
        return {"begin":begin, "end":end, "max_end":float(entries[begin]["index_end"])}
    var middle: int = (begin+end)>>1
    var left: Dictionary = _index_node(begin, middle)
    var right: Dictionary = _index_node(middle, end)
    return {"begin":begin, "end":end,
        "max_end":maxf(float(left["max_end"]), float(right["max_end"])),
        "left":left, "right":right}


func _bound_index(values: PackedFloat64Array, value: float, inclusive: bool) -> int:
    var begin := 0
    var end: int = values.size()
    while begin < end:
        var middle: int = (begin+end)>>1
        if values[middle] < value or (inclusive and values[middle] == value):
            begin = middle+1
        else:
            end = middle
    return begin


func _query_index(node: Dictionary, begin: int, end: int, left: float, output: Array) -> void:
    frame_index_visits += 1
    if node.is_empty() or int(node["end"]) <= begin or int(node["begin"]) >= end or float(node["max_end"]) < left:
        return
    if int(node["end"])-int(node["begin"]) == 1:
        output.append(entries[int(node["begin"])])
        return
    # Range maxima prune expired interior blocks even when an ancient long
    # span keeps every prefix maximum high. Never linearly scan that prefix.
    _query_index(node["left"], begin, end, left, output)
    _query_index(node["right"], begin, end, left, output)


func placements(clock: float, playhead: float, gap: float) -> Array:
    # Inspectable native draw geometry, also used by paint. No source page X
    # becomes time: every origin/endpoint is evaluated by ScoreTimeline.
    frame_scanned_entries = 0
    frame_index_visits = 0
    if not _bound or not is_finite(clock) or not is_finite(playhead) or not is_finite(gap) or gap <= 0.0:
        return []
    var density: float = _renderer.timeline.pixels_per_beat
    var width: float = _renderer.size.x
    if not is_finite(density) or density <= 0.0 or not is_finite(width) or width <= 0.0:
        return []
    var current: float = _renderer.timeline.musical_beat(clock, _renderer.play_from_beat)
    var margin: float = maxf(INK_MARGIN_PX, _ink_margin_spaces*gap)
    var left: float = current-(playhead+margin)/density
    var right: float = current+(width-playhead+margin)/density
    var begin: int = _bound_index(_prefix_max_ends, left, false)
    var end: int = _bound_index(_starts, right, true)
    var visible: Array = []
    if begin < end:
        _query_index(_interval_root, begin, end, left, visible)
    var result: Array = []
    var unit: float = gap/250.0
    frame_scanned_entries = visible.size()
    for item in visible:
        var x: float = _renderer.timeline.screen_x(item["layout_beat"], clock, playhead, _renderer.play_from_beat)
        var end_x: float = _renderer.timeline.screen_x(item["end_beat"], clock, playhead, _renderer.play_from_beat)
        var attachment: String = item["attachment"]
        if not attachment.is_empty():
            # cached_head_offsets already includes the rigid group translation;
            # adding both offsets would move a chord attachment twice.
            var dx: float = float(_renderer.cached_head_offsets.get(attachment,
                _renderer.cached_group_offsets.get(attachment, 0.0)))
            x += dx
            end_x += dx
        var top: float = _renderer._staff_center(item["staff"])-2.0*gap
        for part in item["parts"]:
            var box: Array = part["bounds"]
            var factor := 1.0
            var origin_x: float = x
            var offset: float = float(box[0])
            if part["role"] == "span":
                factor = (end_x-x)/(float(item["span"])*unit)
            else:
                var anchor: float = part["anchor"]
                origin_x += (end_x-x)*anchor
                offset -= float(item["span"])*anchor
            var destination := Rect2(origin_x+offset*unit*factor, top+float(box[1])*unit,
                float(box[2])*unit*factor, float(box[3])*unit)
            if destination.end.x < -INK_MARGIN_PX or destination.position.x > width+INK_MARGIN_PX:
                continue
            result.append({"id":item["id"], "group_ids":item["group_ids"],
                "staff":item["staff"], "role":part["role"], "texture":part["texture"],
                "rect":destination})
    return result


func paint(canvas: CanvasItem, clock: float, playhead: float, gap: float,
        ink: Color = Color.WHITE) -> bool:
    if not _bound or canvas == null or gap <= 0.0 or not is_finite(gap) or not is_finite(clock) or not is_finite(playhead):
        return false
    for part in placements(clock, playhead, gap):
        canvas.draw_texture_rect(part["texture"], part["rect"], false, ink)
    return true
