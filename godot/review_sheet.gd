extends AcceptDialog

# Detailed, scrollable explanation of the authoritative note assessment.
# No timing or scoring decisions are made here.
signal retry_requested(first_bar: int, last_bar: int)

var summary_label: Label
var section_list: VBoxContainer
var active_report: Dictionary = {}


func _ready() -> void:
    title = "Review your playing"
    ok_button_text = "Close"
    min_size = Vector2i(520, 320)
    var root := VBoxContainer.new()
    root.add_theme_constant_override("separation", 12)
    add_child(root)
    summary_label = Label.new()
    summary_label.add_theme_font_size_override("font_size", 19)
    summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    summary_label.custom_minimum_size.y = 65
    root.add_child(summary_label)
    var scroll := ScrollContainer.new()
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    scroll.custom_minimum_size = Vector2(460, 260)
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    root.add_child(scroll)
    section_list = VBoxContainer.new()
    section_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    section_list.add_theme_constant_override("separation", 12)
    scroll.add_child(section_list)


func _line(text: String, font_size: int = 16, muted: bool = false) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_font_size_override("font_size", font_size)
    label.add_theme_color_override("font_color", Color("#A7B9B0") if muted else Color("#E7EAE5"))
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return label


func _issue_text(issue: Dictionary) -> String:
    var bar: int = int(issue.get("bar", 0))
    var pitch: String = str(issue.get("name", "?"))
    var status: String = str(issue.get("status", ""))
    var prefix := "Measure %d · " % bar
    match status:
        "missed":
            return prefix + "Missed " + pitch
        "wrong":
            var actual: String = str(issue.get("played_name", ""))
            return prefix + ("Expected %s, played %s" % [pitch, actual] if not actual.is_empty()
                else "Wrong pitch instead of " + pitch)
        "early":
            return prefix + pitch + " was early"
        "late":
            return prefix + pitch + " was late"
        "short":
            return prefix + pitch + " released too soon"
        "long":
            return prefix + pitch + " held too long"
        "extra":
            return prefix + "Extra key " + pitch
        _:
            return prefix + pitch + " · " + status


func open_review(report: Dictionary) -> void:
    active_report = report
    summary_label.text = "%.0f%% correct · %d of %d notes\n%d missed · %d wrong · %d extra · %d timing/duration errors" % [
        float(report.get("accuracy_percent", 0)), int(report.get("correct", 0)),
        int(report.get("total", 0)), int(report.get("missed", 0)),
        int(report.get("wrong", 0)), int(report.get("extra_notes", 0)),
        int(report.get("early", 0)) + int(report.get("late", 0))
            + int(report.get("short", 0)) + int(report.get("long", 0))]
    for old in section_list.get_children():
        section_list.remove_child(old)
        old.queue_free()
    var sections: Array = report.get("sections", [])
    if sections.is_empty():
        section_list.add_child(_line("No note errors were detected in this attempt.", 18))
    for index in range(mini(sections.size(), 15)):
        var section: Dictionary = sections[index]
        var panel := PanelContainer.new()
        var style := StyleBoxFlat.new()
        style.bg_color = Color("#294139")
        style.set_corner_radius_all(7)
        style.set_content_margin_all(12)
        panel.add_theme_stylebox_override("panel", style)
        section_list.add_child(panel)
        var content := VBoxContainer.new()
        content.add_theme_constant_override("separation", 6)
        panel.add_child(content)
        var first: int = int(section.get("first_bar", 0))
        var last: int = int(section.get("last_bar", first))
        var measure_text := "Measure %d" % first if first == last else "Measures %d–%d" % [first, last]
        content.add_child(_line("%s · %d errors" % [measure_text, int(section.get("errors", 0))], 20))
        var issues: Array = section.get("issues", [])
        for issue_index in range(mini(issues.size(), 10)):
            content.add_child(_line(_issue_text(issues[issue_index]), 16, true))
        if issues.size() > 10:
            content.add_child(_line("…and %d additional notes" % (issues.size()-10), 15, true))
        var repeat_button := Button.new()
        repeat_button.text = "Repeat " + measure_text
        repeat_button.custom_minimum_size.y = 50
        repeat_button.add_theme_font_size_override("font_size", 17)
        repeat_button.pressed.connect(_repeat_section.bind(first, last))
        content.add_child(repeat_button)
    if sections.size() > 15:
        section_list.add_child(_line("%d additional sections not shown here." % (sections.size()-15), 16, true))
    var viewport: Vector2 = get_tree().root.size
    popup_centered(Vector2i(
        int(maxf(300.0, minf(720.0, viewport.x - 32.0))),
        int(maxf(300.0, minf(650.0, viewport.y - 32.0)))))


func _repeat_section(first_bar: int, last_bar: int) -> void:
    hide()
    retry_requested.emit(first_bar, last_bar)
