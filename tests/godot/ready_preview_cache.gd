extends SceneTree

func _initialize() -> void:
    var view = load("res://notation/native/view.gd").new()
    view.size = Vector2(900,500)
    view.set_density(96.0)
    view.active_hand = "right"
    for index in range(18058):
        view.layout.ordered_events.append({"kind":"note","staff":"right",
            "beat":8.0+float(index)*.25})
    var initial: float = view.displayed_scroll_beat()
    var start := Time.get_ticks_usec()
    for index in range(120):
        assert(view.displayed_scroll_beat() == initial)
    var elapsed := Time.get_ticks_usec()-start
    # A cached display projection should be negligible compared with a frame.
    # This generous aggregate bound catches a complete 18k-note scan per poll.
    if elapsed > 300000:
        print("READY_PREVIEW_CACHE_FAIL:120 queries took ",elapsed,"us")
        view.free()
        quit(1)
        return
    view.size.x = 1800.0
    assert(view.displayed_scroll_beat() == 0.0)
    view.size.x = 900.0
    view.set_density(300.0)
    assert(view.displayed_scroll_beat() > initial)
    view.play_from_beat = 8.0
    assert(view.displayed_scroll_beat() == 8.0)
    view.active_hand = "left"
    view.play_from_beat = 0.0
    assert(view.displayed_scroll_beat() == 0.0)
    view.active_hand = "right"
    assert(view.displayed_scroll_beat() > 0.0)
    view.clear_score()
    assert(view.displayed_scroll_beat() == 0.0)
    view.free()
    print("READY_PREVIEW_CACHE_OK")
    quit()
