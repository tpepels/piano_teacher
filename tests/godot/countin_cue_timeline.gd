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
    print("COUNTIN_TIMELINE_FAILURES:",failures)
    quit(0 if failures==0 else 1)
