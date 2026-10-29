extends SceneTree

const NavigationDrawer := preload("res://navigation_drawer.gd")
const ActionButton := preload("res://action_button.gd")
const EventWindow := preload("res://notation/native/event_window.gd")
const SourceVisibility := preload("res://notation/native/source_visibility.gd")
const EngravingReadiness := preload("res://notation/native/engraving_readiness.gd")

class TestFrame:
    extends RefCounted
    func event_visible(event: Dictionary) -> bool:
        return not bool(event.get("hidden", false))

class MockLayout:
    extends RefCounted
    var notation_tuplets: Array = []
    var chord_members: Dictionary = {}
    var beamed_note_ids: Dictionary = {}
    var tie_pairs: Array = []

class MockGlyphs:
    extends RefCounted
    var beam_textures: Dictionary = {}
    var slur_metadata: Dictionary = {}
    func slur_note_ids(_key: String) -> Array:
        return []

var chosen := ""

func _button(label: String, callback: Callable, _primary: bool, _role: String) -> Button:
    var button := ActionButton.new()
    button.text = label
    button.configure(_role)
    button.pressed.connect(callback)
    return button

func _navigate(destination: String) -> void:
    chosen = destination

func _exit_app() -> void:
    chosen = "exit"

func _initialize() -> void:
    var failures := 0
    var host := Control.new()
    root.add_child(host)
    var screens: Dictionary = {}
    for name in ["library", "settings", "lesson"]:
        var page := MarginContainer.new()
        host.add_child(page)
        screens[name] = page
    var drawer = NavigationDrawer.new()
    drawer.mount(host, screens, _button, _navigate, _exit_app)
    drawer.resize(Vector2(1200, 800))
    if not is_equal_approx(drawer.drawer.offset_left, 18.0):
        failures += 1
    if screens["lesson"].get_parent() == host:
        failures += 1
    drawer.present("library", "practice")
    if not drawer.root.visible or not drawer.navigation["library"].is_selected:
        failures += 1
    drawer.navigation["settings"].emit_signal("pressed")
    if chosen != "settings":
        failures += 1
    drawer.present("practice", "library")
    if drawer.root.visible:
        failures += 1
    drawer.resize(Vector2(900, 650))
    if not is_equal_approx(drawer.drawer.offset_left, 8.0):
        failures += 1

    var events: Array = [
        {"id":"a", "beat":0.0},
        {"id":"b", "beat":1.0, "hidden":true},
        {"id":"c", "beat":2.0},
        {"id":"d", "beat":3.0}]
    var visible: Array = EventWindow.visible(events, .9, 2.0, TestFrame.new())
    if visible.size() != 1 or visible[0]["id"] != "c":
        failures += 1
    var gap := {"duration_beats":1.0,"start_beat":3.0,"end_beat":4.0}
    var measures: Array = [{"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0}]
    var previous: Dictionary = SourceVisibility.practice_context_before(
        8.0, 8.0, measures, gap)
    if previous.get("start_beat") != 7.0 or gap["start_beat"] != 3.0:
        failures += 1
    var copied: Dictionary = SourceVisibility.practice_context_before(
        10.0, 8.0, measures, gap)
    if copied.get("start_beat") != 8.0 or copied.get("end_beat") != 12.0:
        failures += 1

    var glyphs := MockGlyphs.new()
    var layout := MockLayout.new()
    if EngravingReadiness.missing(layout,glyphs,RefCounted.new(),
            ["beam1"],true,[],true) != "Missing original Verovio beam: beam1":
        failures += 1
    glyphs.beam_textures["beam1"] = true
    if EngravingReadiness.missing(layout,glyphs,RefCounted.new(),
            ["beam1"],true,[],true) != "":
        failures += 1
    print("NATIVE_REFACTOR_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
