"""Accept note-feature payloads and exact written rhythm obligations.

Acceptance is independent of pixel recognition: producer status never
substitutes for bound, complete measurements of each required construct."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil, floor, isfinite
from .visual_binding import feature_identity, feature_record, measured_records
from .visual_contract import FLAG_COUNTS, STATUSES, finite_score, source_beat, valid_box


_FEATURES = {"stem", "flag", "dot", "accidental"}
_ACCIDENTAL_GLYPHS = {"flat": "acc_flat", "natural": "acc_natural", "sharp": "acc_sharp",
                      "double-flat": "acc_double_flat", "flat-flat": "acc_double_flat",
                      "double-sharp": "acc_double_sharp"}


def _family_evidence(evidence, glyph):
    if not isinstance(evidence, dict) or not glyph:
        return False
    score, runner, margin = (evidence.get(k) for k in ("score", "runner_up", "margin"))
    return (evidence.get("expected") == evidence.get("observed") == glyph
            and finite_score(score) and score >= .72
            and isinstance(runner, (int, float)) and not isinstance(runner, bool) and 0 <= runner <= 1
            and isinstance(margin, (int, float)) and not isinstance(margin, bool) and margin >= .05
            and abs(score - runner - margin) <= .0002 and valid_box(evidence.get("bbox")))


def note_feature_status(construct, original, generated, record, bound=None):
    features = record.get("features") if isinstance(record, dict) else None
    result = features.get(construct) if isinstance(features, dict) else None
    if not isinstance(result, dict) or result.get("status") not in STATUSES:
        return "unverified", "Missing independent measurement for this feature", None
    status = result["status"]
    if status != "verified":
        return status, result.get("reason", "Independent feature remains unverified"), result
    evidence = result.get("evidence")
    valid = isinstance(evidence, dict) and valid_box(evidence.get("bbox"))
    if valid and construct == "stem":
        direction = evidence.get("direction")
        matches = evidence.get("head_matches")
        valid = (isinstance(direction, str) and direction in {"up", "down"}
                 and all(e["_stem"] in (None, direction) for e in (original, generated))
                 and evidence.get("group_id") == generated["_group_id"]
                 and evidence.get("shared_source_ids") == generated["_group_members"]
                 and isinstance(matches, list) and len(matches) == len(generated["_group_members"])
                 and all(finite_score(m) and m >= .79 for m in matches))
    elif valid and construct == "flag":
        count = FLAG_COUNTS.get(original["note_type"])
        stem_status, _, stem_result = note_feature_status("stem", original, generated, record)
        direction = stem_result["evidence"]["direction"] if stem_status == "verified" else None
        valid = (count is not None and original["note_type"] == generated["note_type"]
                 and direction is not None and _family_evidence(evidence, f"flag_{direction}_{count}"))
    elif valid and construct == "dot":
        dots = evidence.get("dots")
        valid = (type(evidence.get("expected_count")) is int
                 and evidence["expected_count"] == original["dots"] == generated["dots"]
                 and isinstance(dots, list) and len(dots) == original["dots"]
                 and all(_family_evidence(dot, "augmentation_dot") for dot in dots)
                 and len({tuple(dot["bbox"]) for dot in dots}) == len(dots))
    elif valid and construct == "accidental":
        glyph = _ACCIDENTAL_GLYPHS.get(original["_accidental"])
        valid = (glyph is not None and glyph == _ACCIDENTAL_GLYPHS.get(generated["_accidental"])
                 and _family_evidence(evidence, glyph))
    elif valid and construct == "flag_absence":
        stem_status, _, stem_result = note_feature_status("stem", original, generated, record)
        stem = stem_result.get("evidence", {}) if stem_status == "verified" else {}
        scores = evidence.get("family_scores")
        box = evidence["bbox"]
        valid = (original["note_type"] == generated["note_type"] == "quarter"
                 and bool(stem) and evidence.get("direction") == stem.get("direction")
                 and evidence.get("stem_bbox") == stem.get("bbox")
                 and evidence.get("group_id") == generated["_group_id"]
                 and evidence.get("shared_source_ids") == generated["_group_members"]
                 and type(evidence.get("expected_count")) is int and evidence["expected_count"] == 0
                 and type(evidence.get("bright_pixels")) is int and evidence["bright_pixels"] == 0
                 and evidence.get("sampled_pixels") == (box[2]-box[0])*(box[3]-box[1])
                 and evidence.get("glyph_minimum") == .72 and isinstance(scores, dict)
                 and set(scores) == {f"flag_{d}_{c}" for d in ("up", "down") for c in range(1, 6)}
                 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                         and isfinite(v) and 0 <= v < .72 for v in scores.values()))
        if valid:
            associated=evidence.get("associated_dots",[])
            raw=evidence.get("raw_bright_pixels",evidence.get("bright_pixels"))
            valid=(isinstance(associated,list) and type(raw) is int and raw>=0
                   and all(isinstance(d,dict) and isinstance(d.get("source_id"),str) for d in associated)
                   and len({d["source_id"] for d in associated})==len(associated))
            excluded=0
            for item in associated if valid else []:
                sid=item.get("source_id")
                owner=(bound or {}).get(sid)
                if not isinstance(item,dict) or sid not in generated["_group_members"] or not owner:
                    valid=False
                    break
                event,measurement=owner
                dot_status,_,dot=note_feature_status("dot",event,event,measurement)
                count=item.get("excluded_pixels")
                if dot_status!="verified" or item.get("measurement")!=dot.get("evidence") or type(count) is not int or count<=0:
                    valid=False
                    break
                area=0
                for glyph in dot["evidence"]["dots"]:
                    b=glyph["bbox"]
                    area+=max(0,min(box[2],b[2])-max(box[0],b[0]))*max(0,min(box[3],b[3])-max(box[1],b[1]))
                if count>area:
                    valid=False
                    break
                excluded+=count
            valid=valid and raw==evidence["bright_pixels"]+excluded
        if valid:
            gap, head, size = evidence.get("staff_gap"), evidence.get("head_bbox"), evidence.get("frame_size")
            head_boxes = evidence.get("head_bboxes")
            numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
            valid = (numeric(gap) and gap > 0 and valid_box(head)
                     and isinstance(head_boxes, list) and len(head_boxes) == len(generated["_group_members"])
                     and all(valid_box(b) for b in head_boxes)
                     and numeric(stem.get("x")) and numeric(stem.get("tip_y"))
                     and isinstance(size, list) and len(size) == 2
                     and all(type(v) is int and v > 0 for v in size)
                     and all(type(v) is int for v in box))
            if valid:
                x, tip, sb = stem["x"], stem["tip_y"], stem["bbox"]
                union = [min(b[0] for b in head_boxes), min(b[1] for b in head_boxes),
                         max(b[2] for b in head_boxes), max(b[3] for b in head_boxes)]
                expected = ([sb[2]+1, tip-2, ceil(x+1.6*gap), min(ceil(tip+2.5*gap), head[1]-1)]
                            if stem["direction"] == "up" else
                            [sb[2]+1, max(floor(tip-2.5*gap), head[3]+1), ceil(x+1.6*gap), tip+3])
                valid = (head == union and box == expected and 0 <= box[0] < box[2] <= size[0]
                         and 0 <= box[1] < box[3] <= size[1])
    return ("verified", "Independent bound feature evidence", result) if valid else (
        "unverified", "Feature evidence does not measure the required source construct", result)


def apply_note_features(output, expected, matched, generated, feature_report):
    measurements = measured_records(feature_report)
    identities = Counter(feature_identity(e) for e in generated.events.values()
                         if e["kind"] == "note" and e["timing_supported"])
    bound={}
    for event in generated.events.values():
        if event["kind"]=="note" and event["timing_supported"]:
            row,_=feature_record(event,measurements,identities)
            if row is not None:
                bound[event["_pixel_id"]]=(event,row)
    by_event = defaultdict(list)
    for row in output:
        path = row["source"].get("xml_ordinal")
        if path in expected and expected[path]["kind"] == "note":
            by_event[path].append(row)
    for path, obligations in by_event.items():
        event, match = expected[path], matched.get(path)
        record, reason = feature_record(match, measurements, identities) if match else (
            None, "Original visible event has no generated counterpart")
        for row in obligations:
            if row["construct"] not in _FEATURES:
                continue
            status, why, evidence = note_feature_status(row["construct"], event, match, record,bound) if record else (
                "unverified", reason, None)
            row.update(status=status, reason=why, evidence=evidence)
        rhythm = next(r for r in obligations if r["construct"] == "note_rhythm")
        if (event["_connectors"] or (match and match["_connectors"])
                or any(r["construct"] in {"beam", "tuplet"} for r in obligations)):
            rhythm.update(status="unsupported", reason="Rhythm still requires independent beam/tuplet evidence")
            continue
        requirements = [r for r in obligations if r["construct"] in {"pitch", "stem", "flag", "dot"}]
        if not any(r["construct"] in {"stem", "flag", "dot"} for r in requirements):
            rhythm.update(status="unsupported", reason="A notehead alone does not certify written rhythm")
            continue
        durations = {"whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
                     **{kind: Fraction(1, 2**count) for kind, count in FLAG_COUNTS.items()}}
        base = durations.get(event["note_type"])
        expected_duration = base * (2 - Fraction(1, 2**event["dots"])) if base is not None else None
        if expected_duration is None or source_beat(expected_duration) != event["duration"]:
            rhythm.update(status="unsupported", reason="Written value needs an independent duration interpretation")
        elif match and any(event[k] != match[k] for k in ("note_type", "duration", "dots")):
            rhythm.update(status="mismatch", reason="Generated written rhythm differs from the original event")
        elif event["note_type"] == "quarter" and note_feature_status(
                "flag_absence", event, match, record,bound)[0] != "verified":
            rhythm.update(status="unverified", reason="Quarter rhythm requires bound independent absent-flag evidence")
        elif all(r["status"] == "verified" for r in requirements):
            rhythm.update(status="verified", reason="Independent head and all required rhythm features verified",
                          evidence={"requirements": [r["id"] for r in requirements]})
            if event["note_type"] == "quarter":
                rhythm["evidence"]["flag_absence"] = record["features"]["flag_absence"]
        else:
            rhythm.update(status="unverified", reason="Every required independent rhythm contribution must verify")
