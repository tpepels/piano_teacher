extends SceneTree
## R1 readiness sweep: drive the real production scene (main.tscn, embedded
## Python engine, real Verovio notation) through one scripted session and
## record what the player actually sees.
##
##   open -> READY -> Play -> count-in -> graded take (simulated MIDI with a
##   known per-note plan, see pyhook/sitecustomize.py) -> Pause -> Resume ->
##   automatic repeat/continuation -> Retry -> clean takes -> next stage.
##
## Controls are pressed through the real buttons. Nothing is mocked. At each
## checkpoint the real framebuffer is saved as PNG next to a JSON sidecar with
## every drawn notehead instance (position, take, ledger status) and the
## engine state snapshot. Every frame is logged to frames.jsonl.
##
## Usage: godot --path godot --windowed --resolution WxH --script
##        <abs>/tests/readiness/r1_sweep.gd -- <out_dir> <max_seconds>

var out_dir := ""
var max_ms := 240000
var app
var renderer
var boot_us := 0
var last_us := 0
var phase := "boot"
var phase_ms := 0
var frames: Array = []
var events: Array = []
var capture_queue: Array = []
var capture_count := 0
var capture_was_last_frame := false
var event_maps: Dictionary = {}   # revision -> {id: [beat, source_id]}
var seen_instances: Dictionary = {}
var t_ready_ms := -1
var t_play_ms := -1
var t_first_ink_ms := -1
var takes: Array = []             # transport ids in order
var take_meta: Dictionary = {}    # tid -> {index, len, first_tb...}
var last_tid := -1
var last_phase := ""
var last_step := -1
var voice
var voice_last_total := 0
var pause_done := false
var pause_requested_ms := -1
var resume_requested := false
var retry_done := false
var stage_seen_ms := -1
var last_capture_beat: Dictionary = {}
var idle_since_ms := -1
var flags: Dictionary = {}
var pending_saves: Array = []
var scenario := "full"   # full | plain (no pause, no retry) | noretry | nopause | cipause

func _initialize() -> void:
    call_deferred("_boot")

func _now_ms() -> int:
    return int((Time.get_ticks_usec()-boot_us)/1000)

func _boot() -> void:
    var args := OS.get_cmdline_user_args()
    out_dir = args[0]
    if args.size() > 1:
        max_ms = int(float(args[1])*1000.0)
    if args.size() > 2:
        scenario = args[2]
    if scenario in ["plain","nopause"]:
        pause_done = true
    if scenario in ["plain","noretry"]:
        retry_done = true
    DirAccess.make_dir_recursive_absolute(out_dir.path_join("shots"))
    boot_us = Time.get_ticks_usec()
    last_us = boot_us
    _write_control("mixed","take1")
    var scene: PackedScene = load("res://main.tscn")
    app = scene.instantiate()
    root.add_child(app)
    RenderingServer.frame_post_draw.connect(_post_draw)
    _event("boot",{"window":DisplayServer.window_get_size(),
        "root":root.size,"rendering":ProjectSettings.get_setting(
            "rendering/renderer/rendering_method")})

func _event(kind: String, data: Dictionary = {}) -> void:
    var row := {"t":_now_ms(),"kind":kind,"phase":phase}
    row.merge(data,true)
    events.append(row)
    print("R1_EVENT:",JSON.stringify(row))

func _write_control(plan: String, label: String) -> void:
    var f := FileAccess.open(out_dir.path_join("control.json"),FileAccess.WRITE)
    f.store_string(JSON.stringify({"plan":plan,"label":label}))
    f.close()

func _advance(next: String) -> void:
    _event("phase",{"to":next})
    phase = next
    phase_ms = _now_ms()

func _state() -> Dictionary:
    return app.last_state if app != null else {}

func _ready_score() -> bool:
    if app.score_session == null or not app.score_session.is_ready():
        return false
    var view = app.practice_view.stage.renderer
    if not view.native_ready or not view.visible or not view.retained_ready():
        return false
    return int(_state().get("revision",-1)) == app.score_session.rendered_revision

func _capture(name: String) -> void:
    capture_queue.append(name)

func _press(button: Button, label: String) -> bool:
    if app.command_state.pending:
        return false
    if button.disabled:
        _event("button_disabled",{"button":label})
        return false
    _event("press",{"button":label,"text":button.text})
    button.pressed.emit()
    return true

func _active_take_key() -> String:
    var s: Dictionary = _state()
    return "%s|%d|%d|%s" % [str(s.get("piece_fingerprint","")),
        int(s.get("revision",-1)),int(s.get("transport_id",-1)),str(s.get("mode","practice"))]

