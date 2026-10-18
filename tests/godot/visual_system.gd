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
    check(card.bg_color == Design.PANEL and drawer.bg_color == Design.FOREST,
        "Cards sit on the forest navigation shell through the shared palette")
    check(drawer.bg_color == Color("#1E3A34") and card.bg_color == Color("#2D3532")
        and modal.bg_color == Color("#2E4D46"),
        "Rendered surfaces retain the approved forest, charcoal and pine palette")
    check(modal.bg_color == Design.PANEL_RAISED and
        modal.corner_radius_top_left >= card.corner_radius_top_left,
        "Modal rises above cards through the same elevation system")
    check(stage.bg_color == Design.STAGE and
        Design.STAGE.get_luminance() < .25 and
        Design.SCORE_INK.get_luminance() > .8 and
        Design.FOREST.get_luminance() < .25,
        "Score has luminous ink on the dark stage and forest shell")
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
        var expected: Color = Design.role_fill(role)
        check(face != null and face.bg_color == expected,
            "Button " + role + " uses its shared fill")
        check(button.focus_mode == Control.FOCUS_ALL and
            button.get_theme_stylebox("focus") is StyleBoxFlat,
            "Button " + role + " maintains a visible keyboard-focus style")
    var row := MusicRow.new()
    host.add_child(row)
    await process_frame
    row.set_entry("A very long music title", "MIDI · imported")
    check(row.title_label.get_theme_color("font_color") == Color("#C4CDC6")
        and row.detail_label.get_theme_color("font_color") == Color("#8B9A92"),
        "Real music tiles use approved stone titles and slate metadata")
    var title_face: Font = row.title_label.get_theme_font("font")
    var detail_face: Font = row.detail_label.get_theme_font("font")
    check(title_face.get_font_name().to_lower().contains("serif")
        and title_face.get_font_name() != detail_face.get_font_name(),
        "Music titles resolve to an available serif face distinct from interface metadata")
    row.set_entry("A very long music title", "MIDI · imported", "warning")
    check(row.get_meta("library_title") == "A very long music title" and
        row.title_label.get_theme_color("font_color") == Design.AMBER and
        row.detail_label.get_theme_color("font_color") == Design.SLATE,
        "Music entry typography respects common colors and source details")
    var transport := Transport.new()
    host.add_child(transport)
    transport.configure("retry")
    check(Design.role_fill("retry") == Design.role_fill("listen")
        and Design.role_fill("play") != Design.role_fill("retry"),
        "Secondary transport shares a neutral surface while Play retains the single accent")
    print("VISUAL_SYSTEM_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
