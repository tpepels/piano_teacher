extends RefCounted
## One forward-only score world. During a run of timed music it follows
## the musical timeline Python publishes (state.musical_timeline): world(t)
## is the same pure function of its segments that grading uses. Outside a
## run (Free, idle, after Stop) the PresentationTimeline holds or moves it.
## Native score clipping and take placement consume the same projection.
const PresentationTimeline := preload("res://presentation_timeline.gd")
const MusicalTimeline := preload("res://musical_timeline.gd")
var timeline = PresentationTimeline.new()
var musical = MusicalTimeline.new()
var beat := 0.0
var last_ms := -1
var bpm := 40.0
var initialized := false
var hold_world := INF
# Python monotonic ms (PianoNative); set by the score admission gateway.
var backend_clock: Callable
var following := false
# World of this run's world 0: where the staff was when the run appeared.
var run_offset := 0.0
var _clock_offset_ms := 0.0

func _backend_ms(at_ms: int) -> float:
    return float(at_ms)-_clock_offset_ms

## Adopt the published timeline. A new run continues from the current
## world; when the run ends the world holds where the run left it.
func follow(published: Variant, at_ms: int) -> void:
    var previous_run: int = musical.run if following else -1
    if not backend_clock.is_valid() or not musical.load_state(published):
        if following:
            _leave_run(at_ms)
        return
    var backend_now: float = float(backend_clock.call())
    if not is_finite(backend_now):
        return
    _clock_offset_ms = float(Time.get_ticks_msec())-backend_now
    if not following or musical.run != previous_run:
        var here: float = project(at_ms) if following else _project_epochs(at_ms)
        following = false
        run_offset = here-musical.world_at(_backend_ms(at_ms))
        following = true
        initialized = true
        hold_world = INF

func _leave_run(at_ms: int) -> void:
    var here: float = project(at_ms)
    following = false
    timeline.reset()
    timeline.initialize(maxi(0,at_ms),maxf(1.0,bpm))
    timeline.epochs[0]["world"] = here
    timeline.last_world = here
    timeline.set_hold(here,maxi(0,at_ms))
    beat = here
    last_ms = timeline.last_ms
    hold_world = timeline.hold_world

## Beats from the first note of take `segment_id` at local `at_ms`
## (negative in its count-in); NAN when the take is not on the timeline.
func take_beat(segment_id: String, at_ms: int) -> float:
    if not following:
        return NAN
    for segment in musical.segments:
        if str(segment.get("kind","")) == "take" and \
                str(segment.get("take_id","")) == segment_id:
            return musical.world_at(_backend_ms(at_ms))-float(segment["world_start"])
    return NAN

## World position of a run-relative timeline world beat.
func run_world(world: float) -> float:
    return run_offset+world

func _follow_rate(at_ms: int) -> float:
    var segment: Dictionary = musical.segment_at(_backend_ms(at_ms))
    if segment.is_empty():
        return bpm
    var into: float = musical.world_at(_backend_ms(at_ms))-float(segment["world_start"])
    return MusicalTimeline.bpm_at(segment,clampf(into,0.0,float(segment["beats"])))

func sample(at_ms: int, selected_bpm: float = NAN) -> float:
    if following:
        if at_ms >= last_ms:
            beat = project(at_ms)
            last_ms = at_ms
            bpm = _follow_rate(at_ms)
        return beat
    if not initialized:
        timeline.initialize(at_ms,selected_bpm if is_finite(selected_bpm) else bpm)
    elif is_finite(selected_bpm) and selected_bpm > 0.0:
        timeline.set_rate(at_ms,selected_bpm)
    beat = timeline.sample(at_ms)
    last_ms = timeline.last_ms
    bpm = timeline.current_rate()
    initialized = timeline.initialized()
    hold_world = timeline.hold_world
    return beat

func sample_uncommitted(at_ms: int, proposed_bpm: float) -> float:
    # A fresh, unbound score may establish the idle rate; a run or an
    # authorized segment keeps its own.
    return sample(at_ms) if following or not timeline.active_segment.is_empty() else \
        sample(at_ms,proposed_bpm)

func _project_epochs(at_ms: int) -> float:
    return timeline.project(at_ms)

func project(at_ms: int) -> float:
    if following:
        var world: float = musical.world_at(_backend_ms(at_ms))
        if not is_finite(world):
            return beat
        # Forward-only: a republished timeline never pulls the staff back.
        return maxf(beat if at_ms >= last_ms else -INF,run_offset+world)
    return timeline.project(at_ms)

func hold_at(world: float) -> void:
    if following:
        return
    timeline.set_hold(world,maxi(0,timeline.last_ms))
    beat = timeline.last_world
    hold_world = timeline.hold_world

func release_hold() -> void:
    if following:
        return
    if is_finite(timeline.hold_world):
        timeline.set_hold(INF,maxi(0,timeline.last_ms))
    hold_world = timeline.hold_world

func physical_travel_ms_to(target_world: float, sampled_ms: int,
        source_beat: float, nominal_bpm: float, authored_segments: Array) -> float:
    return timeline.physical_travel_ms_to(
        target_world,sampled_ms,source_beat,nominal_bpm,authored_segments)

func project_authored_future(at_ms: int, sampled_ms: int,
        source_beat: float, nominal_bpm: float,
        authored_segments: Array) -> float:
    # Free places its first target from a hypothetical future of the held
    # world; a run's future is its timeline.
    if following:
        return project(at_ms)
    if not timeline.active_segment.is_empty() and not is_finite(timeline.hold_world):
        return timeline.project(at_ms)
    return timeline.forecast_authored(
        at_ms,sampled_ms,source_beat,nominal_bpm,authored_segments)

func reset() -> void:
    timeline.reset()
    musical.load_state(null)
    following = false
    run_offset = 0.0
    beat = 0.0
    last_ms = -1
    bpm = 40.0
    initialized = false
    hold_world = INF
