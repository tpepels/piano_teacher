extends SceneTree
const Cues := preload("res://countin_cue_timeline.gd")
var failures := 0

func check(value: bool, message: String) -> void:
    if not value:
        failures += 1
        print("COUNTIN_TIMELINE_FAILED:",message)

func _initialize() -> void:
    var cues := Cues.new()
    var heard: Array[int] = []
    for beat in [-4.0,-3.99,-3.99,-3.0,-2.0,-1.0,-1.0,0.0]:
        var cue: Dictionary = cues.observe("play:1",beat,4)
        if cue.get("count_in",false):
            heard.append(int(cue["syllable"]))
    check(heard == [1,2,3,4],
        "count-in speaks ichi ni san shi exactly once per transport beat")
    check(cues.observe("play:1",-3.0,4).is_empty(),
        "a stale earlier poll cannot replay audio")
    cues.hold("play:1",1.0)
    check(cues.observe("play:1",1.0,4).is_empty(),
        "Pause and unchanged Resume cannot replay the frozen beat")
    # Pause just after a count-in boundary no frame had observed: the beat is
    # still owed to Resume (no skipped syllable), and spoken exactly once.
    var paused := Cues.new()
    check(int(paused.observe("play:p",-4.0,4).get("syllable",0)) == 1, "pause setup speaks 1")
    paused.hold("play:p",-2.98)
    check(paused.continues("play:p",-2.98), "a reused Resume continues the held epoch")
    check(int(paused.observe("play:p",-2.98,4).get("syllable",0)) == 2,
        "the unobserved boundary beat is spoken on Resume, not skipped")
    check(paused.observe("play:p",-2.97,4).is_empty(), "and never twice")
    check(not cues.observe("resume:1",-4.0,4).is_empty(),
        "a genuine Resume countdown is an independent preparation epoch")
    check(cues.observe("resume:1",-4.0,4).is_empty(),
        "duplicate snapshots of Resume cannot speak again")
    check(int(cues.observe("resume:1",-3.0,4).get("syllable",0))==2,
        "Resume uses the original musical beat for its voice syllable")
    check(int(cues.observe("retry:deadline:123",-4.0,4).get(
        "syllable",0))==1,
        "automatic retry preparation has its own unique backend deadline")
    check(cues.observe("retry:deadline:123",-4.0,4).is_empty(),
        "retry preparation polls are deduplicated")
    check(int(cues.observe("retry:deadline:456",-4.0,4).get(
        "syllable",0))==1,
        "next scheduled retry cannot inherit the previous retry's tick")
    cues.reset()
    check(int(cues.observe("play:1",-4.0,4).get("syllable",0))==1,
        "new practice session can restart a prior transport identity")
    check(cues.observe("",NAN,4).is_empty() and
        cues.observe("play:2",-2.0,0).is_empty(),
        "invalid clock samples never produce audible cues")
    # Owner decision 2026-11-08: a lead longer than the count-in is silent;
    # exactly one bar of the meter is counted, never several cycles.
    var long_lead := Cues.new()
    var counted: Array[int] = []
    var other := 0
    var beat := -13.0
    while beat < 0.0:
        var cue: Dictionary = long_lead.observe("play:long",beat,4,4.0)
        if bool(cue.get("count_in",false)):
            counted.append(int(cue["syllable"]))
        if not cue.is_empty() and beat < -4.0-.0001:
            other += 1
        beat += .02
    check(counted == [1,2,3,4] and other == 0,
        "a 13-beat lead emits exactly meter count-in ticks: " + str(counted))
    # The window is the engine's count_in_beats. 0 is a real count-in of
    # zero (a loop continuation): nothing is counted. Only the explicit
    # WHOLE_BAR sentinel means "one bar of the meter".
    var none := Cues.new()
    var none_ticks := 0
    beat = -6.0
    while beat < 0.0:
        if bool(none.observe("play:loop",beat,4,0.0).get("count_in",false)):
            none_ticks += 1
        beat += .02
    check(none_ticks == 0,
        "a loop continuation with count_in_beats 0 counts nothing: " + str(none_ticks))
    check(not Cues.counting(-.5,4,0.0) and Cues.counting(-.5,4,Cues.WHOLE_BAR) and
        Cues.counting(-3.9,4,Cues.WHOLE_BAR) and not Cues.counting(-4.1,4,Cues.WHOLE_BAR),
        "WHOLE_BAR counts exactly one bar; 0 counts none")
    var retry := Cues.new()
    var retry_ticks := 0
    beat = -11.0
    while beat < 0.0:
        if bool(retry.observe("retry:deadline:789",beat,3).get("count_in",false)):
            retry_ticks += 1
        beat += .02
    check(retry_ticks == 3, "a long Retry preparation counts one 3/4 bar")
    print("COUNTIN_TIMELINE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
