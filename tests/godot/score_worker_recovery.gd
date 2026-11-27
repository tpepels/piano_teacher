extends SceneTree
## Real GDExtension, embedded engine, mailbox and exec-launched worker.
var bridge
var replies: Dictionary = {}
var failures := 0

func _initialize() -> void:
    call_deferred("_run")

func _check(ok: bool, problem: String) -> void:
    if not ok:
        failures += 1
        printerr("NATIVE_SCORE_RECOVERY: ",problem)

func _pump() -> void:
    for reply in bridge.take_responses():
        var id: int = int(reply["id"])
        _check(not replies.has(id),"A native request published twice")
        replies[id] = reply

func _wait_for(id: int, timeout_ms: int = 30000) -> Dictionary:
    var deadline: int = Time.get_ticks_msec()+timeout_ms
    while id >= 0 and not replies.has(id) and Time.get_ticks_msec() < deadline:
        _pump()
        await process_frame
    if not replies.has(id):
        _check(false,"Native request %d did not finish" % id)
        return {}
    var reply: Dictionary = replies[id]
    return reply

func _document(reply: Dictionary) -> Dictionary:
    if reply.is_empty():
        return {}
    var bytes: PackedByteArray = reply["body"]
    var body: Variant = JSON.parse_string(bytes.get_string_from_utf8())
    _check(int(reply["status"]) == 0 and body is Dictionary,
        "Unexpected native reply %s" % str(body))
    return body if body is Dictionary else {}

func _submit(operation: String, values: Dictionary = {}) -> int:
    return bridge.submit(operation,JSON.stringify(values))

func _request(operation: String, values: Dictionary = {}) -> Dictionary:
    return _document(await _wait_for(_submit(operation,values)))

func _identity(state: Dictionary, generation: int) -> Dictionary:
    return {"fingerprint":state.get("piece_fingerprint",""),
        "revision":int(state.get("revision",-1)),
        "stage_key":state.get("stage_key",""),"hand":state.get("hand",""),"generation":generation}

func _worker_pid() -> int:
    var output: Array = []
    OS.execute("/bin/ps",["-o","pid=,args=","--ppid",str(OS.get_process_id())],output)
    if not output.is_empty():
        for line in str(output[0]).split("\n",false):
            if line.contains("piano_teacher.application.score_worker"):
                return int(line.strip_edges().get_slice(" ",0))
    return -1

func _signal_worker(pid: int, signum: String) -> bool:
    return pid > 0 and OS.execute("/bin/kill",["-"+signum,str(pid)]) == 0

func _bound(bundle: Dictionary, identity: Dictionary) -> bool:
    return bundle.get("status") == "ready" and \
        int(bundle.get("revision",-1)) == identity["revision"] and \
        bundle.get("fingerprint") == identity["fingerprint"] and \
        bundle.get("stage_key") == identity["stage_key"] and bundle.get("hand") == identity["hand"]

func _start() -> bool:
    bridge = ClassDB.instantiate("PianoNative")
    var deadline: int = Time.get_ticks_msec()+12000
    while bridge != null and not bridge.is_ready() and Time.get_ticks_msec() < deadline:
        await process_frame
    return bridge != null and bridge.is_ready()

func _shutdown(pid: int) -> void:
    bridge = null
    await process_frame
    _check(pid > 0 and not DirAccess.dir_exists_absolute("/proc/%d" % pid) and _worker_pid() == -1,
        "Native shutdown left a live or unreaped score worker")
    replies.clear()

