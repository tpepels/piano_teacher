extends SceneTree
## Phase 6 contract suite for the one score-session owner. Covers the
## production layout/model lifecycle, stale generations, bounded retries,
## real renderer rejection, and recovery. There is no HTTP adapter.
const Session := preload("res://score_asset_session.gd")

class Atlas:
    extends RefCounted
    var loaded := false
    func ready() -> bool:
        return loaded

class Renderer:
    extends RefCounted
    signal retained_ink_compiled
    var glyphs := Atlas.new()
    var native_ready := false
    var visible := false
    var atlas_ok := true
    var model_ok := true
    var retained_ok := true
    var failure_reason := "authentic asset failure"
    var notice := ""
    var atlas_calls: Array = []
    var model_calls: Array = []
    var clears := 0
    var redraws := 0
    func set_verovio_glyphs(font, notes, ties, chords, beams, tuplets, slurs,
            required_slurs, slurs_complete, required_beams, beams_complete) -> bool:
        atlas_calls.append([font,notes,ties,chords,beams,tuplets,slurs,
            required_slurs,slurs_complete,required_beams,beams_complete])
        glyphs.loaded = atlas_ok
        return atlas_ok
    func load_score(candidate: Dictionary) -> bool:
        model_calls.append(candidate.duplicate(true))
        native_ready = model_ok
        return model_ok
    func retained_ready() -> bool:
        return retained_ok
    func clear_score() -> void:
        clears += 1
        native_ready = false
        glyphs.loaded = false
    func queue_redraw() -> void:
        redraws += 1

class Feedback:
    extends RefCounted
    var bindings: Array = []
    var states: Array = []
    func bind_score(renderer, revision: int) -> void:
        bindings.append([renderer, revision])
    func present(state: Dictionary) -> void:
        states.append(state.duplicate(true))

var failures := 0

func check(condition: bool, label: String) -> void:
    if not condition:
        failures += 1
        print("SCORE_ASSET_CONTRACT_FAIL:",label)

func _initialize() -> void:
    call_deferred("run_contract")

func done() -> void:
    print("SCORE_ASSET_SESSION_FAILURES:",failures)
    quit(0 if failures == 0 else 1)

func context(rev: int, phase: String = "loading") -> Dictionary:
    return {"loaded":true,"revision":rev,"phase":phase,
        "awaiting_score_revision":rev,"piece_fingerprint":"piece-%d" % rev}

func layout(rev: int) -> Dictionary:
    return {"revision":rev,"anchors":[{"id":"note"}],
        "attack_map":{"source-note":"note"},
        "native_glyphs":{"font":"authentic"},
        "native_note_templates":{"note":1},
        "native_tie_templates":{"tie":2},
        "native_chord_templates":{"chord":3},
        "native_beam_fragments":{"beam":4},
        "native_tuplet_fragments":{"tuplet":5},
        "native_slur_fragments":{"slur":6},
        "native_required_slur_pairs":[["a","b"]],
        "native_slurs_complete":true,
        "native_required_beam_groups":["a|b"],
        "native_beams_complete":true}

func body(value: Variant) -> PackedByteArray:
    return JSON.stringify(value).to_utf8_buffer()

func track(session, requests: Array, actions: Array, published: Array) -> void:
    session.request_requested.connect(func(kind: String, id: int,
            operation: String, timeout_seconds: float):
        requests.append({"kind":kind,"id":id,"operation":operation,
            "timeout":timeout_seconds}))
    session.action_requested.connect(func(value: Dictionary): actions.append(value))
    session.score_published.connect(func(rev: int): published.append(rev))

func finish_layout(session, rev: int, at_ms: int) -> void:
    session.complete_response("layout",session.pending_id("layout"),0,body(layout(rev)),at_ms)

func finish_model(session, rev: int, at_ms: int) -> void:
    session.complete_response("model",session.pending_id("model"),0,
        body({"revision":rev,"notes":[{"id":"note"}]}),at_ms)

func run_contract() -> void:
    var args := OS.get_cmdline_user_args()
    var which: String = args[0] if not args.is_empty() else ""
    match which:
        "publication": test_publication()
        "stale": test_stale()
        "retry": test_retry()
        "failure": test_failure()
        "native": test_native()
        _: check(false,"Unknown score-session contract: "+which)
    done()

