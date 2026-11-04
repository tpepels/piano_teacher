extends RefCounted
## Presentation only: use the same source measures and repeat/rest contract
## as the retained compositor. No clock, assessment or transport ownership.
const Design := preload("res://practice_theme.gd")
const Barline := preload("res://notation/native/barline_layout.gd")

static func interval(measures: Array, beat: float, contract: Dictionary,
        history: Dictionary, cutoff: float) -> Vector2:
    if not is_finite(beat) or beat < 0.0 or beat >= cutoff:
        return Vector2.INF
    var origin := 0.0
    var local := beat
    if not contract.is_empty():
        for item in history.values():
            var rest: Dictionary = item["measure"]
            if beat >= float(rest["start_beat"]) and beat < float(rest["end_beat"]):
                return Vector2(float(rest["start_beat"]), minf(float(rest["end_beat"]),cutoff))
        var stride := float(contract.get("stride_beats",0.0))
        if stride <= 0.0:
            return Vector2.INF
        origin = floorf(beat/stride)*stride
        local = beat-origin
        var rest: Dictionary = contract.get("gap",{})
        if not rest.is_empty() and local >= float(rest["start_beat"]) and local < float(rest["end_beat"]):
            return Vector2(origin+float(rest["start_beat"]),minf(origin+float(rest["end_beat"]),cutoff))
    # Sorted source boundaries include pickup measures and meter changes.
    var lo := 0
    var hi := measures.size()-1
    while lo <= hi:
        var mid := (lo+hi)/2
        var measure: Dictionary = measures[mid]
        if local < float(measure["start_beat"]):
            hi = mid-1
        elif local >= float(measure["end_beat"]):
            lo = mid+1
        else:
            return Vector2(origin+float(measure["start_beat"]),
                minf(origin+float(measure["end_beat"]),cutoff))
    return Vector2.INF

static func paint(canvas: Control, timeline, beat: float, bounds: Vector2,
        gap: float, top: float, bottom: float, playhead_x: float) -> void:
    if bounds == Vector2.INF:
        return
    var left := Barline.project(bounds.x,timeline,beat,playhead_x,0.0,gap)
    var right := Barline.project(bounds.y,timeline,beat,playhead_x,0.0,gap)
    left = maxf(30.0,left)
    right = minf(canvas.size.x,right)
    if right <= left:
        return
    var area := Rect2(left,top,right-left,bottom-top)
    # Broad illumination is BELOW staff, glyphs, stems and barlines. Thin
    # layers soften the light vertically without blurring the musical ink.
    canvas.draw_rect(area,Color(Design.MINT,.16))
    for i in range(8):
        var inset := float(i)*gap*.22
        var lit := Rect2(left,top+inset,right-left,maxf(0.0,bottom-top-inset*2.0))
        canvas.draw_rect(lit,Color(Design.MINT,.012))
    canvas.draw_line(Vector2(left,top),Vector2(right,top),Color(Design.MINT,.55),1.0,true)
    canvas.draw_line(Vector2(left,bottom),Vector2(right,bottom),Color(Design.MINT,.28),1.0,true)
