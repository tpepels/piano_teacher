extends SceneTree
## Actual bundled audio, visual-to-service connection, and persistent
## playback across teardown/replacement of the countdown UI.
const CountIn := preload("res://game_countin.gd")
const VoicePlayer := preload("res://countin_voice_player.gd")
var failures := 0

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        push_error("COUNTIN_VOICE_FAILED: " + description)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var voice := VoicePlayer.new()
    root.add_child(voice)
    voice.set_spoken_enabled(true)
    var counter := CountIn.new()
    root.add_child(counter)
    counter.attach_voice_service(voice)
    check(voice.available() and voice._streams.size() == 4,
        "all four tracked voice assets decode in the persistent audio owner")
    check(bool(counter.voice_status().get("available",false)),
        "visual countdown knows whether actual speech is available")
    for index in range(4):
        var filename: String = VoicePlayer.VOICE_NAMES[index]
        var path: String = "res://assets/countin/%s.ogg" % filename
        check(ResourceLoader.exists(path) or FileAccess.file_exists(path),
            "tracked recording exists: " + filename)
        var sound: AudioStream = voice._streams[index]
        check(sound != null, "Godot decodes the shipped recording: " + filename)
        if sound != null:
            check(sound.get_length() >= 0.5 and sound.get_length() <= 2.0,
                "plausible spoken word duration: " + filename)
        check(counter.speak_beat(index + 1),
            "real countdown starts word: " + filename)
        check(voice._voice_player.playing,
            "root-owned AudioStreamPlayer plays: " + filename)
    counter.set_spoken_enabled(false)
    check(not counter.speak_beat(1) and not voice._voice_player.playing,
        "voice-off is applied by the persistent audio owner")
    counter.set_spoken_enabled(true)
    check(counter.speak_beat(1), "voice can be enabled again")
    counter.free()
    check(voice.speak_beat(2),
        "removing countdown visuals does not destroy the audio player")
    var replacement := CountIn.new()
    root.add_child(replacement)
    replacement.attach_voice_service(voice)
    check(replacement.speak_beat(3) and voice._voice_player.playing,
        "new countdown visuals use the same persistent audio service")
    replacement.free()
    voice.free()
    print("COUNTIN_VOICE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
