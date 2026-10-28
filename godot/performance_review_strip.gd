extends VBoxContainer
# Settled-performance presentation only. The application owns navigation.
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")

signal review_requested(summary: Dictionary)
var ui_scale := 1.0
var summary_label: Label
var review_button: Button
var _summary: Dictionary = {}

func _ready() -> void:
    visible = false
    summary_label = Label.new()
    summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    summary_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    summary_label.add_theme_color_override("font_color", Design.STONE)
    summary_label.add_theme_font_override("font", Design.font(400))
    summary_label.set_meta("ui_font_base", 17)
    summary_label.add_theme_font_size_override("font_size",
        maxi(14, int(round(17.0*ui_scale))))
    add_child(summary_label)
    review_button = ActionButton.new()
    review_button.text = "Review notes and repeat a section"
    review_button.configure("review")
    review_button.set_meta("ui_font_base", 15)
    review_button.add_theme_font_size_override("font_size",
        maxi(14, int(round(15.0*ui_scale))))
    review_button.custom_minimum_size = Vector2(320.0*ui_scale,38.0*ui_scale)
    review_button.pressed.connect(func():
        review_requested.emit(_summary.duplicate(true)))
    add_child(review_button)

func present(summary: Dictionary) -> void:
    _summary = summary.duplicate(true)
    visible = not summary.is_empty()
    if not visible:
        return
    var timing_count: int = (
        int(summary.get("early",0)) + int(summary.get("late",0))
        + int(summary.get("short",0)) + int(summary.get("long",0)))
    summary_label.text = "%.0f%% correct · %d/%d notes · %d missed · %d wrong · %d timing/duration · %d extra" % [
        float(summary.get("accuracy_percent",0)),
        int(summary.get("correct",0)), int(summary.get("total",0)),
        int(summary.get("missed",0)), int(summary.get("wrong",0)),
        timing_count, int(summary.get("extra_notes",0))]
    var has_weak_bars: bool = not summary.get("weakest_bars",[]).is_empty()
    review_button.visible = has_weak_bars
    review_button.disabled = not has_weak_bars
