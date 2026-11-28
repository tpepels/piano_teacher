extends RefCounted
## Test-only observer of the real Window texture after every completed draw.
## No runtime caller; no synthetic paint or clock. Analysis runs after exit.
const PLAYHEAD_FRACTION := preload("res://notation/shared/spacing_policy.gd").PLAYHEAD_FRACTION
const WIDTH := 640
const HEIGHT := 400
const MAX_FRAMES := 14000
const MAX_CAPTURE_BYTES := 1073741824
const MAX_METADATA_BYTES := 268435456

var step := "boot"
var _app: Node
var _window: Window
var _frames: FileAccess
var _metadata: FileAccess
var _count := 0
var _failed := false
var _enabled := false
var _max_capture_ms := 0.0
var _directory := ""

func start(app: Node, window: Window) -> void:
    var directory: String = OS.get_environment("PIANO_VISUAL_CAPTURE_DIR")
    if directory.is_empty():
        return
    _enabled = true
    _directory = directory
    _app = app
    _window = window
    if DisplayServer.get_name() == "headless":
        _error("Visual acceptance requires a real rendering backend")
        return
    _frames = FileAccess.open(directory.path_join("frames.bin"),FileAccess.WRITE)
    _metadata = FileAccess.open(directory.path_join("frames.jsonl"),FileAccess.WRITE)
    if _frames == null or _metadata == null:
        _error("Cannot open rendered-frame capture")
        return
    # Cap the actual rendered frame rate; capture every draw, not a timed
    # subset. Keep real monotonic time and the production transport intact.
    Engine.max_fps = 30
    RenderingServer.frame_post_draw.connect(_capture)

func _error(message: String) -> void:
    _failed = true
    push_error("VISUAL_CAPTURE_FAILURE: "+message)

func _rect(control: Control, viewport_size: Vector2) -> Array:
    var rect: Rect2 = control.get_global_rect()
    return [rect.position.x/viewport_size.x,rect.position.y/viewport_size.y,
        rect.size.x/viewport_size.x,rect.size.y/viewport_size.y]

func _layers(stage, viewport_size: Vector2) -> Array:
    var result: Array = []
    for child in stage.score_frame.get_children():
        if child is Control and child.has_method("diagnostic_stream_snapshot") and \
                child.is_visible_in_tree():
            result.append({"id":child.get_instance_id(),
                "world":float(child.stream_world_beat),
                "density":float(child.timeline.pixels_per_beat)/viewport_size.x})
    return result

func _sample() -> Dictionary:
    var state: Dictionary = _app.current_state()
    var size: Vector2 = _window.get_visible_rect().size
    var stage = _app.practice_view.stage
    var staff = _app.score_runway.staff_renderer()
    if not is_instance_valid(staff):
        staff = stage.renderer
    var cursor: float = (staff.get_global_rect().position.x+\
        staff.size.x*PLAYHEAD_FRACTION)/size.x
    var flow = _app.score_flow
    var world: float = float(flow.beat)
    if not is_finite(world):
        world = 0.0
    return {"frame":_count,"engine_frame":Engine.get_frames_drawn(),
        "time_ms":float(Time.get_ticks_usec())*.001,
        "sample_ms":float(flow.last_ms),"world":world,"step":step,
        "screen":str(_app.current_screen),"piece":str(state.get("piece_fingerprint","")),
        "ready":_app.score_session.is_ready(),"score":_rect(stage.score_frame,size),
        "playhead":cursor,"staff_hand":str(staff.active_hand),
        "count_in":_rect(stage.count_in,size) if stage.count_in.is_visible_in_tree() else null,
        "layers":_layers(stage,size),"mode":str(state.get("mode","")),
        "phase":str(state.get("phase","")),"revision":state.get("revision",-1),
        "transport":state.get("transport_id",-1),"hand":state.get("hand",""),
        "running":state.get("running",false),"paused":state.get("paused",false),
        "clock_beat":state.get("clock_beat",0.0),"bpm":state.get("bpm",0.0),
        "flow_step":state.get("flow",{}).get("step","") if state.get("flow") is Dictionary else "",
        "playback":state.get("playback_timeline"),
        "timeline":state.get("musical_timeline")}

func _capture() -> void:
    if _failed:
        return
    if _count >= MAX_FRAMES:
        _error("Rendered-frame capture exceeded its bound")
        return
    var began: int = Time.get_ticks_usec()
    var meta: Dictionary = _sample()
    var image: Image = _window.get_texture().get_image()
    if image == null or image.is_empty():
        _error("Window texture has no rendered image")
        return
    image.convert(Image.FORMAT_RGB8)
    image.resize(WIDTH,HEIGHT,Image.INTERPOLATE_BILINEAR)
    var png: PackedByteArray = image.save_png_to_buffer()
    if png.is_empty():
        _error("Cannot encode rendered frame")
        return
    var line: String = JSON.stringify(meta)
    if _frames.get_position()+png.size()+4 > MAX_CAPTURE_BYTES or \
            _metadata.get_position()+line.to_utf8_buffer().size()+1 > MAX_METADATA_BYTES:
        _error("Rendered-frame capture exceeded its storage bound")
        return
    _frames.store_32(png.size())
    _frames.store_buffer(png)
    _metadata.store_line(line)
    if _frames.get_error() != OK or _metadata.get_error() != OK:
        _error("Cannot write rendered frame")
    _count += 1
    _max_capture_ms = maxf(_max_capture_ms,float(Time.get_ticks_usec()-began)*.001)

func finish() -> bool:
    if not _enabled:
        return true
    if RenderingServer.frame_post_draw.is_connected(_capture):
        RenderingServer.frame_post_draw.disconnect(_capture)
    if _frames != null:
        _frames.flush()
        _frames.close()
    if _metadata != null:
        _metadata.flush()
        _metadata.close()
    _frames = null
    _metadata = null
    _app = null
    _window = null
    var success: bool = not _failed and _count > 0
    var manifest := FileAccess.open(_directory.path_join("complete.json"),FileAccess.WRITE)
    if manifest == null:
        return false
    manifest.store_string(JSON.stringify({"frames":_count,"success":success,
        "max_capture_ms":_max_capture_ms}))
    manifest.close()
    print("VISUAL_CAPTURE_COMPLETE frames=",_count," max_capture_ms=",_max_capture_ms)
    return success
