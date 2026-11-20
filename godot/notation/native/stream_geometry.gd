extends RefCounted
## A physical admission snapshot. Only primitive display facts cross into
## stream policy; this value cannot mutate the renderer or its score.
var _ready: bool
var ready: bool:
    get: return _ready
var _world: float
var world: float:
    get: return _world
var _density: float
var density: float:
    get: return _density
var _gap: float
var gap: float:
    get: return _gap
var _duration: float
var duration: float:
    get: return _duration
var _width: float
var width: float:
    get: return _width
var _playhead: float
var playhead: float:
    get: return _playhead
var _rest_gap: float
var rest_gap: float:
    get: return _rest_gap
var _first_header_spaces: float
var first_header_spaces: float:
    get: return _first_header_spaces

func _init(is_ready: bool, at_world: float, pixels_per_beat: float,
        staff_gap: float, source_duration: float, viewport_width: float,
        playhead_x: float, written_rest: float, header_spaces: float) -> void:
    _ready = is_ready
    _world = at_world
    _density = pixels_per_beat
    _gap = staff_gap
    _duration = source_duration
    _width = viewport_width
    _playhead = playhead_x
    _rest_gap = written_rest
    _first_header_spaces = header_spaces
