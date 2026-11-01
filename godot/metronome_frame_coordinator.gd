extends RefCounted
## Count-in, calibration and retry-click presentation use one transport clock.
## The backend grades MIDI; this class owns only audio/UI frame counters.
var settings_view
var practice_view
var clock
var transport_beat_at: Callable
var count_click: Callable
var raw_click: Callable
var calibration_tick_index := -999
var recovery_click_tick := -999
var retry_first_click_sent := false
var count_tick_index := -1
var last_audio_transport_id := -1

func _init(settings, practice, visual_clock, at_beat: Callable,
        on_count: Callable, on_raw: Callable) -> void:
    settings_view = settings
    practice_view = practice
    clock = visual_clock
    transport_beat_at = at_beat
    count_click = on_count
    raw_click = on_raw

func update(state: Dictionary, state_tick_ms: int,
        sampled_beat: float, now_ms: int) -> void:
    var calibration: Dictionary = state.get("midi_calibration", {})
    if bool(calibration.get("active",false)):
        recovery_click_tick = -999
        var beat := float(calibration.get("beat",-2.0)) + \
            maxf(0.0,float(now_ms-state_tick_ms)/1000.0) * \
            float(calibration.get("bpm",80.0))/60.0
        settings_view.animate_calibration_beat(
            beat,true,int(calibration.get("round_beats",12)),
            int(calibration.get("count_in",4)))
        var interval := maxi(1,int(calibration.get("round_beats",12)))
        var total := interval * maxi(1,int(calibration.get("rounds",3)))
        if beat >= 0.0 and beat < float(total):
            var tick := floori(beat + .00001)
            if tick != calibration_tick_index:
                var timely := calibration_tick_index != -999 or beat-float(tick) < .12
                calibration_tick_index = tick
                if timely:
                    var inside_round := posmod(tick,interval)
                    raw_click.call(inside_round == 0 or
                        inside_round == int(calibration.get("count_in",4)))
        return
    calibration_tick_index = -999
    if (settings_view.calibration_beat_pulse != null
            and settings_view.calibration_beat_pulse.visible):
        settings_view.animate_calibration_beat(-1.0,false)
    if (str(state.get("phase","")) in ["feedback","recovering"]
            and clock.retry_active and clock.retry_preparing(now_ms)
            and not bool(state.get("paused",false))):
        var count_beat: float = clock.retry_count_in_beat(now_ms)
        var bar := maxi(1,int(round(float(state.get("count_in_bar_beats",4)))))
        practice_view.stage.count_in.present(count_beat,bar,true,false)
        var tick := floori(count_beat + .00001)
        if tick != recovery_click_tick:
            if count_beat < .10 and count_beat >= -float(bar):
                raw_click.call(posmod(tick,bar) == 0)
                if tick == 0:
                    retry_first_click_sent = true
            recovery_click_tick = tick
        return
    if state.is_empty() or not bool(state.get("running",false)):
        recovery_click_tick = -999
        practice_view.stage.count_in.present(0.0,4,false,false)
        count_tick_index = -999
        return
    recovery_click_tick = -999
    var beat: float = (sampled_beat if is_finite(sampled_beat)
        else float(transport_beat_at.call(now_ms)))
    var paused: bool = bool(state.get("paused",false))
    var bar := maxi(1,int(round(float(state.get("count_in_bar_beats",4)))))
    practice_view.stage.count_in.present(beat,bar,true,paused)
    var attempt: int = int(state.get("transport_id",0))
    if attempt != last_audio_transport_id:
        count_tick_index = -999
        last_audio_transport_id = attempt
    if paused:
        count_tick_index = int(floor(beat + .00001))
        return
    var tick := int(floor(beat + .00001))
    if tick != count_tick_index:
        count_tick_index = tick
        if not (tick == 0 and retry_first_click_sent):
            count_click.call(posmod(tick,bar) == 0,beat)
        if tick >= 0:
            retry_first_click_sent = false
