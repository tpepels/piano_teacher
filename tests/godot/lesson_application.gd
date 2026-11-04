extends "library_fixture.gd"
class App extends "library_application.gd".OfflineApp:
    var lesson_calls := 0
    func _request_lesson() -> void: lesson_calls += 1
func run() -> void:
    var app := App.new()
    root.add_child(app)
    await process_frame
    var view: Control = app.screens["lesson"].find_child("LessonScreen",true,false)
    check(view != null,"Application mounts the independent Lesson screen")
    if view != null:
        var values := {"loaded":true,"piece_fingerprint":"song","lesson_step":1,"hands":["right"],"hand":"right","phase":"ready"}
        app.last_state = values
        app._on_state(0,JSON.stringify(values).to_utf8_buffer())
        check(app.lesson_calls == 1,"Application routes lesson demand to its typed request boundary")
        app._on_lesson(0,JSON.stringify({"piece_fingerprint":"song","steps":[{"number":1},{"number":2}],"total_steps":2}).to_utf8_buffer())
        press(view,"Next passage")
        check(app.commands.back() == {"operation":"practice.command","payload":{"action":"next"}} and app.current_screen == "practice", "Lesson command and navigation signals use real application routing")
        app._on_action(0,JSON.stringify(values).to_utf8_buffer())
        app._send_action({"action":"reset_path","fingerprint":"song","confirm":true})
        app._on_action(0,JSON.stringify(values).to_utf8_buffer())
        check(app.lesson_calls == 2,"Reset invalidates the lesson session through the real acknowledgement route")
        app._on_lesson(0,JSON.stringify({"piece_fingerprint":"song","steps":[{"number":1},{"number":2}]}).to_utf8_buffer())
        view.steps.picker.item_selected.emit(1)
        check(app.commands.back().payload == {"action":"select_step","number":2}, "Lesson Path selection routes an explicit numeric command")
    app.free()
    print("LESSON_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
func press(view: Node, caption: String) -> void:
    for button in view.find_children("*","Button",true,false):
        if button.text == caption:
            button.pressed.emit()
            return
    check(false,"Missing Lesson action: " + caption)
