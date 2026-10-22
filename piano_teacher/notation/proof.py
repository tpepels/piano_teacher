"""Independent Phase 1 score-contract audit.

The oracle reads the ORIGINAL MusicXML with ElementTree and its own cursor/tie
accounting. It does not call the application's MusicXML importer, transcription
code, note-binding validator, or native score-model parser.

Two separate questions are checked:
  * Are the source's performed pitches, written spellings, timings and explicit
    measure attributes still present in the model?
  * Does the native model contain the complete symbol inventory of the actual
    generated MusicXML given to Verovio?

Neither check establishes correct *pixels*. The Phase 2 native compositor
audit must independently check displayed glyph geometry and visibility.

The legacy Phase 1 gates below retain their original attack/inventory scope.
Phase 3's original written-event comparisons, coverage ledger and unsupported
source inventory are implemented in semantic_contract.py using this reader.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from xml.etree import ElementTree as ET


SEMITONES = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


@dataclass(frozen=True)
class WrittenScore:
    notes: tuple[tuple, ...]
    symbols: tuple[dict, ...]
    meter: tuple[tuple, ...]
    keys: tuple[tuple, ...]
    clefs: tuple[tuple, ...]
    bars: tuple[float, ...]
    measures: tuple[dict, ...] = ()
    uncovered: tuple[dict, ...] = ()
    issues: tuple[dict, ...] = ()


def _hand(part_id: str, part_name: str, part_index: int, staff: str) -> str:
    # A separate LH part uses local staff number 1; it is still the left
    # hand. An original single grand-staff part uses staff number 2 for LH.
    if staff == "2" or part_id == "LH" or "left" in part_name.lower():
        return "left"
    if part_id == "RH" or "right" in part_name.lower():
        return "right"
    return "right" if part_index == 0 else "left"


def _q(value) -> float:
    return round(float(value), 8)


def read_written_score(xml: str, *, strict: bool = True) -> WrittenScore:
    """Read MusicXML facts without using any piano_teacher parser.

    The score must be partwise. Tracks voices with MusicXML backup/forward and
    chord semantics; collapses tied continuation notes into held source notes.
    Unsupported attributes, percussion and grace notes are retained in
    ``uncovered`` and must not be claimed as compared. ``strict=False`` retains
    malformed generated tie/empty-measure facts for discrepancy reporting.
    """
    root = ET.fromstring(xml)
    for element in root.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    if root.tag != "score-partwise":
        raise ValueError("Notation proof requires score-partwise MusicXML")
    names = {p.get("id"): p.findtext("part-name", "")
             for p in root.findall("./part-list/score-part")}
    parts = root.findall("part")
    if not parts:
        raise ValueError("No MusicXML parts")
    count = max(len(p.findall("measure")) for p in parts)
    lengths = [Fraction(0) for _ in range(count)]
    raw = []
    meters, keys, clefs = [], [], []
    structures, uncovered, issues = [], [], []
    segment_ids = set()
    for part_index, part in enumerate(parts):
        division = 1
        pid = part.get("id", "")
        name = names.get(pid, "")
        current_meter = None
        current_keys, current_clefs = {}, {}
        part_start = Fraction(0)
        for bar_index, bar in enumerate(part.findall("measure")):
            initial_meter = current_meter
            initial_keys = current_keys.copy()
            initial_clefs = current_clefs.copy()
            position = Fraction(0)
            high_water = Fraction(0)
            last_onset = None
            label = bar.get("number", str(bar_index + 1))
            metadata = []
            for ordinal, element in enumerate(bar):
                identity = dict(id=f"xml-p{part_index}-m{bar_index}-e{ordinal}",
                                xml_id=element.get("id"), part=pid,
                                part_index=part_index, measure=label,
                                measure_index=bar_index,
                                staff=element.findtext("staff", "1"),
                                voice=element.findtext("voice", "1"),
                                ordinal=ordinal)
                if element.tag == "attributes":
                    for attribute in element:
                        if attribute.tag not in ("divisions", "time", "key", "clef"):
                            uncovered.append(dict(source={**identity, "voice": None, "staff": None},
                                construct=attribute.tag,
                                reason=f"MusicXML attribute {attribute.tag} is not compared",
                                xml=ET.tostring(attribute, encoding="unicode")))
                    div = element.findtext("divisions")
                    if div is not None:
                        division = int(div)
                        if division <= 0:
                            raise ValueError("Nonpositive MusicXML divisions")
                    for time in element.findall("time"):
                        current_meter = (int(time.findtext("beats")),
                                         int(time.findtext("beat-type")))
                        meters.append((bar_index, current_meter))
                        metadata.append(dict(kind="meter", onset=_q(position), value=current_meter,
                            hand=None, source={**identity, "voice": None, "staff": None}))
                    for key in element.findall("key"):
                        current_keys[key.get("number", "1")] = int(key.findtext("fifths", "0"))
                        metadata.append(dict(kind="key", onset=_q(position),
                                             staff=key.get("number", "1"),
                                             hand=_hand(pid, name, part_index, key.get("number", "1")),
                                             source={**identity, "voice": None, "staff": key.get("number", "1")},
                                             value=current_keys[key.get("number", "1")]))
                        keys.append((bar_index, _hand(pid, name, part_index,
                                        key.get("number", "1")),
                                     int(key.findtext("fifths", "0"))))
                    for clef in element.findall("clef"):
                        current_clefs[clef.get("number", "1")] = (
                            clef.findtext("sign"), int(clef.findtext("line", "2")),
                            int(clef.findtext("clef-octave-change", "0")))
                        metadata.append(dict(kind="clef", onset=_q(position),
                                             staff=clef.get("number", "1"),
                                             hand=_hand(pid, name, part_index, clef.get("number", "1")),
                                             source={**identity, "voice": None, "staff": clef.get("number", "1")},
                                             value=current_clefs[clef.get("number", "1")]))
                        clefs.append((bar_index, _hand(pid, name, part_index,
                                          clef.get("number", "1")),
                                      clef.findtext("sign"),
                                      int(clef.findtext("line", "2")),
                                      int(clef.findtext("clef-octave-change", "0"))))
                    continue
                if element.tag in ("backup", "forward"):
                    length = Fraction(int(element.findtext("duration")), division)
                    position += length if element.tag == "forward" else -length
                    last_onset = None
                    if position < 0:
                        raise ValueError("Negative MusicXML voice cursor")
                    high_water = max(high_water, position)
                    continue
                if element.tag != "note":
                    if element.tag not in ("print",):
                        uncovered.append(dict(source=identity, construct=element.tag,
                                              reason="Outside timed written-event contract"))
                    continue
                identifier = element.get("id")
                if identifier:
                    if identifier in segment_ids:
                        issues.append(dict(source=identity, reason=f"Duplicate written segment identity: {identifier}"))
                    segment_ids.add(identifier)
                if element.find("grace") is not None:
                    uncovered.append(dict(source=identity, construct="grace_notes",
                                          reason="Untimed ornament not compared by this contract"))
                    continue
                if element.find("unpitched") is not None:
                    uncovered.append(dict(source=identity, construct="unpitched_notes",
                                          reason="Unpitched notation is not supported"))
                    duration = Fraction(element.findtext("duration", "0")) / division
                    position += duration
                    high_water = max(high_water, position)
                    continue
                duration_text = element.findtext("duration")
                if duration_text is None:
                    raise ValueError("Missing MusicXML duration")
                duration = Fraction(int(duration_text), division)
                chord = element.find("chord") is not None
                if chord and last_onset is None:
                    raise ValueError("Chord without preceding onset")
                onset = last_onset if chord else position
                if not chord:
                    last_onset = position
                    position += duration
                high_water = max(high_water, onset + duration, position)
                staff = _hand(pid, name, part_index, element.findtext("staff", "1"))
                spelling = None
                pitch = None
                pitched = element.find("pitch")
                if pitched is not None:
                    step = pitched.findtext("step")
                    if step not in SEMITONES:
                        raise ValueError("Invalid pitch step in source")
                    alteration = Fraction(pitched.findtext("alter", "0"))
                    if alteration.denominator != 1:
                        raise ValueError("Unsupported microtonal source pitch")
                    alter = int(alteration)
                    octave = int(pitched.findtext("octave"))
                    spelling = (step, alter, octave)
                    pitch = (octave + 1) * 12 + SEMITONES[step] + alter
                elif element.find("rest") is None:
                    raise ValueError("Unsupported unpitched XML event")
                modification = element.find("time-modification")
                sound_ties = {t.get("type") for t in element.findall("tie")}
                written_ties = {t.get("type") for t in element.findall("notations/tied")}
                if sound_ties and written_ties and sound_ties != written_ties:
                    issues.append(dict(source=identity, reason="Sound and written ties disagree"))
                tie_types = sound_ties or written_ties
                for mark in element.findall("notations/*"):
                    if mark.tag not in ("tied", "tuplet"):
                        uncovered.append(dict(source=identity, construct=mark.tag,
                                              reason="Source notation outside this contract"))
                raw.append(dict(
                    index=bar_index, measure=(int(label) if label.lstrip("-").isdigit()
                                              else bar_index + 1),
                    source=identity, part=pid, part_index=part_index,
                    raw_staff=identity["staff"],
                    onset=onset, duration=duration, staff=staff,
                    voice=element.findtext("voice", "1"), pitch=pitch,
                    spelling=spelling, id=element.get("id"),
                    kind="note" if pitched is not None else "rest",
                    note_type=element.findtext("type"),
                    dots=len(element.findall("dot")), chord=chord,
                    tie_start="start" in tie_types, tie_stop="stop" in tie_types,
                    tied_marks=tuple(tuple(sorted(t.attrib.items()))
                                     for t in element.findall("notations/tied")),
                    beams=tuple((t.get("number", "1"), (t.text or "").strip(),
                                 tuple(sorted((k, v) for k, v in t.attrib.items() if k != "number")))
                                for t in element.findall("beam")),
                    accidental=element.findtext("accidental"),
                    time_modification=(
                        (int(modification.findtext("actual-notes")),
                         int(modification.findtext("normal-notes")))
                        if modification is not None else None),
                    tuplet_marks=tuple((t.get("type"), t.get("number", "1"),
                                        t.get("bracket", "no"),
                                        t.get("show-number", "actual"))
                                       for t in element.findall("notations/tuplet")),
                    tuplet_extras=tuple(tuple(sorted((k, v) for k, v in t.attrib.items()
                        if k not in ("type", "number", "bracket", "show-number")))
                        for t in element.findall("notations/tuplet")),
                    visible=element.get("print-object") != "no",
                ))
            lengths[bar_index] = max(lengths[bar_index], high_water)
            structures.append(dict(
                source=dict(id=f"xml-p{part_index}-m{bar_index}", part=pid,
                            part_index=part_index, measure=label,
                            measure_index=bar_index, staff=None, voice=None),
                index=bar_index, label=label, part=pid, part_index=part_index,
                start_beat=_q(part_start), end_beat=_q(part_start + high_water),
                duration=_q(high_water), meter=current_meter,
                keys={_hand(pid, name, part_index, s): value for s, value in current_keys.items()},
                clefs={_hand(pid, name, part_index, s): value for s, value in current_clefs.items()},
                metadata=metadata, implicit=bar.get("implicit", "no")))
            structures[-1].update(initial_meter=initial_meter,
                initial_keys={_hand(pid, name, part_index, s): v for s, v in initial_keys.items()},
                initial_clefs={_hand(pid, name, part_index, s): v for s, v in initial_clefs.items()})
            part_start += high_water
    boundaries = [Fraction(0)]
    for length in lengths:
        if length <= 0:
            if strict:
                raise ValueError("Empty source measure")
        boundaries.append(boundaries[-1] + length)
    for entry in raw:
        entry["beat"] = boundaries[entry["index"]] + entry["onset"]
    source_notes = []
    open_ties = {}
    for entry in sorted(raw, key=lambda e: (e["beat"], e["index"])):
        if entry["kind"] != "note":
            continue
        tie_key = (entry["part_index"], entry["raw_staff"], entry["voice"], entry["pitch"])
        end = entry["beat"] + entry["duration"]
        if entry["tie_stop"]:
            if tie_key not in open_ties:
                if strict:
                    raise ValueError("Orphan source tie")
                issues.append(dict(source=entry["source"], reason="Orphan source tie"))
                index = len(source_notes)
                source_notes.append(dict(staff=entry["staff"], pitch=entry["pitch"],
                                         spelling=entry["spelling"], beat=entry["beat"],
                                         end=end, source=entry["source"]))
            else:
                index = open_ties[tie_key]
                if source_notes[index]["end"] != entry["beat"]:
                    if strict:
                        raise ValueError("Non-contiguous source tie")
                    issues.append(dict(source=entry["source"], reason="Non-contiguous source tie"))
                source_notes[index]["end"] = end
        else:
            index = len(source_notes)
            source_notes.append(dict(
                staff=entry["staff"], pitch=entry["pitch"],
                spelling=entry["spelling"], beat=entry["beat"], end=end,
                source=entry["source"]))
        entry["attack_id"] = source_notes[index]["source"]["id"]
        if entry["tie_start"]:
            open_ties[tie_key] = index
        else:
            open_ties.pop(tie_key, None)
    if open_ties:
        if strict:
            raise ValueError("Unterminated source tie")
        for index in open_ties.values():
            issues.append(dict(source=source_notes[index]["source"], reason="Unterminated source tie"))
    canonical = tuple(sorted((
        n["staff"], _q(n["beat"]), _q(n["end"] - n["beat"]),
        n["pitch"], n["spelling"]) for n in source_notes
    ))
    return WrittenScore(canonical, tuple(raw), tuple(meters), tuple(keys),
                        tuple(clefs), tuple(_q(x) for x in boundaries),
                        tuple(structures), tuple(uncovered), tuple(issues))


def _native_notes(model: dict) -> Counter:
    return Counter((
        n["hand"], _q(n["onset_beats"]), _q(n["duration_beats"]),
        int(n["midi_pitch"]), tuple(n["spelling"]) if n["spelling"] else None
    ) for n in model["notes"])


def _difference(name: str, expected: Counter, actual: Counter) -> list[str]:
    missing = expected - actual
    extra = actual - expected
    problems = []
    for label, difference in (("missing", missing), ("extra", extra)):
        if difference:
            examples = list(difference.items())[:4]
            problems.append(f"{name}: {label} {sum(difference.values())}; examples={examples}")
    return problems


def verify_original_musicxml(source_xml: str, native_model: dict) -> dict:
    """Independent source-versus-native semantic gate (original/full score).

    Exercise simplifications intentionally change the notes, so the caller
    MUST use the original, unsimplified full-piece lesson.
    """
    original = read_written_score(source_xml)
    errors = _difference("original attacks", Counter(original.notes),
                         _native_notes(native_model))
    measures = native_model["measures"]
    if len(measures) != len(original.bars) - 1:
        errors.append(f"bar count: source={len(original.bars)-1}, native={len(measures)}")
    for i, measure in enumerate(measures[:len(original.bars)-1]):
        if _q(measure["start_beat"]) != original.bars[i] or (
                _q(measure["end_beat"]) != original.bars[i + 1]):
            errors.append(f"bar {i+1} boundaries disagree")
    for i, meter in original.meter:
        if i < len(measures) and tuple(measures[i]["meter"]) != meter:
            errors.append(f"bar {i+1} meter: expected {meter}")
    for i, hand, value in original.keys:
        if i < len(measures) and measures[i]["keys"].get(hand) != value:
            errors.append(f"bar {i+1} {hand} key: expected {value}")
    for i, hand, sign, line, octave in original.clefs:
        if i >= len(measures):
            continue
        c = measures[i]["clefs"].get(hand, {})
        if (c.get("sign"), c.get("line"), c.get("octave_change", 0)) != (sign, line, octave):
            errors.append(f"bar {i+1} {hand} clef: expected {(sign,line,octave)}")
    return {
        "source_attacks": len(original.notes),
        "source_measures": len(original.bars) - 1,
        "source_written_symbols": len(original.symbols),
        "errors": errors,
        "passed": not errors,
        "scope": "source pitches/durations/spelling, measure grid, explicit meter/key/clef",
    }


def _symbol(entry: dict) -> tuple:
    spell = entry["spelling"]
    if isinstance(spell, dict):
        spell = (spell["step"], int(spell["alter"]), int(spell["octave"]))
    if isinstance(entry["time_modification"], dict):
        mod = (int(entry["time_modification"]["actual"]),
               int(entry["time_modification"]["normal"]))
    else:
        mod = entry["time_modification"]
    marks = entry.get("tuplet_marks", ())
    return (
        entry["id"] if entry["kind"] == "note" else None,
        entry["kind"], entry["staff"], entry["voice"],
        int(entry["measure"]), _q(entry["beat"]), _q(entry["duration_beats"]),
        entry["pitch"], spell, entry["note_type"], int(entry["dots"]),
        bool(entry["chord"]), bool(entry["tie_start"]), bool(entry["tie_stop"]),
        entry["accidental"], mod,
        tuple((m["type"], m["number"], m["bracket"], m["show_number"])
              if isinstance(m, dict) else m for m in marks),
    )


def verify_generated_engraving(generated_xml: str, native_model: dict) -> dict:
    """Compare all native notation events with an independently parsed XML.

    Verovio receives this XML; comparing its symbol inventory catches errors
    between generated engraving and the native semantic score. Pixel fidelity
    is explicitly deferred to the visual validation phase.
    """
    written = read_written_score(generated_xml)
    expected = Counter()
    for e in written.symbols:
        if not e["visible"]:
            continue
        expected[_symbol(dict(e, duration_beats=e["duration"],
                              beat=e["beat"]))] += 1
    # Reading XML uses Fraction for beats; the model uses floats. _symbol
    # normalizes both to 8 decimal places.
    actual = Counter(_symbol(dict(e, pitch=e["midi_pitch"]))
                     for e in native_model["notation_events"])
    errors = _difference("engraving symbols", expected, actual)
    return {"expected_symbols": sum(expected.values()),
            "native_symbols": sum(actual.values()),
            "errors": errors, "passed": not errors,
            "scope": "all notes/rests, onsets, durations, staff/voice, spelling, "
                     "types/dots, ties, accidentals, tuplets and source note IDs"}
