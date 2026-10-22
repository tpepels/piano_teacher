"""Fail-closed visual ledger rooted in original, independently read MusicXML.

Only per-event raster pitch and rest-contour records can verify anything here.
XML agreement supplies correspondence, never visual proof. In particular a
head silhouette does not verify a stem, flag, duration, dot, or connector.
This module has no image, renderer, or native-model dependencies.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from xml.etree import ElementTree as ET

from .proof import _hand, read_written_score


STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
_FLAG_TYPES = {"eighth", "16th", "32nd", "64th", "128th", "256th", "512th", "1024th"}
_NOTE_DATA = {"pitch", "unpitched", "rest", "duration", "voice", "type", "staff",
              "chord", "grace", "cue", "stem", "dot", "beam", "tie", "notations",
              "accidental", "time-modification"}
_CONTAINERS = {"notations", "articulations", "ornaments", "technical", "direction-type"}


@dataclass
class _Inventory:
    elements: list[dict]
    events: dict[str, dict]
    bars: tuple
    measure_count: int
    reader_error: str | None = None


def _number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return value


def _beat(value):
    return round(float(value), 8) if value is not None else None


def _visible(node):
    return node.get("print-object") != "no"


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
                                 _clock=fact["beat"] if fact else None)
                    events[path] = event
                    construct = "rest" if kind == "rest" else "pitch" if pitch is not None else "unpitched"
                    emit(construct, source, path)
                    emit("rest_rhythm" if kind == "rest" else "note_rhythm", source, path)
                    if kind == "rest":
                        emit("rest_placement", source, path)
                    else:
                        stem = node.findtext("stem")
                        if stem != "none" and (stem is not None or source["note_type"] not in {"whole", "breve", "long", "maxima"}):
                            emit("stem", source, path, direction=stem or "implicit")
                        if source["note_type"] in _FLAG_TYPES and not node.findall("beam") and stem != "none":
                            emit("flag", source, path, note_type=source["note_type"])
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
    return _Inventory(elements, events, tuple(boundaries), count, issue)


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
    return [{key: row[key] for key in ("id", "construct", "source")}
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
        if event["note_type"] in {"half", "whole"} or row.get("type_ambiguity"):
            return "ambiguous", "Half/whole rest contour does not distinguish written value or placement", row
    return "verified", "Independent raster evidence for pitch position" if event["kind"] == "note" else "Independent isolated rest contour; placement and dots are separate", row


def visual_elements(original_xml: str | None, generated_xml: str, pitch_report: dict,
                    rest_report: dict, *, hand='both', first_bar=1,
                    last_bar=None, source_name='') -> list[dict]:
    """Build a per-construct ledger for a generated source window.

    ``first_bar``/``last_bar`` are inclusive original measure *indices*, not
    MusicXML measure labels. Omitted ``last_bar`` uses generated window length.
    Original beats stay absolute in source bindings; generated clocks start at
    zero. Source/generated voice labels may normalize; each occurrence and
    measurement is consumed at most once. No report totals prove an element.
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
    if original_xml is not None:
        authored_hands = {event["staff"] for event in original.events.values()}
        for path, event in generated.events.items():
            if path in used_generated:
                continue
            source = dict(event, origin="generated_extra")
            source.pop("timing_supported")
            source.pop("xml_id")
            source.pop("_clock")
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
