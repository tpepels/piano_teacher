extends RefCounted
## One forward-only score world. During any run of music -- Listen, Tempo
## takes and Free -- it follows the musical timeline Python publishes
## (state.musical_timeline): world(t) is the same pure function of its
## segments that grading uses, Free's waits included as holds. Outside a run
## (idle, after Stop) the world stands where the last run left it.
const MusicalTimeline := preload("res://musical_timeline.gd")
var musical = MusicalTimeline.new()
var beat := 0.0
var last_ms := -1
var bpm := 40.0
var initialized := false
# The world the staff rests at (a Free target or idle), INF while moving.
var hold_world := 0.0
# Python monotonic ms (PianoNative); set by the score admission gateway.
var backend_clock: Callable
var following := false
# World of this run's world 0: where the staff was when the run appeared.
var run_offset := 0.0
var _clock_offset_ms := 0.0

func _backend_ms(at_ms: int) -> float:
    return float(at_ms)-_clock_offset_ms

## Adopt the published timeline. A new run continues from the current
## world; when the run ends the world stands where the run left it.
func follow(published: Variant, at_ms: int) -> void:
    # Sample the outgoing run BEFORE replacing its timeline and clock.
    var here: float = project(at_ms)
    var previous_run: int = musical.run if following else -1
    if not backend_clock.is_valid():
        beat = here
        following = false
        hold_world = beat
        return
    var before_us := Time.get_ticks_usec()
    var backend_now: float = float(backend_clock.call())
    var after_us := Time.get_ticks_usec()
    if not is_finite(backend_now):
        return
    if not musical.load_state(published):
        beat = here
        following = false
        hold_world = beat
        return
    # Both clocks are monotonic in the same process. Fix their offset
    # for this run instead of injecting poll-to-poll rounding jitter.
    if not following or musical.run != previous_run:
        _clock_offset_ms = float(before_us+after_us)*.0005-backend_now
        beat = here
        run_offset = here-musical.world_at(_backend_ms(at_ms))
        following = true
        initialized = true

## World position of a run-relative timeline world beat.
func run_world(world: float) -> float:
    return run_offset+world

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

func _follow_rate(at_ms: int) -> float:
    var segment: Dictionary = musical.segment_at(_backend_ms(at_ms))
    if segment.is_empty():
        return bpm
    var into: float = musical.world_at(_backend_ms(at_ms))-float(segment["world_start"])
    return MusicalTimeline.bpm_at(segment,clampf(into,0.0,float(segment["beats"])))

func sample(at_ms: int, _selected_bpm: float = NAN) -> float:
    if at_ms >= last_ms:
        beat = project(at_ms)
        last_ms = at_ms
        if following:
            bpm = _follow_rate(at_ms)
            var held: float = musical.hold_world_at(_backend_ms(at_ms))
            hold_world = run_offset+held if is_finite(held) else INF
        else:
            hold_world = beat
    return beat

func sample_uncommitted(at_ms: int, _proposed_bpm: float) -> float:
    return sample(at_ms)

func project(at_ms: int) -> float:
    if not following:
        return beat
    var world: float = musical.world_at(_backend_ms(at_ms))
    if not is_finite(world):
        return beat
    # Forward-only: a republished timeline never pulls the staff back.
    return maxf(beat if at_ms >= last_ms else -INF,run_offset+world)

## Free places its first target where the timeline brings the staff.
func project_authored_future(at_ms: int, _sampled_ms: int,
        _source_beat: float, _nominal_bpm: float,
        _authored_segments: Array) -> float:
    return project(at_ms)

func reset() -> void:
    musical.load_state(null)
    following = false
    run_offset = 0.0
    beat = 0.0
    last_ms = -1
    bpm = 40.0
    initialized = false
    hold_world = 0.0
