extends RefCounted
const StreamGeometry := preload("res://notation/native/stream_geometry.gd")
## Owns recovery-plan identity, deduplication and read-only physical planning.
## It never withdraws or appends a queue strip; the stream owner commits the
## exact prepared suffix and compensates a failed transaction.
const Admission := preload("res://score_stream_admission.gd")
var _owners: Dictionary = {}
var _openings: Dictionary = {}

func reset() -> void:
    _owners.clear()
    _openings.clear()

func record(identity: String, owner: int, opening: float,
        world: float, empty: bool) -> void:
    _owners[identity] = owner
    _openings[identity] = opening
    diagnose(identity,"admitted",opening,world,
        {"owner":owner,"on_empty_strip":empty})

var _diagnosed_plans: Dictionary = {}

## Diagnostic deduplication belongs to the same plan ledger that records
## admissions, not to NativeScoreView's paint/repaint lifecycle.
func diagnose(identity: String, outcome: String, deadline_world: float,
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

## Use the same physical clearance for measurement and exact admission.
## An empty strip can receive future ink close to the playhead; an occupied
## strip still requires the ordinary offscreen append boundary.
static func free_slot(queue, facts: StreamGeometry, remaining: Array,
        right: float, header: float) -> Dictionary:
    var density: float = maxf(1.0,facts.density)
    var lead: float = maxf(.25,header+Admission.OFFSCREEN_MARGIN_BEATS)
    var close: float = Admission.empty_strip_start(remaining,facts.world,
        lead,header,queue.minimum_peer_opening(density,facts.width,facts.playhead,true,"source"),
        density,facts.gap,facts.duration,
        queue.minimum_peer_opening(density,facts.width,facts.playhead,true,"rest"))
    if is_finite(close):
        return {"start":close,"empty":true}
    var far: float = Admission.earliest_opening(remaining,facts.world,right,
        header,density,facts.gap,facts.duration)
    far = maxf(far,queue.minimum_peer_opening(density,facts.width,facts.playhead)+header)
    return {"start":far,"empty":false}

func prepare(queue, facts: StreamGeometry, source_opening: float,
        graded_deadline_world: float, right: float, header: float,
        plan_id: String, allow_count_in: bool, count_in_beats: float,
        deadline_at_or_after: bool, untimed: bool) -> Dictionary:
    # Recovery decisions arrive from the engine with an absolute graded
    # deadline. Reuse a compatible offline-planned future if possible;
    # otherwise withdraw the maximal safe suffix, then APPEND new source
    # notation at that exact deadline. A late deadline must never cause
    # an onscreen pop or independent renderer camera adjustment.
    if not facts.ready or \
            not is_finite(graded_deadline_world) or \
            source_opening < 0.0 or source_opening >= facts.duration:
        return {}
    var identity: String = plan_id if not plan_id.is_empty() else \
        "%.6f:%.6f" % [source_opening,graded_deadline_world]
    if _owners.has(identity):
        # The plan identity names its source opening, graded take and exact
        # backend deadline: the owner admitted for it IS that take's ink.
        # A tail withdrawal can invalidate it; then admit it again.
        if queue.has_take(int(_owners[identity])):
            return {"already_admitted":true}
        _owners.erase(identity)
        _openings.erase(identity)
    # An already elapsed plan may no longer be reinserted: it would
    # introduce notes behind the real playhead.
    if graded_deadline_world <= facts.world:
        diagnose(identity,"elapsed",graded_deadline_world,facts.world)
        return {}
    # PREPARE: check the actual exact deadline against the queue AFTER
    # maximal safe tail withdrawal, without mutating the live queue.
    # Previously this check ran AFTER trim(facts,), so a late or
    # impossible engine deadline deleted valid pending music first.
    var preview: Dictionary = queue.preview_tail_withdrawal(
        facts.world,facts.density,facts.gap,
        facts.duration,facts.width,facts.playhead)
    var remaining: Array = preview["remaining"]
    var checked: float = Admission.position(remaining,
        facts.world,right,
        header,
        graded_deadline_world,0.0,facts.density,
        facts.gap,facts.duration)
    var on_empty := false
    if untimed:
        # Never shift an authorized Free opening: the backend holds there.
        # Use the same empty-strip decision as the reported travel geometry.
        var slot: Dictionary = free_slot(queue,facts,remaining,right,header)
        checked = graded_deadline_world if graded_deadline_world >= float(slot["start"])-.0001 else NAN
        on_empty = bool(slot["empty"]) and is_finite(checked)
    elif not is_finite(checked) and allow_count_in:
        # The initial command or an already announced backend continuation
        # may use the empty-staff slot; source/rest/peer physical clearance
        # remains mandatory. Practice plans have been announced BEFORE this
        # snapshot, so a partial count-in has already elapsed. The first
        # note still has a guaranteed future reading lead and retains its
        # exact original grading deadline.
        if deadline_at_or_after:
            var density: float = maxf(1.0,facts.density)
            var playhead: float = facts.playhead
            checked = Admission.announced_empty_strip_start(
                remaining,facts.world,count_in_beats,
                header,graded_deadline_world,
                queue.minimum_peer_opening(
                    density,facts.width,playhead,true,"source"),
                density,facts.gap,facts.duration,
                queue.minimum_peer_opening(
                    density,facts.width,playhead,true,"rest"))
            on_empty = is_finite(checked)
        else:
            # Listen/Perform/Learn use one initial full count-in slot, with
            # the original tight timestamp-to-slot equality requirement.
            var onset: float = Admission.empty_strip_start(
                remaining,facts.world,count_in_beats,header,
                queue.minimum_peer_opening(facts.density,facts.width,
                    facts.playhead,true,"source"),
                facts.density,facts.gap,facts.duration,
                queue.minimum_peer_opening(facts.density,facts.width,
                    facts.playhead,true,"rest"))
            if is_finite(onset) and absf(onset-graded_deadline_world) <= \
                    Admission.EMPTY_STRIP_DEADLINE_EPSILON_BEATS:
                checked = graded_deadline_world
                on_empty = true
    if not is_finite(checked):
        var blocking: Array = []
        for item in remaining:
            var bounds: Vector2 = Admission.clip_bounds(item,
                facts.density,facts.gap,facts.duration)
            var finish: float = float(item["world_origin"])+bounds.y/ \
                maxf(1.0,facts.density)
            if finish > facts.world-1.0:
                blocking.append([str(item.get("kind","source")),
                    snappedf(finish,.001)])
        var detail: Dictionary = {"count_in":count_in_beats,
            "header":header,
            "deadline_lead":graded_deadline_world-facts.world,
            "ink_ends":blocking}
        var diagnostic_density: float = maxf(1.0,facts.density)
        var diagnostic_playhead: float = facts.playhead
        var peer_source: float = queue.minimum_peer_opening(
            diagnostic_density,facts.width,diagnostic_playhead,true,"source")
        var peer_rest: float = queue.minimum_peer_opening(
            diagnostic_density,facts.width,diagnostic_playhead,true,"rest")
        if is_finite(peer_source):
            detail["peer_source_floor"] = peer_source
        if is_finite(peer_rest):
            detail["peer_rest_floor"] = peer_rest
        diagnose(identity,"refused_inside_or_overlap",
            graded_deadline_world,facts.world,detail)
        return {}
    var incoming_left: float = checked - header
    if not queue.clears_prior_layers(incoming_left,
            facts.density,facts.width,facts.playhead,on_empty):
        diagnose(identity,"refused_prior_layer",graded_deadline_world,facts.world)
        return {}
    # COMMIT: the exact same exposure snapshot and world coordinate must
    # still hold. No yield/poll/other input runs between preview and commit.
    var saved_suffix: Array = []
    for index in range(remaining.size(),queue.online.size()):
        saved_suffix.append(queue.online[index].duplicate())
    return {"identity":identity,"start":checked,"empty":on_empty,
        "remaining_count":remaining.size(),"saved_suffix":saved_suffix}

func opening(identity: String) -> float:
    return float(_openings.get(identity,NAN))
