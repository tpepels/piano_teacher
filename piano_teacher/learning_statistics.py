"""Read-only descriptive learning statistics from the single local ledger.

Capture from the canonical ledger; format detached bounded rows. Counts describe retained
records, never an inferred lifetime history, mastery award or causal effect.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math


def _object(encoded):
    return json.loads(encoded) if encoded else {}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _day(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).date().isoformat() if parsed.tzinfo else None
    except (ValueError, TypeError):
        return None


class _Residual:
    def __init__(self):
        self.samples = []
        self.count = 0
        self.total = self.absolute = self.mean = self.m2 = 0.0
        self.minimum = self.maximum = None

    def add(self, value):
        if not _number(value):
            return
        self.count += 1
        self.samples.append(value)
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.total += value
        self.absolute += abs(value)
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def result(self):
        samples = sorted(self.samples)
        def quantile(p):
            if not samples:
                return None
            index = (len(samples)-1)*p
            lo, hi = math.floor(index), math.ceil(index)
            return samples[lo] + (samples[hi]-samples[lo])*(index-lo)
        return {"sample_count": self.count,
                "quantiles_seconds": {key: quantile(p) for key, p in (("p05", .05), ("p25", .25), ("p50", .5), ("p75", .75), ("p95", .95))},
                "mean_seconds": self.mean if self.count else None,
                "mean_absolute_seconds": self.absolute / self.count if self.count else None,
                "population_std_seconds": math.sqrt(max(0.0, self.m2 / self.count)) if self.count else None,
                "minimum_seconds": self.minimum, "maximum_seconds": self.maximum}


def _performed_context(context, terminal):
    result = dict(context)
    if isinstance(terminal.get("assistance_used"), bool):
        result["assistance"] = terminal["assistance_used"]
    assessed_end, planned_end = terminal.get("assessed_end_beat"), context.get("end_beat")
    if _number(assessed_end) and _number(planned_end) and assessed_end < planned_end:
        result["end_beat"] = assessed_end
        if result.get("scope") == "full":
            result["scope"] = "partial"
    return result


def _compatibility(before, after):
    """Recheck context rather than trusting an outcome's comparability flags."""
    if before is None or after is None:
        return "unknown"
    left = _performed_context(before["context"], before["terminal"])
    right = _performed_context(after["context"], after["terminal"])
    dimensions = []
    for fields in (("fingerprint", "stage_key", "hand"), ("performed_bpm",),
                   ("scope", "from_beat", "end_beat"), ("rule_id",)):
        dimensions.append(None if any(left.get(k) is None or right.get(k) is None for k in fields)
                          else all(left[k] == right[k] for k in fields))
    for field in ("tempo_map_hash", "calibration_ms", "midi_available"):
        if field in left or field in right:
            dimensions.append(None if left.get(field) is None or right.get(field) is None
                              else left[field] == right[field])
    support = []
    for attempt in (before, after):
        value = attempt["terminal"].get("assistance_used", attempt["context"].get("assistance"))
        support.append(value if isinstance(value, bool) else None)
    dimensions.append(None if any(value is None for value in support) else support[0] == support[1])
    if False in dimensions:
        return "incompatible"
    return "compatible" if all(value is True for value in dimensions) else "unknown"


