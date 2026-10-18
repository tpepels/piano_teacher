extends SceneTree

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("FAIL: ", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    var original: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder + "/layout.json"))
    var pages: Array[Image] = []
    for page in range(int(original.pages)):
        pages.append(Image.load_from_file(folder + "/page-%d.png" % page))
    var helper = load("res://score_strip.gd")
    check(helper != null, "score strip helper must load")
    if helper == null:
        quit(1)
        return
    var probe_tile := {"rect": Rect2(500.0, 0.0, 100.0, 80.0)}
    check(not helper.tile_visible(probe_tile, 0.0, 1.0, 400.0, 50.0),
        "Far-right tile must not issue a draw call")
    check(helper.tile_visible(probe_tile, -250.0, 1.0, 400.0, 50.0),
        "Scrolling a tile into the viewport restores it immediately")
    check(helper.tile_visible(probe_tile, -100.0, 1.0, 400.0, 50.0),
        "Overscan protects the incoming edge of the raster")
    check(not helper.tile_visible(probe_tile, -2000.0, 1.0, 400.0, 50.0),
        "Far-left tile must no longer render")
    check(helper.tile_visible(probe_tile, 0.0, 1.0, 0.0, 50.0),
        "Unknown viewport must fail open, never hide the score")
    # Phase 8G: binary interval selection must agree with the old
    # per-tile predicate across scroll, zoom and both viewport boundaries.
    var many_tiles: Array = []
    var running_left := 0.0
    for n in range(80):
        var width: float = 37.0 + float(n % 7) * 9.0
        many_tiles.append({"rect": Rect2(running_left, 0, width, 100)})
        running_left += width
    var windows := [
        [-1200.0, 1.0, 500.0, 80.0],
        [-180.0, 1.0, 360.0, 0.0],
        [0.0, 1.0, 400.0, 100.0],
        [400.0, 1.0, 400.0, 40.0],
        [-4000.0, 2.0, 800.0, 100.0],
        [-100.0, .42, 480.0, 30.0],
        [-15000.0, 1.0, 400.0, 50.0],
        [-running_left - 500.0, 1.0, 400.0, 50.0]]
    for values in windows:
        var camera_x: float = float(values[0])
        var zoom: float = float(values[1])
        var view_width: float = float(values[2])
        var overscan: float = float(values[3])
        var visible_range: Vector2i = helper.visible_tile_range(
            many_tiles, camera_x, zoom, view_width, overscan)
        for i in range(many_tiles.size()):
            var expected: bool = helper.tile_visible(
                many_tiles[i], camera_x, zoom, view_width, overscan)
            check((i >= visible_range.x and i < visible_range.y) == expected,
                "8G interval search must match real raster visibility at tile %d" % i)
    check(helper.visible_tile_range([], 0, 1, 300, 50) == Vector2i.ZERO,
        "Empty scores have an empty visible interval")
    check(helper.visible_tile_range(many_tiles, 0, 0, 300, 50) ==
        Vector2i(0, many_tiles.size()), "Unusable viewport must preserve all notes")
    # Phase 8H: monochrome tile images use two channels, preserve
    # alpha and grayscale ink, and retain exact source pixel dimensions.
    var original_ink := Image.create(16, 12, false, Image.FORMAT_RGBA8)
    original_ink.fill(Color(1, 1, 1, 0))
    original_ink.set_pixel(0, 0, Color(0, 0, 0, 1))
    original_ink.set_pixel(1, 0, Color(.4, .4, .4, .6))
    original_ink.set_pixel(2, 0, Color(1, 1, 1, 1))
    var compact_ink: Image = helper.compact_monochrome_tile(original_ink)
    check(compact_ink.get_format() == Image.FORMAT_LA8,
        "8H must upload only luminance and alpha channels")
    check(compact_ink.get_data().size() == 16 * 12 * 2,
        "8H raw tile data must use two bytes per source pixel")
    check(compact_ink.get_size() == Vector2i(16, 12),
        "8H must not rescale or re-engrave the source score")
    check(compact_ink.get_pixel(0, 0).r < .02 and
        compact_ink.get_pixel(0, 0).a > .98,
        "solid note ink must survive the image conversion")
    check(absf(compact_ink.get_pixel(1, 0).r - .4) < .02 and
        absf(compact_ink.get_pixel(1, 0).a - .6) < .02,
        "grayscale antialiasing and note transparency are preserved")
    check(compact_ink.get_pixel(2, 0).r > .98,
        "opaque page white remains white for the notation shader")
    var gpu_texture := ImageTexture.create_from_image(compact_ink)
    check(gpu_texture != null and gpu_texture.get_size() == Vector2(16, 12),
        "Godot can create a real graphics texture from compact notation")
    var no_pages: Array[Image] = []
    check(not str(helper.build({}, no_pages).get("error", "")).is_empty(),
          "missing measured systems must return an explicit error")
    check(not str(helper.build(original, no_pages).get("error", "")).is_empty(),
          "missing score pages must return an explicit error")
    # A one-system lesson must retain full image height, not the SVG
    # notehead-origin staff box. Otherwise high ledger notes and long stems
    # disappear BEFORE the Godot viewport can fit their bounding ink.
    var high_ink := Image.create(100, 100, false, Image.FORMAT_RGBA8)
    high_ink.fill(Color.TRANSPARENT)
    high_ink.fill_rect(Rect2i(45, 2, 9, 8), Color.BLACK)
    var high_lines: Array = [.30, .35, .40, .45, .50,
        .60, .65, .70, .75, .80]
    var high_layout := {"continuous_score":true,
        "strip_time_proportional":false, "strip_trim_repeated_headers":false,
        "pages":1, "widths":[100], "heights":[100], "beats":4.0,
        "notes":[], "anchors":[{"beat":0.0, "page":0, "system":"only",
            "x":.5, "y":.4, "ink_left":.45}],
        "systems":[{"page":0, "system":"only", "left":0.0, "right":1.0,
            "top":.28, "bottom":.82, "staff_lines":high_lines,
            "start_beat":0.0, "end_beat":4.0}]}
    var high_pages: Array[Image] = [high_ink]
    var high_strip: Dictionary = helper.build(high_layout, high_pages, false, true)
    check(not high_strip.has("error"),
        "A continuous lesson with extreme ledger notes builds")
    if not high_strip.has("error"):
        var source_crop: Rect2 = high_strip.mappings[0].crop
        check(source_crop.position.y == 0.0 and source_crop.size.y == 100.0,
            "Continuous ink crop retains the full original vertical page")
        var high_tile: Image = high_strip.tiles[0].texture.get_image()
        check(high_tile.get_pixel(49, 4).a > .9,
            "High note ink stays visible above the measured staff box")
    # Phase 7.7a: only loose raster staff rails may disappear at
    # joins; a real vertical measure barline must survive untouched.
    var synthetic := Image.create(80, 70, false, Image.FORMAT_RGBA8)
    synthetic.fill(Color.TRANSPARENT)
    for x in range(80):
        synthetic.set_pixel(x, 15, Color.BLACK)
        synthetic.set_pixel(x, 25, Color.BLACK)
    for y in range(10, 31):
        synthetic.set_pixel(75, y, Color.BLACK)
    var synthetic_mapping := {
        "system": {"staff_lines": [15.0 / 70.0, 25.0 / 70.0]},
        "source_size": Vector2(80, 70),
        "crop": Rect2(0, 0, 80, 70),
        "trimmed_header": true, "entry_padding": 0}
    var removed: int = helper._clear_join_rails(synthetic,
        synthetic_mapping, true, true)
    check(removed > 0, "seam cleanup must remove orphaned staff-rule ink")
    check(synthetic.get_pixel(0, 15).a < .01 and synthetic.get_pixel(79, 15).a < .01,
        "staff joins must be supplied by the continuous rails, not tile ends")
    check(synthetic.get_pixel(40, 15).a > .9,
        "staff ink away from tile joins must remain")
    check(synthetic.get_pixel(75, 20).a > .9 and synthetic.get_pixel(75, 15).a > .9,
        "a real barline near the system end must never be erased")
    # Enlarging musical time must not enlarge a rest or accidental glyph.
    # Native ink copied either side of an empty gap stays pixel-for-pixel
    # identical, unlike the former bilinear stretch of whole musical strips.
    var ink_test := Image.create(120,48,false,Image.FORMAT_RGBA8)
    ink_test.fill(Color.TRANSPARENT)
    for x in range(45,51):
        for y in range(12,18):
            ink_test.set_pixel(x,y,Color.BLACK)
    var stretched_ink: Image = load("res://tempo_strip.gd").warp_image(ink_test,
        [Vector2(0,0),Vector2(20,20),Vector2(90,210),Vector2(120,240)])
    check(stretched_ink.get_width() == 240,
        "Added beat spacing must extend only the horizontal score canvas")
    var ink_pixels := 0
    for x in range(stretched_ink.get_width()):
        if stretched_ink.get_pixel(x,14).a > .5:
            ink_pixels += 1
    check(ink_pixels == 6,
        "Rest symbol must keep original pixel width when adding empty space")
    # Binary tempo projection must be byte-for-byte equivalent to the
    # former first-right-edge linear mapping, including exact control
    # points, duplicated edges, and beyond-the-end positions.
    var tempo_mapper = load("res://tempo_strip.gd")
    var control_points: Array = []
    for ci in range(150):
        var cx: float = float(ci * 13)
        var cy: float = float(ci * 21)
        control_points.append(Vector2(cx, cy))
    for sample_idx in range(-5, 2040, 3):
        var source_coord: float = float(sample_idx)
        var reference: float = 0.0
        var reached := false
        for ci in range(control_points.size()-1):
            var a: Vector2 = control_points[ci]
            var b: Vector2 = control_points[ci+1]
            if source_coord <= b.x:
                reference = lerpf(a.y, b.y,
                    clampf((source_coord-a.x)/(b.x-a.x), 0.0, 1.0))
                reached = true
                break
        if not reached:
            var final: Vector2 = control_points[-1]
            reference = final.y + maxf(0.0, source_coord-final.x)
        check(absf(tempo_mapper.project(source_coord, control_points)-reference) < .001,
            "Indexed tempo mapping must preserve exact notation geometry")
    # 7.7a: the full staff is owned by one continuous layer, not by
    # individual printed system rasters with visible horizontal endings.
    # Keep a genuine end-of-measure barline and a notehead crossing a line.
    var continuous := Image.create(110, 80, false, Image.FORMAT_RGBA8)
    continuous.fill(Color.TRANSPARENT)
    for x in range(110):
        for y in [17, 27, 37, 47, 57]:
            continuous.set_pixel(x, y, Color.BLACK)
    for y in range(10, 66):
        continuous.set_pixel(103, y, Color.BLACK) # real barline
    for x in range(48, 58):
        for y in range(23, 32):
            continuous.set_pixel(x, y, Color.BLACK) # engraved notehead
    var complete_mapping := {
        "system":{"staff_lines":[17.0 / 80.0, 27.0 / 80.0,
            37.0 / 80.0, 47.0 / 80.0, 57.0 / 80.0]},
        "source_size":Vector2(110, 80), "crop":Rect2(0, 0, 110, 80)}
    var replaced: int = helper._extract_isolated_staff_rules(
        continuous, complete_mapping)
    check(replaced > 350,
        "the entire isolated raster staff must be replaced, not just its ends")
    for x in [0, 12, 39, 80, 109]:
        check(continuous.get_pixel(x, 27).a < .01,
            "all isolated staff rules must come from the continuous canvas")
    check(continuous.get_pixel(53, 27).a > .99 and
        continuous.get_pixel(53, 25).a > .99,
        "a real notehead crossing a staff line must retain its native ink")
    check(continuous.get_pixel(103, 37).a > .99 and
        continuous.get_pixel(103, 41).a > .99,
        "the genuine barline must survive, including intersections")
    check(continuous.get_pixel(2, 12).a < .01,
        "rail extraction must not manufacture other glyphs")
    # Exact musical events get equal pixel distances, but noteheads are
    # copied from Verovio at their original widths. The protected note core
    # must be byte-for-byte preserved after extending spaces between beats.
    var tempo = load("res://tempo_strip.gd")
    var tempo_pixels := Image.create(110, 36, false, Image.FORMAT_RGBA8)
    tempo_pixels.fill(Color.TRANSPARENT)
    for center in [20, 50, 80]:
        for x in range(center-5,center+6):
            for y in range(15,22):
                tempo_pixels.set_pixel(x,y,Color.BLACK)
    var positions: Array = [20.0,50.0,80.0]
    var goals: Array = [20.0,60.0,100.0]
    var controls: Array = tempo.controls(positions,goals,110,10.0)
    var stretched: Image = tempo.warp_image(tempo_pixels,controls)
    check(stretched.get_width() == 130,
        "Tempo-based gap stretching must increase scroll width predictably")
    for index in range(3):
        var x: int = roundi(tempo.project(float(positions[index]),controls))
        check(absf(float(x)-float(goals[index])) < 1,
            "Original attack coordinates map exactly to quarter beats")
        for dx in range(-4,5):
            check(stretched.get_pixel(x+dx,18).a > .99,
                "Engraved noteheads must not become stretched or disappear")
    # Huge inserted gaps must not become huge textures or force a fallback
    # to native, uneven spacing. A core at a GPU-sized coordinate stays whole.
    var wide_goals: Array = [20.0, 8192.0, 20000.0]
    var wide_controls: Array = tempo.controls(positions, wide_goals, 110, 10.0)
    var wide_segments: Array = tempo.warp_segments(tempo_pixels, wide_controls)
    var previous_edge := 0
    for segment in wide_segments:
        check(segment.x == previous_edge and segment.image.get_width() <= tempo_pixels.get_width(),
            "Wide proportional notation is contiguous with bounded native textures")
        previous_edge = segment.x + segment.width
    check(previous_edge == roundi(wide_controls[-1].y),
        "Sparse textures cover the complete proportional canvas")
    for target_x in [8192, 20000]:
        for dx in range(-4, 5):
            var found_ink := false
            for segment in wide_segments:
                if target_x+dx >= segment.x and target_x+dx < segment.x+segment.width:
                    var native_x: int = roundi(float(target_x+dx-segment.x)*segment.image.get_width()/segment.width)
                    found_ink = segment.image.get_pixel(native_x,18).a > .99
            check(found_ink, "A GPU-sized coordinate preserves native-width attack pixels")
    var connected_ink := Image.create(110, 36, false, Image.FORMAT_RGBA8)
    connected_ink.fill(Color.TRANSPARENT)
    connected_ink.fill_rect(Rect2i(0,12,110,6), Color.BLACK)
    var connected_segments: Array = tempo.warp_segments(connected_ink,
        [Vector2.ZERO, Vector2(110,20000)])
    check(connected_segments.size() == 1 and connected_segments[0].width == 20000,
        "Connected beam or tie stays in one logical interval across GPU-sized coordinates")
    if connected_segments.size() == 1:
        check(connected_segments[0].image.get_data() == connected_ink.get_data(),
            "Connected notation retains every original pixel without independent boundary resampling")
    var strip: Dictionary = helper.build(original, pages)
    # Phase 1 checkpoint: real Verovio PNGs must remain unspliced, not
    # horizontally warped.  This is the mode used by the practice screen.
    var native_strip: Dictionary = helper.build(original, pages, false, true)
    check(not native_strip.has("error"), "native notation must build successfully")
    if not native_strip.has("error"):
        check(bool(native_strip.layout.get("native_engraving", false)),
            "practice notation exposes the source-ink mode for diagnostics")
        check(native_strip.tiles.size() == original.systems.size(),
            "native mode keeps exactly one untouched glyph crop per source system")
        check(not bool(original.get("native_engraving", false)),
            "native mode must not mutate the caller's authoritative layout")
        for mapping in native_strip.mappings:
            check(mapping.get("tempo_warp", []).is_empty() and
                int(mapping.get("tempo_gap", 0)) == 0 and
                int(mapping.get("entry_padding", 0)) == 0,
                "native glyph tiles have no independent time warp or inserted gaps")
            check(int(mapping.get("splice_left", -1)) == -1 and
                int(mapping.get("splice_right", -1)) == -1 and
                not bool(mapping.get("trimmed_header", false)),
                "native notation cannot splice staff or chop a repeated header")
        for i in range(native_strip.tiles.size()):
            var mapping: Dictionary = native_strip.mappings[i]
            var tile: Dictionary = native_strip.tiles[i]
            check(absf(tile.rect.size.x - mapping.crop.size.x) <= .01,
                "source notation tile width must never be stretched")
        for note in original.get("notes", []):
            var mapped_note: Dictionary = helper.map_point(note, native_strip.layout)
            check(mapped_note.get("page", -1) == 0 and
                is_finite(float(mapped_note.get("x", NAN))),
                "native musical note positions remain available for the MIDI overlay")
    # Phase 8I: compare deferred CPU-packed tiles to the same real
    # Verovio engraving built with eager texture upload.
    var deferred: Dictionary = helper.build(original, pages, true)
    check(not deferred.has("error") and deferred.tiles.size() == strip.tiles.size(),
        "Deferred build preserves every engraved system")
    var packed_bytes := 0
    var raw_bytes := 0
    var indexes: Array[int] = [0, int(strip.tiles.size() / 2), strip.tiles.size() - 1]
    for tile_index in range(deferred.tiles.size()):
        var packed_tile: Dictionary = deferred.tiles[tile_index]
        packed_bytes += int(packed_tile.packed_ink.size())
        raw_bytes += int(packed_tile.upload_bytes)
        check(not packed_tile.has("texture"),
            "Offscreen packed tiles must never hold eager GPU textures")
        check(packed_tile.rect == strip.tiles[tile_index].rect,
            "Packing cannot change the canonical staff and note transforms")
        if indexes.has(tile_index):
            var recovered: Texture2D = helper.tile_texture(packed_tile)
            check(recovered != null,
                "Viewport must restore a real GPU texture on first entry")
            if recovered != null:
                var recovered_img: Image = recovered.get_image()
                var original_img: Image = strip.tiles[tile_index].texture.get_image()
                check(recovered_img.get_size() == original_img.get_size(),
                    "Seek restores original raster dimensions")
                for px in [Vector2i(0, 0),
                           Vector2i(int(recovered_img.get_width() / 2),
                               int(recovered_img.get_height() / 2)),
                           Vector2i(recovered_img.get_width() - 1,
                               recovered_img.get_height() - 1)]:
                    var a: Color = recovered_img.get_pixelv(px)
                    var b: Color = original_img.get_pixelv(px)
                    check(absf(a.r - b.r) < .02 and absf(a.a - b.a) < .02,
                        "8I decompressed score ink must agree with eager GPU texture")
    check(packed_bytes < raw_bytes,
        "Monochrome raster must compress smaller than raw LA8 tile memory")
    var invalid_packed: Dictionary = deferred.tiles[0].duplicate()
    invalid_packed["packed_ink"] = PackedByteArray()
    check(helper.tile_texture(invalid_packed) == null,
        "Corrupt deferred ink must fail explicitly rather than show false notes")
    var flat: Dictionary = strip.layout
    check(strip.tiles.size() == original.systems.size(), "every system becomes a tile")
    if bool(original.get("strip_trim_repeated_headers", false)):
        var cleaned_tiles := 0
        for mapping in strip.mappings:
            if int(mapping.get("rail_pixels_replaced", 0)) > 0:
                cleaned_tiles += 1
        check(cleaned_tiles == strip.mappings.size(),
            "all generated systems, not just seam edges, replace their isolated raster staff rules")
    # Compare identical real SVG tiles with and without the safe repeated
    # header removal. The score must not stretch or re-synthesize any note.
    if bool(original.get("strip_trim_repeated_headers", false)) and original.systems.size() > 1:
        var with_headers: Dictionary = original.duplicate(true)
        with_headers["strip_trim_repeated_headers"] = false
        var baseline: Dictionary = helper.build(with_headers, pages)
        check(not baseline.has("error"), "untrimmed control strip must render")
        check(baseline.tiles.size() == strip.tiles.size(),
            "trimming cannot drop a musical system")
        var safety_splices := 0
        for item in strip.mappings:
            if int(item.get("splice_right", -1)) > int(item.get("splice_left", -1)) \
                    and int(item.get("splice_left", -1)) >= 0:
                safety_splices += 1
        print("SCROLL_SAFE_SPLICES:", safety_splices)
        var shortened := 0
        for i in range(1, strip.mappings.size()):
            var after: Dictionary = strip.mappings[i]
            var before: Dictionary = baseline.mappings[i]
            check(after.crop.position.x >= before.crop.position.x,
                "repeated header removal cannot reveal extra unused page margin")
            check(after.crop.end.x <= before.crop.end.x,
                "trimming cannot add unnecessary trailing page width")
            if bool(after.get("trimmed_tail", false)):
                var original_barline: float = float(after.system.get("last_barline_x", -1.0))
                check(original_barline >= 0.0 and float(after.crop.end.x) >
                    original_barline * float(after.source_size.x) + 3.0,
                    "the actual final barline must remain visible after tail trimming")
            if bool(after.get("trimmed_header", false)):
                shortened += 1
                check(after.crop.size.x < before.crop.size.x,
                    "repeated header must actually shorten this system")
                var earliest_ink := INF
                for source in original.anchors:
                    if int(source.page) == int(after.source_page) and str(source.system) == str(after.source_system):
                        earliest_ink = minf(earliest_ink, float(source.ink_left))
                check(after.crop.position.x + 8 < earliest_ink * float(after.source_size.x),
                    "cropping must leave the earliest engraved accidental and note ink untouched")
        check(shortened > 0, "real generated multi-system lesson should have repeated header clearance")
        # Time-proportional spacing may legitimately *widen* the whole
        # strip to keep notes in lockstep with the metronome. The important
        # crop invariant is that repeated headers are absent; score width
        # is now determined by beats, not by printed-page justification.
        check(strip.size.x > 0 and baseline.size.x > 0,
            "both native and tempo-proportional strips must have positive width")
        for a in range(flat.anchors.size() - 1):
            var source_left: Dictionary = original.anchors[a]
            var source_right: Dictionary = original.anchors[a+1]
            if str(source_left.system) == str(source_right.system) and source_left.page == source_right.page:
                continue
            var gap: float = float(source_right.beat) - float(source_left.beat)
            if gap > .00001:
                var before_gap: float = (float(baseline.layout.anchors[a+1].x) -
                    float(baseline.layout.anchors[a].x)) * float(baseline.size.x)
                var after_gap: float = (float(flat.anchors[a+1].x) -
                    float(flat.anchors[a].x)) * float(strip.size.x)
                check(after_gap <= before_gap + .01,
                    "removing a repeat header cannot increase camera velocity at a system join")
    
    check(flat.notes.size() == original.notes.size(), "all original noteheads survive")
    check(flat.pages == 1, "flattened score has one virtual page")
    var previous_right := 0.0
    var first_line := -1.0
    var rail_positions: Array = []
    for index in range(strip.tiles.size()):
        var tile: Dictionary = strip.tiles[index]
        var rect: Rect2 = tile.rect
        check(int(tile.get("upload_bytes", -1)) ==
            int(rect.size.x) * int(rect.size.y) * 2,
            "8H every uploaded engraving tile uses two bytes per raster pixel")
        check(absf(rect.position.x - previous_right) < .01, "system tiles join horizontally")
        previous_right = rect.end.x
        var line: float = float(flat.systems[index].staff_lines[0]) * strip.size.y
        if first_line < 0.0:
            first_line = line
        check(absf(line - first_line) < .01, "first staff line stays level across pages")
        var lines: Array = flat.systems[index].staff_lines
        if rail_positions.is_empty():
            for y in lines:
                rail_positions.append(float(y) * strip.size.y)
        check(lines.size() == rail_positions.size(), "systems retain the same piano staff lines")
        for rail in range(mini(lines.size(), rail_positions.size())):
            check(absf(float(lines[rail]) * strip.size.y - float(rail_positions[rail])) < .1,
                  "all piano staff lines stay level across systems and pages")
    check(absf(previous_right - strip.size.x) < .01, "strip width covers every tile")
    if bool(original.get("strip_trim_repeated_headers", false)):
        var proportional_speeds: Array[float] = []
        for i in range(flat.anchors.size()-1):
            var start: Dictionary = flat.anchors[i]
            var end: Dictionary = flat.anchors[i+1]
            var duration: float = float(end.beat)-float(start.beat)
            if duration <= .00001:
                continue
            proportional_speeds.append((float(end.x)-float(start.x))*
                float(strip.size.x)/duration)
        check(proportional_speeds.size() > 5,
            "actual Verovio note positions must test many rhythmic intervals")
        if proportional_speeds.size() > 5:
            proportional_speeds.sort()
            var expected: float = proportional_speeds[proportional_speeds.size()/2]
            for rate in proportional_speeds:
                check(absf(float(rate)-expected) <= maxf(1.5,expected*.012),
                    "Every source beat, including a system wrap, must take the same number of pixels")
            print("TEMPO_PROPORTIONAL_AUDIT: rate=", snappedf(expected,.01),
                " deviation=", snappedf(proportional_speeds[-1]-
                proportional_speeds[0],.01), " beats=", proportional_speeds.size())
    # Quantify the musical pixel velocity the real camera must follow.
    # This is the exact Verovio geometry mapped into Godot texture pixels,
    # including accidentals, measure boundaries and joined print systems.
    var velocities: Array[float] = []
    var join_velocities: Array[float] = []
    var unchanged_velocities: Array[float] = []
    for i in range(flat.anchors.size() - 1):
        var left_anchor: Dictionary = flat.anchors[i]
        var right_anchor: Dictionary = flat.anchors[i+1]
        var beats: float = float(right_anchor.beat) - float(left_anchor.beat)
        if beats <= .000001:
            continue
        var pixels: float = (float(right_anchor.x) - float(left_anchor.x)) * strip.size.x
        var velocity: float = pixels / beats
        check(velocity >= -.01, "music must never pan backward as beats increase")
        if velocity < 0:
            continue
        velocities.append(velocity)
        var src_left: Dictionary = original.anchors[i]
        var src_right: Dictionary = original.anchors[i+1]
        if int(src_left.page) != int(src_right.page) or str(src_left.system) != str(src_right.system):
            join_velocities.append(velocity)
            var first_ink_offset := -1.0
            var previous_tail := -1.0
            var trailing_after_barline := -1.0
            for i_mapping in range(strip.mappings.size()):
                var destination: Dictionary = strip.mappings[i_mapping]
                if int(destination.source_page) == int(src_right.page) and str(destination.source_system) == str(src_right.system):
                    first_ink_offset = float(src_right.x) * float(destination.source_size.x) - float(destination.crop.position.x)
                if int(destination.source_page) == int(src_left.page) and str(destination.source_system) == str(src_left.system):
                    previous_tail = float(destination.crop.end.x) - float(src_left.x) * float(destination.source_size.x)
                    if int(destination.get("splice_left", -1)) >= 0:
                        previous_tail -= float(int(destination.get("splice_right", -1)) -
                            int(destination.get("splice_left", -1)))
                    var final_barline: float = float(destination.system.get("last_barline_x", -1.0))
                    if final_barline >= 0.0:
                        trailing_after_barline = float(destination.crop.end.x) - final_barline * float(destination.source_size.x)
            print("SCROLL_JOIN_DETAIL: beat=", float(src_right.beat),
                " duration=", beats, " pixels=", snappedf(pixels, .1),
                " from_end=", snappedf(previous_tail, .1),
                " to_first=", snappedf(first_ink_offset, .1),
                " after_barline=", snappedf(trailing_after_barline, .1))
        else:
            unchanged_velocities.append(velocity)
    if not unchanged_velocities.is_empty() and not join_velocities.is_empty():
        unchanged_velocities.sort()
        join_velocities.sort()
        var typical: float = unchanged_velocities[unchanged_velocities.size() / 2]
        var fastest_join: float = join_velocities[-1]
        var slowest_join: float = join_velocities[0]
        print("SCROLL_VELOCITY_AUDIT: typical=", snappedf(typical, .01),
            " join_min=", snappedf(slowest_join, .01),
            " join_max=", snappedf(fastest_join, .01),
            " join_max_ratio=", snappedf(fastest_join / maxf(1.0, typical), .001),
            " inside=", unchanged_velocities.size(), " joins=", join_velocities.size(),
            " trim=", bool(original.get("strip_trim_repeated_headers", false)))
        check(is_finite(typical) and typical > 0,
            "real music must have a positive finite pixel travel per beat")
    var previous_beat := -INF
    var previous_x := -INF
    for index in range(flat.anchors.size()):
        var anchor: Dictionary = flat.anchors[index]
        var original_anchor: Dictionary = original.anchors[index]
        var ink_point: Dictionary = original_anchor.duplicate(true)
        ink_point.x = original_anchor.ink_left
        var expected_ink: Dictionary = helper.map_point(ink_point, flat)
        check(absf(float(anchor.ink_left) - float(expected_ink.x)) < .000001,
              "opening accidentals and ledger bounds share the notehead transform")
        check(anchor.page == 0 and anchor.system == "strip", "anchors share the virtual staff")
        check(float(anchor.beat) >= previous_beat, "anchors remain in musical order")
        check(float(anchor.x) >= previous_x - .00001, "no backwards sweep at a system wrap")
        previous_beat = float(anchor.beat)
        previous_x = float(anchor.x)
    # Marker positions, including missing system metadata, must match
    # the original scan behavior after indexing source note IDs.
    if not original.get("notes", []).is_empty():
        var source_note: Dictionary = original.notes[0]
        var note_id: String = str(source_note.get("id", ""))
        if not note_id.is_empty():
            check(flat.strip_note_system_index.has(note_id),
                "Built score provides an indexed source system for its notes")
            var by_id: Dictionary = source_note.duplicate(true)
            by_id.erase("source_system")
            by_id.erase("system")
            by_id["note_id"] = note_id
            var indexed: Dictionary = helper.map_point(by_id, flat)
            var explicit: Dictionary = helper.map_point(source_note, flat)
            check(absf(float(indexed.get("x", -1.0)) -
                float(explicit.get("x", -2.0))) < .00001,
                "Indexed feedback note must retain the exact engraving x")
    # Living cues reuse the very same Verovio attacks that were positioned
    # onto the real strip tiles above. Test an actual grand-staff chord,
    # single-note errors and rests without a separate simulated score.
    var living = load("res://living_score.gd")
    check(living != null, "Living score note selector must load")
    var attacks: Array = []
    for note in flat.notes:
        if bool(note.get("is_attack", false)):
            attacks.append(note)
    attacks.sort_custom(func(a: Dictionary, b: Dictionary):
        return float(a.get("source_beat", a.beat)) < float(b.get("source_beat", b.beat)))
    check(not attacks.is_empty(), "Real engraving should expose canonical source attacks")
    if not attacks.is_empty() and living != null:
        var first_beat: float = float(attacks[0].get("source_beat", attacks[0].beat))
        var onset_index: Array = living.prepare(flat)
        check(living.crosses_onset(onset_index, first_beat - .12, first_beat + .01),
            "Playhead should react at the engraved note's real timing")
        check(not living.crosses_onset(onset_index, first_beat + .01, first_beat + .09),
            "One arrival must not replay a pulse during subsequent frames")
        check(not living.crosses_onset(onset_index, first_beat, first_beat),
            "A stopped or paused playhead must not emit a timing pulse")
        var chord: Array = living.next_chord(flat, first_beat - .3)
        var indexed: Array = living.prepare(flat)
        check(living.cue(indexed, first_beat - .3) == chord,
            "Indexed moving-score lookahead disagrees with real note positions")
        check(not chord.is_empty(), "At least one real note must be highlighted")
        var right := false
        var left := false
        for cue in chord:
            var matching := false
            for original_note in flat.notes:
                if str(original_note.id) == str(cue.id):
                    matching = absf(float(original_note.x)-float(cue.x)) < .0000001
                    matching = matching and absf(float(original_note.y)-float(cue.y)) < .0000001
                    break
            check(matching, "Cue lost the canonical notehead position")
            right = right or str(cue.hand) == "right"
            left = left or str(cue.hand) == "left"
        var source_hands: Dictionary = {}
        for note in attacks:
            source_hands[str(note.get("hand", ""))] = true
        if source_hands.has("right") and source_hands.has("left"):
            check(right and left, "The next-chord display omits one physical hand")
        var missed_id: String = str(chord[0].id)
        var red: Array = living.next_chord(flat, first_beat, [
            {"note_id":missed_id, "status":"missed"}])
        check(red.size() == chord.size()-1,
            "Marking one pitch missed must not hide correct chord neighbours")
        for cue in red:
            check(str(cue.id) != missed_id, "A red note must not also glow green")
        var ended: Array = living.next_chord(flat, float(flat.beats)+100)
        check(ended.is_empty(), "No invented cues after the last score note")
        # Where sparse original music leaves a real rest, the cue disappears
        # instead of falsely holding the previously played chord.
        var subsequent := INF
        for attack in attacks:
            var source_beat: float = float(attack.get("source_beat", attack.beat))
            if source_beat > first_beat+.2:
                subsequent = source_beat
                break
        if is_finite(subsequent) and subsequent-first_beat > 2.0:
            check(living.next_chord(flat, first_beat + .2).is_empty(),
                "A long source rest must not show a premature next-chord cue")
    var terminal: Dictionary = original.anchors[-1]
    var end_mark := {"page": terminal.page, "x": terminal.x,
        "y": float(terminal.top) - .02, "beat": float(flat.beats), "status": "extra"}
    var expected_mark: Dictionary = end_mark.duplicate(true)
    expected_mark["system"] = terminal.system
    var expected_end: Dictionary = helper.map_point(expected_mark, flat)
    var mapped_end: Dictionary = helper.map_point(end_mark, flat)
    check(mapped_end.page == 0, "terminal extra on the last source page maps to virtual page zero")
    check(absf(float(mapped_end.x) - float(expected_end.x)) < .000001,
          "terminal extra exactly at exercise end retains the final-system transform")
    check(absf(float(mapped_end.y) - float(expected_end.y)) < .000001,
          "terminal extra keeps its vertical feedback position")
    var checked_join := false
    for index in range(original.anchors.size() - 1):
        var before: Dictionary = original.anchors[index]
        var after: Dictionary = original.anchors[index + 1]
        if before.page == after.page and before.system == after.system:
            continue
        if float(after.beat) <= float(before.beat):
            continue
        var midpoint: float = (float(before.beat) + float(after.beat)) * .5
        # The source-page locator holds its final glyph at a wrap; the
        # virtual strip continues across the join during a held note.
        var extra_at_join := {"page": before.page, "x": before.x,
            "y": float(before.top) - .02, "beat": midpoint,
            "status": "extra", "estimated": true}
        var joined: Dictionary = helper.map_point(extra_at_join, flat)
        var expected_x: float = (float(flat.anchors[index].x) + float(flat.anchors[index+1].x)) * .5
        check(absf(float(joined.x) - expected_x) < .000001,
              "estimated extra between systems follows the continuous strip cursor")
        checked_join = true
        break
    if original.systems.size() > 1:
        check(checked_join, "multi-system fixture exercises a time-bearing system join")
    for index in range(flat.notes.size()):
        var note: Dictionary = flat.notes[index]
        var source: Dictionary = original.notes[index]
        var mapped: Dictionary = helper.map_point(source, strip)
        check(note.page == 0 and note.system == "strip", "notes share the virtual staff")
        check(absf(float(mapped.x) - float(note.x)) < .000001, "feedback shares note x transform")
        check(absf(float(mapped.y) - float(note.y)) < .000001, "feedback shares note y transform")
        var mark: Dictionary = source.duplicate(true)
        mark["note_id"] = mark["id"]
        mark.erase("system")
        mark.erase("id")
        var feedback: Dictionary = helper.map_point(mark, flat)
        check(absf(float(feedback.x) - float(note.x)) < .000001,
              "backend note feedback without system retains exact alignment")
        mark.erase("note_id")
        var extra: Dictionary = helper.map_point(mark, flat)
        check(absf(float(extra.x) - float(note.x)) < .000001,
              "extra-note feedback locates its system by beat")
        check(note.source_page == source.page, "original page identity is preserved")
        var xy: Vector2 = Vector2(float(note.x), float(note.y)) * strip.size
        var has_ink := false
        for tile in strip.tiles:
            if tile.rect.has_point(xy):
                var local: Vector2 = xy - tile.rect.position
                var image: Image = tile.texture.get_image()
                var sample := Rect2i(int(local.x)-1, int(local.y)-2, 9, 5).intersection(
                    Rect2i(Vector2i.ZERO, image.get_size()))
                var alpha_max := 0.0
                for y in range(sample.position.y, sample.end.y):
                    for x in range(sample.position.x, sample.end.x):
                        alpha_max = maxf(alpha_max, image.get_pixel(x, y).a)
                has_ink = alpha_max > .5
                break
        check(has_ink, "flattened notehead lands on real texture ink")
    print("SCORE_STRIP_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