func _exercise() -> void:
    var before_open: Dictionary = await _request("performance.diagnostics")
    var selected: Dictionary = await _request("library.open",{"id":"phase6_native_fixture.mid"})
    var after_open: Dictionary = await _request("performance.diagnostics")
    _check(int(after_open.get("engine_tick",{}).get("samples",0)) >=
        int(before_open.get("engine_tick",{}).get("samples",0))+3,
        "Musical ticks stopped while source preparation waited for real fingering inference")
    var identity := _identity(selected,1)
    _check(_bound(await _request("score.bundle",identity),identity),
        "Original source was not prepared")
    var pid := _worker_pid()
    if not _signal_worker(pid,"STOP"):
        _check(false,"Could not suspend the actual notation child")
        return
    var old_id: int = _submit("score.bundle",identity)
    var before: Dictionary = await _request("performance.diagnostics")
    await create_timer(0.85).timeout
    var during: Dictionary = await _request("performance.diagnostics")
    _check(int(during.get("engine_tick",{}).get("samples",0)) >
        int(before.get("engine_tick",{}).get("samples",0)),
        "Musical ticks stopped while notation could not answer")
    _check(not replies.has(old_id),"A stopped notation worker returned a score")
    var saturated := 0
    var pending: Array[int] = []
    for attempt in range(12):
        var candidate: int = _submit("score.bundle",identity)
        if candidate < 0:
            saturated += 1
        else:
            pending.append(candidate)
    _check(pending.size() == 7 and saturated == 5,
        "Native asset queue exceeded its eight total slots")
    for candidate in pending:
        bridge.cancel_asset(candidate)
    var stopped: Dictionary = await _request("practice.command",{"action":"stop"})
    _check(not stopped.is_empty(),"Stop could not acknowledge during score generation")
    bridge.cancel_asset(old_id)
    var moved: Dictionary = await _request("practice.command",{"action":"select_step","number":3})
    _check(int(moved.get("state",{}).get("revision",-1)) != identity["revision"],
        "Navigation did not change the selected score")
    var replacement: Dictionary = await _request(
        "library.open",{"id":"ci_state_journey_two_four.mid"})
    var current := _identity(replacement,3)
    _check(current["fingerprint"] != identity["fingerprint"] and
        not str(current["fingerprint"]).is_empty(),
        "Source replacement did not commit during the blocked score")
    var retry_id: int = _submit("score.bundle",current)
    bridge.cancel_asset(retry_id)
    current["generation"] = 4
    _check(_bound(await _request("score.bundle",current),current),
        "Retry did not prepare the newest source")
    _check(not replies.has(old_id) and not replies.has(retry_id),
        "A cancelled native score published")
    for candidate in pending:
        _check(not replies.has(candidate),"A cancelled queued score published")
    _check(not DirAccess.dir_exists_absolute("/proc/%d" % pid),
        "Cancellation did not reap a stopped child")
    pid = _worker_pid()
    if not _signal_worker(pid,"KILL"):
        _check(false,"Could not crash the actual notation child")
        return
    current["generation"] = 5
    _check(_bound(await _request("score.bundle",current),current),
        "Score did not recover after a real worker crash")
    _check(_worker_pid() != pid,"A crashed worker was reused")
    # Exercise the same replay receipt used when detached validation rejects
    # the most recent bundle. The replacement must have a fresh PID.
    pid = _worker_pid()
    current["generation"] = 6
    current["rejected_generation"] = 5
    _check(_bound(await _request("score.bundle",current),current) and _worker_pid() != pid,
        "Detached rejection did not retire and replay the matching native result")

func _run() -> void:
    if not ClassDB.class_exists("PianoNative"):
        GDExtensionManager.load_extension("res://native/piano_bridge.gdextension")
    if await _start():
        await _exercise()
        await _shutdown(_worker_pid())
    else:
        _check(false,"Cannot start the production native bridge")
    for run in range(2):
        if await _start():
            var state: Dictionary = await _request(
                "library.open",{"id":"phase6_native_fixture.mid"})
            var identity := _identity(state,run+1)
            _check(_bound(await _request("score.bundle",identity),identity),
                "Restart did not prepare real notation")
            await _shutdown(_worker_pid())
        else:
            _check(false,"Cannot restart the production native bridge")
    print("NATIVE_SCORE_RECOVERY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
