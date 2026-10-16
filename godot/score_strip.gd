extends RefCounted

# Keep page-sized GPU textures: a long course must never become one enormous
# texture. All notation and feedback use the same virtual horizontal canvas.
# Long scores can store completed tiles as compact CPU buffers until
# needed. Ordinary short warmups keep the original fast eager texture path.
const DEFERRED_MIN_SYSTEMS := 8

static func build(layout: Dictionary, pages: Array[Image],
        defer_textures: bool = false) -> Dictionary:
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
    # Natural engraving can leave a *short* join after safe cropping.
    # Preserve constant temporal travel by inserting an unmarked staff
    # extension, without stretching any existing note, accidental or barline.
    # Imported/change-of-context scores are left completely untouched.
    if bool(layout.get("strip_trim_repeated_headers", false)):
        width = _pad_short_system_joins(layout, mappings)
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
        var lead: int = int(mapping.get("entry_padding", 0))
        if lead > 0:
            var expanded := Image.create(image.get_width() + lead,
                image.get_height(), false, image.get_format())
            expanded.fill(Color.TRANSPARENT)
            expanded.blit_rect(image, Rect2i(Vector2i.ZERO, image.get_size()),
                Vector2i(lead, 0))
            # Extend only the five real staff rules per hand. This is
            # transparent space; no added note or simulated engraving.
            for line in mapping.system.get("staff_lines", []):
                var staff_y: int = int(round(float(line) * float(mapping.source_size.y)
                    - float(mapping.crop.position.y)))
                for x in range(lead):
                    for offset in range(-1, 2):
                        var y: int = staff_y + offset
                        if y >= 0 and y < expanded.get_height():
                            expanded.set_pixel(x, y, Color(0, 0, 0,
                                .80 if offset == 0 else .14))
            image = expanded
        # Remove only the loose horizontal rules at the *raster seam*.
        # The single StaffContinuity canvas supplies those pixels instead.
        # A column containing a barline, tie, stem or any non-staff ink is
        # never erased. Actual measure barlines remain fully engraved.
        if bool(layout.get("strip_trim_repeated_headers", false)):
            var has_previous: bool = mappings.find(mapping) > 0
            var has_next: bool = mappings.find(mapping) < mappings.size() - 1
            mapping["seam_pixels_removed"] = _clear_join_rails(
                image, mapping, has_previous, has_next)
        # Verovio's score raster is monochrome engraving with alpha.
        # LA8 preserves the ink luminance and antialiased alpha while
        # requiring two bytes per pixel instead of RGBA8's four.
        # The original source layouts and glyph positions are unchanged.
        image = compact_monochrome_tile(image)
        var tile: Dictionary = {
            "rect": Rect2(mapping.position, Vector2(image.get_size())),
            "upload_bytes": image.get_data().size()}
        if defer_textures:
            # FastLZ on the LA8 raster is inexpensive and reversible. The
            # source buffer lives on the CPU; no Texture2D is uploaded until
            # this engraved system approaches the viewport.
            tile["packed_ink"] = image.get_data().compress(
                FileAccess.COMPRESSION_FASTLZ)
            tile["image_size"] = image.get_size()
        else:
            tile["texture"] = ImageTexture.create_from_image(image)
        tiles.append(tile)
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


# Called only once per source tile, after all raster-safe cropping and
# rail cleanup. Staff notation has no required RGB color channels: existing
# code shades real notes via a separate shader and canvas overlays.
static func compact_monochrome_tile(image: Image) -> Image:
    if image.get_format() != Image.FORMAT_LA8:
        image.convert(Image.FORMAT_LA8)
    return image


