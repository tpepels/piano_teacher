"""Independent original/generated MusicXML obligations and source-derived groups.

Each inventory owns its event facts and full ordinal denominator. No report,
image detector, renderer model or coordinator chooses source obligations."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from .proof import _hand, read_written_score
from .visual_contract import source_beat, source_number
from xml.etree import ElementTree as ET


_FLAG_TYPES = {"eighth", "16th", "32nd", "64th", "128th", "256th", "512th", "1024th"}
_NOTE_DATA = {"pitch", "unpitched", "rest", "duration", "voice", "type", "staff",
              "chord", "grace", "cue", "stem", "dot", "beam", "tie", "notations",
              "accidental", "time-modification"}
_CONTAINERS = {"notations", "articulations", "ornaments", "technical", "direction-type"}


@dataclass
class SourceInventory:
    elements: list[dict]
    events: dict[str, dict]
    bars: tuple
    measure_count: int
    reader_error: str | None = None
    logical_symbols: tuple = ()


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


def source_tuplet_groups(inventory):
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
    hidden = {e["xml_ordinal"] for g in source_tuplet_groups(inventory) if g["hidden"] for e in g["events"]}
    for row in inventory.elements:
        if row["construct"] != "tuplet":
            continue
        metadata = "/time-modification" in row["id"] or row["source"].get("xml_ordinal") in hidden
        row["scope"] = "semantic" if metadata else "visual"


def read_visual_inventory(xml: str, hand: str, origin: str, source_name: str = "") -> SourceInventory:
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
                        measure=source_number(measure.get("number", str(mi))),
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
                    spelling = ([pitch.findtext("step"), source_number(pitch.findtext("alter", "0")),
                                 source_number(pitch.findtext("octave"))] if pitch is not None else None)
                    if fact is not None and fact["spelling"] is not None:
                        spelling = list(fact["spelling"])
                    kind = "rest" if node.find("rest") is not None else "note"
                    source.update(beat=source_beat(fact["beat"]) if fact else None,
                                  duration=source_beat(fact["duration"]) if fact else None,
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
    inventory = SourceInventory(elements, events, tuple(boundaries), count, issue,
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
            for row in read_visual_inventory(original_xml, hand, "original").elements]
