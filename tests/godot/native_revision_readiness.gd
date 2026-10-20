extends SceneTree

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        set_process(false)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var app := FixtureApp.new()
    root.add_child(app)
    app.revision = 2
    app.requested_layout_revision = 2
    app.score_frame = Control.new()
    app.add_child(app.score_frame)
    app.score_layout = {"original":true}
    app._on_layout(0,200,PackedStringArray(),JSON.stringify({
        "revision":3,"anchors":[],"pages":0}).to_utf8_buffer())
    if not app.score_layout.has("original"):
        push_error("A layout from a newer server revision replaced this lesson's assets")
        quit(1)
        return
    app.native_notation_enabled = true
    app.timeline_preview = load("res://notation/native/view.gd").new()
    app.add_child(app.timeline_preview)
    var fixture = load("res://tests/native_glyph_fixture.gd")
    app.timeline_preview.glyphs.load_font(fixture.catalogue())
    app.timeline_model_request = HTTPRequest.new()
    app.add_child(app.timeline_model_request)
    app.last_state = {"loaded":true}
    app.revision = 2
    app.layout_revision = 1
    app._request_timeline_model()
    if app.timeline_model_pending:
        push_error("New score model was requested against the previous lesson's native assets")
        app.timeline_model_request.cancel_request()
        quit(1)
        return
    app.layout_revision = 2
    app._request_timeline_model()
    if not app.timeline_model_pending:
        push_error("Current revision assets must allow the semantic model request")
        quit(1)
        return
    app.timeline_model_request.cancel_request()
    print("NATIVE_REVISION_READINESS_PASS")
    quit(0)
