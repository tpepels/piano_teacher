extends ScrollContainer
# Lesson owns path presentation, choices and reset confirmation state.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL
signal command_requested(command: Dictionary)
signal practice_requested
signal advanced_requested

var stage_labels: Dictionary = {}
var piece_title: Label
var summary: Label
var description: Label
var columns: BoxContainer
var rows: VBoxContainer
var options: PanelContainer
var mode_choice: OptionButton
var hints_toggle: CheckButton
var stop_button: Button
var hand_buttons: Dictionary = {}
var skip_button: Button
var placement_button: Button
var reset_button: Button
var reset_confirmation: VBoxContainer
var _reset_fingerprint := ""
var _context: Dictionary = {}
var _busy := false

func _ready() -> void:
    name = "LessonScreen"
    theme = Design.create()
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    mode_choice = OptionButton.new()
    mode_choice.disabled = true
    mode_choice.fit_to_longest_item = false
    for activity_name in ["Learn notes", "Practice rhythm", "Perform passage", "Perform whole piece"]:
        mode_choice.add_item(activity_name)
    mode_choice.item_selected.connect(func(index: int):
        command_requested.emit({"action": "learn" if index == 0 else "practice" if index == 1 else "perform", "scope": "whole" if index == 3 else "current"}))
    hints_toggle = CheckButton.new()
    hints_toggle.text = "Hints"
    hints_toggle.toggled.connect(func(enabled: bool): command_requested.emit({"action": "hints", "enabled": enabled}))
    stop_button = _button("Stop attempt", func(): command_requested.emit({"action":"stop"}), false, "danger")
    stop_button.tooltip_text = "End the attempt · S"
    stop_button.disabled = true
    var content := UI.stack(14)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(content)
    content.add_child(UI.label("YOUR NEXT STEPS", 14, ACCENT, true))
    content.add_child(UI.title("Lesson path", 32))
    piece_title = UI.title("Choose music to begin", 25)
    content.add_child(piece_title)
    var stages := HBoxContainer.new()
    stages.add_theme_constant_override("separation", 0)
    content.add_child(stages)
    for stage in ["skeleton", "outline", "original"]:
        var label := UI.label("%d. %s" % [stage_labels.size() + 1, stage.capitalize()], 15, MUTED)
        label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        label.tooltip_text = "The current simplification level; available stages depend on this passage."
        label.visible = false
        stages.add_child(label)
        stage_labels[stage] = label
    summary = UI.label("Open a piece to see its lessons.", 15, MUTED)
    content.add_child(summary)
    description = UI.label("", 14, MUTED)
    content.add_child(description)
    columns = BoxContainer.new()
    columns.vertical = get_viewport_rect().size.x < 1280.0
    columns.add_theme_constant_override("separation", 24)
    content.add_child(columns)
    rows = UI.stack(10)
    rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    rows.size_flags_stretch_ratio = 1.15
    columns.add_child(rows)
    var options_panel := UI.card()
    options = options_panel
    options_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    options_panel.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
    columns.add_child(options_panel)
    var path_options := UI.stack(14)
    UI.card_body(options_panel, 18).add_child(path_options)
    path_options.add_child(UI.label("Practice choices", 17, INK, true))
    # FlowContainer inside an expanding, vertically scrolling VBox can
    # calculate a near-zero width for its Label during a resize. The label
    # then wraps to one letter per line and forces the entire activity
    # section (including OptionButton) to become hundreds of pixels tall.
    # These three small controls fit in a single bounded horizontal row.
    var activity := HBoxContainer.new()
    activity.name = "LessonActivityRow"
    activity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    activity.add_theme_constant_override("separation", 14)
    path_options.add_child(activity)
    var activity_caption := UI.label("Activity", 17, MUTED)
    activity_caption.name = "LessonActivityCaption"
    activity_caption.autowrap_mode = TextServer.AUTOWRAP_OFF
    activity_caption.custom_minimum_size.x = 90
    activity_caption.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    activity_caption.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(activity_caption)
    mode_choice.custom_minimum_size = Vector2(210, 44)
    mode_choice.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    mode_choice.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(mode_choice)
    hints_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    hints_toggle.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(hints_toggle)
    var passage_nav := HFlowContainer.new()
    passage_nav.add_theme_constant_override("h_separation", 10)
    path_options.add_child(passage_nav)
    passage_nav.add_child(_button("Previous passage", func():
        command_requested.emit({"action": "previous"})
        practice_requested.emit(), false, "navigation"))
    passage_nav.add_child(_button("Next passage", func():
        command_requested.emit({"action": "next"})
        practice_requested.emit(), false, "navigation"))
    passage_nav.add_child(stop_button)
    var hand_row := HFlowContainer.new()
    hand_row.add_theme_constant_override("separation", 12)
    path_options.add_child(hand_row)
    for hand in ["right", "left", "both"]:
        var button := _button(hand.capitalize() + (" hands" if hand == "both" else " hand"),
            func():
                command_requested.emit({"action": "hand", "hand": hand})
                practice_requested.emit()
        )
        button.configure("choice")
        hand_buttons[hand] = button
        hand_row.add_child(button)
    var course_choices := HFlowContainer.new()
    course_choices.add_theme_constant_override("separation", 8)
    path_options.add_child(course_choices)
    skip_button = _button("Skip this step · no mastery", func(): command_requested.emit({"action": "skip_stage", "reason": "Learner chose to skip this step"}), false, "review")
    skip_button.custom_minimum_size.x = 220
    course_choices.add_child(skip_button)
    placement_button = _button("Try original notes", func(): command_requested.emit({"action": "place_original"}), false, "primary")
    course_choices.add_child(placement_button)
    # The outer scroll owns the whole path. A nested expanding ScrollContainer
    # has zero minimum height inside it, hiding every lesson stage.
    var advanced := _button("Advanced practice controls", func(): advanced_requested.emit(), false, "settings")
    advanced.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    path_options.add_child(advanced)
    # Reset lives in the full Lesson Path drawer, not alongside the three
    # everyday Play / Retry / Listen buttons. It requires a second click.
    reset_button = _button("Reset this song's lesson path…",
        _show_path_reset_confirmation, false, "danger")
    reset_button.disabled = true
    reset_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    reset_button.tooltip_text = "Erase saved mastery, tempo, skipped steps and trouble spots for this song only"
    path_options.add_child(reset_button)
    reset_confirmation = UI.stack(8)
    reset_confirmation.name = "ResetPathConfirmation"
    reset_confirmation.visible = false
    path_options.add_child(reset_confirmation)
    var reset_warning := UI.label(
        "Reset this song to step 1? All saved tempos, mastery, completed notes and skipped steps for this song will be erased. Other songs are unaffected.",
        15, INK)
    reset_warning.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    reset_confirmation.add_child(reset_warning)
    var reset_actions := HFlowContainer.new()
    reset_actions.add_theme_constant_override("h_separation", 10)
    reset_confirmation.add_child(reset_actions)
    reset_actions.add_child(_button("Cancel", _cancel_path_reset, false, "navigation"))
    reset_actions.add_child(_button("Erase this song's progress", _confirm_path_reset,
        false, "danger"))

