extends PanelContainer
# Owns score presentation, native view, hand stages and fixed overlays.
const Design := preload("res://practice_theme.gd")
const UI := preload("res://ui_factory.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL
const GameStage := preload("res://game_stage.gd")
const ScoreViewBase := preload("res://notation/shared/view_base.gd")
const NativeNotation := preload("res://notation/native/view.gd")
const GlowField := preload("res://mint_glow_field.gd")
const GamePhaseCue := preload("res://game_phase_cue.gd")
const GameCountIn := preload("res://game_countin.gd")
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const StepTimeline := preload("res://score_step_timeline.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")
signal navigation_requested(destination: String)
signal score_retry_requested
signal command_requested(command: Dictionary)
var practice_stage_labels: Dictionary = {}
var score_margin_box: MarginContainer
var score_frame: Control
var renderer: Control
var playhead_glow: ColorRect
var runway_steps: Control
var feedback: Node # note-status ledger; strips paint its ink
var effects: Control
var phase_cue: Control
var hand_cue_panel: PanelContainer
var hand_cue_label: Label
var _hand_cue_tween: Tween
var _hand_cue_identity := ""
var _hand_cue_previous_phase := ""
var count_in: Control
var keyboard: Control
var keyboard_slot: Control
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

func _clear_progress_rail(child: Node) -> void:
    var layout: Variant = child.get("layout")
    if layout is Object and "bottom_clearance" in layout:
        layout.bottom_clearance = ScoreViewBase.PROGRESS_RAIL_CLEARANCE

func _ready() -> void:
    name = "PracticeScoreStage"
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
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 210)
    score_region.add_child(score_area)
    score_frame = score_area
    # The stage's progress rail runs along the bottom of the score frame.
    # Every notation view placed here (this stage's, a pre-engraved next
    # stage, a promoted replacement) keeps its lowest ledger notes and their
    # fingerings above the rail's band, before it lays out a score.
    score_frame.child_entered_tree.connect(_clear_progress_rail)
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
    renderer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    # The empty moving staff/playhead exists from application startup,
    # before the first score model or retained note buffer is ready.
    renderer.visible = true
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
    count_in = GameCountIn.new()
    count_in.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    # Four large beat pulses sit above the staff, without a modal overlay.
    score_frame.resized.connect(_place_count_in)
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
    # The hint keyboard has a permanent slot of constant height, so showing
    # or hiding it never resizes the score (the staff must not jump).
    keyboard_slot = Control.new()
    keyboard_slot.name = "HintKeyboardSlot"
    keyboard_slot.mouse_filter = Control.MOUSE_FILTER_IGNORE
    keyboard_slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_region.add_child(keyboard_slot)
    keyboard = HintKeyboard.new()
    keyboard.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    keyboard_slot.add_child(keyboard)
    keyboard_slot.custom_minimum_size.y = keyboard.custom_minimum_size.y


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
    # Read the online queue in place; never copy it on the frame path.
    var current_start: float = renderer.first_strip_origin_after(
        global_visual-.001-_first_attack_offset)+_first_attack_offset
    runway_steps.present(state,global_visual,current_start,
        next_start,next_label,next_density,global_visual)

func present(state: Dictionary, busy: bool) -> void:
    _state = state.duplicate(true)
    _present_hand_cue(state)
    effects.present(state)
    feedback.present(state)
    phase_cue.present(state)
    # Mapped feedback belongs on actual native noteheads; never overlay it.
    practice_note_feedback_panel.visible = false
    keyboard.set_key_fifths(int(state.get("key_fifths", 0)))
    # Python decides whether the keyboard shows (screen.keyboard: the
    # wrong-note hint in Free, otherwise hidden).
    var screen: Dictionary = state.get("screen",{}) if state.get("screen") is Dictionary else {}
    var teaching: Dictionary = state.get("teaching",{}) if state.get("teaching") is Dictionary else {}
    teaching = teaching.duplicate()
    teaching["hint_visible"] = str(screen.get("keyboard","hidden")) == "hint"
    keyboard.update_state(teaching)

var _flow_message_id := -1

func _present_flow_message(flow: Dictionary) -> void:
    # One short message per step/tempo change (practice flow), shown once.
    var id := int(flow.get("message_id", 0))
    var text := str(flow.get("message", ""))
    if id == _flow_message_id:
        return
    _flow_message_id = id
    if text.is_empty():
        return
    hand_cue_label.text = text
    if _hand_cue_tween != null and _hand_cue_tween.is_running():
        _hand_cue_tween.kill()
    hand_cue_panel.visible = true
    hand_cue_panel.modulate.a = 0.0
    _hand_cue_tween = create_tween()
    _hand_cue_tween.tween_property(hand_cue_panel,"modulate:a",1.0,.18)
    _hand_cue_tween.tween_interval(1.4)
    _hand_cue_tween.tween_property(hand_cue_panel,"modulate:a",0.0,.42)
    _hand_cue_tween.tween_callback(func(): hand_cue_panel.visible = false)

func _present_hand_cue(state: Dictionary) -> void:
    if state.get("flow") is Dictionary and bool(state.get("loaded",false)):
        _present_flow_message(state["flow"])
        return
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


func apply_viewport(view_size: Vector2, scale: float, compact: bool) -> void:
    _view_size = view_size
    keyboard.set_ui_scale(scale)
    keyboard_slot.custom_minimum_size.y = keyboard.custom_minimum_size.y
    score_frame.custom_minimum_size.y = 135.0
    for side in ["left","right","top","bottom"]:
        score_margin_box.add_theme_constant_override("margin_" + side,1 if compact else 6)
    practice_playback_banner.add_theme_font_size_override("font_size",UI.font_size(17,scale))
    practice_note_feedback_label.add_theme_font_size_override("font_size",UI.font_size(18,scale))
    practice_note_feedback_panel.offset_left = -minf(330.0,maxf(180.0,score_frame.size.x - 24.0))
    _place_count_in()

func _place_count_in() -> void:
    # The count-in sits in the empty run-up left of the playhead, above the
    # staff; it must never cover the first notes or their stems.
    var playhead_x: float = score_frame.size.x*PLAYHEAD_FRACTION
    count_in.position = Vector2(24.0, 8.0)
    count_in.size = Vector2(maxf(160.0, playhead_x-24.0-28.0), 72.0)

func _button(caption: String, action: Callable, primary := false, role := "") -> Button:
    var button := UI.button(caption,role if not role.is_empty() else "primary" if primary else "secondary")
    button.pressed.connect(action)
    return button

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
