extends SceneTree
const Coordinator := preload("res://practice_frame_coordinator.gd")

class Busy:
    extends RefCounted
    var calls := 0
    func present_busy(_busy: bool) -> void:
        calls += 1

class Effects:
    extends RefCounted
    var last_beat := NAN
    func sync_beat(beat: float, _meter: int, _ungraded: bool) -> void:
        last_beat = beat

class Renderer:
    extends RefCounted
    var last_beat := NAN
    var last_visual := NAN
    func present(_state: Dictionary, beat: float, visual: float) -> void:
        last_beat = beat
        last_visual = visual

class Stage:
    extends RefCounted
    var renderer = Renderer.new()
    var effects = Effects.new()

class Practice:
    extends RefCounted
    var stage = Stage.new()
    var calls := 0
    func present_busy(_busy: bool) -> void:
        calls += 1

class Pulses:
    extends RefCounted
    var prunes := 0
    func prune_expired(_now_ms: int) -> void:
        prunes += 1

class Session:
    extends RefCounted
    var checks := 0
    func ensure_current(_now_ms: int) -> void:
        checks += 1

class Demo:
    extends RefCounted
    var loaded := true
    var started := false
    var synchronized := NAN
    var kept := NAN
    func synchronize(_state: Dictionary, beat: float) -> void:
        synchronized = beat
        started = true
    func keep_synchronized(beat: float, _bpm: float, _segments: Array) -> void:
        kept = beat

class App:
    extends RefCounted
    var last_state: Dictionary = {}
    var frame_diagnostics := false
    var current_screen := "practice"
    var score_effects = Pulses.new()
    var settings_view = Busy.new()
    var practice_view = Practice.new()
    var lesson_view = Busy.new()
    var lesson_session = Session.new()
    var demo_player = Demo.new()
    var action_pending := false
    var listen_sync_diagnostics := false
    var last_listen_sync_report_ms := 0
    var last_playhead_strike_transport := 0
    var last_playhead_strike_beat := 0.0
    var living_chords: Array = []
    var phase0_smoke_mode := false
    var phase0_last_lead_tick := -999
    var phase0_last_cursor_tick := -999
    var clock_samples := 0
    var midi_polls := 0
    var metronome_updates := 0

    func _transport_beat_at(_at_ms: int) -> float:
        clock_samples += 1
        return 1.25

    func _read_live_midi() -> void:
        midi_polls += 1

    var count_in_beat := NAN
    func _update_count_in(beat: float, _at_ms: int) -> void:
        metronome_updates += 1
        count_in_beat = beat

    func _unrolled_score_beat_at(clock: float, _at_ms: int) -> float:
        return clock + 8.0

    func _native_score_ready() -> bool:
        return true

    func _preview_note_arrivals(_groups: Array) -> void:
        pass

func _initialize() -> void:
    var failures := 0
    var app := App.new()
    Coordinator.advance(app,0.016)
    if app.clock_samples != 1 or app.midi_polls != 1 or \
            app.metronome_updates != 1 or app.count_in_beat != 1.25 or \
            app.score_effects.prunes != 1 or \
            app.last_playhead_strike_transport != -1:
        failures += 1
    app.last_state = {"mode":"listen","running":true,"paused":false,
        "loaded":true,"transport_id":7,"play_from_beat":0.0}
    app.last_playhead_strike_transport = 7
    app.last_playhead_strike_beat = 1.0
    Coordinator.advance(app,0.016)
    if app.clock_samples != 2 or app.demo_player.synchronized != 1.25 or \
            app.demo_player.kept != 1.25 or \
            app.practice_view.stage.renderer.last_beat != 1.25 or \
            app.practice_view.stage.renderer.last_visual != 9.25 or \
            app.practice_view.stage.effects.last_beat != 1.25 or \
            app.last_playhead_strike_beat != 1.25:
        failures += 1
    print("PRACTICE_FRAME_COORDINATOR_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
