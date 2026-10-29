extends RefCounted

# Caption slots reserve stable score height across transport phase changes.
static func create(caption: Label, lines: int, feedback: bool) -> Control:
    var slot := Control.new()
    slot.name = "FeedbackCaption" if feedback else "InstructionCaption"
    slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    slot.clip_contents = true
    caption.set_meta("caption_lines", lines)
    caption.max_lines_visible = lines
    caption.mouse_filter = Control.MOUSE_FILTER_PASS
    caption.clip_text = true
    caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    caption.autowrap_mode = (TextServer.AUTOWRAP_OFF if lines == 1
        else TextServer.AUTOWRAP_WORD_SMART)
    slot.add_child(caption)
    caption.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    return slot

static func resize(captions: Array) -> void:
    for caption in captions:
        var lines: int = int(caption.get_meta("caption_lines", 1))
        var font: Font = caption.get_theme_font("font")
        var font_size: int = caption.get_theme_font_size("font_size")
        var line_spacing: int = caption.get_theme_constant("line_spacing")
        caption.get_parent().custom_minimum_size.y = ceilf(
            font.get_height(font_size) * lines + line_spacing * (lines - 1))
