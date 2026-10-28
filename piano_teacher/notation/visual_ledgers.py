"""Accept every required ledger segment at its bound current-image head.

A known missing witness dominates green alternatives. Counts never replace
complete thin, continuous, source-bound segment measurements."""
from __future__ import annotations

from collections import Counter
from math import ceil, isfinite
from .visual_binding import feature_identity, feature_record, measured_records
from .visual_contract import STATUSES, capture_frame_clock, finite_score, valid_box


def _ledger_measurement(observation, event):
    """All required lines must span the same registered head at source staff Y."""
    steps = event.get("_ledger_steps")
    if event.get("_ledger_error") or not steps or observation.get("expected_steps") != steps:
        return False
    matched, evidence = observation.get("matched_segments"), observation.get("evidence")
    if not isinstance(evidence, dict) or evidence.get("status") != "verified":
        return False
    gap, lines, head = (evidence.get(k) for k in ("staff_gap", "staff_lines", "head_bbox"))
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
    if (not numeric(gap) or gap <= 0 or not isinstance(lines, list) or len(lines) != 5 or
            not all(numeric(y) for y in lines) or any(a >= b for a, b in zip(lines, lines[1:])) or
            abs((lines[-1]-lines[0])/4-gap) > .000001 or not valid_box(head) or
            not all(type(v) is int and v >= 0 for v in head) or
            not finite_score(evidence.get("head_match")) or evidence["head_match"] < .79 or
            not head[1] <= lines[-1]-event["_staff_step"]*gap/2 < head[3]):
        return False
    clock = capture_frame_clock(evidence.get("frame"))
    registration = evidence.get("registration")
    if (clock is None or not isinstance(registration, dict) or type(registration.get("pixels")) is not int or
            not finite_score(registration.get("agreement")) or registration["agreement"] < .8 or
            not finite_score(registration.get("margin")) or registration["margin"] < .04 or
            (abs(clock-event["beat"]) <= .0000051 and
             (registration["pixels"] != 0 or registration["agreement"] != 1))):
        return False
    witnesses = evidence.get("witnesses")
    selected = {k: v for k, v in evidence.items() if k != "witnesses"}
    if (not isinstance(witnesses, list) or not witnesses or
            any(not isinstance(w, dict) or w.get("status") not in STATUSES or w["status"] == "mismatch" for w in witnesses) or
            selected not in witnesses or not isinstance(matched, list) or len(matched) != len(steps) or
            evidence.get("segments") != matched):
        return False
    for step, segment in zip(steps, matched):
        if (not isinstance(segment, dict) or segment.get("status") != "verified" or
                type(segment.get("step")) is not int or segment["step"] != step or
                segment.get("head_bbox") != head or segment.get("continuous") is not True or
                segment.get("required_extension_spaces") != .12 or not valid_box(segment.get("bbox"))):
            return False
        box = segment["bbox"]
        if not all(type(v) is int and v >= 0 for v in box):
            return False
        expected_y, y = lines[-1]-step*gap/2, (box[1]+box[3]-1)/2
        expected_fields = dict(expected_y=expected_y, y=y, thickness_spaces=(box[3]-box[1])/gap,
                               left_extension_spaces=(head[0]-box[0])/gap,
                               right_extension_spaces=(box[2]-head[2])/gap)
        if (any(not numeric(segment.get(k)) or abs(segment[k]-v) > .000001 for k, v in expected_fields.items()) or
                abs(y-expected_y) > .13*gap or box[3]-box[1] > max(2, ceil(.14*gap)) or
                box[0] > head[0]-ceil(.12*gap) or box[2] < head[2]+ceil(.12*gap)):
            return False
    return True


def apply_ledgers(output, expected, matched, generated, report):
    measurements = measured_records(report)
    identities = Counter(feature_identity(e) for e in generated.events.values()
                         if e["kind"] == "note" and e["timing_supported"])
    source_ids = Counter(e["_pixel_id"] for e in expected.values() if e["kind"] == "note")
    generated_ids = Counter(e["_pixel_id"] for e in generated.events.values() if e["kind"] == "note")
    for row in output:
        if row["construct"] != "ledger":
            continue
        event = expected[row["source"]["xml_ordinal"]]
        match = matched.get(event["xml_ordinal"])
        row.update(status="unverified", reason="Every source-required ledger line needs bound current-image evidence")
        if (match is None or event.get("_ledger_error") or match.get("_ledger_error") or
                source_ids[event["_pixel_id"]] != 1 or generated_ids[match["_pixel_id"]] != 1 or
                event.get("_ledger_steps") != match.get("_ledger_steps") or
                event.get("_staff_step") != match.get("_staff_step")):
            continue
        record, _reason = feature_record(match, measurements, identities)
        features = record.get("features") if record else None
        observation = features.get("ledger") if isinstance(features, dict) else None
        if not isinstance(observation, dict) or observation.get("status") not in STATUSES:
            continue
        if observation["status"] != "verified":
            row.update(status=observation["status"], reason=observation.get("reason", "Ledger evidence remains unresolved"), evidence=observation)
        elif _ledger_measurement(observation, match):
            row.update(status="verified", reason="All source-required ledger steps have thin continuous ink beyond both registered head edges",
                       evidence=dict(generated_source_id=match["_pixel_id"], oracle_source_id=match["_oracle_id"], pixel=observation))
