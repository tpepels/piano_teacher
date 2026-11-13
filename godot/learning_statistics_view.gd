extends VBoxContainer
## Text report inside existing Settings conventions; no chart or new layout.
signal query_requested(scope: int, action: String)

var scope_picker: OptionButton
var refresh_button: Button
var previous_button: Button
var next_button: Button
var page_label: Label
var report_label: Label

func _ready() -> void:
    var controls := HFlowContainer.new()
    controls.add_theme_constant_override("h_separation", 8)
    add_child(controls)
    scope_picker = OptionButton.new()
    scope_picker.add_item("All history")
    scope_picker.add_item("Current piece")
    scope_picker.item_selected.connect(func(index: int): query_requested.emit(index, "refresh"))
    controls.add_child(scope_picker)
    refresh_button = _button(controls, "Refresh", "refresh")
    previous_button = _button(controls, "Previous", "previous")
    next_button = _button(controls, "Next", "next")
    page_label = Label.new()
    controls.add_child(page_label)
    report_label = Label.new()
    report_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    report_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(report_label)
    present_message("Refresh to read recorded practice. Each page includes up to 250 takes.")
    present_page(false, false, false, 1)

func _button(parent: Control, title: String, action: String) -> Button:
    var button := Button.new()
    button.text = title
    button.custom_minimum_size.y = 40
    button.pressed.connect(func(): query_requested.emit(scope_picker.selected, action))
    parent.add_child(button)
    return button

func present_message(message: String) -> void:
    report_label.text = message

func present_page(busy: bool, previous: bool, next: bool, page: int) -> void:
    refresh_button.disabled = busy
    previous_button.disabled = busy or not previous
    next_button.disabled = busy or not next
    page_label.text = "Page %d · selected window" % page

func _known(value: Variant, fallback: Variant) -> Variant:
    return fallback if value == null else value

func _value(value: Variant, suffix := "") -> String:
    return "unknown" if value == null else ("%.3f" % float(value)).trim_suffix("0").trim_suffix("0").trim_suffix(".") + suffix

func _fraction(numerator: Variant, denominator: Variant) -> String:
    var n := int(_known(numerator, 0))
    var d := int(_known(denominator, 0))
    return "%d / %d (%s)" % [n, d, "unknown" if d == 0 else "%.1f%%" % (100.0*n/d)]

