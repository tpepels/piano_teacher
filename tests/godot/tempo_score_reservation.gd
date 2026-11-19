extends SceneTree
## Regression: Free -> Tempo at a slower BPM must reserve new notation beyond
## the previous guided layer's source and rest BEFORE the backend starts.
## These world coordinates reproduce the 2026-11-18 Pathétique failure.
const Admission := preload("res://score_stream_admission.gd")
const Reservation := preload("res://score_transport_reservation.gd")
const Queue := preload("res://score_stream_queue.gd")

class FakeTimeline:
    extends RefCounted
    var pixels_per_beat := 288.0
    var duration_beats := 8.0

class FakeLayer:
    extends Control
    const PLAYHEAD_FRACTION := 0.33
    var timeline = FakeTimeline.new()
    var _stream_queue = Queue.new()
    func staff_gap() -> float:
        return 22.0

class IncomingLayer:
    extends FakeLayer
    var native_ready := true
    var bpm := 16.0
    var stream_world_beat := 0.0
    var practice_timeline := {"gap":{"duration_beats":2.0}}
    func retained_ready() -> bool:
        return true
    func _stream_right_beats() -> float:
        return size.x * (1.0 - PLAYHEAD_FRACTION) / timeline.pixels_per_beat
    func _stream_header_beats(_opening: float) -> float:
        return 0.82415522875817
    func _stream_source_windows(_opening: float) -> Array[Vector2]:
        return [Vector2(0.0,8.0)]

var failures := 0

func check(condition: bool, reason: String) -> void:
    if not condition:
        failures += 1
        push_error("TEMPO_SCORE_RESERVATION_FAIL: " + reason)

func _initialize() -> void:
    var outgoing := FakeLayer.new()
    outgoing.size = Vector2(1256.0,599.0)
    # Source's last pixel: popping-in floor 18.9122053; rest's last
    # pixel: popping-in floor 20.5566497. The failed backend deadline
    # was only 20.4215330, within that outgoing rest/header clearance.
    outgoing._stream_queue.online = [
        {"kind":"source","world_origin":18.703872,
         "source_floor":0.0,"source_ceiling":8.0,
         "clip_floor":0.0,"clip_ceiling":0.0},
        {"kind":"rest","world_origin":18.5358163398694,
         "source_floor":0.0,"source_ceiling":2.0}]
    var incoming := IncomingLayer.new()
    incoming.size = Vector2(1256.0,599.0)
    incoming._stream_queue.register_peer(outgoing)
    var world := 18.3153996732027
    var bpm := 16.0
    var bar := 2.0
    var count_in_with_latency := bar + 0.4*bpm/60.0
    var header: float = incoming._stream_header_beats(0.0)
    var playhead: float = incoming.size.x*incoming.PLAYHEAD_FRACTION
    var peer_rest: float = incoming._stream_queue.minimum_peer_opening(
        288.0,incoming.size.x,playhead,true,"rest")
    var rejected_deadline := 20.4215330065361
    check(rejected_deadline-header < peer_rest,
        "Original deadline must reproduce the overlapping rest")
    var planned: Dictionary = Reservation.plan(
        incoming,"start",world,0.0,count_in_with_latency)
    check(bool(planned.get("ok",false)),
        "Automatic Tempo should find a physical future reservation")
    if bool(planned.get("ok",false)):
        var onset: float = float(planned["start_world"])
        check(onset > rejected_deadline,
            "Reserved Tempo onset must clear the refused deadline")
        check(onset-header >= peer_rest,
            "Incoming header must clear the outgoing written rest")
        check(onset >= world+count_in_with_latency,
            "A whole count-in plus latency must precede the first note")
        check(not bool(planned.get("empty_strip",false)),
            "Live outgoing ink requires a wholly offscreen source")
        check(float(planned["first_pixel_x"]) > incoming.size.x,
            "The new passage must enter from beyond the viewport")
        check(Admission.lead_seconds(onset,world,bpm) >
            Admission.lead_seconds(bar,0.0,bpm),
            "Slower Tempo must wait for notation, not start after just two beats")
    print("TEMPO_SCORE_RESERVATION_FAILURES:",failures)
    outgoing.free()
    incoming.free()
    quit(0 if failures == 0 else 1)
