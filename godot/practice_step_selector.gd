extends HBoxContainer
# Captures only lesson-step presentation and emits a numeric selection intent.
const UI := preload("res://ui_factory.gd")
signal step_requested(number: int)
var picker: OptionButton
var previous_button: Button
var next_button: Button
var entries: Array = []
var _fingerprint := ""
var _current_fingerprint := ""
var _loaded := false
var _current := 0
var _busy := false

func _ready() -> void:
    name = "PracticeStepControls"
    size_flags_horizontal = Control.SIZE_SHRINK_END
    add_theme_constant_override("separation",5)
    z_index = 6
    previous_button = UI.button("‹","navigation")
    previous_button.custom_minimum_size = Vector2(38,38)
    previous_button.tooltip_text = "Previous lesson step (hand and note level)"
    previous_button.pressed.connect(func(): _select(_current - 1))
    add_child(previous_button)
    picker = OptionButton.new()
    picker.name = "PracticeLessonStepPicker"
    picker.custom_minimum_size = Vector2(225,38)
    picker.fit_to_longest_item = false
    picker.clip_text = true
    picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    picker.tooltip_text = "Choose any lesson step directly, without earning mastery"
    picker.item_selected.connect(func(index: int): _select(index + 1))
    add_child(picker)
    next_button = UI.button("›","navigation")
    next_button.custom_minimum_size = Vector2(38,38)
    next_button.tooltip_text = "Next lesson step (hand and note level)"
    next_button.pressed.connect(func(): _select(_current + 1))
    add_child(next_button)
    _present()

func present_context(state: Dictionary, busy: bool) -> void:
    _loaded = bool(state.get("loaded",false))
    _current_fingerprint = str(state.get("piece_fingerprint",""))
    _current = int(state.get("lesson_step",0))
    if not _loaded:
        entries.clear()
        picker.clear()
        _fingerprint = ""
    present_busy(busy)

func present_busy(busy: bool) -> void:
    _busy = busy
    _present()

func present_overview(values: Dictionary) -> void:
    _fingerprint = str(values.get("piece_fingerprint",""))
    entries = values.get("steps",[]).duplicate(true)
    picker.clear()
    for step in entries:
        picker.add_item("%d/%d · %d–%d · %s · %s" % [int(step.get("number",0)),entries.size(),
            int(step.get("first_bar",1)),int(step.get("last_bar",1)),
            str(step.get("hand","")).capitalize(),str(step.get("level","")).capitalize()])
    _present()

func _present() -> void:
    var ready: bool = _loaded and _fingerprint == _current_fingerprint and not entries.is_empty()
    picker.disabled = _busy or not ready
    previous_button.disabled = _busy or not ready or _current <= 1
    next_button.disabled = _busy or not ready or _current >= entries.size()
    if ready and _current >= 1 and _current <= picker.item_count:
        picker.select(_current - 1)
        picker.text = "Step %d / %d" % [_current,entries.size()]

func _select(number: int) -> void:
    if not picker.disabled and number != _current and number >= 1 and number <= entries.size():
        step_requested.emit(number)

func apply_viewport(view_size: Vector2, scale: float) -> void:
    var compact: bool = view_size.x < 1250.0
    custom_minimum_size.x = 350.0 if view_size.x < 850.0 else 420.0 if compact else 500.0
    picker.custom_minimum_size.x = 120.0 if view_size.x < 850.0 else 150.0 if compact else 180.0
    for arrow in [previous_button,next_button]:
        arrow.custom_minimum_size.x = 40.0
        arrow.add_theme_font_size_override("font_size",UI.font_size(15,scale))
