extends SceneTree
# Exercise Phase 1 on real ImageTexture LA8 bytes, not invented SVG glyphs.

const Exact := preload("res://notation/legacy/exact_spacing.gd")
const BeatCamera := preload("res://notation/shared/beat_camera.gd")
var problems: Array[String] = []

func check(ok: bool, why: String) -> void:
    if not ok:
        problems.append(why)
        push_error(why)

func _initialize() -> void:
    call_deferred("_run")

func _fixture(beam: bool = false) -> Dictionary:
    var width := 300
    var height := 120
    var image := Image.create(width, height, false, Image.FORMAT_LA8)
    image.fill(Color.TRANSPARENT)
    var rails: Array = [.20, .25, .30, .35, .40, .55, .60, .65, .70, .75]
    for rail in rails:
        var row: int = roundi(rail * height)
        for x in range(width):
            image.set_pixel(x, row, Color(0, 0, 0, .75))
    var anchors: Array = []
    var notes: Array = []
    var event_x: Array[int] = [80, 125, 175, 220]
    for beat in range(event_x.size()):
        var px: int = event_x[beat]
        for y in range(42, 47):
            for x in range(px - 2, px + 3):
                image.set_pixel(x, y, Color(0, 0, 0, 1))
        var n := {"id": "note-%d" % beat, "beat": float(beat),
            "page": 0, "system": "only", "x": float(px) / width,
            "y": 44.0 / height}
        anchors.append(n.duplicate(true))
        notes.append(n.duplicate(true))
    if beam:
        # Every candidate cut intersects this genuine long beam, so the
        # entire single system must fall back without altering source pixels.
        for x in range(79, 222):
            image.set_pixel(x, 10, Color(0, 0, 0, 1))
    var texture := ImageTexture.create_from_image(image)
    return {
        "layout": {"continuous_score": true, "pages": 1,
            "widths": [float(width)], "heights": [float(height)],
            "beats": 4.0, "anchors": anchors, "notes": notes,
            "systems": [{"page": 0, "system": "only", "left": 0.0,
                "right": 1.0, "staff_lines": rails}],
            "strip_time_proportional": false,
            "strip_timing_fallback": ""},
        "tiles": [{"texture": texture,
            "rect": Rect2(0.0, 0.0, width, height),
            "upload_bytes": width * height * 2}],
        "size": Vector2(width, height),
    }

func _run() -> void:
    var source: Dictionary = _fixture()
    var result: Dictionary = Exact.reflow(source)
    check(bool(result.layout.get("exact_ink_grid", false)),
        "Simple real Verovio image can acquire one constant beat grid")
    if bool(result.layout.get("exact_ink_grid", false)):
        var grid: Dictionary = BeatCamera.prepare(result.layout)
        check(bool(grid.get("enabled", false)),
            "The exact rearrangement validates in the actual camera")
        var original_image: Image = source.tiles[0].texture.get_image()
        var shifted_image: Image = result.tiles[0].texture.get_image()
        check(shifted_image.get_width() > original_image.get_width(),
            "The grid inserts blank columns; it must never shrink symbols")
        for i in range(4):
            var orig_x: int = roundi(float(source.layout.notes[i].x) * source.size.x)
            var next_x: int = roundi(float(result.layout.notes[i].x) * result.size.x)
            for y in range(42, 47):
                for offset in range(-2, 3):
                    var lhs: Color = original_image.get_pixel(orig_x + offset, y)
                    var rhs: Color = shifted_image.get_pixel(next_x + offset, y)
                    check(absf(lhs.a - rhs.a) < .02 and absf(lhs.r - rhs.r) < .02,
                        "Moved Verovio glyph preserves its exact native pixels")
        check(source.size.x == 300 and source.layout.notes[1].x == 125.0 / 300.0,
            "Source Verovio input is immutable across the renderer")
    var connected: Dictionary = _fixture(true)
    var declined: Dictionary = Exact.reflow(connected)
    check(not bool(declined.layout.get("exact_ink_grid", false)),
        "Connected beam must prohibit unsafe splitting of musical ink")
    check(declined.size == connected.size,
        "Unsafe beam fallback retains the full original source width")
    check(declined.tiles[0].texture.get_image().get_data() == \
        connected.tiles[0].texture.get_image().get_data(),
        "An unsafe fallback must not mutate one source Verovio pixel")
    print("SCORE_EXACT_SPACING_FAILURES:", problems.size())
    quit(0 if problems.is_empty() else 1)
