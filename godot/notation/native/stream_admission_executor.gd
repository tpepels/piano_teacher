extends RefCounted
## Sole two-phase physical commit executor for timed native-score requests.
## The pure ScoreTransportReservation preflight runs against actual renderer
## glyphs, peer layers and immutable queue. This executor is the only
## adapter allowed to withdraw a future suffix and arm its replacement.
const TransportReservation := preload("res://score_transport_reservation.gd")

static func reserve_action(view, action: String, world: float,
        opening: float, count_in_beats: float) -> Dictionary:
    # The ONLY user-command route. First compute both the future slot and
    # safe suffix on immutable previews; failed preflight cannot withdraw
    # any source or start the backend transport. count_in_beats is the
    # engine's next_count_in_beats (one count-in bar).
    var planned: Dictionary = TransportReservation.plan(
        view,action,world,opening,count_in_beats)
    if not bool(planned.get("ok",false)):
        push_error("SCORE_TRANSPORT_PREFLIGHT: %s action=%s opening=%.3f" % [
            str(planned.get("reason","unknown")),action,opening])
        return {}
    view.stream_world_beat = maxf(view.stream_world_beat,world)
    var mode: String = str(planned["mode"])
    var before: Array = view._stream_queue.online.duplicate(true)
    if mode == "reuse":
        if action == "resume":
            # The SAME preflight that chose this source identifies the
            # protected owner. Never run a second, independent selection
            # procedure against a partially modified queue.
            view.trim_future_queue("resume_reuse",int(planned["protected_take"]))
        var existing: Dictionary = view.arm_stream_take(
            world,opening,NAN,action == "resume",false)
        var removed: Array = before.slice(view._stream_queue.online.size())
        if existing.is_empty():
            push_error("SCORE_TRANSPORT_COMMIT: preflight reusable owner vanished")
            if not removed.is_empty():
                view._restore_future_suffix(removed,view.stream_world_beat)
            return {}
        view._stream_arm_rollback["withdrawn_suffix"] = removed
        return view._transport_admission_receipt(planned,existing,world,opening)
    # The preflight and actual withdrawal share Queue.preview_tail_withdrawal
    # and the SAME world coordinate. Do not recalculate a different
    # placement after removing the unseen suffix.
    var intended: float = float(planned["start_world"])
    view.trim_future_queue("user_"+action+"_replace_unseen")
    var removed: Array = before.slice(view._stream_queue.online.size())
    if view._stream_queue.online.size() != int(planned["remaining_count"]):
        push_error("SCORE_TRANSPORT_COMMIT: online queue changed during preflight")
        if not removed.is_empty():
            view._restore_future_suffix(removed,view.stream_world_beat)
        return {}
    view._retry_placement = action == "restart"
    var admitted: Dictionary = view.arm_stream_take(
        world,opening,intended,false,false,
        count_in_beats if bool(planned.get("empty_strip",false)) else 0.0)
    view._retry_placement = false
    if admitted.is_empty():
        push_error("SCORE_TRANSPORT_COMMIT: preflighted future take was not admitted")
        if not removed.is_empty():
            view._restore_future_suffix(removed,view.stream_world_beat)
        return {}
    if absf(float(admitted.get("start_world",NAN))-intended) > .0001:
        push_error("SCORE_TRANSPORT_COMMIT: grading and score deadlines diverged")
        view.cancel_stream_arm()
        if not removed.is_empty():
            view._restore_future_suffix(removed,view.stream_world_beat)
        return {}
    view._stream_arm_rollback["withdrawn_suffix"] = removed
    return view._transport_admission_receipt(planned,admitted,world,opening)
