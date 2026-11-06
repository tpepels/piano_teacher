extends SceneTree
## Actual bundled audio, visual-to-service connection, and persistent
## playback across teardown/replacement of the countdown UI.
const CountIn := preload("res://game_countin.gd")
const VoicePlayer := preload("res://countin_voice_player.gd")
const Coordinator := preload("res://metronome_frame_coordinator.gd")

class FakeSettings:
    extends RefCounted
    var calibration_beat_pulse = null
    func animate_calibration_beat(_beat: float,_active: bool) -> void:
        pass

class FakeStage:
    extends RefCounted
    var count_in

class FakePractice:
    extends RefCounted
    var stage := FakeStage.new()

class FakeClock:
    extends RefCounted
    var retry_active := false
    var retry_deadline_ms := 0.0
    func retry_preparing(_ms: int) -> bool:
        return false
    func retry_count_in_beat(_ms: int) -> float:
        return 0.0
var failures := 0

func check(condition: bool, description: String) -> void:
    if not condition:
        failures += 1
        push_error("COUNTIN_VOICE_FAILED: " + description)

func _at_beat(_ms: int) -> float:
    return -4.0

func _click(_accent: bool, _beat: float = NAN) -> void:
    pass

func _raw_click(_accent: bool) -> void:
    pass

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
    # Exercise the ACTUAL frame-coordinator -> visual -> persistent speech
    # route. The cue must be audible exactly once per backend beat, even if
    # the application polls the same state multiple times.
    var practice := FakePractice.new()
    practice.stage.count_in = replacement
    var audio_frame := Coordinator.new(FakeSettings.new(),practice,
        FakeClock.new(),Callable(self,"_at_beat"),
        Callable(self,"_click"),Callable(self,"_raw_click"))
    var running := {"running":true,"paused":false,"revision":1,
        "phase":"count_in","transport_id":31,"count_in_bar_beats":4}
    var before: int = voice.spoken_cues_total
    audio_frame.update(running,1000,-4.0,1000)
    audio_frame.update(running,1000,-4.0,1020)
    check(voice.spoken_cues_total==before+1 and
        voice.last_spoken_number==1,
        "repeated polls speak Ichi exactly once through the real player")
    audio_frame.update(running,1000,-3.0,1030)
    check(voice.spoken_cues_total==before+2 and
        voice.last_spoken_number==2 and replacement.current==1,
        "visual beat and audible Ni share one sampled musical clock")
    var paused := running.duplicate(true)
    paused["paused"] = true
    audio_frame.update(paused,1000,-2.0,1040)
    check(voice.spoken_cues_total==before+2,
        "Pause cannot emit a new spoken beat")
    var resumed := running.duplicate(true)
    resumed["resume_count_in_beat"] = -4.0
    audio_frame.update(resumed,1050,NAN,1050)
    audio_frame.update(resumed,1050,NAN,1050)
    check(voice.spoken_cues_total==before+3 and
        voice.last_spoken_number==1,
        "Resume creates one new voiced preparation epoch, never duplicates")
    replacement.free()
    voice.free()
    print("COUNTIN_VOICE_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
