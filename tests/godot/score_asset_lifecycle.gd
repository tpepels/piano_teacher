extends SceneTree
## Phase 6 score lifecycle integration. Uses the actual Godot session state
## machine without requiring the compiled bridge or an attached MIDI keyboard.
const Session := preload("res://score_asset_session.gd")

class FakeGlyphs:
    extends RefCounted
    func ready() -> bool:
        return true

class FakeRenderer:
    extends RefCounted
    signal retained_ink_compiled
    var native_ready := true
    var failure_reason := ""
    var glyphs := FakeGlyphs.new()
    var visible := false
    var notice := ""
    var cleared := 0
    var ink_ready := true
    var redraws := 0
    func clear_score() -> void:
        cleared += 1
    func queue_redraw() -> void:
        redraws += 1
    func retained_ready() -> bool:
        return ink_ready
    func load_score(_model: Dictionary) -> bool:
        return true
    func set_verovio_glyphs(_glyphs, _notes, _ties, _chords, _beams,
            _tuplets, _slurs, _pairs, _slurs_complete, _required_beams,
            _beams_complete) -> bool:
        return true

var failures: Array[String] = []

func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        print("SCORE_ASSET_LIFECYCLE_FAIL:",message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var renderer := FakeRenderer.new()
    var session := Session.new(renderer)
    var sent: Array = []
    session.request_requested.connect(func(kind: String, id: int,
            operation: String, timeout_seconds: float):
        sent.append({"kind":kind,"id":id,"operation":operation,
            "timeout":timeout_seconds}))
    session.update_context({"loaded":true,"revision":1,
        "piece_fingerprint":"piece-a","phase":"loading"},1000)
    var stale_layout: int = session.pending_id("layout")
    check(stale_layout >= 0 and sent.size() == 1,
        "opening piece A must dispatch native layout")
    session.update_context({"loaded":true,"revision":2,
        "piece_fingerprint":"piece-b","phase":"loading"},1010)
    var layout_b: int = session.pending_id("layout")
    check(layout_b > stale_layout and sent.size() == 2,
        "new piece starts layout without waiting for previous deadline")
    session.complete_response("layout",stale_layout,3,
        "{\"error\":\"obsolete request\"}".to_utf8_buffer(),1020)
    check(session.pending_id("layout") == layout_b and session.score_error.is_empty(),
        "obsolete layout must not fail or replace current piece")
    session.complete_response("layout",layout_b,0,
        JSON.stringify({"revision":2,"anchors":{}}).to_utf8_buffer(),1030)
    var model_b: int = session.pending_id("model")
    check(model_b > layout_b and sent.size() == 3 and
        float(sent[2]["timeout"]) >= 30.0,
        "semantic model starts after layout with heavy-score deadline")
    session.update_context({"loaded":true,"revision":3,
        "piece_fingerprint":"piece-c","phase":"loading"},1040)
    var layout_c: int = session.pending_id("layout")
    check(layout_c > model_b and not session.timeline_model_pending,
        "new piece invalidates outstanding semantic model")
    session.complete_response("model",model_b,0,
        JSON.stringify({"revision":2}).to_utf8_buffer(),1050)
    check(session.pending_id("layout") == layout_c and
        session.native_score_piece_fingerprint.is_empty(),
        "stale model must never publish prior piece")
    session.complete_response("layout",layout_c,0,
        JSON.stringify({"revision":3,"anchors":{}}).to_utf8_buffer(),1060)
    var model_c: int = session.pending_id("model")
    var timed_out := "{\"error\":\"Embedded operation exceeded its deadline\"}".to_utf8_buffer()
    session.complete_response("model",model_c,3,timed_out,2000)
    check(not session.timeline_model_pending and session.score_error.is_empty(),
        "first timeout schedules bounded retry")
    session.poll(3900)
    check(not session.timeline_model_pending, "retry honors initial backoff")
    session.poll(4000)
    var model_retry: int = session.pending_id("model")
    check(model_retry > model_c, "retry dispatches after backoff")
    session.complete_response("model",model_retry,3,timed_out,5000)
    session.poll(8999)
    check(not session.timeline_model_pending, "second timeout lengthens backoff")
    session.poll(9000)
    var final_model: int = session.pending_id("model")
    session.complete_response("model",final_model,3,timed_out,10000)
    check(not session.score_error.is_empty() and
        bool(session.status()["retry_visible"]),
        "three timeouts surface actionable Retry instead of infinite spinner")
    check(session.retry(10010) and session.score_error.is_empty() and
        session.pending_id("layout") > layout_c,
        "manual Retry resets complete failure chain")
    session.complete_response("layout",session.pending_id("layout"),0,
        JSON.stringify({"revision":3,"anchors":{}}).to_utf8_buffer(),10100)
    var successful_model: int = session.pending_id("model")
    renderer.ink_ready = false
    session.complete_response("model",successful_model,0,
        JSON.stringify({"revision":3,"notes":[]}).to_utf8_buffer(),10200)
    check(not session.is_ready() and session.timeline_model_revision == 3,
        "model completion must not acknowledge uncompiled retained ink")
    session.poll(55200)
    check(not session.score_error.is_empty() and bool(session.status()["retry_visible"]),
        "stuck retained ink must terminate with Retry")
    # Once preparation is visibly slow, Retry works even with layout pending.
    var hanging := Session.new(FakeRenderer.new())
    hanging.update_context({"loaded":true,"revision":20,
        "piece_fingerprint":"slow","phase":"loading"},Time.get_ticks_msec())
    hanging._preparing_since_ms = Time.get_ticks_msec() - 12000
    check(bool(hanging.status()["retry_visible"]) and
        bool(hanging.status()["browse_visible"]),
        "a stalled in-flight layout must expose Retry and Browse")
    var old_request: int = hanging.pending_id("layout")
    check(hanging.retry(Time.get_ticks_msec()) and
        hanging.pending_id("layout") > old_request,
        "Retry must supersede an outstanding 90-second layout")
    hanging.complete_response("layout",old_request,3,
        "{\"error\":\"stale\"}".to_utf8_buffer(),Time.get_ticks_msec())
    check(hanging.score_error.is_empty() and hanging.layout_pending,
        "old layout completion must not override a manual Retry")
    # A worker that has advanced to another score revision must never
    # silently leave the selected piece loading without a retry control.
    var mismatched := Session.new(FakeRenderer.new())
    mismatched.update_context({"loaded":true,"revision":30,
        "piece_fingerprint":"old","phase":"loading"},Time.get_ticks_msec())
    mismatched.complete_response("layout",mismatched.pending_id("layout"),0,
        JSON.stringify({"revision":31,"anchors":[{"id":"new"}]}).to_utf8_buffer(),
        Time.get_ticks_msec())
    check(not mismatched.score_error.is_empty() and
        bool(mismatched.status()["retry_visible"]),
        "revision-mismatched Verovio layout must fail visibly, not spin forever")
    mismatched.update_context({"loaded":true,"revision":31,
        "piece_fingerprint":"new","phase":"loading"},Time.get_ticks_msec())
    check(mismatched.layout_pending and mismatched.score_error.is_empty(),
        "fresh authoritative score revision must automatically retry layout")
    var second_renderer := FakeRenderer.new()
    var second := Session.new(second_renderer)
    second.update_context({"loaded":true,"revision":9,
        "piece_fingerprint":"healthy","phase":"loading",
        "awaiting_score_revision":9},0)
    second.complete_response("layout",second.pending_id("layout"),0,
        JSON.stringify({"revision":9,"anchors":{}}).to_utf8_buffer(),100)
    second.complete_response("model",second.pending_id("model"),0,
        JSON.stringify({"revision":9,"notes":[]}).to_utf8_buffer(),200)
    check(second.is_ready() and second.rendered_revision == 9,
        "healthy retained score still publishes immediately")
    print("SCORE_ASSET_LIFECYCLE_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
