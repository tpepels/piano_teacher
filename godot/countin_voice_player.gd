extends Node
## One persistent audio owner for the entire practice session.
## This service is deliberately independent of score canvases, renderer
## revisions, lesson screens, and backend state polling.
const VOICE_NAMES := ["ichi", "ni", "san", "shi"]
const SETTINGS_PATH := "user://countin_voice.cfg"
const SEEK_SECONDS := 0.21
var spoken_enabled := true
var _voice_player: AudioStreamPlayer
var _streams: Array[AudioStream] = []
var _missing: Array[String] = []
var last_spoken_number := 0
var spoken_cues_total := 0

func _init() -> void:
    var saved := ConfigFile.new()
    if saved.load(SETTINGS_PATH) == OK:
        spoken_enabled = bool(saved.get_value("audio","spoken",true))

func _ready() -> void:
    _voice_player = AudioStreamPlayer.new()
    _voice_player.bus = "Master"
    _voice_player.volume_db = 0.0
    add_child(_voice_player)
    _load_all()

func _load_all() -> void:
    _streams.clear()
    _missing.clear()
    for name in VOICE_NAMES:
        var path: String = "res://assets/countin/%s.ogg" % name
        var sound: AudioStream = null
        # The resource provider supports exported packs; the explicit Ogg
        # decoder also supports an unimported developer checkout.
        if ResourceLoader.exists(path):
            var asset: Resource = ResourceLoader.load(path)
            if asset is AudioStream:
                sound = asset
        if sound == null and FileAccess.file_exists(path):
            sound = AudioStreamOggVorbis.load_from_file(path)
        if sound == null or sound.get_length() <= SEEK_SECONDS + 0.25:
            _missing.append(name)
            _streams.append(null)
        else:
            _streams.append(sound)
    if not _missing.is_empty():
        push_error("Bundled Japanese count-in audio missing or unreadable: " +
            ", ".join(PackedStringArray(_missing)) + " (reinstall or re-pull the tracked Ogg files)")

func available() -> bool:
    return _streams.size() == VOICE_NAMES.size() and _missing.is_empty()

func status() -> Dictionary:
    return {"enabled":spoken_enabled,"available":available(),
        "missing":_missing.duplicate(),
        "audio_bus":_voice_player.bus if _voice_player != null else "",
        "playing":_voice_player.playing if _voice_player != null else false,
        "last_word":last_spoken_number,"spoken_cues_total":spoken_cues_total,
        "master_muted":AudioServer.is_bus_mute(
            AudioServer.get_bus_index("Master"))}

func set_spoken_enabled(enabled: bool) -> void:
    spoken_enabled = enabled
    if not enabled and _voice_player != null:
        _voice_player.stop()
    var config := ConfigFile.new()
    config.set_value("audio","spoken",enabled)
    if config.save(SETTINGS_PATH) != OK:
        push_warning("Count-in audio setting could not be saved")

func speak_beat(number: int) -> bool:
    if not spoken_enabled or _voice_player == null or             number < 1 or number > _streams.size():
        return false
    var sound: AudioStream = _streams[number-1]
    if sound == null:
        # Never say that we played speech when we actually fell back to
        # the click. The missing-asset problem is visible in the terminal.
        return false
    _voice_player.stop()
    _voice_player.stream = sound
    _voice_player.play(SEEK_SECONDS)
    if not _voice_player.playing:
        push_warning("Count-in recording could not start: " +
            VOICE_NAMES[number-1])
        return false
    last_spoken_number = number
    spoken_cues_total += 1
    return true
