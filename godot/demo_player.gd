extends Node
# Actual local PCM output follows the engine's Listen session and clock.
signal prepared(token: String, revision: int)
signal failed(message: String)
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

func _ready() -> void:
    player = AudioStreamPlayer.new()
    add_child(player)
    request = HTTPRequest.new()
    request.timeout = 120.0
    request.request_completed.connect(_downloaded)
    add_child(request)

func synchronize(state: Dictionary) -> void:
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
        if not started:
            player.play(maxf(0.0, float(state.get("clock_beat", 0.0))*60.0/float(state.get("bpm", 60))))
            started = true
        player.stream_paused = bool(state.get("paused", false))
    elif started:
        player.stop()
        started = false

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