func _event_map() -> Dictionary:
    var rev: int = int(renderer.timeline.revision) if renderer.timeline != null else -1
    if not event_maps.has(rev):
        var m: Dictionary = {}
        if renderer.layout != null:
            for e in renderer.layout.ordered_events:
                if str(e.get("kind","")) == "note":
                    m[str(e["id"])] = [float(e.get("beat",0.0)),str(e.get("source_id","")),
                        int(e.get("pitch",-1))]
        event_maps[rev] = m
        var f := FileAccess.open(out_dir.path_join("events_rev%d.json" % rev),FileAccess.WRITE)
        f.store_string(JSON.stringify(m))
        f.close()
    return event_maps[rev]

var origin_key := ""
func _origin_of(take_key: String) -> float:
    # The active take's strip; failing that, the source strip under the
    # playhead (an automatic repeat can stay keyed "autopending").
    origin_key = take_key
    for item in renderer.stream_passes:
        if str(item.get("take_key","")) == take_key and str(item.get("kind","source")) == "source":
            return float(item["world_origin"])
    var world: float = renderer.stream_world_beat
    for item in renderer.stream_passes:
        if str(item.get("kind","source")) != "source":
            continue
        var o: float = float(item["world_origin"])
        if o+float(item.get("source_floor",0.0))-0.01 <= world and \
                world <= o+float(item.get("source_ceiling",INF))+0.01:
            origin_key = str(item.get("take_key",""))
            return o
    origin_key = ""
    return NAN

func _post_draw() -> void:
    if app == null or not is_instance_valid(app) or app.practice_view == null:
        return
    renderer = app.practice_view.stage.renderer
    var us := Time.get_ticks_usec()
    var dt := (us-last_us)/1000.0
    last_us = us
    var s: Dictionary = _state()
    var playhead_x: float = renderer.size.x*renderer.PLAYHEAD_FRACTION
    var density: float = renderer.timeline.pixels_per_beat if renderer.timeline != null else 0.0
    # The same instant the drawn world position was sampled at (main.gd
    # samples one clock per frame); a fresh clock read here would add the
    # frame's own render time as a false strip-to-transport offset.
    var tb: float = app._transport_beat_at(int(app.frame_ms))
    var world: float = renderer.stream_world_beat
    var key: String = _active_take_key()
    var origin: float = _origin_of(key)
    var play_from: float = float(s.get("play_from_beat",0.0))
    var emap: Dictionary = _event_map()
    var bounds := Rect2(Vector2.ZERO,renderer.size)
    var visible := 0
    var near: Array = []
    for inst in renderer.drawn_note_instances:
        var p: Vector2 = inst["position"]
        if not bounds.has_point(p):
            continue
        visible += 1
        var tk: String = str(inst.get("take_key",""))
        # instance_id carries the immutable strip serial; binding a strip to
        # its take re-keys it but is not new ink appearing.
        var ident: String = str(inst["instance_id"])
        if not seen_instances.has(ident):
            seen_instances[ident] = true
            if p.x < renderer.size.x-40.0:
                _event("ink_appeared_inside",{"take":tk,"id":str(inst["event_id"]),
                    "x":p.x,"w":renderer.size.x,"since_play_ms":_now_ms()-t_play_ms})
        if tk == origin_key and absf(p.x-playhead_x) < 1.5*density:
            var info: Array = emap.get(str(inst["event_id"]),[])
            if not info.is_empty():
                var expected: float = (float(info[0])-play_from-tb)*density
                near.append([str(inst["event_id"]),snappedf(p.x-playhead_x,.01),
                    snappedf(expected,.01)])
    if visible > 0 and t_play_ms >= 0 and t_first_ink_ms < 0:
        t_first_ink_ms = _now_ms()
        _event("first_ink",{"after_play_ms":t_first_ink_ms-t_play_ms})
    var ci = app.practice_view.stage.count_in
    var row := {"t":_now_ms(),"dt":snappedf(dt,.01),"cap":capture_was_last_frame,
        "ph":str(s.get("phase","")),"tid":int(s.get("transport_id",-1)),
        "run":bool(s.get("running",false)),"pau":bool(s.get("paused",false)),
        "tb":snappedf(tb,.0001),"w":snappedf(world,.0001),"o":origin,
        "pf":play_from,"d":density,"vis":visible,
        "rr":renderer.retained_ready(),"ci":ci.visible if ci != null else false,
        "step":int(s.get("lesson_step",0)),"near":near,
        "foc":DisplayServer.window_is_focused(),
        "minz":DisplayServer.window_get_mode() == DisplayServer.WINDOW_MODE_MINIMIZED}
    if origin_key != key:
        row["okey"] = origin_key.get_slice("|",2) if "|" in origin_key else origin_key
    if is_finite(origin):
        row["sync_px"] = snappedf((world-(origin+play_from+tb))*density,.01)
    frames.append(row)
    capture_was_last_frame = false
    if voice == null:
        voice = app.get_node_or_null("CountInVoicePlayer")
    if voice != null and int(voice.spoken_cues_total) != voice_last_total:
        voice_last_total = int(voice.spoken_cues_total)
        _event("voice",{"number":int(voice.last_spoken_number),"total":voice_last_total,
            "tid":int(s.get("transport_id",-1)),"tb":tb})
    if not capture_queue.is_empty():
        var name: String = capture_queue.pop_front()
        _save_capture(name,s,playhead_x,density,tb,key,play_from,emap)
        capture_was_last_frame = true

