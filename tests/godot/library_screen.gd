extends "library_fixture.gd"

func test_catalog_signals(view: Control) -> void:
    view.present_catalog(catalog())
    check(titles(view) == ["A Real Long Title", "Second Tune", "Chord Changes"],
        "Recent music leads the catalog without a duplicate ordinary row")
    var requests: Array = []
    view.open_requested.connect(func(identifier: String, resume_saved: bool):
        requests.append([identifier, resume_saved]))
    var rows := entries(view)
    rows[0].pressed.emit()
    rows[1].pressed.emit()
    rows[2].pressed.emit()
    check(requests == [["Collection/real.mid",true],["other.mid",false],["warmup:chords",false]],
        "Rows emit exact source identifiers and distinguish saved continuation")
    check(rows[0].tooltip_text.contains("Continue from saved place") and rows[0].tooltip_text.contains("Collection"),
        "Recent row keeps its complete metadata")
    var intents: Array = []
    view.refresh_requested.connect(func(): intents.append("refresh"))
    view.health_check_requested.connect(func(): intents.append("health"))
    control(view, "LibraryRefresh").pressed.emit()
    control(view, "LibraryHealthButton").pressed.emit()
    check(intents == ["refresh","health"], "Utilities emit intent without networking")

func test_search_debounce(view: Control) -> void:
    view.present_catalog(catalog())
    # Let startup/font loading leave the frame delta before measuring timers.
    await create_timer(.2).timeout
    await process_frame
    var original := entries(view)[0].get_instance_id()
    for query in ["REAL LONG", "collection", "triads"]:
        search(view, query)
        await create_timer(.08).timeout
        check(not entries(view).is_empty() and entries(view)[0].get_instance_id() == original,
            "Typing does not rebuild rows before the 120 ms quiet period")
    await create_timer(.17).timeout
    check(titles(view) == ["Chord Changes"], "Only the final query filters title/folder/focus")
    for query in ["REAL LONG", "collection"]:
        search(view, query)
        await create_timer(.17).timeout
        check(titles(view) == ["A Real Long Title"], "Search matches title and folder without pinning unrelated recent music")
    search(view, "no matching song")
    await create_timer(.17).timeout
    check(entries(view).is_empty() and control(view, "LibraryMessage").text.contains("No matches"),
        "Empty search results explain how to recover")
    view.focus_search(true)
    check(root.gui_get_focus_owner() == control(view, "LibrarySearch"), "Search focus belongs to the screen")

func test_health_rows(view: Control) -> void:
    view.present_catalog(catalog())
    var before := entries(view)[0].get_instance_id()
    view.present_health({"started":true,"running":true,"checked":1,"total":3,
        "items":{"Collection/real.mid":{"status":"warning","message":"Meter repaired","notes":8,"measures":4}}})
    check(entries(view)[0].get_instance_id() != before, "Starting a scan refreshes row diagnoses once")
    var scanning := entries(view)[0].get_instance_id()
    entries(view)[0].grab_focus()
    view.present_health({"started":true,"running":true,"checked":2,"total":3,
        "items":{"Collection/real.mid":{"status":"error","message":"Unreadable"}}})
    check(entries(view)[0].get_instance_id() == scanning
            and root.gui_get_focus_owner() == entries(view)[0],
        "Per-file progress preserves actual row instances and focus")
    check(control(view, "LibraryHealthButton").disabled and control(view, "LibraryHealthLabel").text.contains("2 of 3"),
        "Progress updates the small summary and prevents duplicate checks")
    view.present_health({"started":true,"running":false,"checked":3,"total":3,"error":1,
        "items":{"Collection/real.mid":{"status":"error","message":"Unreadable"}}})
    check(entries(view)[0].get_instance_id() != scanning,
        "Finishing a scan refreshes final row diagnoses once")
    check(entries(view)[0].get_meta("library_status") == "error" and entries(view)[0].tooltip_text.contains("Unreadable"),
        "Final file failures stay attached to their real entry")
    check(not control(view, "LibraryHealthButton").disabled and control(view, "LibraryHealthButton").text == "Recheck files",
        "Finished scans remain repeatable")
    var completed := entries(view)[0].get_instance_id()
    view.present_health({"started":true,"running":true,"checked":0,"total":3,
        "items":{"Collection/real.mid":{"status":"warning","message":"Checking again"}}})
    check(entries(view)[0].get_instance_id() != completed
            and entries(view)[0].get_meta("library_status") == "warning",
        "Starting a recheck refreshes rows once, just like the first scan")

