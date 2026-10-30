"""Project authored tied-mark attributes onto exact regenerated tie endpoints.

The imported piano note merges sounding tie chains, while the lesson engraver
recreates their written note segments. Match a source endpoint only when its
original source attack identity, source clock and generated tie role agree.
Do not invent a tie, change a note or attach an attribute to another chord
tone. Complex styling stays an explicit native-rendering fallback obligation.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction
from xml.etree import ElementTree as ET


def _pitch(note: ET.Element) -> int:
    element = note.find("pitch")
    step = element.findtext("step")
    return ((int(element.findtext("octave")) + 1) * 12
            + dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)[step]
            + int(element.findtext("alter", "0")))


def project_authored_ties(source_parts: list[ET.Element],
                          generated: ET.Element, bindings: dict,
                          phrase, boundaries: tuple[float, ...]
                          ) -> set[str]:
    candidates = defaultdict(list)
    for note in generated.findall(".//note[@id]"):
        binding = bindings.get(note.get("id"))
        if not binding:
            continue
        start = phrase.start + float(binding["display_beat"])
        duration = float(Fraction(note.findtext("duration", "0"), 10080))
        candidates[binding["source_id"]].append((start, start + duration, note))

    unsupported = set()
    for pi, part in enumerate(source_parts):
        divisions = Fraction(1)
        live = {}
        for mi, measure in enumerate(part.findall("measure")):
            cursor = Fraction(0)
            previous = Fraction(0)
            for ordinal, note in enumerate(measure):
                if note.tag == "attributes":
                    if note.find("divisions") is not None:
                        divisions = Fraction(note.findtext("divisions"))
                    continue
                if note.tag in ("backup", "forward"):
                    delta = Fraction(note.findtext("duration", "0"), 1)
                    cursor += (-delta if note.tag == "backup" else delta)
                    previous = cursor
                    continue
                if note.tag != "note" or note.find("grace") is not None:
                    continue
                duration = Fraction(note.findtext("duration", "0")) / divisions
                chord = note.find("chord") is not None
                onset = previous if chord else cursor
                if not chord:
                    cursor += duration
                    previous = onset
                if note.find("pitch") is None:
                    continue
                key = (pi, note.findtext("staff", "1"),
                       note.findtext("voice", "1"), _pitch(note))
                tie_types = {mark.get("type") for mark in note.findall("tie")}
                if not tie_types:
                    tie_types = {mark.get("type") for mark in note.findall("notations/tied")}
                own_id = f"xml-p{pi}-m{mi}-e{ordinal}"
                origin = live.get(key) if "stop" in tie_types else own_id
                if origin is None:
                    continue
                if "start" in tie_types:
                    live[key] = origin
                elif "stop" in tie_types:
                    live.pop(key, None)

                if mi >= len(boundaries):
                    continue
                start = float(Fraction(str(boundaries[mi])) + onset)
                end = start + float(duration)
                for authored in note.findall("notations/tied"):
                    role = authored.get("type")
                    if role not in ("start", "stop"):
                        continue
                    matches = []
                    for generated_start, generated_end, rendered in candidates.get(origin, ()):
                        boundary = generated_end if role == "start" else generated_start
                        target = end if role == "start" else start
                        if abs(boundary - target) > 1e-6:
                            continue
                        for target_mark in rendered.findall("notations/tied"):
                            if target_mark.get("type") == role:
                                matches.append(target_mark)
                    if len(matches) != 1:
                        # A simplified passage can omit one side of a tie.
                        # Retain the generated duration-based tie policy.
                        if matches or any(x != "type" for x in authored.attrib):
                            unsupported.add("note:tied")
                        continue
                    dest = matches[0]
                    for name, value in authored.attrib.items():
                        if name != "type":
                            dest.set(name, value)
                            if name not in {"placement"}:
                                unsupported.add("note:tied")
                    if len(authored):
                        # No native renderer for arbitrary styled tie content.
                        for child in authored:
                            dest.append(ET.fromstring(ET.tostring(child)))
                        unsupported.add("note:tied")
    return unsupported
