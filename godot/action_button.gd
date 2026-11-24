extends Button

# Semantic action roles - one consistent hierarchy across Home, Library,
# Lesson Path, Settings and the practice stage.
# Button.pressed remains the only action; drawing is decoration only.
const Design := preload("res://practice_theme.gd")
const MINT := Design.MINT
var action_role := "secondary"
var is_selected := false
var icon_only := false

func set_icon_only(enabled: bool) -> void:
	icon_only = enabled
	if enabled:
		tooltip_text = text if tooltip_text.is_empty() else tooltip_text
		clip_text = true
		custom_minimum_size = Vector2(40,40)
	_skin()
	queue_redraw()

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
	return Design.MINT if action_role == "utility" and is_selected else Design.role_fill(action_role, is_selected)


func _has_symbol() -> bool:
	# An arrow caption already communicates direction. A second icon also
	# reserves unwanted space and can contradict a Previous chevron.
	if action_role == "navigation" and text in ["‹", "›", "←", "→"]:
		return false
	return action_role in ["navigation", "utility", "listen", "settings", "review",
		"danger", "library", "practice_tempo"]

func _skin_menu() -> void:
	# Game-menu item: a large word on the stage, no box. Hover, focus and
	# selection light a mint key at its left edge (drawn inside the button,
	# so no glow ever spills over a neighbour).
	var rest_box := StyleBoxFlat.new()
	rest_box.bg_color = Color.TRANSPARENT
	rest_box.set_corner_radius_all(8)
	rest_box.content_margin_left = 32
	rest_box.content_margin_right = 16
	rest_box.content_margin_top = 6
	rest_box.content_margin_bottom = 6
	var band := rest_box.duplicate() as StyleBoxFlat
	band.bg_color = Color(Design.CORAL if action_role == "menu_danger" else Design.MINT, .09)
	for state in ["normal","disabled"]:
		add_theme_stylebox_override(state, rest_box)
	for state in ["hover","pressed","hover_pressed","focus"]:
		add_theme_stylebox_override(state, band)
	alignment = HORIZONTAL_ALIGNMENT_LEFT
	add_theme_font_override("font", Design.title_font())
	var rest: Color = Design.CORAL if action_role == "menu_danger" else Color(Design.STONE,.72)
	var lit: Color = Design.CORAL if action_role == "menu_danger" else Design.STONE
	add_theme_color_override("font_color", lit if is_selected else rest)
	for state in ["font_hover_color","font_pressed_color","font_hover_pressed_color","font_focus_color"]:
		add_theme_color_override(state, lit)
	add_theme_color_override("font_disabled_color", lit if is_selected else Color(Design.SLATE,.55))

func _skin_key() -> void:
	# A key cap: raised fill, outline, and a darker depth edge drawn at the
	# bottom (see _draw_key). Hover lights the outline; pressing sinks it.
	var danger := action_role == "key_danger"
	var edge: Color = Design.CORAL if danger else Design.MINT
	var normal := StyleBoxFlat.new()
	normal.bg_color = Design.PANEL_RAISED
	normal.set_corner_radius_all(8)
	normal.set_border_width_all(1)
	normal.border_color = Color(edge, .55) if danger else Color(Design.STONE, .22)
	normal.content_margin_left = 18
	normal.content_margin_right = 18
	normal.content_margin_top = 8
	normal.content_margin_bottom = 11
	add_theme_stylebox_override("normal", normal)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Design.PANEL_RAISED.lightened(.08)
	hover.border_color = Color(edge, .85)
	add_theme_stylebox_override("hover", hover)
	add_theme_stylebox_override("focus", hover)
	var pressed := hover.duplicate() as StyleBoxFlat
	pressed.bg_color = Design.PANEL_RAISED.darkened(.12)
	pressed.content_margin_top = 10
	pressed.content_margin_bottom = 9
	add_theme_stylebox_override("pressed", pressed)
	add_theme_stylebox_override("hover_pressed", pressed)
	var off := normal.duplicate() as StyleBoxFlat
	off.bg_color = Color(Design.PANEL_RAISED, .45)
	off.border_color = Color(Design.STONE, .08)
	add_theme_stylebox_override("disabled", off)
	add_theme_font_override("font", Design.font(600))
	var ink: Color = Design.CORAL if danger else Design.STONE
	if is_selected:
		# A chosen option in a group of keys: a lit, filled key.
		for state in ["normal","hover","focus","disabled"]:
			var lit := (get_theme_stylebox(state) as StyleBoxFlat).duplicate() as StyleBoxFlat
			lit.bg_color = Design.MINT
			lit.border_color = Design.MINT
			add_theme_stylebox_override(state, lit)
		ink = Design.NIGHT
	for state in ["font_color","font_hover_color","font_pressed_color","font_hover_pressed_color","font_focus_color"]:
		add_theme_color_override(state, ink)
	add_theme_color_override("font_disabled_color", Design.NIGHT if is_selected else Color(Design.SLATE, .6))
	alignment = HORIZONTAL_ALIGNMENT_CENTER

