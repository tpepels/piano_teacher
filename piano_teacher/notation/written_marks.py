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


def _slur_marks(head, source, lane, opened):
    for mark in source.findall("notations/slur"):
        key = *lane, mark.get("number", "1")
        if mark.get("type") == "start":
            opened[key] = head, mark
        elif mark.get("type") == "stop" and key in opened:
            first, start = opened.pop(key)
            if first is head:
                continue
            start = deepcopy(start)
            start.set("id", f"slur-{first.get('id')}-{head.get('id')}")
            _notations(first).append(start)
            stop = deepcopy(mark)
            stop.attrib.pop("id", None)
            _notations(head).append(stop)


def _attach_grace(measure, head, note):
    grace = ET.fromstring(note.grace_before)
    # The generated worksheet has one staff per part. Tie the source
    # ornament to its exact printed attack regardless of repeated measures.
    for staff in grace.findall("staff"):
        grace.remove(staff)
    grace.set("id", f"grace-{head.get('id')}")
    voice = grace.find("voice")
    if voice is not None:
        voice.text = head.findtext("voice", "1")
    measure.insert(list(measure).index(head), grace)


def project_written_marks(root, phrase, bindings, divisions, enabled):
    sources = {note.source_id: note for note in phrase.notes if note.written_note and enabled}
    if not sources:
        return
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            opened = {}
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
                _slur_marks(head, source, lane, opened)
                marks = [mark for mark in source.findall("notations/articulations/*")
                         if mark.tag in ("staccato", "tenuto", "accent")]
                if marks:
                    parent = ET.SubElement(_notations(head), "articulations")
                    for mark in marks:
                        ET.SubElement(parent, mark.tag)
                if note.grace_before and head.find("chord") is None:
                    _attach_grace(measure, head, note)
