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
                # One full staff space before the *measured leftmost ink*
                # is enough to protect an accidental or ledger extension.
                # The old 1.7-space gutter was redundant after the header
                # was intentionally removed and still caused acceleration.
                var guard_px: float = maxf(10.0, gap_px * 1.0)
                var candidate: int = maxi(left, int(floor(ink_px - guard_px)))
                if candidate < right - 16 and candidate > left:
                    left = candidate
                    trimmed_header = true
        # Verovio may extend staff lines well beyond the final printed
        # barline. Trim only that redundant trailing run, not a note's
        # native spacing or any written barline/tie/accidental glyph.
        var trimmed_tail := false
        var splice_left := -1
        var splice_right := -1
        if bool(layout.get("strip_trim_repeated_headers", false)) \
                and source_systems.find(system) < source_systems.size() - 1:
            # A tie crossing the upcoming system boundary may extend past
            # this barline. Keep its full original trailing region.
            var following: Dictionary = source_systems[source_systems.find(system) + 1]
            var first_next_beat := INF
            for item in layout.get("notes", []):
                if int(item.get("page", -1)) == int(following.get("page", -1)) \
                        and str(item.get("system", "")) == str(following.get("system", "")):
                    first_next_beat = minf(first_next_beat, float(item.get("beat", INF)))
            var boundary_tie := false
            for item in layout.get("notes", []):
                if int(item.get("page", -1)) == int(following.get("page", -1)) \
                        and str(item.get("system", "")) == str(following.get("system", "")) \
                        and absf(float(item.get("beat", INF)) - first_next_beat) < .000001 \
                        and item.has("is_attack") and not bool(item["is_attack"]):
                    boundary_tie = true
                    break
            var barline_x: float = -1.0 if boundary_tie else float(system.get("last_barline_x", -1.0))
            var staff_lines_for_tail: Array = system.get("staff_lines", [])
            if barline_x >= 0.0 and staff_lines_for_tail.size() >= 2:
                var gap_for_tail: float = absf(float(staff_lines_for_tail[1]) -
                    float(staff_lines_for_tail[0])) * source_size.y
                var final_note_x := -INF
                for item in layout.get("notes", []):
                    if int(item.get("page", -1)) == page and str(item.get("system", "")) == str(system.get("system", "")):
                        final_note_x = maxf(final_note_x, float(item.get("x", -INF)) * source_size.x)
                var last_barline_pixel: float = barline_x * source_size.x
                # Don't trust an unrecognized barline or remove the right
                # portion of a note placed unusually close to that barline.
                if last_barline_pixel >= final_note_x + gap_for_tail * .5:
                    var proposed_right: int = int(ceil(last_barline_pixel +
                        maxf(9.0, gap_for_tail * 1.25)))
                    if proposed_right < right - 8 and proposed_right > left + 16:
                        right = proposed_right
                        trimmed_tail = true
                    # Cut only measured blank space between the last event
                    # and the real system-ending barline. Removing it shortens
                    # the artificial fast camera run while leaving notation
                    # glyphs, barlines and their source identities untouched.
                    var last_event_x := final_note_x
                    for event in layout.get("anchors", []):
                        if int(event.get("page", -1)) == page \
                                and str(event.get("system", "")) == str(system.get("system", "")) \
                                and not bool(event.get("terminal", false)):
                            last_event_x = maxf(last_event_x, float(event.get("x", -INF)) * source_size.x)
                    var cut_start: int = int(ceil(last_event_x + maxf(5.0, gap_for_tail * .45)))
                    var cut_end: int = int(floor(last_barline_pixel - maxf(5.0, gap_for_tail * .45)))
                    var scan_top: int = maxi(0, int(floor(float(system.top) * source_size.y)))
                    var scan_bottom: int = mini(image.get_height(), int(ceil(float(system.bottom) * source_size.y)))
                    if cut_end - cut_start >= 12 and cut_start > left + 8 and cut_end < right - 4:
                        var safe_run: Vector2i = _longest_staff_only_run(image,
                            cut_start, cut_end, scan_top, scan_bottom,
                            staff_lines_for_tail, source_size.y)
                        if safe_run.y - safe_run.x >= 12:
                            splice_left = safe_run.x
                            splice_right = safe_run.y
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
            "trimmed_header": trimmed_header, "trimmed_tail": trimmed_tail,
            "splice_left": splice_left, "splice_right": splice_right})
        width += float(crop.size.x - maxi(0, splice_right - splice_left))
    var size := Vector2(maxf(1.0, width), maxf(1.0, above + below))
    var tiles: Array = []
    for mapping in mappings:
        mapping.position.y = above - float(mapping.staff_offset)
        var image: Image = pages[int(mapping.source_page)].get_region(Rect2i(mapping.crop))
        var cut_a: int = int(mapping.get("splice_left", -1))
        var cut_b: int = int(mapping.get("splice_right", -1))
        if cut_a >= 0 and cut_b > cut_a:
            var crop: Rect2 = mapping.crop
            var relative_a: int = cut_a - int(crop.position.x)
            var relative_b: int = cut_b - int(crop.position.x)
            var stitched := Image.create(image.get_width() - (relative_b - relative_a),
                image.get_height(), false, image.get_format())
            stitched.fill(Color.TRANSPARENT)
            stitched.blit_rect(image, Rect2i(0, 0, relative_a, image.get_height()),
                Vector2i.ZERO)
            stitched.blit_rect(image, Rect2i(relative_b, 0,
                image.get_width() - relative_b, image.get_height()), Vector2i(relative_a, 0))
            image = stitched
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
        system["left"] = _mapped_px(float(system.left), mapping) / size.x
        system["right"] = _mapped_px(float(system.right), mapping) / size.x
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


