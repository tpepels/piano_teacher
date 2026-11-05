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
    var center := Vector2(53.0,size.y*.5)
    var radius := 30.0
    var total := int(result.get("total",0))
    var accuracy := clampf(float(result.get("accuracy_percent",
        100.0*float(result.get("correct",0))/maxi(1,total))),0.0,100.0)
    draw_arc(center,radius,0,TAU,64,Color(Design.PINE,.98),5.5,true)
    if total > 0:
        draw_arc(center,radius,-PI*.5,-PI*.5+TAU*accuracy/100.0,64,
            Color(Design.MINT,.20),10.0,true)
        draw_arc(center,radius,-PI*.5,-PI*.5+TAU*accuracy/100.0,64,
            Design.MINT,4.5,true)
    # Keep only the percentage inside the narrow circular gauge. Previously
    # "Accuracy" was drawn at y+17, crossing the lower arc.
    var caption := "%.0f%%" % accuracy if total > 0 else "—"
    var face: Font = Design.font(600)
    var amount_size := 20
    var extent := face.get_string_size(caption,HORIZONTAL_ALIGNMENT_LEFT,-1,
        amount_size).x
    var baseline := center.y + (face.get_ascent(amount_size) -
        face.get_descent(amount_size))*.5
    draw_string(face,Vector2(center.x-extent*.5,baseline),caption,
        HORIZONTAL_ALIGNMENT_LEFT,-1,amount_size,Design.STONE)
    var text_x := 110.0
    var text_width := maxf(1.0,size.x-text_x-12.0)
    _text("Accuracy",Vector2(text_x,25),16,Design.STONE,text_width)
    _text("%d / %d clean passes" % [accepted_passes,required],
        Vector2(text_x,46),13,Design.SECONDARY_INK,text_width)
    var details := ("%d of %d notes correct" % [int(result.get("correct",0)),total]
        if total > 0 else "Listen/preview · not graded"
        if ungraded else "No assessed attempt yet")
    if total > 0 and result.has("missed") and result.has("wrong"):
        details = "%d correct · %d missed · %d wrong" % [
            int(result.get("correct",0)),int(result.get("missed",0)),
            int(result.get("wrong",0))]
    _text(details,Vector2(text_x,65),12,Design.SECONDARY_INK,text_width)
    var x := text_x
    for item in [["Correct",Design.MINT],["Missed",Design.CORAL],
            ["Timing",Design.AMBER]]:
        if compact and item[0] == "Timing":
            continue
        draw_circle(Vector2(x,size.y-17),3,item[1])
        _text(item[0],Vector2(x+8,size.y-13),10,Design.SECONDARY_INK)
        x += 69.0