def learning_statistics(ledger, fingerprint: str | None = None, *, query=None, snapshot=None) -> dict:
    """Aggregate current-learner evidence, optionally for one exact source.

    Stored acceptance/clean/eligibility flags are reported independently.
    Timing samples use the grader's original signed residuals without matching
    notes again. Missing, pruned and legacy detail never becomes measured zero.
    """
    from .learning_statistics_query import validate_query, capture_statistics
    q = validate_query(query, fingerprint)
    fingerprint = q.get("fingerprint")
    snapshot = snapshot or capture_statistics(ledger.db, ledger.learner_id, q)
    sessions = {}
    daily_sessions, daily_attempts, phases = Counter(), Counter(), Counter()
    unknown_session_dates = unknown_attempt_dates = 0
    for row in snapshot["sessions"]:
        sessions[row["session_id"]] = row
        day = _day(row["started_utc"])
        if day is None:
            unknown_session_dates += 1
        else:
            daily_sessions[day] += 1
        phases.update(_object(row["durations_json"]))

    attempts, states, scopes, groups, statuses, flags = {}, Counter(), Counter(), Counter(), Counter(), Counter()
    assessments = dict(assessed=0, accepted=0, rejected=0, acceptance_unknown=0,
        strict_clean=0, clean_unknown=0, mastery_eligible=0, accepted_mastery_eligible=0,
        accepted_with_warnings=0, extra_notes=0, expected_notes=0)
    residuals = {name: _Residual() for name in ("onset", "release", "duration")}
    elapsed, known_duration, detail_attempts, observation_count = 0.0, 0, 0, 0
    pruned = legacy = unknown_suffix = incomplete_context = 0
    bpm_levels = Counter()
    for row in snapshot["attempts"]:
        context = _object(row["summary_json"])
        terminal = context.get("terminal") or {}
        # No raw MIDI, note lists or private device names enter this projection.
        attempts[row["attempt_id"]] = {"session_id": row["session_id"], "context": context, "terminal": terminal,
                                      "passed": row["passed"], "state": row["state"]}
        states[row["state"]] += 1
        scopes[context.get("scope") or "unknown"] += 1
        pruned += bool(row["detail_pruned"])
        legacy += row["provenance"] == "legacy_bounded"
        unknown_suffix += row["state"] == "process_interrupted" or terminal.get("unknown_suffix") is True
        day = _day(context.get("started_utc"))
        if day is None:
            unknown_attempt_dates += 1
        else:
            daily_attempts[day] += 1
        performed = _performed_context(context, terminal)
        group = (row["fingerprint"], row["stage_key"], context.get("hand"),
                 performed.get("scope"), context.get("performed_bpm"),
                 terminal.get("assistance_used", context.get("assistance")), row["rule_id"],
                 context.get("from_beat"), performed.get("end_beat"))
        if all(value is not None for value in group):
            groups[group] += 1
        else:
            incomplete_context += 1
        bpm = context.get("performed_bpm", row["assessed_bpm"])
        if _number(bpm) and bpm > 0:
            bpm_levels[bpm] += 1
        start, end = context.get("monotonic_start"), terminal.get("monotonic_end")
        if _number(start) and _number(end) and end >= start:
            elapsed += end - start
            known_duration += 1
        if row["assessment_json"] is not None:
            assessment = _object(row["assessment_json"])
            assessments["assessed"] += 1
            assessments["accepted"] += row["passed"] == 1
            assessments["rejected"] += row["passed"] == 0
            assessments["acceptance_unknown"] += row["passed"] is None
            assessments["strict_clean"] += row["clean"] == 1
            assessments["clean_unknown"] += row["clean"] is None
            assessments["mastery_eligible"] += row["mastery_eligible"] == 1
            assessments["accepted_mastery_eligible"] += row["passed"] == 1 and row["mastery_eligible"] == 1
            assessments["accepted_with_warnings"] += row["passed"] == 1 and row["clean"] == 0
            assessments["extra_notes"] += row["extra_notes"]
            assessments["expected_notes"] += assessment.get("note_count", 0)
            statuses.update(assessment.get("status_counts") or {})
        if row["detail_present"]:
            detail_attempts += 1
            for observation in json.loads(row["observations_json"] or "[]"):
                observation_count += 1
                for name, statistic in residuals.items():
                    statistic.add(observation.get(name + "_residual"))
                flags["pitch_error"] += observation.get("pitch_error") is True
                flags["unreleased"] += observation.get("unreleased") is True
                flags["ambiguous_pairing"] += observation.get("ambiguous_pairing") is True
                for kind in ("early", "late"):
                    flags["timing_" + kind] += observation.get("timing_error") == kind
                for kind in ("short", "long"):
                    flags["hold_" + kind] += observation.get("hold_error") == kind
    known_acceptance = assessments["accepted"] + assessments["rejected"]
    assessments["acceptance_rate"] = assessments["accepted"] / known_acceptance if known_acceptance else None
    assessments["acceptance_rate_denominator"] = known_acceptance

    decisions, policies, triggers, outcomes_by_kind, outcome_states = {}, Counter(), Counter(), Counter(), Counter()
    tempo_changes = dict(recorded_changes=0, increases=0, reductions=0)
    def tempo_change(data):
        before = data.get("before_bpm", (data.get("before") or {}).get("bpm"))
        after = data.get("after_bpm", (data.get("after") or {}).get("bpm"))
        if _number(before) and _number(after) and before != after:
            tempo_changes["recorded_changes"] += 1
            tempo_changes["increases" if after > before else "reductions"] += 1
    for row in snapshot["decisions"]:
        data = _object(row["summary_json"])
        decisions[row["decision_id"]] = row["attempt_id"]
        policies[data.get("policy") or "unknown"] += 1
        triggers[data.get("trigger") or "unknown"] += 1
        tempo_change(data)
    for row in snapshot["events"]:
        if row["kind"] in ("manual_action", "progression", "tempo_change"):
            tempo_change(_object(row["summary_json"]))
    outcome_counts = Counter()
    for row in snapshot["outcomes"]:
        data = _object(row["summary_json"])
        outcome_counts["outcomes"] += 1
        outcomes_by_kind[data.get("kind") or "unknown"] += 1
        outcome_states[data.get("state") or "unknown"] += 1
        if data.get("state") == "censored":
            outcome_counts["censored_outcomes"] += 1
            continue
        after = attempts.get(row["attempt_id"])
        category = _compatibility(attempts.get(decisions[row["decision_id"]]), after)
        outcome_counts[category + "_outcomes"] += 1
        if category == "compatible" and after["state"] == "completed" and after["passed"] is not None:
            outcome_counts["compatible_assessed_outcomes"] += 1
            outcome_counts["compatible_accepted_outcomes"] += after["passed"] == 1
    interventions = {key: outcome_counts[key] for key in ("outcomes", "compatible_outcomes",
        "incompatible_outcomes", "unknown_outcomes", "censored_outcomes",
        "compatible_assessed_outcomes", "compatible_accepted_outcomes")}
    interventions.update(decisions=len(decisions), policies=dict(sorted(policies.items())),
        triggers=dict(sorted(triggers.items())), outcomes_by_kind=dict(sorted(outcomes_by_kind.items())),
        outcome_states=dict(sorted(outcome_states.items())), causal_comparison=False,
        compatibility_basis="Same source/stage/hand, performed BPM, scope/range, assistance and grading rule; captured tempo maps, calibration and input availability must also agree. Unknown fields remain unknown.")
    report = {
        "schema_version": 2, "fingerprint": fingerprint, "scope": "retained_current_learner_records",
        "units": {"duration": "seconds", "residuals": "seconds", "tempo": "beats_per_minute", "calendar": "UTC"},
        "sessions": {"count": len(sessions),
                     "with_attempts": len({row["session_id"] for row in attempts.values()}),
                     "open": sum(row["closure_reason"] is None for row in sessions.values()),
                     "closure_reasons": dict(Counter(row["closure_reason"] or "open" for row in sessions.values())),
                     "unknown_start_dates": unknown_session_dates},
        "attempts": {"count": len(attempts), "states": dict(sorted(states.items())), "scopes": dict(sorted(scopes.items())),
                     "repetitions": sum(count - 1 for count in groups.values()),
                     "repetition_groups": len(groups), "unknown_repetition_context": incomplete_context,
                     "unknown_start_dates": unknown_attempt_dates,
                     "repetition_definition": "Additional selected-window attempt IDs at the same exact source, stage, hand, scope/range, performed BPM, recorded assistance and rule."},
        "assessments": assessments,
        "mistakes": {"status_counts": dict(sorted(statuses.items())), "extra_notes": assessments["extra_notes"],
                     "expected_notes": assessments["expected_notes"],
                     "precise_note_rate": statuses["correct"] / assessments["expected_notes"] if assessments["expected_notes"] else None},
        "timing": {**{name: statistic.result() for name, statistic in residuals.items()},
                   "observation_count": observation_count, "independent_flags": dict(sorted(flags.items())),
                   "scope": "Retained grader assignments only; signed residuals, no rematching or physical-latency inference."},
        "durations": {"phase_seconds": dict(sorted(phases.items())) if fingerprint is None and phases else None,
                      "phase_missingness": "piece_attribution_unavailable" if fingerprint is not None else
                                            None if phases else "no_captured_phase_intervals",
                      "measured_attempt_seconds": elapsed if known_duration else None,
                      "attempts_with_measured_duration": known_duration,
                      "attempts_with_unknown_duration": len(attempts) - known_duration,
                      "definition": "Attempt elapsed monotonic time may include pauses; phase totals are captured transition intervals, not inferred practice minutes."},
        "tempo": {**tempo_changes, "levels": [{"bpm": bpm, "attempts": count} for bpm, count in sorted(bpm_levels.items())],
                  "definition": "Recorded BPM changes only; slower successful attempts are not equivalent-tempo improvement."},
        "interventions": interventions,
        "daily": [{"date": day, "sessions": daily_sessions[day], "attempts": daily_attempts[day]}
                  for day in sorted(set(daily_sessions) | set(daily_attempts))],
        "coverage": {"pruned_attempts": pruned,
                     "pruned_sessions": sum(bool(row["detail_pruned"]) for row in sessions.values()),
                     "summary_retained_since_utc": min((row["started_utc"] for row in sessions.values()
                                                        if row["started_utc"]), default=None),
                     "legacy_bounded_attempts": legacy,
                     "unknown_crash_suffix_attempts": unknown_suffix,
                     "attempts_with_retained_detail": detail_attempts,
                     "detail_history_complete": not bool(pruned or legacy or unknown_suffix or states["open"]
                         or any(row["detail_pruned"] or row["closure_reason"] == "process_interrupted"
                                for row in sessions.values())),
                     "limits": ["Counts describe retained evidence, not a complete lifetime before collection or after deletion.",
                                "Legacy acceptance, timing and dates remain unknown; pruning preserves counts but removes note-detail samples.",
                                "Active-session intervals may not yet be flushed. No retention study or causal teaching effect is estimated."]},
    }

    from .learning_statistics_metrics import extend_report
    return extend_report(report, snapshot)
