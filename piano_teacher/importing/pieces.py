"""Source importer for the embedded desktop application.

MIDI (.mid, .midi) is read directly. MusicXML (.musicxml, .xml, .mxl) is
converted to the same performance timeline first, so practice, grading,
fingering and saved progress always use one canonical source model.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, is_zipfile

from ..music import (
    ClefChange,
    KeySignature,
    Note,
    PerformanceNotes,
    Piece,
    load_midi,
    piece_from_performance,
)

MIDI_FORMATS = frozenset({".mid", ".midi"})
MUSICXML_FORMATS = frozenset({".musicxml", ".xml", ".mxl"})
SOURCE_FORMATS = MIDI_FORMATS | MUSICXML_FORMATS


def import_piece(path: str | Path, *, data: bytes | None = None) -> Piece:
    """Load one canonical source with no secondary notation owner."""
    path = Path(path).expanduser()
    if data is None:
        path = path.resolve()
        if not path.is_file():
            raise ValueError(f"No file found: {path}")
    suffix = path.suffix.lower()
    if suffix not in SOURCE_FORMATS:
        raise ValueError("Only MIDI (.mid, .midi) and MusicXML (.musicxml, .xml, .mxl) can be imported")
    if data is None:
        data = path.read_bytes()
    if suffix in MUSICXML_FORMATS:
        return load_musicxml(path, data)
    return load_midi(path, data=data)


def load_musicxml(path: Path, data: bytes) -> Piece:
    """Project music21's performed occurrences with their written source objects."""
    from music21.musicxml.xmlToM21 import MusicXMLImporter
    try:
        data, warnings = _score_bytes(data)
        root = ET.fromstring(data)
        for element in root.iter():
            element.tag = element.tag.rsplit("}", 1)[-1]
        if root.tag != "score-partwise":
            raise ValueError("Only score-partwise MusicXML is supported")
        written = _index_notes(root)
        reader = MusicXMLImporter()
        reader.xmlRootToScore(root, reader.stream)
    except Exception as exc:
        raise ValueError(f"Cannot read MusicXML: {exc}") from exc
    return _performed_piece(reader.stream, written, path, warnings)


def _score_bytes(data):
    snapshot = BytesIO(data)
    if not is_zipfile(snapshot):
        return data, set()
    with ZipFile(snapshot) as archive:
        first = next((name for name in archive.namelist() if "META-INF" not in name
                      and Path(name).suffix in MUSICXML_FORMATS), None)
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            roots = container.findall(".//{*}rootfile")
            selected = next((node for node in roots if node.get("media-type") ==
                "application/vnd.recordare.musicxml+xml"), roots[0]).attrib["full-path"]
            declared = archive.read(selected)
        except (ET.ParseError, KeyError, IndexError):
            if first is None:
                raise ValueError("Compressed MusicXML has no score document") from None
            return archive.read(first), {"Missing or unusable MXL manifest; read the first score document."}
        if first and first != selected:
            historical = archive.read(first)
            try:
                root = ET.fromstring(historical)
            except ET.ParseError:
                return declared, set()
            if root.tag.rsplit("}", 1)[-1] == "score-partwise":
                return historical, {"Multiple score documents; opened the original import selection."}
        return declared, set()


def _index_notes(root):
    written = {}
    for pi, part in enumerate(root.findall("part"), 1):
        divisions = 1
        for mi, measure in enumerate(part.findall("measure"), 1):
            for ordinal, note in enumerate(measure):
                if note.tag == "attributes":
                    divisions = int(note.findtext("divisions", str(divisions)))
                if note.tag != "note":
                    continue
                identifier = f"xml-p{pi}-m{mi}-n{ordinal}"
                written[identifier] = ET.tostring(note, encoding="unicode"), divisions
                # music21 does not import MusicXML note IDs. Its public
                # editorial reference survives staff splitting, chord
                # assembly and repeats, including each individual tone.
                # Keep the original note intact in the lookup above.
                level = note.find("level")
                if level is None:
                    level = ET.SubElement(note, "level")
                level.text = identifier
    return written


