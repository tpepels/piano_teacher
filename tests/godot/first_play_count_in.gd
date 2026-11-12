extends SceneTree
## Owner decision 2026-11-08 (Task 2b): "the notes should appear closer to the
## playhead, so the wait is about one bar" and "There should always only be a
## single ichi ni .. countdown, never more. Only the bar before the start of
## the exercise." This drives the production app (native_production_fixture)
## through a first Play on an empty strip and through the real count-in cue
## coordinator with a lead longer than one bar.

class RecordingRequest extends RefCounted:
    var timeout := 5.0
    var calls: Array[Dictionary]
    func _init(recorded: Array[Dictionary]) -> void:
        calls = recorded
    func request(_operation: String, payload: Dictionary) -> int:
        calls.append(payload.duplicate(true))
        return OK

class RecordingVoice extends Node:
    var spoken: Array[int] = []
    var spoken_enabled := true
    func speak_beat(number: int) -> bool:
        spoken.append(number)
        return true
    func set_spoken_enabled(enabled: bool) -> void:
        spoken_enabled = enabled
    func status() -> Dictionary:
        return {"enabled":spoken_enabled,"available":true,"missing":[]}

class FixtureApp extends "native_production_fixture.gd":
    var wire_commands: Array[Dictionary] = []
    var clicks := 0
    func _ready() -> void:
        super._ready()
        action_request = RecordingRequest.new(wire_commands)
    func _count_tick(_accent: bool, _sampled_beat: float = NAN) -> void:
        clicks += 1
    func _raw_click(_accent: bool) -> void:
        clicks += 1

var app: FixtureApp
var failures: Array[String] = []
var take_origin := NAN
var transport := 500
var voice: RecordingVoice

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("FIRST_PLAY_COUNT_IN_FAIL:", message)

func ready_frames() -> void:
    # The production frame owner prepares the hidden READY take.
    var renderer = app.practice_view.stage.renderer
    for _i in range(4):
        app._process(0.0)
        await process_frame
    var deadline := Time.get_ticks_msec() + 5000
    while not renderer.retained_ready() and Time.get_ticks_msec() < deadline:
        app._process(0.0)
        await process_frame

func first_play_lands_one_count_in_bar_ahead() -> void:
    var renderer = app.practice_view.stage.renderer
    var count_in: float = float(app.last_state.get("next_count_in_beats", NAN))
    check(is_finite(count_in) and count_in > 0.0,
        "The engine publishes the count-in a Play will use: " + str(count_in))
    if not is_finite(count_in):
        count_in = float(app.last_state.get("count_in_bar_beats", 4.0))
    var bpm: float = float(app.last_state.get("bpm", 60.0))
    var visual_now: float = app.score_flow.project(Time.get_ticks_msec())
    var visible_before: int = app._visible_score_noteheads()
    check(visible_before == 0, "READY shows no ink right of the playhead")
    app._send_action({"action":"start"})
    check(app.wire_commands.size() == 1, "Play reaches the engine exactly once")
    if app.wire_commands.is_empty():
        return
    var lead_seconds: float = float(app.wire_commands[0].get(
        "presentation_lead_seconds", NAN))
    var lead_beats: float = lead_seconds*bpm/60.0
    var armed: int = renderer._stream_armed_serial
    var origin := NAN
    for item in renderer._stream_queue.online:
        if int(item.get("take_owner", item["serial"])) == armed:
            origin = float(item["world_origin"])
            break
    var opening: float = maxf(0.0, float(app.last_state.get("play_from_beat", 0.0)))
    var start_world: float = origin + opening
    take_origin = origin
    print("FIRST_PLAY_MEASURE:", JSON.stringify({
        "bpm":bpm, "count_in_beats":count_in,
        "lead_beats":lead_beats, "lead_seconds":lead_seconds,
        "start_world_minus_now":start_world-visual_now}))
    # One count-in bar, plus at most the frame or two between sampling
    # visual_now here and inside _send_action.
    check(lead_beats >= count_in - .001 and lead_beats <= count_in + .15,
        "Play -> first note is one count-in bar (%.2f beats), got %.2f beats" % [
            count_in, lead_beats])
    check(absf((start_world - visual_now) - lead_beats) < .15,
        "The score deadline equals the lead sent to the grading engine")
    # The opening is on screen immediately, already approaching the playhead;
    # it does not travel in from beyond the right edge.
    app._process(0.0)
    await process_frame
    app._process(0.0)
    var first_x := INF
    var first_onset := INF
    for event in renderer.layout.ordered_events:
        var id: String = str(event.get("id", ""))
        if renderer.drawn_noteheads.has(id) and float(event.beat) < first_onset:
            first_onset = float(event.beat)
            first_x = float(renderer.drawn_noteheads[id].x)
    var playhead_x: float = renderer.size.x*renderer.PLAYHEAD_FRACTION
    var density: float = renderer.timeline.pixels_per_beat
    check(is_finite(first_x) and first_x < renderer.size.x,
        "The opening note is visible right after Play")
    var world_now: float = renderer.stream_world_beat
    var expected_x: float = playhead_x + (origin + first_onset - world_now)*density
    check(absf(first_x - expected_x) < density*.5,
        "The first notehead sits one count-in bar right of the playhead: x=%.1f expected %.1f" % [
            first_x, expected_x])

