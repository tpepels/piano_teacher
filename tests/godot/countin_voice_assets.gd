extends SceneTree
## End-to-end asset and AudioStreamPlayer regression. These actual shipped
## recordings must decode, have nonzero duration and start playback in Godot.
const CountIn := preload("res://game_countin.gd")
var failures := 0

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        push_error("COUNTIN_VOICE_FAILED: " + description)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var counter := CountIn.new()
    root.add_child(counter)
    counter.set_spoken_enabled(true)
    check(counter._voice_streams.size() == 4,
        "all four bundled sound assets are preloaded")
    for index in range(4):
        var filename: String = CountIn.VOICE_NAMES[index]
        var path: String = "res://assets/countin/%s.ogg" % filename
        check(FileAccess.file_exists(path), "recording shipped: " + filename)
        var sound: AudioStream = counter._voice_streams[index]
        check(sound != null, "Godot decodes recording: " + filename)
        if sound != null:
            check(sound.get_length() >= 0.5 and sound.get_length() <= 2.0,
                "plausible voice clip duration: " + filename)
        check(counter.speak_beat(index + 1),
            "voice scheduler starts recording: " + filename)
        check(counter._voice_player.playing,
            "AudioStreamPlayer is actually playing: " + filename)
    counter.set_spoken_enabled(false)
    check(not counter.speak_beat(1) and
        not counter._voice_player.playing,
        "voice-off setting prevents audio playback")
    counter.set_spoken_enabled(true)
    check(counter.speak_beat(1),
        "turning spoken count-in back on resumes audible playback")
    counter.free()
    print("COUNTIN_VOICE_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
