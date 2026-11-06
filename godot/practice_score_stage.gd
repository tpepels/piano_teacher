extends PanelContainer
# Owns score presentation, native view, hand stages and fixed overlays.
const Design := preload("res://practice_theme.gd")
const UI := preload("res://ui_factory.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL
const GameStage := preload("res://game_stage.gd")
const NativeNotation := preload("res://notation/native/view.gd")
const GlowField := preload("res://mint_glow_field.gd")
const GamePhaseCue := preload("res://game_phase_cue.gd")
const GameImpactCallout := preload("res://game_impact_callout.gd")
const GameCountIn := preload("res://game_countin.gd")
const StepTimeline := preload("res://score_step_timeline.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")
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
var playhead_glow: ColorRect
var runway_steps: Control
var feedback: Control
var effects: Control
var phase_cue: Control
var hand_cue_panel: PanelContainer
var hand_cue_label: Label
var _hand_cue_tween: Tween
var _hand_cue_identity := ""
var _hand_cue_previous_phase := ""
var impact_callout: Control
var count_in: Control
var keyboard: Control
var score_status_panel: CenterContainer
var score_status_label: Label
var score_browse_button: Button
var score_retry_button: Button
var practice_playback_banner: Label
var practice_note_feedback_panel: PanelContainer
var practice_note_feedback_label: Label
var _state: Dictionary = {}
var _view_size := Vector2(800,600)
var _marker_renderer
var _marker_revision := -999999
var _marker_hand := ""
var _first_attack_offset := INF

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
    # Practice is one continuous score canvas, without a framed card.
    var seamless_panel := StyleBoxFlat.new()
    seamless_panel.bg_color = Color.TRANSPARENT
    seamless_panel.set_content_margin_all(0)
    score_panel.add_theme_stylebox_override("panel",seamless_panel)
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    var score_margin := UI.card_body(score_panel, 10)
    score_margin_box = score_margin
    var score_region := VBoxContainer.new()
    score_region.add_theme_constant_override("separation", 8)
    score_margin.add_child(score_region)
    # The stage markers are reparented into More by PracticeScreen.
    # Do not leave an empty score header behind after that move.
    score_region.add_child(practice_stage_bar)
    fingering_status_label = UI.label("",12,Design.SECONDARY_INK)
    fingering_status_label.visible = false
    fingering_status_label.clip_text = true
    fingering_status_label.custom_minimum_size.x = 180
    fingering_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    # PracticeScreen moves this label into its More popup. A permanent
    # warning/caption slot takes space from the engraving even when hidden.
    score_region.add_child(fingering_status_label)
    fingering_status_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    fingering_status_label.max_lines_visible = 1
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 210)
    score_region.add_child(score_area)
    score_frame = score_area
    score_frame.clip_contents = true
    # Background is owned by the full Practice page. Keeping another
    # opaque backdrop inside the score creates the visible hard-edged box.
    effects = GameStage.new()
    effects.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(effects)
    playhead_glow = GlowField.new()
    playhead_glow.name = "PlayheadBloom"
    playhead_glow.configure(0,1.35,Color("#54F9B7"))
    playhead_glow.visible = false
    score_frame.add_child(playhead_glow)
    renderer = NativeNotation.new()
    renderer.external_backdrop = true
    renderer.compact_inactive_staff = true
    renderer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    renderer.visible = false
    score_frame.add_child(renderer)

    runway_steps = StepTimeline.new()
    runway_steps.mouse_filter = Control.MOUSE_FILTER_IGNORE
    runway_steps.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    runway_steps.custom_minimum_size.y = 30
    runway_steps.offset_left = 0
    runway_steps.offset_right = 0
    runway_steps.offset_top = 2
    runway_steps.offset_bottom = 32
    runway_steps.z_index = 8
    score_frame.add_child(runway_steps)
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
    # Preserve native-engraving failure details rather than clipping them.
    score_status_label.clip_text = false
    score_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
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
    # One unobtrusive, transient hand cue on passage/hand change and retries.
    # Do not allocate a persistent header row or overlay any notation ink.
    hand_cue_panel = PanelContainer.new()
    hand_cue_panel.name = "HandCue"
    hand_cue_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hand_cue_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    hand_cue_panel.position = Vector2(24, 46)
    hand_cue_panel.custom_minimum_size = Vector2(124, 32)
    var hand_style := Design.bordered_surface(Color("#174239", .91), 16, .34)
    hand_style.border_color = Color(Design.HIGHLIGHT, .36)
    hand_style.set_content_margin_all(9)
    hand_cue_panel.add_theme_stylebox_override("panel",hand_style)
    hand_cue_label = UI.label("", 14, Design.HIGHLIGHT)
    hand_cue_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    hand_cue_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    hand_cue_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    hand_cue_panel.add_child(hand_cue_label)
    hand_cue_panel.visible = false
    score_frame.add_child(hand_cue_panel)
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
    # Four large beat pulses sit above the staff, without a modal overlay.
    count_in.position = Vector2(24, 24)
    count_in.size = Vector2(270, 72)
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


func present_playhead_glow(score_ready: bool) -> void:
    if playhead_glow == null or renderer == null or not is_instance_valid(renderer):
        return
    var display: bool = score_ready and renderer.visible and renderer.native_ready
    playhead_glow.visible = display
    if not display:
        return
    var line: Rect2 = renderer.playhead_region()
    var desired_position := Vector2(line.position.x-94.0,line.position.y-38.0)
    var desired_size := Vector2(188.0,line.size.y+76.0)
    if playhead_glow.position != desired_position:
        playhead_glow.position = desired_position
    if playhead_glow.size != desired_size:
        playhead_glow.size = desired_size


