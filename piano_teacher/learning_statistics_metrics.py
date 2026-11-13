"""Pure descriptive projections of bounded, original ledger facts."""
from collections import Counter, defaultdict
from bisect import bisect_left, bisect_right
from hashlib import sha256
from datetime import datetime
import json

from .learning_statistics import _number, _Residual, _compatibility, _performed_context


def obj(value):
    return json.loads(value) if value else {}


CONTEXT = ("fingerprint", "stage_key", "hand", "performed_bpm", "scope", "from_beat", "end_beat",
           "assistance", "rule_id", "tempo_map_hash", "calibration_ms", "midi_available", "target_bpm", "mode")


def context(row):
    c = obj(row["summary_json"])
    c = _performed_context(c, c.get("terminal") or {})
    return {k: c.get(k, row.get(k)) for k in CONTEXT}


def key(c):
    return json.dumps(c, sort_keys=True, separators=(",", ":"))


def rate(n, d):
    return n/d if d else None


def phase_intervals(snapshot):
    """Union once per session/phase; indexed intersections avoid attempts×events scans."""
    grouped = defaultdict(lambda: defaultdict(list))
    runs = {s["session_id"]: s["run_id"] for s in snapshot["sessions"]}
    missing = truncated = retained = 0
    phases = set()
    for event in snapshot["events"]:
        if event["kind"] != "phase_intervals":
            continue
        data = obj(event["data_json"])
        intervals = data.get("intervals")
        if not isinstance(intervals, list) or data.get("run_id", runs.get(event["session_id"])) != runs.get(event["session_id"]):
            missing += 1
            continue
        for interval in intervals:
            if not (isinstance(interval, dict) and _number(interval.get("start")) and _number(interval.get("end"))
                    and 0 <= interval["start"] <= interval["end"] and isinstance(interval.get("phase"), str)):
                missing += 1
                continue
            phase = interval["phase"]
            if retained >= 20000 or phase not in phases and len(phases) >= 64:
                truncated += 1
                continue
            phases.add(phase)
            retained += 1
            grouped[event["session_id"]][phase].append((interval["start"], interval["end"]))
    result = {}
    for session, groups in grouped.items():
        result[session] = {}
        for phase, pairs in groups.items():
            merged = []
            for lo, hi in sorted(pairs):
                if merged and lo <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
                else:
                    merged.append((lo, hi))
            result[session][phase] = (merged, [p[0] for p in merged], [p[1] for p in merged])
    return result, missing, truncated


