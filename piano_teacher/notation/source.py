"""Immutable MusicXML provenance, independent of engraving and assessment.

The importer and lesson compiler share source IDs, not pitch-based guesses.
XML strings are individual musical events/instructions, never whole copied parts.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
from xml.etree import ElementTree as ET


def identity(value: str) -> str:
    return 'ptx' + hashlib.sha256(value.encode()).hexdigest()[:28]


def ratio(value: Fraction) -> tuple[int, int]:
    return value.numerator, value.denominator


@dataclass(frozen=True)
class SourceEvent:
    id: str
    source_id: str | None
    hand: str
    voice: str
    measure: int
    beat: tuple[int, int]
    duration: tuple[int, int]
    xml: str
    anchor_id: str = ''


@dataclass(frozen=True)
class SourceMark:
    id: str
    kind: str
    event_id: str
    hand: str
    voice: str
    beat: tuple[int, int]
    xml: str


@dataclass(frozen=True)
class SourceGroup:
    id: str
    kind: str
    event_ids: tuple[str, ...]
    mark_ids: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    continuation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceNotation:
    events: tuple[SourceEvent, ...] = ()
    marks: tuple[SourceMark, ...] = ()
    groups: tuple[SourceGroup, ...] = ()
    # Keep written boundaries rational; float phrase grids are an assessment
    # interface, not a replacement for MusicXML's exact divisions/cursors.
    measure_boundaries: tuple[tuple[int, int], ...] = ()

    @classmethod
    def from_dict(cls, data: dict) -> SourceNotation:
        return cls(tuple(SourceEvent(**{**r, 'beat': tuple(r['beat']),
                             'duration': tuple(r['duration'])}) for r in data['events']),
                   tuple(SourceMark(**{**r, 'beat': tuple(r['beat'])}) for r in data['marks']),
                   tuple(SourceGroup(**{**r, 'event_ids': tuple(r['event_ids']),
                        'mark_ids': tuple(r['mark_ids']),
                        'continuation_ids': tuple(r.get('continuation_ids', ())),
                        'attributes': tuple(tuple(a) for a in r['attributes'])})
                         for r in data['groups']),
                   tuple(tuple(value) for value in data.get('measure_boundaries', ())))


def index_source(xml: str, notes) -> SourceNotation:
    """Read exact written events using the importer's canonical ordinal IDs."""
    from ..music import _named_hand

    root = ET.fromstring(xml)
    part_names = {part.get('id'): part.findtext('part-name', '')
                  for part in root.findall('./part-list/score-part')}
    by_source = {n.source_id: n for n in notes}
    hands = {n.voice: n.hand for n in notes}
    events, marks, groups = [], [], []
    opened = {}
    pending_graces = {}
    previous_anchors = {}
    measure_boundaries = []
    for pi, part in enumerate(root.findall('part')):
        named_hand = _named_hand(part_names.get(part.get('id'), ''))
        # Match the importer's upper/lower convention using every timed
        # source staff, including staves with no graded pitched events.
        staffs = {note.findtext('staff', '1') for note in part.findall('./measure/note')
                  if note.find('grace') is None}

        def source_hand(voice: str, staff: str) -> str:
            fallback = named_hand or ('left' if len(staffs) == 2 and staff != '1' else 'right')
            return hands.get(voice, next((hand for key, hand in hands.items()
                if key.startswith(f'xml-p{pi}-s{staff}-')), fallback))

        divisions = Fraction(1)
        offset = Fraction(0)
        part_boundaries = [ratio(offset)]
        ties = {}
        for mi, measure in enumerate(part.findall('measure')):
            cursor = extent = Fraction(0)
            previous = Fraction(0)
            ending_marks = []
            for ordinal, child in enumerate(measure):
                raw_id = f'xml-p{pi}-m{mi}-e{ordinal}'
                if child.tag == 'attributes':
                    divisions = Fraction(child.findtext('divisions', str(divisions)))
                    continue
                if child.tag in ('backup', 'forward'):
                    amount = Fraction(child.findtext('duration')) / divisions
                    cursor += amount if child.tag == 'forward' else -amount
                    extent = max(extent, cursor)
                    continue
                if child.tag == 'direction':
                    staff = child.findtext('staff', '1')
                    voice = f"xml-p{pi}-s{staff}-v{child.findtext('voice', '1')}"
                    hand = source_hand(voice, staff)
                    at = offset + cursor + Fraction(child.findtext('offset', '0')) / divisions
                    for di, dt in enumerate(child.findall('direction-type')):
                        for ki, instruction in enumerate(dt):
                            identifier = identity(f'{raw_id}:direction:{di}:{ki}')
                            direction = ET.fromstring(ET.tostring(child))
                            for old in direction.findall('direction-type'):
                                direction.remove(old)
                            kind = ET.Element('direction-type')
                            tag = ET.fromstring(ET.tostring(instruction))
                            tag.set('id', identifier)
                            kind.append(tag)
                            direction.insert(0, kind)
                            old_offset = direction.find('offset')
                            if old_offset is not None:
                                direction.remove(old_offset)
                            marks.append(SourceMark(identifier, instruction.tag, '',
                                'both' if instruction.tag == 'pedal' else hand,
                                voice, ratio(at), ET.tostring(direction, encoding='unicode')))
                    continue
                if child.tag == 'barline':
                    for ei, tag in enumerate(child.findall('ending')):
                        identifier=identity(f'{raw_id}:ending:{ei}')
                        tag.set('id',identifier)
                        ending_marks.append((identifier,child.get('location','right'),ET.tostring(tag,encoding='unicode')))
                    continue
                if child.tag != 'note':
                    continue
                staff = child.findtext('staff', '1')
                voice = f"xml-p{pi}-s{staff}-v{child.findtext('voice','1')}"
                grace = child.find('grace') is not None
                chord = child.find('chord') is not None
                at = previous if chord else cursor
                duration = Fraction(0) if grace else Fraction(child.findtext('duration')) / divisions
                if not chord and not grace:
                    previous = cursor
                    cursor += duration
                extent = max(extent, at + duration, cursor)
                identifier = identity(raw_id)
                child.set('id', identifier)
                pitch = child.find('pitch')
                tie_types = {t.get('type') for t in child.findall('tie') + child.findall('notations/tied')}
                key = voice, tuple(pitch.findtext(k, '0') for k in ('step', 'alter', 'octave')) if pitch is not None else ()
                source = ties.get(key) if 'stop' in tie_types else raw_id
                if pitch is None or grace:
                    source = None
                if source and 'start' in tie_types:
                    ties[key] = source
                elif 'stop' in tie_types:
                    ties.pop(key, None)
                imported = by_source.get(source)
                hand = imported.hand if imported is not None else source_hand(voice, staff)
                for ni, notation in enumerate(child.findall('notations')):
                    for ki, tag in enumerate(notation):
                        if tag.tag == 'tied':
                            continue
                        mid = identity(f'{raw_id}:notation:{ni}:{ki}')
                        tag.set('id', mid)
                        if tag.tag not in ('slur', 'tuplet'):
                            # Leaf IDs survive Verovio's promotion of an articulation
                            # or ornament out of its MusicXML wrapper.
                            if len(tag) == 1:
                                tag.attrib.pop('id', None)
                                tag[0].set('id', mid)
                            marks.append(SourceMark(mid, tag.tag, identifier, hand,
                                voice, ratio(offset+at), ET.tostring(tag, encoding='unicode')))
                anchor = ''
                if grace:
                    if child.find('grace').get('steal-time-previous') is not None:
                        anchor = previous_anchors.get(voice, '')
                    else:
                        pending_graces.setdefault(voice, []).append(len(events))
                elif source:
                    previous_anchors[voice] = source
                    for index in pending_graces.pop(voice, []):
                        from dataclasses import replace
                        events[index] = replace(events[index], anchor_id=source)
                event = SourceEvent(identifier, source, hand, voice, mi,
                    ratio(offset+at), ratio(duration), ET.tostring(child, encoding='unicode'), anchor)
                events.append(event)
                starts, stops = [], []
                tags = child.findall('notations/slur') + child.findall('notations/tuplet')
                tags += [b for b in child.findall('beam') if b.get('number','1') == '1']
                for tag in tags:
                    number = tag.get('number', '1')
                    scope = voice
                    gkey = tag.tag, scope, number
                    marker = tag.get('type', '') if tag.tag != 'beam' else (tag.text or '').strip()
                    if tag.get('id') is None:
                        tag.set('id', identity(f'{raw_id}:beam:{number}'))
                    if marker in ('start', 'begin'):
                        starts.append((gkey, tag))
                    if marker in ('stop', 'end'):
                        stops.append((gkey, tag))
                    if marker == 'continue' and gkey in opened:
                        opened[gkey][3].append(tag.get('id'))
                for gkey, tag in starts:
                    attributes=dict(tag.attrib)
                    if tag.tag == 'tuplet':
                        actual=tag.findtext('tuplet-actual/tuplet-number')
                        normal=tag.findtext('tuplet-normal/tuplet-number')
                        if actual is not None and normal is not None:
                            attributes.update(actual=actual,normal=normal)
                            attributes['actual_type']=tag.findtext('tuplet-actual/tuplet-type','')
                            attributes['normal_type']=tag.findtext('tuplet-normal/tuplet-type','')
                    opened[gkey] = [[], [tag.get('id')], tuple(attributes.items()), []]
                for gkey, group in opened.items():
                    if gkey[1] == voice:
                        group[0].append(identifier)
                for gkey, tag in stops:
                    if gkey not in opened and gkey[0] == 'slur':
                        candidates=[key for key in opened if key[0]=='slur'
                                    and key[1].startswith(f'xml-p{pi}-') and key[2]==gkey[2]]
                        if len(candidates)==1:
                            gkey=candidates[0]
                    group = opened.pop(gkey, None)
                    if group:
                        if not group[0] or group[0][-1] != identifier:
                            group[0].append(identifier)
                        group[1].append(tag.get('id'))
                        groups.append(SourceGroup(identity('group:'+group[1][0]),
                            gkey[0], tuple(group[0]), tuple(group[1]), group[2], tuple(group[3])))
                # Beam IDs were assigned after the event snapshot.
                if child.findall('beam'):
                    from dataclasses import replace
                    events[-1] = replace(events[-1], xml=ET.tostring(child, encoding='unicode'))
            for identifier, location, xml in ending_marks:
                marks.append(SourceMark(identifier,'ending','','both','',
                    ratio(offset if location == 'left' else offset+extent),xml))
            offset += extent
            part_boundaries.append(ratio(offset))
        if pi == 0:
            measure_boundaries = part_boundaries
    for (kind, _, _), (members, marker_ids, attributes, continuations) in opened.items():
        groups.append(SourceGroup(identity('unclosed:'+marker_ids[0]), kind,
            tuple(members), tuple(marker_ids), attributes, tuple(continuations)))
    return SourceNotation(tuple(events), tuple(marks), tuple(groups), tuple(measure_boundaries))
