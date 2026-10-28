extends ScrollContainer
# Home owns its catalog presentation and captured Continue target.
# Navigation, opening music and platform actions are coordinated by signals.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK

signal library_requested
signal settings_requested
signal exit_requested
signal open_requested(identifier: String, resume_saved: bool)

var cards: BoxContainer
var count_label: Label
var recent_label: Label
var resume_button: Button
var _recent_identifier := ""

func _ready() -> void:
    name = "HomeScreen"
    theme = Design.create()
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    var home_layout := UI.stack(26)
    home_layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(home_layout)
    var home_nav := HBoxContainer.new()
    home_layout.add_child(home_nav)
    home_nav.add_child(UI.label("Piano Teacher", 24, INK, true))
    var spacer := Control.new()
    spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_nav.add_child(spacer)
    var settings := UI.button("Settings", "settings")
    settings.pressed.connect(func(): settings_requested.emit())
    home_nav.add_child(settings)
    var quit_button := UI.button("Quit", "danger")
    quit_button.pressed.connect(func(): exit_requested.emit())
    home_nav.add_child(quit_button)
    var header := UI.stack(12)
    home_layout.add_child(header)
    header.add_child(UI.label("Your practice", 34, INK, true))
    header.add_child(UI.label("Choose your music or continue your last lesson.", 18, MUTED))
    var home_row := BoxContainer.new()
    cards = home_row
    home_row.add_theme_constant_override("separation", 20)
    home_layout.add_child(home_row)
    var library_card := UI.card()
    library_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_row.add_child(library_card)
    var library_inner := UI.stack(17)
    UI.card_body(library_card, 32).add_child(library_inner)
    library_inner.add_child(UI.label("YOUR MUSIC", 13, MUTED, true))
    count_label = UI.label("Discovering your music…", 25, INK, true)
    library_inner.add_child(count_label)
    library_inner.add_child(UI.label("MIDI and MusicXML from your selected folder", 15, MUTED))
    var browse := UI.button("Browse library  →", "primary")
    browse.pressed.connect(func(): library_requested.emit())
    library_inner.add_child(browse)
    var recent_card := UI.card()
    recent_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_row.add_child(recent_card)
    var recent_inner := UI.stack(17)
    UI.card_body(recent_card, 32).add_child(recent_inner)
    recent_inner.add_child(UI.label("LAST OPENED", 13, MUTED, true))
    recent_label = UI.label("No recent piece", 25, INK, true)
    recent_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    recent_label.clip_text = true
    recent_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    recent_inner.add_child(recent_label)
    recent_inner.add_child(UI.label("Pick up where you left off", 15, MUTED))
    resume_button = UI.button("Continue  →", "primary")
    resume_button.pressed.connect(func():
        if not resume_button.disabled and not _recent_identifier.is_empty():
            open_requested.emit(_recent_identifier, true))
    recent_inner.add_child(resume_button)
    home_layout.add_child(UI.label("Connect your USB MIDI keyboard and select your music. Progress stays on this computer.", 14, MUTED))


func present_catalog(catalog: Dictionary) -> void:
    count_label.text = "%d scores · %d built-in warm-ups" % [int(catalog.get("count", 0)), catalog.get("warmups", []).size()]
    var recent: String = str(catalog.get("last_piece", ""))
    _recent_identifier = ""
    for entry in catalog.get("warmups", []) + catalog.get("pieces", []):
        if str(entry.get("id", "")) == recent:
            _recent_identifier = recent
            break
    resume_button.disabled = _recent_identifier.is_empty()
    var title := recent.get_file().get_basename().replace("_", " ")
    for entry in catalog.get("warmups", []):
        if str(entry.get("id", "")) == recent:
            title = str(entry.get("title", title))
            break
    recent_label.text = title if not recent.is_empty() else "No recent piece"

func present_catalog_unavailable() -> void:
    count_label.text = "Practice engine unavailable"
    resume_button.disabled = true

func present_operation_error(message: String) -> void:
    recent_label.text = message

func apply_viewport(view_size: Vector2, scale: float) -> void:
    var width: float = view_size.x
    cards.vertical = width < 1380
    for control in find_children("*", "Control", true, false):
        if control.has_meta("ui_font_base"):
            control.add_theme_font_size_override("font_size", UI.font_size(int(control.get_meta("ui_font_base")), scale))