func _save_capture(name: String, s: Dictionary, playhead_x: float, density: float,
        tb: float, key: String, play_from: float, emap: Dictionary) -> void:
    capture_count += 1
    var base := "%03d_%s" % [capture_count,name]
    var img: Image = root.get_texture().get_image()
    var png_path: String = out_dir.path_join("shots").path_join(base+".png")
    # Encode off the main thread so the capture does not stall the scroll.
    pending_saves.append(WorkerThreadPool.add_task(func(): img.save_png(png_path)))
    var instances: Array = []
    var ledger = app.practice_view.stage.feedback
    var rgo: Vector2 = renderer.get_global_rect().position
    for inst in renderer.drawn_note_instances:
        var p: Vector2 = inst["position"]
        var tk: String = str(inst.get("take_key",""))
        var clip: Vector2 = inst.get("clip_x",Vector2(-INF,INF))
        var info: Array = emap.get(str(inst["event_id"]),[])
        instances.append({"id":str(inst["event_id"]),"src":str(inst.get("source_id","")),
            "take":tk,"x":p.x+rgo.x,"y":p.y+rgo.y,"lx":p.x,"head":str(inst.get("head","")),
            "gap":float(inst.get("gap",0.0)),"clip":[clip.x+rgo.x,clip.y+rgo.x],
            "beat":info[0] if not info.is_empty() else null,
            "status":ledger.status_for(tk,str(inst["event_id"])) if ledger != null else ""})
    var state_copy: Dictionary = s.duplicate(true)
    state_copy.erase("practice_timeline")
    var final_xf: Transform2D = root.get_final_transform()
    var sidecar := {"name":name,"t":_now_ms(),"phase":phase,"tb":tb,
        "scale":final_xf.x.x,"offset":[final_xf.origin.x,final_xf.origin.y],
        "image_size":[img.get_width(),img.get_height()],
        "world":renderer.stream_world_beat,"density":density,
        "playhead_x":playhead_x+rgo.x,"renderer_rect":[rgo.x,rgo.y,renderer.size.x,renderer.size.y],
        "active_take":key,"play_from":play_from,"instances":instances,
        "visible_takes":renderer.visible_take_keys(),
        "passes":_pass_summary(),"state":state_copy}
    var f := FileAccess.open(out_dir.path_join("shots").path_join(base+".json"),FileAccess.WRITE)
    f.store_string(JSON.stringify(sidecar))
    f.close()
    _event("capture",{"file":base+".png","tb":tb})

func _pass_summary() -> Array:
    var out: Array = []
    for item in renderer.stream_passes:
        out.append({"serial":item.get("serial"),"kind":item.get("kind"),
            "take":item.get("take_key"),"origin":item.get("world_origin"),
            "floor":item.get("source_floor"),"ceiling":item.get("source_ceiling"),
            "pending":item.get("pending"),"empty_strip":item.get("admitted_on_empty_strip",false)})
    return out

func _finish(reason: String) -> void:
    _event("finish",{"reason":reason})
    var f := FileAccess.open(out_dir.path_join("frames.jsonl"),FileAccess.WRITE)
    for row in frames:
        f.store_line(JSON.stringify(row))
    f.close()
    var g := FileAccess.open(out_dir.path_join("events.json"),FileAccess.WRITE)
    g.store_string(JSON.stringify({"events":events,"t_ready_ms":t_ready_ms,
        "t_play_ms":t_play_ms,"t_first_ink_ms":t_first_ink_ms,"takes":takes,
        "take_meta":take_meta,"reason":reason,"scenario":scenario}))
    g.close()
    for task in pending_saves:
        WorkerThreadPool.wait_for_task_completion(task)
    print("R1_SWEEP_DONE:",reason)
    quit(0)
    # With the embedded worker and the virtual MIDI port alive the process
    # can outlive quit(); everything is written, so end it.
    await create_timer(3.0).timeout
    print("R1_SWEEP_FORCED_EXIT")
    OS.kill(OS.get_process_id())

