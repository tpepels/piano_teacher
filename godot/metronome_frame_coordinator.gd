extends RefCounted
## One authoritative musical clock drives every count-in audio/visual cue.
## Only calibration has its separate, intentional measurement epoch.
const CueTimeline := preload("res://countin_cue_timeline.gd")
const TempoTimeline := preload("res://tempo_timeline.gd")
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
# The count-in of a Play/Retry/Resume Godot itself reserved (round 4, M4):
# its first-beat deadline is known locally when the user acts, so every
# syllable is spoken on its beat even before the engine's state, one
# snapshot latency later, reports the take. While it runs it owns every
# count-in syllable; no other source (running transport, Resume countdown,
# Retry preparation) speaks a count-in beat until one beat after its
# deadline, so a hand-off can never re-speak a syllable (C1/I1).
var _reserved: Dictionary = {}
var _count_in_owned_until_ms := -INF
var _count_in_owned_transport := -1
var _frame_now_ms := 0
# The engine's deadline for the reserved take may differ from Godot's by
# at most this much before the countdown is re-based onto it (logged).
const RESERVED_AGREEMENT_MS := 40.0

func reserve_count_in(deadline_ms: float, bpm: float, bar_beats: float,
        meter: Variant, count_in_beats: float, action: String = "start",
        authorized_plan: Dictionary = {}, take_id: String = "") -> void:
    if not is_finite(deadline_ms) or not is_finite(bpm) or bpm <= 0.0 or \
            not is_finite(count_in_beats) or count_in_beats <= 0.0:
        _reserved = {}
        return
    var plan: Dictionary = authorized_plan.duplicate(true)
    if not plan.is_empty():
        if (absf(float(plan.get("beats",-1.0))-count_in_beats) > 0.0001
                or absf(float(plan.get("bpm",-1.0))-bpm) > 0.0001
                or plan.get("meter",[]) != meter):
            push_error("COUNT_IN_PLAN: renderer and coordinator disagree")
            _reserved.clear()
            return
    _reserved = {"deadline_ms":deadline_ms,"bpm":bpm,"bar":bar_beats,
        "meter":meter,"count_in":count_in_beats,"action":action,
        "plan":plan,"token":"authorized:"+take_id if not take_id.is_empty()
            else "countin:%d" % roundi(deadline_ms),"acked_ms":NAN}

func cancel_reserved_count_in() -> void:
    _reserved = {}
    _count_in_owned_until_ms = -INF

func acknowledge_reserved_count_in(now_ms: int) -> void:
    # The engine accepted the command: the first snapshot from now on must
    # show the take (or Retry) for this deadline, or nothing is spoken.
    if not _reserved.is_empty():
        _reserved["acked_ms"] = float(now_ms)

static func engine_count_in_deadline_ms(state: Dictionary, action: String,
        offset_ms: float) -> float:
    # The coordinator's authorized segment is the exact epoch for Start,
    # Restart, automatic continuation and Resume. Never infer it from a
    # speculative score plan or a UI-local timer.
    var timeline: Variant = state.get("playback_timeline")
    if timeline is Dictionary and bool(state.get("running",false)) and \
            not bool(state.get("paused",false)):
        var agreed: float = float(timeline.get("deadline_ms",NAN))
        if is_finite(agreed) and agreed > 0.0:
            return agreed+offset_ms
    if not bool(state.get("running",false)) or bool(state.get("paused",false)):
        return NAN
    var bpm: float = maxf(1.0,float(state.get("bpm",60.0)))
    var countdown: Variant = state.get("resume_count_in_beat")
    if action == "resume" and countdown != null and float(countdown) < 0.0 and \
            state.has("clock_sampled_at_ms"):
        return float(state["clock_sampled_at_ms"])+offset_ms- \
            TempoTimeline.seconds_from_beats(float(countdown),bpm)*1000.0
    return float(state.get("visual_run_at_ms",NAN))+offset_ms


