extends SceneTree
# The renderer/feedback doubles expose only their actual component boundary.
# Literal revisions, deadlines and HTTP bodies exercise the session decisions.
class Atlas:
    extends RefCounted
    var loaded := false
    func ready() -> bool:
        return loaded

class Renderer:
    extends RefCounted
    var glyphs := Atlas.new()
    var native_ready := false
    var visible := false
    var failure_reason := "authentic asset failure"
    var notice := ""
    var atlas_ok := true
    var model_ok := true
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
    func clear_score() -> void:
        clears += 1
        native_ready = false
    func queue_redraw() -> void:
        redraws += 1

class Feedback:
    extends RefCounted
    var bindings: Array = []
    var states: Array = []
    func bind_score(renderer, revision: int) -> void:
        bindings.append([renderer,revision])
    func present(state: Dictionary) -> void:
        states.append(state.duplicate(true))

var Session
var failures := 0

func check(condition: bool, label: String) -> void:
    if not condition:
        failures += 1
        print("FAIL: ",label)

func _initialize() -> void:
    if not FileAccess.file_exists("res://score_asset_session.gd"):
        check(false,"independent score asset owner missing")
        finish()
        return
    Session = load("res://score_asset_session.gd")
    call_deferred("run_contract")

func finish() -> void:
    print("SCORE_ASSET_SESSION_FAILURES:",failures)
    quit(0 if failures == 0 else 1)

func state(revision: int, phase: String = "loading") -> Dictionary:
    return {"loaded":true,"revision":revision,"phase":phase,
        "awaiting_score_revision":revision,"piece_fingerprint":"piece-"+str(revision),
        "feedback_marks":[{"note_id":"source-a","status":"correct"}]}

func layout(revision: int) -> Dictionary:
    return {"revision":revision,"anchors":[{"id":"a"}],"attack_map":{"source-a":"a"},
        "native_glyphs":{"font":"authentic"},"native_note_templates":{"note":1},
        "native_tie_templates":{"tie":2},"native_chord_templates":{"chord":3},
        "native_beam_fragments":{"beam":4},"native_tuplet_fragments":{"tuplet":5},
        "native_slur_fragments":{"slur":6},"native_required_slur_pairs":[["a","b"]],
        "native_slurs_complete":true,"native_required_beam_groups":["a|b"],"native_beams_complete":true}

func body(value: Variant) -> PackedByteArray:
    return JSON.stringify(value).to_utf8_buffer()

func wire(session, requests: Array, actions: Array, publications: Array) -> void:
    session.request_requested.connect(func(kind: String, id: int, path: String, timeout: float):
        requests.append({"kind":kind,"id":id,"path":path,"timeout":timeout}))
    session.action_requested.connect(func(command: Dictionary): actions.append(command))
    session.score_published.connect(func(revision: int): publications.append(revision))

func run_contract() -> void:
    var contract: String = OS.get_cmdline_user_args()[0]
    if contract == "publication":
        test_publication()
    elif contract == "stale":
        test_stale_responses()
    elif contract == "retry":
        test_retry()
    elif contract == "failure":
        test_failures()
    elif contract == "native":
        test_actual_renderer_boundary()
    finish()