def extend_report(report, snapshot):
    attempts = snapshot["attempts"]
    by_id = {a["attempt_id"]: a for a in attempts}
    pitch = Counter(correct_required_pitches=0, assessed_obligations=0, wrong=0, omitted=0,
                    extra=0, extra_obligation_denominator=0, unknown_obligations=0, censored_attempts=0, unassessed_attempts=0)
    strata, residual_contexts = {}, {}
    error_groups = {kind: {} for kind in ("source_notes", "onsets", "measures", "contexts")}
    error_group_truncation = Counter()
    timing_context_truncation = 0
    trajectory = []
    phase_index, phase_missing, phase_truncated = phase_intervals(snapshot)
    session_runs = {s["session_id"]: s["run_id"] for s in snapshot["sessions"]}
    attributed = Counter()
    phase_attempts = 0
    incomplete_phase_attempts = 0
    attempt_active = {}
    for a in attempts:
        c, summary = context(a), obj(a["summary_json"])
        terminal = summary.get("terminal") or {}
        c["assistance"] = terminal.get("assistance_used", c["assistance"])
        c["recorded_mastery_eligible"] = None if a["assessment_json"] is None else bool(a["mastery_eligible"])
        k = key(c)
        s = strata.setdefault(k, {**c, "attempts": 0, "accepted": 0, "accepted_denominator": 0,
                                  "strict_clean": 0, "clean_denominator": 0, "mastery_eligible": 0})
        s["attempts"] += 1
        if a["passed"] is not None:
            s["accepted_denominator"] += 1
            s["accepted"] += a["passed"] == 1
        if a["clean"] is not None:
            s["clean_denominator"] += 1
            s["strict_clean"] += a["clean"] == 1
        s["mastery_eligible"] += a["mastery_eligible"] == 1
        trajectory.append({**c, "attempt_id": a["attempt_id"], "sequence": a["sequence"],
                           "started_utc": summary.get("started_utc"), "state": a["state"],
                           "reason": a["reason"], "accepted": None if a["passed"] is None else bool(a["passed"])})
        start, end = summary.get("monotonic_start"), terminal.get("monotonic_end")
        ranges = {}
        if (_number(start) and _number(end) and 0 <= start <= end
                and summary.get("run_id", session_runs.get(a["session_id"])) == session_runs.get(a["session_id"])):
            for phase, (pairs, starts, ends) in phase_index.get(a["session_id"], {}).items():
                lo, hi = bisect_right(ends, start), bisect_left(starts, end)
                if hi > lo:
                    ranges[phase] = [(max(start, left), min(end, right)) for left, right in pairs[lo:hi]]
        if ranges:
            active = 0
            covered = []
            for phase, pairs in ranges.items():
                merged = []
                for lo, hi in sorted(pairs):
                    if merged and lo <= merged[-1][1]:
                        merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
                    else:
                        merged.append((lo, hi))
                seconds = sum(hi-lo for lo, hi in merged)
                covered.extend(merged)
                attributed[phase] += seconds
                if phase in ("practice", "active"):
                    active += seconds
            union = []
            for lo, hi in sorted(covered):
                if union and lo <= union[-1][1]:
                    union[-1] = (union[-1][0], max(hi, union[-1][1]))
                else:
                    union.append((lo, hi))
            complete_phases = abs(sum(hi-lo for lo, hi in union)-(end-start)) < 1e-6
            incomplete_phase_attempts += not complete_phases
            if complete_phases:
                attempt_active[a["attempt_id"]] = active
            phase_attempts += 1
        assessment = obj(a["assessment_json"])
        count = assessment.get("note_count", 0)
        pitch["extra"] += a["extra_notes"] or 0
        if a["extra_notes"] is not None:
            pitch["extra_obligation_denominator"] += count
        pitch["censored_attempts"] += a["state"] != "completed"
        pitch["unassessed_attempts"] += a["assessment_json"] is None
        observations = json.loads(a["observations_json"] or "[]")
        known = 0
        for o in observations:
            local_spb = o.get("local_seconds_per_beat")
            local = {**c, "local_seconds_per_beat": local_spb if _number(local_spb) and local_spb > 0 else None,
                     "local_bpm": 60/local_spb if _number(local_spb) and local_spb > 0 else None}
            local_key = key(local)
            if local_key in residual_contexts or len(residual_contexts) < 250:
                residual = residual_contexts.setdefault(local_key, {"context": local,
                    **{name: _Residual() for name in ("onset", "release", "duration")}, "observations": 0})
                residual["observations"] += 1
                for name in ("onset", "release", "duration"):
                    residual[name].add(o.get(name+"_residual"))
            else:
                timing_context_truncation += 1
            omission = o.get("omitted") is True
            observed = omission or (o.get("pitch_error") in (True, False) and type(o.get("pitch_error")) is bool)
            correct = observed and not omission and o.get("pitch_error") is False
            wrong = observed and not omission and o.get("pitch_error") is True
            if observed:
                known += 1
                pitch["assessed_obligations"] += 1
                pitch["correct_required_pitches"] += correct
                pitch["wrong"] += wrong
                pitch["omitted"] += omission
            for kind, dimensions in (
                    ("source_notes", ("source_id",)), ("onsets", ("onset_group_id", "source_beat")),
                    ("measures", ("source_measure",)), ("contexts", ())):
                location = {d: o.get(d) for d in dimensions}
                if kind == "source_notes":
                    location.update({d: o.get(d) for d in ("onset_group_id", "source_beat", "source_measure")})
                location["authored_hand"] = o.get("authored_hand")
                identity = {**c, **location}
                identity_key = key(identity)
                if identity_key not in error_groups[kind] and len(error_groups[kind]) >= 1000:
                    error_group_truncation[kind] += 1
                    continue
                e = error_groups[kind].setdefault(identity_key, {**identity, "exposures": 0,
                    "exposure_unit": "required_note_obligations_at_location",
                    "assessed_pitch_exposures": 0, "pitch_errors": 0, "omissions": 0,
                    "status_errors": 0, "status_denominator": 0, "unknown_pitch": 0})
                e["exposures"] += 1
                e["assessed_pitch_exposures"] += observed
                e["pitch_errors"] += wrong
                e["omissions"] += omission
                e["unknown_pitch"] += not observed
                if o.get("status") is not None:
                    e["status_denominator"] += 1
                    e["status_errors"] += o["status"] != "correct"
        pitch["unknown_obligations"] += max(0, count-known)
    pitch = dict(pitch)
    for label, numerator in (("accuracy", "correct_required_pitches"), ("wrong_rate", "wrong"), ("omission_rate", "omitted"), ("extra_rate", "extra")):
        pitch[label] = rate(pitch[numerator], pitch["extra_obligation_denominator"] if label == "extra_rate" else pitch["assessed_obligations"])
    pitch["rate_denominator"] = pitch["assessed_obligations"]
    pitch["unobserved_suffix_obligations"] = None if pitch["censored_attempts"] or pitch["unassessed_attempts"] else 0
    pitch["definition"] = "Original independent pitch assignments / observed required obligations; unknown and censored suffix targets are excluded. Extras / assessed obligations with a recorded extra count (compact summaries survive pruning)."
    report["pitch"] = pitch
    report["assessment_strata"] = [{**s, "accepted_rate": rate(s["accepted"], s["accepted_denominator"]),
        "clean_rate": rate(s["strict_clean"], s["clean_denominator"])} for s in strata.values()]
    report["timing"]["contexts"] = [{**r["context"], "observations": r["observations"],
        **{name: {**r[name].result(), "missing_observations": r["observations"]-r[name].count}
           for name in ("onset", "release", "duration")}} for r in residual_contexts.values()]
    report["timing"]["quantile_method"] = "Exact linear interpolation on bounded retained samples (p*(n-1)); no imputation."
    report["timing"].update(attempts_without_retained_detail=sum(not a["detail_present"] for a in attempts),
                            obligations_without_pitch_detail=pitch["unknown_obligations"],
                            context_row_limit=250, context_truncated_observations=timing_context_truncation)
    report["errors"] = {kind: [{**e, "pitch_error_rate": rate(e["pitch_errors"], e["assessed_pitch_exposures"]),
        "status_error_rate": rate(e["status_errors"], e["status_denominator"])} for e in groups.values()] for kind, groups in error_groups.items()}
    report["errors"]["detail_missing_attempts"] = sum(not a["detail_present"] for a in attempts)
    report["errors"].update(location_row_limit=1000, omitted_location_obligations=dict(error_group_truncation))
    def chronological(step):
        try:
            stamp = datetime.fromisoformat(step["started_utc"].replace("Z", "+00:00"))
            if stamp.tzinfo is not None:
                return (0, stamp.timestamp(), step["sequence"])
        except (TypeError, ValueError, AttributeError):
            pass
        return (1, 0, step["sequence"])
    trajectory.sort(key=chronological)
    report["tempo"].update(trajectory=trajectory, trajectory_order="Captured UTC chronology within selected page; unknown dates follow in insertion order.",
        aborts=sum(a["state"] == "aborted" for a in attempts), interruptions=sum(a["state"] in ("interrupted", "process_interrupted") for a in attempts),
        retries=sum(a["reason"] in ("retry", "restart") or obj(a["summary_json"]).get("parent_decision_id") is not None for a in attempts),
        retry_definition="Distinct attempts linked to a recorded prior decision, plus explicit manual retry/restart terminals.",
        change_events=[{"attempt_id": e["attempt_id"], "kind": e["kind"],
                        **{k: v for k, v in obj(e["summary_json"]).items() if k in (
                            "before_bpm", "after_bpm", "before_stage", "after_stage", "action", "origin", "utc")}}
                       for e in snapshot["events"] if e["kind"] in ("manual_action", "progression", "tempo_change")])
    report["durations"].update(attributed_phase_seconds=dict(sorted(attributed.items())) if phase_attempts else None,
        active_practice_seconds=attributed["practice"]+attributed["active"] if phase_attempts else None,
        phase_attributed_attempts=phase_attempts, phase_unknown_attempts=len(attempts)-phase_attempts,
        phase_detail_missing_events=phase_missing, phase_interval_limit=20000,
        phase_name_limit=64, truncated_phase_intervals=phase_truncated,
        attempts_with_incomplete_phase_coverage=incomplete_phase_attempts,
        attribution_definition="Unioned recorded per-session monotonic phase intervals intersected with recorded attempt bounds. Unflushed/legacy/pruned phases remain unknown; elapsed time is not active time.")
    report["query"] = snapshot["query"]
    report["coverage"].update(snapshot["resource"], window_only=True,
        selected_attempts=len(attempts), has_more_attempts=snapshot["query"]["has_more"])
    if (snapshot["resource"]["detail_budget_truncated_attempts"] or snapshot["resource"]["truncated_observations"]
            or any(snapshot["resource"]["related_truncation"].values())):
        report["coverage"]["detail_history_complete"] = False
    report["mastery"] = mastery_episodes(snapshot, attempt_active)
    report["fixed_policy_comparison"] = policy_comparison(snapshot, by_id, attempt_active)
    if (phase_truncated or error_group_truncation or timing_context_truncation
            or report["fixed_policy_comparison"]["excluded"].get("cohort_row_limit")):
        report["coverage"]["detail_history_complete"] = False
    return report


