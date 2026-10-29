extends Node
## Owns generated click resources, the real audio player, and observed-tick
## scheduling. The caller supplies its authoritative projected transport beat;
## this owner has no timer, transport extrapolation, Main or visual-control refs.
## Add it to the scene tree before presenting a running transport.
signal pulse(accent: bool, tick: int, phase: String)

var click_player: AudioStreamPlayer
var click_high: AudioStreamWAV
var click_low: AudioStreamWAV
var count_tick_index := -1
var last_audio_transport_id := -1

func _init() -> void:
    click_high = make_count_click(1160.0)
    click_low = make_count_click(770.0)
    click_player = AudioStreamPlayer.new()
    click_player.volume_db = -5.0
    add_child(click_player)
    set_process(false)

static func make_count_click(frequency: float) -> AudioStreamWAV:
    # Exact existing Main PCM: mono signed little-endian 16-bit samples.
    const RATE := 44100
    const FRAMES := 4200
    var samples := PackedByteArray()
    samples.resize(FRAMES * 2)
    for i in range(FRAMES):
        var t: float = float(i) / float(RATE)
        var envelope: float = pow(1.0 - float(i) / float(FRAMES), 4.0)
        var wave: float = sin(TAU * frequency * t) * envelope * 0.46
        samples.encode_s16(i * 2, int(wave * 32767.0))
    var audio := AudioStreamWAV.new()
    audio.format = AudioStreamWAV.FORMAT_16_BITS
    audio.mix_rate = RATE
    audio.stereo = false
    audio.data = samples
    return audio

func present(state: Dictionary, transport_beat: float, metronome_enabled: bool = true) -> Dictionary:
    # Visual ownership stays with the caller; return only its existing inputs.
    if state.is_empty() or not bool(state.get("running",false)):
        count_tick_index = -999
        return {"beat":0.0,"bar_beats":4,"running":false,"paused":false}
    var paused: bool = bool(state.get("paused",false))
    var bar_beats: int = maxi(1,int(round(float(state.get("count_in_bar_beats",4)))))
    var visual := {"beat":transport_beat,"bar_beats":bar_beats,"running":true,"paused":paused}
    var attempt: int = int(state.get("transport_id",0))
    if attempt != last_audio_transport_id:
        count_tick_index = -999
        last_audio_transport_id = attempt
    if paused:
        count_tick_index = int(floor(transport_beat+0.00001))
        return visual
    var tick: int = int(floor(transport_beat+0.00001))
    if tick != count_tick_index:
        count_tick_index = tick
        # One sound for the current observed tick, even across skipped ticks,
        # repeated passages or a shortened pickup. Full source meter accents.
        _count_tick(posmod(tick,bar_beats) == 0,transport_beat,metronome_enabled,
            tick,str(state.get("phase","")))
    return visual

func _count_tick(accent: bool, beat: float, enabled: bool, tick: int, phase: String) -> void:
    if click_player == null:
        return
    if not enabled and beat >= 0.0:
        return
    click_player.stream = click_high if accent else click_low
    click_player.play()
    # Pulse observes an actual play request. Main can retain its smoke log;
    # the visual count-in can keep its continuously projected beat input.
    pulse.emit(accent,tick,phase)
