extends RefCounted

# Phase 1: lossless spacing for a *single* continuous Verovio system.
#
# The source of truth is still the genuine Verovio raster. Insert transparent
# columns only where the WHOLE original column contains no non-staff ink.
# A tie, beam, slur, accidental or other connected symbol protects its entire
# column and forbids a cut. Never interpolate, stretch or synthesize glyphs.
#
# All placements use the same absolute quarter-beat x axis. If any event
# interval is unsafe, reject the WHOLE passage and return its native engraving.
const BeatCamera := preload("res://score_beat_camera.gd")
const MAX_TILE_WIDTH := 16384
const GUARD_COLUMNS := 3

static func _failure(source: Dictionary, message: String) -> Dictionary:
    var result: Dictionary = source.duplicate(true)
    var layout: Dictionary = source["layout"].duplicate(true)
    layout["exact_ink_grid"] = false
    layout["exact_ink_grid_reason"] = message
    result["layout"] = layout
    return result

static func _protected_columns(image: Image, rail_rows: Array) -> PackedByteArray:
    var width: int = image.get_width()
    var height: int = image.get_height()
    var protected := PackedByteArray()
    protected.resize(width)
    var bands := PackedByteArray()
    bands.resize(height)
    for row in rail_rows:
        var centre: int = roundi(float(row) * height)
        for y in range(maxi(0, centre - 3), mini(height, centre + 4)):
            bands[y] = 1
    # LA8 is the exact native Verovio ink format produced by ScoreStrip.
    # Scanning the immutable two-byte raster once is cheaper than repeated
    # get_pixel() calls for every interval in a dense imported MIDI.
    var pixels: PackedByteArray = image.get_data()
    for y in range(height):
        if bands[y] != 0:
            continue
        var row_start: int = y * width * 2
        for x in range(width):
            if protected[x] != 0:
                continue
            var at: int = row_start + x * 2
            if pixels[at + 1] >= 42 and pixels[at] < 236:
                protected[x] = 1
    return protected

static func _clean_cut(protected: PackedByteArray,
        start: int, end: int, guard: int) -> int:
    # Preserve a full staff space around each event; an SVG note's measured
    # origin does not include its flags and nearby accidental/ledger ink.
    var left: int = maxi(guard + GUARD_COLUMNS, start + guard)
    var right: int = mini(protected.size() - guard - GUARD_COLUMNS,
        end - guard)
    if right <= left:
        return -1
    var middle: int = (left + right) / 2
    for delta in range(right - left + 1):
        for sign in [-1, 1]:
            var at: int = middle + sign * delta
            if at < left or at > right:
                continue
            var empty := true
            for x in range(at - GUARD_COLUMNS, at + GUARD_COLUMNS + 1):
                if protected[x] != 0:
                    empty = false
                    break
            if empty:
                return at
    return -1

static func _translated_x(x: float, cuts: Array) -> float:
    var shifted := x
    for cut in cuts:
        if x > float(cut.x):
            shifted += float(cut.extra)
    return shifted

