extends PanelContainer
# Owns score presentation, native view, hand stages and fixed overlays.
const Design := preload("res://practice_theme.gd")
const UI := preload("res://ui_factory.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL
const GameStage := preload("res://game_stage.gd")
const NativeNotation := preload("res://notation/native/view.gd")
const GamePhaseCue := preload("res://game_phase_cue.gd")
const GameImpactCallout := preload("res://game_impact_callout.gd")
const GameCountIn := preload("res://game_countin.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")
const PracticeStepSelector := preload("res://practice_step_selector.gd")
signal navigation_requested(destination: String)
signal score_retry_requested
signal command_requested(command: Dictionary)
var practice_stage_bar: HFlowContainer
var practice_stage_labels: Dictionary = {}
var presented_hand_stages: Array = []
var fingering_status_label: Label
var score_margin_box: MarginContainer
var score_frame: Control
var renderer: Control
var feedback: Control
var effects: Control
var phase_cue: Control
var impact_callout: Control
var count_in: Control
var keyboard: Control
var steps: PracticeStepSelector
var score_status_panel: CenterContainer
var score_status_label: Label
var score_browse_button: Button
var score_retry_button: Button
var practice_playback_banner: Label
var practice_note_feedback_panel: PanelContainer
var practice_note_feedback_label: Label
var _state: Dictionary = {}
var _view_size := Vector2(800,600)

func _ready() -> void:
    name = "PracticeScoreStage"
    practice_stage_bar = HFlowContainer.new()
    practice_stage_bar.add_theme_constant_override("h_separation", 10)
    practice_stage_bar.add_theme_constant_override("v_separation", 6)
    practice_stage_bar.visible = false
    for hand in ["right", "left", "both"]:
        var stage_label := UI.label("", 12, MUTED)
        stage_label.custom_minimum_size = Vector2(140, 26)
        stage_label.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
        stage_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
        var stage_style := Design.bordered_surface(Design.PANEL_RECESSED, Design.RADIUS_INPUT, .25)
        stage_style.set_content_margin_all(8)
        stage_label.add_theme_stylebox_override("normal", stage_style)
        practice_stage_bar.add_child(stage_label)
        practice_stage_labels[hand] = stage_label
    practice_playback_banner = UI.label("", 18, Design.AMBER, true)
    practice_playback_banner.visible = false
    practice_playback_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_playback_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
    var score_panel: PanelContainer = self
    # One continuous performance stage, not another grey website card.
    score_panel.add_theme_stylebox_override("panel", Design.stage_surface())
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    var score_margin := UI.card_body(score_panel, 10)
    score_margin_box = score_margin
    var score_region := VBoxContainer.new()
    score_region.add_theme_constant_override("separation", 8)
    score_margin.add_child(score_region)
    # Reserve a stable header row so navigation clears high notes and staves.
    var score_header := HBoxContainer.new()
    score_header.alignment = BoxContainer.ALIGNMENT_END
    score_header.add_theme_constant_override("separation", 8)
    score_region.add_child(score_header)
    practice_stage_bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_header.add_child(practice_stage_bar)
    fingering_status_label = UI.label("",12,Design.SECONDARY_INK)
    fingering_status_label.visible = false
    fingering_status_label.clip_text = true
    fingering_status_label.custom_minimum_size.x = 180
    fingering_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    # Reserve a separate caption row. Fingering warnings must not steal
    # width from the hand ribbon and make it reflow during a transport.
    var fingering_slot := Control.new()
    fingering_slot.name = "FingeringStatusCaption"
    fingering_slot.custom_minimum_size.y = 18.0
    fingering_slot.clip_contents = true
    score_region.add_child(fingering_slot)
    fingering_slot.add_child(fingering_status_label)
    fingering_status_label.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    fingering_status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    fingering_status_label.max_lines_visible = 1
    steps = PracticeStepSelector.new()
    score_header.add_child(steps)
    steps.step_requested.connect(func(number: int):
        command_requested.emit({"action":"select_step","number":number}))
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 210)
    score_region.add_child(score_area)
    score_frame = score_area
    score_frame.clip_contents = true
    effects = GameStage.new()
    effects.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(effects)
    renderer = NativeNotation.new()
    renderer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    renderer.visible = false
    score_frame.add_child(renderer)
    effects.surface_visible = false
    effects.z_index = 1
    feedback = preload("res://native_score_feedback.gd").new()
    feedback.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(feedback)
    if not renderer.set_density_from_env():
        push_warning("Native score density: " + str(renderer.notice))
    # Score status must live inside the score panel: feedback_label is replaced
    # by regular state polling and cannot hold engraving errors reliably.
    score_status_panel = CenterContainer.new()
    score_status_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_area.add_child(score_status_panel)
    var status_content := UI.stack(12)
    status_content.custom_minimum_size = Vector2(280, 85)
    status_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_status_panel.add_child(status_content)
    score_status_label = UI.label("Choose a piece from your library", 18, Design.SCORE_INK)
    score_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    score_status_label.clip_text = true
    status_content.add_child(score_status_label)
    score_browse_button = _button("Choose music", func(): navigation_requested.emit("library"), true)
    score_browse_button.visible = true
    status_content.add_child(score_browse_button)
    score_retry_button = _button("Retry score", func(): score_retry_requested.emit(), false, "review")
    score_retry_button.visible = false
    status_content.add_child(score_retry_button)
    # A compact, unobtrusive cue. A huge centred numeral hid the movement.
    phase_cue = GamePhaseCue.new()
    phase_cue.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    phase_cue.offset_left = 178.0
    phase_cue.offset_right = -18.0
    phase_cue.offset_top = 46.0
    phase_cue.offset_bottom = 88.0
    score_frame.add_child(phase_cue)
    # Short earned-judgment coaching, placed below the notes on the right.
    # No preview note may create one of these success/correction labels.
    impact_callout = GameImpactCallout.new()
    # Native reactions stay on exact noteheads. The legacy coaching card
    # can cover low staff ink when the contextual keyboard reduces height.
    impact_callout.visible = false
    impact_callout.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    impact_callout.offset_left = -264.0
    impact_callout.offset_right = -14.0
    impact_callout.offset_top = -116.0
    impact_callout.offset_bottom = -54.0
    score_frame.add_child(impact_callout)
    count_in = GameCountIn.new()
    count_in.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    count_in.position = Vector2(22, 46)
    count_in.size = Vector2(142, 38)
    count_in.visible = false
    score_frame.add_child(count_in)
    # A visible retry notice must not consume vertical space or force the
    # bottom transport buttons off smaller laptop screens.
    practice_playback_banner.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    practice_playback_banner.offset_left = 20.0
    practice_playback_banner.offset_right = -20.0
    practice_playback_banner.offset_top = 54.0
    practice_playback_banner.offset_bottom = 112.0
    score_frame.add_child(practice_playback_banner)
    # A stationary feedback badge stays visible even after a missed note
    # scrolls left out of view. It never covers the playing cursor.
    practice_note_feedback_panel = PanelContainer.new()
    var feedback_style := Design.surface(Color("#27362F"), 9)
    feedback_style.set_border_width_all(2)
    feedback_style.border_color = Color("#ED665F")
    feedback_style.set_content_margin_all(9)
    practice_note_feedback_panel.add_theme_stylebox_override("panel", feedback_style)
    practice_note_feedback_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_note_feedback_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
    practice_note_feedback_panel.offset_left = -330.0
    practice_note_feedback_panel.offset_right = -12.0
    practice_note_feedback_panel.offset_top = 10.0
    practice_note_feedback_panel.offset_bottom = 60.0
    practice_note_feedback_panel.visible = false
    score_frame.add_child(practice_note_feedback_panel)
    practice_note_feedback_label = UI.label("", 20, Color("#FF827A"), true)
    practice_note_feedback_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_note_feedback_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    practice_note_feedback_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    practice_note_feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_note_feedback_panel.add_child(practice_note_feedback_label)
    keyboard = HintKeyboard.new()
    score_region.add_child(keyboard)