func _take_len(s: Dictionary) -> float:
    return maxf(1.0,float(s.get("duration_beats",8.0))-float(s.get("play_from_beat",0.0)))

func _process(_delta: float) -> bool:
    if app == null or not is_instance_valid(app):
        return false
    var now := _now_ms()
    if now > max_ms:
        _capture("timeout_final")
        if flags.has("final_requested"):
            _finish("max_time")
            return true
        flags["final_requested"] = true
        return false
    if not app.score_error.is_empty() and not flags.has("score_error"):
        flags["score_error"] = true
        _event("score_error",{"error":str(app.score_error)})
        _capture("score_error")
    var s: Dictionary = _state()
    var tid: int = int(s.get("transport_id",-1))
    var running: bool = bool(s.get("running",false))
    var st_phase: String = str(s.get("phase",""))
    if st_phase != last_phase:
        _event("engine_phase",{"from":last_phase,"to":st_phase,"tid":tid,
            "step":s.get("lesson_step"),"feedback":str(s.get("feedback",""))})
        last_phase = st_phase
    var step: int = int(s.get("lesson_step",0))
    if step != last_step:
        _event("lesson_step",{"from":last_step,"to":step,"steps":s.get("lesson_steps")})
        if last_step > 0 and step != last_step and phase != "boot" and stage_seen_ms < 0:
            stage_seen_ms = now
            _capture("next_stage_shown")
        last_step = step
    var tb: float = app._transport_beat_now()
    if running:
        idle_since_ms = -1   # an idle wait is only one uninterrupted stop
    if running and tid != last_tid and tid >= 0:
        takes.append(tid)
        take_meta[str(tid)] = {"index":takes.size(),"start_ms":now,
            "len":_take_len(s),"from":s.get("play_from_beat"),"bpm":s.get("bpm"),
            "step":step,"preview":s.get("preview_only")}
        _event("take_started",{"tid":tid,"index":takes.size(),"len":_take_len(s),
            "preview":s.get("preview_only"),"bpm":s.get("bpm"),"step":step,
            "cib":s.get("count_in_bar_beats"),"ci":s.get("count_in_beats"),
            "pf":s.get("play_from_beat")})
        last_tid = tid
        # The performer reads the plan when it sees the NEXT take start.
        var index: int = takes.size()
        _write_control("mixed" if index < 2 else "clean","take%d" % (index+1))
    match phase:
        "boot":
            if not app.native_started or not app.startup_last_music_checked:
                return false
            if not bool(s.get("loaded",false)) or not _ready_score():
                return false
            t_ready_ms = now
            _event("ready",{"notes":renderer.timeline.notes.size() if renderer else -1,
                "revision":s.get("revision"),"steps":s.get("lesson_steps"),
                "bpm":s.get("bpm"),"strategy":s.get("exercise_strategy")})
            _capture("ready")
            _advance("wait_midi")
        "wait_midi":
            if not FileAccess.file_exists(out_dir.path_join("performer_connected")):
                if now-phase_ms > 30000:
                    _event("midi_not_connected")
                    _finish("midi_not_connected")
                    return true
                return false
            if app.command_state.pending or not _ready_score() or \
                    str(s.get("device","")).is_empty():
                if now-phase_ms > 30000:
                    _event("midi_device_not_in_state",{"device":s.get("device")})
                    _finish("midi_not_in_state")
                    return true
                return false
            if now-phase_ms < 1500:
                return false
            _capture("ready_midi_connected")
            _advance("play")
        "play":
            if _press(app.practice_view.start_button,"Play"):
                t_play_ms = now
                _advance("take1")
        "take1":
            if not running or tid != (takes[0] if not takes.is_empty() else -2):
                return false
            var count_in: float = float(s.get("count_in_beats",4.0))
            if not flags.has("ci_mid") and tb > -count_in*0.5 and tb < 0.0:
                flags["ci_mid"] = true
                _capture("take1_countin")
            if scenario == "cipause" and not flags.has("ci_paused") and \
                    tb > -count_in+1.15 and tb < -0.5:
                if _press(app.practice_view.start_button,"Pause(count-in)"):
                    flags["ci_paused"] = true
                    pause_done = true
                    _capture("take1_countin_pause_pressed")
                    _advance("paused")
                    return false
            if not flags.has("first_note") and tb >= 0.0:
                flags["first_note"] = true
                _capture("take1_first_note_at_playhead")
            var length: float = float(take_meta[str(tid)]["len"])
            _periodic(tid,tb,"take1")
            if pause_done and not flags.has("pause_skipped") and tb >= length*0.45:
                flags["pause_skipped"] = true
                _advance("take1_rest")
                return false
            if not pause_done and tb >= length*0.45 and not bool(s.get("paused",false)):
                if _press(app.practice_view.start_button,"Pause"):
                    pause_done = true
                    pause_requested_ms = now
                    _capture("take1_pause_pressed")
                    _advance("paused")
        "paused":
            if not bool(s.get("paused",false)):
                if now-phase_ms > 5000:
                    _event("pause_not_acknowledged")
                    _advance("take1_rest")
                return false
            if not flags.has("paused_shot") and now-phase_ms > 700:
                flags["paused_shot"] = true
                _capture("take1_paused")
            if now-phase_ms > 2200 and _press(app.practice_view.start_button,"Resume"):
                _advance("resuming")
        "resuming":
            if bool(s.get("paused",false)):
                return false
            if not flags.has("resume_ci") and app.practice_view.stage.count_in.visible:
                flags["resume_ci"] = true
                _capture("take1_resume_countin")
            if now-phase_ms > 2500 or tid != takes[0]:
                _capture("take1_resumed_playing")
                _advance("take1_rest")
        "take1_rest":
            # Let take 1 finish and the engine repeat/continue on its own.
            if running and tid == takes[0]:
                _periodic(tid,tb,"take1")
                return false
            if takes.size() >= 2 and running and tid == takes[1]:
                _capture("take2_started")
                _advance("take2")
                return false
            _idle_play(s,now,"after_take1")
        "take2":
            if tid != takes[1]:
                _advance("take2_ended_early")
                return false
            _periodic(tid,tb,"take2")
            if retry_done and not flags.has("retry_skipped"):
                flags["retry_skipped"] = true
                _advance("clean_takes")
                return false
            var len2: float = float(take_meta[str(tid)]["len"])
            if not retry_done and tb >= len2*0.35:
                if _press(app.practice_view.practice_retry_button,"Retry"):
                    retry_done = true
                    _capture("retry_pressed")
                    _advance("retry")
        "take2_ended_early":
            _advance("retry")
            retry_done = true
        "retry":
            if not flags.has("retry_mid") and now-phase_ms > 900:
                flags["retry_mid"] = true
                _capture("retry_preparing")
            if app.practice_view.stage.count_in.visible and not flags.has("retry_ci"):
                flags["retry_ci"] = true
                _capture("retry_countin")
            if running and takes.size() >= 3 and tid == takes[-1] and tid != takes[1]:
                _advance("clean_takes")
                return false
            _idle_play(s,now,"after_retry")
        "clean_takes":
            if running:
                _periodic(tid,tb,"take%d" % takes.size())
                if not flags.has("first_at_%d" % tid) and tb >= 0.0:
                    flags["first_at_%d" % tid] = true
                    _capture("take%d_first_note" % takes.size())
            else:
                _idle_play(s,now,"clean")
            if stage_seen_ms > 0 and now-stage_seen_ms > 12000:
                _capture("next_stage_playing")
                _finish("next_stage_reached")
                return true
    return false

