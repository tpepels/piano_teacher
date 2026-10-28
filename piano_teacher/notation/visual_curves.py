"""Accept unique source-bound tie/slur endpoints and exclusive connected runs.

Independent pairing and current-frame checks prevent one physical curve
from certifying distinct source pairs."""
from __future__ import annotations

from collections import Counter, defaultdict
from math import isfinite
from .visual_contract import STATUSES, capture_frame_clock, valid_box


def _connector_pairs(inventory):
    """Pair explicit inventory endpoints without trusting an incoming report."""
    declarations = defaultdict(list)
    for row in inventory.elements:
        if row["construct"] in {"tie", "slur"}:
            declarations[row["source"].get("xml_ordinal")].append(row)
    opened, pairs = {}, []
    for path, event in inventory.events.items():
        if event["kind"] != "note" or not event["timing_supported"]:
            continue
        rows = declarations[path]
        # At a chain's middle note the incoming pair closes before the next
        # outgoing pair opens, regardless of XML child order.
        for row in sorted(rows, key=lambda r: r["source"]["details"]["attributes"].get("type") != "stop"):
            attrs = row["source"]["details"]["attributes"]
            kind, number = row["construct"], attrs.get("number", "1")
            role = attrs.get("type")
            if role not in {"start", "stop"} or not isinstance(number, str) or not number:
                continue
            key = (kind, event["part_index"], number)
            if kind == "tie":
                key += (event["staff"], event["voice"], tuple(event["spelling"]))
            if role == "start":
                # Keep duplicate starts poisoned until their matching stop.
                opened[key] = (event, row) if key not in opened else None
                continue
            start = opened.pop(key, None)
            if start is None:
                continue
            a, first = start
            marks = [first["source"]["details"]["attributes"], attrs]
            if (event["_clock"] <= a["_clock"] or
                    (kind == "tie" and a["_clock"]+a["_duration"] != event["_clock"]) or
                    any(m.get("line-type", "solid") != "solid" or
                        m.get("print-object") == "no" or
                        m.get("placement") not in (None, "above", "below") for m in marks)):
                continue
            # Repeated stop declarations must not let the first one pass.
            if sum(r["construct"] == kind and
                   r["source"]["details"]["attributes"].get("type") == "stop" and
                   r["source"]["details"]["attributes"].get("number", "1") == number for r in rows) != 1:
                continue
            pairs.append(dict(construct=kind, number=number, events=[a, event],
                              rows=[first, row], placements=[m.get("placement") for m in marks]))
    return pairs