static func reflow(original: Dictionary) -> Dictionary:
    if original.has("error"):
        return original
    var layout: Dictionary = original.get("layout", {})
    var tiles: Array = original.get("tiles", [])
    var systems: Array = layout.get("systems", [])
    if not bool(layout.get("continuous_score", false)) or tiles.size() != 1 \
            or systems.size() != 1:
        return _failure(original, "Exact ink spacing requires one Verovio system")
    var source_tile: Dictionary = tiles[0]
    var texture: Texture2D = source_tile.get("texture") as Texture2D
    if texture == null:
        return _failure(original, "Original engraved tile is not resident")
    var image: Image = texture.get_image()
    if image == null or image.get_format() != Image.FORMAT_LA8:
        return _failure(original, "Original Verovio glyph pixels are not LA8")
    var native_width: int = image.get_width()
    var native_height: int = image.get_height()
    var anchors: Array = layout.get("anchors", []).duplicate(true)
    anchors.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a.get("beat", 0.0)) < float(b.get("beat", 0.0)))
    var events: Array[Vector2] = []
    for anchor in anchors:
        var beat: float = float(anchor.get("beat", -INF))
        var source_x: float = float(anchor.get("x", -INF)) * native_width
        if not is_finite(beat) or not is_finite(source_x) \
                or source_x < 0.0 or source_x >= native_width:
            return _failure(original, "Non-finite or out-of-bounds Verovio anchor")
        if not events.is_empty() and absf(beat - events[-1].x) < .000001:
            if absf(source_x - events[-1].y) > 2.0:
                return _failure(original, "Conflicting simultaneous score positions")
            continue
        if not events.is_empty() and source_x <= events[-1].y:
            return _failure(original, "Non-monotone engraved event positions")
        events.append(Vector2(beat, source_x))
    if events.size() < 3:
        return _failure(original, "Too few independent rhythmic events")
    var rates: Array[float] = []
    for i in range(events.size() - 1):
        var beat_gap: float = events[i + 1].x - events[i].x
        if beat_gap <= .000001:
            return _failure(original, "Zero-duration Verovio rhythmic interval")
        rates.append((events[i + 1].y - events[i].y) / beat_gap)
    rates.sort()
    if rates[0] <= 0.0 or rates[-1] > rates[rates.size() / 2] * 4.0:
        return _failure(original, "Imported rhythmic ornaments need a complex glyph-group layout")
    # Expansion only. Never compress a stem/beam or change a notehead width.
    var rate: float = rates[-1] + .5
    var projected_width: float = native_width + rate * (events[-1].x - events[0].x) \
        - (events[-1].y - events[0].y)
    if projected_width > MAX_TILE_WIDTH or projected_width > native_width * 4.0:
        return _failure(original, "Exact Verovio spacing exceeds bounded tile memory")
    var rails: Array = systems[0].get("staff_lines", [])
    if rails.size() != 10:
        return _failure(original, "Not a complete two-hand grand staff")
    var gap: int = maxi(8, roundi(absf(float(rails[1]) - float(rails[0])) * native_height))
    var protected: PackedByteArray = _protected_columns(image, rails)
    var cuts: Array = []
    var added := 0
    for i in range(events.size() - 1):
        var source_left: float = events[i].y
        var source_right: float = events[i + 1].y
        var target_left: float = events[0].y + (events[i].x - events[0].x) * rate
        var target_right: float = events[0].y + (events[i + 1].x - events[0].x) * rate
        var expansion: int = roundi(target_right - target_left) \
            - roundi(source_right - source_left)
        if expansion < 0:
            return _failure(original, "Engraving would require glyph compression")
        if expansion == 0:
            continue
        var cut: int = _clean_cut(protected, roundi(source_left),
            roundi(source_right), gap)
        if cut < 0:
            return _failure(original,
                "A beam, tie, slur or other genuine Verovio ink blocks a safe gap")
        cuts.append({"x": cut, "extra": expansion})
        added += expansion
    if cuts.is_empty():
        return _failure(original, "No safe empty interval requires translation")
    var new_width: int = native_width + added
    if new_width > MAX_TILE_WIDTH:
        return _failure(original, "Exact Verovio strip exceeds GPU tile limit")
    var rearranged := Image.create(new_width, native_height, false, Image.FORMAT_LA8)
    rearranged.fill(Color.TRANSPARENT)
    var src_start := 0
    var offset := 0
    for cut in cuts:
        var cut_x: int = int(cut.x)
        if cut_x < src_start:
            return _failure(original, "Overlapping engraver cut points")
        rearranged.blit_rect(image,
            Rect2i(src_start, 0, cut_x - src_start, native_height),
            Vector2i(src_start + offset, 0))
        src_start = cut_x
        offset += int(cut.extra)
    rearranged.blit_rect(image,
        Rect2i(src_start, 0, native_width - src_start, native_height),
        Vector2i(src_start + offset, 0))

    var result: Dictionary = original.duplicate(true)
    var flat: Dictionary = layout.duplicate(true)
    for key in ["notes", "anchors"]:
        for glyph in flat.get(key, []):
            glyph["x"] = _translated_x(float(glyph["x"]) * native_width, cuts) / new_width
    for system in flat.get("systems", []):
        system["left"] = _translated_x(float(system["left"]) * native_width, cuts) / new_width
        system["right"] = _translated_x(float(system["right"]) * native_width, cuts) / new_width
    flat["widths"] = [float(new_width)]
    flat["strip_size"] = Vector2(new_width, native_height)
    flat["strip_time_proportional"] = true
    flat["exact_ink_grid"] = true
    flat["exact_ink_grid_cuts"] = cuts.size()
    flat["exact_ink_grid_added_pixels"] = added
    var beat_grid: Dictionary = BeatCamera.prepare(flat)
    if not bool(beat_grid.get("enabled", false)):
        return _failure(original, "Exact ink spacing failed beat-grid audit: " + str(
            beat_grid.get("reason", "unknown")))
    var new_tile: Dictionary = source_tile.duplicate()
    new_tile["texture"] = ImageTexture.create_from_image(rearranged)
    new_tile["rect"] = Rect2(Vector2.ZERO, Vector2(new_width, native_height))
    new_tile["upload_bytes"] = new_width * native_height * 2
    result["tiles"] = [new_tile]
    result["size"] = Vector2(new_width, native_height)
    result["layout"] = flat
    return result
