"""Project expressive MusicXML onto lessons by *imported source-note identity*.

The lesson's note set and cursor are authoritative. Source markup must never
introduce omitted notes, change performance timing, or create orphan slurs.
Native supports source slur fragments; other expression classes deliberately
request complete Verovio-page fallback until matching native ink exists.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from xml.etree import ElementTree as ET


def project_annotations(source_musicxml: str, lesson_xml: str,
                        bindings: dict, phrase, *, boundaries: tuple[float, ...]
                        ) -> tuple[str, tuple[str, ...]]:
    if not source_musicxml:
        return lesson_xml, ()
    source = ET.fromstring(source_musicxml)
    output = ET.fromstring(lesson_xml)
    if source.tag != "score-partwise":
        raise ValueError("Annotations require score-partwise source MusicXML")
    for tag in source.iter():
        tag.tag = tag.tag.rsplit("}", 1)[-1]

    # The first generated segment is the only target for a source attack's
    # articulation or ornament; tied continuations must not repeat it.
    targets = {}
    hands = {}
    for child in output.findall(".//note[@id]"):
        binding = bindings.get(child.get("id"))
        if not binding or not binding["is_attack"]:
            continue
        sid = binding["source_id"]
        if sid in targets:
            raise ValueError("Source attack has multiple expressive anchors")
        targets[sid] = child
        hands[sid] = binding["hand"]

    original_notes = {}
    part_staves = defaultdict(set)
    voice_hands = defaultdict(set)
    measure_voice_hands = defaultdict(set)
    source_parts = source.findall("part")
    for pi, part in enumerate(source_parts):
        for mi, measure in enumerate(part.findall("measure")):
            for ordinal, child in enumerate(measure):
                if child.tag != "note" or child.find("pitch") is None:
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                original_notes[sid] = child
                if sid in targets:
                    hand = hands[sid]
                    voice = child.findtext("voice", "1")
                    part_staves[(pi, child.findtext("staff", "1"))].add(hand)
                    voice_hands[(pi, voice)].add(hand)
                    measure_voice_hands[(pi, mi, voice)].add(hand)

    # Slur numbers are local to the original part and voice; the same number
    # may be used simultaneously by two voices or across two staves.
    paired_slurs = set()
    started = {}
    for pi, part in enumerate(source_parts):
        for mi, measure in enumerate(part.findall("measure")):
            for ordinal, child in enumerate(measure):
                if child.tag != "note" or child.find("pitch") is None:
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                voice = child.findtext("voice", "1")
                for mark in child.findall("./notations/slur"):
                    key = pi, voice, mark.get("number", "1")
                    if mark.get("type") == "start":
                        started[key] = sid
                    elif mark.get("type") == "stop" and key in started:
                        first = started.pop(key)
                        if first in targets and sid in targets and hands[first] == hands[sid]:
                            paired_slurs.add((first, sid, key))

    unrendered = set()
    for sid, dest in targets.items():
        original = original_notes.get(sid)
        if original is None:
            continue  # MIDI source IDs have no original MusicXML decorations.
        original_notations = original.find("notations")
        if original_notations is not None:
            target_notations = dest.find("notations")
            for item in original_notations:
                if item.tag in ("tied", "tuplet"):
                    # Recomputed from the exercise's own note durations.
                    continue
                if item.tag == "slur":
                    key = (int(sid.split("-")[1][1:]),
                           original.findtext("voice", "1"),
                           item.get("number", "1"))
                    mark_type = item.get("type")
                    if mark_type == "start":
                        keep = any(a == sid and k == key for a,b,k in paired_slurs)
                    elif mark_type == "stop":
                        keep = any(b == sid and k == key for a,b,k in paired_slurs)
                    else:
                        keep = False
                    if not keep:
                        continue
                if target_notations is None:
                    target_notations = ET.SubElement(dest, "notations")
                target_notations.append(deepcopy(item))
                if item.tag != "slur":
                    unrendered.add("note:" + item.tag)
        for lyric in original.findall("lyric"):
            dest.append(deepcopy(lyric))
            unrendered.add("note:lyric")

    # Preserve meaningful directions on the correct *generated hand*.
    # Each generated part is one staff, so source <staff> is used for
    # routing but is not copied. Offset is relative to the measure start,
    # keeping note/grading cursors unchanged even for multiple voices.
    generated = {
        (hand, int(measure.get("number"))): measure
        for part in output.findall("part")
        for hand in (["right"] if part.get("id") == "RH" else ["left"])
        for measure in part.findall("measure")
    }
    for pi, part in enumerate(source_parts):
        divisions = Fraction(1)
        for mi, measure in enumerate(part.findall("measure")):
            measure_number = mi + 1
            cursor = Fraction(0)
            for child in measure:
                if child.tag == "attributes" and child.find("divisions") is not None:
                    divisions = Fraction(child.findtext("divisions"))
                elif child.tag in ("backup", "forward"):
                    delta = Fraction(child.findtext("duration")) / divisions
                    cursor += delta if child.tag == "forward" else -delta
                elif child.tag == "note":
                    if child.find("chord") is None and child.find("grace") is None:
                        cursor += Fraction(child.findtext("duration", "0")) / divisions
                elif child.tag == "direction":
                    source_staff = child.findtext("staff")
                    source_voice = child.findtext("voice")
                    if source_staff:
                        # An explicit staff remains authoritative. A voice
                        # restriction, when present, must not contradict it.
                        candidate_hands = set(part_staves.get((pi, source_staff), set()))
                        if source_voice:
                            matching = (measure_voice_hands.get((pi, mi, source_voice))
                                        or voice_hands.get((pi, source_voice), set()))
                            if matching:
                                candidate_hands &= matching
                    elif source_voice:
                        # One MusicXML part can contain both piano hands.
                        # A voice-specific direction must not be discarded
                        # solely because the part has two active staves.
                        candidate_hands = set(
                            measure_voice_hands.get((pi, mi, source_voice))
                            or voice_hands.get((pi, source_voice), set()))
                    else:
                        candidate_hands = set().union(
                            *(v for (index, _), v in part_staves.items() if index == pi))
                    # Unstaffed directions in ambiguous piano grand staves
                    # cannot be placed safely on either generated hand.
                    if len(candidate_hands) != 1:
                        continue
                    hand = next(iter(candidate_hands))
                    dest_measure = generated.get((hand, measure_number))
                    if dest_measure is None:
                        continue
                    relative = cursor + Fraction(child.findtext("offset", "0")) / divisions
                    if relative < 0:
                        continue
                    measure_start = (boundaries[mi] if len(boundaries) > mi
                                     else phrase.start if measure_number == phrase.first_bar else None)
                    if measure_start is None:
                        continue
                    absolute = measure_start + float(relative)
                    if not phrase.start - 1e-7 <= absolute < phrase.end - 1e-7:
                        continue
                    types = child.findall("direction-type")
                    if not types:
                        continue
                    rendered = ET.Element("direction", {
                        k: v for k,v in child.attrib.items() if k in ("placement","directive")})
                    for kind in types:
                        rendered.append(deepcopy(kind))
                    ET.SubElement(rendered, "offset").text = str(
                        round(float(relative)*10080))
                    index = next((i for i, node in enumerate(dest_measure)
                                  if node.tag not in {"attributes","barline"}),len(dest_measure))
                    dest_measure.insert(index, rendered)
                    unrendered.update("direction:" + type_.tag
                                      for group in types for type_ in group)
    return ET.tostring(output, encoding="unicode"), tuple(sorted(unrendered))
