extends SceneTree

# Phase 6: use *real* source layout and raster PNGs emitted by Python/Verovio.
# No fake note positions, scoring, or mocked score-strip transformations.
var failures: Array[String] = []


func _initialize() -> void:
    call_deferred("_run")


func _check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        push_error("PHASE6_GODOT_FAIL: " + message)


func _run() -> void:
    var arguments := OS.get_cmdline_user_args()
    if arguments.is_empty():
        push_error("Expected diagnostic artifact directory")
        quit(2)
        return
    var folder: String = arguments[0]
    var helper = preload("res://notation/legacy/strip.gd")
    var manifests: Array = []
    var directory := DirAccess.open(folder)
    if directory == null:
        push_error("No diagnostic artifact directory")
        quit(2)
        return
    directory.list_dir_begin()
    while true:
        var filename: String = directory.get_next()
        if filename.is_empty():
            break
        if filename.begins_with("sample-") and filename.ends_with(".json"):
            manifests.append(filename)
    directory.list_dir_end()
    manifests.sort()
    _check(not manifests.is_empty(), "No real engraved samples to display")
    for filename in manifests:
        var manifest: Variant = JSON.parse_string(
            FileAccess.get_file_as_string(folder.path_join(filename)))
        if not manifest is Dictionary:
            _check(false, "Malformed engraving manifest: " + filename)
            continue
        var source: Dictionary = manifest.get("layout", {})
        var pages: Array[Image] = []
        for page_name in manifest.get("pages", []):
            var image := Image.new()
            var error := image.load(folder.path_join(str(page_name)))
            _check(error == OK, "Cannot decode raster page: " + str(page_name))
            if error == OK:
                pages.append(image)
        if pages.size() != manifest.get("pages", []).size():
            continue
        var built: Dictionary = helper.build(source, pages)
        _check(not built.has("error"), "Cannot build score strip: " + str(built.get("error", "")))
        if built.has("error"):
            continue
        var flat: Dictionary = built["layout"]
        _check(flat["notes"].size() == source.get("notes", []).size(),
            "A source notehead disappeared from the visible score")
        _check(built["tiles"].size() == source.get("systems", []).size(),
            "A source staff system disappeared from the score strip")
        _check(int(flat["pages"]) == 1, "Navigation must use one virtual horizontal score")
        var previous_x := -INF
        var previous_beat := -INF
        for anchor in flat.get("anchors", []):
            var x: float = float(anchor.get("x", -1.0))
            var beat: float = float(anchor.get("beat", -1.0))
            _check(beat >= previous_beat-0.00001, "Score beats move backwards")
            _check(x >= previous_x-0.00001, "Moving cursor moves backwards across a staff join")
            previous_x = x
            previous_beat = beat
        for i in range(flat.get("notes", []).size()):
            var original: Dictionary = source["notes"][i]
            var note: Dictionary = flat["notes"][i]
            var mapped: Dictionary = helper.map_point(original, flat)
            _check(int(note["page"]) == 0, "Visible notehead is on wrong virtual page")
            _check(absf(float(note["x"])-float(mapped["x"])) < 0.00001,
                "Visual x and source note x disagree")
            _check(absf(float(note["y"])-float(mapped["y"])) < 0.00001,
                "Visual y and source note y disagree")
            var mark: Dictionary = original.duplicate(true)
            mark["note_id"] = mark.get("id", "")
            mark.erase("system")
            mark.erase("id")
            var projected: Dictionary = helper.map_point(mark, flat)
            _check(absf(float(projected["x"])-float(note["x"])) < 0.00001,
                "Feedback notehead no longer aligns with displayed note")
        for tile in built["tiles"]:
            var texture: Texture2D = tile["texture"]
            _check(texture != null and texture.get_width() > 0 and texture.get_height() > 0,
                "Godot failed to upload a real raster score tile")
    if failures.is_empty():
        print("PHASE6_GODOT_PASS ", manifests.size(), " real engraved sample(s)")
    quit(0 if failures.is_empty() else 1)
