extends RefCounted
# Native barline layout, separate from paint and GPU glyph management.
# Semantic quarter-beat positions and staff bounds are supplied explicitly.
static func boundary(measures: Array, measure: Dictionary, timeline,
        clock: float, playhead_x: float, play_from_beat: float,
        gap: float, top: float, bottom: float) -> Dictionary:
    var index: int = measures.find(measure)
    if index < 0:
        return {}
    var mark: Variant = measure.get("left_barline")
    if index == 0 and not mark is Dictionary:
        return {}
    if index > 0:
        var previous: Dictionary = measures[index-1]
        var previous_right: Variant = previous.get("right_barline")
        if not mark is Dictionary:
            mark = previous_right
        elif previous_right is Dictionary and \
                str(previous_right.get("repeat","")) == "backward" and \
                str(mark.get("repeat","")) == "forward":
            # Right repeat followed by left repeat at the same barline.
            mark = {"style":"heavy-heavy","repeat":"both"}
    if not mark is Dictionary:
        mark = {"style":"regular","repeat":""}
    var x: float = timeline.screen_x(float(measure.get("start_beat", 0.0)),
        clock, playhead_x, play_from_beat) - gap*1.35
    return {"x":x, "top":top,
        "bottom":bottom,
        "style":str(mark.get("style","regular")),
        "repeat":str(mark.get("repeat",""))}


static func terminal(measures: Array, timeline,
        clock: float, playhead_x: float, play_from_beat: float,
        gap: float, top: float, bottom: float) -> Dictionary:
    if measures.is_empty():
        return {}
    var last: Dictionary = measures[-1]
    var mark: Variant = last.get("right_barline")
    if not mark is Dictionary:
        mark = {"style":"regular","repeat":""}
    var x: float = timeline.screen_x(float(last.get("end_beat",0.0)),
        clock,playhead_x,play_from_beat)-gap*.45
    return {"x":x, "top":top,
        "bottom":bottom,
        "style":str(mark.get("style","regular")),
        "repeat":str(mark.get("repeat",""))}


# Per SMuFL, barline strokes are drawn as structural rules. Unlike
# noteheads/stems they are variable-length rules spanning both staves;
# their repeat punctuation is genuine Verovio E044 music-font ink.
static func strokes(style: String, gap: float) -> Array:
    var thin: float = maxf(1.15,gap*.095)
    var heavy: float = maxf(3.1,gap*.35)
    var separation: float = gap*.44
    match style:
        "none": return []
        "regular", "dashed", "dotted":
            return [{"offset":0.0,"width":thin}]
        "heavy":
            return [{"offset":0.0,"width":heavy}]
        "light-light":
            return [{"offset":-separation,"width":thin},
                {"offset":0.0,"width":thin}]
        "light-heavy":
            return [{"offset":-separation,"width":thin},
                {"offset":0.0,"width":heavy}]
        "heavy-light":
            return [{"offset":-separation,"width":heavy},
                {"offset":0.0,"width":thin}]
        "heavy-heavy":
            return [{"offset":-separation,"width":heavy},
                {"offset":0.0,"width":heavy}]
    return []


