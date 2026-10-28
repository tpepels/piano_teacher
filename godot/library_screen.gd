extends VBoxContainer
# Owns Library controls, captured presentation values and search/scan rendering.
# HTTP lifetimes, opening music and navigation belong to the application.
const UI := preload("res://ui_factory.gd")
const Design := preload("res://practice_theme.gd")
const LibraryRow := preload("res://library_row.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL

signal open_requested(identifier: String, resume_saved: bool)
signal refresh_requested
signal health_check_requested

var ui_scale := 1.0
var library_heading: BoxContainer
var library_search: LineEdit
var library_filter_timer: Timer
var library_scroll: ScrollContainer
var library_path_label: Label
var library_rows: VBoxContainer
var library_message: Label
var library_health_button: Button
var library_health_label: Label
var library_info: Dictionary = {}
var library_health_info: Dictionary = {}
var library_error := ""
var _operation_message := ""
var _request_error := ""
var _visible_count := 0
var _viewport_width := 1220.0

func _ready() -> void:
    name = "LibraryScreen"
    theme = Design.create()
    add_theme_constant_override("separation", 10)
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    var library_layout: VBoxContainer = self
    library_heading = BoxContainer.new()
    library_heading.add_theme_constant_override("separation", 20)
    library_layout.add_child(library_heading)
    var library_intro := UI.stack(4)
    library_intro.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    library_heading.add_child(library_intro)
    library_intro.add_child(UI.label("PIANO TEACHER", 14, ACCENT, true))
    library_intro.add_child(UI.title("Your music", 32))
    library_path_label = UI.label("Looking for scores…", 13, MUTED)
    library_path_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    library_path_label.clip_text = true
    library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    library_layout.add_child(library_path_label)
    library_search = LineEdit.new()
    library_search.placeholder_text = "Search songs…"
    library_search.clear_button_enabled = true
    library_search.tooltip_text = "Ctrl+F or / to focus search · Esc closes the library"
    library_search.custom_minimum_size = Vector2(220, 40)
    library_search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    # Avoid destroying and recreating every music-row button on every key.
    # The visible search text changes immediately; results settle after the
    # final keystroke without blocking the score renderer.
    library_filter_timer = Timer.new()
    library_filter_timer.one_shot = true
    library_filter_timer.wait_time = .12
    library_filter_timer.timeout.connect(_populate)
    add_child(library_filter_timer)
    library_search.text_changed.connect(func(_text: String):
        if library_scroll != null:
            library_scroll.scroll_vertical = 0
        library_filter_timer.start())
    library_heading.add_child(library_search)
    # Shortcuts remain active and discoverable in the search tooltip.
    # A permanent tiny instruction line made the library feel like a form.
    var library_utilities := HBoxContainer.new()
    library_utilities.add_theme_constant_override("separation", 10)
    library_layout.add_child(library_utilities)
    library_utilities.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    var refresh := UI.button("Refresh", "utility")
    refresh.name = "LibraryRefresh"
    refresh.pressed.connect(func(): refresh_requested.emit())
    library_utilities.add_child(refresh)
    library_health_button = UI.button("Check files", "settings")
    library_health_button.pressed.connect(func(): health_check_requested.emit())
    # Dynamic text also says "Checking…" or "Recheck files". Reserve room
    # from the start so the button does not visibly resize or clip.
    library_health_button.custom_minimum_size.x = maxf(
        library_health_button.custom_minimum_size.x,
        UI.font_size(15, ui_scale) * 8.3 + 48.0 * ui_scale)
    library_utilities.add_child(library_health_button)
    # Import problems must appear next to the action, not at the very
    # bottom of a full-screen library where they are easy to miss.
    library_message = UI.label("", 13, MUTED)
    library_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_message.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    library_utilities.add_child(library_message)
    library_health_label = UI.label("", 16, MUTED)
    library_health_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_health_label.visible = false
    library_layout.add_child(library_health_label)
    var scroll := ScrollContainer.new()
    library_scroll = scroll
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    library_layout.add_child(scroll)
    library_rows = UI.stack(18)
    library_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(library_rows)
    for pair in [[library_heading,"LibraryHeading"], [library_search,"LibrarySearch"],
            [library_scroll,"LibraryScroll"], [library_path_label,"LibraryPath"],
            [library_rows,"LibraryRows"], [library_message,"LibraryMessage"],
            [library_health_button,"LibraryHealthButton"], [library_health_label,"LibraryHealthLabel"]]:
        pair[0].name = pair[1]

func present_catalog(catalog: Dictionary) -> void:
    library_info = catalog.duplicate(true)
    _request_error = ""
    library_path_label.text = str(library_info.get("folder", ""))
    _operation_message = ""
    _populate()
    _update_layout()

func present_health(parsed: Dictionary) -> void:
    var previous_started: bool = bool(library_health_info.get("started", false))
    var previous_running: bool = bool(library_health_info.get("running", false))
    library_health_info = parsed.duplicate(true)
    var active: bool = bool(parsed.get("running", false))
    var started: bool = bool(parsed.get("started", false))
    library_health_button.disabled = active
    library_health_button.text = "Checking…" if active else "Recheck files" if started else "Check files"
    library_health_label.visible = started
    if started:
        library_health_label.text = (
            "Checking %d of %d files · %d OK · %d repaired · %d errors" if active
            else "File check complete: %d of %d · %d OK · %d repaired · %d errors"
        ) % [int(parsed.get("checked", 0)), int(parsed.get("total", 0)),
             int(parsed.get("ok", 0)), int(parsed.get("warning", 0)), int(parsed.get("error", 0))]
        if not str(parsed.get("message", "")).is_empty():
            library_health_label.text += "\n" + str(parsed["message"])
    # A large music collection may scan hundreds of files. Rebuilding
    # every clickable row at each file-progress tick caused visible drawer
    # flicker, lost keyboard focus and expensive Godot allocations. Keep
    # updating the small progress label; rebuild row statuses only at start
    # and once when the scan finishes.
    if previous_started != started or previous_running != active:
        _populate()


func present_health_message(message: String) -> void:
    library_health_label.visible = true
    library_health_label.text = message

func present_request_error(message: String) -> void:
    _request_error = message
    _render_message()

func present_open_status(message: String, is_error: bool = false) -> void:
    _request_error = ""
    library_error = message if is_error else ""
    _operation_message = "" if is_error else message
    _render_message()

func apply_viewport(view_size: Vector2, scale: float) -> void:
    _viewport_width = view_size.x
    ui_scale = scale
    for node in find_children("*", "Control", true, false):
        if node.has_meta("ui_font_base"):
            node.add_theme_font_size_override("font_size",
                UI.font_size(int(node.get_meta("ui_font_base")), scale))
        if node.has_method("set_text_scale"):
            node.set_text_scale(scale)
    _update_layout()

func focus_search(select_all: bool = false) -> void:
    library_search.grab_focus()
    if select_all:
        library_search.select_all()

func is_search_focused() -> bool:
    return library_search.has_focus()

func _update_layout() -> void:
    library_heading.vertical = _viewport_width < 1100.0
    library_path_label.visible = false
    library_search.tooltip_text = library_path_label.text + "\nCtrl+F or / to search"
    _render_message()

func _render_message() -> void:
    var pieces: Array = library_info.get("pieces", [])
    var warmups: Array = library_info.get("warmups", [])
    var issue: String = str(library_info.get("error", ""))
    if not library_error.is_empty():
        library_message.text = library_error
    elif not _request_error.is_empty():
        library_message.text = _request_error
    elif not _operation_message.is_empty():
        library_message.text = _operation_message
    elif not issue.is_empty():
        library_message.text = issue
    elif pieces.is_empty() and warmups.is_empty():
        library_message.text = "No scores yet. Add .mid, .midi or MusicXML files to this folder."
    elif _visible_count == 0:
        library_message.text = "No matches for “%s”. Try another title or clear the search." % library_search.text.strip_edges()
    else:
        library_message.text = "%d personal files  ·  %d built-in warm-ups  ·  %d shown" % [pieces.size(), warmups.size(), _visible_count]
    library_message.add_theme_color_override("font_color",
        Color("#FF8B82") if not library_error.is_empty() else MUTED)
    library_message.visible = _viewport_width >= 1100.0 or not library_error.is_empty() \
        or not _request_error.is_empty() or not _operation_message.is_empty() \
        or not issue.is_empty() or _visible_count == 0

func _last_library_entry() -> Dictionary:
    var identifier: String = str(library_info.get("last_piece", ""))
    if not identifier.is_empty():
        for entry in library_info.get("warmups", []) + library_info.get("pieces", []):
            if str(entry.get("id", "")) == identifier:
                return entry
    return {}

func _populate() -> void:
    if library_rows == null:
        return
    if library_filter_timer != null and not library_filter_timer.is_stopped():
        library_filter_timer.stop()
    for child in library_rows.get_children():
        library_rows.remove_child(child)
        child.queue_free()
    var pieces: Array = library_info.get("pieces", [])
    var warmups: Array = library_info.get("warmups", [])
    var query := library_search.text.strip_edges().to_lower()
    var visible := 0
    var recent: Dictionary = _last_library_entry()
    var show_recent: bool = query.is_empty() and not recent.is_empty()
    var sections: Array = []
    if show_recent:
        sections.append({"title": "LAST OPENED", "entries": [recent], "resume": true})
    sections.append({"title": "YOUR MUSIC", "entries": pieces})
    sections.append({"title": "BUILT-IN WARM-UPS", "entries": warmups})
    for section in sections:
        var section_added := false
        var grid: GridContainer
        for entry in section.entries:
            var identifier: String = str(entry.get("id", ""))
            var resume_saved: bool = bool(section.get("resume", false))
            if show_recent and not resume_saved and identifier == str(recent.get("id", "")):
                continue
            var title: String = str(entry.get("title", "Untitled"))
            var location: String = str(entry.get("folder", ""))
            var focus: String = str(entry.get("focus", ""))
            if not query.is_empty() and not (title + " " + location + " " + focus).to_lower().contains(query):
                continue
            if not section_added:
                library_rows.add_child(UI.label(str(section.title).capitalize(), 15, MUTED, true))
                grid = GridContainer.new()
                grid.columns = 1
                grid.add_theme_constant_override("h_separation", 12)
                grid.add_theme_constant_override("v_separation", 12)
                grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
                library_rows.add_child(grid)
                section_added = true
            var format_name: String = str(entry.get("format", ""))
            var hint: String = ("%d BPM · %s" % [int(entry.get("bpm", 0)), focus]
                if not focus.is_empty() else
                location if not location.is_empty() else "Music folder")
            var diagnosis: Dictionary = library_health_info.get("items", {}).get(identifier, {})
            var status: String = str(diagnosis.get("status", ""))
            var detail: String = format_name + "  ·  " + hint
            if status == "error":
                detail = "Needs attention  ·  " + detail
            elif status == "warning":
                detail = "Repaired  ·  " + detail
            if resume_saved:
                detail = "Continue from saved place  ·  " + detail
            var row := LibraryRow.new()
            if resume_saved:
                row.pressed.connect(func(): open_requested.emit(identifier, true))
            else:
                row.pressed.connect(func(): open_requested.emit(identifier, false))
            grid.add_child(row)
            row.set_entry(title.replace("_", " "), detail, status)
            row.set_text_scale(ui_scale)
            if entry.has("description"):
                row.tooltip_text += "\n" + str(entry["description"])
            if not diagnosis.is_empty():
                row.tooltip_text += "\nImport check: " + str(diagnosis.get("message", ""))
                if status != "error":
                    row.tooltip_text += " · %d notes · %d measures" % [
                        int(diagnosis.get("notes", 0)), int(diagnosis.get("measures", 0))]
            visible += 1
    _visible_count = visible
    _render_message()
