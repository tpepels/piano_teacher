extends RefCounted
## Sole mutable ledger of this renderer revision's note/rest streams.
## The retained queue enforces immutable on-screen geometry and safe
## append/withdraw. View performs drawing and passes geometry capabilities.
## Physical admission operates on this ledger; a repaint never resets it.
const StreamQueue := preload("res://score_stream_queue.gd")

var queue = StreamQueue.new()
var last_take := ""
var was_paused := false
var paused_source := 0.0
var paused_owner := -1
var live_serial := -1
var armed_serial := -1
var armed_segment_id := ""
var live_segment_id := ""
var arm_rollback: Dictionary = {}
var arm_acknowledged := false
var serial := 0
var last_admitted := -1
var planned_ids: Dictionary = {}
var planned_openings: Dictionary = {}
var retry_placement := false

func reset(view) -> void:
    # No direct queue array replacement: the queue first releases its own
    # previously visible/archived retained source strips and peer references.
    queue.reset(view)
    planned_ids.clear()
    planned_openings.clear()
    last_take = ""
    was_paused = false
    paused_source = 0.0
    paused_owner = -1
    live_serial = -1
    armed_serial = -1
    armed_segment_id = ""
    live_segment_id = ""
    arm_rollback.clear()
    arm_acknowledged = false
    last_admitted = -1
    retry_placement = false

func register_predecessor(previous) -> void:
    queue.register_peer(previous)

func queue_generation() -> int:
    return serial

func bound_segment() -> String:
    return live_segment_id

func has_armed_reservation() -> bool:
    return armed_serial >= 0 and arm_acknowledged