func _reserved_count_in(state: Dictionary, state_tick_ms: int,
        now_ms: int) -> bool:
    if _reserved.is_empty():
        return false
    if bool(state.get("paused",false)):
        # The existing countdown is frozen; no syllables may be spoken
        # while physical MIDI grading is paused. Resume retains the same
        # take identity so already-spoken syllables cannot replay.
        var stopped: Dictionary = _reserved
        var sample: float = TempoTimeline.beats_from_milliseconds(
            float(now_ms)-float(stopped["deadline_ms"]),
            float(stopped["bpm"]))
        var token: String = str(stopped["token"])
        var pulse: float = CueTimeline.pulse_beats(stopped["meter"])
        _cues.hold(token,sample/pulse)
        practice_view.stage.count_in.present(0.0,4,false,true)
        _reserved.clear()
        return true
    var acked: float = float(_reserved["acked_ms"])
    # Only a snapshot the engine SAMPLED after it accepted the command can
    # confirm it (a poll already in flight may show the state before it).
    var sampled_ms: float = float(state.get("clock_sampled_at_ms",-INF))+ \
        float(clock.backend_offset_ms) if bool(clock.has_backend_offset) else -INF
    if is_finite(acked) and sampled_ms >= acked:
        # One check, on the first snapshot after the engine accepted it.
        _reserved["acked_ms"] = NAN
        var engine: float = engine_count_in_deadline_ms(state,
            str(_reserved["action"]),float(clock.backend_offset_ms))
        if not is_finite(engine):
            # No take started for this deadline (an error, reload_score,
            # a refused start): it must not be counted in.
            _reserved = {}
            return false
        var reserved: float = float(_reserved["deadline_ms"])
        if absf(engine-reserved) > RESERVED_AGREEMENT_MS:
            push_error("COUNT_IN_DEADLINE_DISAGREEMENT: "+JSON.stringify({
                "action":_reserved["action"],"reserved_ms":reserved,
                "engine_ms":engine}))
            # Do not create a second clock by moving an already scheduled
            # voice cue. A mismatch is rejected for diagnostics and cannot
            # play syllables at a non-authoritative time.
            _reserved.clear()
            return false
    var deadline: float = float(_reserved["deadline_ms"])
    var bpm: float = float(_reserved["bpm"])
    var beat: float = TempoTimeline.beats_from_milliseconds(float(now_ms)-deadline,bpm)
    if beat >= 0.0:
        # For one beat the same take's own transport (running or resumed
        # countdown of this transport) may still report a count-in beat:
        # it was already spoken. A later take (an announced continuation)
        # has its own countdown and is never suppressed.
        _count_in_owned_until_ms = deadline+TempoTimeline.seconds_from_beats(1.0,bpm)*1000.0
        _count_in_owned_transport = int(state.get("transport_id",-1))
        _reserved = {}
        return false
    var authored: Dictionary = _reserved.get("plan",{})
    _count_in(str(_reserved["token"]),beat,float(_reserved["bar"]),
        _reserved["meter"],true,float(_reserved["count_in"]),
        false,false,float(authored.get("pulse_beats",NAN)))
    return true

