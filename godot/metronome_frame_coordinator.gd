extends RefCounted
## One authoritative musical clock drives every count-in audio/visual cue.
## Only calibration has its separate, intentional measurement epoch.
const CueTimeline := preload("res://countin_cue_timeline.gd")
## The backend grades MIDI; this class owns only audio/UI frame counters.
var settings_view
var practice_view
var clock
var transport_beat_at: Callable
var count_click: Callable
var raw_click: Callable
var calibration_tick_index := -999
var retry_first_click_sent := false
var _cues := CueTimeline.new()

func _dispatch_cue(token: String, beat: float, bar: int,
        use_raw_click: bool, count_in_beats: float = 0.0) -> void:
    var cue: Dictionary = _cues.observe(token,beat,bar,count_in_beats)
    if cue.is_empty():
        return
    var tick: int = int(cue["tick"])
    var accent: bool = bool(cue["accent"])
    if tick < 0 and practice_view.stage.count_in.speak_beat(
            int(cue["syllable"])):
        return
    if token.begins_with("running:") and tick == 0 and retry_first_click_sent:
        retry_first_click_sent = false
        return
    if use_raw_click:
        raw_click.call(accent)
        if token.begins_with("retry:") and tick == 0:
            retry_first_click_sent = true
    else:
        count_click.call(accent,beat)
        if tick >= 0:
            retry_first_click_sent = false

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
        _cues.reset()
        var bpm: float = maxf(1.0,float(calibration.get("bpm",80.0)))
        var beat: float
        # State replies can be delayed while the in-process worker prepares
        # notation. Project click/beat from the backend's actual monotonic
        # epoch, not from the midpoint of a potentially queued request.
        var start_backend_ms: float = float(calibration.get("start_at_ms",NAN))
        if is_finite(start_backend_ms) and bool(clock.has_backend_offset):
            beat = (float(now_ms)-float(clock.backend_offset_ms)-
                start_backend_ms)*bpm/60000.0
        else:
            # Before the first clock calibration, retain a bounded startup
            # preview; the backend will publish its epoch on the next poll.
            beat = float(calibration.get("beat",-2.0)) + \
                maxf(0.0,float(now_ms-state_tick_ms)/1000.0)*bpm/60.0
        var count_in := maxi(0,int(calibration.get("count_in",4)))
        var ticks_per_round := maxi(1,int(calibration.get("ticks",8)))
        var total := count_in + ticks_per_round * maxi(
            1,int(calibration.get("rounds",5)))
        settings_view.animate_calibration_beat(
            beat,true,ticks_per_round,count_in)
        if beat >= 0.0 and beat < float(total):
            var tick := floori(beat + .00001)
            if tick != calibration_tick_index:
                var timely := calibration_tick_index != -999 or beat-float(tick) < .12
                calibration_tick_index = tick
                if timely:
                    # Only the initial four beats are preparation. The click
                    # never pauses between the eight-tap measurement rounds.
                    var round_start := tick >= count_in and \
                        posmod(tick-count_in,ticks_per_round) == 0
                    raw_click.call(tick == 0 or round_start)
        return
    calibration_tick_index = -999
    if (settings_view.calibration_beat_pulse != null
            and settings_view.calibration_beat_pulse.visible):
        settings_view.animate_calibration_beat(-1.0,false)
    var preparing_retry: bool = (
        str(state.get("phase","")) in ["feedback","recovering"] and
        bool(clock.retry_active) and clock.retry_preparing(now_ms) and
        not bool(state.get("paused",false)))
    if preparing_retry:
        var retry_beat: float = clock.retry_count_in_beat(now_ms)
        var meter: int = maxi(1,int(round(float(state.get(
            "count_in_bar_beats",4)))))
        practice_view.stage.count_in.present(retry_beat,meter,true,false)
        var deadline_value: Variant = clock.get("retry_deadline_ms")
        var retry_key: String = str(roundi(float(deadline_value))) \
            if deadline_value != null else str(int(state.get("transport_id",0)))
        _dispatch_cue("retry:%d:%s" % [
            int(state.get("revision",-1)),retry_key],retry_beat,meter,true)
        return
    # The engine's one count-in bar; a longer lead before it stays silent.
    var count_in_beats: float = float(state.get("count_in_beats",0.0))
    var resume_value: Variant = state.get("resume_count_in_beat")
    var moving: bool = bool(state.get("running",false)) and \
        not bool(state.get("paused",false))
    if resume_value != null and moving:
        var bpm: float = maxf(1.0,float(state.get("bpm",60.0)))
        var resume_beat: float = float(resume_value) + \
            maxf(0.0,float(now_ms-state_tick_ms))*bpm/60000.0
        if resume_beat < 0.0:
            var resume_meter: int = maxi(1,int(round(float(
                state.get("count_in_bar_beats",4)))))
            practice_view.stage.count_in.present(
                resume_beat,resume_meter,true,false,count_in_beats)
            _dispatch_cue("resume:%d:%d" % [
                int(state.get("revision",-1)),
                int(state.get("transport_id",0))],
                resume_beat,resume_meter,true,count_in_beats)
            return
    if state.is_empty() or not bool(state.get("running",false)):
        practice_view.stage.count_in.present(0.0,4,false,false)
        _cues.reset()
        retry_first_click_sent = false
        return
    var beat: float = sampled_beat if is_finite(sampled_beat) else \
        float(transport_beat_at.call(now_ms))
    var paused: bool = bool(state.get("paused",false))
    var bar: int = maxi(1,int(round(float(state.get(
        "count_in_bar_beats",4)))))
    practice_view.stage.count_in.present(beat,bar,true,paused,count_in_beats)
    var token: String = "running:%d:%d" % [
        int(state.get("revision",-1)),int(state.get("transport_id",0))]
    if paused:
        _cues.hold(token,beat)
        return
    _dispatch_cue(token,beat,bar,false,count_in_beats)
