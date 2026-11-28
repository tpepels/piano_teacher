extends SceneTree
## Exercise real detached CPU preparation, texture upload and retained drawing.
## The bundle is produced by the production Python/Verovio engine.
const Session := preload("res://score_asset_session.gd")
const Native := preload("res://notation/native/view.gd")
const Meter := preload("res://moving_meter_grid.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
var failures := 0
var fixture: Dictionary
var view
var session
var actions: Array = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("SCORE_READINESS_FAIL: ",message)

func state(revision: int) -> Dictionary:
    return {"loaded":true,"revision":revision,"piece_fingerprint":fixture["fingerprint"],
        "stage_key":fixture["stage_key"],"hand":fixture["hand"],
        "phase":"loading","awaiting_score_revision":revision}

func bundle(revision: int) -> PackedByteArray:
    var data: Dictionary = fixture.duplicate(true)
    data["revision"] = revision
    data["model"]["revision"] = revision
    data["layout"]["revision"] = revision
    return JSON.stringify(data).to_utf8_buffer()

func reply(revision: int) -> void:
    session.complete_response("bundle",session.pending_id("bundle"),0,bundle(revision),Time.get_ticks_msec())

func wait_until_finished(revision: int) -> void:
    var deadline: int = Time.get_ticks_msec()+15000
    while Time.get_ticks_msec() < deadline and not session.is_ready() and session.score_error.is_empty():
        session.advance_preparation()
        view.present_flow(0.0,{},0.0,false)
        session.poll(Time.get_ticks_msec())
        if session.layout_revision == revision and not view.retained_ready():
            check(actions.is_empty(),"Incomplete retained notation cannot authorize a take")
        await process_frame

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("PIANO_TEST_SCORE_BUNDLE")))
    if not data is Dictionary or data.get("status") != "ready":
        printerr("SCORE_READINESS_FAIL: missing authentic score fixture")
        quit(1)
        return
    fixture = data
    root.size = Vector2i(1280,800)
    view = Native.new()
    root.add_child(view)
    view.size = Vector2(1200,650)
    session = Session.new(view)
    session.action_requested.connect(func(value: Dictionary): actions.append(value))
    view.active_hand = str(fixture["hand"])
    session.update_context(state(1),Time.get_ticks_msec())
    reply(1)
    check(session.layout_pending and not session.is_ready() and actions.is_empty(),
        "Received data does not authorize playback before background preparation")
    # Supersede a real in-flight job before the session joins it.
    session.update_context(state(2),Time.get_ticks_msec())
    reply(2)
    # Use the same real retained score after a viewport change during upload.
    # A fresh atlas would repeat all PNG/SVG rasterization for this resize.
    var upload_deadline: int = Time.get_ticks_msec()+5000
    while session._uploading == null and not session.is_ready() and \
            session.score_error.is_empty() and Time.get_ticks_msec() < upload_deadline:
        session.advance_preparation()
        await process_frame
    var atlas = null
    if session._uploading != null:
        atlas = session._uploading.result["engraving"]
    view.size = Vector2(1150,650)
    await wait_until_finished(2)
    check(session.is_ready() and session.rendered_revision == 2 and
        actions == [{"action":"score_ready","revision":2}],
        "Only the selected revision becomes ready after authentic retained drawing: "+session.score_error)
    if atlas != null:
        check(view.engraving == atlas,"Resizing during upload repeated rasterization")
    if session.is_ready():
        check(view.glyphs.textures.values()[0] is Texture2D,
            "Published glyphs have completed their texture upload")
        check(view.engraving.stream_source_key == StreamQueue.source_identity(view.timeline.model),
            "Worker source identity must match the installed model after refit")
        check(view.glyphs._prepared_head_sizes.is_empty() and view.glyphs._assets._prepared_cutouts.is_empty(),
            "Prepared status upload work must be finished before publication")
        check(not view.glyphs._assets._head_masks._head_cutouts.is_empty(),
            "Authentic source masks must be prepared before the first graded draw")
        var original = view.engraving
        var selected: Dictionary = state(2)
        var target: Dictionary = {}
        for event in view.layout.ordered_events:
            if event.get("kind") == "note" and event.get("is_attack",false):
                target = event
                break
        check(not target.is_empty(),"Authentic fixture contains an editable attack")
        if not target.is_empty():
            var source: String = str(target["source_id"])
            var hand: String = view.layout.performing_hand(target)
            for finger in [1,3]:
                selected["fingering"] = {"annotation_version":finger,"annotations":{
                    source:{"source_id":source,"finger":finger,"hand":hand,"origin":"manual"}}}
                session.update_context(selected,Time.get_ticks_msec())
                check(int(target.get("fingering",{}).get("finger",-1)) == finger and
                    session.is_ready() and view.engraving == original,
                    "Repeated correction changes the actual attack annotation without reloading notation")
            selected["fingering"] = {"annotation_version":4,"annotations":{}}
            session.update_context(selected,Time.get_ticks_msec())
            check(not target.has("fingering") and session.is_ready(),
                "Removing a correction clears the existing annotation without reloading")
    actions.clear()
    session.update_context(state(3),Time.get_ticks_msec())
    var old: int = session.pending_id("bundle")
    reply(3)
    check(session.retry(Time.get_ticks_msec()),"Retry supersedes the in-flight worker")
    session.complete_response("bundle",old,1,JSON.stringify({"error":"obsolete"}).to_utf8_buffer(),Time.get_ticks_msec())
    check(session.score_error.is_empty(),"An obsolete error cannot poison Retry")
    reply(3)
    await wait_until_finished(3)
    check(session.is_ready() and session.rendered_revision == 3 and
        actions == [{"action":"score_ready","revision":3}],"Retry installs the selected score: "+session.score_error)
    actions.clear()
    session.update_context(state(4),Time.get_ticks_msec())
    var malformed_id: int = session.pending_id("bundle")
    var replayed: Array = []
    session.request_requested.connect(func(_kind, _id, _path, _timeout, identity):
        replayed.append(identity))
    var incomplete: Dictionary = JSON.parse_string(bundle(4).get_string_from_utf8())
    incomplete["layout"]["native_beams_complete"] = false
    session.complete_response("bundle",malformed_id,0,JSON.stringify(incomplete).to_utf8_buffer(),
        Time.get_ticks_msec())
    var deadline: int = Time.get_ticks_msec()+5000
    while replayed.is_empty() and Time.get_ticks_msec() < deadline:
        session.advance_preparation()
        await process_frame
    check(replayed.size() == 1 and replayed[0].get("rejected_generation",-1) >= 0 and
        actions.is_empty(),"An invalid payload retries once and identifies the child reply to retire")
    session.complete_response("bundle",session.pending_id("bundle"),0,
        "{}".to_utf8_buffer(),Time.get_ticks_msec())
    await wait_until_finished(4)
    check(not session.is_ready() and not session.score_error.is_empty() and
        session.status().retry_visible and actions.is_empty(),"Malformed score fails visibly without authorizing playback")
    view.size = Vector2(10,10)
    session.update_context(state(7),Time.get_ticks_msec())
    var received: int = Time.get_ticks_msec()
    session.complete_response("bundle",session.pending_id("bundle"),0,bundle(7),received)
    session.poll(received+45000)
    check(not session.layout_pending and not session.is_ready() and
        session.status().retry_visible and actions.is_empty(),
        "A viewport that never becomes usable expires with Retry available")
    view.size = Vector2(1200,650)
    session.update_context({"loaded":false,"revision":4},Time.get_ticks_msec())
    check(not session.is_ready() and session.status().browse_visible,"Closing music revokes readiness")
    var grid: Array = [{"start_beat":0.0,"end_beat":4.0}]
    check(Meter.visible_lines(4000.0,1000.0,330.0,100.0,0.0,grid).has(4000.0),
        "Barlines persist far beyond the written score")
    check(Meter.visible_lines(-4000.0,1000.0,330.0,100.0,0.0,grid).has(-4000.0),
        "Barlines persist far before the written score")
    # Shutdown is terminal even if a reply or a new snapshot arrives later.
    session.update_context(state(5),Time.get_ticks_msec())
    var closing_id: int = session.pending_id("bundle")
    reply(5)
    session.shutdown_preparation()
    session.complete_response("bundle",closing_id,0,bundle(5),Time.get_ticks_msec())
    session.update_context(state(6),Time.get_ticks_msec())
    session.advance_preparation()
    check(not session.layout_pending and not session.is_ready() and
        actions.is_empty(),"Shutdown cannot resurrect a cancelled score")
    session.shutdown_preparation()
    session.replace_renderer(null)
    view.queue_free()
    print("SCORE_READINESS_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