# Restore an unmodified LA8 raster on demand. This is deliberately
# independent of tile visibility and musical time, so seek cannot
# introduce new note positions, re-engrave, or modify the source score.
static func tile_texture(tile: Dictionary) -> Texture2D:
    var eager: Variant = tile.get("texture")
    if eager is Texture2D:
        return eager
    var compressed: PackedByteArray = tile.get("packed_ink", PackedByteArray())
    var dimensions: Vector2i = tile.get("image_size", Vector2i.ZERO)
    var expected: int = int(tile.get("upload_bytes", 0))
    if dimensions.x <= 0 or dimensions.y <= 0 \
            or expected != dimensions.x * dimensions.y * 2 \
            or compressed.is_empty():
        return null
    var pixels: PackedByteArray = compressed.decompress(
        expected, FileAccess.COMPRESSION_FASTLZ)
    if pixels.size() != expected:
        return null
    var image := Image.create_from_data(dimensions.x, dimensions.y, false,
        Image.FORMAT_LA8, pixels)
    if image == null or image.is_empty():
        return null
    return ImageTexture.create_from_image(image)


# Return anchors for one original system. The backend order is musical-time
# order; the original page/system pairing is essential for multi-page scores.
static func _source_anchors(layout: Dictionary, mapping: Dictionary) -> Array:
    var result: Array = []
    for item in layout.get("anchors", []):
        if int(item.get("page", -1)) == int(mapping.source_page) \
                and str(item.get("system", "")) == str(mapping.source_system):
            result.append(item)
    return result


static func _pad_short_system_joins(layout: Dictionary, mappings: Array) -> float:
    var groups: Array = []
    var speeds: Array[float] = []
    for mapping in mappings:
        var group: Array = _source_anchors(layout, mapping)
        groups.append(group)
        for index in range(group.size() - 1):
            var left: Dictionary = group[index]
            var right: Dictionary = group[index + 1]
            var span: float = float(right.get("beat", 0.0)) - float(left.get("beat", 0.0))
            if span <= .000001:
                continue
            var native_pixels: float = _mapped_px(float(right.x), mapping) \
                - _mapped_px(float(left.x), mapping)
            if native_pixels > 0.0:
                speeds.append(native_pixels / span)
    if speeds.is_empty():
        return 0.0
    speeds.sort()
    var target: float = speeds[speeds.size() / 2]
    var running_width := 0.0
    for index in range(mappings.size()):
        var mapping: Dictionary = mappings[index]
        var padding := 0
        if index > 0 and not groups[index-1].is_empty() and not groups[index].is_empty():
            var previous: Dictionary = mappings[index-1]
            var end: Dictionary = groups[index-1][-1]
            var beginning: Dictionary = groups[index][0]
            var beat_gap: float = float(beginning.beat) - float(end.beat)
            if beat_gap > .000001:
                var previous_cut: float = maxf(0.0, float(
                    int(previous.get("splice_right", -1)) - int(previous.get("splice_left", -1))))
                var tail: float = float(previous.crop.size.x) - previous_cut \
                    + float(previous.get("entry_padding", 0)) \
                    - (_mapped_px(float(end.x), previous) - float(previous.position.x))
                var head: float = _mapped_px(float(beginning.x), mapping) \
                    - float(mapping.position.x)
                var measured: float = tail + head
                var gap_px: float = 16.0
                var lines: Array = mapping.system.get("staff_lines", [])
                if lines.size() >= 2:
                    gap_px = absf(float(lines[1]) - float(lines[0])) * float(mapping.source_size.y)
                var desired: float = maxf(0.0, target * beat_gap - measured)
                # Limit long rests / unusual imported glyphs; do not try to
                # invent several beats worth of staff where there is no ink.
                padding = int(round(minf(desired, maxf(24.0, gap_px * 4.75))))
        mapping["entry_padding"] = padding
        mapping["position"] = Vector2(running_width, 0.0)
        var cut: float = maxf(0.0, float(
            int(mapping.get("splice_right", -1)) - int(mapping.get("splice_left", -1))))
        running_width += float(mapping.crop.size.x) - cut + float(padding)
    return running_width


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