func present_report(r: Dictionary) -> void:
    var count := int(r.get("attempts", {}).get("count", 0))
    if count == 0:
        present_message("No recorded takes in this window. Choose All history or practise a piece, then Refresh.")
        return
    var a: Dictionary = r.get("assessments", {})
    var p: Dictionary = r.get("pitch", {})
    var coverage: Dictionary = r.get("coverage", {})
    var lines: Array[String] = ["%d recorded takes · retained evidence in this page" % count,
        "Pitch: " + _fraction(p.get("correct_required_pitches"), p.get("assessed_obligations")),
        "Wrong pitches: %s · omissions: %s · extras: %s (each per observed obligation). Unknown obligations: %d." % [
            _fraction(p.get("wrong"), p.get("rate_denominator")), _fraction(p.get("omitted"), p.get("rate_denominator")),
            _fraction(p.get("extra"), p.get("extra_obligation_denominator")), int(p.get("unknown_obligations", 0))],
        "Accepted: %s · strict clean: %s · mastery eligible: %d." % [
            _fraction(a.get("accepted"), a.get("acceptance_rate_denominator")),
            _fraction(a.get("strict_clean"), int(a.get("assessed", 0))-int(a.get("clean_unknown", 0))), int(a.get("mastery_eligible", 0))]]
    lines.append("Unassessed takes: %d; unobserved suffix obligations: %s. Extra-note denominators include retained assessed summaries." % [int(p.get("unassessed_attempts", 0)), _value(p.get("unobserved_suffix_obligations"))])
    for s in r.get("assessment_strata", []).slice(0, 8):
        lines.append("%s · %s · %s BPM · assistance %s · eligible %s: accepted %s; clean %s." % [
            str(_known(s.get("scope"), "unknown")), str(_known(s.get("hand"), "unknown")), _value(s.get("performed_bpm")),
            str(s.get("assistance") if s.get("assistance") != null else "unknown"),
            str(_known(s.get("recorded_mastery_eligible"), "unknown")),
            _fraction(s.get("accepted"), s.get("accepted_denominator")), _fraction(s.get("strict_clean"), s.get("clean_denominator"))])
    for name in ["onset", "release", "duration"]:
        var t: Dictionary = r.get("timing", {}).get(name, {})
        lines.append("%s residuals: n=%d · bias %ss · spread %ss · p05 / median / p95 %s / %s / %ss." % [
            name.capitalize(), int(t.get("sample_count", 0)), _value(t.get("mean_seconds")), _value(t.get("population_std_seconds")),
            _value(t.get("quantiles_seconds", {}).get("p05")), _value(t.get("quantiles_seconds", {}).get("p50")),
            _value(t.get("quantiles_seconds", {}).get("p95"))])
    for t in r.get("timing", {}).get("contexts", []).slice(0, 4):
        lines.append("Timing context: performed %s BPM / local %s BPM · %s · %s · calibration %s ms; onset missing %d / %d." % [
            _value(t.get("performed_bpm")), _value(t.get("local_bpm")), str(_known(t.get("hand"), "unknown")), str(_known(t.get("scope"), "unknown")),
            _value(t.get("calibration_ms")), int(t.get("onset", {}).get("missing_observations", 0)), int(t.get("observations", 0))])
    var durations: Dictionary = r.get("durations", {})
    lines.append("Measured active practice: %ss. Attempt elapsed: %ss (includes pauses)." % [
        _value(durations.get("active_practice_seconds")), _value(durations.get("measured_attempt_seconds"))])
    var phases: Dictionary = _known(durations.get("attributed_phase_seconds"), {})
    var phase_text: Array[String] = []
    for phase in ["guided", "count_in", "feedback", "preparation", "pause"]:
        phase_text.append("%s %ss" % [phase.replace("_", " "), _value(phases.get(phase))])
    lines.append("Recorded phases: " + "; ".join(phase_text) + ". Unflushed or missing intervals remain unknown.")
    lines.append("Phase evidence: %d takes with recorded intervals, %d without, %d with incomplete interval coverage." % [
        int(durations.get("phase_attributed_attempts", 0)), int(durations.get("phase_unknown_attempts", 0)),
        int(durations.get("attempts_with_incomplete_phase_coverage", 0))])
    var tempo: Dictionary = r.get("tempo", {})
    lines.append("Exact-context repetitions: %d · aborted %d · explicit retries %d · recorded tempo changes %d." % [
        int(r.get("attempts", {}).get("repetitions", 0)), int(tempo.get("aborts", 0)), int(tempo.get("retries", 0)), int(tempo.get("recorded_changes", 0))])
    var journey: Array[String] = []
    for step in tempo.get("trajectory", []).slice(0, 12):
        journey.append("%s BPM (%s, %s)" % [_value(step.get("performed_bpm")), str(_known(step.get("hand"), "unknown")), str(_known(step.get("scope"), "unknown"))])
    lines.append("Recorded tempo sequence: " + " → ".join(journey))
    var mastery: Dictionary = r.get("mastery", {})
    lines.append("Mastery: %d unfinished/censored episodes. Imported or earlier-page gaps prevent time-to-mastery estimates." % int(mastery.get("censored_episodes", 0)))
    for episode in mastery.get("episodes", []).slice(0, 4):
        lines.append("Target %s BPM: %d observed takes, %d accepted eligible; attempts to recorded mastery %s, active seconds %s." % [
            _value(episode.get("target_bpm")), int(episode.get("attempts_observed", 0)), int(episode.get("accepted_eligible_attempts", 0)),
            _value(episode.get("attempts_to_mastery")), _value(episode.get("active_seconds_to_mastery"))])
    var errors: Dictionary = r.get("errors", {})
    for e in errors.get("source_notes", []).slice(0, 8):
        lines.append("Source note %s · measure %s · beat %s · %s · %s BPM · stage %s: wrong %s, missed %d / %d note obligations." % [
            str(_known(e.get("source_id"), "unknown")), str(_known(e.get("source_measure"), "unknown")), _value(e.get("source_beat")),
            str(_known(e.get("authored_hand"), "unknown")), _value(e.get("performed_bpm")),
            str(_known(e.get("stage_key"), "unknown")),
            _fraction(e.get("pitch_errors"), e.get("assessed_pitch_exposures")), int(e.get("omissions", 0)), int(e.get("exposures", 0))])
    for dimension in ["onsets", "measures"]:
        for e in errors.get(dimension, []).slice(0, 4):
            lines.append("%s %s · %s BPM · %s: status errors %s note obligations." % [dimension.capitalize(),
                str(_known(e.get("onset_group_id") if dimension == "onsets" else e.get("source_measure"), "unknown")),
                _value(e.get("performed_bpm")), str(_known(e.get("hand"), "unknown")),
                _fraction(e.get("status_errors"), e.get("status_denominator"))])
    var interventions: Dictionary = r.get("interventions", {})
    lines.append("Interventions: compatible accepted %s; incompatible %d, unknown %d, censored %d." % [
        _fraction(interventions.get("compatible_accepted_outcomes"), interventions.get("compatible_assessed_outcomes")),
        int(interventions.get("incompatible_outcomes", 0)), int(interventions.get("unknown_outcomes", 0)), int(interventions.get("censored_outcomes", 0))])
    for policy in r.get("fixed_policy_comparison", {}).get("policies", []):
        lines.append("Policy %s: %d recorded decisions, %d exact-context cohorts." % [str(policy.get("policy_id", "unknown")), int(policy.get("decisions", 0)), policy.get("cohorts", []).size()])
        for cohort in policy.get("cohorts", []).slice(0, 3):
            lines.append("  %s BPM · %s · %s: comparable proximal %s; unsupported target verification %s; comparable verification %s; observed active burden %ss." % [
                _value(cohort.get("performed_bpm")), str(_known(cohort.get("hand"), "unknown")), str(_known(cohort.get("scope"), "unknown")),
                _fraction(cohort.get("proximal", {}).get("accepted"), cohort.get("proximal", {}).get("assessed_denominator")),
                _fraction(cohort.get("episode_verification", {}).get("unsupported_full_target_accepted"), cohort.get("episode_verification", {}).get("unsupported_full_target_assessed_denominator")),
                _fraction(cohort.get("episode_verification", {}).get("accepted"), cohort.get("episode_verification", {}).get("assessed_denominator")),
                _value(cohort.get("active_seconds_observed"))])
    lines.append("Coverage: %d pruned takes · %d legacy · %d crash suffixes · %d detail-budget omissions. More pages: %s." % [
        int(coverage.get("pruned_attempts", 0)), int(coverage.get("legacy_bounded_attempts", 0)), int(coverage.get("unknown_crash_suffix_attempts", 0)),
        int(coverage.get("detail_budget_truncated_attempts", 0)), str(r.get("query", {}).get("has_more", false))])
    lines.append("Read bounds: %d detail bytes / %d; %d / %d observations, %d truncated. Related omissions (at least): %s. Location obligations omitted by caps: %s; timing context omissions: %d." % [
        int(coverage.get("detail_bytes_read", 0)), int(r.get("query", {}).get("detail_budget_bytes", 0)),
        int(coverage.get("observation_count", 0)), int(coverage.get("observation_limit", 0)), int(coverage.get("truncated_observations", 0)),
        str(coverage.get("related_truncation", {})), str(errors.get("omitted_location_obligations", {})),
        int(r.get("timing", {}).get("context_truncated_observations", 0))])
    lines.append("Lists show up to 8 contexts/notes, 4 timing/mastery contexts, 12 tempo steps and 3 cohorts per policy in this view. Detail and related-row caps are reported by the typed query. Retained evidence is not lifetime history. Expertise and earlier exposure may be unknown; selection bias remains. Slower/shorter/assisted success is incomparable. No causal or learning-effect estimate.")
    report_label.text = "\n\n".join(lines)
