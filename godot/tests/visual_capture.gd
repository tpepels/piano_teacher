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
var _fps := 30
var _pacing_only := false
var _events: Array = []
var _previous_capture_ms := 0.0
var _pre_draw_us := 0
var _last_draw_us := 0
var _previous_display_fallbacks := 0
var _midi_until_ms := -1.0

# Test-only markers taken BEFORE the real input is sent. They are attached
# to the next completed viewport frame, not reconstructed from phase names.
func mark(kind: String, label: String = "", pitch: int = -1, attack_offset: float = 0.0) -> void:
    if not _enabled or _failed:
        return
    if _pacing_only and kind != "midi":
        if kind == "injected_hitch":
            _events.append({"kind":kind,"label":label})
        return
    var state: Dictionary = _app.current_state()
    var flow = _app.score_flow
    var stage = _app.practice_view.stage
    var viewport_size: Vector2 = _window.get_visible_rect().size
    var targets: Array = []
    var baseline: Array = []
    if kind == "midi":
        _midi_until_ms = float(Time.get_ticks_usec())*.001+400.0
        var renderer = stage.renderer
        var teaching: Variant = state.get("teaching")
        if label == "wrong" and teaching is Dictionary:
            for note in teaching.get("expected_notes",[]):
                targets.append(str(note.get("source_id","")))
        else:
            # The journey supplies the authored attack offset, not a
            # nearest-note guess or a notehead observed after injection.
            var current: Variant = state.get("playback_timeline",{}).get("current")
            if current is Dictionary:
                var source: Dictionary = current.get("source",{})
                if int(source.get("revision",-1)) == renderer.timeline.revision:
                    targets = correct_probe_targets(renderer.timeline.model,pitch,
                        float(source.get("from_beat",NAN))+attack_offset)
        baseline = _painted_heads(stage,viewport_size)
    _events.append({"kind":kind,"label":label,"pitch":pitch,"targets":targets,"baseline_feedback":baseline,
        "take":_take_key(state),
        "at_ms":float(Time.get_ticks_usec())*.001,
        "world":float(flow.beat),"bpm":float(state.get("bpm",0.0)),
        "paused":bool(state.get("paused",false)),
        "button_text":str(_app.practice_view.start_button.text),
        "transport":int(state.get("transport_id",-1)),
        "midi_count":int(state.get("midi_input_count",0)),
        "layers":_layers(stage,viewport_size) if kind == "transition" else [],
        "primary_layer":stage.renderer.get_instance_id() if kind == "transition" else -1,
        "opening_header_beats":maxf(stage.renderer._stream_header_beats(0.0),
            stage.renderer._stream_header_beats(1.0))+.25 if kind == "transition" else 0.0})

static func _take_key(state: Dictionary) -> String:
    return "%s|%d|%d|%s" % [str(state.get("piece_fingerprint","")),int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),str(state.get("mode",""))]

# Only active source attacks at the authored onset can satisfy this
# probe. The separate painted-feedback witness still requires the
# authenticated take, the correct source identity and visible core ink.
static func correct_probe_targets(model: Dictionary, pitch: int, source_beat: float) -> Array:
    var targets: Array = []
    if not is_finite(source_beat):
        return targets
    var active: Array = model.get("active_note_ids",[])
    for note in model.get("notes",[]):
        var source: String = str(note.get("id",""))
        if active.has(source) and int(note.get("midi_pitch",-1)) == pitch and \
                absf(float(note.get("onset_beats",INF))-source_beat) < .0001:
            targets.append(source)
    return targets

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
    _pacing_only = OS.get_environment("PIANO_VISUAL_PACING_ONLY") == "1"
    if not _pacing_only:
        _frames = FileAccess.open(directory.path_join("frames.bin"),FileAccess.WRITE)
    _metadata = FileAccess.open(directory.path_join("frames.jsonl"),FileAccess.WRITE)
    if (not _pacing_only and _frames == null) or _metadata == null:
        _error("Cannot open rendered-frame capture")
        return
    # Cap the actual rendered frame rate; capture every draw, not a timed
    # subset. Keep real monotonic time and the production transport intact.
    var requested: String = OS.get_environment("PIANO_VISUAL_FPS")
    if requested in ["30","60","120"]:
        _fps = int(requested)
    Engine.max_fps = _fps
    if _pacing_only:
        RenderingServer.frame_pre_draw.connect(_before_draw)
    RenderingServer.frame_post_draw.connect(_capture)

func _before_draw() -> void:
    _pre_draw_us = Time.get_ticks_usec()

func _error(message: String) -> void:
    _failed = true
    push_error("VISUAL_CAPTURE_FAILURE: "+message)

