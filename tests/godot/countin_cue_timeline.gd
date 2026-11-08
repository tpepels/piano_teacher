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
    var capped := Cues.new()
    var capped_ticks := 0
    beat = -9.0
    while beat < 0.0:
        if bool(capped.observe("play:capped",beat,4,2.0).get("count_in",false)):
            capped_ticks += 1
        beat += .02
    check(capped_ticks == 2,
        "a tempo-capped count-in counts only its own beats: " + str(capped_ticks))
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