func _draw_key() -> void:
	if (disabled and not is_selected) or button_pressed:
		return
	# The key's depth: a darker band under its face, inside the bounds.
	var depth := Rect2(Vector2(1.0, size.y-4.0), Vector2(size.x-2.0, 3.0))
	draw_rect(depth, Color(Design.NIGHT, .55), true)
	if is_hovered() or has_focus():
		var tone: Color = Design.CORAL if action_role == "key_danger" else Design.MINT
		draw_rect(Rect2(Vector2(8.0, size.y-4.0), Vector2(size.x-16.0, 2.0)), Color(tone, .9), true)

func _skin() -> void:
	if action_role.begins_with("menu"):
		_skin_menu()
		return
	if action_role.begins_with("key"):
		_skin_key()
		return
	var accent: Color = _accent()
	var background: Color = _background()
	var flat := action_role in ["navigation", "utility", "library"]
	var important := action_role == "primary" or (is_selected and action_role in ["choice", "utility"])
	var normal := StyleBoxFlat.new()
	normal.bg_color = background
	normal.set_corner_radius_all(Design.RADIUS_INPUT)
	normal.set_border_width_all(1)
	normal.border_color = (Color(Design.MINT,.60) if action_role == "practice_tempo"
		else Color(accent,.66) if important else Color(Design.BORDER,.5))
	normal.content_margin_left = 0 if icon_only else 36 if _has_symbol() else 14
	normal.content_margin_right = 0 if icon_only else 14
	normal.content_margin_top = 8
	normal.content_margin_bottom = 8
	normal.shadow_color = Color(Design.NIGHT,.22)
	normal.shadow_size = 2
	normal.shadow_offset = Vector2(0,2)
	add_theme_stylebox_override("normal", normal)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = background.lightened(.09)
	hover.border_color = Color(Design.HIGHLIGHT,.92) if important else Color(Design.MINT,.70)
	hover.shadow_size = 2
	add_theme_stylebox_override("hover", hover)
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = background.darkened(.13)
	pressed.shadow_size = 0
	pressed.shadow_offset = Vector2.ZERO
	add_theme_stylebox_override("pressed", pressed)
	add_theme_stylebox_override("hover_pressed", pressed)
	var disabled_style := normal.duplicate() as StyleBoxFlat
	disabled_style.bg_color = background if action_role == "choice" and is_selected else Design.PANEL_RECESSED
	disabled_style.border_color = (Color(MINT, .83) if action_role == "choice" and
		is_selected else Color(Design.BORDER, .3))
	disabled_style.shadow_size = 0
	add_theme_stylebox_override("disabled", disabled_style)
	var focus := normal.duplicate() as StyleBoxFlat
	focus.bg_color = Color.TRANSPARENT
	focus.set_border_width_all(2)
	focus.border_color = Design.FOCUS
	focus.shadow_size = 0
	add_theme_stylebox_override("focus", focus)
	var ink := Design.NIGHT if important else Design.STONE
	if flat:
		ink = Design.SECONDARY_INK
	if action_role == "danger":
		ink = Design.CORAL
	add_theme_color_override("font_color", ink)
	add_theme_color_override("font_hover_color", Design.NIGHT if important else Design.FOCUS)
	add_theme_color_override("font_pressed_color", Design.NIGHT if important else Design.FOCUS)
	add_theme_color_override("font_hover_pressed_color", Design.NIGHT if important else Design.FOCUS)
	add_theme_color_override("font_focus_color", ink)
	add_theme_color_override("font_disabled_color",
		Design.NIGHT if action_role == "choice" and is_selected else Design.SLATE)
	add_theme_color_override("icon_normal_color",
		Design.NIGHT if important else accent)
	if icon_only:
		for state in ["font_color","font_hover_color","font_pressed_color",
				"font_hover_pressed_color","font_focus_color","font_disabled_color"]:
			add_theme_color_override(state,Color.TRANSPARENT)