func test_publication() -> void:
    var renderer := Renderer.new()
    var feedback := Feedback.new()
    var session := Session.new(renderer,feedback)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    track(session,requests,actions,publications)
    check(session.status()["browse_visible"] and not session.is_ready(),
        "unloaded score should offer library navigation")
    session.update_context(context(7),100)
    check(requests.size() == 1 and requests[0]["operation"] == "score.native_layout"
        and float(requests[0]["timeout"]) == 90.0,
        "layout is one native operation with its own deadline")
    session.poll(150)
    check(requests.size() == 1 and actions.is_empty(),
        "semantic/model and score ack must wait for the engraved atlas")
    finish_layout(session,7,200)
    check(renderer.atlas_calls.size() == 1 and
        renderer.atlas_calls[0][0] == {"font":"authentic"} and
        renderer.atlas_calls[0][7] == [["a","b"]] and
        renderer.atlas_calls[0][9] == ["a|b"],
        "native glyph, slur and beam data pass through without replacement")
    check(requests.size() == 2 and requests[1]["operation"] == "score.semantic"
        and float(requests[1]["timeout"]) == 30.0,
        "model starts only after glyphs with realistic score deadline")
    check(not session.is_ready() and publications.is_empty() and actions.is_empty(),
        "layout alone cannot start the practice transport")
    var released := session.layout_snapshot()
    released["anchors"].clear()
    check(session.layout_snapshot()["anchors"].size() == 1,
        "external layout snapshot cannot mutate session data")
    finish_model(session,7,250)
    check(session.is_ready() and session.rendered_revision == 7 and renderer.visible,
        "matching semantic model and retained ink publish the score")
    check(publications == [7] and actions == [
        {"action":"score_ready","revision":7}],
        "only the exact current revision acknowledges ready score")
    check(feedback.bindings[-1] == [renderer,7] and
        feedback.states[-1] == context(7),
        "feedback receives the actual installed renderer and source context")
    check(not session.status()["visible"],"ready score hides blocking status")
    session.update_context(context(7,"ready"),300)
    check(requests.size() == 2 and actions.size() == 1,
        "identical revision must not be reloaded or re-acknowledged")
    renderer.native_ready = false
    check(not session.is_ready(),"loss of native readiness invalidates publication")

func test_stale() -> void:
    var renderer := Renderer.new()
    var session := Session.new(renderer)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    track(session,requests,actions,publications)
    session.update_context(context(1),0)
    var old_layout: int = session.pending_id("layout")
    session.update_context(context(2),1)
    var layout2: int = session.pending_id("layout")
    check(requests.size() == 2 and layout2 > old_layout,
        "switch to piece two supersedes an outstanding layout immediately")
    session.complete_response("layout",old_layout,3,body({"error":"obsolete"}),2)
    check(session.pending_id("layout") == layout2 and session.score_error.is_empty(),
        "obsolete geometry failure must not poison new piece")
    finish_layout(session,2,3)
    var old_model: int = session.pending_id("model")
    session.update_context(context(3),4)
    var layout3: int = session.pending_id("layout")
    check(layout3 > old_model and not session.timeline_model_pending,
        "switch to piece three supersedes an outstanding semantic model")
    session.complete_response("model",old_model,0,body({"revision":2}),5)
    check(renderer.model_calls.is_empty() and session.pending_id("layout") == layout3,
        "stale response must not install previous semantic score")
    finish_layout(session,3,6)
    var bad_model: int = session.pending_id("model")
    session.complete_response("model",bad_model,0,body({"revision":2}),7)
    check(not session.timeline_model_pending and
        session.timeline_model_retry_after_ms == 2007,
        "wrong semantic revision schedules bounded retry")
    session.poll(2006)
    check(not session.timeline_model_pending,"retry deadline is enforced")
    session.poll(2007)
    finish_model(session,3,2008)
    check(session.is_ready() and actions == [
        {"action":"score_ready","revision":3}] and publications == [3],
        "only actual final current source may acknowledge practice")
    var other := context(3)
    other["piece_fingerprint"] = "different-fingerprint"
    session.update_context(other,2009)
    check(not session.is_ready() and session.layout_pending,
        "fingerprint changes invalidate score even with same revision")
    session.update_context({"loaded":false,"revision":3},2010)
    check(not session.is_ready() and session.status()["browse_visible"],
        "closing a score invalidates all pending requests")