func _dispatch_cue(token: String, beat: float, bar: int,
        use_raw_click: bool, count_in_beats: float = CueTimeline.WHOLE_BAR,
        drop_late: bool = false) -> void:
    if beat < 0.0 and (token.begins_with("running:") or token.begins_with("resume:")) and \
            token.ends_with(":%d" % _count_in_owned_transport) and \
            float(_frame_now_ms) < _count_in_owned_until_ms:
        # The reserved countdown already spoke this count-in.
        return
    var cue: Dictionary = _cues.observe(token,beat,bar,count_in_beats,drop_late)
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
        paused: bool = false, drop_late: bool = false,
        authored_pulse: float = NAN) -> void:
    # One place turns a count-in reading into circles and cues, in the
    # meter's main pulse (M3); simple meters are unchanged.
    var pulse: float = (authored_pulse if is_finite(authored_pulse)
        and authored_pulse > 0.0 else CueTimeline.pulse_beats(meter))
    var units: Array = CueTimeline.in_pulses(beat,bar_beats,count_in_beats,
        pulse)
    practice_view.stage.count_in.present(float(units[0]),int(units[1]),true,
        paused,float(units[2]))
    if paused:
        _cues.hold(token,float(units[0]))
        return
    _dispatch_cue(token,float(units[0]),int(units[1]),use_raw_click,
        float(units[2]),drop_late)


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
    _frame_now_ms = now_ms
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
            beat = TempoTimeline.beats_from_milliseconds(
                float(now_ms)-float(clock.backend_offset_ms)-start_backend_ms,bpm)
        else:
            # Before the first clock calibration, retain a bounded startup
            # preview; the backend will publish its epoch on the next poll.
            beat = float(calibration.get("beat",-2.0)) + \
                TempoTimeline.beats_from_milliseconds(maxf(0.0,float(now_ms-state_tick_ms)),bpm)
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
    if _reserved_count_in(state,state_tick_ms,now_ms):
        return
    # Graphical audio has exactly one authorized take identity. Its
    # CountInPlan is an immutable source of spoken pulses and visible
    # preparation. With no current receipt, nothing may count down.
    if state.has("playback_timeline"):
        var playback: Variant = state.get("playback_timeline")
        var active: Variant = (playback.get("current")
            if playback is Dictionary else null)
        if active is Dictionary:
            var plan: Variant = active.get("count_in_plan")
            var take: String = str(active.get("take_id",""))
            if plan is Dictionary and not take.is_empty():
                var deadline_ms: float = float(active.get("deadline_ms",NAN))
                if is_finite(deadline_ms) and clock.has_backend_offset:
                    var tempo: float = maxf(1.0,float(plan.get("bpm",60.0)))
                    var beat_ms: float = deadline_ms+float(clock.backend_offset_ms)
                    var before: float = TempoTimeline.beats_from_milliseconds(
                        float(now_ms)-beat_ms,tempo)
                    var token: String = "authorized:"+take
                    var paused: bool = bool(state.get("paused",false))
                    if before < 0.0:
                        _count_in(token,before,
                            float(plan.get("bar_beats",4.0)),
                            plan.get("meter",[4,4]),true,
                            float(plan.get("beats",0.0)),paused,paused,
                            float(plan.get("pulse_beats",1.0)))
                        return
                    if bool(state.get("running",false)):
                        # Source-time metronome is still permitted AFTER
                        # beat zero. It does not create another countdown.
                        _count_in(token,sampled_beat,
                            float(plan.get("bar_beats",4.0)),
                            plan.get("meter",[4,4]),false,0.0,paused,
                            false,float(plan.get("pulse_beats",1.0)))
                        return
        practice_view.stage.count_in.present(0.0,4,false,false)
        # Preserve the heard-beat token if a paused take still owns it;
        # otherwise discard an expired no-longer-authorized cue epoch.
        if not bool(state.get("paused",false)):
            _cues.reset()
        return
    # All automatic and manual count-ins are published only after the
    # coordinator's admitted segment is authorized. There is no countdown
    # for an unadmitted retry or a speculative backend announcement.
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
            TempoTimeline.beats_from_milliseconds(maxf(0.0,float(now_ms-state_tick_ms)),bpm)
        if resume_beat < 0.0:
            # A Resume that reuses the paused count-in keeps its original
            # first-beat deadline, so its countdown is the same musical axis
            # as the transport beat. Continue that epoch: a syllable already
            # heard before Pause is not spoken again (one cycle only). This
            # continued countdown resumes mid-beat by construction, so a
            # beat first observed late is consumed (R1 M4); every other
            # count-in is spoken from a deadline Godot reserved (round 4).
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
                state.get("count_in_meter"),true,count_in_beats,false,true)
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
