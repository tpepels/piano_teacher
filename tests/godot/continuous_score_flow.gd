extends SceneTree
## One endless score timeline. No MIDI hardware, rendering switch or
## source transport state may reverse it, pause it, or cause a re-anchor.
const Flow := preload("res://continuous_score_flow.gd")
const Tempo := preload("res://tempo_timeline.gd")

var failures := 0

func check(condition: bool, reason: String) -> void:
    if not condition:
        failures += 1
        print("CONTINUOUS_SCORE_FLOW_FAIL:",reason)

func _initialize() -> void:
    var flow := Flow.new()
    var start: float = flow.sample(1000,60.0)
    check(is_equal_approx(start,0.0),"Start is unshifted")
    var before: float = flow.sample(2000,60.0)
    check(is_equal_approx(before,1.0),"One second at 60 BPM advances one beat")
    # Paused, waiting, recovering, next step and retry are deliberately NOT
    # parameters of the score-flow clock. They affect only admitted ink.
    var pause: float = flow.sample(3000,60.0)
    var paused_again: float = flow.sample(4000,60.0)
    var retry: float = flow.sample(5000,60.0)
    check(pause < paused_again and paused_again < retry,
        "Pause and retry cannot stop or reverse the visual bar")
    var changed: float = flow.sample(6000,90.0)
    check(is_equal_approx(changed,5.0),
        "Tempo changes integrate the preceding interval at the old speed")
    check(is_equal_approx(flow.project(7000),6.5),
        "New speed applies only to future visual time")
    check(is_equal_approx(flow.sample(6500,30.0),5.75),
        "Current beat is preserved at tempo change")
    var at_7200: float = flow.sample(7200,30.0)
    var at_7500: float = flow.sample(7500,30.0)
    check(at_7500 > at_7200,"Time advances after tempo changes")
    check(flow.sample(7300,30.0) >= at_7500,
        "Out-of-order frame timestamps cannot rewind the visual bar")
    check(flow.project(8500) >= flow.sample(8500,30.0),
        "Projection is monotonic even during irregular polling")
    check(flow.project(15000) > flow.project(8500),
        "Indefinite idle period keeps scrolling forever")
    var map: Array = [
        {"start_beat":0.0,"end_beat":2.0,"bpm":48.0},
        {"start_beat":2.0,"end_beat":4.0,"bpm":96.0},
        {"start_beat":4.0,"end_beat":6.0,"bpm":60.0}]
    check(is_equal_approx(Tempo.bpm_at_beat(-1.0,40.0,map),40.0)
        and is_equal_approx(Tempo.bpm_at_beat(1.9,40.0,map),48.0)
        and is_equal_approx(Tempo.bpm_at_beat(2.0,40.0,map),96.0)
        and is_equal_approx(Tempo.bpm_at_beat(5.0,40.0,map),60.0),
        "Streaming velocity tracks authored variable-tempo sections exactly")
    var varying := Flow.new()
    varying.sample(1000,Tempo.bpm_at_beat(-2.0,40.0,map))
    varying.sample(2000,Tempo.bpm_at_beat(0.0,40.0,map))
    varying.sample(3000,Tempo.bpm_at_beat(2.0,40.0,map))
    check(is_equal_approx(varying.project(4000),40.0/60.0+48.0/60.0+96.0/60.0),
        "Tempo changes modify only forward velocity, never the world origin")
    print("CONTINUOUS_SCORE_FLOW_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
