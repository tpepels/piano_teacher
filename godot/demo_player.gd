extends Node
# Actual local PCM output follows the engine's Listen session and clock.
signal prepared(token: String, revision: int)
signal failed(message: String)
const ListenSync := preload("res://listen_sync.gd")
var sync_monitor = ListenSync.new()
var last_sync_probe_ms := 0
var last_start_offset_s := 0.0
var player: AudioStreamPlayer
var request: HTTPRequest
var token := ""
var revision := -1
var audio_path := ""
var loaded := false
var acknowledged := false
var started := false
var downloading := false
var audio_error := false
# Independent local gain for the recorded piano; no MIDI output changes.
var listen_volume_db := 6.0

func _ready() -> void:
    player = AudioStreamPlayer.new()
    var config := ConfigFile.new()
    if config.load("user://audio.cfg") == OK:
        listen_volume_db = clampf(float(config.get_value("audio", "listen_volume_db", 6.0)), -12.0, 12.0)
    player.volume_db = listen_volume_db
    add_child(player)
    request = HTTPRequest.new()
    request.timeout = 120.0
    request.request_completed.connect(_downloaded)
    add_child(request)

func set_listen_volume_db(value: float) -> void:
    listen_volume_db = clampf(value, -12.0, 12.0)
    if player != null:
        player.volume_db = listen_volume_db
    var config := ConfigFile.new()
    config.set_value("audio", "listen_volume_db", listen_volume_db)
    config.save("user://audio.cfg")

func synchronize(state: Dictionary, visual_beat: float = NAN) -> void:
    if str(state.get("mode", "")) != "listen" or not state.get("demo") is Dictionary:
        clear()
        return
    var demo: Dictionary = state["demo"]
    var next_token: String = str(demo.get("token", ""))
    if next_token.is_empty():
        clear()
        return
    if next_token != token:
        clear()
        token = next_token
        revision = int(state.get("revision", -1))
        audio_path = "user://listen-%s.wav" % token
    if not loaded and not downloading and not audio_error and not str(demo.get("url", "")).is_empty():
        request.download_file = audio_path
        downloading = true
        var error: int = request.request("http://127.0.0.1:8765" + str(demo.get("url", "")))
        if error != OK:
            failed.emit("Cannot prepare Listen audio. Try Listen again.")
        return
    if not loaded:
        return
    if not bool(demo.get("ready", false)):
        # Repeat an acknowledgement if another control request was in flight.
        prepared.emit(token, revision)
        return
    if bool(state.get("running", false)):
        var bpm: float = maxf(1.0, float(state.get("bpm", 60)))
        var beat: float = visual_beat if is_finite(visual_beat) else float(
            state.get("clock_beat", 0.0))
        var target_s: float = maxf(0.0, beat * 60.0 / bpm)
        if not started:
            # Align the sound with the extrapolated visible score clock,
            # not the earlier snapshot timestamp returned by HTTP.
            last_start_offset_s = minf(target_s,
                maxf(0.0, player.stream.get_length() - .05))
            player.play(last_start_offset_s)
            started = true
            sync_monitor.reset_pending()
        player.stream_paused = bool(state.get("paused", false))
        if bool(state.get("paused", false)):
            sync_monitor.reset_pending()
        else:
            keep_synchronized(beat, bpm)
    elif started:
        player.stop()
        started = false
        sync_monitor.reset_pending()

# Sample the *audible* software play position, excluding the output-device
# buffer estimated by Godot. It is not a piano or speaker latency meter.
# Inspect at most five times per second and correct only persistent drift.
func keep_synchronized(visual_beat: float, bpm: float) -> void:
    if not loaded or not started or player == null or not player.playing \
            or player.stream_paused or not is_finite(visual_beat) or bpm <= .0:
        return
    var now_ms: int = Time.get_ticks_msec()
    if now_ms - last_sync_probe_ms < 200:
        return
    last_sync_probe_ms = now_ms
    var duration_s: float = player.stream.get_length()
    var target_s: float = maxf(0.0, visual_beat * 60.0 / bpm)
    var audible_s: float = maxf(0.0, player.get_playback_position() +
        AudioServer.get_time_since_last_mix() - AudioServer.get_output_latency())
    if sync_monitor.evaluate(target_s, audible_s, duration_s, now_ms):
        player.seek(clampf(target_s, 0.0, duration_s - .05))

func sync_report() -> Dictionary:
    return sync_monitor.report()


func _downloaded(result: int, code: int, _headers: PackedStringArray, _body: PackedByteArray) -> void:
    downloading = false
    if token.is_empty():
        return
    if result != HTTPRequest.RESULT_SUCCESS or code != 200:
        audio_error = true
        failed.emit("Listen audio could not load. Try Listen again.")
        return
    var stream := AudioStreamWAV.load_from_file(audio_path)
    if stream == null or stream.data.is_empty():
        audio_error = true
        failed.emit("Listen audio could not be decoded. Try Listen again.")
        return
    player.stream = stream
    loaded = true
    prepared.emit(token, revision)

func clear() -> void:
    if request != null:
        request.cancel_request()
    if player != null:
        player.stop()
        player.stream = null
    if not audio_path.is_empty() and audio_path.begins_with("user://"):
        DirAccess.remove_absolute(audio_path)
    token = ""
    audio_path = ""
    revision = -1
    loaded = false
    started = false
    downloading = false
    audio_error = false
    last_start_offset_s = 0.0
    last_sync_probe_ms = 0
    sync_monitor.reset_session()
