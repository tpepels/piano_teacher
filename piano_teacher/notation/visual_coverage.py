"""Fail-closed visual ledger rooted in original, independently read MusicXML.

Only bound raster pitch, rest-contour, note-feature and connector records verify rows.
XML agreement supplies correspondence, never visual proof. In particular a
head silhouette does not verify a stem, flag, duration, dot, or connector.
This module has no image, renderer, or native-model dependencies.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
import json
from math import isfinite, ceil, floor
from xml.etree import ElementTree as ET

from .proof import _hand, read_written_score


STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
_FLAG_TYPES = {"eighth", "16th", "32nd", "64th", "128th", "256th", "512th", "1024th"}
_NOTE_DATA = {"pitch", "unpitched", "rest", "duration", "voice", "type", "staff",
              "chord", "grace", "cue", "stem", "dot", "beam", "tie", "notations",
              "accidental", "time-modification"}
_CONTAINERS = {"notations", "articulations", "ornaments", "technical", "direction-type"}

_FEATURES = {"stem", "flag", "dot", "accidental"}
_ACCIDENTAL_GLYPHS = {"flat": "acc_flat", "natural": "acc_natural", "sharp": "acc_sharp",
                      "double-flat": "acc_double_flat", "flat-flat": "acc_double_flat",
                      "double-sharp": "acc_double_sharp"}
_FLAG_COUNTS = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4, "128th": 5}


@dataclass
class _Inventory:
    elements: list[dict]
    events: dict[str, dict]
    bars: tuple
    measure_count: int
    reader_error: str | None = None
    logical_symbols: tuple = ()


def _number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _beat(value):
    return round(float(value), 8) if value is not None else None


def _visible(node):
    return node.get("print-object") != "no"


def _written_accidentals(written):
    """Keep implicit cancellations and alterations in the source denominator."""
    state, required = {}, {}
    for note in written.symbols if written else ():
        if note["kind"] != "note":
            continue
        keys = [(at, fifths) for at, staff, fifths in written.keys
                if staff == note["staff"] and at <= note["index"]]
        fifths = max(keys, key=lambda row: row[0])[1] if keys else 0
        signature = {step: 1 if fifths > 0 else -1
                     for step in ("FCGDAEB" if fifths > 0 else "BEADGCF")[:abs(fifths)]}
        step, alter, octave = note["spelling"]
        accidentals = state.setdefault((note["part_index"], note["index"], note["staff"]), {})
        previous = accidentals.get((step, octave), signature.get(step, 0))
        mark = note["accidental"]
        if mark is None and not note["tie_stop"] and alter != previous:
            mark = {-2: "double-flat", -1: "flat", 0: "natural", 1: "sharp", 2: "double-sharp"}.get(alter, f"alteration-{alter}")
        required[note["source"]["id"]] = mark
        accidentals[step, octave] = alter
    return required


def _ledger_requirement(written, note):
    """Source staff steps from conventional G4/F3/C4 clef references."""
    clefs = []
    for measure in written.measures:
        if measure["index"] > note["index"] or measure["source"]["part_index"] != note["part_index"]:
            continue
        for mark in measure["metadata"]:
            if mark["kind"] != "clef" or mark["staff"] != note["raw_staff"]:
                continue
            if measure["index"] == note["index"] and float(mark["onset"]) > float(note["onset"]):
                continue
            clefs.append((measure["index"], float(mark["onset"]), mark["value"]))
    if not clefs:
        return [], None, "No explicit source clef for ledger expectations"
    sign, line, octave_change = max(clefs, key=lambda c: c[:2])[2]
    anchors = {"G": ("G", 4), "F": ("F", 3), "C": ("C", 4)}
    if sign not in anchors or not 1 <= line <= 5 or not -2 <= octave_change <= 2:
        return [], None, "Unsupported source clef for ledger expectations"
    letter, octave = anchors[sign]
    reference = 7*(octave+octave_change)+"CDEFGAB".index(letter)
    step, _alter, octave = note["spelling"]
    staff_step = 7*octave+"CDEFGAB".index(step)-reference+2*(line-1)
    steps = list(range(-2, staff_step-1, -2) if staff_step < 0 else range(10, staff_step+1, 2))
    changing = any(m["kind"] == "clef" and float(m["onset"]) > 0
                   for measure in written.measures if measure["index"] == note["index"] and
                   measure["source"]["part_index"] == note["part_index"] for m in measure["metadata"])
    return steps, staff_step, "Mid-measure clef changes require time-resolved ledger proof" if changing else None


def _source_tuplet_groups(inventory):
    """Complete explicit boundaries and every intervening source member."""
    lanes = defaultdict(list)
    for event in inventory.events.values():
        if event["timing_supported"]:
            lanes[event["part_index"], event.get("_raw_staff"), event["voice"]].append(event)
    groups = []
    for members in lanes.values():
        members.sort(key=lambda e: e["_clock"])
        opened = {}
        for i, event in enumerate(members):
            for mark in event.get("_tuplet_declarations", []):
                number, role = mark.get("number", "1"), mark.get("type")
                if role == "start":
                    opened[number] = (i, mark) if number not in opened else None
                elif role == "stop":
                    start = opened.pop(number, None)
                    if start is None:
                        continue
                    first, a = start
                    events = members[first:i+1]
                    marks = [m for e in events for m in e.get("_tuplet_declarations", [])]
                    ratios = {e.get("_ratio") for e in events}
                    if (len(marks) != 2 or len(ratios) != 1 or None in ratios or
                            any(m.get("print-object") == "no" for m in marks)):
                        continue
                    # Visual inventory deliberately omits nonprinting notes.
                    # They must not disappear from semantic group ownership.
                    first_event, last_event = events[0], events[-1]
                    logical = [n["source"]["id"] for n in inventory.logical_symbols
                               if n["part_index"]+1 == first_event["part_index"] and
                               n["raw_staff"] == first_event["_raw_staff"] and n["voice"] == first_event["voice"] and
                               first_event["_clock"] <= n["beat"] <= last_event["_clock"]]
                    if logical != [e["_oracle_id"] for e in events]:
                        continue
                    ratio = next(iter(ratios))
                    if any(type(n) is not int or n <= 0 for n in ratio):
                        continue
                    hidden = (a.get("bracket") == "no" and a.get("show-number") == "none" and
                              mark.get("bracket", "no") == "no" and mark.get("show-number", "none") == "none")
                    groups.append(dict(events=events, number=number, ratio=ratio, hidden=hidden))
    counts = Counter(e["xml_ordinal"] for group in groups for e in group["events"])
    return [g for g in groups if all(counts[e["xml_ordinal"]] == 1 for e in g["events"])]


def _scope_tuplet_rows(inventory):
    hidden = {e["xml_ordinal"] for g in _source_tuplet_groups(inventory) if g["hidden"] for e in g["events"]}
    for row in inventory.elements:
        if row["construct"] != "tuplet":
            continue
        metadata = "/time-modification" in row["id"] or row["source"].get("xml_ordinal") in hidden
        row["scope"] = "semantic" if metadata else "visual"


def _read(xml: str, hand: str, origin: str, source_name: str = "") -> _Inventory:
    if hand not in ("both", "left", "right"):
        raise ValueError("Invalid hand mode")
    root = ET.fromstring(xml)
    # MusicXML is commonly namespaced. The independent oracle accepts local tags.
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if root.tag != "score-partwise":
        raise ValueError("Visual inventory requires score-partwise MusicXML")
    parts = root.findall("part")
    if not parts:
        raise ValueError("No MusicXML parts")
    issue = None
    try:
        written = read_written_score(ET.tostring(root, encoding="unicode"), strict=False)
    except (ValueError, TypeError, KeyError) as exc:
        # Preserve all explicit constructs even when the timing oracle cannot
        # interpret the score. Such events cannot acquire verified pitch status.
        written = None
        issue = str(exc)
    facts = iter(written.symbols if written else ())
    accidentals = _written_accidentals(written)
    names = {p.get("id"): p.findtext("part-name", "")
             for p in root.findall("./part-list/score-part")}
    elements, events = [], {}

    def emit(construct, source, path, **details):
        row_source = dict(source)
        if details:
            row_source["details"] = details
        identity = f"{origin}:{path}:{construct}"
        elements.append(dict(id=identity, construct=construct, status="unsupported",
                             source=row_source,
                             reason=f"No independent pixel detector for {construct}"))

    def leaves(node, source, path):
        for i, child in enumerate(node, 1):
            if not _visible(child):
                continue
            child_path = f"{path}/{child.tag}{i}"
            if child.tag in _CONTAINERS:
                leaves(child, source, child_path)
            else:
                construct = {"tied": "tie", "time": "meter",
                             "time-modification": "tuplet"}.get(child.tag, child.tag)
                emit(construct, source, child_path, text=(child.text or "").strip(),
                     attributes=dict(child.attrib), xml=ET.tostring(child, encoding="unicode"))

    for pi, part in enumerate(parts, 1):
        pid = part.get("id", "")
        part_name = names.get(pid, "")
        for mi, measure in enumerate(part.findall("measure"), 1):
            mp = f"p{pi}/m{mi}"
            base = dict(id=measure.get("id") or mp,
                        measure=_number(measure.get("number", str(mi))),
                        measure_index=mi, part=pid, part_index=pi,
                        staff="both", voice=None,
                        beat=written.bars[mi-1] if written else None, origin=origin)
            if source_name:
                base["source_name"] = source_name
            emit("measure", base, mp)
            if not any(b.get("location", "right") == "right" for b in measure.findall("barline")):
                emit("barline", base, mp + "/implicit-right", implicit=True)
            ni = 0
            for ei, node in enumerate(measure, 1):
                path = f"{mp}/{node.tag}{ei}"
                if node.tag == "note":
                    ni += 1
                    path = f"{mp}/n{ni}"
                    grace = node.find("grace") is not None
                    timed = not grace and node.find("unpitched") is None
                    fact = next(facts, None) if written and timed else None
                    staff = _hand(pid, part_name, pi-1, node.findtext("staff", "1"))
                    if not _visible(node) or (hand != "both" and staff != hand):
                        continue
                    source = dict(base, id=node.get("id") or path, staff=staff,
                                  voice=node.findtext("voice", "1"), xml_ordinal=path)
                    pitch = node.find("pitch")
                    spelling = ([pitch.findtext("step"), _number(pitch.findtext("alter", "0")),
                                 _number(pitch.findtext("octave"))] if pitch is not None else None)
                    if fact is not None and fact["spelling"] is not None:
                        spelling = list(fact["spelling"])
                    kind = "rest" if node.find("rest") is not None else "note"
                    source.update(beat=_beat(fact["beat"]) if fact else None,
                                  duration=_beat(fact["duration"]) if fact else None,
                                  spelling=spelling, note_type=node.findtext("type"),
                                  dots=len(node.findall("dot")), grace=grace)
                    event = dict(source, kind=kind, xml_id=node.get("id"),
                                 timing_supported=fact is not None,
                                 _clock=fact["beat"] if fact else None,
                                 _duration=fact["duration"] if fact else None,
                                 _pixel_id=(fact["id"] or fact["source"]["id"]) if fact else None,
                                 _oracle_id=fact["source"]["id"] if fact else None,
                                 _raw_staff=fact["raw_staff"] if fact else None,
                                 _ratio=fact["time_modification"] if fact else None,
                                 _tuplet_declarations=[dict(t.attrib) for t in node.findall("notations/tuplet")],
                                 _chord=bool(fact and fact["chord"]),
                                 _stem=node.findtext("stem"),
                                 _connectors=bool(node.findall("beam") or node.findall("time-modification")
                                                  or node.findall("notations/tuplet")),
                                 _accidental=accidentals.get(fact["source"]["id"]) if fact else None)
                    events[path] = event
                    construct = "rest" if kind == "rest" else "pitch" if pitch is not None else "unpitched"
                    emit(construct, source, path)
                    emit("rest_rhythm" if kind == "rest" else "note_rhythm", source, path)
                    if kind == "note" and fact is not None and spelling is not None:
                        steps, staff_step, error = _ledger_requirement(written, fact)
                        event.update(_ledger_steps=steps, _staff_step=staff_step, _ledger_error=error)
                        if steps or error:
                            emit("ledger", source, path, expected_steps=steps, error=error)
                    if kind == "rest":
                        emit("rest_placement", source, path)
                    else:
                        stem = node.findtext("stem")
                        if stem != "none" and (stem is not None or source["note_type"] not in {"whole", "breve", "long", "maxima"}):
                            emit("stem", source, path, direction=stem or "implicit")
                        if source["note_type"] in _FLAG_TYPES and not node.findall("beam") and stem != "none":
                            emit("flag", source, path, note_type=source["note_type"])
                    if (kind == "note" and node.find("accidental") is None
                            and event["_accidental"] is not None):
                        emit("accidental", source, path + "/implicit-accidental",
                             implicit=True, text=event["_accidental"])
                    for ci, child in enumerate(node, 1):
                        if not _visible(child):
                            continue
                        cp = f"{path}/{child.tag}{ci}"
                        if child.tag in {"beam", "dot", "accidental", "time-modification"}:
                            emit("tuplet" if child.tag == "time-modification" else child.tag,
                                 source, cp, text=(child.text or "").strip(), attributes=dict(child.attrib))
                        elif child.tag == "tie":
                            # <tie> is playback data; <tied> describes the same
                            # printed endpoint. Count it once when both occur.
                            if not any(t.get("type") == child.get("type") for t in node.findall("notations/tied")):
                                emit("tie", source, cp, attributes=dict(child.attrib))
                        elif child.tag == "notations":
                            leaves(child, source, cp)
                        elif child.tag not in _NOTE_DATA:
                            emit(child.tag, source, cp, xml=ET.tostring(child, encoding="unicode"))
                    continue
                if not _visible(node):
                    continue
                if node.tag == "attributes":
                    for ai, attribute in enumerate(node, 1):
                        if attribute.tag in {"divisions", "staves", "instruments"} or not _visible(attribute):
                            continue
                        attr_staff = (_hand(pid, part_name, pi-1, attribute.get("number", "1"))
                                      if attribute.tag in {"clef", "key", "staff-details", "transpose"} else "both")
                        if hand != "both" and attr_staff not in ("both", hand):
                            continue
                        ap = f"{path}/{attribute.tag}{ai}"
                        source = dict(base, id=attribute.get("id") or ap, staff=attr_staff)
                        emit("meter" if attribute.tag == "time" else attribute.tag,
                             source, ap, xml=ET.tostring(attribute, encoding="unicode"))
                elif node.tag in {"direction", "harmony", "figured-bass", "barline", "print"}:
                    staff = (_hand(pid, part_name, pi-1, node.findtext("staff", "1"))
                             if node.tag != "barline" else "both")
                    if hand != "both" and staff not in (hand, "both"):
                        continue
                    source = dict(base, id=node.get("id") or path, staff=staff)
                    if node.tag == "direction":
                        for di, direction in enumerate(node.findall("direction-type"), 1):
                            leaves(direction, source, f"{path}/direction-type{di}")
                    elif node.tag != "print":
                        emit(node.tag, source, path, xml=ET.tostring(node, encoding="unicode"))
                elif node.tag not in {"backup", "forward", "sound"}:
                    emit(node.tag, dict(base, id=node.get("id") or path), path,
                         xml=ET.tostring(node, encoding="unicode"))
    if issue:
        emit("musicxml_inventory", dict(id="independent-reader", measure=1, measure_index=1, staff="both",
                                        origin=origin), "reader-limitation", error=issue)
    count = max(len(part.findall("measure")) for part in parts)
    boundaries = list(written.bars) if written else []
    if written:
        # The oracle exposes rounded public bar clocks, but raw symbol clocks
        # remain Fraction. Recover exact starts before subtracting a window:
        # round(2/3, 8) - round(1/3, 8) differs from round(1/3, 8).
        for symbol in written.symbols:
            boundaries[symbol["index"]] = symbol["beat"] - symbol["onset"]
    # Reconstruct only declared source chords; simultaneous voices cannot
    # borrow a shared physical stem by claiming the same onset.
    groups, previous = [], None
    notes = [e for e in events.values() if e["kind"] == "note" and e["timing_supported"]]
    for event in sorted(notes, key=lambda e: e["_clock"]):
        key = (event["part_index"], event["measure_index"], event["staff"], event["voice"], event["_clock"])
        if event["_chord"] and previous == key:
            groups[-1].append(event)
        else:
            groups.append([event])
        previous = key
    for group in groups:
        for event in group:
            event["_group_id"] = group[0]["_oracle_id"]
            event["_group_members"] = [e["_pixel_id"] for e in group]
    for index, event in enumerate(e for e in events.values() if e["kind"] == "rest"):
        event["_pixel_id"] = event["xml_id"] or f"measure-{event['measure']}-voice-{event['voice']}-rest-{index}"
    inventory = _Inventory(elements, events, tuple(boundaries), count, issue,
                           tuple(written.symbols) if written else ())
    _scope_tuplet_rows(inventory)
    return inventory


def source_inventory(original_xml: str | None, hand: str = "both", *,
                     source_name: str = "") -> list[dict]:
    """Canonical full-source projection for an independent aggregate denominator.

    IDs use full XML part/measure/note ordinals, never a window-local index.
    ``source.id`` preserves an explicit XML ID or uses that ordinal path. Call
    this on the pinned ORIGINAL XML and compare ``id/construct/source`` against
    original-origin ledger rows; generated extras have their own origin.
    For MIDI, return the required limitation binding without a window prefix;
    visual ledgers namespace its ID per window and add the first measure.
    """
    if hand not in ("both", "left", "right"):
        raise ValueError("Invalid hand mode")
    if original_xml is None:
        return [dict(id="midi-written-transcription", construct="midi_written_transcription",
                     source=dict(id="midi-written-transcription", source_name=source_name,
                                 origin="midi", staff=hand))]
    return [{key: row[key] for key in ("id", "construct", "source", "scope") if key in row}
            for row in _read(original_xml, hand, "original").elements]


def _key(event, offset=0):
    if event["beat"] is None:
        return None
    clock = event.get("_clock", Fraction(str(event["beat"])))
    return (event["kind"], _beat(clock - offset), event["staff"],
            tuple(event["spelling"]) if event["kind"] == "note" and event["spelling"] else None)


def _measured(report):
    measured = report.get("measured", []) if isinstance(report, dict) else []
    return [row for row in measured if isinstance(row, dict)] if isinstance(measured, list) else []


def _finite_score(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and 0 < value <= 1)



def _rectangular_rest_identified(row, kind):
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
    return (correct and _finite_score(row.get("shape_match")) and row["shape_match"] >= .65
            and numeric(rival) and 0 <= rival <= 1 and row["shape_match"]-rival >= .03
            and all(type(row.get(k)) is int and row[k] >= 12
                    for k in ("changed_pixels", "visible_original_ink_removed"))
            and isinstance(row.get("delta_file"), str) and bool(row["delta_file"]))

def _pixel(event, measured, used):
    candidates = []
    for i, row in enumerate(measured):
        if i in used or row.get("staff") != event["staff"]:
            continue
        if _number(row.get("measure")) != event["measure"]:
            continue
        try:
            if _beat(row.get("beat")) != event["beat"]:
                continue
        except (ValueError, TypeError):
            continue
        if str(row.get("voice")) != event["voice"]:
            continue
        if event["kind"] == "note" and row.get("spelling") is not None:
            if list(row["spelling"]) != event["spelling"]:
                continue
        elif event["kind"] == "note":
            continue
        if event["xml_id"] and row.get("source_id") != event["xml_id"]:
            continue
        candidates.append((i, row))
    if not candidates:
        return "unverified", "No matching independent per-event pixel record", None
    if len(candidates) != 1:
        return "ambiguous", "Multiple pixel records cannot establish a unique event identity", None
    i, row = candidates[0]
    used.add(i)
    status = row.get("status")
    if status not in STATUSES:
        return "unverified", "Pixel record has no recognized evidence status", row
    if status != "verified":
        return status, row.get("reason", f"Independent pixel record is {status}"), row
    if event["kind"] == "note":
        expected_glyph = ("head_whole" if event["note_type"] == "whole" else
                          "head_half" if event["note_type"] == "half" else "head_black")
        if row.get("glyph") != expected_glyph or not _finite_score(row.get("match")):
            return "unverified", "Pitch record lacks a measured glyph match", row
    else:
        if row.get("required_rest") != event["note_type"]:
            return "unverified", "Rest record does not identify the required written rest", row
        if not _finite_score(row.get("shape_match")):
            return "unverified", "Rest record lacks an independently measured contour", row
        if (row.get("type_ambiguity") or (event["note_type"] in {"half", "whole"}
                and not _rectangular_rest_identified(row, event["note_type"]))):
            return "ambiguous", "Half/whole rest contour lacks independent staff-grid orientation", row
    return "verified", "Independent raster evidence for pitch position" if event["kind"] == "note" else "Independent isolated rest contour and required grid orientation; voice-lane placement and dots are separate", row



def _feature_identity(event):
    return (event["_pixel_id"], event["measure"], event["staff"], event["voice"],
            event["beat"], tuple(event["spelling"]) if event["spelling"] else None)


def _feature_record(event, measured, identities):
    identity = _feature_identity(event)
    if identities[identity] != 1:
        return None, "Independent XML event identity is not unique"
    matches = []
    for row in measured:
        beat, spelling = row.get("beat"), row.get("spelling")
        if (isinstance(beat, bool) or not isinstance(beat, (int, float)) or not isfinite(beat)
                or isinstance(row.get("measure"), bool)
                or not isinstance(spelling, (list, tuple)) or len(spelling) != 3
                or not isinstance(spelling[0], str)
                or any(type(value) is not int for value in spelling[1:])):
            continue
        key = (row.get("source_id"), _number(row.get("measure")), row.get("staff"),
               str(row.get("voice")), _beat(beat), tuple(spelling))
        if key == identity:
            matches.append(row)
    if len(matches) != 1:
        return None, "No unique matching independent per-event feature record"
    return matches[0], ""


def _box(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and isfinite(x) for x in value)
            and value[0] < value[2] and value[1] < value[3])


def _family_evidence(evidence, glyph):
    if not isinstance(evidence, dict) or not glyph:
        return False
    score, runner, margin = (evidence.get(k) for k in ("score", "runner_up", "margin"))
    return (evidence.get("expected") == evidence.get("observed") == glyph
            and _finite_score(score) and score >= .72
            and isinstance(runner, (int, float)) and not isinstance(runner, bool) and 0 <= runner <= 1
            and isinstance(margin, (int, float)) and not isinstance(margin, bool) and margin >= .05
            and abs(score - runner - margin) <= .0002 and _box(evidence.get("bbox")))


def _feature_status(construct, original, generated, record, bound=None):
    features = record.get("features") if isinstance(record, dict) else None
    result = features.get(construct) if isinstance(features, dict) else None
    if not isinstance(result, dict) or result.get("status") not in STATUSES:
        return "unverified", "Missing independent measurement for this feature", None
    status = result["status"]
    if status != "verified":
        return status, result.get("reason", "Independent feature remains unverified"), result
    evidence = result.get("evidence")
    valid = isinstance(evidence, dict) and _box(evidence.get("bbox"))
    if valid and construct == "stem":
        direction = evidence.get("direction")
        matches = evidence.get("head_matches")
        valid = (isinstance(direction, str) and direction in {"up", "down"}
                 and all(e["_stem"] in (None, direction) for e in (original, generated))
                 and evidence.get("group_id") == generated["_group_id"]
                 and evidence.get("shared_source_ids") == generated["_group_members"]
                 and isinstance(matches, list) and len(matches) == len(generated["_group_members"])
                 and all(_finite_score(m) and m >= .79 for m in matches))
    elif valid and construct == "flag":
        count = _FLAG_COUNTS.get(original["note_type"])
        stem_status, _, stem_result = _feature_status("stem", original, generated, record)
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
        stem_status, _, stem_result = _feature_status("stem", original, generated, record)
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
                dot_status,_,dot=_feature_status("dot",event,event,measurement)
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
            valid = (numeric(gap) and gap > 0 and _box(head)
                     and isinstance(head_boxes, list) and len(head_boxes) == len(generated["_group_members"])
                     and all(_box(b) for b in head_boxes)
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


def _apply_features(output, expected, matched, generated, feature_report):
    measurements = _measured(feature_report)
    identities = Counter(_feature_identity(e) for e in generated.events.values()
                         if e["kind"] == "note" and e["timing_supported"])
    bound={}
    for event in generated.events.values():
        if event["kind"]=="note" and event["timing_supported"]:
            row,_=_feature_record(event,measurements,identities)
            if row is not None:
                bound[event["_pixel_id"]]=(event,row)
    by_event = defaultdict(list)
    for row in output:
        path = row["source"].get("xml_ordinal")
        if path in expected and expected[path]["kind"] == "note":
            by_event[path].append(row)
    for path, obligations in by_event.items():
        event, match = expected[path], matched.get(path)
        record, reason = _feature_record(match, measurements, identities) if match else (
            None, "Original visible event has no generated counterpart")
        for row in obligations:
            if row["construct"] not in _FEATURES:
                continue
            status, why, evidence = _feature_status(row["construct"], event, match, record,bound) if record else (
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
                     **{kind: Fraction(1, 2**count) for kind, count in _FLAG_COUNTS.items()}}
        base = durations.get(event["note_type"])
        expected_duration = base * (2 - Fraction(1, 2**event["dots"])) if base is not None else None
        if expected_duration is None or _beat(expected_duration) != event["duration"]:
            rhythm.update(status="unsupported", reason="Written value needs an independent duration interpretation")
        elif match and any(event[k] != match[k] for k in ("note_type", "duration", "dots")):
            rhythm.update(status="mismatch", reason="Generated written rhythm differs from the original event")
        elif event["note_type"] == "quarter" and _feature_status(
                "flag_absence", event, match, record,bound)[0] != "verified":
            rhythm.update(status="unverified", reason="Quarter rhythm requires bound independent absent-flag evidence")
        elif all(r["status"] == "verified" for r in requirements):
            rhythm.update(status="verified", reason="Independent head and all required rhythm features verified",
                          evidence={"requirements": [r["id"] for r in requirements]})
            if event["note_type"] == "quarter":
                rhythm["evidence"]["flag_absence"] = record["features"]["flag_absence"]
        else:
            rhythm.update(status="unverified", reason="Every required independent rhythm contribution must verify")



def _rest_dots_verified(evidence, count):
    if (not isinstance(evidence, dict) or evidence.get("status") != "verified"
            or any(type(evidence.get(key)) is not int or evidence[key] != count
                   for key in ("expected_count", "observed_count"))):
        return False
    dots = evidence.get("dots")
    if (not isinstance(dots, list) or len(dots) != count
            or any(not isinstance(dot, dict) or not _box(dot.get("box"))
                   or not _finite_score(dot.get("shape_match")) or dot["shape_match"] < .8 for dot in dots)):
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
    if not all(_box(box) for box in boxes):
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
    return (_finite_score(evidence.get("registration_match")) and evidence["registration_match"] >= .79
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

def _apply_rest_evidence(output, expected, matched):
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
                 and not isinstance(record.get("measure"), bool) and _number(record.get("measure")) == match["measure"]
                 and isinstance(clock, (int, float)) and not isinstance(clock, bool) and isfinite(clock)
                 and _beat(clock) == match["beat"] and record.get("staff") == match["staff"]
                 and str(record.get("voice")) == match["voice"]
                 and record.get("required_rest") == record.get("observed_rest") == event["note_type"]
                 and _finite_score(record.get("shape_match")) and record["shape_match"] >= .65
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
                     **{kind: Fraction(1, 2**count) for kind, count in _FLAG_COUNTS.items()}}
        base = durations.get(event["note_type"])
        value = base * (2 - Fraction(1, 2**event["dots"])) if base is not None else None
        arithmetic = (value is not None and value == event["_duration"] == match["_duration"]
                      and not event["_connectors"] and not match["_connectors"])
        verified = dots_verified and arithmetic
        rhythm.update(status="verified" if verified else "unverified",
                      reason="Bound rest type, every dot and exact written duration verified" if verified else
                             "Rest rhythm requires bound type, all independent dots and exact source duration arithmetic",
                      evidence=dict(pixel=record, expected_duration=str(value)))

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
    if (not _box(box) or not all(type(v) is int and v >= 0 for v in box) or
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


def _connector_frame_clock(frame):
    if (not isinstance(frame, str) or not frame.startswith("native-") or not frame.endswith(".png") or
            "/" in frame or "\\" in frame):
        return None
    try:
        clock = float(frame[7:-4])
    except ValueError:
        return None
    return clock if isfinite(clock) else None


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
                not _box(head.get("bbox")) or
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
    clock = _connector_frame_clock(frame)
    if (clock is None or
            not events[0]["beat"]-.00001 <= clock <= events[1]["beat"]+.00001):
        return None
    for motion, event in zip(correspondence, events):
        if not isinstance(motion, dict):
            return None
        onset = _connector_frame_clock(motion.get("onset_frame"))
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


def _apply_connectors(output, original, matched, generated, report):
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
    clock = _connector_frame_clock(frame)
    if clock is None:
        return False
    if (not _box(evidence.get("bbox")) or not numeric(gap) or gap <= 0 or
            not isinstance(lines, list) or len(lines) != 5 or not all(numeric(y) for y in lines) or
            any(a >= b for a, b in zip(lines, lines[1:])) or
            abs((lines[-1]-lines[0])/4-gap) > .0001 or
            not isinstance(anchors, list) or len(anchors) != len(events)):
        return False
    for anchor, event in zip(anchors, events):
        if (not isinstance(anchor, dict) or anchor.get("source_id") != event["_oracle_id"] or
                not _box(anchor.get("bbox")) or
                not all(numeric(anchor.get(k)) for k in ("x", "y", "gap", "head_match")) or
                abs(anchor["gap"]-gap) > .0001 or not .79 <= anchor["head_match"] <= 1):
            return False
        registration = anchor.get("registration")
        if (not isinstance(registration, dict) or type(registration.get("pixels")) is not int or
                not _finite_score(registration.get("agreement")) or registration["agreement"] < .8 or
                not _finite_score(registration.get("margin")) or registration["margin"] < .04):
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
        if (not isinstance(stem, dict) or not _box(stem.get("bbox")) or
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
        for level in range(2, min(_FLAG_COUNTS[left["note_type"]], _FLAG_COUNTS[right["note_type"]])+1):
            lm = {int(n): value for n, value, _ in left["beams"]}
            rm = {int(n): value for n, value, _ in right["beams"]}
            if (not lm and not rm) or (lm.get(level) in {"begin", "continue"} and rm.get(level) in {"continue", "end"}):
                minimum = level
        intervals.extend((x, minimum, max(_FLAG_COUNTS[left["note_type"]], _FLAG_COUNTS[right["note_type"]])) for x in xs)
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
    text, bracket, _number = identity
    digits = evidence.get("digits")
    codes = [f"E{0x880+int(c):03X}" if c.isdigit() else "E88A" for c in text]
    if (evidence.get("expected_numeral") != text or not _box(evidence.get("number_bbox")) or
            not _finite_score(evidence.get("numeral_match")) or evidence["numeral_match"] < .79 or
            not _finite_score(evidence.get("numeral_margin")) or evidence["numeral_margin"] < .05 or
            not isinstance(digits, list) or len(digits) != len(codes)):
        return False
    for digit, code in zip(digits, codes):
        if (not isinstance(digit, dict) or digit.get("code") != code or not _box(digit.get("bbox")) or
                not _finite_score(digit.get("match")) or digit["match"] < .79 or
                not _finite_score(digit.get("runner_up")) or
                not _finite_score(digit.get("margin")) or digit["margin"] < .03 or
                abs(digit["match"]-digit["runner_up"]-digit["margin"]) > .0002):
            return False
    if any(a["bbox"][2] > b["bbox"][0] for a, b in zip(digits, digits[1:])):
        return False
    return not (bracket or "bracket_bbox" in evidence) or (
        _box(evidence.get("bracket_bbox")) and _finite_score(evidence.get("bracket_match")) and evidence["bracket_match"] >= .72)


def _apply_group_connectors(output, original, matched, generated, original_xml, generated_xml, reports):
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
                    _beat(beat) != events[0]["beat"] or
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
                if (any(f["kind"] != "note" or f["note_type"] not in _FLAG_COUNTS for f in facts) or
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
        if not event or not match or event["kind"] != "note" or event["note_type"] not in _FLAG_COUNTS:
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
        value = Fraction(1, 2**_FLAG_COUNTS[event["note_type"]])*(2-Fraction(1, 2**event["dots"]))
        if ratio:
            value *= Fraction(ratio[1], ratio[0])
        if value != event["_duration"] or value != match["_duration"]:
            continue
        rhythm = next(r for r in obligations if r["construct"] == "note_rhythm")
        rhythm.update(status="verified", reason="Bound graphical connectors, required features and exact source duration verified",
                      evidence=dict(beam=beam, tuplet=tuplet, expected_duration=str(value)))


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
            abs((lines[-1]-lines[0])/4-gap) > .000001 or not _box(head) or
            not all(type(v) is int and v >= 0 for v in head) or
            not _finite_score(evidence.get("head_match")) or evidence["head_match"] < .79 or
            not head[1] <= lines[-1]-event["_staff_step"]*gap/2 < head[3]):
        return False
    clock = _connector_frame_clock(evidence.get("frame"))
    registration = evidence.get("registration")
    if (clock is None or not isinstance(registration, dict) or type(registration.get("pixels")) is not int or
            not _finite_score(registration.get("agreement")) or registration["agreement"] < .8 or
            not _finite_score(registration.get("margin")) or registration["margin"] < .04 or
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
                segment.get("required_extension_spaces") != .12 or not _box(segment.get("bbox"))):
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


def _apply_ledgers(output, expected, matched, generated, report):
    measurements = _measured(report)
    identities = Counter(_feature_identity(e) for e in generated.events.values()
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
        record, _reason = _feature_record(match, measurements, identities)
        features = record.get("features") if record else None
        observation = features.get("ledger") if isinstance(features, dict) else None
        if not isinstance(observation, dict) or observation.get("status") not in STATUSES:
            continue
        if observation["status"] != "verified":
            row.update(status=observation["status"], reason=observation.get("reason", "Ledger evidence remains unresolved"), evidence=observation)
        elif _ledger_measurement(observation, match):
            row.update(status="verified", reason="All source-required ledger steps have thin continuous ink beyond both registered head edges",
                       evidence=dict(generated_source_id=match["_pixel_id"], oracle_source_id=match["_oracle_id"], pixel=observation))


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


def _apply_tuplet_semantics(output, original, expected, matched, generated,
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
    for group in _source_tuplet_groups(generated):
        groups[tuple(e["xml_ordinal"] for e in group["events"])].append(group)
    original_ids = Counter(e["_pixel_id"] for e in original.events.values() if e["timing_supported"])
    generated_ids = Counter(e["_pixel_id"] for e in generated.events.values() if e["timing_supported"])
    proven = {}
    for group in _source_tuplet_groups(original):
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
    measurements = _measured(feature_report)
    identities = Counter(_feature_identity(e) for e in generated.events.values() if e["kind"] == "note" and e["timing_supported"])
    bound = {}
    for event in generated.events.values():
        if event["kind"] == "note" and event["timing_supported"]:
            record, _ = _feature_record(event, measurements, identities)
            if record is not None:
                bound[event["_pixel_id"]] = (event, record)
    durations = {"whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1),
                 **{kind: Fraction(1, 2**count) for kind, count in _FLAG_COUNTS.items()}}
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
            record, _ = _feature_record(match, measurements, identities)
            if _feature_status("flag_absence", event, match, record, bound)[0] != "verified":
                continue
            graphics["flag_absence"] = record["features"]["flag_absence"]
        rhythm.update(status="verified", reason="Exact chosen ratio arithmetic, bound native semantics and all required graphics verified",
                      evidence=dict(expected_duration=str(value), semantics=evidence, **graphics))


def visual_elements(original_xml: str | None, generated_xml: str, pitch_report: dict,
                    rest_report: dict, *, hand='both', first_bar=1,
                    last_bar=None, source_name='', feature_report: dict | None = None,
                    connector_report: dict | None = None, beam_report: dict | None = None,
                    tuplet_report: dict | None = None, ledger_report: dict | None = None,
                    semantic_report: dict | None = None) -> list[dict]:
    """Build a per-construct ledger for a generated source window.

    ``first_bar``/``last_bar`` are inclusive original measure *indices*, not
    MusicXML measure labels. Omitted ``last_bar`` uses generated window length.
    Original beats stay absolute in source bindings; generated clocks start at
    zero. Source/generated voice labels may normalize; each occurrence and
    measurement is consumed at most once. No report totals prove an element.
    Optional ``feature_report`` is from ``verify_note_feature_pixels`` on the
    exact captured ``generated_xml``. Omission preserves legacy feature statuses.
    Bound stem/flag/dot evidence may combine with the independent head record
    into rhythm evidence. Optional beam/tuplet reports also require complete
    ordered source groups, graphical witnesses and exact duration arithmetic.
    Optional ``connector_report`` supplies per-pair tie/slur observations;
    aggregate status never authorizes an original endpoint obligation.
    Optional ``ledger_report`` proves every source-required ledger step for
    each inventoried note, independently of the ordinary feature counts.
    ``semantic_report`` is a per-event generated/native contract. Deliberately
    hidden complete tuplet groups have semantic scope, never pixel evidence.
    """
    if isinstance(first_bar, bool) or not isinstance(first_bar, int) or first_bar < 1:
        raise ValueError("first_bar must be a positive measure index")
    generated = _read(generated_xml, hand, "generated", source_name if original_xml is None else "")
    if last_bar is None:
        last_bar = first_bar + generated.measure_count - 1
    if isinstance(last_bar, bool) or not isinstance(last_bar, int) or last_bar < first_bar:
        raise ValueError("last_bar must be an inclusive index at or after first_bar")
    original = _read(original_xml, hand, "original") if original_xml is not None else generated
    start, end = (first_bar, last_bar) if original_xml is not None else (1, generated.measure_count)
    offset = original.bars[start-1] if original.bars and start <= original.measure_count else 0
    output = [dict(row) for row in original.elements
              if start <= row["source"].get("measure_index", start) <= end]
    expected = {path: event for path, event in original.events.items()
                if start <= event["measure_index"] <= end}
    available = defaultdict(list)
    for path, event in generated.events.items():
        if event["timing_supported"]:
            available[_key(event)].append(path)
    matched, used_generated = {}, set()
    for path, event in expected.items():
        choices = available.get(_key(event, offset), [])
        choices = [p for p in choices if p not in used_generated]
        if choices:
            choices.sort(key=lambda p: (generated.events[p]["xml_id"] != event["xml_id"],
                                        generated.events[p]["voice"] != event["voice"]))
            selected = choices[0]
            matched[path] = generated.events[selected]
            used_generated.add(selected)
    measurements = {"note": _measured(pitch_report), "rest": _measured(rest_report)}
    used_pixels = {"note": set(), "rest": set()}
    for row in output:
        if row["construct"] not in {"pitch", "rest"}:
            continue
        event = expected[row["source"]["xml_ordinal"]]
        if not event["timing_supported"]:
            row.update(status="unsupported", reason="Independent XML timing reader does not support this event")
            continue
        match = matched.get(event["xml_ordinal"])
        if match is None:
            row.update(status="unverified" if generated.reader_error else "mismatch",
                       reason="Generated XML timing cannot establish correspondence: " + generated.reader_error
                              if generated.reader_error else "Original visible event missing or changed in generated window")
            continue
        if event["kind"] == "rest" and match["note_type"] != event["note_type"]:
            row.update(status="mismatch", reason="Generated rest type differs from original written rest")
            continue
        status, reason, evidence = _pixel(match, measurements[event["kind"]], used_pixels[event["kind"]])
        row.update(status=status, reason=reason,
                   evidence=dict(generated={key: match[key] for key in
                       ("id", "measure", "staff", "voice", "beat", "spelling", "note_type")},
                       pixel=evidence))
    _apply_rest_evidence(output, expected, matched)
    if feature_report is not None:
        _apply_features(output, expected, matched, generated, feature_report)
    if connector_report is not None:
        _apply_connectors(output, original, matched, generated, connector_report)
    if beam_report is not None or tuplet_report is not None:
        _apply_group_connectors(output, original, matched, generated, original_xml, generated_xml,
                                {"beam": beam_report, "tuplet": tuplet_report})
    if ledger_report is not None:
        _apply_ledgers(output, expected, matched, generated, ledger_report)
    _apply_tuplet_semantics(output, original, expected, matched, generated, original_xml, generated_xml,
                            semantic_report, feature_report)
    if original_xml is not None:
        authored_hands = {event["staff"] for event in original.events.values()}
        for path, event in generated.events.items():
            if path in used_generated:
                continue
            source = dict({k: v for k, v in event.items() if not k.startswith("_")}, origin="generated_extra")
            source.pop("timing_supported")
            source.pop("xml_id")
            scaffolding = event["kind"] == "rest" and event["staff"] not in authored_hands
            unsupported = scaffolding or not event["timing_supported"]
            output.append(dict(id=f"generated-extra:w{first_bar}-{last_bar}:{path}",
                               construct="staff_scaffolding" if scaffolding else
                                         "generated_event" if not event["timing_supported"] else
                                         "rest" if event["kind"] == "rest" else "pitch",
                               status="unsupported" if unsupported else "mismatch", source=source,
                               reason="Blank-hand rest scaffolding has no authored counterpart; its contour does not certify source notation"
                                      if scaffolding else "Independent timing reader cannot establish a source counterpart"
                                      if not event["timing_supported"] else "Generated visible event has no original source counterpart"))
    else:
        # Generated ordinals restart in every MIDI window. Namespace every row
        # while preserving the label and local generated source bindings.
        for row in output:
            row["id"] = f"w{first_bar}-{last_bar}:" + row["id"]
        output.append(dict(id=f"w{first_bar}-{last_bar}:midi-written-transcription",
                           construct="midi_written_transcription", status="unsupported",
                           source=dict(id="midi-written-transcription", source_name=source_name,
                                       origin="midi", measure=first_bar, staff=hand),
                           reason="MIDI has no unique original written score; this ledger covers only the generated written transcription"))
    return output


def coverage_counts(elements: list[dict]) -> dict:
    """Aggregator schema: every row contributes to exactly one status."""
    counts = Counter(row["status"] for row in elements)
    unknown = counts.keys() - STATUSES
    if unknown:
        raise ValueError(f"Unknown coverage statuses: {sorted(unknown)}")
    return dict(expected=len(elements), **{status: counts[status] for status in STATUSES})
