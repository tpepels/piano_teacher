extends RefCounted
const StreamGeometry := preload("res://notation/native/stream_geometry.gd")
## Sole two-phase physical commit executor for timed native-score requests.
## The pure ScoreTransportReservation preflight runs against actual renderer
## glyphs, peer layers and immutable queue. This executor is the only
## adapter allowed to withdraw a future suffix and arm its replacement.
const TransportReservation := preload("res://score_transport_reservation.gd")

static func reserve_action(stream, facts: StreamGeometry, preflight: Dictionary,
        action: String, world: float, opening: float, count_in_beats: float,
        right: float, header: float, bpm: float) -> Dictionary:
    # The ONLY user-command route. First compute both the future slot and
    # safe suffix on immutable previews; failed preflight cannot withdraw
    # any source or start the backend transport. count_in_beats is the
    # engine's next_count_in_beats (one count-in bar).
    var planned: Dictionary = TransportReservation.plan_facts(
        preflight,action,world,opening,count_in_beats)
    if not bool(planned.get("ok",false)):
        push_error("SCORE_TRANSPORT_PREFLIGHT: %s action=%s opening=%.3f" % [
            str(planned.get("reason","unknown")),action,opening])
        return {}
    var mode: String = str(planned["mode"])
    var before: Array = stream.online_snapshot()
    if mode == "reuse":
        if action == "resume":
            # The SAME preflight that chose this source identifies the
            # protected owner. Never run a second, independent selection
            # procedure against a partially modified queue.
            stream.trim(facts,"resume_reuse",int(planned["protected_take"]))
        var existing: Dictionary = stream.arm_take(facts,
            world,opening,right,header,NAN,action == "resume",false)
        var removed: Array = before.slice(stream.online_size())
        if existing.is_empty():
            push_error("SCORE_TRANSPORT_COMMIT: preflight reusable owner vanished")
            if not removed.is_empty():
                stream.restore_future_suffix(facts,removed,facts.world)
            return {}
        stream.remember_withdrawn_suffix(removed)
        return stream.receipt(planned,existing,world,opening,
            facts.first_header_spaces if opening <= .0001 else 1.6,
            facts.density,facts.gap,facts.duration,facts.world,right,bpm)
    # The preflight and actual withdrawal share Queue.preview_tail_withdrawal
    # and the SAME world coordinate. Do not recalculate a different
    # placement after removing the unseen suffix.
    var intended: float = float(planned["start_world"])
    stream.trim(facts,"user_"+action+"_replace_unseen")
    var removed: Array = before.slice(stream.online_size())
    if stream.online_size() != int(planned["remaining_count"]):
        push_error("SCORE_TRANSPORT_COMMIT: online queue changed during preflight")
        if not removed.is_empty():
            stream.restore_future_suffix(facts,removed,facts.world)
        return {}
    stream.retry_placement_enabled(action == "restart")
    var admitted: Dictionary = stream.arm_take(facts,
        world,opening,right,header,intended,false,false,
        count_in_beats if bool(planned.get("empty_strip",false)) else 0.0)
    stream.retry_placement_enabled(false)
    if admitted.is_empty():
        push_error("SCORE_TRANSPORT_COMMIT: preflighted future take was not admitted")
        if not removed.is_empty():
            stream.restore_future_suffix(facts,removed,facts.world)
        return {}
    if absf(float(admitted.get("start_world",NAN))-intended) > .0001:
        push_error("SCORE_TRANSPORT_COMMIT: grading and score deadlines diverged")
        stream.cancel_arm(facts,facts.world)
        if not removed.is_empty():
            stream.restore_future_suffix(facts,removed,facts.world)
        return {}
    stream.remember_withdrawn_suffix(removed)
    return stream.receipt(planned,admitted,world,opening,
        facts.first_header_spaces if opening <= .0001 else 1.6,
        facts.density,facts.gap,facts.duration,facts.world,right,bpm)
