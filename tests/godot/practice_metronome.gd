extends SceneTree
# No Main, HTTP, visual count-in control or transport clock is constructed.
var failures := 0

func check(condition: bool, label: String) -> void:
    if not condition:
        failures += 1
        print("FAIL: ",label)

func _initialize() -> void:
    if not FileAccess.file_exists("res://practice_metronome.gd"):
        check(false,"independent practice metronome missing")
        finish()
        return
    call_deferred("run_contract")

func finish() -> void:
    print("PRACTICE_METRONOME_FAILURES:",failures)
    quit(0 if failures == 0 else 1)

func state(attempt: int = 7, paused: bool = false, mode: String = "practice") -> Dictionary:
    return {"running":true,"paused":paused,"transport_id":attempt,
        "count_in_bar_beats":3.0,"mode":mode,"phase":"count_in"}

func run_contract() -> void:
    var Metronome = load("res://practice_metronome.gd")
    var metronome: Node = Metronome.new()
    root.add_child(metronome)
    var pulses: Array = []
    metronome.pulse.connect(func(accent: bool, tick: int, phase: String):
        pulses.append([accent,tick,phase]))
    var visual: Dictionary = metronome.present({},9.0)
    check(visual == {"beat":0.0,"bar_beats":4,"running":false,"paused":false},"stopped visual inputs remain UI-owned plain data")
    check(metronome.count_tick_index == -999 and pulses.is_empty(),"stopped transport resets observed tick")
    visual = metronome.present(state(),-3.0,false)
    check(pulses == [[true,-3,"count_in"]],"negative count-in sounds even with practice metronome disabled")
    check(visual == {"beat":-3.0,"bar_beats":3,"running":true,"paused":false},"full source meter retained despite pickup duration")
    check(metronome.click_player.stream == metronome.click_high,"accent selects actual high stream")
    metronome.present(state(),-2.75,false)
    check(pulses.size() == 1,"same beat never retriggers")
    metronome.present(state(),-2.0,false)
    check(pulses[-1] == [false,-2,"count_in"] and metronome.click_player.stream == metronome.click_low,"negative modulo preserves source-meter weak beat")
    metronome.present(state(),-.2,false)
    check(pulses.size() == 3 and pulses[-1][1] == -1,"skipped ticks produce one current click without catch-up burst")
    metronome.present(state(),0.0,false)
    check(pulses.size() == 3 and metronome.count_tick_index == 0,"disabled preference suppresses nonnegative beat only")
    metronome.present(state(),.25,true)
    check(pulses.size() == 3,"enabling inside an already observed beat cannot replay it")
    metronome.present(state(),1.0,true)
    check(pulses[-1] == [false,1,"count_in"],"positive practice beat uses same scheduler")
    metronome.present(state(7,true),2.2,true)
    check(pulses.size() == 4 and metronome.count_tick_index == 2,"pause consumes frozen tick without sounding")
    metronome.present(state(),2.2,true)
    check(pulses.size() == 4,"resume on frozen tick remains silent")
    metronome.present(state(),3.0,true)
    check(pulses[-1] == [true,3,"count_in"],"resumed bar boundary accents")
    metronome.present(state(8,true),-1.2,true)
    check(pulses.size() == 5 and metronome.count_tick_index == -2 and metronome.last_audio_transport_id == 8,"new paused attempt resets identity then consumes its tick")
    metronome.present(state(8),-1.2,true)
    check(pulses.size() == 5,"paused new attempt resumes without duplicate click")
    metronome.present(state(9),-1.2,true)
    check(pulses.size() == 6 and pulses[-1][1] == -2,"new unpaused transport retriggers current beat")
    var stopped := {"running":false,"transport_id":9,"phase":"recovering","visual_scroll_beat":88.0}
    metronome.present(stopped,88.0,true)
    check(pulses.size() == 6 and metronome.count_tick_index == -999,"recovery scrolling cannot manufacture a running beat")
    metronome.present(state(9,false,"listen"),-1.2,true)
    check(pulses.size() == 7,"restart after stopped recovery resets even with same transport identity")
    var listen: Dictionary = state(9,false,"listen")
    listen["phase"] = "playing"
    metronome.present(listen,0.0,false)
    check(pulses.size() == 7,"Listen respects disabled nonnegative metronome preference")
    metronome.present(listen,1.0,true)
    check(pulses[-1] == [false,1,"playing"],"Listen retains original running-click behavior when enabled")
    var rounded: Dictionary = state(10)
    rounded["count_in_bar_beats"] = 2.5
    visual = metronome.present(rounded,3.0,true)
    check(visual["bar_beats"] == 3 and pulses[-1][0],"source meter rounds before accent calculation")
    rounded["transport_id"] = 11
    rounded["count_in_bar_beats"] = 0.0
    visual = metronome.present(rounded,2.0,true)
    check(visual["bar_beats"] == 1 and pulses[-1][0],"invalid short meter retains original minimum one")
    # Literal epsilon samples discriminate flooring from rounding and avoid
    # accidental early/late clicks immediately beside a beat boundary.
    metronome.present(state(12),.99998,true)
    check(pulses[-1][1] == 0,"beat before epsilon boundary remains previous tick")
    metronome.present(state(12),.999995,true)
    check(pulses[-1][1] == 1,"original 0.00001 beat epsilon retained")
    metronome.present(state(12),4.2,true)
    var count: int = pulses.size()
    metronome.present(state(12),2.2,true)
    check(pulses.size() == count+1 and pulses[-1][1] == 2,"running clock rewind emits only observed current tick")
    check(metronome.get_child_count() == 1 and metronome.click_player.get_parent() == metronome,"metronome owns actual player lifecycle")
    check(metronome.click_player.volume_db == -5.0,"original click output gain retained")
    var folder: String = OS.get_cmdline_user_args()[0]
    var report: Dictionary = {}
    for name in ["high","low"]:
        var audio: AudioStreamWAV = metronome.click_high if name == "high" else metronome.click_low
        FileAccess.open(folder.path_join(name+".pcm"),FileAccess.WRITE).store_buffer(audio.data)
        report[name] = {"format":audio.format,"mix_rate":audio.mix_rate,"stereo":audio.stereo,
            "volume_db":metronome.click_player.volume_db,"bytes":audio.data.size()}
    FileAccess.open(folder.path_join("audio.json"),FileAccess.WRITE).store_string(JSON.stringify(report))
    var player = weakref(metronome.click_player)
    metronome.free()
    check(player.get_ref() == null,"freeing owner frees the real audio player")
    finish()
