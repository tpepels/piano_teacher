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

func one_countdown_for_a_long_lead() -> void:
    var count_in = app.practice_view.stage.count_in
    var voice := RecordingVoice.new()
    root.add_child(voice)
    count_in.attach_voice_service(voice)
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
    await first_play_lands_one_count_in_bar_ahead()
    await one_countdown_for_a_long_lead()
    print("FIRST_PLAY_COUNT_IN_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
