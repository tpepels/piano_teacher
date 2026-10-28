extends SceneTree

var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("LIBRARY_SCREEN_FAIL:", message)

func catalog() -> Dictionary:
    return {"last_piece":"Collection/real.mid", "folder":"/music", "count":2,
        "pieces":[
            {"id":"other.mid", "title":"Second Tune", "format":"MIDI", "folder":"Quiet"},
            {"id":"Collection/real.mid", "title":"A Real Long Title", "format":"MIDI", "folder":"Collection"}],
        "warmups":[{"id":"warmup:chords", "title":"Chord Changes", "bpm":68, "focus":"Triads"}]}

func control(view: Node, key: String) -> Node:
    return view.find_child(key, true, false)

func entries(view: Node) -> Array[Button]:
    var found: Array[Button] = []
    for node in view.find_children("*", "Button", true, false):
        if node.has_meta("library_title"):
            found.append(node)
    return found

func titles(view: Node) -> Array:
    var result: Array = []
    for row in entries(view):
        result.append(row.get_meta("library_title"))
    return result

func search(view: Node, query: String) -> void:
    var field: LineEdit = control(view, "LibrarySearch")
    field.text = query
    field.text_changed.emit(query)