def _written_id(element):
    for reference in (*element.editorial.footnotes, *element.editorial.comments):
        if reference.levelInformation:
            return reference.levelInformation
    return ""


def _without_repeats(score):
    from music21 import bar, repeat
    plain = score.coreCopyAsDerivation("withoutRepeats")
    for measure in plain.recurse().getElementsByClass("Measure"):
        for side in ("leftBarline", "rightBarline"):
            if isinstance(getattr(measure, side), bar.Repeat):
                setattr(measure, side, bar.Barline("regular"))
        for mark in list(measure.getElementsByClass(repeat.RepeatExpression)):
            measure.remove(mark)
    from music21 import spanner
    for site in plain.recurse(includeSelf=True, streamsOnly=True):
        for bracket in list(site.getElementsByClass(spanner.RepeatBracket)):
            site.remove(bracket)
    return plain


def _written_sources(score, written, warnings):
    """Attach stable written location and untimed ornaments before repeat expansion."""
    from music21 import stream

    for part in score.parts:
        for measure in part.getElementsByClass(stream.Measure):
            for lane in [measure, *measure.voices]:
                _anchor_graces(lane, written, warnings)


def _anchor_graces(lane, written, warnings):
    pending = []
    for element in list(lane.notesAndRests):
        if element.duration.isGrace:
            markup = written.get(_written_id(element), ("", 0))[0]
            pending.append(markup if element.isNote and element.duration.type in ("eighth", "16th") else "")
            lane.remove(element)
        elif pending:
            if element.isRest:
                warnings.add("Grace notes before rests are not displayed.")
            elif len(pending) == 1 and pending[0]:
                element.editorial.graceBefore = pending[0]
            else:
                warnings.add("Chordal, grouped or unusual-duration grace notes are not displayed.")
            pending.clear()
    if pending:
        warnings.add("Grace notes without a following attack are not displayed.")


def _performed_piece(score, written, path, warnings):
    from music21 import defaults, key, meter, repeat, tempo
    from music21.midi import ChannelVoiceMessages, translate

    _written_sources(score, written, warnings)
    try:
        performed = translate.prepareStreamForMidi(score)
    except repeat.ExpanderException:
        warnings.add("Malformed repeats were read once as written.")
        performed = translate.prepareStreamForMidi(_without_repeats(score))

    parts, packets, ordinals, names = _schedule(performed)
    ticks = defaults.ticksPerQuarter
    changes, tempos, keys, fingers = [], [], [], []
    notes = PerformanceNotes(ticks)
    occurrence = defaultdict(int)
    last_tick = 0
    for packet in packets:
        track, tick = packet["trackId"], packet["offset"]
        event, element = packet["midiEvent"], packet.get("obj")
        last_tick = max(last_tick, tick)
        ordinal = ordinals[track]
        ordinals[track] += 1
        if isinstance(element, meter.TimeSignature):
            changes.append((tick / ticks, element.numerator, element.denominator))
        elif isinstance(element, tempo.MetronomeMark):
            tempos.append((tick, int.from_bytes(event.data, "big")))
        elif isinstance(element, key.KeySignature):
            keys.append(KeySignature(tick / ticks, element.sharps,
                                     mode="minor" if getattr(element, "mode", None) == "minor" else "major"))
        elif event.type in (ChannelVoiceMessages.NOTE_ON, ChannelVoiceMessages.NOTE_OFF) and event.channel != 10:
            channel, pitch = event.channel - 1, event.pitch
            if event.type == ChannelVoiceMessages.NOTE_ON and event.velocity:
                source_id = f"midi-t{track}-e{ordinal}"
                note, finger = _attack(packet, source_id, written, occurrence, warnings, ticks)
                notes.attack(note, tick)
                if finger:
                    fingers.append((source_id, finger))
            else:
                notes.release(track, channel, pitch, tick)
    notes.finish()
    piece = piece_from_performance(path, notes.notes, names, changes, tempos, keys,
        last_tick + defaults.ticksAtStart, ticks, 60, 2, notes.warnings, "musicxml")
    clefs = _source_clefs(piece, parts, warnings)
    return replace(piece, authored_fingerings=tuple(fingers), clef_changes=clefs,
                   import_warnings=(*piece.import_warnings, *sorted(warnings)))