func test_publication() -> void:
    var renderer := Renderer.new()
    var feedback := Feedback.new()
    renderer.native_ready = true  # Borrowed old ink is not this owner's publication.
    var session = Session.new(renderer,feedback)
    check(not session.is_ready(),"fresh owner cannot inherit readiness from a preloaded renderer")
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    wire(session,requests,actions,publications)
    check(session.status()["text"] == "Choose a piece to begin" and session.status()["browse_visible"],"empty selection status")
    session.update_context(state(7),100)
    check(requests.size() == 1 and requests[0]["kind"] == "layout" and requests[0]["path"] == "/score/layout?native=1" and requests[0]["timeout"] == 90.0,"exact native layout request intent")
    check(session.layout_pending and not session.timeline_model_pending and not session.is_ready(),"layout is not semantic readiness")
    session.poll(500)
    check(requests.size() == 1 and actions.is_empty(),"model and ack wait for atlas")
    # An unsolicited/out-of-order model cannot bypass the real two-part gate.
    session.complete_response("model",999,200,body({"revision":7}),501)
    check(renderer.model_calls.is_empty() and actions.is_empty(),"unsolicited model cannot publish")
    session.complete_response("layout",int(requests[0]["id"]),200,body(layout(7)),600)
    check(renderer.atlas_calls == [[{"font":"authentic"},{"note":1.0},{"tie":2.0},{"chord":3.0},{"beam":4.0},{"tuplet":5.0},{"slur":6.0},[["a","b"]],true,["a|b"],true]],"authentic atlas arguments and completeness flags preserved")
    check(requests.size() == 2 and requests[1]["path"] == "/score/model" and requests[1]["timeout"] == 5.0,"model follows published authentic atlas")
    check(session.layout_revision == 7 and session.timeline_model_revision == -1 and session.rendered_revision == -1 and not session.is_ready() and actions.is_empty(),"both publications required before acknowledgment")
    var published: Dictionary = session.layout_snapshot()
    check(published == {"revision":7.0,"anchors":[{"id":"a"}],"attack_map":{"source-a":"a"}},"layout publication strips heavy native assets")
    published["anchors"].clear()
    check(session.layout_snapshot()["anchors"].size() == 1,"layout snapshot cannot mutate owned publication")
    session.complete_response("model",int(requests[1]["id"]),200,body({"revision":7,"notes":[{"id":"a"}]}),700)
    check(session.is_ready() and session.rendered_revision == 7 and session.timeline_model_revision == 7 and renderer.visible,"matching model and atlas publish one ready score")
    check(actions == [{"action":"score_ready","revision":7}] and publications == [7],"readiness ack is exact and current")
    check(feedback.bindings[-1] == [renderer,7] and feedback.states[-1] == state(7),"feedback binds to actual renderer after model success")
    check(session.native_score_piece_fingerprint == "piece-7" and not session.status()["visible"],"piece identity and status readiness published together")
    session.update_context(state(7,"ready"),800)
    check(requests.size() == 2 and actions.size() == 1,"same ready state does not reload score")
    renderer.native_ready = false
    check(not session.is_ready(),"renderer readiness participates in public predicate")
    var next_renderer := Renderer.new()
    var next_session = Session.new(next_renderer)
    var next_requests: Array = []
    var next_actions: Array = []
    var next_publications: Array = []
    wire(next_session,next_requests,next_actions,next_publications)
    var context: Dictionary = state(8)
    context["awaiting_score_revision"] = 7
    next_session.update_context(context,0)
    next_session.complete_response("layout",int(next_requests[-1]["id"]),200,body(layout(8)),1)
    next_session.complete_response("model",int(next_requests[-1]["id"]),200,body({"revision":8}),2)
    check(next_session.is_ready() and next_actions.is_empty(),"finish-time ack waits for backend awaiting revision to match")

