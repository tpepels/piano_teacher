extends SceneTree
## The asset port supplies completion/failure facts; ScoreAssetSession makes
## every readiness, stale-response and recovery decision. A genuine native
## renderer also checks rejection of incomplete engraving.
const Session := preload("res://score_asset_session.gd")
const Native := preload("res://notation/native/view.gd")

class GlyphFacts:
    extends RefCounted
    var accepted := false
    func ready() -> bool: return accepted

class AssetPort:
    extends RefCounted
    signal retained_ink_compiled
    var glyphs := GlyphFacts.new()
    var native_ready := false
    var visible := false
    var compiled := false
    var failure_reason := "Incomplete source engraving"
    var notice := ""
    func set_verovio_glyphs(_font, _notes, _ties, _chords, _beams, _tuplets,
            _slurs, _required_slurs, _slurs_complete, _required_beams, _beams_complete) -> bool:
        glyphs.accepted = true
        return true
    func load_score(_candidate: Dictionary) -> bool:
        native_ready = true
        return true
    func retained_ready() -> bool: return compiled
    func retained_generation() -> int: return 0
    func clear_score() -> bool:
        native_ready = false
        glyphs.accepted = false
        compiled = false
        return true
    func queue_redraw() -> void: pass

var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("SCORE_READINESS_FAIL: ",message)

func state(revision: int) -> Dictionary:
    return {"loaded":true,"revision":revision,"piece_fingerprint":"piece-%d" % revision,
        "phase":"loading","awaiting_score_revision":revision}

func reply(session, kind: String, revision: int, at_ms: int = 0) -> void:
    var data := {"revision":revision,"anchors":[{"id":"head"}],"notes":[{"id":"source"}]}
    session.complete_response(kind,session.pending_id(kind),0,JSON.stringify(data).to_utf8_buffer(),at_ms)

func _initialize() -> void:
    print("SCORE_READINESS: expected SCORE_ASSET_FAILURE logs exercise rejection and recovery")
    var assets := AssetPort.new()
    var session := Session.new(assets)
    var actions: Array = []
    session.action_requested.connect(func(value: Dictionary): actions.append(value))
    session.update_context(state(1),0)
    var old_layout: int = session.pending_id("layout")
    session.update_context(state(2),1)
    session.complete_response("layout",old_layout,3,JSON.stringify({"error":"old failure"}).to_utf8_buffer(),2)
    check(session.score_error.is_empty() and not session.is_ready(),"A previous piece's delayed failure cannot poison the selected music")
    reply(session,"layout",2)
    var old_model: int = session.pending_id("model")
    session.update_context(state(3),3)
    session.complete_response("model",old_model,0,JSON.stringify({"revision":2}).to_utf8_buffer(),4)
    check(not session.is_ready() and actions.is_empty(),"A previous piece's timing result cannot authorize playback")
    reply(session,"layout",3)
    reply(session,"model",3)
    check(not session.is_ready() and actions.is_empty(),"Available note data cannot start music before retained notation finishes")
    assets.compiled = true
    assets.retained_ink_compiled.emit()
    check(session.is_ready() and not session.status().visible
        and actions == [{"action":"score_ready","revision":3}],"The complete selected score unblocks playback and clears preparation")
    session.update_context(state(4),5)
    var before_retry: int = session.pending_id("layout")
    check(session.retry(5),"Retry can supersede a preparation that is still pending")
    session.complete_response("layout",before_retry,1,
        JSON.stringify({"error":"Obsolete preparation failed"}).to_utf8_buffer(),6)
    check(session.score_error.is_empty(),"A late result from before Retry cannot reinstate its old error")
    session.complete_response("layout",session.pending_id("layout"),1,
        JSON.stringify({"error":"Cannot engrave this source"}).to_utf8_buffer(),6)
    check(not session.is_ready() and not session.status().error.is_empty()
        and session.status().retry_visible and session.status().browse_visible,
        "A failed score blocks playback and offers Retry or different music")
    check(actions.size() == 1,"Failed preparation cannot authorize an attempt")
    check(session.retry(7),"The learner can retry failed score preparation")
    reply(session,"layout",4)
    reply(session,"model",4)
    assets.compiled = true
    assets.retained_ink_compiled.emit()
    check(session.is_ready() and session.score_error.is_empty()
        and actions[-1] == {"action":"score_ready","revision":4},"Retry recovers the selected score and removes its error")
    session.update_context({"loaded":false,"revision":4},8)
    check(not session.is_ready() and session.status().browse_visible,"Closing music revokes playback readiness")
    var native := Native.new()
    var native_session := Session.new(native)
    native_session.update_context(state(5),0)
    reply(native_session,"layout",5)
    check(not native_session.is_ready() and not native_session.score_error.is_empty()
        and native_session.status().retry_visible,"The real native renderer rejects absent authentic glyphs visibly")
    session.replace_renderer(null)
    native_session.replace_renderer(null)
    native.free()
    print("SCORE_READINESS_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
