extends SceneTree

const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")
const Transport := preload("res://game_transport_button.gd")
const MusicRow := preload("res://library_row.gd")
var failures: Array[String] = []

func check(ok: bool, name: String) -> void:
    if not ok:
        failures.append(name)
        push_error("VISUAL_SYSTEM_FAIL: " + name)

func _initialize() -> void:
    _verify.call_deferred()

func _verify() -> void:
    var theme := Design.create()
    var host := Control.new()
    host.theme = theme
    root.add_child(host)
    var card := Design.card_surface()
    var drawer := Design.drawer_surface()
    var modal := Design.modal_surface()
    var stage := Design.stage_surface()
    check(card.bg_color == Design.PANEL and drawer.bg_color == Design.PANEL,
        "Cards and contextual drawer share one surface color")
    check(modal.bg_color == Design.PANEL_RAISED and
        modal.corner_radius_top_left >= card.corner_radius_top_left,
        "Modal rises above cards through the same elevation system")
    check(stage.bg_color == Design.STAGE,
        "Score stage has the canonical quiet background")
    check(theme.get_stylebox("normal", "LineEdit") is StyleBoxFlat and
        theme.get_stylebox("focus", "LineEdit") is StyleBoxFlat and
        theme.get_color("caret_color", "LineEdit") == Design.MINT,
        "Text fields use the canonical form and keyboard-focus style")
    check(Design.role_accent("primary") == Design.role_accent("play") and
        Design.role_accent("review") == Design.role_accent("retry") and
        Design.role_accent("settings") == Design.role_accent("listen"),
        "Ordinary controls and transport controls share semantic accent roles")
    for role in ["primary", "review", "settings", "danger", "library", "navigation"]:
        var button := ActionButton.new()
        host.add_child(button)
        button.configure(role)
        var face := button.get_theme_stylebox("normal") as StyleBoxFlat
        check(face != null and face.bg_color == Design.role_fill(role),
            "Button " + role + " uses its shared fill")
        check(button.focus_mode == Control.FOCUS_ALL and
            button.get_theme_stylebox("focus") is StyleBoxFlat,
            "Button " + role + " maintains a visible keyboard-focus style")
    var row := MusicRow.new()
    host.add_child(row)
    await process_frame
    row.set_entry("A very long music title", "MIDI · imported", "warning")
    check(row.get_meta("library_title") == "A very long music title" and
        row.title_label.get_theme_color("font_color") == Design.AMBER and
        row.detail_label.get_theme_color("font_color") == Design.SLATE,
        "Music entry typography respects common colors and source details")
    var transport := Transport.new()
    host.add_child(transport)
    transport.configure("retry")
    check(transport.AMBER == Design.role_accent("review"),
        "Transport retry matches the review accent")
    print("VISUAL_SYSTEM_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
