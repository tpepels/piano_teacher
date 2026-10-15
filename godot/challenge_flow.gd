extends RefCounted

# Pure presentation of the engine's existing three-clean-run lesson rule.
# The backend alone decides whether a take was clean, whether a stage is
# mastered, and when it is safe to advance to a new hand or passage.
static func present(state: Dictionary) -> Dictionary:
    if not bool(state.get("loaded", false)):
        return {"visible":false, "label":"", "detail":"", "kind":"idle"}
    var mode: String = str(state.get("mode", "practice"))
    if mode not in ["practice", "learn"]:
        return {"visible":false, "label":"", "detail":"", "kind":"idle"}
    var name: String = str(state.get("hand", "right"))
    var hand: String = "BOTH HANDS" if name == "both" else name.to_upper() + " HAND"
    var raw_streak: int = clampi(int(state.get("streak", 0)), 0, 3)
    var phase: String = str(state.get("phase", "ready"))
    if mode == "learn":
        var teaching: Dictionary = state.get("teaching", {}) if state.get("teaching") is Dictionary else {}
        var done: int = maxi(0, int(teaching.get("target_index", 0)))
        var total: int = maxi(0, int(teaching.get("target_count", 0)))
        var learner: Dictionary = state.get("learner", {}) if state.get("learner") is Dictionary else {}
        var idea: int = int(learner.get("unit_number", 0))
        var units: int = int(learner.get("total_units", 0))
        var context: String = ("Idea %d/%d" % [idea, maxi(idea, units)]
            if idea > 0 else hand + " · FIND NOTES")
        return {"visible":true,
            "label":context + " · " + hand,
            "detail":"%d of %d notes found · timing comes later" % [done, total],
            "kind":"learn", "streak":raw_streak}
    if bool(state.get("preview_only", false)):
        return {"visible":true, "label":"%s · PREVIEW" % hand,
            "detail":"MIDI piano required to earn clean runs",
            "kind":"preview", "streak":0}
    var result: Variant = state.get("take_result")
    if phase == "feedback" and result is Dictionary:
        if bool(result.get("clean", false)):
            var completed: int = mini(3, raw_streak + 1)
            var detail := "Three clean full passes unlock the next stage"
            var seconds = state.get("transition_in_seconds")
            if seconds != null and bool(state.get("auto", false)):
                detail = "Next automatically in %.1f s" % maxf(0.0, float(seconds))
            return {"visible":true,
                "label":"✓ CLEAN PASS · %s · %d/3" % [hand, completed],
                "detail":detail,
                "kind":"success", "streak":completed}
        return {"visible":true,
            "label":"RETRY · %s" % hand,
            "detail":"Review the red notes; the clean-run streak resets",
            "kind":"retry", "streak":0}
    if phase == "recovering":
        return {"visible":true, "label":"SHORT RETRY · %s" % hand,
            "detail":str(state.get("next_action", "Practise the difficult bars again")),
            "kind":"recovering", "streak":raw_streak}
    var label := "%s · %d/3 CLEAN" % [hand, raw_streak]
    var detail := "Play this short challenge three times cleanly"
    if bool(state.get("warmup", false)):
        detail = "Next hand unlocks after three clean runs"
        if name == "both":
            detail = "Final stage · master both hands together"
    if phase == "paused":
        detail = "Paused · press Play when ready"
    elif phase == "count_in":
        detail = "Get ready · the count-in is not graded"
    elif phase == "playing":
        detail = "Follow the score · each chord note counts separately"
    elif phase == "loading":
        detail = "Preparing the next short challenge"
    return {"visible":true, "label":label,
            "detail":detail, "kind":"progress", "streak":raw_streak}


static func newly_unlocked(previous: Dictionary, current: Dictionary) -> String:
    # Only respond to a real backend transition; restoring already-complete
    # stages or switching to another piece never replays a celebration.
    if not bool(previous.get("loaded", false)) or not bool(current.get("loaded", false)):
        return ""
    if str(previous.get("title", "")) != str(current.get("title", "")):
        return ""
    var old_stages: Dictionary = {}
    for stage in previous.get("hand_stages", []):
        old_stages[str(stage.get("hand", ""))] = bool(stage.get("complete", false))
    if old_stages.is_empty():
        return ""
    for stage in current.get("hand_stages", []):
        var hand: String = str(stage.get("hand", ""))
        if not old_stages.has(hand) or bool(old_stages[hand]) or not bool(stage.get("complete", false)):
            continue
        var next_hand := ""
        for following in current.get("hand_stages", []):
            if bool(following.get("active", false)) and not bool(following.get("complete", false)):
                next_hand = str(following.get("hand", ""))
                break
        var completed_name: String = "BOTH HANDS" if hand == "both" else hand.to_upper() + " HAND"
        if next_hand.is_empty():
            return "✓ %s COMPLETE" % completed_name
        var upcoming: String = "BOTH HANDS" if next_hand == "both" else next_hand.to_upper() + " HAND"
        return "✓ %s COMPLETE · %s UNLOCKED" % [completed_name, upcoming]
    return ""
