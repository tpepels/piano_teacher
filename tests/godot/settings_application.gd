extends "library_fixture.gd"
const OfflineApp = preload("library_application.gd").OfflineApp

func click(view: Control, caption: String) -> void:
    for node in view.find_children("*","Button",true,false):
        if node.text == caption:
            node.pressed.emit()
            return
    check(false,"Missing Settings action: " + caption)

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    var app := OfflineApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    var view: Control = app.settings_view
    check(view.has_method("present_preferences"),"Application Settings presentation is independent")
    if view.has_method("present_preferences"):
        app._on_settings(0,JSON.stringify(
            {"music_dir":"/scores","fullscreen":false,"metronome":false}).to_utf8_buffer())
        check(view.folder_edit.text == "/scores" and not view.metronome_toggle.button_pressed,
            "Main presents backend preferences through the value contract")
        view.folder_edit.text = "  /chosen  "
        click(view,"Save folder")
        check(app.commands.back() == {"operation":"settings.update","payload":{"music_dir":"/chosen"}},
            "Folder intent sends the exact trimmed value to the typed settings operation")
        app._on_action(0,JSON.stringify({}).to_utf8_buffer())
        view.tempo_setting.value = 112
        view.apply_tempo_button.pressed.emit()
        check(app.commands.back() == {"operation":"practice.command","payload":{"action":"tempo","bpm":112}},
            "Tempo intent sends the exact existing command")
        app._on_action(0,JSON.stringify({}).to_utf8_buffer())
        app._navigate("settings")
        app.device_menu_requested = true
        app._on_devices(0,JSON.stringify({"devices":["Piano A","Piano B"]}).to_utf8_buffer())
        check(view.device_menu.visible and view.device_menu.get_item_text(3) == "Piano B",
            "A requested chooser opens only with the fresh device response")
        view.device_menu.hide()
        view.device_menu.id_pressed.emit(1)
        check(app.commands.back() == {"operation":"midi.device.select","payload":{"name":"Piano B"}},
            "Device selection dispatches the captured name rather than a main-owned widget index")
        app._on_action(0,JSON.stringify({}).to_utf8_buffer())
        app._on_settings(0,JSON.stringify(
            {"music_dir":"/scores","fullscreen":false,"midi_device":"Piano A"}).to_utf8_buffer())
        check(app.commands.back() == {"operation":"midi.device.select","payload":{"name":"Piano A"}},
            "Saved-device restoration remains in application coordination")
        app._on_action(1,JSON.stringify({"error":"Device unavailable"}).to_utf8_buffer())
        check(view.settings_message.text == "Device unavailable", "Worker failures remain visible in Settings")
        app._send_action({"action":"tempo","bpm":112})
        app._process(0.0)
        check(view.apply_tempo_button.disabled, "Main supplies busy values to the screen")
        app._on_action(0,JSON.stringify({}).to_utf8_buffer())
        app._process(0.0)
        check(not view.apply_tempo_button.disabled, "Main supplies the acknowledged busy value")
    app.free()
    print("SETTINGS_OWNERSHIP_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
