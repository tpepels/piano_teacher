"""Accept complete ordered beam/tuplet groups and every graphical witness.

Source identity, anchors, beam levels, numeral/bracket requirements and
exact duration arithmetic retain separate acceptance conditions."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from math import ceil, floor, isfinite
from .proof import read_written_score
from .visual_contract import FLAG_COUNTS, capture_frame_clock, finite_score, source_beat, valid_box


def _group_members(record, inventory):
    """Bind the full ordered interval, including source-declared chord members."""
    identifiers = record.get("source_ids")
    if (not isinstance(identifiers, list) or not identifiers or
            any(not isinstance(s, str) for s in identifiers) or len(set(identifiers)) != len(identifiers)):
        return None
    by_id = {e["_oracle_id"]: e for e in inventory.events.values() if e["timing_supported"]}
    if any(s not in by_id for s in identifiers):
        return None
    events = [by_id[s] for s in identifiers]
    canonical = [e["xml_id"] or e["_oracle_id"] for e in events]
    counts = Counter(e["xml_id"] or e["_oracle_id"] for e in inventory.events.values())
    if record.get("event_ids") != canonical or any(counts[s] != 1 for s in canonical):
        return None
    a, b = events[0], events[-1]
    lane = lambda e: (e["part_index"], e["measure_index"], e["staff"], e["voice"])
    full = [e for e in inventory.events.values() if e["timing_supported"] and lane(e) == lane(a)
            and a["_clock"] <= e["_clock"] <= b["_clock"]]
    if events != full:
        return None
    return events


def _group_anchors(evidence, events):
    anchors, lines, gap = (evidence.get(k) for k in ("anchors", "staff_lines", "staff_gap"))
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
    frame = evidence.get("frame")
    clock = capture_frame_clock(frame)
    if clock is None:
        return False
    if (not valid_box(evidence.get("bbox")) or not numeric(gap) or gap <= 0 or
            not isinstance(lines, list) or len(lines) != 5 or not all(numeric(y) for y in lines) or
            any(a >= b for a, b in zip(lines, lines[1:])) or
            abs((lines[-1]-lines[0])/4-gap) > .0001 or
            not isinstance(anchors, list) or len(anchors) != len(events)):
        return False
    for anchor, event in zip(anchors, events):
        if (not isinstance(anchor, dict) or anchor.get("source_id") != event["_oracle_id"] or
                not valid_box(anchor.get("bbox")) or
                not all(numeric(anchor.get(k)) for k in ("x", "y", "gap", "head_match")) or
                abs(anchor["gap"]-gap) > .0001 or not .79 <= anchor["head_match"] <= 1):
            return False
        registration = anchor.get("registration")
        if (not isinstance(registration, dict) or type(registration.get("pixels")) is not int or
                not finite_score(registration.get("agreement")) or registration["agreement"] < .8 or
                not finite_score(registration.get("margin")) or registration["margin"] < .04):
            return False
        if abs(clock-event["beat"]) <= .0000051 and registration != dict(pixels=0, agreement=1., margin=1.):
            return False
    return True


def _beam_measurement(evidence, events, facts):
    anchors, stems, samples = (evidence.get(k) for k in ("anchors", "stems", "samples"))
    leaders = [i for i, e in enumerate(events) if not e["_chord"]]
    if (len(leaders) < 2 or not isinstance(stems, list) or len(stems) != len(leaders) or
            type(evidence.get("stem_up")) is not bool or not isinstance(samples, list) or not samples or
            type(evidence.get("continuity_columns")) is not int):
        return False
    up, gap = evidence["stem_up"], evidence["staff_gap"]
    for j, i in enumerate(leaders):
        chord = anchors[i:leaders[j+1] if j+1 < len(leaders) else len(events)]
        stem = stems[j]
        if (not isinstance(stem, dict) or not valid_box(stem.get("bbox")) or
                not all(isinstance(stem.get(k), (int, float)) and not isinstance(stem[k], bool) and
                        isfinite(stem[k]) for k in ("x", "top", "bottom")) or
                stem["bbox"][1] != stem["top"] or stem["bbox"][3] != stem["bottom"] or
                not stem["bbox"][0] <= stem["x"] < stem["bbox"][2] or
                any(e["_stem"] not in (None, "up" if up else "down") for e in events[i:leaders[j+1] if j+1 < len(leaders) else len(events)])):
            return False
        high, low = min(a["y"] for a in chord), max(a["y"] for a in chord)
        center = (max(chord, key=lambda a: a["y"]) if up else min(chord, key=lambda a: a["y"]))["x"]
        left, right = (center+.3*gap, center+.9*gap) if up else (center-.9*gap, center-.3*gap)
        if not floor(left) <= stem["x"] <= ceil(right):
            return False
        if up:
            valid = stem["top"] <= high-1.25*gap and low-.3*gap <= stem["bottom"] <= low+.5*gap
        else:
            valid = stem["bottom"] >= low+1.25*gap and high-.5*gap <= stem["top"] <= high+.3*gap
        if not valid:
            return False
    wanted_x, continuity = [], 0
    intervals = []
    for j, (a, b) in enumerate(zip(stems, stems[1:])):
        if b["x"]-a["x"] < 1.3*gap:
            return False
        xs = list(range(ceil(a["x"]+.15*gap), floor(b["x"]-.15*gap)+1))
        wanted_x.extend(xs)
        continuity += floor(b["x"])-ceil(a["x"])+1
        left, right = facts[leaders[j]], facts[leaders[j+1]]
        minimum = 1
        # Full secondary levels cannot disappear into a primary-only report.
        for level in range(2, min(FLAG_COUNTS[left["note_type"]], FLAG_COUNTS[right["note_type"]])+1):
            lm = {int(n): value for n, value, _ in left["beams"]}
            rm = {int(n): value for n, value, _ in right["beams"]}
            if (not lm and not rm) or (lm.get(level) in {"begin", "continue"} and rm.get(level) in {"continue", "end"}):
                minimum = level
        intervals.extend((x, minimum, max(FLAG_COUNTS[left["note_type"]], FLAG_COUNTS[right["note_type"]])) for x in xs)
    if [s.get("x") if isinstance(s, dict) else None for s in samples] != wanted_x or evidence["continuity_columns"] != continuity:
        return False
    for sample, (_, minimum, maximum) in zip(samples, intervals):
        thickness = sample.get("thickness_spaces")
        if (type(sample.get("levels")) is not int or not minimum <= sample["levels"] <= maximum or
                not isinstance(thickness, list) or len(thickness) != sample["levels"] or
                not all(isinstance(t, (int, float)) and not isinstance(t, bool) and isfinite(t) and t > 0 for t in thickness)):
            return False
    return True


def _tuplet_identity(facts):
    ratios = {f["time_modification"] for f in facts}
    if len(ratios) != 1 or None in ratios:
        return None
    starts = [m for m in facts[0]["tuplet_marks"] if m[0] == "start"]
    stops = [m for m in facts[-1]["tuplet_marks"] if m[0] == "stop"]
    if len(starts) != 1 or len(stops) != 1 or starts[0][1] != stops[0][1]:
        return None
    mark = starts[0]
    if mark[2:] == ("no", "none") or mark[3] == "none":
        return None
    if any(f["tuplet_marks"] for f in facts[1:-1]):
        return None  # Nested/continuing graphics need distinct group identities.
    actual, normal = next(iter(ratios))
    return str(actual)+(f":{normal}" if mark[3] == "both" else ""), mark[2] == "yes", mark[1]


def _tuplet_measurement(evidence, identity):
    text, bracket, source_number = identity
    digits = evidence.get("digits")
    codes = [f"E{0x880+int(c):03X}" if c.isdigit() else "E88A" for c in text]
    if (evidence.get("expected_numeral") != text or not valid_box(evidence.get("number_bbox")) or
            not finite_score(evidence.get("numeral_match")) or evidence["numeral_match"] < .79 or
            not finite_score(evidence.get("numeral_margin")) or evidence["numeral_margin"] < .05 or
            not isinstance(digits, list) or len(digits) != len(codes)):
        return False
    for digit, code in zip(digits, codes):
        if (not isinstance(digit, dict) or digit.get("code") != code or not valid_box(digit.get("bbox")) or
                not finite_score(digit.get("match")) or digit["match"] < .79 or
                not finite_score(digit.get("runner_up")) or
                not finite_score(digit.get("margin")) or digit["margin"] < .03 or
                abs(digit["match"]-digit["runner_up"]-digit["margin"]) > .0002):
            return False
    if any(a["bbox"][2] > b["bbox"][0] for a, b in zip(digits, digits[1:])):
        return False
    return not (bracket or "bracket_bbox" in evidence) or (
        valid_box(evidence.get("bracket_bbox")) and finite_score(evidence.get("bracket_match")) and evidence["bracket_match"] >= .72)


def apply_group_connectors(output, original, matched, generated, original_xml, generated_xml, reports):
    """Consume graphical beam/tuplet groups, preserving semantic ratio rows."""
    try:
        source_facts = {f["source"]["id"]: f for f in read_written_score(original_xml or generated_xml, strict=False).symbols}
        generated_facts = {f["source"]["id"]: f for f in read_written_score(generated_xml, strict=False).symbols}
    except (ValueError, TypeError, KeyError):
        return
    inverse = {e["xml_ordinal"]: original.events[path] for path, e in matched.items()}
    by_event = defaultdict(list)
    for row in output:
        by_event[row["source"].get("xml_ordinal")].append(row)
    proven = defaultdict(dict)
    for kind, report in reports.items():
        if report is None:
            continue
        records = report.get("measured", []) if isinstance(report, dict) else []
        if not isinstance(records, list):
            continue
        for row in output:
            attrs = row["source"].get("details", {}).get("attributes", {})
            if row["construct"] == kind and row.get("scope") != "semantic" and (kind == "beam" or attrs.get("type") in {"start", "stop"}):
                row.update(status="unverified", reason="No unique bound graphical connector group")
        for record in records:
            if (not isinstance(record, dict) or record.get("construct") != kind or
                    record.get("graphical") is not True or record.get("status") != "verified"):
                continue
            events = _group_members(record, generated)
            if events is None or any(e["xml_ordinal"] not in inverse for e in events):
                continue
            beat = record.get("beat")
            if (isinstance(record.get("measure"), bool) or record.get("measure") != events[0]["measure"] or
                    record.get("staff") != events[0]["staff"] or record.get("voice") != events[0]["voice"] or
                    not isinstance(beat, (int, float)) or isinstance(beat, bool) or not isfinite(beat) or
                    source_beat(beat) != events[0]["beat"] or
                    not isinstance(record.get("reference_group"), str) or not record["reference_group"]):
                continue
            originals = [inverse[e["xml_ordinal"]] for e in events]
            original_record = dict(source_ids=[e["_oracle_id"] for e in originals],
                                   event_ids=[e["xml_id"] or e["_oracle_id"] for e in originals])
            if _group_members(original_record, original) != originals:
                continue
            duplicates = [r for r in records if isinstance(r, dict) and r.get("construct") == kind and
                          (r.get("source_ids") == record["source_ids"] or r.get("event_ids") == record["event_ids"])]
            if len(duplicates) != 1:
                continue
            facts = [source_facts[e["_oracle_id"]] for e in originals]
            gfacts = [generated_facts[e["_oracle_id"]] for e in events]
            if any((a["note_type"], a["dots"], a["time_modification"]) !=
                   (b["note_type"], b["dots"], b["time_modification"]) for a, b in zip(facts, gfacts)):
                continue
            if kind == "beam":
                if (any(f["kind"] != "note" or f["note_type"] not in FLAG_COUNTS for f in facts) or
                        any(a["beams"] and a["beams"] != b["beams"] for a, b in zip(facts, gfacts))):
                    continue
                leaders = [f for f in facts if not f["chord"]]
                primary = [[value for number, value, _ in f["beams"] if number == "1"] for f in leaders]
                if any(primary) and primary != [["begin"], *[["continue"] for f in leaders[1:-1]], ["end"]]:
                    continue
                identity = None
            else:
                identity = _tuplet_identity(facts)
                if identity is None or identity != _tuplet_identity(gfacts):
                    continue
            evidence = record.get("evidence")
            witnesses = evidence.get("witnesses") if isinstance(evidence, dict) else None
            if not isinstance(witnesses, list) or not witnesses:
                continue
            valid = all(isinstance(w, dict) and w.get("status") == "verified" and
                        _group_anchors(w, events) and
                        (_beam_measurement(w, originals, facts) if kind == "beam" else _tuplet_measurement(w, identity))
                        for w in witnesses)
            if not valid or any(evidence.get(k) != v for k, v in witnesses[0].items() if k not in {"status", "reason"}):
                continue
            for event in originals:
                path = event["xml_ordinal"]
                if path in proven[kind]:
                    proven[kind][path] = None  # More than one group cannot choose an owner.
                else:
                    proven[kind][path] = record
    for kind, events in proven.items():
        for path, record in events.items():
            if record is None:
                continue
            for row in by_event[path]:
                attrs = row["source"].get("details", {}).get("attributes", {})
                if (row["construct"] == kind and row.get("scope") != "semantic" and (kind == "beam" or attrs.get("type") in {"start", "stop"}) or
                        kind == "beam" and row["construct"] == "stem"):
                    row.update(status="verified", reason="Independent graphical group bound to every original/generated source event", evidence=record)
    # A beam supplies measured stems; a graphical tuplet supplies the ratio's
    # printed witness. Arithmetic and all other feature obligations still apply.
    for path, obligations in by_event.items():
        event, match = original.events.get(path), matched.get(path)
        if not event or not match or event["kind"] != "note" or event["note_type"] not in FLAG_COUNTS:
            continue
        beam, tuplet = proven["beam"].get(path), proven["tuplet"].get(path)
        if not beam and not tuplet:
            continue
        fact = source_facts[event["_oracle_id"]]
        ratio = fact["time_modification"]
        if (fact["beams"] and not beam) or (ratio and not tuplet):
            continue
        requirements = [r for r in obligations if r["construct"] in {"pitch", "stem", "flag", "dot", "beam"}]
        if not requirements or any(r["status"] != "verified" for r in requirements):
            continue
        value = Fraction(1, 2**FLAG_COUNTS[event["note_type"]])*(2-Fraction(1, 2**event["dots"]))
        if ratio:
            value *= Fraction(ratio[1], ratio[0])
        if value != event["_duration"] or value != match["_duration"]:
            continue
        rhythm = next(r for r in obligations if r["construct"] == "note_rhythm")
        rhythm.update(status="verified", reason="Bound graphical connectors, required features and exact source duration verified",
                      evidence=dict(beam=beam, tuplet=tuplet, expected_duration=str(value)))
