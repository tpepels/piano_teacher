"""Project source marks only onto their bound, unmodified performed attacks."""
from copy import deepcopy
from fractions import Fraction
from xml.etree import ElementTree as ET


def _notations(note):
    element = note.find("notations")
    return ET.SubElement(note, "notations") if element is None else element


def _rhythmic_marks(source, head, divisions, output_divisions):
    # A display window can divide an authored note at a different barline.
    # Copy engraving details only when the visible segment has its exact
    # written value and the same structural role in its tie/tuplet/beam.
    if not source.findtext("duration") or divisions <= 0:
        return
    if Fraction(source.findtext("duration")) / divisions != Fraction(
            head.findtext("duration")) / output_divisions:
        return
    if source.findtext("type") != head.findtext("type"):
        return
    for path, identity in (("notations/tied", "type"), ("notations/tuplet", "type"),
                           ("beam", "number")):
        for target in head.findall(path):
            matches = [mark for mark in source.findall(path)
                       if mark.get(identity, "1") == target.get(identity, "1")
                       and (path != "beam" or mark.text == target.text)]
            if len(matches) == 1:
                target.attrib.update({k: v for k, v in matches[0].attrib.items() if k != "id"})


def _slur_marks(head, source, note, lane, opened, spans):
    for mark in source.findall("notations/slur"):
        key = *lane, mark.get("number", "1")
        if mark.get("type") == "start":
            opened[key] = head, mark, dict(note.slur_ends).get(key[-1])
        elif mark.get("type") == "stop" and key in opened:
            first, start, destination = opened.pop(key)
            if first is head or destination != note.written_id:
                continue
            spans.append((first, head, start, mark, "slur"))


def _publish_slurs(part, spans):
    # Repeat expansion and merging written voices into one worksheet part
    # can bring independent slurs with the same original number together.
    # Give overlapping pairs distinct numbers in the generated document.
    order = {note: i for i, note in enumerate(part.findall("measure/note"))}
    ends = {}
    for first, last, start, stop, kind in sorted(spans, key=lambda span: order[span[0]]):
        number = start.get("number", "1")
        if ends.get(number, -1) > order[first]:
            number = next(str(i) for i in range(1, len(ends) + 2)
                          if ends.get(str(i), -1) <= order[first])
        ends[number] = order[last]
        start = deepcopy(start)
        stop = deepcopy(stop)
        start.set("number", str(number))
        stop.set("number", str(number))
        start.set("id", f"{kind}-{first.get('id')}-{last.get('id')}")
        stop.attrib.pop("id", None)
        _notations(first).append(start)
        _notations(last).insert(0, stop)


def _attach_grace(measure, head, note, source, spans):
    contents = list(measure)
    index = contents.index(head)
    while index > 0 and contents[index].find("chord") is not None:
        index -= 1
    started = {}
    for offset, markup in enumerate(note.grace_before):
        grace = ET.fromstring(markup)
        for staff in grace.findall("staff"):
            grace.remove(staff)
        grace.set("id", f"grace-{head.get('id')}-{offset}")
        voice = grace.find("voice")
        if voice is not None:
            voice.text = head.findtext("voice", "1")
        for mark in grace.findall("notations/slur"):
            grace.find("notations").remove(mark)
            number = mark.get("number", "1")
            if mark.get("type") == "start":
                started[number] = grace, mark
            elif mark.get("type") == "stop" and number in started:
                first, start = started.pop(number)
                spans.append((first, grace, start, mark, "ornament"))
        measure.insert(index + offset, grace)
    for stop in source.findall("notations/slur[@type='stop']"):
        number = stop.get("number", "1")
        if number in started:
            first, start = started.pop(number)
            spans.append((first, head, start, stop, "ornament"))


def project_written_marks(root, phrase, bindings, divisions, enabled):
    sources = {note.source_id: note for note in phrase.notes if note.written_note and enabled}
    if not sources:
        return
    for part in root.findall("part"):
        opened = {}
        spans = []
        for measure in part.findall("measure"):
            for head in measure.findall("note"):
                binding = bindings.get(head.get("id"))
                if not binding or not binding["is_attack"]:
                    continue
                note = sources.get(binding["source_id"])
                if note is None:
                    continue
                source = ET.fromstring(note.written_note)
                _rhythmic_marks(source, head, note.written_divisions, divisions)
                lane = note.voice, head.findtext("voice", "1")
                _slur_marks(head, source, note, lane, opened, spans)
                marks = [mark for mark in source.findall("notations/articulations/*")
                         if mark.tag in ("staccato", "tenuto", "accent")]
                if marks:
                    parent = ET.SubElement(_notations(head), "articulations")
                    for mark in marks:
                        ET.SubElement(parent, mark.tag)
                if note.grace_before:
                    _attach_grace(measure, head, note, source, spans)
        _publish_slurs(part, spans)