func test_stale_responses() -> void:
    var renderer := Renderer.new()
    var session = Session.new(renderer)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    wire(session,requests,actions,publications)
    session.update_context(state(1),0)
    var first: int = requests[-1]["id"]
    session.update_context(state(2),1)
    check(requests.size() == 1,"revision change preserves in-flight layout slot")
    session.complete_response("layout",first,503,body({"error":"old layout failed"}),2)
    check(session.score_error.is_empty() and renderer.atlas_calls.is_empty() and requests.size() == 2,"old layout failure cannot poison new revision; current layout requested")
    var current: int = requests[-1]["id"]
    session.complete_response("layout",first,200,body(layout(1)),3)
    check(session.layout_pending and requests.size() == 2,"duplicate old reply cannot consume current request slot")
    session.complete_response("layout",current,200,body(layout(2)),4)
    var old_model: int = requests[-1]["id"]
    session.update_context(state(3),5)
    check(not renderer.visible and not session.is_ready() and session.layout_snapshot().is_empty(),"new revision hides previous asset publication")
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(3)),6)
    check(session.layout_revision == 3 and session.timeline_model_pending,"current atlas may finish before previous model drains")
    session.complete_response("model",old_model,500,body({"error":"old model failed"}),7)
    check(session.score_error.is_empty() and renderer.model_calls.is_empty() and requests[-1]["kind"] == "model" and requests[-1]["id"] != old_model,"stale model transport failure drains without current retry delay")
    var model_id: int = requests[-1]["id"]
    session.complete_response("model",old_model,200,body({"revision":3}),8)
    check(session.timeline_model_pending and renderer.model_calls.is_empty(),"old token cannot publish even with current payload revision")
    session.complete_response("model",model_id,200,body({"revision":2}),9)
    check(renderer.model_calls.is_empty() and actions.is_empty(),"wrong model revision ignored")
    session.poll(10)
    session.complete_response("model",int(requests[-1]["id"]),200,body({"revision":3}),11)
    check(session.is_ready() and actions == [{"action":"score_ready","revision":3}],"only current revision completes readiness")
    var replacement: Dictionary = state(3)
    replacement["piece_fingerprint"] = "another-piece"
    session.update_context(replacement,12)
    session.complete_response("model",model_id,200,body({"revision":3}),13)
    check(not session.is_ready() and session.native_score_piece_fingerprint.is_empty(),"piece identity change cannot reuse old readiness even at same revision")
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(3)),14)
    session.complete_response("model",int(requests[-1]["id"]),200,body({"revision":3}),15)
    check(session.is_ready() and session.native_score_piece_fingerprint == "another-piece","fresh publication binds current piece identity")
    session.update_context(state(4),16)
    var pending_layout: int = requests[-1]["id"]
    var prior: int = requests.size()
    session.update_context({"loaded":false,"revision":4},17)
    session.complete_response("layout",pending_layout,500,body({"error":"obsolete"}),18)
    check(not session.is_ready() and not renderer.visible and requests.size() == prior and session.status()["browse_visible"] and session.score_error.is_empty(),"unloaded context drains old requests without publishing or requesting a model")

func test_retry() -> void:
    var renderer := Renderer.new()
    var session = Session.new(renderer)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    wire(session,requests,actions,publications)
    check(not session.retry(0),"retry is inert without a loaded score")
    session.update_context(state(5),10)
    check(not session.retry(11) and requests.size() == 1,"retry cannot duplicate pending layout")
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(5)),20)
    session.complete_response("model",int(requests[-1]["id"]),503,body({"error":"busy"}),100)
    check(session.timeline_model_retry_after_ms == 2100 and session.score_error.is_empty() and renderer.notice == "Score model unavailable; retrying","semantic transport failure keeps exact nonfatal backoff")
    session.poll(2099)
    check(requests.size() == 2,"backoff forbids early semantic retry")
    session.poll(2100)
    check(requests.size() == 3,"semantic retry starts at exact deadline")
    session.request_start_result("model",int(requests[-1]["id"]),ERR_CANT_CONNECT,2200)
    check(not session.timeline_model_pending and session.timeline_model_retry_after_ms == 4200 and renderer.notice == "Cannot load semantic score","request-start failure releases model slot and preserves notice")
    session.poll(4200)
    var old_model: int = requests[-1]["id"]
    check(session.retry(4201),"explicit retry resets entire asset publication")
    check(session.layout_revision == -1 and session.timeline_model_revision == -1 and session.rendered_revision == -1,"retry resets all readiness revisions")
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(5)),4202)
    session.complete_response("model",old_model,200,body({"revision":5}),4203)
    check(renderer.model_calls.is_empty() and actions.is_empty(),"same-revision model from prior retry generation cannot acknowledge new assets")
    session.complete_response("model",int(requests[-1]["id"]),200,body({"revision":5}),4204)
    check(session.is_ready(),"fresh model completes retried score")
    # Finish-time ack is conditional on the backend awaiting this revision;
    # a later loading poll can repeat an intent dropped by a busy action port.
    var loading: Dictionary = state(5)
    session.update_context(loading,4205)
    check(actions.size() == 2,"ready loading poll retains acknowledgment retry behavior")

