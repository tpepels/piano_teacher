extends SceneTree
## Application-level guard that a native layout and its semantic fragments
## describe the same revision. Score lifecycle ownership lives in
## ScoreAssetSession; its positive layout-then-model path is covered by
## tests/godot/score_asset_session.gd. No score command reaches an engine here.

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        set_process(false)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var app := FixtureApp.new()
    root.add_child(app)
    var session = app.score_session
    session.update_context({"loaded":true,"revision":2,"piece_fingerprint":"a"},1000)
    var layout_id: int = session.pending_id("layout")
    if layout_id < 0:
        push_error("A loaded revision must request its own native layout")
        quit(1)
        return
    session.complete_response("layout",layout_id,0,JSON.stringify({
        "revision":3,"anchors":[],"pages":0}).to_utf8_buffer(),1001)
    if app.layout_revision == 3 or not app.score_layout.is_empty():
        push_error("A layout from a newer server revision replaced this lesson's assets")
        quit(1)
        return
    var fixture = load("res://tests/native_glyph_fixture.gd")
    app.practice_view.stage.renderer.glyphs.load_font(fixture.catalogue())
    app._request_timeline_model()
    if app.timeline_model_pending:
        push_error("New score model was requested against the previous lesson's native assets")
        quit(1)
        return
    print("NATIVE_REVISION_READINESS_PASS")
    quit(0)
