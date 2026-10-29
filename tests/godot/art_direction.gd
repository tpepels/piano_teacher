extends SceneTree
## Actual application composition: HTTP/native review, or server-free geometry.
## Only geometry mode supplies state. Screenshots always use main.tscn unchanged.

class GeometryApp extends "res://main.gd":
    # Keep production _ready(), theme, controls, resize and response handlers.
    # Suppress the wire, not the scene. Never claim native readiness here.
    var network_requests := 0

    func _poll() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_library() -> void:
        pass

    func _request_library_health() -> void:
        pass

    func _request_lesson() -> void:
        _on_lesson(0, 200, PackedStringArray(), JSON.stringify({
            "current_step": 1, "completed_steps": 0, "total_steps": 3,
            "steps": [{"number": 1, "exercise": 1, "hand": "right", "level": "original",
                "kind": "practice", "first_bar": 9, "last_bar": 12}]
        }).to_utf8_buffer())

    func _request_layout() -> void:
        pass

    func _request_timeline_model() -> void:
        pass

    func _send_post(_path: String, _payload: Dictionary) -> void:
        network_requests += 1
        push_error("ART_DIRECTION_UNEXPECTED_HTTP: " + _path)

var app: Control
var config: Dictionary = {}
var captures: Array = []
var failures: Array[String] = []
var output := ""
var dimensions := Vector2i(1920, 1080)
var geometry_only := false
var render := false
var deadline_ms := 0
var workflow_checks: Array[String] = []
var workflow_captures: Array = []
const EPSILON := 2.0

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, detail: String) -> void:
    if not ok:
        failures.append(detail)
        print("ART_DIRECTION_FAIL:", detail)

func write_report() -> void:
    if output.is_empty():
        return
    var report := {"schema_version": 1, "mode": "geometry" if geometry_only else "http",
        "scene": "res://main.tscn", "viewport": [root.size.x, root.size.y],
        "window_mode": root.mode,
        "window_geometry": window_geometry(),
        "display_server": DisplayServer.get_name(), "render": render,
        "network_requests": int(app.get("network_requests")) if geometry_only and app != null else -1,
        "captures": captures, "failures": failures,
        "exercise_controls": bool(config.get("exercise_controls", false)),
        "native_input": bool(config.get("native_input", false)),
        "workflow_checks": workflow_checks, "workflow_captures": workflow_captures}
    var file := FileAccess.open(output.path_join("art-direction.json"), FileAccess.WRITE)
    if file == null:
        push_error("Cannot write art-direction.json: " + error_string(FileAccess.get_open_error()))
        return
    file.store_string(JSON.stringify(report, "  "))
    file.close()

func wait_until(predicate: Callable, label: String) -> bool:
    var step_deadline: int = mini(deadline_ms, Time.get_ticks_msec() + 60000)
    while not predicate.call():
        if Time.get_ticks_msec() >= step_deadline:
            check(false, "Timed out waiting for " + label + ": " + JSON.stringify(native_status()))
            write_report()
            return false
        await process_frame
    return true

func screen_transform(control: Control) -> Transform2D:
    # Includes Window content scaling in headless and visible display servers.
    return root.get_final_transform() * control.get_global_transform_with_canvas()

func screen_rect(control: Control) -> Rect2:
    return screen_transform(control) * Rect2(Vector2.ZERO, control.size)

func rect_data(rectangle: Rect2) -> Dictionary:
    return {"x": rectangle.position.x, "y": rectangle.position.y,
        "width": rectangle.size.x, "height": rectangle.size.y}

func fits(rectangle: Rect2, container: Rect2) -> bool:
    return rectangle.has_area() and container.grow(EPSILON).encloses(rectangle)

func overlaps(first: Rect2, second: Rect2) -> bool:
    var intersection := first.intersection(second)
    return intersection.size.x > EPSILON and intersection.size.y > EPSILON

func scroll_ancestor(control: Control) -> bool:
    var ancestor := control.get_parent()
    while ancestor != null and ancestor != app:
        if ancestor is ScrollContainer:
            return true
        ancestor = ancestor.get_parent()
    return false

func exposed_rect(control: Control) -> Rect2:
    var result := screen_rect(control).intersection(Rect2(Vector2.ZERO, Vector2(root.size)))
    var ancestor := control.get_parent()
    while ancestor != null:
        if ancestor is Control and ancestor.clip_contents:
            result = result.intersection(screen_rect(ancestor))
        ancestor = ancestor.get_parent()
    return result

func interactive(control: Control) -> bool:
    return control is BaseButton or control is LineEdit or control is SpinBox or control is Slider

func collect_controls(node: Node, result: Array) -> void:
    if node is Control and not node.is_visible_in_tree():
        return
    if node is Control and interactive(node):
        # SpinBox's LineEdit and a custom button's children are one hit target.
        result.append(node)
        return
    for child in node.get_children():
        if not child is Window:
            collect_controls(child, result)