# Erase orphaned *horizontal* staff-rule fragments where adjacent
# engraved image tiles meet. The rails behind all the tiles are already
# continuous, so their positions are preserved. Guard each individual column:
# never cut a real barline or a notation glyph that happens to cross the edge.
static func _clear_join_rails(image: Image, mapping: Dictionary,
        has_previous: bool, has_next: bool) -> int:
    var measured: Array = mapping.system.get("staff_lines", [])
    if measured.is_empty() or image.get_width() <= 4:
        return 0
    var rail_y: Array = []
    for fraction in measured:
        rail_y.append(float(fraction) * float(mapping.source_size.y) -
            float(mapping.crop.position.y))
    var columns: Array[int] = []
    var edge: int = mini(9, floori(float(image.get_width()) / 4.0))
    if has_previous and bool(mapping.get("trimmed_header", false)):
        for x in range(edge):
            columns.append(x + int(mapping.get("entry_padding", 0)))
    if has_next:
        for x in range(image.get_width() - edge, image.get_width()):
            columns.append(x)
    var removed := 0
    for x in columns:
        if x < 0 or x >= image.get_width():
            continue
        # The source-height normalization here is deliberately 1: rail_y
        # already describes local *pixel* coordinates of this stitched tile.
        if not _staff_only_gap(image, x, x + 1, 0, image.get_height(), rail_y, 1.0):
            continue
        for rail in rail_y:
            var center := roundi(float(rail))
            for y in range(maxi(0, center - 3), mini(image.get_height(), center + 4)):
                if image.get_pixel(x, y).a > .01:
                    image.set_pixel(x, y, Color.TRANSPARENT)
                    removed += 1
    return removed


static func _mapped_px(normalized: float, mapping: Dictionary) -> float:
    var absolute: float = normalized * float(mapping.source_size.x)
    var removed_start: int = int(mapping.get("splice_left", -1))
    var removed_end: int = int(mapping.get("splice_right", -1))
    if removed_start >= 0 and removed_end > removed_start:
        if absolute >= removed_end:
            absolute -= float(removed_end - removed_start)
        elif absolute > removed_start:
            absolute = float(removed_start)
    return absolute - float(mapping.crop.position.x) + float(mapping.position.x) \
        + float(mapping.get("entry_padding", 0))


# Phase 8F: avoid submitting far-offscreen Verovio tiles to the
# renderer. Textures and native geometry stay loaded for instant seeking;
# the overdraw margin prevents a seam flashing on a fast transport update.
static func tile_visible(tile: Dictionary, content_x: float, scale: float,
        viewport_width: float, overscan: float) -> bool:
    var rect: Rect2 = tile.get("rect", Rect2())
    if viewport_width <= 0.0 or scale <= 0.0 or rect.size.x <= 0.0:
        return true # Invalid view: fail open rather than hide sheet music.
    var left: float = content_x + rect.position.x * scale
    var right: float = left + rect.size.x * scale
    return right >= -overscan and left <= viewport_width + overscan


# Return the half-open contiguous tile interval which intersects the
# moving viewport plus its overscan. Build() puts systems in horizontal
# order, with positive widths and no overlap. Two binary searches make
# camera movement O(log systems), regardless of the length of the piece.
static func visible_tile_range(tiles: Array, content_x: float, scale: float,
        viewport_width: float, overscan: float) -> Vector2i:
    var count: int = tiles.size()
    if count == 0:
        return Vector2i.ZERO
    if not is_finite(content_x) or not is_finite(scale) or scale <= 0.0 \
            or not is_finite(viewport_width) or viewport_width <= 0.0 \
            or not is_finite(overscan) or overscan < 0.0:
        return Vector2i(0, count) # Fail open: never hide notation.
    var minimum: float = (-overscan - content_x) / scale
    var maximum: float = (viewport_width + overscan - content_x) / scale
    var low := 0
    var high := count
    # First tile whose right edge reaches the left viewport boundary.
    while low < high:
        var mid: int = (low + high) >> 1
        var rect: Rect2 = tiles[mid].get("rect", Rect2())
        if rect.end.x < minimum:
            low = mid + 1
        else:
            high = mid
    var first: int = low
    low = first
    high = count
    # First tile starting strictly after the right viewport boundary.
    while low < high:
        var mid: int = (low + high) >> 1
        var rect: Rect2 = tiles[mid].get("rect", Rect2())
        if rect.position.x <= maximum:
            low = mid + 1
        else:
            high = mid
    return Vector2i(first, low)


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
