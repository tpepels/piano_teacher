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
    var no_pages: Array[Image] = []
    check(not str(helper.build({}, no_pages).get("error", "")).is_empty(),
          "missing measured systems must return an explicit error")
    check(not str(helper.build(original, no_pages).get("error", "")).is_empty(),
          "missing score pages must return an explicit error")
    var strip: Dictionary = helper.build(original, pages)
    var flat: Dictionary = strip.layout
    check(strip.tiles.size() == original.systems.size(), "every system becomes a tile")
    check(flat.notes.size() == original.notes.size(), "all original noteheads survive")
    check(flat.pages == 1, "flattened score has one virtual page")
    var previous_right := 0.0
    var first_line := -1.0
    var rail_positions: Array = []
    for index in range(strip.tiles.size()):
        var tile: Dictionary = strip.tiles[index]
        var rect: Rect2 = tile.rect
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
    var previous_beat := -INF
    var previous_x := -INF
    for anchor in flat.anchors:
        check(anchor.page == 0 and anchor.system == "strip", "anchors share the virtual staff")
        check(float(anchor.beat) >= previous_beat, "anchors remain in musical order")
        check(float(anchor.x) >= previous_x - .00001, "no backwards sweep at a system wrap")
        previous_beat = float(anchor.beat)
        previous_x = float(anchor.x)
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