func active_controls() -> Array:
    var result: Array = []
    collect_controls(app.screens[app.current_screen], result)
    if app.current_screen != "practice":
        collect_controls(app.navigation_rail, result)
    return result

func collect_captions(node: Node, result: Array) -> void:
    if node is Control and not node.is_visible_in_tree():
        return
    if node is Label and not node.text.strip_edges().is_empty():
        result.append(node)
    for child in node.get_children():
        if not child is Window:
            collect_captions(child, result)

func caption_metrics(caption: Label) -> Dictionary:
    var font: Font = caption.get_theme_font("font")
    var font_size: int = caption.get_theme_font_size("font_size")
    var words := caption.text.replace("\n", " ").replace("\r", " ").replace("\t", " ").split(" ", false)
    var longest_word := ""
    var longest_width := 0.0
    for word in words:
        var width: float = font.get_string_size(word, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
        if width > longest_width:
            longest_width = width
            longest_word = word
    var padding := Vector2.ZERO
    if caption.has_theme_stylebox("normal"):
        padding = caption.get_theme_stylebox("normal").get_minimum_size()
    var scale: Vector2 = screen_transform(caption).get_scale().abs()
    return {"path": str(app.get_path_to(caption)), "text": caption.text,
        "rect": rect_data(screen_rect(caption)), "longest_word": longest_word,
        "longest_word_width": longest_width * scale.x,
        "text_width": font.get_string_size(caption.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x * scale.x,
        "content_width": maxf(0.0, caption.size.x - padding.x) * scale.x,
        "line_height": font.get_height(font_size) * scale.y,
        "line_count": caption.get_line_count(), "word_count": words.size(),
        "wraps": caption.autowrap_mode != TextServer.AUTOWRAP_OFF,
        "explicit_line_breaks": caption.text.contains("\n"),
        # Long music titles deliberately use ellipsis; ordinary captions do not.
        "allows_truncation": caption.clip_text or caption.text_overrun_behavior != TextServer.OVERRUN_NO_TRIMMING}

func check_captions(label: String) -> Array:
    var captions: Array = []
    collect_captions(app.screens[app.current_screen], captions)
    if app.current_screen != "practice":
        collect_captions(app.navigation_rail, captions)
    var metrics: Array = []
    for caption in captions:
        if not exposed_rect(caption).has_area():
            continue
        var measured := caption_metrics(caption)
        metrics.append(measured)
        if bool(measured["allows_truncation"]):
            continue
        check(float(measured["content_width"]) + EPSILON >= float(measured["longest_word_width"]),
            "%s: caption fits its longest word '%s': %s (%.1f < %.1f px)" % [label,
                measured["longest_word"], measured["path"], measured["content_width"], measured["longest_word_width"]])
        if bool(measured["wraps"]) and not bool(measured["explicit_line_breaks"]):
            check(int(measured["line_count"]) <= int(measured["word_count"]),
                label + ": caption cannot wrap individual characters into extra lines: " + str(measured["path"]))
    return metrics

func single_line_height_budget(control: Control) -> float:
    var text_control: Control = control.get_line_edit() if control is SpinBox else control
    var font: Font = text_control.get_theme_font("font")
    var font_size: int = text_control.get_theme_font_size("font_size")
    # Natural text height plus theme padding, with room for a 36-40px input.
    # Do not derive this limit from a wrapped Label's allocated/minimum height.
    var padding := 24.0
    if text_control.has_theme_stylebox("normal"):
        padding = maxf(padding, text_control.get_theme_stylebox("normal").get_minimum_size().y)
    return ceilf(font.get_height(font_size)) + padding

func check_settings_rows(label: String) -> Dictionary:
    var all_captions: Array = []
    collect_captions(app.screens["settings"], all_captions)
    var metrics := {}
    for item in [["target_tempo", "Target tempo", app.settings_view.tempo_setting],
            ["piano_volume", "Piano volume", app.settings_view.listen_volume_slider]]:
        var control: Control = item[2]
        var caption: Label
        for candidate in all_captions:
            if candidate.text == item[1]:
                caption = candidate
                break
        check(caption != null, label + ": settings caption exists: " + str(item[1]))
        if caption == null:
            continue
        var row: Control = control.get_parent()
        var budget := single_line_height_budget(control)
        for child in row.get_children():
            if child is Control and child.is_visible_in_tree():
                budget = maxf(budget, single_line_height_budget(child))
        var height_limit: float = budget * screen_transform(row).y.length()
        var measured := caption_metrics(caption)
        var row_rect := screen_rect(row)
        var control_rect := screen_rect(control)
        metrics[item[0]] = {"caption": measured, "row": rect_data(row_rect),
            "control": rect_data(control_rect), "height_limit": height_limit}
        # Check even below the scroll fold: a giant row must not make these
        # basic settings hundreds of pixels tall and effectively inaccessible.
        check(int(measured["line_count"]) == 1 and
            float(measured["content_width"]) + EPSILON >= float(measured["text_width"]),
            label + ": settings caption stays on one readable line: " + str(item[1]))
        check(row_rect.size.y <= height_limit + EPSILON and control_rect.size.y <= height_limit + EPSILON and
            screen_rect(caption).size.y <= height_limit + EPSILON,
            "%s: %s row/control height is bounded by text + padding (row %.1f, control %.1f, limit %.1f px)" % [
                label, item[1], row_rect.size.y, control_rect.size.y, height_limit])
    return metrics

func requests_idle() -> bool:
    # Polls continue normally; only actions/assets/drawer data gate captures.
    return not (app.action_pending or app.layout_pending or
        app.timeline_model_pending or app.library_pending or app.lesson_session.pending or
        app.settings_pending or app.device_pending or app.library_health_pending) and \
        app.pending_transport_action.is_empty() and app.pending_library_piece.is_empty()

func native_status() -> Dictionary:
    if app == null:
        return {"checked": not geometry_only, "app_created": false}
    var renderer = app.timeline_preview
    var status := {"checked": not geometry_only,
        "renderer_script": str(renderer.get_script().resource_path) if renderer != null else "",
        "score_ready": app._native_score_ready(), "native_ready": false, "visible": false, "drawn_noteheads": 0,
        "visible_noteheads": 0, "revision": app.revision,
        "state_revision": int(app.last_state.get("revision", -1)),
        "layout_revision": app.layout_revision, "rendered_revision": app.rendered_revision,
        "model_revision": app.timeline_model_revision, "phase": app.last_state.get("phase", ""),
        "action_pending": app.action_pending, "pending_action": app.pending_transport_action,
        "window_size": [root.size.x, root.size.y], "window_mode": root.mode,
        "window_geometry": window_geometry(),
        "covered_by_drawer": app.current_screen != "practice"}
    if renderer == null:
        return status
    status["native_ready"] = renderer.native_ready
    status["visible"] = renderer.is_visible_in_tree()
    status["failure_reason"] = renderer.failure_reason
    status["drawn_noteheads"] = renderer.drawn_noteheads.size()
    status["visible_symbols"] = renderer.visible_symbols
    status["clock_beat"] = renderer.clock_beat
    status["play_from_beat"] = renderer.play_from_beat
    status["pixels_per_beat"] = renderer.timeline.pixels_per_beat
    status["model_notes"] = renderer.timeline.notes.size()
    status["first_bar"] = renderer.timeline.model.get("first_bar", -1)
    var bounds := Rect2(Vector2.ZERO, renderer.size)
    for center in renderer.drawn_noteheads.values():
        if bounds.has_point(center):
            status["visible_noteheads"] += 1
    return status

func native_is_ready() -> bool:
    var status := native_status()
    var revision: int = int(status.get("revision", -1))
    return revision >= 0 and status.get("renderer_script", "") == "res://notation/native/view.gd" and \
        bool(status.get("score_ready", false)) and bool(status.get("native_ready", false)) and \
        bool(status.get("visible", false)) and \
        str(status.get("failure_reason", "")).is_empty() and \
        revision == int(status.get("state_revision", -2)) and \
        revision == int(status.get("layout_revision", -2)) and \
        revision == int(status.get("rendered_revision", -2)) and \
        revision == int(status.get("model_revision", -2)) and \
        int(status.get("visible_noteheads", 0)) > 0

func expected_window_scale() -> float:
    return maxf(1.0, minf(float(dimensions.x) / 1280.0, float(dimensions.y) / 800.0))

func window_geometry() -> Dictionary:
    var transform := root.get_final_transform()
    return {"physical_viewport": rect_data(transform * root.get_visible_rect()),
        "content_scale": root.content_scale_factor,
        "physical_scale": [transform.x.length(), transform.y.length()],
        "expected_scale": expected_window_scale(),
        "native_mode_checked": DisplayServer.get_name() != "headless"}

func window_geometry_ready() -> bool:
    # Dummy headless displays can report MODE_MINIMIZED despite correct
    # rendering dimensions. Native mode is meaningful only for visible runs.
    if DisplayServer.get_name() != "headless" and root.mode != Window.MODE_WINDOWED:
        return false
    var physical: Rect2 = root.get_final_transform() * root.get_visible_rect()
    var expected := expected_window_scale()
    return (root.size == dimensions and
        physical.position.length() <= EPSILON and physical.size.distance_to(Vector2(dimensions)) <= EPSILON and
        absf(root.content_scale_factor - expected) < 0.001 and
        absf(root.get_final_transform().x.length() - expected) < 0.001 and
        absf(root.get_final_transform().y.length() - expected) < 0.001)

func prepare_window() -> bool:
    if not await wait_until(func() -> bool:
        return app.preferences.has("fullscreen") and not app.settings_pending,
        "initial settings response before final window sizing"):
        return false
    check(not bool(app.preferences["fullscreen"]), "Review backend preferences require fullscreen=false")
    # The project starts fullscreen. Apply physical dimensions AGAIN after
    # its initial settings response and asynchronous display-mode transition.
    # Never resize the screenshot to conceal a compositor/window mismatch.
    var stable_frames := [0]
    return await wait_until(func() -> bool:
        if DisplayServer.get_name() != "headless" and root.mode != Window.MODE_WINDOWED:
            root.mode = Window.MODE_WINDOWED
            stable_frames[0] = 0
            return false
        if root.size != dimensions:
            root.size = dimensions
            stable_frames[0] = 0
            return false
        if not window_geometry_ready():
            stable_frames[0] = 0
            return false
        stable_frames[0] += 1
        return int(stable_frames[0]) >= 3,
        "windowed physical dimensions after settings")

func settled() -> bool:
    var stable_frames := [0]
    var previous_value := [""]
    return await wait_until(func() -> bool:
        var tween_done: bool = app.drawer_intro == null or not app.drawer_intro.is_running()
        if not requests_idle() or not tween_done or not window_geometry_ready():
            stable_frames[0] = 0
            return false
        var signature: Array = [rect_data(screen_rect(app)), app.current_screen]
        for control in active_controls():
            signature.append(rect_data(screen_rect(control)))
        signature.append(rect_data(screen_rect(app.practice_score_panel)))
        var value := JSON.stringify(signature)
        stable_frames[0] = int(stable_frames[0]) + 1 if previous_value[0] == value else 0
        previous_value[0] = value
        return int(stable_frames[0]) >= 3,
        "stable physical layout and acknowledged requests")

func capture(label: String) -> bool:
    if not await settled():
        return false
    var viewport := Rect2(Vector2.ZERO, Vector2(root.size))
    var stage := screen_rect(app.practice_score_panel)
    var transport := screen_rect(app.practice_controls)
    var primary := screen_rect(app.start_button)
    var navigation := screen_rect(app.practice_navigation)
    var rectangles := {"application": rect_data(screen_rect(app)),
        "score_stage": rect_data(stage), "score_frame": rect_data(screen_rect(app.score_frame)),
        "transport": rect_data(transport), "primary_transport": rect_data(primary),
        "navigation": rect_data(navigation), "header": rect_data(screen_rect(app.practice_header)),
        "title": rect_data(screen_rect(app.title_label)), "tempo": rect_data(screen_rect(app.speed_label))}
    var sample := {"name": label, "screen": app.current_screen,
        "phase": str(app.last_state.get("phase", "")), "rects": rectangles,
        "score_height_ratio": stage.size.y / float(root.size.y),
        "native": native_status(), "controls": [], "screenshot": null, "image_size": null,
        "window_geometry": window_geometry(), "captions": check_captions(label), "settings_rows": {}}
    check(window_geometry_ready(), label + ": physical viewport dimensions and scale match")
    check(fits(screen_rect(app), viewport), label + ": application fits physical viewport")
    if app.current_screen == "practice":
        check(not app.game_impact_callout.is_visible_in_tree(),
            label + ": native feedback never covers notation with a coaching card")
        check(fits(stage, viewport) and fits(transport, viewport) and fits(navigation, viewport),
            label + ": score, navigation and transport fit")
        var header := screen_rect(app.practice_header)
        check(not overlaps(stage, transport) and not overlaps(stage, header) and
            not overlaps(stage, navigation) and not overlaps(header, transport),
            label + ": score, header and transport do not overlap")
        # Navigation may be nested inside the redesigned single header.
        if not app.practice_header.is_ancestor_of(app.practice_navigation):
            check(not overlaps(navigation, header), label + ": separate navigation does not overlap header")
        check(not overlaps(screen_rect(app.title_label), screen_rect(app.speed_label)),
            label + ": piece title does not overlap tempo")
        if label == "practice_ready" and dimensions.x >= 1280 and dimensions.y >= 800:
            check(stage.size.y / float(root.size.y) > 0.60,
                label + ": desktop score stage occupies more than 60% of viewport height")
        var nav_controls: Array = []
        collect_controls(app.practice_navigation, nav_controls)
        for control in nav_controls:
            var rectangle := screen_rect(control)
            check(rectangle.size.y <= primary.size.y + EPSILON and
                rectangle.get_area() <= primary.get_area() + EPSILON * primary.size.x,
                label + ": navigation is no larger than primary transport: " + control.name)
        for button in [app.start_button, app.practice_retry_button, app.listen_button]:
            check(button.is_visible_in_tree() and fits(screen_rect(button), viewport),
                label + ": transport stays visible: " + button.text)
        if not geometry_only:
            check(not app.start_button.disabled, label + ": primary transport is usable")
            check(not app.score_status_panel.is_visible_in_tree(), label + ": no score loading cover")
    else:
        rectangles["drawer"] = rect_data(screen_rect(app.overlay_drawer))
        rectangles["active_page"] = rect_data(screen_rect(app.screens[app.current_screen]))
        check(app.overlay_root.is_visible_in_tree() and fits(screen_rect(app.overlay_drawer), viewport),
            label + ": active drawer fits")
        check(fits(screen_rect(app.screens[app.current_screen]), viewport), label + ": active page fits")
        for control in app.screen_navigation.values():
            check(fits(screen_rect(control), viewport), label + ": drawer navigation fits")
        if app.current_screen == "library":
            check(fits(screen_rect(app.library_view.library_search), viewport), label + ": library search fits")
            check(app.library_view.library_rows.get_child_count() > 0, label + ": real library rows are populated")
        if app.current_screen == "lesson":
            check(app.lesson_view.rows.get_child_count() > 0, label + ": lesson path is populated")
        if app.current_screen == "settings":
            sample["settings_rows"] = check_settings_rows(label)
    var shown: Array = []
    for control in active_controls():
        var rectangle := screen_rect(control)
        var exposed := exposed_rect(control)
        var scrollable := scroll_ancestor(control)
        check(rectangle.position.x >= -EPSILON and rectangle.end.x <= viewport.end.x + EPSILON,
            label + ": control fits horizontally: " + str(app.get_path_to(control)))
        if not exposed.has_area():
            check(scrollable, label + ": unscrollable control cannot disappear offscreen: " + str(app.get_path_to(control)))
            continue # Offscreen scroll content is accessible by scrolling.
        sample["controls"].append({"path": str(app.get_path_to(control)),
            "text": str(control.get("text")) if control is BaseButton or control is LineEdit else control.get_class(),
            "rect": rect_data(rectangle), "visible_rect": rect_data(exposed),
            "scrollable": scrollable, "clipped": not fits(rectangle, exposed)})
        check(rectangle.position.x >= exposed.position.x - EPSILON and rectangle.end.x <= exposed.end.x + EPSILON,
            label + ": control is not clipped horizontally: " + str(app.get_path_to(control)))
        check(scrollable or fits(rectangle, exposed),
            label + ": control is not clipped: " + str(app.get_path_to(control)))
        for other in shown:
            check(not overlaps(exposed, exposed_rect(other)),
                label + ": controls do not overlap: " + str(app.get_path_to(control)) + " / " + str(app.get_path_to(other)))
        shown.append(control)
    if not geometry_only:
        check(native_is_ready(), label + ": visible native ink and all revisions match")
        check(app.revision == int(config["revision"]), label + ": selected MIDI revision is preserved")
        check(int(app.last_state.get("selected_start_bar", -1)) == int(config["measure"]),
            label + ": requested source measure is preserved")
        check(absf(float(app.timeline_preview.play_from_beat) - float(config["play_from_beat"])) < 0.00001,
            label + ": native playback origin matches the source measure")
    if render:
        # Capture actual viewport pixels at the requested size; no resampling.
        app.queue_redraw()
        RenderingServer.force_draw()
        var image := root.get_texture().get_image()
        if image != null:
            sample["image_size"] = [image.get_width(), image.get_height()]
        check(image != null and image.get_size() == dimensions,
            label + ": screenshot has the requested full pixel dimensions")
        if image != null and image.get_size() == dimensions:
            var filename := label + ".png"
            var error := image.save_png(output.path_join(filename))
            check(error == OK, label + ": PNG saved: " + error_string(error))
            sample["screenshot"] = filename
    captures.append(sample)
    write_report()
    return true

func show_geometry_state(phase: String) -> void:
    var state := {"loaded": true, "revision": 7, "title": "Ala – Joep Beving",
        "mode": "practice", "kind": "practice", "phase": phase,
        "first_bar": 9, "last_bar": 12, "selected_start_bar": 9, "piece_last_bar": 80,
        "running": phase in ["playing", "paused"], "paused": phase == "paused",
        "clock_beat": 1.0 if phase != "ready" else 0.0, "play_from_beat": 0.0,
        "bpm": 120, "target_bpm": 120, "duration_beats": 16.0, "transport_id": 3,
        "hand": "right", "hands": ["left", "right", "both"],
        "hand_stages": [{"hand": "right", "active": true}, {"hand": "left"}, {"hand": "both"}],
        "lesson_level": "original", "skip_available": true, "feedback_marks": [],
        "preview_only": true, "feedback": "Ready to practise"}
    app._on_state(0, 200, PackedStringArray(), JSON.stringify(state).to_utf8_buffer())

func geometry_journey() -> bool:
    app.set_process(false)
    app._on_settings(0, 200, PackedStringArray(), JSON.stringify({
        "fullscreen": false, "music_dir": "/review/music", "metronome": true}).to_utf8_buffer())
    if not await prepare_window():
        return false
    app._on_library(0, 200, PackedStringArray(), JSON.stringify({
        "folder": "/review/music", "count": 1, "last_piece": "ala.mid", "warmups": [],
        "pieces": [{"id": "ala.mid", "title": "Ala – Joep Beving", "format": "MIDI", "folder": "Music"}]
    }).to_utf8_buffer())
    for phase in ["ready", "playing", "paused"]:
        show_geometry_state(phase)
        if not await capture("practice_" + phase):
            return false
    for destination in ["library", "lesson", "settings"]:
        app._navigate(destination)
        if not await capture("lesson_path" if destination == "lesson" else destination):
            return false
    check(app.network_requests == 0, "Geometry fixture never sends HTTP requests")
    return true

func http_journey() -> bool:
    if not await prepare_window():
        return false
    if not await wait_until(func() -> bool:
        return native_is_ready() and requests_idle() and app.current_screen == "practice" and \
            str(app.last_state.get("phase", "")) == "ready" and not app.start_button.disabled,
        "actual MIDI measure ready with visible native noteheads"):
        return false
    if not await capture("practice_ready"):
        return false
    app.start_button.pressed.emit()
    if not await wait_until(func() -> bool:
        return requests_idle() and native_is_ready() and str(app.last_state.get("phase", "")) == "playing",
        "Play acknowledged and count-in completed"):
        return false
    var clock: float = app.timeline_preview.clock_beat
    if not await wait_until(func() -> bool:
        return str(app.last_state.get("phase", "")) == "playing" and \
            app.timeline_preview.clock_beat >= clock + 0.25, "native musical clock advances"):
        return false
    if not await capture("practice_playing"):
        return false
    app.start_button.pressed.emit()
    if not await wait_until(func() -> bool:
        return requests_idle() and str(app.last_state.get("phase", "")) == "paused" and \
            bool(app.last_state.get("paused", false)), "Pause acknowledged"):
        return false
    if not await capture("practice_paused"):
        return false
    for destination in ["library", "lesson", "settings"]:
        app._navigate(destination)
        if not await wait_until(func() -> bool:
            return app.current_screen == destination and requests_idle(), destination + " data loaded"):
            return false
        if not await capture("lesson_path" if destination == "lesson" else destination):
            return false
    if bool(config.get("exercise_controls", false)):
        return await practice_control_journey()
    return true

func click_control(control: BaseButton) -> bool:
    var ancestor := control.get_parent()
    while ancestor != null:
        if ancestor is ScrollContainer:
            ancestor.ensure_control_visible(control)
        ancestor = ancestor.get_parent()
    await settled()
    check(control.is_visible_in_tree() and not control.disabled, "Control is available: " + control.text)
    if not control.is_visible_in_tree() or control.disabled:
        return false
    for pressed in [true, false]:
        var event := InputEventMouseButton.new()
        event.button_index = MOUSE_BUTTON_LEFT
        event.pressed = pressed
        event.position = control.get_global_rect().get_center()
        root.push_input(event, true)
        await process_frame
    return true

func press_key(code: Key) -> void:
    for pressed in [true, false]:
        var event := InputEventKey.new()
        event.keycode = code
        event.pressed = pressed
        Input.parse_input_event(event)
        await process_frame

func native_picker_backwards() -> bool:
    # Target only this fixture's X11 window on its isolated display. Real X
    # events let Godot route input into the separate native PopupMenu window.
    check(DisplayServer.get_name() == "X11", "Native popup input requires X11")
    if DisplayServer.get_name() != "X11": return false
    var windows: Array = []
    var status := OS.execute("xdotool", PackedStringArray(["search", "--onlyvisible",
        "--pid", str(OS.get_process_id()), "--name", "^Practice UX " + str(OS.get_process_id()) + "$"]), windows, true)
    check(status == 0 and not windows.is_empty(), "Find only this audit's native window")
    if status != 0 or windows.is_empty(): return false
    var window_id := ""
    for line in str(windows[0]).split("\n"):
        if line.strip_edges().is_valid_int():
            window_id = line.strip_edges()
            break
    check(not window_id.is_empty(), "Find numeric native window identity")
    if window_id.is_empty(): return false
    var point: Vector2 = screen_rect(app.lesson_steps.picker).get_center()
    var details: Array = []
    status = OS.execute("xdotool", PackedStringArray(["windowfocus", "--sync", window_id,
        "mousemove", "--window", window_id, str(int(point.x)), str(int(point.y)), "click", "1"]), details, true)
    check(status == 0, "Native mouse opens lesson picker")
    if status != 0: return false
    if not await wait_until(func() -> bool: return app.lesson_steps.picker.get_popup().visible, "actual native lesson popup"): return false
    var popup: PopupMenu = app.lesson_steps.picker.get_popup()
    # A native menu may start without keyboard focus when the pointer is
    # outside its rows. Read actual UI focus, then reach the desired item using
    # real keys; never set selection or emit its signal in this path.
    if popup.get_focused_item() < 0:
        status = OS.execute("xdotool", PackedStringArray(["key", "--clearmodifiers", "Down"]), details, true)
        if not await wait_until(func() -> bool: return popup.get_focused_item() >= 0, "popup keyboard focus"): return false
    var delta: int = int(app.last_state.get("lesson_step", 0)) - 2 - popup.get_focused_item()
    var keys := PackedStringArray(["key", "--clearmodifiers"])
    for index in range(absi(delta)):
        keys.append("Down" if delta > 0 else "Up")
    keys.append("Return")
    status = OS.execute("xdotool", keys, details, true)
    check(status == 0, "Native keyboard chooses previous popup item")
    return status == 0

func workflow_ready(label: String) -> bool:
    return await wait_until(func() -> bool:
        return requests_idle() and native_is_ready() and str(app.last_state.get("phase", "")) == "ready",
        label)

func workflow_record(label: String) -> void:
    await settled()
    var sample := {"name": label, "phase": app.last_state.get("phase"),
        "hand": app.last_state.get("hand"), "bpm": app.last_state.get("bpm"),
        "step": app.last_state.get("lesson_step"), "revision": app.revision,
        "screenshot": null}
    if label == "listen":
        sample["audio_playing"] = app.demo_player.player.playing
        sample["pcm_bytes"] = app.demo_player.player.stream.data.size() if app.demo_player.player.stream is AudioStreamWAV else 0
    if render:
        RenderingServer.force_draw()
        var image := root.get_texture().get_image()
        var filename := "workflow_" + label + ".png"
        check(image != null and image.get_size() == dimensions, label + ": raw workflow viewport")
        if image != null:
            check(image.save_png(output.path_join(filename)) == OK, label + ": save workflow viewport")
            sample["screenshot"] = filename
    workflow_captures.append(sample)
    write_report()

func practice_control_journey() -> bool:
    app._navigate("practice")
    if not await wait_until(func() -> bool: return requests_idle() and native_is_ready(), "Practice controls loaded"):
        return false
    var original_step := int(app.last_state.get("lesson_step", 0))
    var original_bpm := int(app.last_state.get("bpm", 0))
    var target_bpm := int(app.last_state.get("target_bpm", 0))
    check(original_step > 1, "Review source allows backward lesson selection")
    if not await click_control(app.tempo_down_button): return false
    if not await workflow_ready("visible -5 BPM acknowledged"): return false
    check(int(app.last_state.get("bpm", 0)) == original_bpm - 5, "Visible -5 BPM changes current tempo by exactly five")
    check(int(app.last_state.get("target_bpm", 0)) == target_bpm, "Manual tempo preserves automatic target")
    workflow_checks.append("manual_minus_five")
    await workflow_record("manual_minus_five")
    if not await click_control(app.tempo_up_button): return false
    if not await workflow_ready("visible +5 BPM acknowledged"): return false
    check(int(app.last_state.get("bpm", 0)) == original_bpm, "Visible +5 BPM restores tempo")
    workflow_checks.append("manual_plus_five")
    if not await click_control(app.lesson_steps.next_button): return false
    if not await workflow_ready("next lesson step"): return false
    check(int(app.last_state.get("lesson_step", 0)) == original_step + 1, "Next selects following step")
    workflow_checks.append("next_step")
    if not await click_control(app.lesson_steps.previous_button): return false
    if not await workflow_ready("previous lesson step"): return false
    check(int(app.last_state.get("lesson_step", 0)) == original_step, "Previous returns to the prior step")
    check(int(app.last_state.get("bpm", 0)) == original_bpm, "Returning step restores its saved manual tempo")
    workflow_checks.append("previous_step")
    var picker_revision: int = app.revision
    if bool(config.get("native_input", false)):
        if not await native_picker_backwards(): return false
    else:
        # Headless coverage checks the selection binding, independently of the
        # rendered X11 journey which exercises the native popup itself.
        app.lesson_steps.picker.select(original_step - 2)
        app.lesson_steps.picker.item_selected.emit(original_step - 2)
    if not await wait_until(func() -> bool:
        return requests_idle() and native_is_ready() and app.revision > picker_revision,
        "picker backward selection"): return false
    check(int(app.last_state.get("lesson_step", 0)) == original_step - 1,
        "Picker selects the requested earlier step: actual %d expected %d" % [int(app.last_state.get("lesson_step", 0)), original_step - 1])
    if int(app.last_state.get("lesson_step", 0)) != original_step - 1: return false
    workflow_checks.append("picker_backwards")
    # The preceding entry may be a connection passage (Both only). Return to
    # this source's Learn passage before exercising its three hand choices.
    if not await click_control(app.lesson_steps.next_button): return false
    if not await workflow_ready("restore source step before hand choices"): return false
    check(int(app.last_state.get("lesson_step", 0)) == original_step, "Restore source lesson step")
    # Switch away first so the Right check must click its real control too.
    app._navigate("lesson")
    if not await wait_until(func() -> bool: return requests_idle(), "initial hand choices loaded"): return false
    if not await click_control(app.lesson_view.hand_buttons["left"]): return false
    if not await workflow_ready("switch away before testing Right control"): return false
    for hand in ["right", "left", "both"]:
        app._navigate("lesson")
        if not await wait_until(func() -> bool: return requests_idle(), "hand choices loaded"): return false
        if str(app.last_state.get("hand", "")) != hand:
            if not await click_control(app.lesson_view.hand_buttons[hand]): return false
        else:
            app._navigate("practice")
        if not await workflow_ready(hand + " hand notation ready"): return false
        check(app.current_screen == "practice" and str(app.last_state.get("hand", "")) == hand,
            hand + ": real hand selection acknowledged")
        workflow_checks.append(hand)
        await workflow_record(hand)
    if not await click_control(app.start_button): return false
    if not await wait_until(func() -> bool: return str(app.last_state.get("phase", "")) == "count_in", "real count-in"): return false
    check(app.tempo_down_button.disabled and app.tempo_up_button.disabled, "Manual tempo is guarded during count-in")
    workflow_checks.append("count_in")
    await workflow_record("count_in")
    if not await wait_until(func() -> bool: return str(app.last_state.get("phase", "")) == "playing", "count-in completes"): return false
    if not await click_control(app.start_button): return false
    if not await wait_until(func() -> bool: return requests_idle() and str(app.last_state.get("phase", "")) == "paused", "visible Pause"): return false
    workflow_checks.append("pause")
    var paused_bpm := int(app.last_state.get("bpm", 0))
    if not await click_control(app.tempo_down_button): return false
    if not await workflow_ready("paused -5 BPM"): return false
    check(int(app.last_state.get("bpm", 0)) == paused_bpm - 5, "Paused -5 BPM is preserved as a direct manual control")
    workflow_checks.append("paused_minus_five")
    # A manual change intentionally abandons the old take. Retry becomes
    # available once another real attempt exists, rather than on a blank Ready.
    if not await click_control(app.start_button): return false
    if not await wait_until(func() -> bool: return requests_idle() and str(app.last_state.get("phase", "")) == "count_in", "manually paced take starts"): return false
    var previous_transport := int(app.last_state.get("transport_id", -1))
    if not await click_control(app.practice_retry_button): return false
    if not await wait_until(func() -> bool:
        return requests_idle() and str(app.last_state.get("phase", "")) == "count_in" and \
            int(app.last_state.get("transport_id", -1)) > previous_transport,
        "Retry starts fresh count-in"): return false
    check(int(app.last_state.get("bpm", 0)) == paused_bpm - 5, "Retry preserves manually chosen BPM")
    workflow_checks.append("retry")
    if not await click_control(app.listen_button): return false
    if not await wait_until(func() -> bool:
        return requests_idle() and str(app.last_state.get("mode", "")) == "listen" and \
            app.demo_player.loaded and app.demo_player.player.playing and \
            app.demo_player.player.stream is AudioStreamWAV and app.demo_player.player.stream.data.size() > 10000,
        "Listen downloads and plays actual PCM audio"): return false
    workflow_checks.append("listen")
    await workflow_record("listen")
    if not await click_control(app.listen_button): return false
    if not await workflow_ready("Listen returns to Practice"): return false
    check(str(app.last_state.get("mode", "")) == "practice", "Listen returns to unscored ready Practice")
    workflow_checks.append("return_to_practice")
    app.start_button.release_focus()
    await press_key(KEY_SPACE)
    if not await wait_until(func() -> bool: return str(app.last_state.get("phase", "")) == "count_in", "Space starts Practice"): return false
    await press_key(KEY_P)
    if not await wait_until(func() -> bool: return str(app.last_state.get("phase", "")) == "paused", "P pauses Practice"): return false
    workflow_checks.append("keyboard_play_pause")
    await workflow_record("keyboard_paused")
    return true

func run() -> void:
    var arguments := OS.get_cmdline_user_args()
    if arguments.size() != 1:
        push_error("Usage: art_direction.gd -- /absolute/config.json")
        quit(1)
        return
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
    if not parsed is Dictionary:
        push_error("Art direction config must be a JSON object")
        quit(1)
        return
    config = parsed
    output = str(config["output"])
    dimensions = Vector2i(int(config["size"][0]), int(config["size"][1]))
    geometry_only = str(config.get("mode", "http")) == "geometry"
    render = bool(config.get("render", false))
    if bool(config.get("native_input", false)):
        root.title = "Practice UX " + str(OS.get_process_id())
    deadline_ms = Time.get_ticks_msec() + int(float(config.get("timeout_seconds", 90)) * 1000.0)
    check(not render or (not geometry_only and DisplayServer.get_name() != "headless"),
        "Screenshots require a visible real HTTP application")
    if not failures.is_empty():
        write_report()
        quit(1)
        return
    root.mode = Window.MODE_WINDOWED
    root.borderless = true
    root.size = dimensions
    app = GeometryApp.new() if geometry_only else load("res://main.tscn").instantiate()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    app._navigate("practice")
    var completed: bool
    if geometry_only:
        completed = await geometry_journey()
    else:
        completed = await http_journey()
    check(completed and captures.size() == 6, "All six application views captured")
    write_report()
    print("ART_DIRECTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
