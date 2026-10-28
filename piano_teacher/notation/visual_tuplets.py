"""Accept hidden-tuplet semantics without inventing visual evidence.

Complete source groups, native payload bindings, exact ratio arithmetic
and every required graphic remain separate obligations."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from fractions import Fraction
from .proof import read_written_score
from .visual_binding import feature_identity, feature_record, measured_records
from .visual_contract import FLAG_COUNTS
from .visual_inventory import source_tuplet_groups
from .visual_notes import note_feature_status


def _semantic_value(value):
    if isinstance(value, (Fraction, float)):
        return round(float(value), 8)
    if isinstance(value, dict):
        return {k: _semantic_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_semantic_value(v) for v in value]
    return value


def _semantic_equal(a, b):
    # JSON types matter: True must not stand in for a numeric ratio member.
    try:
        return json.dumps(_semantic_value(a), sort_keys=True, allow_nan=False) == json.dumps(
            _semantic_value(b), sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        return False


def _native_tuplet_binding(fact, report):
    """Validate payloads against generated XML, not merely report status."""
    rows = report.get("elements", []) if isinstance(report, dict) else []
    if not isinstance(rows, list):
        return None
    own = [r for r in rows if isinstance(r, dict) and r.get("boundary") == "generated->native" and
           isinstance(r.get("source"), dict) and r["source"].get("id") == fact["source"]["id"]]
    if not own or any(r.get("status") != "verified" for r in own):
        return None
    written = ("kind", "staff", "onset", "duration", "pitch", "spelling", "note_type", "dots", "chord", "accidental", "visible")
    required = {
        "written_notes" if fact["kind"] == "note" else "written_rests": {k: fact[k] for k in written},
        "voices": fact["voice"],
        "ties": {k: fact[k] for k in ("tie_start", "tie_stop")},
        "tuplets": {k: fact[k] for k in ("time_modification", "tuplet_marks")},
        "tuplet_attributes": fact["tuplet_extras"],
        "written_tie_attributes": fact["tied_marks"],
        "beams": fact["beams"],
    }
    if fact["kind"] == "note":
        required["segment_identity"] = fact["id"]
    bound = []
    for construct, value in required.items():
        candidates = [r for r in own if r.get("construct") == construct]
        if len(candidates) != 1:
            return None
        row = candidates[0]
        if (row.get("source") != fact["source"] or not _semantic_equal(row.get("expected"), value) or
                not _semantic_equal(row.get("actual"), value)):
            return None
        bound.append(row)
    if any(isinstance(r, dict) and r.get("boundary") == "generated" and
           isinstance(r.get("source"), dict) and r["source"].get("id") == fact["source"]["id"] and
           r.get("status") != "verified" for r in rows):
        return None
    return bound


def apply_tuplet_semantics(output, original, expected, matched, generated,
                            original_xml, generated_xml, semantic_report, feature_report):
    """Hidden notation is a semantic policy; rhythm still needs actual graphics."""
    ratio_events = [e for e in expected.values() if e.get("_ratio") is not None or e.get("_tuplet_declarations")]
    if not ratio_events:
        return
    by_event = defaultdict(list)
    for row in output:
        by_event[row["source"].get("xml_ordinal")].append(row)
    try:
        source_facts = {e["source"]["id"]: e for e in read_written_score(original_xml or generated_xml, strict=False).symbols}
        generated_facts = {e["source"]["id"]: e for e in read_written_score(generated_xml, strict=False).symbols}
    except (ValueError, TypeError, KeyError):
        return
    groups = defaultdict(list)
    for group in source_tuplet_groups(generated):
        groups[tuple(e["xml_ordinal"] for e in group["events"])].append(group)
    original_ids = Counter(e["_pixel_id"] for e in original.events.values() if e["timing_supported"])
    generated_ids = Counter(e["_pixel_id"] for e in generated.events.values() if e["timing_supported"])
    proven = {}
    for group in source_tuplet_groups(original):
        originals = group["events"]
        if any(e["xml_ordinal"] not in expected for e in originals):
            continue
        events = [matched.get(e["xml_ordinal"]) for e in originals]
        if (any(e is None for e in events) or any(original_ids[e["_pixel_id"]] != 1 for e in originals) or
                any(generated_ids[e["_pixel_id"]] != 1 for e in events)):
            continue
        candidates = groups[tuple(e["xml_ordinal"] for e in events)]
        if len(candidates) != 1 or any(group[k] != candidates[0][k] for k in ("number", "ratio", "hidden")):
            continue
        sfacts = [source_facts[e["_oracle_id"]] for e in originals]
        gfacts = [generated_facts[e["_oracle_id"]] for e in events]
        fields = ("kind", "note_type", "dots", "time_modification", "tuplet_marks", "tuplet_extras")
        if any(not _semantic_equal({k: a[k] for k in fields}, {k: b[k] for k in fields}) for a, b in zip(sfacts, gfacts)):
            continue
        native = [_native_tuplet_binding(fact, semantic_report) for fact in gfacts]
        if any(rows is None for rows in native):
            continue
        evidence = dict(kind="semantic", hidden=group["hidden"], ratio=list(group["ratio"]),
                        number=group["number"], generated_source_ids=[e["_pixel_id"] for e in events],
                        oracle_source_ids=[e["_oracle_id"] for e in events], native_contract=native)
        for event in originals:
            path = event["xml_ordinal"]
            proven[path] = evidence
            for row in by_event[path]:
                if row["construct"] == "tuplet" and row.get("scope") == "semantic":
                    row.update(status="verified", reason="Source ratio, complete group and display metadata agree with the bound native semantic contract",
                               evidence=evidence)
    measurements = measured_records(feature_report)
    identities = Counter(feature_identity(e) for e in generated.events.values() if e["kind"] == "note" and e["timing_supported"])
    bound = {}
    for event in generated.events.values():
        if event["kind"] == "note" and event["timing_supported"]:
            record, _ = feature_record(event, measurements, identities)
            if record is not None:
                bound[event["_pixel_id"]] = (event, record)
    durations = {"whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
                 **{kind: Fraction(1, 2**count) for kind, count in FLAG_COUNTS.items()}}
    for event in ratio_events:
        path, match = event["xml_ordinal"], matched.get(event["xml_ordinal"])
        if event["kind"] != "note":
            continue
        rhythm = next(r for r in by_event[path] if r["construct"] == "note_rhythm")
        rhythm.update(status="unverified", reason="Rhythm requires a complete source group, bound ratio semantics and every actual graphic")
        evidence = proven.get(path)
        if evidence is None or match is None:
            continue
        requirements = [r for r in by_event[path] if r["construct"] in {"pitch", "stem", "flag", "dot", "beam", "tuplet"}]
        if (not any(r["construct"] in {"stem", "flag", "dot", "beam"} for r in requirements) or
                any(r["status"] != "verified" for r in requirements)):
            continue
        base, ratio = durations.get(event["note_type"]), event["_ratio"]
        value = base*(2-Fraction(1, 2**event["dots"]))*Fraction(ratio[1], ratio[0]) if base is not None and ratio else None
        if value != event["_duration"] or value != match["_duration"]:
            continue
        graphics = dict(requirements=[r["id"] for r in requirements if r.get("scope") != "semantic"])
        if event["note_type"] == "quarter":
            record, _ = feature_record(match, measurements, identities)
            if note_feature_status("flag_absence", event, match, record, bound)[0] != "verified":
                continue
            graphics["flag_absence"] = record["features"]["flag_absence"]
        rhythm.update(status="verified", reason="Exact chosen ratio arithmetic, bound native semantics and all required graphics verified",
                      evidence=dict(expected_duration=str(value), semantics=evidence, **graphics))
