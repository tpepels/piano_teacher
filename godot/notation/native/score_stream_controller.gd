extends RefCounted
## Sole mutable ledger of this renderer revision's note/rest streams.
## The retained queue enforces immutable on-screen geometry and safe
## append/withdraw. View performs drawing and passes geometry capabilities.
## Physical admission operates on this ledger; a repaint never resets it.
const StreamQueue := preload("res://score_stream_queue.gd")
const Admission := preload("res://score_stream_admission.gd")

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

func online_snapshot() -> Array:
    # Admission PREPARE reads a frozen copy, never the live FIFO array.
    return queue.online.duplicate(true)

func online_size() -> int:
    return queue.online.size()

func remember_withdrawn_suffix(previous: Array) -> void:
    # Rollback is owned by the stream ledger. The native executor may
    # attach only the exact suffix removed by its immediately preceding
    # successful preflight.
    arm_rollback["withdrawn_suffix"] = previous

func retry_placement_enabled(enabled: bool) -> void:
    retry_placement = enabled

func queue_generation() -> int:
    return serial

func bound_segment() -> String:
    return live_segment_id

func has_armed_reservation() -> bool:
    return armed_serial >= 0 and arm_acknowledged

## A peer can inspect immutable physical clearance facts, not this queue's
## live nodes, serials or rollback state.  This value is recomputed at
## preflight rather than retained across engraving/density changes.
func peer_clearance_facts(density: float, gap: float,
        duration: float, playhead_x: float) -> Dictionary:
    var ends: Array[Dictionary] = []
    for item in queue.online:
        var bounds: Vector2 = Admission.clip_bounds(
            item,density,gap,duration)
        ends.append({
            "rest":str(item.get("kind","source")) == "rest",
            "end_world":float(item["world_origin"])+bounds.y/density
        })
    return {"queue_id":queue.get_instance_id(),"density":density,
        "playhead_x":playhead_x,"ends":ends}

## The queue retires the earliest expired source/rest strips.  The same
## ledger owns the resulting live and armed take identities; the drawing
## view must not repair those identities from retired serials.
func prune_expired(owner: Control, world: float, density: float,
        gap: float, duration: float, playhead_x: float) -> void:
    var retired: Array[int] = queue.expire_front(
        owner,world,density,gap,duration,playhead_x)
    if retired.has(live_serial) and not queue.has_take(live_serial):
        live_serial = -1
    if retired.has(armed_serial) and not queue.has_take(armed_serial):
        armed_serial = -1
        arm_acknowledged = false
        arm_rollback.clear()

var _diagnosed_plans: Dictionary = {}

## Diagnostic deduplication belongs to the same plan ledger that records
## admissions, not to NativeScoreView's paint/repaint lifecycle.
func diagnose_plan(identity: String, outcome: String, deadline_world: float,
        world: float, extra: Dictionary = {}) -> void:
    if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") != "1":
        return
    var seen: String = identity+"|"+outcome
    if _diagnosed_plans.has(seen):
        return
    _diagnosed_plans[seen] = true
    var row: Dictionary = {"plan_id":identity,"outcome":outcome,
        "deadline_world":deadline_world,"world":world}
    row.merge(extra,true)
    print("SCORE_PLAN_QUEUE:",JSON.stringify(row))