func _idle_play(s: Dictionary, now: int, label: String) -> void:
    # If the engine stops and waits for the user, press Play like a user.
    if bool(s.get("running",false)) or app.command_state.pending:
        idle_since_ms = -1
        return
    if idle_since_ms < 0:
        idle_since_ms = now
        return
    if now-idle_since_ms > 15000:
        if not flags.has("idle_"+label+str(takes.size())):
            flags["idle_"+label+str(takes.size())] = true
            _capture("idle_"+label)
            _event("engine_waits_for_user",{"label":label,
                "button":app.practice_view.start_button.text,
                "phase_engine":str(s.get("phase",""))})
        if app.practice_view.start_button.text.begins_with("Play") and \
                _press(app.practice_view.start_button,"Play("+label+")"):
            idle_since_ms = -1

func _periodic(tid: int, tb: float, label: String) -> void:
    # Enough frames that every graded head is seen left of the playhead.
    var density: float = renderer.timeline.pixels_per_beat
    var step_beats: float = maxf(0.75,renderer.size.x*0.25/maxf(1.0,density))
    var last: float = float(last_capture_beat.get(tid,-INF))
    if tb >= 0.0 and tb-last >= step_beats:
        last_capture_beat[tid] = tb
        _capture("%s_b%05.1f" % [label,tb])
