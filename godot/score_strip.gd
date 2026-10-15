extends RefCounted

# Keep page-sized GPU textures: a long course must never become one enormous
# texture. All notation and feedback use the same virtual horizontal canvas.
static func build(layout: Dictionary, pages: Array[Image]) -> Dictionary:
    var source_systems: Array = layout.get("systems", []).duplicate(true)
    if source_systems.is_empty():
        return _failure("The engraving has no measured staff systems")
    source_systems.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a.get("start_beat", 0.0)) < float(b.get("start_beat", 0.0)))
    var mappings: Array = []
    var above := 0.0
    var below := 0.0
    var width := 0.0
    for system in source_systems:
        var page: int = int(system.get("page", 0))
        if page < 0 or page >= pages.size() or pages[page] == null:
            return _failure("An engraved score page is missing")
        var image: Image = pages[page]
        var source_size := Vector2(image.get_width(), image.get_height())
        # CairoSVG rounds the PNG surface height to integer pixels while its
        # drawing context keeps the unrounded height derived from SVG aspect.
        # Use that same coordinate extent, rather than stretching coordinates
        # by the rounded height differently on every page.
        var widths: Array = layout.get("widths", [])
        var heights: Array = layout.get("heights", [])
        if page < widths.size() and page < heights.size() and float(widths[page]) > 0.0:
            source_size.y = source_size.x * float(heights[page]) / float(widths[page])
        # Leave room for the opening clefs, meter and hand labels. Subsequent
        # systems keep their own clefs while moving through the timing line.
        var left: int = maxi(0, int(floor(minf(.02, float(system.left)) * source_size.x)))
        var right: int = mini(image.get_width(), int(ceil((float(system.right) + .02) * source_size.x)))
        var trimmed_header := false
        if not mappings.is_empty() and bool(layout.get("strip_trim_repeated_headers", false)):
            # The backend has verified this generated two-hand lesson has no
            # subsequent clef, meter, key or navigation changes. Discard the
            # *reprinted* system header, which otherwise becomes a huge
            # artificial beat gap every time two printed lines are joined.
            # Crop a little before the exact leftmost note/rest ink; preserve
            # noteheads, accidentals, ledger lines and all glyph sizes.
            var first_beat: float = INF
            var first_ink: float = INF
            for anchor in layout.get("anchors", []):
                if int(anchor.get("page", -1)) != page or str(anchor.get("system", "")) != str(system.get("system", "")):
                    continue
                var at_beat: float = float(anchor.get("beat", INF))
                if at_beat < first_beat - .000001:
                    first_beat = at_beat
                    first_ink = float(anchor.get("ink_left", anchor.get("x", 0.0)))
                elif absf(at_beat - first_beat) <= .000001:
                    first_ink = minf(first_ink, float(anchor.get("ink_left", anchor.get("x", 0.0))))
            var staff_lines: Array = system.get("staff_lines", [])
            var tied_into_system := false
            for note in layout.get("notes", []):
                if int(note.get("page", -1)) != page or str(note.get("system", "")) != str(system.get("system", "")):
                    continue
                if absf(float(note.get("beat", INF)) - first_beat) <= .000001 \
                        and note.has("is_attack") and not bool(note["is_attack"]):
                    # A continuation tie can start to the left of the
                    # notehead; the glyph's ink_left does not encompass that
                    # entire curve. Retain this header rather than clip music.
                    tied_into_system = true
                    break
            if not tied_into_system and is_finite(first_ink) and staff_lines.size() >= 2:
                var gap_px: float = absf(float(staff_lines[1]) - float(staff_lines[0])) * source_size.y
                var ink_px: float = first_ink * source_size.x
                var guard_px: float = maxf(10.0, gap_px * 1.7)
                var candidate: int = maxi(left, int(floor(ink_px - guard_px)))
                if candidate < right - 16 and candidate > left:
                    left = candidate
                    trimmed_header = true
        var top: int = maxi(0, int(floor(float(system.top) * source_size.y)))
        var bottom: int = mini(image.get_height(), int(ceil(float(system.bottom) * source_size.y)))
        if right <= left or bottom <= top:
            return _failure("An engraved staff system has invalid bounds")
        var crop := Rect2i(left, top, right-left, bottom-top)
        var lines: Array = system.get("staff_lines", [])
        var staff_top: float = float(lines[0]) * source_size.y if not lines.is_empty() else float(top)
        var offset: float = staff_top - float(top)
        above = maxf(above, offset)
        below = maxf(below, float(crop.size.y) - offset)
        mappings.append({"source_page": page, "source_system": str(system.get("system", "")),
            "source_size": source_size, "crop": Rect2(crop), "position": Vector2(width, 0),
            "staff_offset": offset, "system": system,
            "trimmed_header": trimmed_header})
        width += float(crop.size.x)
    var size := Vector2(maxf(1.0, width), maxf(1.0, above + below))
    var tiles: Array = []
    for mapping in mappings:
        mapping.position.y = above - float(mapping.staff_offset)
        var image: Image = pages[int(mapping.source_page)].get_region(Rect2i(mapping.crop))
        tiles.append({"texture": ImageTexture.create_from_image(image),
            "rect": Rect2(mapping.position, Vector2(image.get_size()))})
    var flat: Dictionary = layout.duplicate(true)
    flat["pages"] = 1
    flat["widths"] = [size.x]
    flat["heights"] = [size.y]
    flat["strip_size"] = size
    flat["strip_mappings"] = mappings
    for key in ["notes", "anchors"]:
        var positioned: Array = []
        for source in layout.get(key, []):
            positioned.append(map_point(source, flat))
        flat[key] = positioned
    var flat_systems: Array = []
    for mapping in mappings:
        var system: Dictionary = mapping.system.duplicate(true)
        var source_size: Vector2 = mapping.source_size
        var crop: Rect2 = mapping.crop
        var position: Vector2 = mapping.position
        system["source_page"] = system.get("page", 0)
        system["source_system"] = system.get("system", "")
        system["page"] = 0
        system["system"] = "strip"
        system["left"] = (float(system.left)*source_size.x-crop.position.x+position.x)/size.x
        system["right"] = (float(system.right)*source_size.x-crop.position.x+position.x)/size.x
        system["top"] = (float(system.top)*source_size.y-crop.position.y+position.y)/size.y
        system["bottom"] = (float(system.bottom)*source_size.y-crop.position.y+position.y)/size.y
        var lines: Array = []
        for y in system.get("staff_lines", []):
            lines.append((float(y)*source_size.y-crop.position.y+position.y)/size.y)
        system["staff_lines"] = lines
        flat_systems.append(system)
    flat["systems"] = flat_systems
    return {"layout": flat, "tiles": tiles, "size": size,
        "crop_origin": Vector2.ZERO, "crop_size": Vector2.ONE, "mappings": mappings}


