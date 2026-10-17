extends Button

# Semantic action roles - one consistent hierarchy across Home, Library,
# Lesson Path, Settings and the practice stage.
# Button.pressed remains the only action; drawing is decoration only.
const Design := preload("res://practice_theme.gd")
const SAGE := Design.SLATE
const MINT := Design.MINT
const BLUE := Design.BLUE
const AMBER := Design.AMBER
const CORAL := Design.CORAL
var action_role := "secondary"
var is_selected := false

func _init() -> void:
    focus_mode = Control.FOCUS_ALL
    mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND

func _ready() -> void:
    mouse_entered.connect(queue_redraw)
    mouse_exited.connect(queue_redraw)
    focus_entered.connect(queue_redraw)
    focus_exited.connect(queue_redraw)
    button_down.connect(queue_redraw)
    button_up.connect(queue_redraw)

func configure(role: String) -> void:
    action_role = role
    set_meta("ui_button_role",role)
    _skin()
    queue_redraw()

func set_selected(selected: bool) -> void:
    if is_selected == selected:
        return
    is_selected = selected
    _skin()
    queue_redraw()

func _accent() -> Color:
    return Design.role_accent(action_role)


func _background() -> Color:
    return Design.role_fill(action_role, is_selected)


func _has_symbol() -> bool:
    return action_role != "secondary"

func _skin() -> void:
    var accent: Color = _accent()
    var background: Color = _background()
    var flat := action_role in ["navigation", "utility", "library"]
    var important := action_role == "primary" or (action_role == "choice" and is_selected)
    var rounded := Design.RADIUS_CARD + 1 if important else (
        Design.RADIUS_INPUT + 2 if not flat else Design.RADIUS_INPUT)
    var normal := StyleBoxFlat.new()
    normal.bg_color = Color(background, .62) if action_role == "library" else background
    normal.set_corner_radius_all(rounded)
    normal.set_border_width_all(2 if important else 1)
    normal.border_color = Color(accent, .94 if important else .55 if not flat else .20)
    normal.content_margin_left = 48 if _has_symbol() else 18
    normal.content_margin_right = 17
    normal.content_margin_top = 12
    normal.content_margin_bottom = 12
    if important:
        normal.shadow_size = 5
        normal.shadow_color = Color(accent, .24)
        normal.shadow_offset = Vector2(0, 2)
    add_theme_stylebox_override("normal", normal)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = background.lightened(.14) if not flat else Color("#2C4842", .9)
    hover.border_color = Color(accent, .94)
    hover.shadow_size = 8 if important else 3
    hover.shadow_color = Color(accent, .23)
    add_theme_stylebox_override("hover", hover)
    var pressed := normal.duplicate() as StyleBoxFlat
    pressed.bg_color = background.darkened(.13)
    pressed.shadow_size = 0
    pressed.shadow_offset = Vector2.ZERO
    add_theme_stylebox_override("pressed", pressed)
    add_theme_stylebox_override("hover_pressed", pressed)
    var disabled_style := normal.duplicate() as StyleBoxFlat
    disabled_style.bg_color = (background if action_role == "choice" and
        is_selected else Color("#182725", .6))
    disabled_style.border_color = (Color(MINT, .83) if action_role == "choice" and
        is_selected else Color("#667B72", .2))
    disabled_style.shadow_size = 0
    add_theme_stylebox_override("disabled", disabled_style)
    var focus := normal.duplicate() as StyleBoxFlat
    focus.bg_color = Color.TRANSPARENT
    focus.set_border_width_all(2)
    focus.border_color = Design.FOCUS
    focus.shadow_size = 0
    add_theme_stylebox_override("focus", focus)
    var ink := Design.FOCUS if important else Design.STONE
    if flat:
        ink = Design.SLATE
    if action_role == "danger":
        ink = Design.CORAL
    add_theme_color_override("font_color", ink)
    add_theme_color_override("font_hover_color", Design.FOCUS)
    add_theme_color_override("font_pressed_color", Design.FOCUS)
    add_theme_color_override("font_hover_pressed_color", Design.FOCUS)
    add_theme_color_override("font_focus_color", Design.FOCUS)
    add_theme_color_override("font_disabled_color",
        MINT if action_role == "choice" and is_selected else Color("#718B80"))
    add_theme_color_override("icon_normal_color", accent)

func _draw() -> void:
    if not _has_symbol() or size.x < 45 or size.y < 32:
        return
    var accent: Color = _accent()
    var alpha := 1.0 if action_role == "choice" and is_selected else .32 if disabled else 1.0
    accent.a *= alpha
    var center := Vector2(23.0, size.y*.5)
    var radius := 14.0 if action_role in ["primary", "choice"] else 12.5
    draw_circle(center, radius, Color(accent, .14 if not disabled else .06))
    match action_role:
        "primary":
            draw_line(center+Vector2(-6, 0),center+Vector2(6, 0),accent,2.4,true)
            draw_line(center+Vector2(1,-5),center+Vector2(6,0),accent,2.4,true)
            draw_line(center+Vector2(1,5),center+Vector2(6,0),accent,2.4,true)
        "navigation":
            var backward := text.begins_with("←") or text in ["Close","Back"]
            var direction := -1.0 if backward else 1.0
            draw_line(center+Vector2(-direction*5,0),center+Vector2(direction*5,0),accent,1.9,true)
            draw_line(center+Vector2(direction*1,-4),center+Vector2(direction*5,0),accent,1.9,true)
            draw_line(center+Vector2(direction*1,4),center+Vector2(direction*5,0),accent,1.9,true)
        "utility":
            for x in [-5.0, 0.0, 5.0]:
                draw_circle(center+Vector2(x,0),1.65,accent)
        "listen":
            draw_circle(center + Vector2(-5, 0), 2.6, accent)
            draw_arc(center + Vector2(-5, 0), 6.8, -.36*PI, .36*PI, 24, accent, 2.0, true)
            draw_arc(center + Vector2(-5, 0), 11.0, -.36*PI, .36*PI, 24, accent, 1.6, true)
        "settings":
            draw_arc(center,5.5,0,TAU,24,accent,1.9,true)
            draw_circle(center,1.7,accent)
            for i in range(6):
                var v := Vector2.RIGHT.rotated(float(i)*TAU/6.0)
                draw_line(center+v*7,center+v*9,accent,1.8,true)
        "review":
            draw_arc(center,6.0,-.55*PI,1.24*PI,24,accent,2.1,true)
            draw_colored_polygon(PackedVector2Array([
                center+Vector2(-7,-5),center+Vector2(-7,3),
                center+Vector2(-1,-2)]),accent)
        "danger":
            draw_line(center+Vector2(-4,-4),center+Vector2(4,4),accent,2.2,true)
            draw_line(center+Vector2(4,-4),center+Vector2(-4,4),accent,2.2,true)
        "library":
            draw_line(center+Vector2(3,-7),center+Vector2(3,5),accent,2.1,true)
            draw_line(center+Vector2(3,-7),center+Vector2(8,-5),accent,2.0,true)
            draw_circle(center+Vector2(-.5,6),3.4,accent)
        "choice":
            if is_selected:
                draw_line(center+Vector2(-6,0),center+Vector2(-1,5),accent,2.2,true)
                draw_line(center+Vector2(-1,5),center+Vector2(7,-5),accent,2.2,true)
            else:
                draw_arc(center,5.5,0,TAU,24,accent,1.6,true)