func present_runway_steps(state: Dictionary, global_visual: float,
        next_start: float = INF, next_label: String = "",
        next_density: float = NAN) -> void:
    if runway_steps == null or renderer == null:
        return
    runway_steps.set_density(renderer.timeline.pixels_per_beat)
    # The section introduction follows the first engraved ATTACK, not the
    # barline of a measure which may still contain a written rest.
    # Recompute only after a renderer/revision/active-hand change.
    var hand: String = str(state.get("hand","both"))
    if (_marker_renderer != renderer or
            _marker_revision != renderer.timeline.revision or
            _marker_hand != hand):
        _marker_renderer = renderer
        _marker_revision = renderer.timeline.revision
        _marker_hand = hand
        var model: Dictionary = renderer.timeline.model if renderer.timeline.model is Dictionary else {}
        _first_attack_offset = StepTimeline.first_playable_beat(model,hand)
    # A step title is attached to an already reserved source copy, never
    # positioned from a READY-only camera or backend scroll offset.
    var current_start := INF
    for item in renderer.stream_passes:
        var onset: float = float(item["world_origin"])+_first_attack_offset
        if onset >= global_visual-.001:
            current_start = minf(current_start,onset)
    runway_steps.present(state,global_visual,current_start,
        next_start,next_label,next_density,global_visual)

func present(state: Dictionary, busy: bool) -> void:
    _state = state.duplicate(true)
    _present_hand_cue(state)
    effects.present(state)
    feedback.present(state)
    phase_cue.present(state)
    _update_hand_stages(state)
    # Mapped feedback belongs on actual native noteheads; never overlay it.
    practice_note_feedback_panel.visible = false
    keyboard.set_key_fifths(int(state.get("key_fifths", 0)))
    if str(state.get("mode","practice")) == "learn":
        keyboard.update_state(state.get("teaching",{}) if state.get("teaching") is Dictionary else {})
    else:
        keyboard.update_live(state.get("midi_next_pitches",[]),state.get("midi_held_pitches",[]),state.get("midi_visual_events",[]),
            not str(state.get("device","")).is_empty() and str(state.get("mode","")) in ["practice","perform"])

func _present_hand_cue(state: Dictionary) -> void:
    if not bool(state.get("loaded",false)):
        _hand_cue_identity = ""
        _hand_cue_previous_phase = ""
        if _hand_cue_tween != null and _hand_cue_tween.is_running():
            _hand_cue_tween.kill()
        hand_cue_panel.visible = false
        return
    var hand: String = str(state.get("hand","both"))
    if hand not in ["right","left","both"]:
        return
    var identity: String = "%s|%s|%s|%s|%s" % [
        str(state.get("piece_fingerprint","")),
        str(state.get("lesson_step",-1)),hand,
        str(state.get("first_bar",-1)),str(state.get("stage_label",""))]
    var phase: String = str(state.get("phase",""))
    var fresh_count_in: bool = phase == "count_in" and _hand_cue_previous_phase != "count_in"
    _hand_cue_previous_phase = phase
    if identity == _hand_cue_identity and not fresh_count_in:
        return
    _hand_cue_identity = identity
    hand_cue_label.text = ("Right hand" if hand == "right"
        else "Left hand" if hand == "left" else "Both hands")
    if _hand_cue_tween != null and _hand_cue_tween.is_running():
        _hand_cue_tween.kill()
    hand_cue_panel.visible = true
    hand_cue_panel.modulate.a = 0.0
    _hand_cue_tween = create_tween()
    _hand_cue_tween.tween_property(hand_cue_panel,"modulate:a",1.0,.18)
    _hand_cue_tween.tween_interval(1.35)
    _hand_cue_tween.tween_property(hand_cue_panel,"modulate:a",0.0,.42)
    _hand_cue_tween.tween_callback(func(): hand_cue_panel.visible = false)


func pulse_hand_unlock() -> void:
    call_deferred("_pulse_hand_stage")

func apply_viewport(view_size: Vector2, scale: float, compact: bool) -> void:
    _view_size = view_size
    keyboard.set_ui_scale(scale)
    fingering_status_label.custom_minimum_size.y = ceilf(
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
            Design.NIGHT if active else Design.MINT if complete else MUTED)
        var stage_color := Design.MINT if active else Design.FOREST if complete else Design.PANEL_RECESSED
        var style := Design.bordered_surface(stage_color, Design.RADIUS_INPUT,.4)
        style.set_content_margin_all(5)
        style.border_color = Design.HIGHLIGHT if active else Color(Design.MINT,.4) if complete else Color(Design.BORDER,.3)
        style.shadow_color = Color(Design.MINT,.18)
        style.shadow_size = 8 if active else 0
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



func present_score_status(status: Dictionary) -> void:
    if score_status_panel == null:
        return
    score_status_panel.visible = bool(status.get("visible",true))
    # One session owns loading phase, readiness and recovery controls.
    phase_cue.visible = score_status_panel.visible
    score_retry_button.visible = score_status_panel.visible and \
        bool(status.get("retry_visible",false))
    score_browse_button.visible = score_status_panel.visible and \
        bool(status.get("browse_visible",false))
    if not score_status_panel.visible:
        return
    score_status_label.text = str(status.get("text","Preparing sheet music…"))
    score_status_label.tooltip_text = score_status_label.text
