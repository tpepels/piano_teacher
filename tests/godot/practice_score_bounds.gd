extends SceneTree

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("SCORE_BOUNDS_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    app.revision = 0
    app.layout_revision = 0
    app.requested_revision = 0
    app.requested_page = 0
    app.score_layout = JSON.parse_string(FileAccess.get_file_as_string(folder + "/layout.json"))
    var pages: Array[Image] = []
    for page in range(int(app.score_layout.pages)):
        pages.append(Image.load_from_file(folder + "/page-%d.png" % page))
    app.page_images = pages.duplicate()
    app.source_layout = app.score_layout
    app.last_state = {"phase":"ready"}
    app._on_score(0, 200, PackedStringArray(), FileAccess.get_file_as_bytes(folder + "/score.png"))
    # Measure actual source ink independently of the production fitting code.
    var ink_top := INF
    var ink_bottom := -INF
    for mapping in app.score_layout.strip_mappings:
        var source: Image = pages[int(mapping.source_page)]
        var ink: Rect2i = source.get_region(Rect2i(mapping.crop)).get_used_rect()
        ink_top = minf(ink_top, float(mapping.position.y) + ink.position.y)
        ink_bottom = maxf(ink_bottom, float(mapping.position.y) + ink.end.y)
    var native_height: float = app.score_overlay.image_size.y
    for dimensions in [Vector2i(1536,960), Vector2i(1024,768), Vector2i(800,600)]:
        root.size = dimensions
        var baseline := Vector2.ZERO
        for phase in ["ready", "count_in", "playing", "paused", "playing"]:
            app.last_state = {"phase":phase, "hand_stages":[
                {"hand":"left", "active":true}, {"hand":"right"}, {"hand":"both"}]}
            app._update_hand_stages(app.last_state)
            await process_frame
            await process_frame
            app._layout_moving_score()
            if baseline == Vector2.ZERO:
                baseline = app.score_content.size
            check(app.score_content.size.distance_to(baseline) < .1,
                "%s %s: transport does not resize notation" % [dimensions,phase])
            var scale: float = app.score_content.size.y / native_height
            var top: float = app.score_content.position.y + ink_top * scale
            var bottom: float = app.score_content.position.y + ink_bottom * scale
            check(top >= 4.0, "%s %s: opening clefs fit above the staff (%s)" % [dimensions,phase,top])
            check(bottom <= app.score_frame.size.y - 28.0,
                "%s %s: bass clef/meter fit above progress rail (%s > %s)" % [dimensions,phase,bottom,app.score_frame.size.y-28])
    print("SCORE_BOUNDS_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
