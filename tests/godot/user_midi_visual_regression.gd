extends SceneTree
# Render *the actual ScoreStrip.build path* for a real user MIDI fixture.
# Input directory: layout.json + page-N.png. Output: native/production
# strip PNG tiles and a machine-readable mapping for pixel comparisons.

var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        push_error(message)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    if args.size() != 2:
        push_error("Usage: -- INPUT_DIR OUTPUT_DIR")
        quit(2)
        return
    var input_dir: String = args[0]
    var out_dir: String = args[1]
    DirAccess.make_dir_recursive_absolute(out_dir)
    var parsed: Variant = JSON.parse_string(
        FileAccess.get_file_as_string(input_dir.path_join("layout.json")))
    if not parsed is Dictionary:
        push_error("Expected a real Verovio layout.json")
        quit(2)
        return
    var original: Dictionary = parsed
    var pages: Array[Image] = []
    for index in range(int(original.get("pages", 0))):
        var path: String = input_dir.path_join("page-%d.png" % index)
        var img: Image = Image.load_from_file(path)
        check(img != null and not img.is_empty(), "Unreadable Verovio page: " + path)
        if img == null or img.is_empty():
            quit(1)
            return
        pages.append(img)
    var helper = load("res://score_strip.gd")
    var report := {"cases": {}, "source_note_count": original.get("notes", []).size(),
        "continuous_score": bool(original.get("continuous_score", false))}
    var untouched_strip: Dictionary = {}
    for mode in ["native", "production"]:
        # Exactly the same native setting as main.gd during ordinary playback:
        # fresh continuous exercises use native glyphs, other pieces use
        # the legacy time-proportional strip unless explicitly overridden.
        var untouched: bool = (mode == "native" or
            bool(original.get("continuous_score", false)))
        var result: Dictionary = helper.build(original, pages, false, untouched)
        if result.has("error"):
            check(false, mode + ": " + str(result.error))
            continue
        if mode == "native":
            untouched_strip = result
        var tiles: Array = result.tiles
        var mappings: Array = result.mappings
        var beat_grid: Dictionary = load("res://score_beat_camera.gd").prepare(
            result.layout)
        check(tiles.size() == mappings.size() and
            tiles.size() >= original.get("systems", []).size(),
            mode + ": lost an engraved system")
        # Sparse/ornament-heavy imported MIDI must not allocate a virtual
        # million-pixel score in order to keep all noteheads on a single
        # tempo-derived axis. Preserve the original engraving if too dense.
        var source_pixels_wide := 0.0
        for mapping in mappings:
            source_pixels_wide += float(mapping.crop.size.x)
        check(result.size.x <= source_pixels_wide * 8.0,
            mode + ": pathological full-score width: " + str(result.size.x))
        var output := {"tiles": [], "notes": [], "width": float(result.size.x),
            "height": float(result.size.y),
            "native": bool(result.layout.get("native_engraving", false)),
            "beat_camera": beat_grid,
            "timing_fallback": str(result.layout.get("strip_timing_fallback", "")),
            "proportional": bool(result.layout.get("strip_time_proportional", false))}
        for i in range(tiles.size()):
            var mapping: Dictionary = mappings[i]
            var tile: Dictionary = tiles[i]
            var pixels: Image = (tile.texture as Texture2D).get_image()
            var filename: String = "%s-tile-%d.png" % [mode, i]
            var saved: Error = pixels.save_png(out_dir.path_join(filename))
            check(saved == OK, "Cannot save " + filename)
            var crop: Rect2 = mapping.crop
            var rect: Rect2 = tile.rect
            var staff_rows: Array = []
            for line in mapping.system.get("staff_lines", []):
                staff_rows.append(float(line) * float(mapping.source_size.y) -
                    crop.position.y)
            output.tiles.append({
                "file": filename,
                "page": int(mapping.source_page),
                "crop": [int(crop.position.x), int(crop.position.y),
                    int(crop.size.x), int(crop.size.y)],
                "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
                "actual_width": pixels.get_width(),
                "actual_height": pixels.get_height(),
                "staff_rows": staff_rows,
                "warped": mapping.get("tempo_warp", []).size() > 0,
                "trimmed_header": bool(mapping.get("trimmed_header", false)),
                "spliced": int(mapping.get("splice_left", -1)) >= 0,
            })
        var mapped_ids: Dictionary = {}
        for src in original.get("notes", []):
            var note: Dictionary = helper.map_point(src, result.layout)
            var id: String = str(src.get("id", ""))
            check(not id.is_empty() and not mapped_ids.has(id),
                mode + ": lost/duplicate identity " + id)
            mapped_ids[id] = true
            check(int(note.get("page", -1)) == 0 and
                is_finite(float(note.get("x", NAN))) and
                is_finite(float(note.get("y", NAN))),
                mode + ": missing projected note " + id)
            output.notes.append({"id": id, "x": note.get("x", -1),
                "y": note.get("y", -1), "source_id": src.get("source_id", "")})
        check(mapped_ids.size() == original.get("notes", []).size(),
            mode + ": different number of projected notes")
        report.cases[mode] = output
    # A short lesson has one native Verovio system. Exercise Phase 1's
    # actual candidate layout against the same source pixels/IDs, regardless
    # of whether this specific passage can safely be represented on a grid.
    if bool(original.get("continuous_score", false)) and not untouched_strip.is_empty():
        var exact: Dictionary = load("res://score_exact_spacing.gd").reflow(
            untouched_strip)
        var enabled: bool = bool(exact["layout"].get("exact_ink_grid", false))
        var audit: Dictionary = load("res://score_beat_camera.gd").prepare(
            exact["layout"])
        if enabled:
            check(bool(audit.get("enabled", false)),
                "Exact Verovio layout failed to validate the transport beat grid")
            var native_notes: Array = untouched_strip["layout"]["notes"]
            var translated_notes: Array = exact["layout"]["notes"]
            check(native_notes.size() == translated_notes.size(),
                "Exact grid lost a Verovio source note")
            var source_pixels: Image = (
                untouched_strip["tiles"][0]["texture"] as Texture2D).get_image()
            var new_pixels: Image = (
                exact["tiles"][0]["texture"] as Texture2D).get_image()
            for k in range(mini(native_notes.size(), 80)):
                var before: Dictionary = native_notes[k]
                var after: Dictionary = translated_notes[k]
                check(str(before.get("id", "")) == str(after.get("id", "")),
                    "Exact Verovio group translation changed a source note ID")
                check(absf(float(before.get("y", 0.0)) -
                    float(after.get("y", 0.0))) < .000001,
                    "Lossless horizontal Verovio translation changed pitch height")
                var source_x: int = roundi(float(before.get("x", 0.0)) *
                    source_pixels.get_width())
                var output_x: int = roundi(float(after.get("x", 0.0)) *
                    new_pixels.get_width())
                var center_y: int = roundi(float(before.get("y", 0.0)) *
                    source_pixels.get_height())
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        var px: Vector2i = Vector2i(source_x + dx, center_y + dy)
                        var moved: Vector2i = Vector2i(output_x + dx, center_y + dy)
                        if Rect2i(Vector2i.ZERO, source_pixels.get_size()).has_point(px) \
                                and Rect2i(Vector2i.ZERO, new_pixels.get_size()).has_point(moved):
                            var ink: Color = source_pixels.get_pixelv(px)
                            var preserved: Color = new_pixels.get_pixelv(moved)
                            check(absf(ink.a - preserved.a) < .025 and
                                absf(ink.r - preserved.r) < .025,
                                "Verovio notehead pixel was resampled by Phase 1")
            check(new_pixels.save_png(out_dir.path_join("exact-tile-0.png")) == OK,
                "Cannot save actual exact-grid Verovio evidence")
        else:
            # The entire score is left alone if one beam/tie/slur blocks the
            # grid. Never mix partial warps with unchanged Verovio notation.
            check(exact["size"] == untouched_strip["size"],
                "Unsafe Verovio fallback resized its musical score")
        report["exact_ink_grid"] = {
            "enabled": enabled,
            "reason": str(exact["layout"].get("exact_ink_grid_reason", "")),
            "source_note_count": exact["layout"].get("notes", []).size(),
            "camera": audit,
            "added_pixels": exact["layout"].get("exact_ink_grid_added_pixels", 0)
        }
    var report_path: String = out_dir.path_join("godot-strip-report.json")
    var result_file: FileAccess = FileAccess.open(report_path, FileAccess.WRITE)
    if result_file == null:
        check(false, "Cannot write Godot visual regression report")
    else:
        result_file.store_string(JSON.stringify(report, "\t") + "\n")
        result_file.close()
    print("USER_MIDI_VISUAL_FAILURES:", failures.size())
    quit(1 if not failures.is_empty() else 0)
