extends "res://notation/shared/view_base.gd"
# Diagnostic onset/duration visualization. Shared transport and timing are
# owned by view_base.gd and used independently by the native notation view.

func _draw() -> void:
    var w: float = size.x
    var h: float = size.y
    if w < 100.0 or h < 80.0:
        return
    draw_rect(Rect2(Vector2.ZERO, size), BACKGROUND)
    var font: Font = ThemeDB.fallback_font
    var playhead_x := w * PLAYHEAD_FRACTION
    var top := h * .32
    var bottom := h * .65
    var staff_gap: float = minf(13.0, h * .026)
    for hand_index in range(2):
        var center: float = top if hand_index == 0 else bottom
        var hand: String = "right" if hand_index == 0 else "left"
        var tint: Color = FOREGROUND if active_hand == hand or active_hand == "both" else MUTED
        for line_index in range(5):
            var rail_y := center + (float(line_index)-2.0)*staff_gap
            draw_line(Vector2(0, rail_y), Vector2(w, rail_y),
                Color(tint, .19), 1.0, true)
    if not timeline.has_score():
        draw_string(font, Vector2(18, h*.5), notice,
            HORIZONTAL_ALIGNMENT_LEFT, -1, 15, FOREGROUND)
        return
    var from: float = play_from_beat
    var camera_clock: float = clock_beat if running or paused else 0.0
    var left_edge: float = timeline.musical_beat(camera_clock, from) - \
        playhead_x / timeline.pixels_per_beat
    var right_edge: float = left_edge + w / timeline.pixels_per_beat
    # The empty count-in lies on the SAME quarter-beat axis as the real notes.
    # No separate bar-width formula, rescaling or note-derived interpolation.
    if count_in_beats > 0.0:
        var count_start: float = timeline.count_in_start(from, count_in_beats)
        for boundary in [count_start, from]:
            var x: float = timeline.screen_x(boundary, camera_clock,
                playhead_x, from)
            if x >= 0.0 and x <= w:
                draw_line(Vector2(x, top-staff_gap*2.5),
                    Vector2(x, bottom+staff_gap*2.5),
                    Color(GRID, .55), 1.5, true)
    # Measure ends originate only from semantic ScoreModel.
    for measure in timeline.measures:
        var beat: float = float(measure.get("start_beat", 0.0))
        if beat < left_edge - .05 or beat > right_edge + .05:
            continue
        var x: float = timeline.screen_x(beat, camera_clock,
            playhead_x, from)
        draw_line(Vector2(x, top-staff_gap*2.5),
            Vector2(x, bottom+staff_gap*2.5),
            Color(GRID, .35), 1.1, true)
        draw_string(font, Vector2(x+5.0, top-staff_gap*3.4),
            str(measure.get("number", 0)), HORIZONTAL_ALIGNMENT_LEFT,
            -1, 11, MUTED)
    visible_onsets = 0
    for note in timeline.notes:
        var onset: float = float(note.get("onset_beats", 0.0))
        var duration: float = float(note.get("duration_beats", 0.0))
        if onset > right_edge+.15 or onset+duration < left_edge-.15:
            continue
        var x: float = timeline.screen_x(onset, camera_clock,
            playhead_x, from)
        var lane: String = str(note.get("hand", "right"))
        var pitch: int = int(note.get("midi_pitch", 60))
        var y_center: float = top if lane == "right" else bottom
        # Deliberately NOT actual music engraving. A relative pitch marker
        # is enough to confirm timing, spacing and upcoming-note visibility.
        var y: float = y_center - clampf(float(pitch - (65 if lane == "right" else 48)),
            -12.0, 12.0) * (staff_gap*.48)
        var ink: Color = (HIGHLIGHT if lane == "right" else LEFT_TONE)
        if active_hand != "both" and lane != active_hand:
            ink.a = .35
        draw_rect(Rect2(x, y-2.0, maxf(2.0, duration * timeline.pixels_per_beat),
            4.0), Color(ink, .23))
        draw_circle(Vector2(x, y), 4.5, ink)
        visible_onsets += 1
    # The stationary playhead is one draw call, never moving with engraving.
    draw_line(Vector2(playhead_x, top-staff_gap*4.0),
        Vector2(playhead_x, bottom+staff_gap*3.5),
        HIGHLIGHT, 2.0, true)
    var stage: String = ("COUNT-IN" if camera_clock < 0.0 and running else
        "PAUSED" if paused else "PLAYING" if running else "READY")
    var speed: float = timeline.pixels_per_second(bpm)
    draw_string(font, Vector2(14.0, 24.0),
        "PHASE B · TIMELINE TEST   %s   %.0f BPM   %.0f px/beat" % [
            stage, bpm, timeline.pixels_per_beat],
        HORIZONTAL_ALIGNMENT_LEFT, -1, 13, FOREGROUND)
    draw_string(font, Vector2(14.0, h-13.0),
        "%.2f beat · %.1f px/s · %d visible attacks · markers only" % [
            timeline.musical_beat(camera_clock, from), speed, visible_onsets],
        HORIZONTAL_ALIGNMENT_LEFT, -1, 11, MUTED)
