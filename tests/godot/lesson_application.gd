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
        app._on_state(0,200,PackedStringArray(),JSON.stringify(values).to_utf8_buffer())
        check(app.lesson_calls == 1,"Application routes lesson demand to its HTTP boundary")
        app._on_lesson(0,200,PackedStringArray(),JSON.stringify({"piece_fingerprint":"song","steps":[{"number":1},{"number":2}],"total_steps":2}).to_utf8_buffer())
        press(view,"Next passage")
        check(app.posts.back() == {"path":"/control","payload":{"action":"next"}} and app.current_screen == "practice", "Lesson command and navigation signals use real application routing")
        app.action_pending = false
        app.last_post_path = "/control"
        app.last_control_action = "reset_path"
        app._on_action(0,200,PackedStringArray(),JSON.stringify(values).to_utf8_buffer())
        check(app.lesson_calls == 2,"Reset invalidates the lesson session through the real acknowledgement route")
        app.action_pending = false
        app._on_lesson(0,200,PackedStringArray(),JSON.stringify({"piece_fingerprint":"song","steps":[{"number":1},{"number":2}]}).to_utf8_buffer())
        app.lesson_steps.picker.item_selected.emit(1)
        check(app.posts.back().payload == {"action":"select_step","number":2}, "Practice step selection routes an explicit numeric command")
    app.free()
    print("LESSON_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
func press(view: Node, caption: String) -> void:
    for button in view.find_children("*","Button",true,false):
        if button.text == caption:
            button.pressed.emit()
            return
    check(false,"Missing Lesson action: " + caption)
