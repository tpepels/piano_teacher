extends Control
## Read-only presentation of assessed results. Empty/ungraded sessions show
## an empty ring, never a manufactured accuracy or successful note count.
const Design := preload("res://practice_theme.gd")
var result: Dictionary = {}
var accepted_passes := 0
var required := 3
var ungraded := true
var _face := Design.card_surface()

func _init() -> void:
    custom_minimum_size = Vector2(330,104)
    mouse_filter = Control.MOUSE_FILTER_PASS
    tooltip_text = "Accuracy is shown after an assessed take. Preview and Listen do not earn results."
    resized.connect(queue_redraw)

func present(state: Dictionary) -> void:
    var next_ungraded: bool = bool(state.get("preview_only",false)) or str(state.get("mode","")) in ["listen","learn"]
    var next: Dictionary = {}
    if not next_ungraded:
        var summary: Variant = state.get("performance_summary")
        var take: Variant = state.get("take_result")
        if summary is Dictionary and not summary.is_empty():
            next = summary
        elif take is Dictionary:
            next = take
    var count := int(state.get("streak",0)) if not next_ungraded else 0
    var total := maxi(1,int(state.get("clean_runs_required",3)))
    if next != result or count != accepted_passes or total != required or next_ungraded != ungraded:
        result = next.duplicate(true)
        accepted_passes = count
        required = total
        ungraded = next_ungraded
        queue_redraw()

func _text(value: String, at: Vector2, font_size: int, tone: Color, width: float = -1) -> void:
    draw_string(Design.font(),at,value,HORIZONTAL_ALIGNMENT_LEFT,width,font_size,tone)

func _draw() -> void:
    draw_style_box(_face,Rect2(Vector2.ZERO,size))
    var compact := size.x < 320.0
    var center := Vector2(49,size.y*.5)
    var radius := 29.0
    var total := int(result.get("total",0))
    var accuracy := clampf(float(result.get("accuracy_percent",
        100.0*float(result.get("correct",0))/maxi(1,total))),0.0,100.0)
    draw_arc(center,radius,0,TAU,64,Color(Design.PINE,.98),6,true)
    if total > 0:
        draw_arc(center,radius,-PI*.5,-PI*.5+TAU*accuracy/100.0,64,Color(Design.MINT,.22),12,true)
        draw_arc(center,radius,-PI*.5,-PI*.5+TAU*accuracy/100.0,64,Design.MINT,5,true)
    var caption := "%.0f%%" % accuracy if total > 0 else "—"
    var extent := Design.font(600).get_string_size(caption,HORIZONTAL_ALIGNMENT_LEFT,-1,18).x
    draw_string(Design.font(600),center+Vector2(-extent*.5,3),caption,HORIZONTAL_ALIGNMENT_LEFT,-1,18,Design.STONE)
    _text("Accuracy",center+Vector2(-25,17),10,Design.SECONDARY_INK)
    _text("Performance",Vector2(96,24),16,Design.STONE,size.x-108)
    _text("%d / %d accepted passes" % [accepted_passes,required],Vector2(96,45),13,Design.SECONDARY_INK,size.x-108)
    var details := "%d/%d correct" % [int(result.get("correct",0)),total] if total > 0 else "Preview · ungraded" if ungraded else "Awaiting assessed take"
    if total > 0 and result.has("missed") and result.has("wrong"):
        details = "%d/%d correct · %d missed · %d wrong" % [
            int(result.get("correct",0)),total,
            int(result.get("missed",0)),int(result.get("wrong",0))]
    _text(details,Vector2(96,64),13,Design.SECONDARY_INK,size.x-108)
    var x := 100.0
    for item in [["Correct",Design.MINT],["Missed",Design.CORAL],["Timing",Design.AMBER]]:
        if compact and item[0] == "Timing":
            continue
        draw_circle(Vector2(x,size.y-17),3,item[1])
        _text(item[0],Vector2(x+7,size.y-13),10,Design.SECONDARY_INK)
        x += 72.0
