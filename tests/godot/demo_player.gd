extends SceneTree
var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("DEMO_FAIL:", message)
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var demo = load("res://demo_player.gd").new()
    root.add_child(demo)
    var path: String = OS.get_cmdline_user_args()[0]
    demo.token = "lesson-a"
    demo.revision = 8
    demo.audio_path = path
    demo._downloaded(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), PackedByteArray())
    check(demo.player.stream is AudioStreamWAV, "Downloads load a real PCM stream")
    check(demo.player.stream.data.size() > 2000, "Stream carries rendered samples")
    check(not demo.player.playing, "Audio waits for backend ready acknowledgement")
    var state: Dictionary = {"mode":"listen", "revision":8, "running":true, "paused":false, "clock_beat":0.0, "bpm":80, "demo":{"token":"lesson-a", "ready":true}}
    demo.synchronize(state)
    check(demo.player.playing, "Running Listen starts actual audio output")
    state["paused"] = true
    demo.synchronize(state)
    check(demo.player.stream_paused, "Pause freezes the audio stream")
    state["paused"] = false
    demo.synchronize(state)
    check(not demo.player.stream_paused, "Resume releases the same stream")
    state["mode"] = "practice"
    demo.synchronize(state)
    check(not demo.player.playing, "Returning to student input stops the demo")
    check(demo.token.is_empty(), "Obsolete Listen identity is discarded")
    print("DEMO_PLAYER_FAILURES:", failures.size())
    quit(1 if failures.size() else 0)
