extends RefCounted
const InkSpacing := preload("res://notation/native/ink_spacing.gd")
## Choose one authentic staff scale and one density for the entire source.
## No canvas, clock or tempo ownership. The caller installs the returned density.
const MAX_STAFF_GAP := 22.0
const MIN_LOOKAHEAD_BEATS := 1.75
const MIN_READABLE_STAFF_GAP := 14.0

static func choose(score, ink_geometry, preferred: float, playhead_fraction: float) -> Dictionary:
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
