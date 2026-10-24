extends SceneTree
# Offline library samples enter the same asset/model handlers as Practice.
const FixtureApp := preload("native_production_fixture.gd")
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        push_error("NATIVE_LIBRARY_FAIL: " + message)

func run() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 1:
        push_error("Usage: -- EVIDENCE_DIR")
        quit(2)
        return
    var folder: String = args[0]
    var manifests: Array[String] = []
    for filename in DirAccess.get_files_at(folder):
        if filename.begins_with("sample-") and filename.ends_with(".json"):
            manifests.append(filename)
    manifests.sort()
    check(not manifests.is_empty(), "No library samples supplied")
    root.size = Vector2i(1220, 780)
    var samples: Array = []
    for filename in manifests:
        var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
            folder.path_join(filename)))
        var app := FixtureApp.new()
        app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(app)
        await process_frame
        await process_frame
        var error: String = app.load_native_fixture(folder.path_join(
            str(manifest.get("native_fixture", "missing"))))
        check(error.is_empty(), filename + ": " + error)
        if not error.is_empty():
            app.queue_free()
            await process_frame
            continue
        var view = app.timeline_preview
        var feedback = app.native_score_feedback
        check(app._native_score_ready() and app.rendered_revision == app.revision
            and not app.start_button.disabled and not app.score_status_panel.visible,
            filename + ": native readiness must enable production display and Play")
        var source_ids: Array[String] = []
        for note in view.timeline.notes:
            source_ids.append(str(note.id))
        var attack_sources: Dictionary = {}
        for event in view.ordered_events:
            if str(event.get("kind", "")) == "note" and bool(event.get("is_attack", false)):
                attack_sources[str(event.source_id)] = str(event.id)
        check(attack_sources.size() == source_ids.size(),
            filename + ": each source attack must have native notation")
        var feedback_sources: Array[String] = []
        for source in source_ids:
            check(attack_sources.has(source), filename + ": lost source ID " + source)
            if feedback != null and str(feedback.source_to_id.get(source, "")) == \
                    str(attack_sources.get(source, "missing")):
                feedback_sources.append(source)
        check(feedback_sources.size() == source_ids.size(),
            filename + ": feedback must bind every source attack to native notation")
        # Seek to a genuine source attack. Source rests before it must not
        # let an empty native viewport pass as a displayed score.
        var first_beat: float = float(view.timeline.notes[0].onset_beats)
        var state: Dictionary = app.last_state.duplicate(true)
        state["running"] = false
        state["paused"] = true
        state["play_from_beat"] = first_beat
        view.present(state, 0.0)
        view.queue_redraw()
        await process_frame
        await process_frame
        RenderingServer.force_draw()
        check(view.is_visible_in_tree() and not view.drawn_noteheads.is_empty(),
            filename + ": production must actually paint native heads")
        var displayed: Array[String] = []
        for source in source_ids:
            var id: String = str(attack_sources.get(source, ""))
            if not view.drawn_noteheads.has(id):
                continue
            var point: Vector2 = view.drawn_noteheads[id]
            if Rect2(Vector2.ZERO, view.size).has_point(point):
                displayed.append(source)
                check(feedback != null and feedback.note_position(id).is_equal_approx(point),
                    filename + ": feedback must follow the displayed native head")
        check(not displayed.is_empty(), filename + ": no source attack is visible in the native stage")
        samples.append({"measure": manifest.measure, "ready": app._native_score_ready(),
            "source_ids": source_ids, "displayed_source_ids": displayed,
            "feedback_source_ids": feedback_sources})
        app.queue_free()
        await process_frame
    var output := FileAccess.open(folder.path_join("native-library-report.json"), FileAccess.WRITE)
    check(output != null, "Cannot write native library evidence")
    if output != null:
        output.store_string(JSON.stringify({"samples": samples, "failures": failures}, "  ") + "\n")
        output.close()
    if failures.is_empty():
        print("PHASE6_GODOT_PASS")
    quit(0 if failures.is_empty() else 1)