func test_errors_resize(view: Control) -> void:
    view.present_catalog(catalog())
    view.apply_viewport(Vector2(800,600),1.0)
    view.present_open_status("Cannot open selected music: Pause rejected",true)
    view.present_catalog(catalog())
    view.apply_viewport(Vector2(1536,960),1.0)
    view.apply_viewport(Vector2(800,600),1.0)
    var message: Label = control(view,"LibraryMessage")
    check(message.visible and message.text.contains("Pause rejected"),
        "Catalog refresh and compact resize cannot erase or hide an open failure")
    check(message.get_theme_color("font_color") == Color("#FF8B82"), "Import failures keep their error treatment")
    view.present_open_status("Opening score…")
    check(message.get_theme_color("font_color") != Color("#FF8B82"),
        "A new selection clears the preceding import error treatment")
    view.present_open_status("")
    search(view,"no matching song")
    await create_timer(.17).timeout
    view.apply_viewport(Vector2(1536,960),1.0)
    view.apply_viewport(Vector2(800,600),1.0)
    check(message.visible and message.text.contains("No matches"),
        "Compact resize retains an empty-result explanation")
    view.present_health_message("Cannot check music files: offline")
    check(control(view,"LibraryHealthLabel").visible and control(view,"LibraryHealthLabel").text.contains("offline"),
        "Health request failures have an owned visible status")

func test_request_recovery(view: Control) -> void:
    check(view.has_method("present_request_error"), "Library distinguishes transient request failures from import failures")
    if not view.has_method("present_request_error"):
        return
    view.present_catalog(catalog())
    view.present_request_error("Practice engine unavailable")
    check(control(view,"LibraryMessage").visible and control(view,"LibraryMessage").text.contains("unavailable"),
        "A failed catalog request stays visible beside the catalog")
    view.present_catalog(catalog())
    check(not control(view,"LibraryMessage").text.contains("unavailable"),
        "A successful catalog response clears a transient request failure")
    view.present_open_status("Cannot open score: Unreadable file",true)
    view.present_catalog(catalog())
    check(control(view,"LibraryMessage").text.contains("Unreadable file"),
        "Successful catalog responses retain the independent import failure")

func test_snapshots(view: Control) -> void:
    var listing := catalog()
    view.present_catalog(listing)
    listing.pieces.clear()
    listing.warmups.clear()
    search(view,"collection")
    await create_timer(.17).timeout
    check(titles(view) == ["A Real Long Title"], "The screen captures catalog values before deferred filtering")
    var health := {"started":true,"running":true,"items":{"Collection/real.mid":{"status":"warning","message":"Repaired"}}}
    view.present_health(health)
    health.items["Collection/real.mid"].status = "error"
    search(view,"")
    await create_timer(.17).timeout
    check(entries(view)[0].get_meta("library_status") == "warning",
        "Caller mutation cannot change captured health diagnoses")

func test_empty_recent(view: Control) -> void:
    var listing := catalog()
    listing.last_piece = "missing.mid"
    view.present_catalog(listing)
    check(titles(view) == ["Second Tune","A Real Long Title","Chord Changes"],
        "A missing recent identifier creates no broken Continue action")
    listing.last_piece = "warmup:chords"
    view.present_catalog(listing)
    check(titles(view) == ["Chord Changes","Second Tune","A Real Long Title"],
        "Warm-up recent music uses its catalog title and appears once")
    view.present_catalog({"pieces":[],"warmups":[],"error":"Music folder unavailable"})
    view.apply_viewport(Vector2(800,600),1.0)
    check(control(view,"LibraryMessage").visible and control(view,"LibraryMessage").text == "Music folder unavailable",
        "Catalog errors take precedence over the empty-library message")
    view.present_catalog({"pieces":[],"warmups":[]})
    check(control(view,"LibraryMessage").text.contains("No scores yet"), "An empty library offers recovery guidance")

func run() -> void:
    var scenario := OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    if not ResourceLoader.exists("res://library_screen.gd"):
        check(false,"Standalone Library screen contract is not implemented")
    else:
        var view = load("res://library_screen.gd").new()
        view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(view)
        await process_frame
        match scenario:
            "catalog_signals": test_catalog_signals(view)
            "search_debounce": await test_search_debounce(view)
            "health_rows": test_health_rows(view)
            "errors_resize": await test_errors_resize(view)
            "request_recovery": test_request_recovery(view)
            "snapshots": await test_snapshots(view)
            "empty_recent": test_empty_recent(view)
        view.free()
    print("LIBRARY_SCREEN_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
