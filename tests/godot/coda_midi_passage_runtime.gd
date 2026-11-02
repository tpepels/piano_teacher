extends SceneTree

# A real Python-produced later-bar MIDI Coda score model is consumed by the
# same Godot semantic timeline / visual transport clock used by the UI.
# This headless contract excludes the native extension and physical keyboard.
var failures: Array[String] = []
func check(ok: bool, reason: String) -> void:
    if not ok:
        failures.append(reason)
        print("CODA_MIDI_GODOT_FAIL: ",reason)

func close() -> void:
    print("CODA_MIDI_GODOT_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    if args.size()!=1 or not FileAccess.file_exists(args[0]):
        check(false,"Expected actual Python-exported Coda MIDI score model")
        close()
        return
    var raw = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    if not raw is Dictionary:
        check(false,"Python-exported score model is invalid JSON")
        close()
        return
    check(raw.get("schema","")=="coda-midi-godot-semantics-v1",
          "Unknown Coda MIDI handoff schema")
    check(raw.get("source_format","")=="midi","Score did not come from MIDI")
    check(int(raw.get("source_first_bar",-1))==2,
          "A later source measure was not selected")
    check(float(raw.get("source_start_beat",-1.0))==3.0,
          "Source absolute beat origin missing")
    check(int(raw.get("source_ppq",0))>0,"Original source PPQ lost")
    var score: Dictionary=raw.get("score_model",{})
    var timeline=load("res://notation/shared/timeline.gd").new()
    check(timeline.load_model(score),"Actual transformed score model rejected: "+
          timeline.last_error)
    if not timeline.has_score():
        close()
        return
    check(timeline.revision==73,"Exact selected-stage revision lost")
    check(absf(timeline.duration_beats-6.0)<.000001,
          "The x2 later-bar exercise must last six local beats")
    check(timeline.measures.size()==2,"Source 3/4 written slowdown has two bars")
    check(score["notes"].size()==raw["source_ids"].size(),
          "A transformed note attack is missing or duplicated")
    for note in score["notes"]:
        check(raw["source_ids"].has(note["id"]),
              "Godot model lost original MIDI attack identity")
        var start: float=float(note["onset_beats"])
        var duration: float=float(note["duration_beats"])
        check(start>=0.0 and start+duration<=timeline.duration_beats+.000001,
              "Selected note is outside its local practice passage")
    check(timeline.set_density(100.0),"Cannot configure score density")
    var beat_clock=load("res://visual_transport_clock.gd").new()
    var bpm: float=float(raw["exercise_bpm"])
    var base_ms:=100000
    var state: Dictionary={"revision":73,"transport_id":1,
        "bpm":bpm,"running":true,"paused":false,
        "clock_beat":0.0,"play_from_beat":0.0}
    beat_clock.accept(state,base_ms,base_ms)
    for tick in range(1,41):
        var at: int=base_ms+tick*100
        var observed: float=beat_clock.score_beat(at)
        var expected: float=tick*.1*bpm/60.0
        check(absf(observed-expected)<.00001,
              "Practice clock stalled or jumped at frame %d" % tick)
        var x: float=timeline.screen_x(3.0,observed,420.0)
        check(absf(x-(420.0+(3.0-expected)*100.0))<.001,
              "Fixed playhead changed velocity through a rest/bar transition")
    state["paused"]=true
    state["running"]=false
    state["clock_beat"]=beat_clock.now(base_ms+4000)
    beat_clock.accept(state,base_ms+4000,base_ms+4000)
    var frozen: float=beat_clock.score_beat(base_ms+4000)
    check(absf(beat_clock.score_beat(base_ms+5600)-frozen)<.000001,
          "Pause failed to freeze later-bar Coda score")
    state["paused"]=false
    state["running"]=true
    beat_clock.accept(state,base_ms+5600,base_ms+5600)
    check(beat_clock.score_beat(base_ms+6600)>frozen,
          "Resume failed to advance at original BPM")
    state["transport_id"]=2
    state["clock_beat"]=-2.0
    beat_clock.accept(state,base_ms+6700,base_ms+6700)
    check(absf(beat_clock.score_beat(base_ms+6700)+2.0)<.000001,
          "Retry must begin its own count-in at selected passage zero")
    check(beat_clock.matches(state),"Retry uses stale transport or score revision")
    close()
