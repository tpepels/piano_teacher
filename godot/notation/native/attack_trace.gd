extends Control
## Physical attack positions on the scrolling staff's outer rules.
## This surface is visual only. It reads the committed world clock; the
## grade, pitch and timestamp are supplied by the sequenced backend event.
const Design := preload("res://practice_theme.gd")
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const LIFETIME_MS := 1100.0
var _points: Array = []

func _ready() -> void:
    name = "AttackTrace"
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    z_index = 2

func present(markers: Array, renderer, flow, world: float) -> void:
    var had_points := not _points.is_empty()
    _points.clear()
    if renderer != null and is_instance_valid(renderer) and renderer.native_ready and flow.following:
        var gap: float = renderer.staff_gap()
        var density: float = renderer.timeline.pixels_per_beat
        var now := Time.get_ticks_msec()
        for marker in markers:
            if int(marker["run"]) != flow.musical.run:
                continue
            var age: float = maxf(0.0,float(now-int(marker["shown_ms"])))
            if age >= LIFETIME_MS:
                continue
            var x: float = size.x*PLAYHEAD_FRACTION + (flow.run_world(float(marker["world"]))-world)*density
            if x < 29.0 or x > size.x:
                continue
            var staff: String = str(marker["staff"])
            # Bumps sit on the outside staff rule so the noteheads stay clear.
            var y: float = renderer.layout.staff_center(staff) + (2.0 if staff == "left" else -2.0)*gap
            var color: Color = Design.HIGHLIGHT
            if not bool(marker["graded"]):
                color = Design.SECONDARY_INK
            elif str(marker["status"]) in ["early","late"]:
                color = Design.AMBER
            elif str(marker["status"]) in ["unexpected","count_in"]:
                color = Design.CORAL
            var alpha: float = 1.0-smoothstep(0.0,LIFETIME_MS,age)
            _points.append({"position":Vector2(x,y),"color":color,"alpha":alpha})
    if had_points or not _points.is_empty():
        queue_redraw()

func _draw() -> void:
    for point in _points:
        var position: Vector2 = point["position"]
        var color: Color = point["color"]
        var alpha: float = float(point["alpha"])
        draw_circle(position,9.0,Color(color,.10*alpha),true,-1.0,true)
        draw_circle(position,5.5,Color(color,.24*alpha),true,-1.0,true)
        draw_circle(position,3.0,Color(color,alpha),true,-1.0,true)