func present(state: Dictionary, busy: bool) -> void:
    _state = state.duplicate(true)
    effects.present(state)
    feedback.present(state)
    phase_cue.present(state)
    steps.present_context(state,busy)
    _update_hand_stages(state)
    # Mapped feedback belongs on actual native noteheads; never overlay it.
    practice_note_feedback_panel.visible = false
    keyboard.set_key_fifths(int(state.get("key_fifths", 0)))
    if str(state.get("mode","practice")) == "learn":
        keyboard.update_state(state.get("teaching",{}) if state.get("teaching") is Dictionary else {})
    else:
        keyboard.update_live(state.get("midi_next_pitches",[]),state.get("midi_held_pitches",[]),state.get("midi_visual_events",[]),
            not str(state.get("device","")).is_empty() and str(state.get("mode","")) in ["practice","perform"])

func pulse_hand_unlock() -> void:
    call_deferred("_pulse_hand_stage")

func apply_viewport(view_size: Vector2, scale: float, compact: bool) -> void:
    _view_size = view_size
    steps.apply_viewport(view_size,scale)
    keyboard.set_ui_scale(scale)
    fingering_status_label.get_parent().custom_minimum_size.y = ceilf(
        fingering_status_label.get_theme_font("font").get_height(fingering_status_label.get_theme_font_size("font_size")))
    # Update widths even if the hand state itself has not changed.
    presented_hand_stages.clear()
    _update_hand_stages(_state)
    score_frame.custom_minimum_size.y = 135.0
    for side in ["left","right","top","bottom"]:
        score_margin_box.add_theme_constant_override("margin_" + side,1 if compact else 6)
    practice_playback_banner.add_theme_font_size_override("font_size",UI.font_size(17,scale))
    practice_note_feedback_label.add_theme_font_size_override("font_size",UI.font_size(18,scale))
    practice_note_feedback_panel.offset_left = -minf(330.0,maxf(180.0,score_frame.size.x - 24.0))

