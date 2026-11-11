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
        use_raw_click: bool, count_in_beats: float = CueTimeline.WHOLE_BAR) -> void:
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

func _count_in(token: String, beat: float, bar_beats: float, meter: Variant,
        use_raw_click: bool, count_in_beats: float = CueTimeline.WHOLE_BAR,
        paused: bool = false) -> void:
    # One place turns a count-in reading into circles and cues, in the
    # meter's main pulse (M3); simple meters are unchanged.
    var units: Array = CueTimeline.in_pulses(beat,bar_beats,count_in_beats,
        CueTimeline.pulse_beats(meter))
    practice_view.stage.count_in.present(float(units[0]),int(units[1]),true,
        paused,float(units[2]))
    if paused:
        _cues.hold(token,float(units[0]))
        return
    _dispatch_cue(token,float(units[0]),int(units[1]),use_raw_click,float(units[2]))

func _announced_count_in(state: Dictionary, now_ms: int) -> bool:
    # An automatic continuation starts AT its announced graded deadline,
    # so its one count-in bar is spoken during the rest, in the bar right
    # before that deadline (score_queue_next: deadline and bar length). The
    # token is the deadline's, the same one the retry preparation clock
    # uses, so the two can never both speak the same bar.
    var plan: Variant = state.get("score_queue_next")
    if not plan is Dictionary or bool(state.get("running",false)) or \
            bool(state.get("paused",false)) or \
            not str(state.get("phase","")) in ["feedback","recovering","preview_gap"] or \
            not bool(clock.has_backend_offset):
        return false
    var bar_beats: float = float(plan.get("count_in_beats",0.0))
    if bar_beats <= 0.0:
        return false
    var deadline_ms: float = float(plan.get("deadline_at_ms",NAN)) + \
        float(clock.backend_offset_ms)
    # The announced take's own start tempo (a tempo-step repeat counts in
    # at its new BPM, not at the rest's).
    var bpm: float = maxf(1.0,float(plan.get("bpm",state.get("bpm",60.0))))
    var beat: float = (float(now_ms)-deadline_ms)/60000.0*bpm
    if not is_finite(beat) or not CueTimeline.counting(beat,1,bar_beats):
        return false
    _count_in("retry:%d:%s" % [int(state.get("revision",-1)),
        str(roundi(deadline_ms))],beat,bar_beats,
        plan.get("count_in_meter",state.get("count_in_meter")),true,bar_beats)
    return true

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
    # A rest's count-in belongs to the take the engine ANNOUNCED for it
    # (score_queue_next). An unannounced repeat counts in once it starts.
    var preparing_retry: bool = (
        str(state.get("phase","")) in ["feedback","recovering"] and
        state.get("score_queue_next") is Dictionary and
        bool(clock.retry_active) and clock.retry_preparing(now_ms) and
        not bool(state.get("paused",false)))
    if preparing_retry:
        var retry_beat: float = clock.retry_count_in_beat(now_ms)
        var deadline_value: Variant = clock.get("retry_deadline_ms")
        var retry_key: String = str(roundi(float(deadline_value))) \
            if deadline_value != null else str(int(state.get("transport_id",0)))
        var plan_meter: Variant = state.get("score_queue_next",{}).get(
            "count_in_meter",state.get("count_in_meter"))
        _count_in("retry:%d:%s" % [int(state.get("revision",-1)),retry_key],
            retry_beat,float(state.get("count_in_bar_beats",4)),plan_meter,true)
        return
    if _announced_count_in(state,now_ms):
        return
    # The engine's one count-in bar; a longer lead before it stays silent.
    # A hand-built snapshot without the key counts one bar of the meter.
    var count_in_beats: float = float(state.get("count_in_beats",
        CueTimeline.WHOLE_BAR))
    var resume_value: Variant = state.get("resume_count_in_beat")
    var moving: bool = bool(state.get("running",false)) and \
        not bool(state.get("paused",false))
    if resume_value != null and moving:
        var bpm: float = maxf(1.0,float(state.get("bpm",60.0)))
        var resume_beat: float = float(resume_value) + \
            maxf(0.0,float(now_ms-state_tick_ms))*bpm/60000.0
        if resume_beat < 0.0:
            # A Resume that reuses the paused count-in keeps its original
            # first-beat deadline, so its countdown is the same musical axis
            # as the transport beat. Continue that epoch: a syllable already
            # heard before Pause is not spoken again (one cycle only).
            var transport_beat: float = sampled_beat if is_finite(sampled_beat) \
                else float(transport_beat_at.call(now_ms))
            var running_token: String = "running:%d:%d" % [
                int(state.get("revision",-1)),int(state.get("transport_id",0))]
            var pulse: float = CueTimeline.pulse_beats(state.get("count_in_meter"))
            var continued: bool = is_finite(transport_beat) and \
                absf(transport_beat-resume_beat) < .05 and \
                _cues.continues(running_token,resume_beat/pulse)
            var resume_token: String = running_token if continued else \
                "resume:%d:%d" % [int(state.get("revision",-1)),
                int(state.get("transport_id",0))]
            _count_in(resume_token,resume_beat,
                float(state.get("count_in_bar_beats",4)),
                state.get("count_in_meter"),true,count_in_beats)
            return
    if state.is_empty() or not bool(state.get("running",false)):
        practice_view.stage.count_in.present(0.0,4,false,false)
        _cues.reset()
        retry_first_click_sent = false
        return
    var beat: float = sampled_beat if is_finite(sampled_beat) else \
        float(transport_beat_at.call(now_ms))
    var paused: bool = bool(state.get("paused",false))
    var token: String = "running:%d:%d" % [
        int(state.get("revision",-1)),int(state.get("transport_id",0))]
    _count_in(token,beat,float(state.get("count_in_bar_beats",4)),
        state.get("count_in_meter"),false,count_in_beats,paused)
