extends RefCounted
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
const Admission := preload("res://score_stream_admission.gd")
const StreamQueue := preload("res://score_stream_queue.gd")
## Choose one authentic staff scale and one density for the entire source.
## No canvas, clock or tempo ownership. The caller installs the returned density.
const MAX_STAFF_GAP := 22.0
const MIN_LOOKAHEAD_BEATS := 3.0
const MIN_READABLE_STAFF_GAP := 14.0
# Target below the 2.25-bar physical ceiling: allow for a delayed
# announcement and for a subsequent tempo step faster than this take.
const AUTOMATIC_REST_TARGET_BARS := 1.85

static func automatic_rest_density_floor(rest_beats: float,
        header_spaces: float, staff_gap: float) -> float:
    # Printed rest -> entire authentic initial header -> graded first beat.
    # The full rest occupies rest_beats; the new header and two short raster
    # margins occupy the remainder. A single higher horizontal density
    # shortens this *printed geometry* in beats without retiming source notes.
    if rest_beats <= 0.0 or header_spaces <= 0.0 or staff_gap <= 0.0:
        return 0.0
    var available: float = rest_beats*(AUTOMATIC_REST_TARGET_BARS-1.0) - \
        2.0*Admission.OFFSCREEN_MARGIN_BEATS
    if available <= 0.0:
        return INF
    # Also force the source's last physical stroke inside the full rest:
    # otherwise the 60px source-clearance path is necessarily longer.
    return maxf(2.2*staff_gap/rest_beats,
        (header_spaces*staff_gap+StreamQueue.PEER_REST_MARGIN_PX)/available)

static func choose(score, ink_geometry, preferred: float, playhead_fraction: float,
        opening_header_spaces: float = 0.0) -> Dictionary:
    # Maintain at least 36px between repeated quick attacks. The existing
    # authentic-ink collision solver may raise this floor as necessary.
    var density: float = InkSpacing.readable_density(
        score.timeline.model.get("notes", []), preferred)
    var ink_density: float = density
    var staff_gap_limit: float = MAX_STAFF_GAP
    var selected_density_witness: Dictionary = {}
    var last_witness: Dictionary = {}
    var fits_density := false
    # The hidden Practice canvas is sometimes loaded before Godot assigns
    # its first Control width. A zero-width value must not force every
    # passage through five extremely expensive candidate engravings.
    # Use the standard desktop viewport for that brief pre-layout state.
    var viewport_width: float = score.size.x if score.size.x >= 640.0 else 1536.0
    var max_usable_density: float = (
        viewport_width*(1.0-playhead_fraction)/MIN_LOOKAHEAD_BEATS)
    var rest_beats: float = float(score.timeline.model.get(
        "practice_timeline",{}).get("gap",{}).get("duration_beats",0.0))
    var fallbacks: Array = []
    for candidate_gap in [MAX_STAFF_GAP,17.0,14.0,11.0,8.5]:
        var tested_gap: float = float(candidate_gap)
        score.layout_rest_lanes(tested_gap,density)
        var first: Dictionary = ink_geometry.minimum_density(density,tested_gap)
        var trial: float = first["density"]
        var first_witness: Dictionary = first["witness"].duplicate(true)
        score.layout_rest_lanes(tested_gap,trial)
        var second: Dictionary = ink_geometry.minimum_density(trial,tested_gap)
        var second_trial: float = second["density"]
        var second_witness: Dictionary = second["witness"].duplicate(true)
        last_witness = second_witness
        var final_witness: Dictionary = second_witness if second_trial > trial else first_witness
        trial = maxf(trial,second_trial)
        var repeat_floor: float = automatic_rest_density_floor(
            rest_beats,opening_header_spaces,tested_gap)
        if repeat_floor > trial:
            trial = repeat_floor
            final_witness = {"reason":"automatic-rest-header-clearance",
                "required_density":repeat_floor,"staff_gap":tested_gap,
                "rest_beats":rest_beats,
                "header_spaces":opening_header_spaces,
                "target_rest_bars":AUTOMATIC_REST_TARGET_BARS}
        if not is_finite(trial) or trial > score.timeline.MAX_SCORE_PIXELS_PER_BEAT:
            continue
        var fit_option: Dictionary = {
            "gap":tested_gap, "density":trial, "witness":final_witness}
        fallbacks.append(fit_option)
        if tested_gap >= MIN_READABLE_STAFF_GAP and trial > max_usable_density:
            continue
        staff_gap_limit = tested_gap
        ink_density = trial
        selected_density_witness = final_witness.duplicate(true)
        fits_density = true
        break
    if not fits_density and not fallbacks.is_empty():
        # An exceptionally dense score may not permit the target lookahead
        # at a legible staff size. Prefer the smallest scale still >=14px.
        # Never select an arbitrary sub-legible size solely to pass a metric.
        var alternate: Dictionary = fallbacks[-1]
        for option in fallbacks:
            if float(option["gap"]) >= MIN_READABLE_STAFF_GAP:
                alternate = option
        staff_gap_limit = float(alternate["gap"])
        ink_density = float(alternate["density"])
        selected_density_witness = alternate["witness"].duplicate(true)
        fits_density = true
    if fits_density:
        selected_density_witness["staff_gap"] = staff_gap_limit
        selected_density_witness["selected_density"] = ink_density
        selected_density_witness["available_lookahead_beats"] = (
            score.size.x*(1.0-playhead_fraction)/ink_density)
        # The accepted scale can be different from the last trial; use the
        # corresponding rest lanes instead of stale rejected-candidate lanes.
        score.layout_rest_lanes(staff_gap_limit,ink_density)
    return {"ok":fits_density,"density":ink_density,"staff_gap":staff_gap_limit,
        "witness":selected_density_witness,"last_witness":last_witness,
        "error":"" if fits_density else "Source glyph ink cannot fit within the fixed musical timeline"}