func _button(caption: String, action: Callable, primary := false, role := "") -> Button:
    var button := UI.button(caption,role if not role.is_empty() else "primary" if primary else "secondary")
    button.pressed.connect(action)
    return button

func _update_hand_stages(state: Dictionary) -> void:
    var stages: Array = state.get("hand_stages", [])
    # Transport changes must not add/remove a layout row: doing so changes
    # the score's zoom and moves its notes at Start and Pause.
    practice_stage_bar.visible = not stages.is_empty()
    if stages == presented_hand_stages:
        return
    presented_hand_stages = stages.duplicate(true)
    var by_hand: Dictionary = {}
    for stage in stages:
        by_hand[str(stage.get("hand", ""))] = stage
    for hand in practice_stage_labels:
        var label: Label = practice_stage_labels[hand]
        label.visible = by_hand.has(hand)
        if not label.visible:
            continue
        var stage: Dictionary = by_hand[hand]
        var active: bool = bool(stage.get("active", false))
        var complete: bool = bool(stage.get("complete", false))
        var locked: bool = bool(stage.get("locked", false))
        var word: String = "Both hands" if hand == "both" else str(hand).capitalize() + " hand"
        label.autowrap_mode = TextServer.AUTOWRAP_OFF
        label.clip_text = true
        label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
        label.text = ("✓ " if complete else "● " if active else "○ ") + word + (" · locked" if locked else "")
        label.tooltip_text = "Completed" if complete else "Active hand" if active else "Locked" if locked else "Next hand"
        label.custom_minimum_size = Vector2(102 if _view_size.x < 1150.0 else 122, 24)
        label.add_theme_color_override("font_color",
            Color("#79DAAD") if complete else INK if active else MUTED)
        # Read as a three-step instrument runway, not three separate
        # web-form cards. The active hand has a bright lower edge; completed
        # hands retain a quieter mint trace, and locked ones recede.
        var stage_color := Color(Design.PINE, .45) if active else Color.TRANSPARENT
        var style := Design.surface(stage_color, 5)
        style.set_content_margin_all(5)
        style.set_border_width_all(0)
        style.set_border_width(SIDE_BOTTOM, 1)
        style.border_color = Design.TEAL if active else Color(Design.SAGE, .3)
        label.add_theme_stylebox_override("normal", style)


