extends RefCounted

# Owns the music/settings navigation drawer and its transition animation.
# The app retains routing, practice pause semantics and backend requests.
const Design := preload("res://practice_theme.gd")
const UI := preload("res://ui_factory.gd")

var root: Control
var drawer: PanelContainer
var rail: VBoxContainer
var navigation: Dictionary = {}
var intro: Tween

func mount(host: Control, screens: Dictionary, make_button: Callable,
        navigate: Callable, exit_app: Callable) -> void:
    root = Control.new()
    root.name = "MusicAndSettingsDrawer"
    root.z_index = 10
    root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    host.add_child(root)
    var backdrop := ColorRect.new()
    backdrop.color = Design.NIGHT
    backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(backdrop)
    drawer = PanelContainer.new()
    drawer.name = "ContextDrawer"
    drawer.clip_contents = true
    drawer.add_theme_stylebox_override(
        "panel", Design.bordered_surface(Design.PANEL_RECESSED, 14, .25))
    root.add_child(drawer)
    var shell := HBoxContainer.new()
    shell.add_theme_constant_override("separation", 0)
    drawer.add_child(shell)
    var rail_panel := PanelContainer.new()
    rail_panel.add_theme_stylebox_override(
        "panel", Design.surface(Color(Design.NIGHT, .52), 10))
    shell.add_child(rail_panel)
    rail = UI.stack(8)
    rail.custom_minimum_size.x = 150
    rail_panel.add_child(rail)
    var brand := UI.title("Piano\nTeacher", 23)
    brand.custom_minimum_size.y = 100
    rail.add_child(brand)
    for item in [["library", "Library"], ["lesson", "Lesson path"],
            ["settings", "Settings"]]:
        var destination: String = item[0]
        var button: Button = make_button.call(item[1],
            func(): navigate.call(destination), false, "choice")
        button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        button.custom_minimum_size.x = 0
        rail.add_child(button)
        navigation[destination] = button
    var spacer := Control.new()
    spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
    rail.add_child(spacer)
    var practice_button: Button = make_button.call(
        "Practice", func(): navigate.call("practice"), true, "primary")
    rail.add_child(practice_button)
    var exit_button: Button = make_button.call(
        "Exit", exit_app, false, "danger")
    exit_button.tooltip_text = "Close Piano Teacher (Ctrl+Q)"
    rail.add_child(exit_button)
    var pages := Control.new()
    pages.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    pages.size_flags_vertical = Control.SIZE_EXPAND_FILL
    shell.add_child(pages)
    for page in ["library", "settings", "lesson"]:
        var content: Control = screens[page]
        content.reparent(pages, false)
        content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.visible = false

func present(screen: String, previous_screen: String) -> void:
    if root == null:
        return
    for destination in navigation:
        navigation[destination].set_selected(destination == screen)
    root.visible = screen != "practice"
    if intro != null and intro.is_running():
        intro.kill()
    if screen != "practice" and previous_screen == "practice":
        # Animate the drawer only, without redrawing the fullscreen scrim.
        drawer.modulate.a = 0.0
        intro = root.create_tween()
        intro.tween_property(drawer, "modulate:a", 1.0, .18) \
            .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
    else:
        drawer.modulate.a = 1.0

func resize(view_size: Vector2) -> void:
    if drawer == null:
        return
    var inset := 18.0 if view_size.x >= 1100.0 else 8.0
    drawer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    drawer.offset_left = inset
    drawer.offset_top = inset
    drawer.offset_right = -inset
    drawer.offset_bottom = -inset
    rail.custom_minimum_size.x = 160.0 if view_size.x >= 1100.0 else 125.0
