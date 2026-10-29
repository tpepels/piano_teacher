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


# Native Godot uses original Verovio font contours for these precisely
# specified marks. Anything else stays on original Verovio-page fallback.
NATIVE_ARTICULATIONS = frozenset({"staccato", "tenuto", "accent"})
NATIVE_DYNAMICS = frozenset({"p", "pp", "ppp", "mp", "mf", "f", "ff", "fff"})
NATIVE_PEDAL_TYPES = frozenset({"start", "stop"})
NATIVE_HAIRPIN_TYPES = frozenset({"crescendo", "diminuendo", "stop"})


def _native_notation(element: ET.Element) -> bool:
    return (element.tag == "articulations"
            and len(element) == 1
            and all(tag.tag in NATIVE_ARTICULATIONS and not tag.attrib
                    for tag in element))


def _native_direction(element: ET.Element) -> bool:
    if element.tag == "dynamics":
        return len(element) == 1 and element[0].tag in NATIVE_DYNAMICS and not element[0].attrib
    if element.tag == "wedge":
        # Only ordinary matched wedge pairs. Niente, spread overrides,
        # dashed wedges and other source embellishments stay in Verovio.
        number = element.get("number", "1")
        return (element.get("type") in NATIVE_HAIRPIN_TYPES
                and number.isdigit() and 1 <= int(number) <= 128
                and set(element.attrib) <= {"type", "number"})
    if element.tag == "pedal":
        return (element.get("type") in NATIVE_PEDAL_TYPES
                and element.get("number", "1") == "1"
                and element.get("line", "no") in ("yes", "no")
                and element.get("sign", "yes") in ("yes", "no")
                and (element.get("line", "no") == "yes"
                     or element.get("sign", "yes") == "yes"))
    return False