def mastery_episodes(snapshot, active):
    transitions = {e["attempt_id"]: obj(e["summary_json"]) for e in snapshot["events"]
                   if e["kind"] == "progression"}
    groups = {}
    filter_censored = any(k in snapshot["query"] for k in ("date_from", "date_to", "bpm_min", "bpm_max", "scope", "policy"))
    for a in snapshot["attempts"]:
        c = context(a)
        episode_context = {k: c[k] for k in ("fingerprint", "stage_key", "hand", "target_bpm", "rule_id")}
        episode_context["session_id"] = a["session_id"]
        k = key(episode_context)
        rules = obj(snapshot["rules"].get(a["rule_id"]))
        criterion = rules.get("mastery")
        target_known = c["target_bpm"] is not None
        g = groups.setdefault(k, {**episode_context, "criterion": criterion,
            "required_accepted_runs": (rules.get("lesson_settings") or {}).get("clean_runs_to_master"),
            "attempts_observed": 0, "eligible_attempts": 0, "accepted_eligible_attempts": 0,
            "accepted_eligible_target_attempts": 0,
            "active_seconds_observed": 0, "unknown_phase_attempts": 0, "mastered": False,
            "historical_gap_unknown": a["provenance"] != "native" or not target_known,
            "left_censored": a.get("has_prior_episode_attempts", False),
            "initial_progress_unknown": a.get("has_prior_episode_attempts", False), "mastery_attempt_id": None})
        if g["mastered"]:
            continue
        g["attempts_observed"] += 1
        g["eligible_attempts"] += a["mastery_eligible"] == 1
        g["accepted_eligible_attempts"] += a["mastery_eligible"] == 1 and a["passed"] == 1
        g["accepted_eligible_target_attempts"] += (a["mastery_eligible"] == 1 and a["passed"] == 1
            and c["target_bpm"] is not None and c["performed_bpm"] == c["target_bpm"]
            and c["scope"] == "full" and c["assistance"] is False)
        g["active_seconds_observed"] += active.get(a["attempt_id"], 0)
        g["unknown_phase_attempts"] += a["attempt_id"] not in active
        event = transitions.get(a["attempt_id"], {})
        # Read the captured award; never recreate mastery from three passes.
        if event.get("mastery_transition") is True and a["mastery_eligible"] == 1 and a["passed"] == 1:
            g["mastered"] = True
            g["mastery_attempt_id"] = a["attempt_id"]
    episodes = []
    for g in groups.values():
        g["filter_censored"] = filter_censored
        required = g["required_accepted_runs"]
        g["criterion_evidence_complete"] = (type(required) is int and required > 0
            and g["accepted_eligible_target_attempts"] >= required)
        if g["mastered"] and not g["criterion_evidence_complete"]:
            # The award remains authoritative. It does not prove that this
            # session contains all attempts/time that earned a restored streak.
            g["left_censored"] = g["initial_progress_unknown"] = True
        complete = g["mastered"] and not g["left_censored"] and not g["historical_gap_unknown"] and not filter_censored
        g.update(censored=not g["mastered"], attempts_to_mastery=g["attempts_observed"] if complete else None,
            active_seconds_to_mastery=g["active_seconds_observed"] if complete and not g["unknown_phase_attempts"] else None)
        episodes.append(g)
    return dict(episodes=episodes, censored_episodes=sum(e["censored"] for e in episodes),
                definition="Recorded eligibility/rule/target and progression awards only. Unfinished episodes are right censored; prior-session/page/imported or unproved initial progress precludes complete attempts/time-to-mastery estimates.")


