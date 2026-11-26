extends Control
## Physical attack positions at their actual pitch on the scrolling staff.
## This surface is visual only. It reads the committed world clock; the
## grade, pitch and timestamp are supplied by the sequenced backend event.
const Design := preload("res://practice_theme.gd")
const GhostNotePainter := preload("res://notation/native/ghost_note_painter.gd")
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const LIFETIME_MS := 1100.0
var _points: Array = []

func _ready() -> void:
    name = "AttackTrace"
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    z_index = 2

func present(markers: Array, feedback, flow, world: float) -> void:
    var had_points := not _points.is_empty()
    _points.clear()
    if flow.following:
        var now := Time.get_ticks_msec()
        for marker in markers:
            if int(marker["run"]) != flow.musical.run:
                continue
            var age: float = maxf(0.0,float(now-int(marker["shown_ms"])))
            if age >= LIFETIME_MS:
                continue
            var renderer = feedback.renderer_for_attack(int(marker["revision"]))
            if renderer == null or not is_instance_valid(renderer):
                continue
            var density: float = renderer.timeline.pixels_per_beat
            var x: float = size.x*PLAYHEAD_FRACTION + (flow.run_world(float(marker["world"]))-world)*density
            if x < 29.0 or x > size.x:
                continue
            var pitch_position := GhostNotePainter.pitch_position(renderer.painter,marker)
            if pitch_position.is_empty():
                continue
            var y: float = float(pitch_position["y"])
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