def project_annotations(source_musicxml: str, lesson_xml: str,
                        bindings: dict, phrase, *, boundaries: tuple[float, ...],
                        fingering_sources: frozenset[str] = frozenset()
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

    # A slur may start/end on one tone of a chord. An exercise can omit that
    # specific pitch while retaining another pitch at the same source onset.
    # Reanchor the slur to the surviving chord tone, never to a later attack.
    chord_siblings = {}
    for pi, part in enumerate(source_parts):
        for mi, measure in enumerate(part.findall("measure")):
            active = []
            for ordinal, original in enumerate(measure):
                if original.tag != "note" or original.find("pitch") is None:
                    active = []
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                if original.find("chord") is None:
                    active = [sid]
                else:
                    active.append(sid)
                for member in active:
                    chord_siblings[member] = tuple(active)

    def rendered_slur_anchor(sid):
        if sid in targets:
            return sid
        return next((sibling for sibling in chord_siblings.get(sid, ())
                     if sibling in targets), None)

    # Preserve source-authored beam groups only when ALL their notes survive
    # in the same generated hand, measure and voice with the same written
    # duration. We must not silently replace explicit 8th-note beams with
    # isolated flags. Shortened lessons can legitimately lose a partial
    # group: never leave an orphan beam begin/end in those variants. The
    # primary beam owns its secondary levels/subgroups/hooks: select the
    # complete primary group, then copy each note's original marks once.
    groups = defaultdict(list)
    group_indices = defaultdict(int)
    for pi, part in enumerate(source_parts):
        for mi, measure in enumerate(part.findall("measure")):
            for ordinal, original in enumerate(measure):
                if original.tag != "note" or original.find("pitch") is None:
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                for mark in original.findall("beam"):
                    if mark.get("number", "1") != "1":
                        continue
                    group_key = (pi, mi, original.findtext("voice", "1"),
                                 original.findtext("staff", "1"),
                                 mark.get("number", "1"))
                    if (mark.text or "").strip() == "begin":
                        group_indices[group_key] += 1
                    groups[(*group_key, group_indices[group_key])].append(
                        (sid, mark.text or ""))
    for group_key, members in groups.items():
        # Each original group MUST have one begin, an end, and no splits.
        # Chord members cannot independently start beams.
        kinds = [kind.strip() for _, kind in members]
        if len(members) < 2 or kinds[0] != "begin" or kinds[-1] != "end" or (
                any(kind not in ("continue", "begin", "end")
                    or (0 < i < len(kinds)-1 and kind != "continue")
                    for i, kind in enumerate(kinds))):
            continue
        translated = []
        for sid, _kind in members:
            original = original_notes.get(sid)
            dest = targets.get(sid)
            if original is None or dest is None:
                break
            if original.find("chord") is not None or (
                    original.findtext("type") != dest.findtext("type")):
                break
            # Never attach source beams to an attack whose exercise rhythm
            # changed during simplification/quantization.
            original_duration = original.findtext("duration")
            generated_duration = dest.findtext("duration")
            if not original_duration or not generated_duration:
                break
            translated.append((dest, original, sid))
        if len(translated) != len(members):
            continue
        if len({(hands[sid], dest.findtext("voice", "1"))
                for dest, _src, sid in translated}) != 1:
            continue
        source_divisions = None
        # Source and generated division units may differ, so verify each
        # duration as a Fraction of a quarter note.
        pi, mi, *_ = group_key
        for tag in source_parts[pi].findall("measure")[mi].findall("attributes/divisions"):
            source_divisions = int(tag.text)
        if source_divisions is None:
            for prior in source_parts[pi].findall("measure")[:mi]:
                for tag in prior.findall("attributes/divisions"):
                    source_divisions = int(tag.text)
        if not source_divisions:
            continue
        valid = True
        for dest, original, _sid in translated:
            if (Fraction(int(original.findtext("duration")),source_divisions)
                    != Fraction(int(dest.findtext("duration")),10080)):
                valid = False
                break
        if not valid:
            continue
        for dest, original, _sid in translated:
            if dest.findall("beam"):
                raise ValueError("Conflicting source beam marks in generated score")
            for original_mark in original.findall("beam"):
                dest.append(deepcopy(original_mark))

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
                        first_target = rendered_slur_anchor(first)
                        last_target = rendered_slur_anchor(sid)
                        if (first_target is not None and last_target is not None
                                and hands[first_target] == hands[last_target]
                                and first_target != last_target):
                            paired_slurs.add((first, sid, key))

    unrendered = set()
    for sid, dest in targets.items():
        original = original_notes.get(sid)
        if original is None:
            continue  # MIDI source IDs have no original MusicXML decorations.
        stem = original.find("stem")
        if stem is not None:
            # Direction is authored notation, not a pitch-based layout hint.
            # Keep the binding's existing source attack/timing authoritative.
            dest.append(deepcopy(stem))
            if (stem.text or "").strip() not in {"up", "down"}:
                unrendered.add("note:stem")
        original_notations = original.find("notations")
        if original_notations is not None:
            target_notations = dest.find("notations")
            for item in original_notations:
                if item.tag == 'technical' and sid in fingering_sources:
                    # The durable original-piece plan supplies this ink in
                    # the native view, including manual replacements. Preserve
                    # every other technical mark and its fallback obligation.
                    item = deepcopy(item)
                    for finger in item.findall('fingering'):
                        item.remove(finger)
                    if not len(item):
                        continue
                if item.tag in ("tied", "tuplet"):
                    # Recomputed from the exercise's own note durations.
                    continue
                if item.tag == "slur":
                    # Inject paired source slurs after other notations, so a
                    # chord-reduced endpoint can use its retained head.
                    continue
                if target_notations is None:
                    target_notations = ET.SubElement(dest, "notations")
                target_notations.append(deepcopy(item))
                if item.tag != "slur" and not _native_notation(item):
                    unrendered.add("note:" + item.tag)
        for lyric in original.findall("lyric"):
            dest.append(deepcopy(lyric))
            unrendered.add("note:lyric")

    for first, last, key in paired_slurs:
        for sid, role in ((first, "start"), (last, "stop")):
            destination = targets[rendered_slur_anchor(sid)]
            annotations = destination.find("notations")
            if annotations is None:
                annotations = ET.SubElement(destination, "notations")
            for mark in original_notes[sid].findall("notations/slur"):
                if (mark.get("type") == role
                        and mark.get("number", "1") == key[2]):
                    annotations.append(deepcopy(mark))

    # A grace note's XML ordinal is not a graded attack. Project it only
    # when its immediately following scored note is in this lesson. This
    # applies to the same original voice/staff and cannot leak into another
    # hand or a simplified lesson with the anchor omitted.
    destination_measures = {
        id(note): measure
        for part in output.findall("part")
        for measure in part.findall("measure")
        for note in measure.findall("note")
    }
    for pi, part in enumerate(source_parts):
        pending = defaultdict(list)
        for mi, measure in enumerate(part.findall("measure")):
            for ordinal, note in enumerate(measure):
                if note.tag != "note":
                    continue
                key = (note.findtext("voice", "1"), note.findtext("staff", "1"))
                if note.find("grace") is not None:
                    pending[key].append(note)
                    continue
                group = pending.pop(key, [])
                if not group or note.find("pitch") is None:
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                target = targets.get(sid)
                if target is None:
                    continue
                parent = destination_measures[id(target)]
                if (len(group) != 1 or group[0].find("chord") is not None
                        or group[0].findtext("type") not in ("eighth", "16th")
                        or group[0].find("notations") is not None
                        or group[0].find("grace").get("slash", "no") != "no"):
                    # Verovio still receives the original markings, but the
                    # native renderer must not silently imitate complex ink.
                    unrendered.add("note:grace")
                for index, original_grace in enumerate(group):
                    added = deepcopy(original_grace)
                    added.attrib.clear()
                    added.set("id", f"pt-grace-{sid}-{index}")
                    for staff in list(added.findall("staff")):
                        added.remove(staff)
                    for voice in list(added.findall("voice")):
                        voice.text = target.findtext("voice", "1")
                    parent.insert(list(parent).index(target), added)

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
                                      for group in types for type_ in group
                                      if not _native_direction(type_) or
                                      child.get("placement", "below") != "below")
    # A partial hairpin must never appear as an arbitrary open wedge. An
    # excerpt, shortened variant, or unpaired source mark is still faithfully
    # handled by the original Verovio page instead of guessed native ink.
    hairpins = defaultdict(list)
    for (hand, number), measure in generated.items():
        for ordinal, direction in enumerate(measure.findall("direction")):
            for wedge in direction.findall("./direction-type/wedge"):
                hairpins[hand].append((
                    number, int(direction.findtext("offset", "0")), ordinal,
                    wedge.get("number", "1"), wedge.get("type", "")))
    for marks in hairpins.values():
        open_wedges = {}
        for measure, offset, ordinal, number, kind in sorted(marks):
            position = (measure, offset)
            if kind in {"crescendo", "diminuendo"}:
                if number in open_wedges:
                    unrendered.add("direction:wedge")
                open_wedges[number] = position
            elif kind == "stop":
                started = open_wedges.pop(number, None)
                if started is None or position <= started:
                    unrendered.add("direction:wedge")
            else:
                unrendered.add("direction:wedge")
        if open_wedges:
            unrendered.add("direction:wedge")

    return ET.tostring(output, encoding="unicode"), tuple(sorted(unrendered))
