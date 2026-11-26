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
const GameCountIn := preload("res://game_countin.gd")
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const HintKeyboard := preload("res://hint_keyboard.gd")
const HeldNotesStaff := preload("res://held_notes_staff.gd")
signal navigation_requested(destination: String)
signal score_retry_requested
signal command_requested(command: Dictionary)
var practice_stage_labels: Dictionary = {}
var score_margin_box: MarginContainer
var score_frame: Control
var renderer: Control
var playhead_glow: ColorRect
var feedback: Node # note-status ledger; strips paint its ink
var effects: Control
var count_in: Control
var keyboard: Control
var held_staff: Control
var score_status_panel: CenterContainer
var score_status_label: Label
var score_browse_button: Button
var score_retry_button: Button
var practice_playback_banner: Label
var notification_row: Control
var _notice_tween: Tween
var _notice_text := ""
var _view_size := Vector2(800,600)

func _clear_progress_rail(child: Node) -> void:
    var layout: Variant = child.get("layout")
    if layout is Object and "bottom_clearance" in layout:
        layout.bottom_clearance = ScoreViewBase.PROGRESS_RAIL_CLEARANCE

func _ready() -> void:
    name = "PracticeScoreStage"
    practice_playback_banner = UI.label("", 15, Design.HIGHLIGHT)
    practice_playback_banner.visible = false
    practice_playback_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_playback_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_playback_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
    # Text belongs to the score, not a bordered notification card.
    practice_playback_banner.add_theme_color_override("font_shadow_color",Color(Design.NIGHT,.65))
    practice_playback_banner.add_theme_constant_override("shadow_offset_y",1)
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
    # Keep a slim, invariant text lane immediately above the playhead.
    # It is not part of the notation viewport or the count-in's drawing area.
    score_region.add_theme_constant_override("separation",2)
    notification_row = Control.new()
    notification_row.custom_minimum_size.y = 34.0
    notification_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
    notification_row.clip_contents = true
    score_region.add_child(notification_row)
    notification_row.add_child(practice_playback_banner)
    practice_playback_banner.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    practice_playback_banner.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM
    notification_row.resized.connect(_place_notice)
    _place_notice()
    practice_playback_banner.clip_text = true
    practice_playback_banner.max_lines_visible = 2
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
    playhead_glow.configure(0,1.0,Color("#54F9B7"))
    playhead_glow.visible = false
    score_frame.add_child(playhead_glow)
    renderer = NativeNotation.new()
    renderer.external_backdrop = true
    renderer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    # The empty moving staff/playhead exists from application startup,
    # before the first score model or retained note buffer is ready.
    renderer.visible = true
    score_frame.add_child(renderer)

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
    count_in = GameCountIn.new()
    count_in.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    # Four large beat pulses sit above the staff, without a modal overlay.
    score_frame.resized.connect(_place_count_in)
    count_in.visible = false
    score_frame.add_child(count_in)
    # The hint keyboard and the held-notes staff sit at either end of the
    # transport row (practice_chrome places them), not under the score.
    keyboard = HintKeyboard.new()
    held_staff = HeldNotesStaff.new()
    held_staff.visible = false


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


func present(state: Dictionary, busy: bool) -> void:
    effects.present(state)
    feedback.present(state)
    keyboard.set_key_fifths(int(state.get("key_fifths", 0)))
    # Python decides whether the keyboard shows (screen.keyboard: the
    # wrong-note hint in Free, otherwise hidden).
    var screen: Dictionary = state.get("screen",{}) if state.get("screen") is Dictionary else {}
    var teaching: Dictionary = state.get("teaching",{}) if state.get("teaching") is Dictionary else {}
    teaching = teaching.duplicate()
    teaching["hint_visible"] = str(screen.get("keyboard","hidden")) == "hint"
    keyboard.update_state(teaching)
    held_staff.visible = bool(state.get("loaded", false))
    held_staff.present(state.get("midi_held_pitches", []) if state.get("midi_held_pitches") is Array else [],
        int(state.get("key_fifths", 0)), _loaded_glyphs())

# The keyboard and held-notes staff are placed by the practice chrome; free
# them here when no row adopted them (a stage built on its own).
func _notification(what: int) -> void:
    if what == NOTIFICATION_PREDELETE:
        for node in [keyboard, held_staff]:
            if is_instance_valid(node) and node.get_parent() == null:
                node.free()
var _glyph_atlas = null

# The glyph atlas of whichever notation view has loaded the score's font
# (views are replaced as stages are pre-engraved and promoted).
func _loaded_glyphs():
    if _glyph_atlas != null and _glyph_atlas.ready():
        return _glyph_atlas
    for view in score_frame.get_children():
        var atlas = view.get("glyphs") if view.has_method("set_density_from_env") else null
        if atlas != null and atlas.ready():
            _glyph_atlas = atlas
            return atlas
    return null

func apply_viewport(view_size: Vector2, scale: float, compact: bool) -> void:
    _view_size = view_size
    keyboard.set_ui_scale(scale)
    held_staff.set_ui_scale(scale)
    score_frame.custom_minimum_size.y = 135.0
    for side in ["left","right","top","bottom"]:
        score_margin_box.add_theme_constant_override("margin_" + side,1 if compact else 6)
    practice_playback_banner.add_theme_font_size_override("font_size",UI.font_size(15,scale))
    notification_row.custom_minimum_size.y = maxf(32.0,36.0*scale)
    _place_notice()
    _place_count_in()

func _place_notice() -> void:
    # Start the text close to the fixed reading axis, without moving ink.
    practice_playback_banner.offset_left = notification_row.size.x*PLAYHEAD_FRACTION
    practice_playback_banner.offset_right = -6.0

func present_notice(text: String) -> void:
    if text == _notice_text:
        return
    _notice_text = text
    if _notice_tween != null and _notice_tween.is_valid():
        _notice_tween.kill()
    _notice_tween = create_tween()
    if text.is_empty():
        _notice_tween.tween_property(practice_playback_banner,"modulate:a",0.0,.18)
        _notice_tween.tween_callback(func():
            practice_playback_banner.visible = false
            practice_playback_banner.text = "")
    else:
        practice_playback_banner.text = text
        practice_playback_banner.visible = true
        practice_playback_banner.modulate.a = 0.0
        _notice_tween.tween_property(practice_playback_banner,"modulate:a",1.0,.12)

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
    score_retry_button.visible = score_status_panel.visible and \
        bool(status.get("retry_visible",false))
    score_browse_button.visible = score_status_panel.visible and \
        bool(status.get("browse_visible",false))
    if not score_status_panel.visible:
        return
    score_status_label.text = str(status.get("text","Preparing sheet music…"))
    score_status_label.tooltip_text = score_status_label.text
