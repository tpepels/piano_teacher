extends RefCounted
## One pure key-event policy for all practice and navigation shortcuts.
## It returns semantic effects; Main only invokes the same UI command ports
## used by buttons, while hardware piano keys use the backend's equivalent
## semantic command. No keyboard path chooses a musical deadline.
const PRACTICE_KEYS := [
    KEY_ESCAPE,KEY_SPACE,KEY_P,KEY_R,KEY_S,KEY_L,KEY_LEFT,KEY_RIGHT]

static func capture_action(event: InputEvent,screen: String,
        modal: bool,focused_text: bool,
        library_search_focused: bool) -> String:
    if not event is InputEventKey:
        return ""
    var key: InputEventKey = event
    if key.pressed and not key.echo and screen == "library" and \
            ((key.ctrl_pressed and key.keycode == KEY_F)
            or (key.keycode == KEY_SLASH and not library_search_focused)):
        return "focus_library_search"
    if modal or (focused_text and key.keycode not in [
            KEY_F11,KEY_ESCAPE] and not (
            key.ctrl_pressed and key.keycode == KEY_Q)):
        return ""
    if key.keycode == KEY_ESCAPE and screen in ["library","settings","lesson"]:
        return "keyboard"
    if key.keycode == KEY_F11 or key.ctrl_pressed and key.keycode == KEY_Q:
        return "keyboard"
    return "keyboard" if screen == "practice" and \
        key.keycode in PRACTICE_KEYS else ""

static func command(event: InputEvent,screen: String,source_picker: bool,
        modal: bool,focused_text: bool) -> Dictionary:
    if source_picker or not event is InputEventKey:
        return {}
    var key: InputEventKey = event
    if not key.pressed or key.echo or modal:
        return {}
    if focused_text and key.keycode not in [KEY_F11,KEY_ESCAPE] and \
            not (key.ctrl_pressed and key.keycode == KEY_Q):
        return {}
    if key.ctrl_pressed and key.keycode == KEY_Q:
        return {"kind":"exit"}
    if key.keycode == KEY_F11:
        return {"kind":"fullscreen"}
    if key.keycode == KEY_ESCAPE:
        return {"kind":"navigate",
            "target":"library" if screen == "practice" else "practice"}
    if screen != "practice":
        return {}
    if key.keycode == KEY_P and key.shift_pressed:
        return {"kind":"advanced_pause"}
    match key.keycode:
        KEY_SPACE:
            return {"kind":"primary"}
        KEY_P:
            return {"kind":"pause"}
        KEY_R:
            return {"kind":"retry"}
        KEY_L:
            return {"kind":"listen"}
        KEY_S:
            return {"kind":"command","action":"stop"}
        KEY_LEFT:
            return {"kind":"command","action":"previous"}
        KEY_RIGHT:
            return {"kind":"command","action":"next"}
    return {}