def _schedule(performed):
    from music21.midi import translate
    # The same music21 scheduling primitives that assigned historical ordinal
    # IDs retain the source object on every packet. No SMF is written or read.
    programs, dynamic_channels = translate.channelInstrumentData(performed)
    parts = list(performed.parts)
    for part in parts:
        part.stripTies(inPlace=True, matchByPitch=True)
    tracks = translate.packetStorageFromSubstreamList(parts)
    translate.updatePacketStorageWithChannelInfo(tracks, programs)
    channels = {track: value["initChannel"] for track, value in tracks.items()}
    packets = translate.assignPacketsToChannels(
        [packet for value in tracks.values() for packet in value["rawPackets"]],
        channelByInstrument=programs, channelsDynamic=dynamic_channels,
        initTrackIdToChannelMap=channels)

    ordinals, names = {}, {}
    for track, value in tracks.items():
        instrument = value["initInstrument"]
        names[track] = (instrument.bestName() or "") if instrument else ""
        prefix = translate.getStartEvents(channel=channels[track], instrumentObj=instrument)
        ordinals[track] = sum(not event.isDeltaTime() for event in prefix)

    return parts, packets, ordinals, names


def _attack(packet, source_id, written, occurrence, warnings, ticks):
    track, tick, element = packet["trackId"], packet["offset"], packet["obj"]
    event = packet["midiEvent"]
    pitch = event.pitch
    authored_finger = None
    # A chord can contain enharmonic unisons. Bind each member
    # once, in source order, even when its sounding pitch repeats.
    members = [i for i, p in enumerate(element.pitches) if p.midi == pitch]
    index = occurrence[id(element), pitch]
    occurrence[id(element), pitch] += 1
    if index >= len(members):
        warnings.add("An expanded attack has no unambiguous written source.")
        return Note(tick/ticks, (tick+packet["duration"])/ticks, pitch, track,
                    event.channel-1, source_id=source_id, voice=f"midi-t{track}-c{event.channel-1}",
                    velocity=event.velocity), None
    member = members[index]
    written_pitch = element.pitches[member]
    alter = written_pitch.accidental.alter if written_pitch.accidental else 0
    spelling = ((written_pitch.step, int(alter), written_pitch.octave)
                if float(alter).is_integer() and written_pitch.ps == pitch else None)
    component = element.notes[member] if element.isChord else element
    written_id = _written_id(component)
    markup, divisions = written.get(written_id, ("", 0))
    source = ET.fromstring(markup) if markup else None
    if source is not None:
        finger = source.findtext("notations/technical/fingering")
        if finger is not None and finger.strip() in ("1", "2", "3", "4", "5"):
            authored_finger = int(finger)
    else:
        warnings.add("An expanded attack has no unambiguous written source.")
    voice = source.findtext("voice", "1") if source is not None else "1"
    note = Note(tick/ticks, (tick+packet["duration"])/ticks, pitch, track, event.channel-1,
                source_id=source_id, voice=f"xml-t{track}-v{voice}",
                spelling=spelling, velocity=event.velocity, written_id=written_id,
                written_note=markup, written_divisions=divisions,
                grace_before=getattr(element.editorial, "graceBefore", "") if member == 0 else "")
    return note, authored_finger


def _source_clefs(piece, parts, warnings):
    from music21 import clef
    hands = defaultdict(set)
    for note in piece.notes:
        hands[note.track].add(note.hand)
    clefs = []
    for track, part in enumerate(parts):
        if len(hands[track]) != 1:
            continue
        for mark in part.recurse().getElementsByClass(clef.Clef):
            beat = float(mark.getOffsetInHierarchy(part))
            if (beat not in piece.bar_boundaries or mark.sign not in ("F", "G", "C")
                    or mark.line not in range(1, 6) or mark.octaveChange not in (-1, 0, 1)):
                warnings.add("A clef change cannot be displayed on the current practice grid.")
                continue
            clefs.append(ClefChange(beat, mark.sign, mark.line, mark.octaveChange,
                                    next(iter(hands[track]))))
    return tuple(dict.fromkeys(clefs))