func transport_state(beat: float, paused: bool) -> Dictionary:
    var fixture: Dictionary = app.last_state
    var count_in: float = float(fixture.get("next_count_in_beats", 4.0))
    return {"loaded":true, "revision":app.revision,
        "piece_fingerprint":str(fixture.get("piece_fingerprint", "")),
        "transport_id":transport, "mode":"practice", "hand":"both",
        "phase":"paused" if paused else "count_in" if beat < 0.0 else "playing",
        "running":true, "paused":paused, "clock_beat":beat,
        "bpm":float(fixture.get("bpm", 60.0)), "play_from_beat":0.0,
        "count_in_beats":count_in, "count_in_bar_beats":4,
        "next_count_in_beats":count_in, "pause_context":"count_in" if paused else null,
        "duration_beats":app.practice_view.stage.renderer.timeline.duration_beats}

func publish(state: Dictionary) -> void:
    app.last_state = state
    app.last_state_tick = Time.get_ticks_msec()
    app.visual_transport_clock.accept(state, app.last_state_tick, app.last_state_tick)

func pause_one_beat_into_count_in_then_resume() -> void:
    # Task 2b review regression: with the opening one count-in bar ahead,
    # Pause one beat into the count-in, then Resume. Resume must reuse the
    # paused take's immutable ink: its lead is the remainder of the bar, not
    # a new offscreen append, and only one count-in cycle is heard.
    var renderer = app.practice_view.stage.renderer
    var count_in: float = float(app.last_state.get("next_count_in_beats", 4.0))
    var bpm: float = float(app.last_state.get("bpm", 60.0))
    # Round 4 (M4): Godot speaks the count-in from the deadline it reserved
    # at the Play press, so "1" may already have been heard on that press.
    var heard_at_press: Array = voice.spoken.duplicate()
    voice.spoken.clear()
    var ready_state: Dictionary = app.last_state.duplicate()
    # Play's acknowledgement binds the armed take to its transport.
    var world: float = app.score_flow.project(Time.get_ticks_msec())
    app._on_action(0, JSON.stringify(transport_state(world - take_origin, false)).to_utf8_buffer())
    var deadline := Time.get_ticks_msec() + 8000
    while Time.get_ticks_msec() < deadline:
        world = app.score_flow.project(Time.get_ticks_msec())
        if world - take_origin >= -(count_in - 1.0):
            break
        publish(transport_state(world - take_origin, false))
        app._process(0.0)
        await process_frame
    var paused_beat: float = app.score_flow.project(Time.get_ticks_msec()) - take_origin
    publish(transport_state(paused_beat, true))
    for _i in range(6):
        app._process(0.0)
        await process_frame
    app.wire_commands.clear()
    app._send_action({"action":"resume"})
    check(app.wire_commands.size() == 1, "Resume reaches the engine")
    if app.wire_commands.is_empty():
        return
    var sent: Dictionary = app.wire_commands[0]
    var lead_beats: float = float(sent.get("presentation_lead_seconds", NAN))*bpm/60.0
    var remainder: float = take_origin - app.score_flow.project(Time.get_ticks_msec())
    print("PAUSE_RESUME_MEASURE:", JSON.stringify({"bpm":bpm,
        "count_in_beats":count_in, "paused_beat":paused_beat,
        "lead_beats":lead_beats, "remaining_bar_beats":remainder,
        "reuse_pending_score":sent.get("reuse_pending_score")}))
    check(bool(sent.get("reuse_pending_score", false)),
        "Resume reuses the paused take's already placed ink")
    check(lead_beats > 0.0 and lead_beats <= count_in - 1.0 + .05,
        "Resume waits at most the remainder of the bar: %.2f beats" % lead_beats)
    check(absf(lead_beats - remainder) < .15,
        "Resume's deadline is the paused opening's own world position")
    # The countdown on Resume covers only the remaining beats of that bar.
    var resumed: Dictionary = transport_state(paused_beat, false)
    resumed["resume_count_in_beat"] = -lead_beats
    var tick := Time.get_ticks_msec()
    var elapsed := 0
    while -lead_beats + float(elapsed)*bpm/60000.0 < 0.0:
        # The engine's transport beat and the resume countdown share the
        # original first-beat deadline after a reused Resume.
        app.metronome_frame.update(resumed, tick,
            -lead_beats + float(elapsed)*bpm/60000.0, tick + elapsed)
        elapsed += 20
    var cycle: Array = (heard_at_press + voice.spoken) if voice.spoken.size() < 4 \
        else voice.spoken
    check(cycle == [1, 2, 3, 4],
        "Pause and Resume inside the count-in hear exactly one cycle: %s (at Play: %s)" % [
            str(voice.spoken),str(heard_at_press)])
    print("PAUSE_RESUME_SPOKEN:", JSON.stringify({"spoken":voice.spoken}))
    app.last_state = ready_state