func test_retry() -> void:
    var renderer := Renderer.new()
    var session := Session.new(renderer)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    track(session,requests,actions,publications)
    check(not session.retry(0),"Retry without a loaded piece is a no-op")
    session.update_context(context(5),100)
    var old_layout: int = session.pending_id("layout")
    check(session.retry(110) and session.pending_id("layout") > old_layout,
        "Retry replaces in-flight native layout")
    session.complete_response("layout",old_layout,0,body(layout(5)),111)
    check(session.layout_pending and renderer.atlas_calls.is_empty(),
        "stale response after manual Retry cannot install ink")
    finish_layout(session,5,112)
    var model: int = session.pending_id("model")
    session.request_start_result("model",model,ERR_CANT_CONNECT,120)
    check(session.timeline_model_retry_after_ms == 2120 and
        not session.timeline_model_pending,
        "model start failure schedules first bounded backoff")
    session.poll(2120)
    model = session.pending_id("model")
    var timeout := body({"error":"Embedded operation exceeded its deadline"})
    session.complete_response("model",model,3,timeout,2200)
    check(session.timeline_model_retry_after_ms == 6200,
        "second transient failure increases recovery delay")
    session.poll(6199)
    check(not session.timeline_model_pending,"second retry cannot start early")
    session.poll(6200)
    session.complete_response("model",session.pending_id("model"),3,timeout,6300)
    check(not session.score_error.is_empty() and session.status()["retry_visible"],
        "third failure is terminal and offers explicit Retry")
    check(session.retry(6310) and session.score_error.is_empty(),
        "manual Retry resets retry budget and score assets")
    finish_layout(session,5,6320)
    finish_model(session,5,6330)
    check(session.is_ready() and publications == [5],
        "a healthy retry publishes the complete native score")
    session.update_context(context(5),6340)
    check(actions.size() == 2,
        "loading poll may repeat acknowledgement when command port was busy")

func test_failure() -> void:
    for kind in ["start","rejected","empty","positions","wrong-revision",
            "atlas","model-invalid","model-render"]:
        var renderer := Renderer.new()
        var feedback := Feedback.new()
        var session := Session.new(renderer,feedback)
        var requests: Array = []
        var actions: Array = []
        var publications: Array = []
        track(session,requests,actions,publications)
        session.update_context(context(9),0)
        var layout_id: int = session.pending_id("layout")
        match kind:
            "start":
                session.request_start_result("layout",layout_id,ERR_CANT_CONNECT,1)
            "rejected":
                session.complete_response("layout",layout_id,1,
                    body({"error":"Invalid score"}),1)
            "empty":
                session.complete_response("layout",layout_id,0,PackedByteArray(),1)
            "positions":
                session.complete_response("layout",layout_id,0,
                    body({"revision":9}),1)
            "wrong-revision":
                session.complete_response("layout",layout_id,0,
                    body(layout(10)),1)
            _:
                if kind == "atlas":
                    renderer.atlas_ok = false
                finish_layout(session,9,1)
                if kind == "model-invalid":
                    session.complete_response("model",session.pending_id("model"),0,
                        "not json".to_utf8_buffer(),2)
                elif kind == "model-render":
                    renderer.model_ok = false
                    finish_model(session,9,2)
        var accepted_message := not session.score_error.is_empty()
        check(accepted_message and not session.is_ready() and not renderer.visible,
            "score failure must reject partial score: "+kind)
        check(actions.is_empty() and publications.is_empty(),
            "failed score must never acknowledge MIDI start: "+kind)
        check(session.status()["retry_visible"] and session.status()["browse_visible"],
            "score error offers Retry and Browse: "+kind)
        check(feedback.bindings[-1] == [renderer,-1],
            "failed score must detach native feedback: "+kind)
    var renderer := Renderer.new()
    var session := Session.new(renderer)
    session.update_context(context(10),0)
    renderer.retained_ok = false
    finish_layout(session,10,10)
    finish_model(session,10,20)
    check(not session.is_ready(),"retained ink must be ready before score acknowledgement")
    session.poll(45020)
    check(session.status()["retry_visible"] and not session.is_ready(),
        "stalled retained ink fails visibly after bounded deadline")

func test_native() -> void:
    var Native := load("res://notation/native/view.gd")
    var NativeFeedback := load("res://native_score_feedback.gd")
    var renderer: Control = Native.new()
    var feedback: Node = NativeFeedback.new()
    var session := Session.new(renderer,feedback)
    session.update_context(context(13),0)
    finish_layout(session,13,1)
    check(not session.score_error.is_empty() and not session.is_ready(),
        "real native renderer must reject missing authentic brace glyph")
    check(not renderer.visible and feedback.score_revision == -1 and
        feedback.bound_revisions().is_empty(),
        "real native feedback must be detached on glyph rejection")
    check(session.retry(2),"native failure can restart canonical asset lifecycle")
    feedback.free()
    renderer.free()
    check(not session.is_ready(),"freed native view cannot retain readiness")
