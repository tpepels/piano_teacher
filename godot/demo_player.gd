extends Node
# Actual local PCM output follows the engine's Listen session and clock.
signal prepared(token: String, revision: int)
signal failed(message: String)
const ListenSync := preload("res://listen_sync.gd")
const TempoTimeline := preload("res://tempo_timeline.gd")
var sync_monitor = ListenSync.new()
var last_sync_probe_ms := 0
var last_start_offset_s := 0.0
var player: AudioStreamPlayer
var request
var command_bus: Node
var token := ""
var revision := -1
var audio_path := ""
var loaded := false
var acknowledged := false
var started := false
var downloading := false
var audio_error := false

# A Listen response may contain megabytes of PCM. Decode an exclusively
# owned resource off the scene thread; only publish the matching token
# after the task finishes. Never wait for a running decode during navigation.
class DecodeJob extends RefCounted:
    var body: PackedByteArray
    var generation: int
    var stream: AudioStreamWAV
    func run() -> void:
        stream = AudioStreamWAV.load_from_buffer(body)
        body = PackedByteArray()
        if stream != null and stream.data.is_empty():
            stream = null

var _decode_generation := 0
var _decode_id := -1
var _decode_job: DecodeJob
var _queued_decode: DecodeJob
# Independent local gain for the recorded piano; no MIDI output changes.
var listen_volume_db := 6.0

func configure(bus: Node) -> void:
    command_bus = bus

func _ready() -> void:
    player = AudioStreamPlayer.new()
    var config := ConfigFile.new()
    if config.load("user://audio.cfg") == OK:
        listen_volume_db = clampf(float(config.get_value("audio", "listen_volume_db", 6.0)), -12.0, 12.0)
    player.volume_db = listen_volume_db
    add_child(player)
    request = preload("res://inprocess_request.gd").new()
    request.configure(command_bus)
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
    if not loaded and not downloading and not audio_error and bool(demo.get("audio_available", false)):
        downloading = true
        var error: int = request.request("listen.audio", {"token": token})
        if error != OK:
            failed.emit("Cannot prepare Listen audio. Try Listen again.")
        return
    if not loaded:
        return
    if not bool(demo.get("ready", false)):
        # Repeat an acknowledgement if another control request was in flight.
        prepared.emit(token, revision)
        return
    _sync_playback(state,visual_beat)

func _sync_playback(state: Dictionary, visual_beat: float) -> void:
    if bool(state.get("running", false)):
        var timeline: Variant = state.get("playback_timeline")
        if timeline is Dictionary and not bool(timeline.get("presentation_confirmed",true)):
            if started:
                player.stream_paused = true
            return
        var bpm: float = maxf(1.0, float(state.get("bpm", 60)))
        var beat: float = visual_beat if is_finite(visual_beat) else float(
            state.get("clock_beat", 0.0))
        # The lead-in moves the sheet and the playhead, but the WAV starts
        # on the downbeat. Never seek ahead during first start: doing that
        # irreversibly cuts the first piano attack after processing/audio latency.
        if not started and beat < 0.0:
            return
        if not started:
            last_start_offset_s = 0.0
            player.play(0.0)
            started = true
            sync_monitor.reset_pending()
            last_sync_probe_ms = Time.get_ticks_msec()
        player.stream_paused = bool(state.get("paused", false))
        if bool(state.get("paused", false)):
            sync_monitor.reset_pending()
        else:
            keep_synchronized(beat, bpm, state.get("tempo_segments", []))
    elif started:
        player.stop()
        started = false
        sync_monitor.reset_pending()

# Sample the *audible* software play position, excluding the output-device
# buffer estimated by Godot. It is not a piano or speaker latency meter.
# Inspect at most five times per second and correct only persistent drift.
func keep_synchronized(visual_beat: float, bpm: float, segments: Array = []) -> void:
    if not loaded or not started or player == null or not player.playing \
            or player.stream_paused or not is_finite(visual_beat) or bpm <= .0:
        return
    var now_ms: int = Time.get_ticks_msec()
    if now_ms - last_sync_probe_ms < 200:
        return
    last_sync_probe_ms = now_ms
    var duration_s: float = player.stream.get_length()
    var target_s: float = maxf(0.0, TempoTimeline.seconds_at_beat(visual_beat, bpm, segments))
    var audible_s: float = maxf(0.0, player.get_playback_position() +
        AudioServer.get_time_since_last_mix() - AudioServer.get_output_latency())
    if sync_monitor.evaluate(target_s, audible_s, duration_s, now_ms):
        player.seek(clampf(target_s, 0.0, duration_s - .05))

func sync_report() -> Dictionary:
    return sync_monitor.report()


func _downloaded(code: int, body: PackedByteArray) -> void:
    downloading = false
    if token.is_empty():
        return
    if code != 0 or body.is_empty():
        audio_error = true
        failed.emit("Listen audio could not load. Try Listen again.")
        return
    var job := DecodeJob.new()
    job.generation = _decode_generation
    job.body = body
    downloading = true
    _queued_decode = job
    _start_decode()

func _start_decode() -> void:
    if _decode_id >= 0 or _queued_decode == null:
        return
    _decode_job = _queued_decode
    _queued_decode = null
    _decode_id = WorkerThreadPool.add_task(_decode_job.run,false,"Decode Listen PCM")
    if _decode_id < 0:
        _decode_job = null
        downloading = false
        audio_error = true
        failed.emit("Cannot start Listen audio decoding.")

func _process(_delta: float) -> void:
    if _decode_id >= 0 and WorkerThreadPool.is_task_completed(_decode_id):
        var joined: Error = WorkerThreadPool.wait_for_task_completion(_decode_id)
        var job: DecodeJob = _decode_job
        _decode_job = null
        _decode_id = -1
        if job.generation == _decode_generation and not token.is_empty():
            var publish_started: int = Time.get_ticks_usec()
            downloading = false
            if joined != OK or job.stream == null:
                audio_error = true
                failed.emit("Listen audio could not be decoded. Try Listen again.")
            else:
                player.stream = job.stream
                loaded = true
                prepared.emit(token,revision)
            if OS.get_environment("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
                print("LISTEN_PCM_PUBLISH:",JSON.stringify({"at_ms":float(publish_started)*.001,
                    "elapsed_ms":float(Time.get_ticks_usec()-publish_started)*.001,"revision":revision}))
    _start_decode()

func clear() -> void:
    if token.is_empty() and not downloading and not loaded and not started and not audio_error:
        return
    _decode_generation += 1
    _queued_decode = null
    if is_instance_valid(request):
        request.cancel_request()
    if is_instance_valid(player):
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


func _exit_tree() -> void:
    clear()
    if _decode_id >= 0:
        WorkerThreadPool.wait_for_task_completion(_decode_id)
        _decode_id = -1
    _decode_job = null
