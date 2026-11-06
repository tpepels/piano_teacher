extends Control
## Score-overlay visuals only. No audio player, external IO, or independent
## clock is allowed here. A persistent root-owned voice service handles sound.
var count := 4
var current := -1
var beats_left := 0
var beat_fraction := 0.0
var _voice_service: Node

var spoken_enabled: bool:
    get:
        if _voice_service != null:
            return bool(_voice_service.get("spoken_enabled"))
        return true

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE

func attach_voice_service(service: Node) -> void:
    assert(service != null and service.has_method("speak_beat") and
        service.has_method("set_spoken_enabled"))
    _voice_service = service

func set_spoken_enabled(enabled: bool) -> void:
    if _voice_service != null:
        _voice_service.set_spoken_enabled(enabled)

func voice_status() -> Dictionary:
    return _voice_service.status() if _voice_service != null else {
        "enabled":spoken_enabled,"available":false,
        "missing":["audio_service_not_attached"]}

func speak_beat(number: int) -> bool:
    return bool(_voice_service.speak_beat(number)) if _voice_service != null else false

func present(beat: float, beats_per_bar: int, running: bool, paused: bool) -> void:
    var show: bool = running and not paused and is_finite(beat) and beat < 0.0
    var next_count: int = clampi(beats_per_bar,1,12)
    var step: int = posmod(int(floor(beat+.00001)),next_count) if show else -1
    var fraction: float = fposmod(beat,1.0) if show else 0.0
    var remaining: int = maxi(1,int(ceil(-beat-.00001))) if show else 0
    if (visible != show or count != next_count or current != step
            or beats_left != remaining or (show and absf(beat_fraction-fraction)>.012)):
        visible = show
        count = next_count
        current = step
        beats_left = remaining
        beat_fraction = fraction
        queue_redraw()

func _draw() -> void:
    if not visible or size.x < 110.0 or size.y < 45.0:
        return
    var n: int = mini(count,12)
    var gap: float = minf(50.0,(size.x-28.0)/float(maxi(1,n)))
    var first_x: float = size.x*.5 - gap*float(n-1)*.5
    var center_y: float = size.y*.38
    var radius: float = 19.0 if n <= 6 else 13.5
    var pulse: float = pow(1.0-beat_fraction,3.0)
    var font: Font = ThemeDB.fallback_font
    var font_size: int = 17 if n <= 6 else 13
    var caption_size: int = 11
    var syllables: Array[String] = ["Ichi", "Ni", "San", "Shi"]
    for i in range(n):
        var center := Vector2(first_x+gap*float(i),center_y)
        var active: bool = i == current
        var old: bool = i < current
        if active:
            draw_circle(center,radius+6.0+4.0*pulse,
                Color("#55F5C3",.09+.18*pulse))
        draw_circle(center,radius,
            Color("#53E9B6",.88) if active else
            Color("#23433E",.94) if old else Color("#15332F",.85))
        draw_arc(center,radius,-PI*.5,
            -PI*.5+TAU*(beat_fraction if active else 1.0 if old else 0.0),
            40,Color("#B9FFE4",.92) if active else
            Color("#467D6C",.65),2.1,true)
        var numeral: String = str(i+1)
        var ink: Color = Color("#052F28") if active else Color("#D0E9DD")
        var text_width: float = font.get_string_size(
            numeral,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size).x
        var baseline: float = center.y+(
            font.get_ascent(font_size)-font.get_descent(font_size))*.5
        draw_string(font,Vector2(center.x-text_width*.5,baseline),
            numeral,HORIZONTAL_ALIGNMENT_LEFT,-1,font_size,ink)
        if n <= 6:
            var caption: String = syllables[i] if i < 4 else str(i+1)
            var caption_width: float = font.get_string_size(
                caption,HORIZONTAL_ALIGNMENT_LEFT,-1,caption_size).x
            draw_string(font,Vector2(center.x-caption_width*.5,
                center.y+radius+16.0),caption,
                HORIZONTAL_ALIGNMENT_LEFT,-1,caption_size,
                Color("#B3D8C9",.92) if active else Color("#6F988D",.78))