func _draw_menu_key() -> void:
	# Every menu choice carries a key notch, dim at rest, so it reads as
	# something to press; hover, focus and selection light it.
	var lit := is_selected or ((is_hovered() or has_focus()) and not disabled)
	var tone: Color = Design.CORAL if action_role == "menu_danger" else Design.MINT
	var h := size.y*.56
	var key := Rect2(Vector2(10.0,(size.y-h)*.5),Vector2(5.0,h))
	if not lit and not button_pressed:
		draw_rect(key, Color(Design.STONE, .10 if disabled else .32), true)
		return
	# Soft bloom kept inside the button: three widening, fading layers.
	for i in range(3, 0, -1):
		var grow := float(i)*3.0
		draw_rect(key.grow(grow), Color(tone, .07), true)
	draw_rect(key, tone, true)

func _draw() -> void:
	if action_role.begins_with("menu"):
		_draw_menu_key()
		return
	if action_role.begins_with("key"):
		_draw_key()
		return
	if not _has_symbol() or size.x < 32 or size.y < 32:
		return
	var accent: Color = _accent()
	var alpha := 1.0 if action_role == "choice" and is_selected else .32 if disabled else 1.0
	accent.a *= alpha
	if (is_selected and action_role in ["choice", "utility"]) or action_role == "primary":
		accent = Color(Design.NIGHT,alpha)
	elif is_hovered() and not disabled:
		accent = Design.MINT
	var center := Vector2(size.x*.5 if icon_only else 18.0, size.y*.5)
	match action_role:
		"primary":
			draw_line(center+Vector2(-6, 0),center+Vector2(6, 0),accent,2.4,true)
			draw_line(center+Vector2(1,-5),center+Vector2(6,0),accent,2.4,true)
			draw_line(center+Vector2(1,5),center+Vector2(6,0),accent,2.4,true)
		"navigation":
			var backward := text.begins_with("←") or text.begins_with("Previous") or text in ["Close", "Back", "Practice"]
			var direction := -1.0 if backward else 1.0
			draw_line(center+Vector2(-direction*5,0),center+Vector2(direction*5,0),accent,1.9,true)
			draw_line(center+Vector2(direction*1,-4),center+Vector2(direction*5,0),accent,1.9,true)
			draw_line(center+Vector2(direction*1,4),center+Vector2(direction*5,0),accent,1.9,true)
		"utility":
			for x in [-5.0, 0.0, 5.0]:
				draw_circle(center+Vector2(x,0),1.65,accent)
		"practice_tempo":
			# Small drawn metronome; no eighth-note glyph or emoji fallback.
			var left := center+Vector2(-6.5,7)
			var right := center+Vector2(6.5,7)
			var upper_left := center+Vector2(-2.8,-5.5)
			var upper_right := center+Vector2(2.8,-5.5)
			for edge in [[left,right],[left,upper_left],[upper_left,upper_right],[upper_right,right]]:
				draw_line(edge[0],edge[1],accent,1.65,true)
			draw_line(center+Vector2(-1,3),center+Vector2(4,-8),accent,1.7,true)
			draw_circle(center+Vector2(4,-8),1.5,accent)
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
