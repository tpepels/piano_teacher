extends RefCounted
# Source-event queues for stage reactions. NativeScoreFeedback owns visible
# score marks; these queues never draw or transform page-coordinate ink.
var marks: Array = []
var hit_pulses: Array = []
var wrong_ghosts: Array = []
var preview_pulses: Array = []

func prune_expired(ticks_ms: int) -> void:
    # Visual lifespan only. No scoring, timing, or MIDI input is modified.
    for queue in [hit_pulses, wrong_ghosts, preview_pulses]:
        for index in range(queue.size() - 1, -1, -1):
            if int(queue[index].get("until_ms", 0)) <= ticks_ms:
                queue.remove_at(index)