# Animate the newly active hand without extra buttons or a separate
# modal. Deferred until the backend-driven hand-stage labels are updated.
func _pulse_hand_stage() -> void:
    var hand: String = str(_state.get("hand", ""))
    if not practice_stage_labels.has(hand):
        return
    var label: Label = practice_stage_labels[hand]
    if not label.visible:
        return
    label.modulate = Color("#A6FFE0")
    var transition := create_tween()
    transition.tween_property(label, "modulate", Color.WHITE, .68) \
        .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)



func present_fingering(summary: Variant, placement_issues: int, fingering_save_error: String) -> void:
    if fingering_status_label == null:
        return
    if not summary is Dictionary:
        summary = {}
    var status: String = str(summary.get("status",""))
    var unknown: int = int(summary.get("unknown",0))
    var review: int = int(summary.get("review",0))
    var unavailable: bool = status in ["unavailable","failed","error"]
    var detail: String = str(summary.get("error",""))
    var issues := PackedStringArray()
    for issue in summary.get("issues",[]):
        issues.append(str(issue))
    if not issues.is_empty():
        detail += ("\n" if not detail.is_empty() else "")+"\n".join(issues)
    fingering_status_label.visible = unavailable or unknown > 0 or review > 0 or placement_issues > 0 or not fingering_save_error.is_empty()
    if not fingering_save_error.is_empty():
        fingering_status_label.text = "Fingering not saved"
        detail = fingering_save_error
    elif unavailable:
        fingering_status_label.text = "Automatic fingering unavailable"
    elif unknown > 0:
        fingering_status_label.text = "%d unknown finger%s" % [unknown,"" if unknown == 1 else "s"]
        if detail.is_empty():
            detail = "Some source notes have no reliable finger assignment."
    elif review > 0:
        fingering_status_label.text = "Check %d fingering%s" % [review,"" if review == 1 else "s"]
    elif placement_issues > 0:
        fingering_status_label.text = "%d fingering%s need%s space" % [placement_issues,"" if placement_issues == 1 else "s","s" if placement_issues == 1 else ""]
    else:
        fingering_status_label.text = ""
    if placement_issues > 0:
        if unknown > 0 or review > 0 or unavailable or not fingering_save_error.is_empty():
            fingering_status_label.text += " · %d need%s space" % [placement_issues,"s" if placement_issues == 1 else ""]
        detail += ("\n" if not detail.is_empty() else "")+ \
            "Some fingerings cannot fit beside their notes at this staff size. Enlarge the practice window to give the score more space."
    fingering_status_label.tooltip_text = (detail+"\n" if not detail.is_empty() else "")+ \
        "Right-click any attack note, or tap a finger number, to correct it. Unknown notes can also be edited."



func present_score_status(loaded: bool, ready: bool, score_error: String) -> void:
    if score_status_panel == null:
        return
    score_status_panel.visible = not ready
    # Phase guidance already has captions below the score and count-in
    # lights. An opaque capsule must never cover engraved noteheads.
    phase_cue.visible = score_status_panel.visible
    if not score_status_panel.visible:
        return
    if not score_error.is_empty():
        score_status_label.text = "Unable to display sheet music:\n" + score_error
        score_retry_button.visible = true
        score_browse_button.visible = false
    elif loaded:
        score_status_label.text = "Preparing sheet music…"
        score_retry_button.visible = false
        score_browse_button.visible = false
    else:
        score_status_label.text = "Choose a piece to begin"
        score_retry_button.visible = false
        score_browse_button.visible = true

