"""Accept rest contours, dots, rhythm and bounded readable placement separately.

These checks establish neither intended voice lanes nor global ink absence."""
from __future__ import annotations

from fractions import Fraction
from math import isfinite
from .visual_contract import FLAG_COUNTS, STATUSES, finite_score, source_beat, source_number, valid_box


def rectangular_rest_identified(row, kind):
    """Consume the rest detector's grid orientation, never infer a voice lane."""
    evidence = row.get("orientation_evidence")
    if (row.get("type_ambiguity") is not False or row.get("observed_rest") != kind
            or not isinstance(evidence, dict) or evidence.get("observed_rest") != kind):
        return False
    lines, gap = evidence.get("staff_lines"), evidence.get("staff_gap")
    numeric = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)
    if (not isinstance(lines, (list, tuple)) or len(lines) != 5
            or not all(numeric(x) for x in lines) or not numeric(gap) or gap <= 0
            or any(abs((b-a)-gap) > .15*gap for a, b in zip(lines, lines[1:]))):
        return False
    hanging, sitting, height = (evidence.get(k) for k in
        ("hanging_edge_error_spaces", "sitting_edge_error_spaces", "height_spaces"))
    if (not all(numeric(x) for x in (hanging, sitting, height))
            or not .35 <= height <= .65 or not 0 <= hanging <= .5 or not 0 <= sitting <= .5):
        return False
    correct = (hanging <= .13 and sitting >= .30) if kind == "whole" else (
        sitting <= .13 and hanging >= .30)
    rival = row.get("next_family_score")
    return (correct and finite_score(row.get("shape_match")) and row["shape_match"] >= .65
            and numeric(rival) and 0 <= rival <= 1 and row["shape_match"]-rival >= .03
            and all(type(row.get(k)) is int and row[k] >= 12
                    for k in ("changed_pixels", "visible_original_ink_removed"))
            and isinstance(row.get("delta_file"), str) and bool(row["delta_file"]))


def _rest_dots_verified(evidence, count):
    if (not isinstance(evidence, dict) or evidence.get("status") != "verified"
            or any(type(evidence.get(key)) is not int or evidence[key] != count
                   for key in ("expected_count", "observed_count"))):
        return False
    dots = evidence.get("dots")
    if (not isinstance(dots, list) or len(dots) != count
            or any(not isinstance(dot, dict) or not valid_box(dot.get("box"))
                   or not finite_score(dot.get("shape_match")) or dot["shape_match"] < .8 for dot in dots)):
        return False
    boxes = [dot["box"] for dot in dots]
    return all(a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
               for i, a in enumerate(boxes) for b in boxes[:i])


def _rest_placement_verified(evidence, record):
    """Validate bounded readable layout; this does not declare a voice lane."""
    if not isinstance(evidence, dict) or evidence.get("status") != "verified":
        return False
    numeric = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x)
    if evidence.get("bbox") != record.get("observed_box"):
        return False
    orientation = record.get("orientation_evidence")
    if isinstance(orientation, dict) and any(evidence.get(k) != orientation.get(k) for k in ("staff_lines", "staff_gap")):
        return False
    lines, gap = evidence.get("staff_lines"), evidence.get("staff_gap")
    if (not isinstance(lines, list) or len(lines) != 5 or not all(numeric(x) for x in lines)
            or not numeric(gap) or gap <= 0
            or any(abs((b-a)-gap) > .15*gap for a, b in zip(lines, lines[1:]))):
        return False
    boxes = [evidence.get(k) for k in ("bbox", "body_bbox", "silhouette_bbox")]
    if not all(valid_box(box) for box in boxes):
        return False
    silhouette = boxes[-1]
    if any(box[0] < silhouette[0] or box[1] < silhouette[1]
           or box[2] > silhouette[2] or box[3] > silhouette[3] for box in boxes[:2]):
        return False
    corridor, baseline_range = evidence.get("corridor_y"), evidence.get("baseline_range_y")
    if any(not isinstance(pair, list) or len(pair) != 2 or not all(numeric(x) for x in pair)
           or pair[0] > pair[1] for pair in (corridor, baseline_range)):
        return False
    baseline, relative, phase, clearance, pixels = (evidence.get(k) for k in
        ("baseline_y", "relative_offset_spaces", "grid_phase_error_spaces", "min_clearance_spaces", "min_clearance_pixels"))
    if not all(numeric(x) for x in (baseline, relative, phase, clearance, pixels)):
        return False
    offset = (baseline-lines[2])/gap
    grid_step = 1. if record.get("required_rest") in {"whole", "half"} else .5
    grid_distance = lambda value: abs(value-round(value/grid_step)*grid_step)
    endpoint_phases = [grid_distance((y-lines[2])/gap) for y in baseline_range]
    return (finite_score(evidence.get("registration_match")) and evidence["registration_match"] >= .79
            and evidence.get("required_clearance_spaces") == .12
            and evidence.get("grid_phase_tolerance_spaces") == .13
            and clearance >= .12 and pixels/gap >= .12 and abs(pixels/gap-clearance) <= .0001
            and type(evidence.get("clearance_capped")) is bool
            and evidence.get("clearance_search_spaces") == 1.
            and 0 <= phase <= .13 and max(endpoint_phases) <= phase+.0002
            and abs(offset-relative) <= .0001 and grid_distance(offset) <= .13
            and baseline_range[0] <= baseline <= baseline_range[1]
            and baseline_range[1]-baseline_range[0] <= .26*gap
            and lines[0]-2.5*gap <= corridor[0] <= silhouette[1]-.5
            and silhouette[3]+.5 <= corridor[1] <= lines[-1]+2.5*gap)


