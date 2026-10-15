"""Read source MusicXML attacks and explicit measure structure without quantizing.

Music21 remains the notation reader at the public import seam. This source
parser preserves the XML's voice/staff, duration, spelling and measure data that
normalization can otherwise merge or omit before grading receives the events.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET
import zipfile

from .music import Note, Piece, KeySignature, ClefChange, _assign_hands, _named_hand, _phrases


def _xml_root(path: Path):
    try:
        if path.suffix.lower() == '.mxl':
            with zipfile.ZipFile(path) as archive:
                container = ET.fromstring(archive.read('META-INF/container.xml'))
                rootfile = next((element.get('full-path') for element in container.iter()
                                 if element.tag.rsplit('}', 1)[-1] == 'rootfile'), None)
                if not rootfile:
                    raise ValueError('Compressed MusicXML has no declared score rootfile')
                root = ET.fromstring(archive.read(rootfile))
        else:
            root = ET.parse(path).getroot()
    except (ET.ParseError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError(f'Cannot read source MusicXML: {exc}') from exc
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'score-partwise':
        raise ValueError('Unsupported MusicXML layout; export a score-partwise document')
    return root


def _number(text, label, *, integer=False):
    try:
        value = Fraction(text)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(f'Invalid MusicXML {label}: {text}') from exc
    if integer and value.denominator != 1:
        raise ValueError(f'Unsupported microtonal MusicXML {label}: {text}')
    return int(value) if integer else value


def load_musicxml(path: Path, *, bpm: int) -> Piece:
    root = _xml_root(path)
    names = {part.get('id'): part.findtext('part-name', '')
             for part in root.findall('./part-list/score-part')}
    notes = []
    tracks = {}
    track_names = {}
    source_staffs = {}
    metadata = []
    signatures = {}
    grid = None

    def track_for(part_index, staff, name):
        binding = part_index, staff
        if binding not in tracks:
            tracks[binding] = len(tracks)
            track_names[tracks[binding]] = name
        return tracks[binding]

    for part_index, part in enumerate(root.findall('part')):
        name = names.get(part.get('id'), '')
        divisions = Fraction(1)
        offset = Fraction(0)
        part_grid = [Fraction(0)]
        ties = {}
        source_staffs[part_index] = set()
        for measure_index, measure in enumerate(part.findall('measure')):
            cursor = extent = Fraction(0)
            previous_note = None
            for ordinal, element in enumerate(measure):
                if element.tag == 'attributes':
                    if element.find('divisions') is not None:
                        divisions = _number(element.findtext('divisions'), 'divisions')
                        if divisions <= 0:
                            raise ValueError('MusicXML divisions must be positive')
                    if element.find('transpose') is not None:
                        transposition = element.find('transpose')
                        if any(_number(transposition.findtext(field, '0'), 'transposition') != 0
                               for field in ('chromatic', 'octave-change')):
                            raise ValueError('Unsupported transposing MusicXML part; export concert piano pitches')
                    for time in element.findall('time'):
                        if cursor:
                            raise ValueError('Unsupported mid-measure meter change')
                        beats = time.findall('beats')
                        types = time.findall('beat-type')
                        if len(beats) != 1 or len(types) != 1:
                            raise ValueError('Unsupported compound MusicXML meter declaration')
                        numerator = _number(beats[0].text, 'meter numerator', integer=True)
                        denominator = _number(types[0].text, 'meter denominator', integer=True)
                        if numerator <= 0 or denominator <= 0:
                            raise ValueError('MusicXML meter must be positive')
                        signature = numerator, denominator
                        if offset in signatures and signatures[offset] != signature:
                            raise ValueError('conflicting MusicXML meters between source parts')
                        signatures[offset] = signature
                    for key in element.findall('key'):
                        if key.find('fifths') is None:
                            raise ValueError('Unsupported nontraditional MusicXML key signature')
                        metadata.append(('key', part_index, key.get('number'), offset+cursor,
                                         _number(key.findtext('fifths'), 'key fifths', integer=True),
                                         key.findtext('mode')))
                    for clef in element.findall('clef'):
                        sign = clef.findtext('sign')
                        if sign not in ('G', 'F', 'C'):
                            raise ValueError(f'Unsupported MusicXML clef {sign}')
                        metadata.append(('clef', part_index, clef.get('number', '1'), offset+cursor,
                                         sign, _number(clef.findtext('line', '2'), 'clef line', integer=True),
                                         _number(clef.findtext('clef-octave-change', '0'), 'clef octave change', integer=True)))
                elif element.tag in ('backup', 'forward'):
                    duration = _number(element.findtext('duration'), 'cursor duration')/divisions
                    if duration <= 0:
                        raise ValueError('MusicXML cursor duration must be positive')
                    cursor += duration if element.tag == 'forward' else -duration
                    if cursor < 0:
                        raise ValueError('MusicXML backup precedes the source measure')
                    extent = max(extent, cursor)
                    previous_note = None
                elif element.tag == 'note':
                    if element.find('grace') is not None:
                        raise ValueError('Unsupported grace note: no source duration for timed assessment')
                    if element.find('unpitched') is not None:
                        raise ValueError('Unsupported unpitched note in piano material')
                    duration = _number(element.findtext('duration'), 'note duration')/divisions
                    if duration <= 0:
                        raise ValueError('MusicXML note duration must be positive')
                    voice, staff = element.findtext('voice', '1'), element.findtext('staff', '1')
                    source_staffs[part_index].add(staff)
                    track = track_for(part_index, staff, name)
                    is_chord = element.find('chord') is not None
                    if is_chord:
                        if previous_note is None or previous_note[1:] != (voice, staff):
                            raise ValueError('MusicXML chord has no matching preceding source attack')
                        onset = previous_note[0]
                    else:
                        onset = cursor
                        previous_note = onset, voice, staff
                        cursor += duration
                    extent = max(extent, onset+duration, cursor)
                    if element.find('rest') is not None:
                        if is_chord:
                            raise ValueError('MusicXML rest cannot be a chord tone')
                        continue
                    pitch_element = element.find('pitch')
                    if pitch_element is None:
                        raise ValueError('MusicXML note has neither a pitched attack nor a rest')
                    step = pitch_element.findtext('step')
                    if step not in ('C', 'D', 'E', 'F', 'G', 'A', 'B'):
                        raise ValueError(f'Invalid MusicXML pitch step {step}')
                    alter = _number(pitch_element.findtext('alter', '0'), 'pitch alteration', integer=True)
                    octave = _number(pitch_element.findtext('octave'), 'pitch octave', integer=True)
                    pitch = (octave+1)*12+{'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[step]+alter
                    if not 0 <= pitch <= 127:
                        raise ValueError('MusicXML pitch is outside the MIDI piano range')
                    spelling = step, alter, octave
                    source_voice = f'xml-p{part_index}-s{staff}-v{voice}'
                    tie_types = {tie.get('type') for tie in element.findall('tie')}
                    if not tie_types:
                        tie_types = {tie.get('type') for tie in element.findall('./notations/tied')}
                    if not tie_types <= {'start', 'stop'}:
                        raise ValueError('Unsupported MusicXML tie declaration')
                    binding = track, source_voice, pitch
                    start, end = offset+onset, offset+onset+duration
                    if 'stop' in tie_types:
                        if binding not in ties:
                            raise ValueError(f'orphan tie in MusicXML part {part_index+1}, voice {voice}, pitch {pitch}')
                        index = ties[binding]
                        if abs(notes[index].end-float(start)) > 1e-8:
                            raise ValueError(f'non-contiguous tie in MusicXML voice {voice}, pitch {pitch}')
                        notes[index] = replace(notes[index], end=float(end))
                        if 'start' not in tie_types:
                            del ties[binding]
                    else:
                        if binding in ties:
                            raise ValueError(f'unterminated MusicXML tie before another attack in voice {voice}')
                        identifier = f'xml-p{part_index}-m{measure_index}-e{ordinal}'
                        notes.append(Note(float(start), float(end), pitch, track, 0,
                                          source_id=identifier, voice=source_voice, spelling=spelling))
                        if 'start' in tie_types:
                            ties[binding] = len(notes)-1
            if extent <= 0:
                raise ValueError('MusicXML source measure has no explicit rhythmic duration')
            offset += extent
            part_grid.append(offset)
        if ties:
            raise ValueError(f'unterminated MusicXML tie in part {part_index+1}')
        if grid is not None and part_grid != grid:
            raise ValueError('conflicting MusicXML measure grids between source parts')
        grid = part_grid
    if not notes or grid is None:
        raise ValueError('The score has no playable notes')
    # Explicit names win over register, including crossed LH/RH material.
    # A source piano grand staff supplies conventional upper/lower roles.
    for (part_index, staff), track in tracks.items():
        name = track_names[track]
        if len(source_staffs[part_index]) == 2 and _named_hand(name) is None:
            track_names[track] = 'Right hand' if staff == '1' else 'Left hand'
    notes = _assign_hands(notes, track_names, 60)
    hands = {}
    for note in notes:
        hands.setdefault(note.track, set()).add(note.hand)
    keys, clefs = [], []
    for kind, part_index, staff, beat, *values in metadata:
        chosen = [track for (part, source_staff), track in tracks.items()
                  if part == part_index and (staff is None or source_staff == staff)]
        role = set().union(*(hands.get(track, {_named_hand(track_names[track])}) for track in chosen)) - {None}
        if not role:
            continue  # No active or explicitly named hand for this empty source staff.
        hand = next(iter(role)) if len(role) == 1 else 'both'
        if kind == 'key':
            keys.append(KeySignature(float(beat), values[0], hand, values[1]))
        else:
            clefs.append(ClefChange(float(beat), values[0], values[1], values[2], hand))
    notes.sort(key=lambda note: (note.start, note.pitch, note.track))
    boundaries = tuple(float(beat) for beat in grid)
    changes = tuple((float(beat), *signature) for beat, signature in sorted(signatures.items()))
    return Piece(path.stem, bpm, tuple(notes), _phrases(notes, list(boundaries), 2),
                 bar_boundaries=boundaries, time_signatures=changes,
                 key_signatures=tuple(dict.fromkeys(keys)), clef_changes=tuple(dict.fromkeys(clefs)))