func _rect(control: Control, viewport_size: Vector2) -> Array:
    var rect: Rect2 = control.get_global_rect()
    return [rect.position.x/viewport_size.x,rect.position.y/viewport_size.y,
        rect.size.x/viewport_size.x,rect.size.y/viewport_size.y]

const Admission := preload("res://score_stream_admission.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")

func _strips(view, viewport_size: Vector2) -> Array:
    # A physical witness from the actual retained queue, not from the
    # teaching mode or a guessed time window around a transition.
    var snapshot: Array = view.diagnostic_stream_snapshot()
    var authorized: Dictionary = {}
    for item in snapshot:
        if str(item.get("kind","source")) == "source":
            var key: String = str(item.get("take_key",""))
            var owner: int = int(item.get("take_owner",item["serial"]))
            if not key.is_empty() and key not in ["prepared","predicted"]:
                authorized[owner] = true
    var result: Array = []
    var density: float = float(view.timeline.pixels_per_beat)
    var gap: float = float(view.staff_gap())
    var duration: float = float(view.timeline.sounding_duration_beats)
    var origin_x: float = view.get_global_rect().position.x
    var playhead: float = view.size.x*PLAYHEAD_FRACTION
    for item in snapshot:
        var clip = item.get("clip")
        var owner: int = int(item.get("take_owner",item["serial"]))
        var kind: String = str(item.get("kind","source"))
        var bounds: Vector2 = Admission.clip_bounds(item,density,gap,duration)
        var origin: float = float(item["world_origin"])
        var x: float = origin_x+playhead+(origin-float(view.stream_world_beat))*density
        var admitted_density: float = float(item.get("admitted_density",density))
        var admitted_gap: float = float(item.get("admitted_staff_gap",gap))
        var admitted_world: float = float(item.get("admitted_world",INF))
        var admitted_x: float = float(item.get("admitted_playhead_x",playhead))
        var admitted_width: float = float(item.get("admitted_viewport_width",view.size.x))
        var admitted_bounds: Vector2 = Admission.clip_bounds(item,admitted_density,admitted_gap,duration)
        var first_x: float = admitted_x+(origin-admitted_world)*admitted_density+admitted_bounds.x
        result.append({"id":str(item.get("slot_id",str(item["serial"])+":"+kind)),
            "left":(x+bounds.x)/viewport_size.x,"right":(x+bounds.y)/viewport_size.x,
            "gutter":(origin_x+29.0)/viewport_size.x,
            "kind":kind,"world_end":origin+bounds.y/maxf(1.0,density),
            "visible":is_instance_valid(clip) and clip.is_visible_in_tree(),
            "ever_visible":bool(item.get("ever_visible",false)),
            "authorized":authorized.has(owner),
            "admitted_inside":is_finite(admitted_world) and first_x <= admitted_width
                and (kind == "rest" or bool(item.get("admitted_on_empty_strip",false))),
            "future":is_finite(admitted_world) and origin+float(item.get("source_floor",0.0)) > admitted_world})
    return result

func _painted_heads(stage, viewport_size: Vector2) -> Array:
    var result: Array = []
    for view in stage.score_frame.get_children():
        if not view is Control or not view.has_method("diagnostic_stream_snapshot") or not view.is_visible_in_tree():
            continue
        for item in view.diagnostic_stream_snapshot():
            var segment = item.get("segment")
            var clip = item.get("clip")
            if not is_instance_valid(segment) or not is_instance_valid(clip) or \
                    not clip.is_visible_in_tree() or not is_instance_valid(segment.get("status_layer")):
                continue
            var clip_rect: Rect2 = clip.get_global_rect()
            for entry in segment.status_layer.painted_feedback:
                var head: Dictionary = entry["instance"]
                var at: Vector2 = segment.to_global(head["position"])
                if not clip_rect.has_point(at) or at.x < 0.0 or at.x >= viewport_size.x:
                    continue
                result.append({"take":entry["take"],"source":str(head.get("source_id","")),
                    "event":str(head.get("event_id","")),"slot":str(item.get("slot_id","")),
                    "layer":view.get_instance_id(),"status":entry["status"],
                    "x":at.x/viewport_size.x,"y":at.y/viewport_size.y,
                    "rx":float(head["gap"])*.85/viewport_size.x,
                    "ry":float(head["gap"])*.65/viewport_size.y})
    return result

func _midi_sample(now_ms: float) -> Dictionary:
    if now_ms > _midi_until_ms:
        return {}
    var state: Dictionary = _app.current_state()
    var size: Vector2 = _window.get_visible_rect().size
    return {"midi_count":int(state.get("midi_input_count",0)),
        "midi_pitch":state.get("midi_input_note"),"midi_take":_take_key(state),
        "painted_feedback":_painted_heads(_app.practice_view.stage,size)}

