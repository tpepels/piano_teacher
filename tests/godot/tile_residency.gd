extends SceneTree
# The native successor of tile residency: source events stay indexed once,
# the visible window bounds frame work, and seeks reuse authentic atlases.
class FixtureApp extends "native_production_fixture.gd":
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("NATIVE_RESIDENCY_FAIL:", message)

func atlas_ids(view: Control) -> Dictionary:
    var ids: Dictionary = {}
    for group in ["textures","note_textures","note_stem_textures","tie_textures",
            "chord_textures","chord_heads_textures","chord_stem_textures",
            "beam_textures","tuplet_textures","slur_textures"]:
        var textures: Dictionary = view.glyphs.get(group)
        for key in textures:
            ids[group+"/"+str(key)] = textures[key].get_instance_id()
    return ids

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1024,768)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var folder: String = OS.get_cmdline_user_args()[0]
    var error: String = app.load_native_fixture(folder)
    check(error.is_empty(),error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.timeline_preview
    var atlas: Dictionary = atlas_ids(view)
    var source: Dictionary = view.timeline.model.duplicate(true)
    var child_count: int = app.find_children("*","",true,false).size()
    check(view.layout.ordered_events.size() >= 300, "Stress fixture contains a long source score")
    check(not atlas.is_empty(), "Residency checks actual authentic texture resources")
    var duration: float = view.timeline.duration_beats
    for fraction in [0.0,.9,.1,.75,.4,.99,.2,.8,0.0,.99]:
        var beat: float = minf(duration-1.0,duration*float(fraction))
        app.last_state = {"loaded":true,"revision":app.revision,"running":true,
            "paused":true,"phase":"playing","clock_beat":beat,"bpm":80,
            "hand":"right","transport_id":33,"play_from_beat":0.0}
        app._process(0.0)
        view.queue_redraw()
        await process_frame
        await process_frame
        RenderingServer.force_draw()
        check(not view.drawn_noteheads.is_empty(), "Rapid seek paints source notes immediately")
        check(view.frame_scanned_events < view.layout.ordered_events.size()/4,
            "Each frame visits a bounded visible event window, even near the end")
        check(atlas_ids(view) == atlas, "Seeks reuse the same authentic atlas resources")
        check(app.find_children("*","",true,false).size() == child_count,
            "Rapid seeks do not accumulate scene nodes")
        check(view.timeline.model == source, "Seeking preserves all original source events")
        check(app._native_score_ready(), "Seek retains matching production readiness")
    # A rejected real model must invalidate readiness rather than exposing
    # stale notation. A fresh prepared payload must recover through handlers.
    var invalid: Dictionary = source.duplicate(true)
    invalid["schema"] = "invalid-test-schema"
    app._on_timeline_model(0,200,PackedStringArray(),JSON.stringify(invalid).to_utf8_buffer())
    check(not app._native_score_ready() and not view.native_ready,
        "Rejected source model clears actual renderer readiness")
    check(not app.score_error.is_empty(), "Rejected source has a persistent error")
    check(app.load_native_fixture(folder).is_empty(), "Fresh authentic preparation recovers rejected model")
    check(app._native_score_ready(), "Recovered production model is ready again")
    print("TILE_RESIDENCY_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