func _show_path_reset_confirmation() -> void:
    if _busy or not bool(_context.get("loaded", false)):
        return
    _reset_fingerprint = str(_context.get("piece_fingerprint", ""))
    reset_confirmation.visible = not _reset_fingerprint.is_empty()

func _cancel_path_reset() -> void:
    reset_confirmation.visible = false
    _reset_fingerprint = ""

func _confirm_path_reset() -> void:
    var current: String = str(_context.get("piece_fingerprint", ""))
    if _busy or _reset_fingerprint.is_empty() or _reset_fingerprint != current:
        _cancel_path_reset()
        return
    command_requested.emit({"action": "reset_path", "fingerprint": current, "confirm": true})
    _cancel_path_reset()


func present_context(state: Dictionary, busy: bool) -> void:
    _context = state.duplicate(true)
    present_busy(busy)
    if not bool(state.get("loaded",false)):
        mode_choice.disabled = true
        _cancel_path_reset()
        return
    if reset_confirmation.visible and str(state.get("piece_fingerprint","")) != _reset_fingerprint:
        _cancel_path_reset()
    var learning: bool = str(state.get("mode","practice")) == "learn"
    var warmup: bool = bool(state.get("warmup",false))
    var phase: String = str(state.get("phase","ready"))
    mode_choice.select(0 if learning else 2 if str(state.get("mode","")) == "perform" else 1)
    mode_choice.set_item_text(1,"Warm-up practice" if warmup else "Practice rhythm")
    for index in [0,2,3]: mode_choice.set_item_disabled(index,warmup)
    mode_choice.disabled = false
    if str(state.get("mode","")) == "listen": mode_choice.text = "Listen"
    hints_toggle.visible = learning
    hints_toggle.disabled = not learning or phase == "loading"
    hints_toggle.set_pressed_no_signal(bool(state.get("hints_enabled",false)))
    placement_button.visible = bool(state.get("placement_available",false))
    skip_button.disabled = not bool(state.get("skip_available",false))
    for hand in hand_buttons:
        var button: Button = hand_buttons[hand]
        button.set_selected(str(state.get("hand","")) == hand)
        button.disabled = not state.get("hands",[]).has(hand) or str(state.get("hand","")) == hand
    stop_button.disabled = (phase in ["ready","guided_complete","disconnected"]) if learning else not (
        bool(state.get("running",false)) or phase in ["count_in","playing","paused","feedback","recovering","loading","preview_gap"])

func present_busy(busy: bool) -> void:
    _busy = busy
    reset_button.disabled = busy or not bool(_context.get("loaded",false))

func present_error(message: String) -> void:
    summary.text = message

