extends RefCounted
## Evaluates the musical timeline Python publishes in state.musical_timeline
## (piano_teacher/application/musical_timeline.py): the same segments, holds
## and closed forms, so the scrolling world and the clicks follow exactly the
## time <-> world mapping grading uses. Times are Python monotonic ms, the
## same steady clock as PianoNative.monotonic_milliseconds().
const TempoCurve := preload("res://tempo_curve.gd")

var run := -1
var segments: Array = []
var holds: Array = []
var end_world := INF

func load_state(published: Variant) -> bool:
    ## Adopt a published timeline; false when there is none.
    if not published is Dictionary or (published.get("segments",[]) as Array).is_empty():
        run = -1
        segments = []
        holds = []
        end_world = INF
        return false
    run = int(published.get("run",-1))
    segments = published.get("segments",[])
    holds = published.get("holds_ms",[])
    var closed: Variant = published.get("end_world")
    end_world = float(closed) if closed != null else INF
    return true

func active() -> bool:
    return not segments.is_empty()

func paused() -> bool:
    return not holds.is_empty() and holds[-1][1] == null

func musical_ms(t_ms: float) -> float:
    var m := t_ms
    for hold in holds:
        var at: float = float(hold[0])
        if t_ms > at:
            var length: float = INF if hold[1] == null else float(hold[1])
            m -= minf(t_ms-at,length)
    return m

static func _beats(segment: Dictionary) -> float:
    return float(segment.get("beats",0.0))

static func seconds_at(segment: Dictionary, beats: float) -> float:
    beats = clampf(beats,0.0,_beats(segment))
    var elapsed := 0.0
    for span in segment.get("spans",[]):
        var length: float = float(span[0])
        if beats <= length:
            return elapsed+TempoCurve.seconds_at(beats,length,float(span[1]),float(span[2]))
        elapsed += TempoCurve.seconds_at(length,length,float(span[1]),float(span[2]))
        beats -= length
    return elapsed

static func beat_at(segment: Dictionary, seconds: float) -> float:
    if seconds <= 0.0:
        return 0.0
    var passed := 0.0
    for span in segment.get("spans",[]):
        var length: float = float(span[0])
        var whole: float = TempoCurve.seconds_at(length,length,float(span[1]),float(span[2]))
        if seconds <= whole:
            return minf(_beats(segment),passed+TempoCurve.beat_at(seconds,length,float(span[1]),float(span[2])))
        seconds -= whole
        passed += length
    return _beats(segment)

static func bpm_at(segment: Dictionary, beats: float) -> float:
    var spans: Array = segment.get("spans",[])
    for span in spans:
        var length: float = float(span[0])
        if beats < length:
            return TempoCurve.bpm_at(beats,length,float(span[1]),float(span[2]))
        beats -= length
    var last: Array = spans[-1]
    return float(last[2])

static func end_ms(segment: Dictionary) -> float:
    return float(segment["start_ms"])+seconds_at(segment,_beats(segment))*1000.0

func world_at(t_ms: float) -> float:
    ## World beat (relative to the run) at Python monotonic ms `t_ms`.
    if segments.is_empty():
        return NAN
    var m: float = musical_ms(t_ms)
    var first: Dictionary = segments[0]
    if m <= float(first["start_ms"]):
        return minf(float(first["world_start"]),end_world)
    var chosen: Dictionary = first
    for segment in segments:
        if float(segment["start_ms"]) > m:
            break
        chosen = segment
    var world: float
    var finish: float = end_ms(chosen)
    if m >= finish and chosen == segments[-1]:
        world = float(chosen["world_start"])+_beats(chosen)+ \
            (m-finish)/60000.0*bpm_at(chosen,_beats(chosen))
    else:
        world = float(chosen["world_start"])+beat_at(chosen,(m-float(chosen["start_ms"]))/1000.0)
    return minf(world,end_world)

func segment_at(t_ms: float) -> Dictionary:
    if segments.is_empty():
        return {}
    var m: float = musical_ms(t_ms)
    var chosen: Dictionary = segments[0]
    for segment in segments:
        if float(segment["start_ms"]) > m:
            break
        chosen = segment
    return chosen
