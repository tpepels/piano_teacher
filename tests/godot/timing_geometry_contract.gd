extends SceneTree
## Whole-axis spacing contract. Horizontal tuning is a presentation choice,
## not another tempo calculation or a per-note engraving exception.
const Spacing := preload("res://notation/shared/spacing_policy.gd")
const Timeline := preload("res://notation/shared/timeline.gd")
const Barline := preload("res://notation/native/barline_layout.gd")
const ContextPainter := preload("res://notation/native/context_painter.gd")
const ViewportFit := preload("res://notation/native/viewport_fit.gd")
const InkGeometry := preload("res://notation/native/ink_geometry.gd")
const Admission := preload("res://score_stream_admission.gd")
const Markers := preload("res://score_step_timeline.gd")
const MeterGrid := preload("res://moving_meter_grid.gd")
const Flow := preload("res://continuous_score_flow.gd")
const Tempo := preload("res://tempo_timeline.gd")
const NativeView := preload("res://notation/native/view.gd")
const RenderPass := preload("res://notation/native/render_pass.gd")
const RetainedProjection := preload("res://notation/native/retained_note_projection.gd")
const ScoreView := preload("res://notation/shared/view_base.gd")

var failures := 0

func check(ok: bool, reason: String) -> void:
    if not ok:
        failures += 1
        print("TIMING_GEOMETRY_FAIL: ", reason)

func near(actual: float, wanted: float, tolerance: float = .0001) -> bool:
    return is_finite(actual) and absf(actual-wanted) <= tolerance

func _initialize() -> void:
    call_deferred("_run_contract")