func present_overview(values: Dictionary) -> void:
    var parsed: Dictionary = values.duplicate(true)
    if parsed.is_empty():
        for child in rows.get_children():
            rows.remove_child(child)
            child.queue_free()
        for label in stage_labels.values(): label.visible = false
        summary.text = "Open a piece to see its lessons."
        return
    piece_title.text = str(_context.get("title", "Your music")).replace("_", " ")
    var available: Array = []
    var current: Dictionary = {}
    for step in parsed.get("steps", []):
        if int(step.get("number", -1)) == int(parsed.get("current_step", 0)):
            current = step
            break
    for step in parsed.get("steps", []):
        if step.get("exercise") == current.get("exercise") and step.get("hand") == current.get("hand") \
                and not available.has(str(step.get("level", ""))):
            available.append(str(step.get("level", "")))
    var visible_number := 0
    for level in stage_labels:
        var label: Label = stage_labels[level]
        label.visible = available.has(level)
        if label.visible:
            visible_number += 1
            label.text = "%d. %s" % [visible_number, str(level).capitalize()]
        var selected: bool = str(_context.get("lesson_level", "")) == level
        label.add_theme_color_override("font_color", INK if selected else MUTED)
        var face := Design.bordered_surface(Design.PINE if selected else Design.PANEL_RECESSED, 6, .6 if selected else .25)
        face.border_color = Design.TEAL if selected else Color(Design.SAGE, .3)
        label.add_theme_stylebox_override("normal", face)
    summary.text = "%d of %d stages completed · %d clean performances at your target tempo" % [
        int(parsed.get("completed_steps", 0)), int(parsed.get("total_steps", 0)),
        int(_context.get("clean_runs_required", 3))]
    description.text = "Learn the notes. Bring the hands together. Make it music."
    for child in rows.get_children():
        rows.remove_child(child)
        child.queue_free()
    var trouble: Array = parsed.get("trouble_spots", [])
    if not trouble.is_empty():
        rows.add_child(UI.label("Your trouble spots", 18, INK, true))
        for spot in trouble:
            var stage_key: String = str(spot.get("stage_key", ""))
            var from_beat: float = float(spot.get("start_beat", 0))
            var revisit := _button("Revisit bars %d–%d" % [int(spot.get("first_bar", 1)), int(spot.get("last_bar", 1))],
                func(): command_requested.emit({"action": "revisit_trouble", "stage_key": stage_key, "start_beat": from_beat}))
            revisit.call("configure", "review")
            revisit.tooltip_text = "Find these notes again, then return to rhythm practice"
            rows.add_child(revisit)
    var groups: Dictionary = {}
    for step in parsed.get("steps", []):
        var key := str(step.get("exercise", 0))
        if not groups.has(key):
            groups[key] = {"first": step.get("first_bar", 0), "last": step.get("last_bar", 0),
                "kind": str(step.get("kind", "learn")), "labels": [], "complete": true, "current": false}
        var group: Dictionary = groups[key]
        group["complete"] = bool(group["complete"]) and bool(step.get("completed", false))
        group["current"] = bool(group["current"]) or int(step.get("number", 0)) == int(parsed.get("current_step", 0))
        var detail := "%s: %s" % [str(step.get("hand", "")).capitalize(), str(step.get("level", "")).capitalize()]
        if str(step.get("skip_status", "active")) in ["skipped", "placed"] and not bool(step.get("completed", false)):
            detail += " (%s; not mastered)" % str(step["skip_status"])
        group["labels"].append(detail)
    for key in groups:
        var group: Dictionary = groups[key]
        var chapter := PanelContainer.new()
        var chapter_style := Design.surface(Color(Design.PINE,.32) if bool(group["current"]) else Color.TRANSPARENT, 6)
        chapter_style.set_content_margin_all(14)
        chapter_style.set_border_width(SIDE_LEFT, 3 if bool(group["current"]) else 1)
        chapter_style.border_color = ACCENT if bool(group["current"]) else Color(Design.SAGE,.3)
        chapter.add_theme_stylebox_override("panel", chapter_style)
        var row := UI.stack(4)
        chapter.add_child(row)
        var status := "Completed" if bool(group["complete"]) else "Current passage" if bool(group["current"]) else str(group["kind"]).capitalize()
        row.add_child(UI.label("%s · Measures %d–%d" % [status, int(group["first"]), int(group["last"])], 18,
            ACCENT if bool(group["current"]) else INK, bool(group["current"])))
        var detail: String = " → ".join(group["labels"])
        row.tooltip_text = detail
        if bool(group["current"]):
            row.add_child(UI.label(detail, 14, MUTED))
        rows.add_child(chapter)

func apply_viewport(view_size: Vector2, scale: float) -> void:
    columns.vertical = view_size.x < 1280.0
    columns.move_child(options,0 if columns.vertical else 1)
    for control in find_children("*","Control",true,false):
        if control.has_meta("ui_font_base"):
            control.add_theme_font_size_override("font_size",UI.font_size(int(control.get_meta("ui_font_base")),scale))
    mode_choice.add_theme_font_size_override("font_size",UI.font_size(15,scale))
    mode_choice.custom_minimum_size = Vector2(minf(235.0,maxf(170.0,view_size.x * 0.22)),50.0)
    hints_toggle.add_theme_font_size_override("font_size",UI.font_size(15,scale))

func _button(caption: String, action: Callable, primary := false, role := "") -> Button:
    var button := UI.button(caption,role if not role.is_empty() else "primary" if primary else "secondary")
    button.pressed.connect(action)
    return button
