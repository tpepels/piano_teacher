extends "library_fixture.gd"
const OfflineApp = preload("library_application.gd").OfflineApp

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    var app := OfflineApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    var view: Control = app.screens["home"].find_child("HomeScreen",true,false)
    check(view != null,"Main mounts the independently owned Home screen")
    if view != null:
        app._on_library(0,JSON.stringify(catalog()).to_utf8_buffer())
        view.resume_button.pressed.emit()
        check(app.commands == [{"operation":"library.open","payload":{"id":"Collection/real.mid"}}]
            and app.command_state.resume_requested, "Home Continue uses the real application saved-place route")
        app._on_action(1,JSON.stringify({"error":"Unreadable"}).to_utf8_buffer())
        check(view.recent_label.text == "Unreadable", "The application presents action errors to Home through values")
        app._on_library(1,PackedByteArray())
        check(view.count_label.text == "Practice engine unavailable" and view.resume_button.disabled,
            "Worker failure is coordinated without touching Home widgets")
        app._navigate("home")
        check(app.current_screen == "practice" and not app.screens["home"].visible,
            "The legacy Home route still redirects to Practice")
        view.library_requested.emit()
        check(app.current_screen == "library", "Library intent remains application navigation")
        view.settings_requested.emit()
        check(app.current_screen == "settings" and app.settings_return_screen == "library",
            "Settings intent retains the navigation return origin")
    app.free()
    print("HOME_SCREEN_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