static func _failure(message: String) -> Dictionary:
    return {"error": message, "layout": {}, "tiles": [], "size": Vector2.ZERO,
        "crop_origin": Vector2.ZERO, "crop_size": Vector2.ONE, "mappings": []}


static func map_point(source: Dictionary, strip: Dictionary) -> Dictionary:
    var layout: Dictionary = strip.get("layout", strip)
    var size: Vector2 = layout.get("strip_size", Vector2.ONE)
    var mapped: Dictionary = source.duplicate(true)
    var page: int = int(source.get("source_page", source.get("page", 0)))
    var system: String = str(source.get("source_system", source.get("system", "")))
    # HTTP feedback names a note_id, page and beat; it does not carry system.
    if system.is_empty() and source.has("note_id"):
        for note in layout.get("notes", []):
            if str(note.get("id", "")) == str(source.note_id):
                system = str(note.get("source_system", ""))
                break
    if system.is_empty():
        for mapping in layout.get("strip_mappings", []):
            if page != int(mapping.source_page):
                continue
            var bounds: Dictionary = mapping.system
            var beat: float = float(source.get("beat", -1.0))
            var end: float = float(bounds.get("end_beat", INF))
            var at_final_end: bool = absf(beat - end) <= .000001 and absf(beat - float(layout.get("beats", -1.0))) <= .000001
            if beat >= float(bounds.get("start_beat", 0.0)) and (beat < end or at_final_end):
                system = str(mapping.source_system)
                break
            if not source.has("beat") and float(source.get("y", 0.0)) >= float(bounds.top) and float(source.get("y", 0.0)) <= float(bounds.bottom):
                system = str(mapping.source_system)
                break
    for mapping in layout.get("strip_mappings", []):
        if page != int(mapping.source_page) or system != str(mapping.source_system):
            continue
        var source_size: Vector2 = mapping.source_size
        var crop: Rect2 = mapping.crop
        var position: Vector2 = mapping.position
        var x: float = float(source.get("source_x", source.get("x", 0.0)))
        var y: float = float(source.get("source_y", source.get("y", 0.0)))
        mapped["source_page"] = page
        mapped["source_system"] = system
        mapped["source_x"] = x
        mapped["source_y"] = y
        mapped["page"] = 0
        mapped["system"] = "strip"
        mapped["x"] = (x*source_size.x-crop.position.x+position.x)/size.x
        mapped["y"] = (y*source_size.y-crop.position.y+position.y)/size.y
        if source.has("ink_left"):
            var ink_left: float = float(source.get("source_ink_left", source.ink_left))
            mapped["source_ink_left"] = ink_left
            mapped["ink_left"] = (ink_left*source_size.x-crop.position.x+position.x)/size.x
        for key in ["top", "bottom"]:
            if source.has(key):
                mapped[key] = (float(source[key])*source_size.y-crop.position.y+position.y)/size.y
        if not source.has("note_id") and (bool(source.get("estimated", false)) or str(source.get("status", "")) == "extra"):
            # Estimated extras belong to musical time, rather than a glyph.
            # Source-page locate_beat holds at a system end; the strip keeps
            # moving through the join, so use its continuous timing anchors.
            var anchors: Array = layout.get("anchors", [])
            var beat: float = float(source.get("beat", 0.0))
            for index in range(anchors.size()):
                var left: Dictionary = anchors[index]
                if index + 1 < anchors.size() and float(anchors[index+1].beat) <= beat + .000001:
                    continue
                mapped["x"] = float(left.x)
                if index + 1 < anchors.size():
                    var right: Dictionary = anchors[index+1]
                    var span: float = float(right.beat) - float(left.beat)
                    if span > 0.0:
                        var fraction: float = clampf((beat - float(left.beat)) / span, 0.0, 1.0)
                        mapped["x"] = lerpf(float(left.x), float(right.x), fraction)
                break
        return mapped
    return mapped
