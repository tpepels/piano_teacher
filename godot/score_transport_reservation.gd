extends RefCounted
## One pure preflight for every user-triggered Play/Resume/Retry.
## All source geometry, queue exposure and peer-layer accounting live in
## existing authoritative ScoreStreamAdmission / ScoreStreamQueue contracts.
## This class cannot create, move, arm, or remove CanvasItems.
const Admission := preload("res://score_stream_admission.gd")

static func _refuse(reason: String) -> Dictionary:
    return {"ok":false,"reason":reason}

static func plan(renderer, action: String, world: float,
        source_opening: float) -> Dictionary:
    if action not in ["start","resume","restart"]:
        return _refuse("unsupported_action")
    if not is_finite(world) or not is_finite(source_opening):
        return _refuse("invalid_transport_coordinate")
    if not bool(renderer.native_ready) or not renderer.retained_ready():
        return _refuse("notation_not_compiled")
    var duration: float = float(renderer.timeline.duration_beats)
    if duration <= 0.0 or source_opening < 0.0 or             source_opening >= duration:
        return _refuse("invalid_source_interval")
    if renderer._stream_source_windows(source_opening).is_empty():
        return _refuse("no_source_measures")
    var density: float = float(renderer.timeline.pixels_per_beat)
    var staff_gap: float = float(renderer.staff_gap())
    var width: float = float(renderer.size.x)
    if density <= 0.0 or staff_gap <= 0.0 or width < 100.0:
        return _refuse("score_viewport_not_ready")
    var queue = renderer._stream_queue
    var right: float = renderer._stream_right_beats()
    var header: float = renderer._stream_header_beats(source_opening)
    var preview_world: float = maxf(world,float(renderer.stream_world_beat))
    # A prepared, fully offscreen take is the cheapest valid reservation.
    # Reuse MUST be verified before planning any tail withdrawal.
    var reusable := -1
    if action == "start":
        reusable = Admission.select(queue.online,"ready",
            source_opening,preview_world,right,header)
    elif action == "resume":
        if bool(renderer._stream_was_paused) and                 absf(source_opening-float(renderer._stream_paused_source)) < .0001:
            reusable = Admission.select(queue.online,"paused",
                source_opening,preview_world,0.0,0.0,
                str(renderer._stream_last_take))
        if reusable < 0:
            reusable = Admission.select(queue.online,"automatic",
                source_opening,preview_world,right,header)
    if reusable >= 0:
        return {"ok":true,"mode":"reuse","action":action,
            "opening":source_opening,
            "protected_take":int(queue.online[reusable].get("take_owner",
                queue.online[reusable]["serial"])),
            "start_world":float(queue.online[reusable]["world_origin"]) +
                source_opening,"reason":"existing_future_owner"}
    # All possible mutations are previewed on a local ARRAY copy only.
    # Visible and already-exposed strips remain fixed forever.
    var withdrawn: Dictionary = queue.preview_tail_withdrawal(
        preview_world,density,staff_gap,duration,width,
        width*renderer.PLAYHEAD_FRACTION)
    var survivors: Array = withdrawn["remaining"]
    var onset: float = Admission.position(survivors,preview_world,
        right,header,NAN,Admission.READY_TRAVEL_BEATS,
        density,staff_gap,duration)
    var peer_floor: float = queue.minimum_peer_opening(
        density,width,width*renderer.PLAYHEAD_FRACTION)
    if is_finite(peer_floor):
        onset = maxf(onset,peer_floor+header+Admission.REST_GAP_BEATS)
    if not is_finite(onset):
        return _refuse("no_finite_future_slot")
    var first_pixel_x: float = width*renderer.PLAYHEAD_FRACTION +         (onset-header-preview_world)*density
    if first_pixel_x <= width:
        return _refuse("not_fully_offscreen")
    return {"ok":true,"mode":"append","action":action,
        "opening":source_opening,"start_world":onset,
        "first_pixel_x":first_pixel_x,
        "first_ink_delay_seconds":
            maxf(0.0,(first_pixel_x-width)/density)*60.0/
                maxf(1.0,float(renderer.bpm)),
        "remaining_count":survivors.size(),
        "withdraw_owners":withdrawn["owners"].duplicate(),
        "reason":"new_immutable_future_slot"}