def apply_rest_evidence(output, expected, matched):
    for rest in [r for r in output if r["construct"] == "rest"]:
        path = rest["source"]["xml_ordinal"]
        event, match = expected[path], matched.get(path)
        record = rest.get("evidence", {}).get("pixel")
        if not isinstance(record, dict) or match is None:
            continue
        obligations = [r for r in output if r["source"].get("xml_ordinal") == path]
        rhythm = next(r for r in obligations if r["construct"] == "rest_rhythm")
        dots = record.get("dot_evidence")
        if dots is None:
            continue  # Older contour-only reports cannot establish rhythm.
        clock = record.get("beat")
        rival = record.get("next_family_score")
        bound = (rest["status"] == "verified" and record.get("source_id") == match["_pixel_id"]
                 and not isinstance(record.get("measure"), bool) and source_number(record.get("measure")) == match["measure"]
                 and isinstance(clock, (int, float)) and not isinstance(clock, bool) and isfinite(clock)
                 and source_beat(clock) == match["beat"] and record.get("staff") == match["staff"]
                 and str(record.get("voice")) == match["voice"]
                 and record.get("required_rest") == record.get("observed_rest") == event["note_type"]
                 and finite_score(record.get("shape_match")) and record["shape_match"] >= .65
                 and isinstance(rival, (int, float)) and not isinstance(rival, bool) and 0 <= rival <= 1
                 and record["shape_match"]-rival >= .03
                 and all(type(record.get(k)) is int and record[k] >= 12
                         for k in ("changed_pixels", "visible_original_ink_removed")))
        dots_verified = bound and event["dots"] == match["dots"] and _rest_dots_verified(dots, event["dots"])
        placement = record.get("placement_evidence")
        if isinstance(placement, dict):
            target = next(r for r in obligations if r["construct"] == "rest_placement")
            status = placement.get("status")
            if not dots_verified:
                status, reason = "unverified", "Placement requires a bound, independently identified rest and every source dot"
            elif status != "verified":
                status = status if status in STATUSES else "unverified"
                reason = placement.get("reason", "Independent rest placement is unresolved")
            elif _rest_placement_verified(placement, record):
                reason = "Independent font registration, readable staff corridor and bright-ink clearance verified; intended voice lane is not certified"
            else:
                status, reason = "unverified", "Placement record lacks valid grid, corridor or independent clearance measurements"
            target.update(status=status, reason=reason, evidence=placement)
        for row in obligations:
            if row["construct"] == "dot":
                row.update(status="verified" if dots_verified else "unverified",
                           reason="Every bound source rest dot has distinct independent contour evidence"
                                  if dots_verified else "Source rest dots lack independent count and contour evidence",
                           evidence=dots)
        durations = {"whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
                     **{kind: Fraction(1, 2**count) for kind, count in FLAG_COUNTS.items()}}
        base = durations.get(event["note_type"])
        value = base * (2 - Fraction(1, 2**event["dots"])) if base is not None else None
        arithmetic = (value is not None and value == event["_duration"] == match["_duration"]
                      and not event["_connectors"] and not match["_connectors"])
        verified = dots_verified and arithmetic
        rhythm.update(status="verified" if verified else "unverified",
                      reason="Bound rest type, every dot and exact written duration verified" if verified else
                             "Rest rhythm requires bound type, all independent dots and exact source duration arithmetic",
                      evidence=dict(pixel=record, expected_duration=str(value)))
