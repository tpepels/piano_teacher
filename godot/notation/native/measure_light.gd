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
    # The reference uses a pool of light, not an opaque green rectangle.
    # Preserve luminous boundaries while retaining sharp white staff ink.
    canvas.draw_rect(area,Color(Design.MINT,.085))
    var glow_width := minf(area.size.x,maxf(28.0,gap*6.0))
    var glow_center := clampf(playhead_x,left+glow_width*.5,right-glow_width*.5)
    for band in range(4):
        var width := glow_width*(1.0-float(band)*.18)
        canvas.draw_rect(Rect2(glow_center-width*.5,top,width,bottom-top),
            Color(Design.MINT,.016+float(band)*.009))
    # Narrow edge halos make the measure readable without coloring every
    # notehead and rest. This presentation uses the existing score geometry.
    for edge_x in [left,right]:
        canvas.draw_rect(Rect2(edge_x-3.0,top,6.0,bottom-top),
            Color(Design.MINT,.070))
        canvas.draw_line(Vector2(edge_x,top),Vector2(edge_x,bottom),
            Color(Design.HIGHLIGHT,.65),1.1,true)
    canvas.draw_rect(Rect2(left,top,right-left,3.0),Color(Design.MINT,.055))
    canvas.draw_line(Vector2(left,top),Vector2(right,top),
        Color(Design.HIGHLIGHT,.85),1.25,true)
    canvas.draw_line(Vector2(left,bottom),Vector2(right,bottom),
        Color(Design.MINT,.48),1.0,true)