func _layers(stage, viewport_size: Vector2) -> Array:
    var result: Array = []
    for child in stage.score_frame.get_children():
        if child is Control and child.has_method("diagnostic_stream_snapshot") and \
                child.is_visible_in_tree():
            result.append({"id":child.get_instance_id(),
                "world":float(child.stream_world_beat),
                "density":float(child.timeline.pixels_per_beat)/viewport_size.x,
                "strips":_strips(child,viewport_size)})
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
        "sample_ms":float(flow.last_ms),"backend_sample_ms":flow.diagnostic_backend_sample_ms(),
        "world":world,"motion_world":float(staff.stream_world_beat),"step":step,
        "timing_version":2,"fps":_fps,"capture_cost_ms":_previous_capture_ms,
        "run_offset":float(flow.run_offset),"following":bool(flow.following),
        "events":_events.duplicate(true),
        "painted_feedback":_painted_heads(stage,size) if float(Time.get_ticks_usec())*.001 <= _midi_until_ms else [],
        "midi_count":int(state.get("midi_input_count",0)),
        "midi_pitch":state.get("midi_input_note"),"midi_take":_take_key(state),
        "teaching":state.get("teaching"),
        "button_text":str(_app.practice_view.start_button.text),
        "button_disabled":bool(_app.practice_view.start_button.disabled),
        "screen":str(_app.current_screen),"piece":str(state.get("piece_fingerprint","")),
        "ready":_app.score_session.is_ready(),"score":_rect(stage.score_frame,size),
        "playhead":cursor,"staff_hand":str(staff.active_hand),
        "count_in":_rect(stage.count_in,size) if stage.count_in.is_visible_in_tree() else null,
        "layers":_layers(stage,size),"strip_witness_version":1,
        "mode":str(state.get("mode","")),
        "phase":str(state.get("phase","")),"revision":state.get("revision",-1),
        "transport":state.get("transport_id",-1),"hand":state.get("hand",""),
        "running":state.get("running",false),"paused":state.get("paused",false),
        "clock_beat":state.get("clock_beat",0.0),"bpm":state.get("bpm",0.0),
        "target_bpm":state.get("target_bpm",0.0),
        "flow_step":state.get("flow",{}).get("step","") if state.get("flow") is Dictionary else "",
        "playback":state.get("playback_timeline"),
        "timeline":state.get("musical_timeline")}

func _capture() -> void:
    if _failed:
        return
    if _count >= MAX_FRAMES*(_fps/30.0):
        _error("Rendered-frame capture exceeded its bound")
        return
    var began: int = Time.get_ticks_usec()
    if _pacing_only:
        # No screenshot/readback, resize, PNG encoding or full queue/state
        # snapshot. A second real-rendered run measures pacing independently.
        var draw_ms: float = float(began-_pre_draw_us)*.001 if _pre_draw_us > _last_draw_us else -1.0
        var between_draws_ms: float = float(_pre_draw_us-_last_draw_us)*.001 if _last_draw_us > 0 and _pre_draw_us > _last_draw_us else -1.0
        _last_draw_us = began
        var fallback_delta: int = Glyphs.display_fallback_count-_previous_display_fallbacks
        _previous_display_fallbacks = Glyphs.display_fallback_count
        _metadata.store_line(JSON.stringify({
            "draw_ms":draw_ms,"between_draws_ms":between_draws_ms,
            "display_fallbacks":fallback_delta,
            "frame":_count,"engine_frame":Engine.get_frames_drawn(),
            "time_ms":float(began)*.001,"fps":_fps,
            "capture_cost_ms":_previous_capture_ms,"step":step,
            "screen":str(_app.current_screen),"ready":_app.score_session.is_ready(),
            "phase":str(_app.state_inbox.current.get("phase","")),
            "revision":int(_app.state_inbox.current.get("revision",-1)),
            "events":_events,"midi_sample":_midi_sample(float(began)*.001)}))
        if _metadata.get_error() != OK:
            _error("Cannot write lightweight pacing record")
            return
        _events.clear()
        _count += 1
        _previous_capture_ms = float(Time.get_ticks_usec()-began)*.001
        _max_capture_ms = maxf(_max_capture_ms,_previous_capture_ms)
        return
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
    _events.clear()
    _count += 1
    _previous_capture_ms = float(Time.get_ticks_usec()-began)*.001
    _max_capture_ms = maxf(_max_capture_ms,_previous_capture_ms)

func finish() -> bool:
    if not _enabled:
        return true
    if RenderingServer.frame_pre_draw.is_connected(_before_draw):
        RenderingServer.frame_pre_draw.disconnect(_before_draw)
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
        "max_capture_ms":_max_capture_ms,"pacing_only":_pacing_only,"fps":_fps}))
    manifest.close()
    print("VISUAL_CAPTURE_COMPLETE frames=",_count," max_capture_ms=",_max_capture_ms)
    return success