func test_failures() -> void:
    for damage in ["start","http","empty","positions","atlas","model","model-json"]:
        var renderer := Renderer.new()
        var feedback := Feedback.new()
        var session = Session.new(renderer,feedback)
        var requests: Array = []
        var actions: Array = []
        var publications: Array = []
        wire(session,requests,actions,publications)
        session.update_context(state(9),0)
        var id: int = requests[-1]["id"]
        if damage == "start":
            session.request_start_result("layout",id,ERR_CANT_CONNECT,1)
            check(session.score_error == "Cannot request score geometry from the practice engine","layout start failure message")
        elif damage == "http":
            session.complete_response("layout",id,422,body({"error":"Unusable source"}),1)
            check(session.score_error == "Unusable source","layout HTTP detail retained")
        elif damage == "empty":
            session.complete_response("layout",id,0,PackedByteArray(),1)
            check(session.score_error == "Practice engine unavailable. Start Piano Teacher with ./run.sh","unavailable engine message")
        elif damage == "positions":
            session.complete_response("layout",id,200,body({"revision":9}),1)
            check(session.score_error == "The engraving engine returned invalid note positions","invalid layout position message")
        else:
            renderer.atlas_ok = damage != "atlas"
            session.complete_response("layout",id,200,body(layout(9)),1)
            if damage == "model":
                renderer.model_ok = false
                session.complete_response("model",int(requests[-1]["id"]),200,body({"revision":9}),2)
            elif damage == "model-json":
                session.complete_response("model",int(requests[-1]["id"]),200,"bad json".to_utf8_buffer(),2)
                check(session.score_error.is_empty() and session.timeline_model_retry_after_ms == 2002,"malformed semantic response is retried without parser errors")
                continue
            check(session.score_error == "authentic asset failure","authentic renderer rejection message retained")
        check(not session.is_ready() and not renderer.visible and actions.is_empty() and publications.is_empty(),"failure cannot expose or acknowledge partial assets: "+damage)
        check(session.rendered_revision == -1 and session.timeline_model_revision == -1 and feedback.bindings[-1] == [renderer,-1],"failure clears renderer and feedback readiness: "+damage)
        check(session.status()["retry_visible"] and not session.status()["browse_visible"] and session.status()["text"] == "Unable to display sheet music:\n"+session.score_error,"failed status preserves retry affordance: "+damage)
    var renderer := Renderer.new()
    var session = Session.new(renderer)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    wire(session,requests,actions,publications)
    session.update_context(state(10),0)
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(11)),1)
    check(session.score_error.is_empty() and session.layout_revision == -1 and requests.size() == 1,"layout from advanced server waits for normal revision poll")
    session.update_context(state(11),2)
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(11)),3)
    renderer.glyphs.loaded = false
    session.complete_response("model",int(requests[-1]["id"]),200,body({"revision":10}),4)
    var count: int = requests.size()
    session.poll(5)
    check(requests.size() == count,"semantic retry waits for genuine atlas readiness")


func test_actual_renderer_boundary() -> void:
    var Native = load("res://notation/native/view.gd")
    var NativeFeedback = load("res://native_score_feedback.gd")
    var renderer: Control = Native.new()
    var feedback: Control = NativeFeedback.new()
    var session = Session.new(renderer,feedback)
    var requests: Array = []
    var actions: Array = []
    var publications: Array = []
    wire(session,requests,actions,publications)
    session.update_context(state(13),0)
    session.complete_response("layout",int(requests[-1]["id"]),200,body(layout(13)),1)
    check(session.score_error == "Missing authentic Verovio glyph: brace" and not session.is_ready(),"real renderer validates authentic atlas at actual publication boundary")
    check(not renderer.visible and feedback.score_revision == -1 and feedback.source_to_id.is_empty(),"actual native feedback is detached from failed assets")
    check(actions.is_empty() and publications.is_empty(),"actual renderer rejection never acknowledges readiness")
    check(session.retry(2) and requests.size() == 2,"retry uses actual renderer clear lifecycle")
    feedback.free()
    renderer.free()
    check(not session.is_ready(),"borrowed renderer lifetime cannot leave stale readiness")