# A splice is allowed only where the raster contains staff lines and no
# other visible ink. Beams, ties, accidentals, articulations, dynamics and
# nonstandard symbols all cause an automatic safe fallback.
static func _staff_only_gap(image: Image, x0: int, x1: int, y0: int, y1: int,
        lines: Array, source_height: float) -> bool:
    for x in range(x0, x1):
        for y in range(y0, y1):
            var pixel: Color = image.get_pixel(x, y)
            if pixel.a < .18 or (pixel.r >= .92 and pixel.g >= .92 and pixel.b >= .92):
                continue
            var on_staff := false
            for fraction in lines:
                if absf(float(y) - float(fraction) * source_height) <= 2.5:
                    on_staff = true
                    break
            if not on_staff:
                return false
    return true


static func _longest_staff_only_run(image: Image, x0: int, x1: int,
        y0: int, y1: int, lines: Array, source_height: float) -> Vector2i:
    # Start just after the final event and stop before the known barline.
    # Select the longest uninterrupted run of genuine staff-only columns.
    # A stem, slur or note fragment anywhere in the middle splits the run,
    # instead of making us discard all potential safe whitespace.
    var best := Vector2i(-1, -1)
    var current := -1
    for x in range(x0, x1 + 1):
        var safe: bool = x < x1 and _staff_only_gap(
            image, x, x + 1, y0, y1, lines, source_height)
        if safe and current < 0:
            current = x
        if not safe and current >= 0:
            if x - current > best.y - best.x:
                best = Vector2i(current, x)
            current = -1
    return best


static func _mapped_px(normalized: float, mapping: Dictionary) -> float:
    var absolute: float = normalized * float(mapping.source_size.x)
    var removed_start: int = int(mapping.get("splice_left", -1))
    var removed_end: int = int(mapping.get("splice_right", -1))
    if removed_start >= 0 and removed_end > removed_start:
        if absolute >= removed_end:
            absolute -= float(removed_end - removed_start)
        elif absolute > removed_start:
            absolute = float(removed_start)
    return absolute - float(mapping.crop.position.x) + float(mapping.position.x)


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
        mapped["x"] = _mapped_px(x, mapping) / size.x
        mapped["y"] = (y*source_size.y-crop.position.y+position.y)/size.y
        if source.has("ink_left"):
            var ink_left: float = float(source.get("source_ink_left", source.ink_left))
            mapped["source_ink_left"] = ink_left
            mapped["ink_left"] = _mapped_px(ink_left, mapping) / size.x
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