func one_countdown_for_a_long_lead() -> void:
    var count_in = app.practice_view.stage.count_in
    voice.spoken.clear()
    var bar := 4
    var shown_early := false
    var shown_in_bar := false
    # The engine's count-in stays one bar even when the score's lead is far
    # longer (ink appended behind other moving ink).
    var state := {"loaded":true, "running":true, "paused":false,
        "phase":"count_in", "revision":7, "transport_id":41, "bpm":60.0,
        "count_in_beats":4.0, "count_in_bar_beats":bar}
    app.clicks = 0
    var beat := -13.0
    while beat < 0.0:
        app.metronome_frame.update(state, Time.get_ticks_msec(), beat,
            Time.get_ticks_msec())
        if count_in.visible:
            if beat < -4.0 - .0001:
                shown_early = true
            else:
                shown_in_bar = true
        beat += .05
    check(voice.spoken == [1, 2, 3, 4],
        "A 13-beat lead speaks exactly one Ichi Ni San Shi: " + str(voice.spoken))
    check(app.clicks == 0, "The silent lead before the count-in bar has no clicks")
    check(not shown_early, "No countdown is shown before the count-in bar")
    check(shown_in_bar, "The countdown is shown during the count-in bar")
    # Resume after a long pause: one bar of countdown before grading resumes.
    voice.spoken.clear()
    var resumed := {"loaded":true, "running":true, "paused":false,
        "phase":"count_in", "revision":7, "transport_id":42, "bpm":60.0,
        "count_in_beats":4.0, "count_in_bar_beats":bar,
        "resume_count_in_beat":-9.0}
    var tick := Time.get_ticks_msec()
    var elapsed := 0
    while elapsed <= 9000:
        app.metronome_frame.update(resumed, tick, 5.0, tick + elapsed)
        elapsed += 50
    check(voice.spoken == [1, 2, 3, 4],
        "A 9-beat resume lead speaks exactly one countdown: " + str(voice.spoken))
    print("FIRST_PLAY_COUNT_IN_TICKS:", JSON.stringify({"spoken":voice.spoken}))

func run() -> void:
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.size = Vector2i(1600, 1000)
    root.add_child(app)
    await process_frame
    app._navigate("practice")
    var fixture_error: String = await app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(fixture_error.is_empty(), fixture_error)
    if not fixture_error.is_empty():
        print("FIRST_PLAY_COUNT_IN_FAILURES:", failures.size())
        quit(1)
        return
    await ready_frames()
    voice = RecordingVoice.new()
    root.add_child(voice)
    app.practice_view.stage.count_in.attach_voice_service(voice)
    await first_play_lands_one_count_in_bar_ahead()
    await pause_one_beat_into_count_in_then_resume()
    await one_countdown_for_a_long_lead()
    print("FIRST_PLAY_COUNT_IN_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