def _connector_runs(evidence):
    """Check exact, eight-connected observed curve runs, without image dependencies."""
    runs = evidence.get("pixel_runs")
    box = evidence.get("component_bbox")
    count = evidence.get("connected_pixels")
    if (not valid_box(box) or not all(type(v) is int and v >= 0 for v in box) or
            type(count) is not int or count <= 0 or not isinstance(runs, list) or not runs):
        return None
    if any(not isinstance(r, (list, tuple)) or len(r) != 3 or
           any(type(v) is not int or v < 0 for v in r) or r[1] >= r[2] for r in runs):
        return None
    ordered = sorted(map(tuple, runs))
    if (sum(b-a for y, a, b in ordered) != count or
            [min(a for y, a, b in ordered), ordered[0][0],
             max(b for y, a, b in ordered), ordered[-1][0]+1] != list(box)):
        return None
    parents = list(range(len(ordered)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    previous, current, last_y = [], [], None
    for i, (y, a, b) in enumerate(ordered):
        if y != last_y:
            previous = current if last_y is not None and y == last_y+1 else []
            current, last_y = [], y
        if current and a <= ordered[current[-1]][2]:
            return None  # Duplicate/overlapping or non-maximal same-row runs.
        for j in previous:
            _, left, right = ordered[j]
            if a <= right and left <= b:
                parents[root(i)] = root(j)
        current.append(i)
    return ordered if len({root(i) for i in range(len(ordered))}) == 1 else None


def _connector_measurement(row, events, placements):
    """Validate the producer's endpoint, motion and thin-curve measurements."""
    evidence = row.get("evidence")
    if not isinstance(evidence, dict):
        return None
    heads, correspondence = evidence.get("heads"), evidence.get("correspondence")
    if not isinstance(heads, list) or len(heads) != 2 or not isinstance(correspondence, list) or len(correspondence) != 2:
        return None
    numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v)
    for head, event in zip(heads, events):
        if (not isinstance(head, dict) or head.get("source_id") != event["_pixel_id"] or
                not valid_box(head.get("bbox")) or
                not all(type(v) is int and v >= 0 for v in head["bbox"]) or
                not all(numeric(head.get(k)) for k in ("x", "y", "gap", "contour_score")) or
                head["gap"] <= 0 or not .79 <= head["contour_score"] <= 1 or
                not head["bbox"][0] <= head["x"] < head["bbox"][2] or
                not head["bbox"][1] <= head["y"] < head["bbox"][3]):
            return None
    gap = min(h["gap"] for h in heads)
    if events[0]["staff"] != events[1]["staff"] or heads[1]["x"]-heads[0]["x"] < 1.5*gap:
        return None
    frame = evidence.get("frame")
    clock = capture_frame_clock(frame)
    if (clock is None or
            not events[0]["beat"]-.00001 <= clock <= events[1]["beat"]+.00001):
        return None
    for motion, event in zip(correspondence, events):
        if not isinstance(motion, dict):
            return None
        onset = capture_frame_clock(motion.get("onset_frame"))
        if (onset is None or abs(onset-event["beat"]) > .0000051 or
                type(motion.get("shift")) is not int or
                not numeric(motion.get("contour_agreement")) or not .8 <= motion["contour_agreement"] <= 1 or
                (clock == onset and (motion["shift"] != 0 or motion["contour_agreement"] != 1))):
            return None
    distances = evidence.get("endpoint_distances_spaces")
    if (not numeric(evidence.get("curvature_spaces")) or evidence["curvature_spaces"] < .16 or
            not numeric(evidence.get("max_thickness_spaces")) or not 0 < evidence["max_thickness_spaces"] <= .8 or
            not isinstance(distances, list) or len(distances) != 2 or
            not all(numeric(d) and 0 <= d <= .9 for d in distances)):
        return None
    runs = _connector_runs(evidence)
    if runs is None:
        return None
    # Respect authored above/below placement even if generated XML omitted it.
    ranks, total, middle = ((evidence["connected_pixels"]-1)//2, evidence["connected_pixels"]//2), 0, []
    for y, a, b in runs:
        middle.extend(y for rank in ranks if total <= rank < total+b-a)
        total += b-a
    median = sum(middle)/2
    if any((p == "above" and median >= min(h["y"] for h in heads)) or
           (p == "below" and median <= max(h["y"] for h in heads)) for p in placements):
        return None
    return runs


def apply_connectors(output, original, matched, generated, report):
    """Credit both declarations of a unique original-to-generated source pair."""
    obligations = {r["id"]: r for r in output if r["construct"] in {"tie", "slur"}}
    for row in obligations.values():
        row.update(status="unverified", reason="No unique bound connector observation")
    observations = report.get("observations", []) if isinstance(report, dict) else []
    if not isinstance(observations, list):
        return
    generated_pairs = defaultdict(list)
    for pair in _connector_pairs(generated):
        generated_pairs[(pair["construct"], pair["number"], *(e["xml_ordinal"] for e in pair["events"]))].append(pair)
    original_ids = Counter(e["_pixel_id"] for e in original.events.values() if e["kind"] == "note")
    generated_ids = Counter(e["_pixel_id"] for e in generated.events.values() if e["kind"] == "note")
    candidates = []
    for pair in _connector_pairs(original):
        if not all(r["id"] in obligations for r in pair["rows"]):
            continue  # A clipped source-window boundary has no complete pair witness.
        events = [matched.get(e["xml_ordinal"]) for e in pair["events"]]
        if (any(e is None for e in events) or
                any(original_ids[e["_pixel_id"]] != 1 for e in pair["events"]) or
                any(generated_ids[e["_pixel_id"]] != 1 for e in events)):
            continue
        key = (pair["construct"], pair["number"], *(e["xml_ordinal"] for e in events))
        if len(generated_pairs[key]) != 1:
            continue
        source_ids = [e["_pixel_id"] for e in events]
        oracle_ids = [e["_oracle_id"] for e in events]
        records = [r for r in observations if isinstance(r, dict) and
                   r.get("construct") == pair["construct"] and r.get("number") == pair["number"] and
                   (r.get("source_ids") == source_ids or r.get("oracle_source_ids") == oracle_ids)]
        if len(records) != 1:
            continue
        observation = records[0]
        if observation.get("source_ids") != source_ids or observation.get("oracle_source_ids") != oracle_ids:
            continue
        status = observation.get("status")
        if status not in STATUSES or not isinstance(observation.get("evidence"), dict):
            continue
        runs = None
        if status == "verified":
            runs = _connector_measurement(observation, events, pair["placements"])
            if runs is None:
                continue
        evidence = dict(original_source_ids=[e["id"] for e in pair["events"]],
                        generated_source_ids=source_ids, oracle_source_ids=oracle_ids, pixel=observation)
        candidates.append((pair, observation, status, evidence, runs))
    conflicted = set()
    for i, (_, observation, status, _, runs) in enumerate(candidates):
        if status != "verified":
            continue
        for j, (_, other, other_status, _, other_runs) in enumerate(candidates[:i]):
            if other_status == "verified" and observation["evidence"]["frame"] == other["evidence"]["frame"]:
                if any(y == yy and a < bb and aa < b for y, a, b in runs for yy, aa, bb in other_runs):
                    conflicted.update((i, j))
    for i, (pair, observation, status, evidence, _) in enumerate(candidates):
        if i in conflicted:
            status = "unverified"
        reason = ("Curve ink is shared by distinct source pairs" if i in conflicted else
                  "Independent bound source-pair head and connected-curve evidence" if status == "verified" else
                  observation.get("evidence", {}).get("reason", "Independent connector remains unverified"))
        for endpoint in pair["rows"]:
            obligations[endpoint["id"]].update(status=status, reason=reason, evidence=evidence)