def policy_comparison(snapshot, by_id, active):
    # Stored policy identity/parameters remain historical facts. Current policy
    # defaults are never substituted for missing captured resolved parameters.
    baselines = ("adaptive", "steady-repeat", "slow-practice", "micro-loop", "guided-repair", "finish-then-review")
    policies = {name: {"policy_id": name, "decisions": 0, "cohorts": []} for name in baselines}
    cohorts = {}
    comparison_groups = {}
    excluded = Counter()
    outcomes = defaultdict(list)
    for o in snapshot["outcomes"]:
        outcomes[o["decision_id"]].append(o)
    for d in snapshot["decisions"]:
        facts = obj(d["data_json"] or d["summary_json"])
        policy = facts.get("policy")
        if policy not in policies:
            excluded["unknown_policy"] += 1
            continue
        policies[policy]["decisions"] += 1
        before = by_id.get(d["attempt_id"])
        if before is None:
            excluded["missing_exposure"] += 1
            continue
        c = context(before)
        c["assistance"] = (obj(before["summary_json"]).get("terminal") or {}).get("assistance_used", c["assistance"])
        rules = obj(snapshot["rules"].get(before["rule_id"]))
        resolved = facts.get("parameters")
        if not isinstance(resolved, dict) and isinstance(rules.get("retry"), dict) and rules["retry"].get("policy_id") == policy:
            resolved = rules["retry"]
        c.update(expertise=None, exposure="selected_retained_window", policy_parameters=resolved,
                 expertise_missingness="not_captured", prior_exposure_missingness="precollection_or_pruned_history_unknown")
        # The canonical rule hash also freezes intervention configuration.
        # Remove exactly those intervention fields for a cross-policy grading
        # context identity; preserve every actual grading/generator/support fact.
        grading = {k: v for k, v in rules.items() if k not in ("retry", "retry_version")}
        valid_grading = (rules.get("schema_version") == 1 and isinstance(rules.get("grader"), str)
                         and isinstance(rules.get("lesson_settings"), dict) and isinstance(rules.get("mastery"), str))
        c["grading_context_id"] = sha256(key(grading).encode()).hexdigest() if valid_grading else None
        required = ("fingerprint", "stage_key", "hand", "performed_bpm", "scope", "from_beat", "end_beat", "assistance", "rule_id")
        if any(c[k] is None for k in required) or not isinstance(resolved, dict):
            excluded["unknown_context_or_parameters"] += 1
            continue
        cohort_key = (policy, key(c))
        if cohort_key not in cohorts and len(cohorts) >= 250:
            excluded["cohort_row_limit"] += 1
            continue
        g = cohorts.setdefault(cohort_key, {**c, "policy_id": policy, "decisions": 0,
            "proximal": Counter(), "episode_verification": Counter(), "active_seconds_observed": 0,
            "burden_attempts_with_phase": 0, "burden_attempts_unknown_phase": 0})
        g["decisions"] += 1
        g["active_seconds_observed"] += active.get(d["attempt_id"], 0)
        g["burden_attempts_with_phase"] += d["attempt_id"] in active
        g["burden_attempts_unknown_phase"] += d["attempt_id"] not in active
        for outcome in outcomes[d["decision_id"]]:
            data = obj(outcome["summary_json"])
            kind = data.get("kind")
            if kind not in ("proximal", "episode_verification"):
                excluded["unknown_outcome_kind"] += 1
                continue
            bucket = g[kind]
            bucket["linked_outcomes"] += 1
            if data.get("state") == "censored":
                bucket["censored"] += 1
                continue
            after = by_id.get(outcome["attempt_id"])
            def adapter(a):
                return None if a is None else {"context": obj(a["summary_json"]), "terminal": obj(a["summary_json"]).get("terminal") or {}}
            compatible = _compatibility(adapter(before), adapter(after))
            if compatible == "compatible" and any(
                    context(a).get(field) is None for a in (before, after)
                    for field in ("tempo_map_hash", "calibration_ms", "midi_available")):
                compatible = "unknown"
            if kind == "episode_verification" and after is not None:
                ac = context(after)
                if ac["scope"] != "full" or ac["assistance"] is not False:
                    compatible = "incompatible"
                if (after["state"] == "completed" and ac["scope"] == "full" and ac["assistance"] is False
                        and ac["target_bpm"] is not None and ac["performed_bpm"] == ac["target_bpm"]
                        and after["mastery_eligible"] == 1 and after["passed"] is not None):
                    bucket["unsupported_full_target_assessed_denominator"] += 1
                    bucket["unsupported_full_target_accepted"] += after["passed"] == 1
            bucket[compatible] += 1
            if compatible == "compatible" and after["state"] == "completed" and after["passed"] is not None:
                bucket["assessed_denominator"] += 1
                bucket["accepted"] += after["passed"] == 1
    for g in cohorts.values():
        if not g["burden_attempts_with_phase"]:
            g["active_seconds_observed"] = None
        for kind in ("proximal", "episode_verification"):
            counts = g[kind]
            g[kind] = {**counts, "accepted_rate": rate(counts["accepted"], counts["assessed_denominator"]),
                       "assessed_denominator": counts["assessed_denominator"],
                       "unsupported_full_target_accepted_rate": rate(counts["unsupported_full_target_accepted"], counts["unsupported_full_target_assessed_denominator"])}
        policies[g["policy_id"]]["cohorts"].append(g)
        if g["grading_context_id"] is None:
            excluded["unknown_grading_context_for_cross_policy_group"] += g["decisions"]
            continue
        dimensions = {k: v for k, v in g.items() if k in CONTEXT and k != "rule_id"}
        dimensions.update(grading_context_id=g["grading_context_id"], expertise=g["expertise"], exposure=g["exposure"])
        group = comparison_groups.setdefault(key(dimensions), {**dimensions, "arms": [],
            "comparability": "source_tempo_support_grading_matched; expertise_and_prior_exposure_unknown",
            "expertise_matched": None, "prior_exposure_matched": None})
        group["arms"].append({"policy_id": g["policy_id"], "rule_id": g["rule_id"],
            "policy_parameters": g["policy_parameters"], "decisions": g["decisions"],
            "proximal": g["proximal"], "episode_verification": g["episode_verification"],
            "active_seconds_observed": g["active_seconds_observed"]})
    return dict(policies=list(policies.values()), excluded=dict(excluded), causal_comparison=False,
        cohort_row_limit=250,
        grading_context_groups=list(comparison_groups.values()),
        comparison="Descriptive exact source/stage/hand/tempo/range/support/rule cohorts with captured policy parameters. Expertise and precollection exposure are unknown; selection bias remains. No pooled policy superiority or learning-effect estimate.")
