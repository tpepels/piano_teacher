extends RefCounted
## Owns the single generated click player, its prepared WAVs and
## playback witness. Count-in and MIDI calibration consume this service;
## it neither creates musical deadlines nor judges notes.
const RATE := 44100
const FRAMES := 4200

var player: AudioStreamPlayer
var high: AudioStreamWAV
var low: AudioStreamWAV
var click_cues_total := 0
var _settings
var _inbox
var _smoke := false

func bind_preferences(settings_session, inbox, smoke: bool) -> void:
    _settings = settings_session
    _inbox = inbox
    _smoke = smoke

func practice_click(accent: bool, sampled_beat: float) -> void:
    if not bool(_settings.preferences.get("metronome",true)) and sampled_beat >= 0.0:
        return
    if click(accent) and _smoke:
        print("PHASE0_CLICK:",str(_inbox.current.get("phase","")))

static func _make_click(frequency: float) -> AudioStreamWAV:
    var samples := PackedByteArray()
    samples.resize(FRAMES*2)
    for i in range(FRAMES):
        var t: float = float(i)/float(RATE)
        var envelope: float = pow(1.0-float(i)/float(FRAMES),4.0)
        var wave: float = sin(TAU*frequency*t)*envelope*0.46
        samples.encode_s16(i*2,int(wave*32767.0))
    var audio := AudioStreamWAV.new()
    audio.format = AudioStreamWAV.FORMAT_16_BITS
    audio.mix_rate = RATE
    audio.stereo = false
    audio.data = samples
    return audio

func install(root: Node) -> void:
    if player != null:
        return
    high = _make_click(1160.0)
    low = _make_click(770.0)
    player = AudioStreamPlayer.new()
    player.volume_db = -5.0
    root.add_child(player)

func click(accent: bool) -> bool:
    if player == null or not is_instance_valid(player):
        return false
    player.stream = high if accent else low
    player.play()
    if not player.playing:
        return false
    click_cues_total += 1
    return true


func shutdown() -> void:
    if is_instance_valid(player):
        player.stop()
        player.stream = null
    player = null
    high = null
    low = null