func _run_contract() -> void:
    # A real mixed-duration source axis: pickup (1/8), 4/4, 3/4, 6/8.
    # The rest and notehead projections must use exactly the same quarter beats.
    var measures := [
        {"start_beat":0.0, "end_beat":0.5, "meter":[1,8]},
        {"start_beat":0.5, "end_beat":4.5, "meter":[4,4]},
        {"start_beat":4.5, "end_beat":7.5, "meter":[3,4]},
        {"start_beat":7.5, "end_beat":10.5, "meter":[6,8]},
    ]
    var original := {
        "schema":Timeline.SCHEMA, "beat_unit":"quarter", "revision":19,
        "duration_beats":10.5, "measures":measures,
        "notes":[
            {"id":"pickup","onset_beats":0.0,"duration_beats":0.5},
            {"id":"first","onset_beats":0.5,"duration_beats":1.0},
            {"id":"syncopated","onset_beats":2.25,"duration_beats":0.25},
            {"id":"three_four","onset_beats":4.5,"duration_beats":3.0},
            {"id":"compound","onset_beats":7.5,"duration_beats":1.5},
        ],
    }
    var source_before: String = JSON.stringify(original)
    var timeline := Timeline.new()
    check(timeline.load_model(original), "mixed source meter and notes load")
    check(near(Timeline.DEFAULT_PIXELS_PER_BEAT,Spacing.DEFAULT_PIXELS_PER_BEAT),
        "semantic timeline reads central default density")
    check(near(RenderPass.PLAYHEAD_FRACTION,Spacing.PLAYHEAD_FRACTION) and
        near(ScoreView.PLAYHEAD_FRACTION,Spacing.PLAYHEAD_FRACTION),
        "retained notes and score projection share one playhead fraction")
    check(near(ViewportFit.MAX_STAFF_GAP,Spacing.MAX_STAFF_GAP) and
        near(InkGeometry.MAX_STAFF_GAP,Spacing.MAX_STAFF_GAP),
        "viewport fitting and ink clearance use the same staff-size limit")
    check(near(ViewportFit.MIN_LOOKAHEAD_BEATS,Admission.MIN_READING_BEATS) and
        near(Admission.MIN_READING_BEATS,Spacing.MIN_LOOKAHEAD_BEATS),
        "reading-space requirements share one policy")
    var markers := Markers.new()
    check(near(markers._density,Spacing.DEFAULT_PIXELS_PER_BEAT) and
        near(markers._next_density,Spacing.DEFAULT_PIXELS_PER_BEAT),
        "step labels inherit the default score scale")
    markers.free()

    var playhead := 510.0
    var visual_world := 2.25
    var gap := 20.0
    for density in [48.0,96.0,144.0,240.0]:
        check(timeline.set_density(density),
            "select valid per-score density %.0f" % density)
        var note_a: float = timeline.screen_x(0.5,visual_world,playhead)
        var note_b: float = timeline.screen_x(2.25,visual_world,playhead)
        check(near(note_b-note_a,1.75*density),
            "separated source attacks preserve quarter-beat distance")
        var boundary_x: Array = []
        for measure in measures:
            boundary_x.append(Barline.project(float(measure["start_beat"]),
                timeline,visual_world,playhead,0.0,gap))
        boundary_x.append(Barline.project(float(measures[-1]["end_beat"]),
            timeline,visual_world,playhead,0.0,gap))
        for index in range(measures.size()):
            var width: float = boundary_x[index+1]-boundary_x[index]
            var beats: float = float(measures[index]["end_beat"])-float(measures[index]["start_beat"])
            check(near(width,beats*density),
                "pickup, 4/4, 3/4 and 6/8 boundaries scale uniformly")
        check(near(Barline.project(2.25,timeline,visual_world,playhead,0.0,gap) -
            note_b,-gap*Barline.LEAD_STAFF_SPACES),
            "staff-space boundary clearance does not change musical X")
        var first_clef: float = ContextPainter.clef_lead_pixels(0,gap)
        var six_sharps: float = ContextPainter.clef_lead_pixels(6,gap)
        check(near(six_sharps-first_clef,
                6.0*ContextPainter.HEADER_KEY_COLUMN_UNITS*gap/
                ContextPainter.HEADER_UNITS_PER_SPACE),
            "header collision clearance and engraved key columns share spacing")

        var rest := {"kind":"rest","source_ceiling":3.0}
        var rest_bounds: Vector2 = Admission.clip_bounds(rest,density,gap,10.5)
        check(near(rest_bounds.y-rest_bounds.x,3.0*density),
            "silent preparation measure has the same density as the source")
        var source := {"kind":"source","clip_floor":0.5,"clip_ceiling":4.5,
            "clip_leading_spaces":1.5,"clip_trailing_spaces":2.0}
        var source_bounds: Vector2 = Admission.clip_bounds(source,density,gap,10.5)
        check(near(source_bounds.y-source_bounds.x,4.0*density+3.5*gap),
            "source clip only adds measured glyph clearance")
        check(near(Markers.marker_x(4.5,visual_world,density,1536.0) -
            timeline.screen_x(4.5,visual_world,
                1536.0*Spacing.PLAYHEAD_FRACTION),0.0),
            "lesson markers and noteheads agree on source beat position")

        var rules: Array[float] = MeterGrid.visible_lines(
            5.0,4000.0,1500.0,density,0.0,measures)
        for boundary in [0.0,0.5,4.5,7.5,10.5]:
            check(rules.has(boundary),
                "blank-staff rules use authored meter at density %.0f" % density)

        for bpm in [40.0,80.0,120.0]:
            var elapsed := 0.25
            var moved: float = timeline.screen_x(2.25,
                visual_world+elapsed*bpm/60.0,playhead)
            check(near(note_b-moved,elapsed*timeline.pixels_per_second(bpm)),
                "only velocity changes with BPM, never source note spacing")
        check(near(Admission.empty_strip_start([],5.0,4.0,1.5,NAN,
                density,gap,10.5),9.0),
            "count-in slot is measured in beats regardless of density")

    check(JSON.stringify(original) == source_before,
        "changing density does not mutate source notes or measure boundaries")

    # Source-local artwork anchors must follow their head through the one
    # canonical camera projection. The painter keeps its original anchors
    # immutable; exported framebuffer/hit instances use screen coordinates.
    # Chord heads can have an anchor different from the head centre.
    var local_note := {"event_id":"source", "position":Vector2(30.0,120.0),
        "anchor":Vector2(24.0,121.0), "head":"head_whole"}
    var projected: Array = []
    var nearest: Dictionary = {}
    check(RetainedProjection.append_visible([local_note],240.0,1000.0,
        200.0,1,projected,nearest) == 1,
        "retained notehead projects into the visible viewport")
    if not projected.is_empty():
        check(projected[0]["position"] == Vector2(270.0,120.0) and
            projected[0]["anchor"] == Vector2(264.0,121.0),
            "retained template anchor and head use the same screen transform")
        check(local_note["position"] == Vector2(30.0,120.0) and
            local_note["anchor"] == Vector2(24.0,121.0),
            "projecting a take cannot mutate its local engraved geometry")

    # Hidden READY scores are already committed physical ink, even while
    # playback reports idle. Neither current source nor its queued rest may
    # shift in response to a new spacing preference. Unchanged requests are
    # harmless, and a newly empty score owner may accept a new density.
    var reserved_view := NativeView.new()
    var initially_selected: float = reserved_view.timeline.pixels_per_beat
    reserved_view._stream_queue.online.append({
        "kind":"source","world_origin":12.0,"source_floor":0.0,
        "source_ceiling":4.0,"admitted_density":initially_selected})
    check(not reserved_view.set_density(144.0) and
        near(reserved_view.timeline.pixels_per_beat,initially_selected),
        "hidden READY source locks the horizontal scale before transport starts")
    check(reserved_view.set_density(initially_selected) and
        reserved_view._stream_queue.online.size() == 1,
        "unchanged density keeps existing source reservation intact")
    reserved_view._stream_queue.online.clear()
    check(reserved_view.set_density(144.0) and
        near(reserved_view.timeline.pixels_per_beat,144.0),
        "clearing all reservations permits tuning the next score")
    reserved_view.free()

    # Speedups and slowdowns change the derivative of an endless world axis.
    # A delayed retrospective slowdown may pay timing debt gradually, but
    # must neither freeze nor rewind its published presentation coordinate.
    var flow := Flow.new()
    check(near(flow.sample(1000,60.0),0.0),"world begins at source-neutral zero")
    var one: float = flow.sample(2000,60.0)
    var two: float = flow.sample(3000,120.0)
    var three: float = flow.sample(4000,120.0)
    var four: float = flow.sample(5000,40.0)
    var five: float = flow.sample(6000,40.0)
    check(one < two and two < three and three < four and four < five,
        "40/60/120 BPM changes never stop or reverse the visual bar")
    flow.switch_rate_at(5500.0,20.0)
    var after_late_change: float = flow.project(6000)
    check(after_late_change >= five and flow.project(7000) > after_late_change,
        "a late slower-tempo notice never rewinds or stops the world")

    # Every countdown, admission lead and display clock must agree on the
    # same signed quarter-beat conversions, including negative count-in time.
    for rate in [12.0,24.0,40.0,80.0,120.0,240.0]:
        for signed_beats in [-8.0,-3.0,-0.25,0.0,0.125,1.0,4.0,12.0]:
            var seconds: float = Tempo.seconds_from_beats(signed_beats,rate)
            check(near(Tempo.beats_from_seconds(seconds,rate),signed_beats),
                "signed BPM-to-seconds conversion is reversible")
            check(near(Tempo.beats_from_milliseconds(seconds*1000.0,rate),
                signed_beats),
                "backend millisecond epochs agree with seconds and source beats")
    check(Flow.MAX_SLOWDOWN_REPAY_FRACTION >= 0.0 and
        Flow.MAX_SLOWDOWN_REPAY_FRACTION < 1.0,
        "late slowdown debt repayment leaves strictly positive forward progress")

    var segments := [
        {"start_beat":0.0,"end_beat":2.0,"bpm":40.0},
        {"start_beat":2.0,"end_beat":4.0,"bpm":120.0},
        {"start_beat":4.0,"end_beat":6.0,"bpm":60.0},
    ]
    for beat in [0.0,0.5,1.75,2.0,2.5,3.9,4.0,5.5,6.0]:
        var seconds: float = Tempo.seconds_at_beat(beat,80.0,segments)
        check(near(Tempo.beat_at_seconds(seconds,80.0,segments),beat),
            "authored fast/slow tempo map round-trips exact source beats")
    print("TIMING_GEOMETRY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
