"""Independent, bounded MIDI-to-written-policy audit (stdlib only).

No production importer, quantizer, lesson builder or model parser supplies
expectations. See docs/midi-transcription-rules.md for the policy and limits.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from fractions import Fraction
import hashlib
from pathlib import Path
import re
from statistics import median
import struct
from xml.etree import ElementTree as ET

RULE_VERSION = 'midi-transcription-rules-v1'
REQUIRED_RULES = (
    'source_decode', 'physical_performance', 'hand_policy', 'warning_dispositions',
    'meter_grid', 'printed_rhythm', 'bar_fill', 'source_mapping',
    'tie_continuity', 'display_quantization', 'native_notation', 'hand_mode',
)
_DIVISIONS = 10080
_VALUES = dict(whole=Fraction(4), half=Fraction(2), quarter=Fraction(1),
               eighth=Fraction(1, 2), **{'16th': Fraction(1, 4),
               '32nd': Fraction(1, 8), '64th': Fraction(1, 16), '128th': Fraction(1, 32)})


def _json(value):
    if isinstance(value, (Fraction, float)):
        return round(float(value), 8)
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


class _Audit:
    def __init__(self, path, xml, model, hand):
        self.path, self.xml, self.model, self.hand = Path(path), xml, model, hand
        self.elements = []

    def check(self, rule, source_id, expected, actual, *, status=None, evidence=None):
        expected, actual = _json(expected), _json(actual)
        self.elements.append(dict(rule=rule, source_id=source_id, expected=expected,
            actual=actual, status=status or ('verified' if expected == actual else 'mismatch'),
            evidence=_json(evidence or {})))


def _smf(data):
    """Strict SMF event decoder with raw ordinals, including meta events."""
    if len(data) < 14 or data[:4] != b'MThd':
        raise ValueError('Missing or truncated SMF header')
    size = int.from_bytes(data[4:8], 'big')
    fmt, count, ppq = struct.unpack('>HHH', data[8:14])
    if size < 6 or size+8 > len(data) or fmt not in (0, 1) or not count or (fmt == 0 and count != 1):
        raise ValueError('Unsupported SMF format/header')
    if not ppq or ppq & 0x8000:
        raise ValueError('Only positive PPQ time divisions are implemented')
    offset, events = size+8, []

    def vlq(pos, end):
        value = 0
        for _ in range(4):
            if pos >= end:
                raise ValueError('Truncated SMF variable integer')
            byte = data[pos]
            value, pos = (value << 7) | (byte & 127), pos+1
            if byte < 128:
                return value, pos
        raise ValueError('Oversized SMF variable integer')

    for track in range(count):
        if data[offset:offset+4] != b'MTrk' or offset+8 > len(data):
            raise ValueError('Missing track chunk')
        length = int.from_bytes(data[offset+4:offset+8], 'big')
        offset += 8
        end, tick, ordinal, running, ended = offset+length, 0, 0, None, False
        if end > len(data):
            raise ValueError('Truncated track chunk')
        while offset < end:
            if ended:
                raise ValueError('Events after end-of-track')
            delta, offset = vlq(offset, end)
            tick += delta
            if offset >= end:
                raise ValueError('Missing event status')
            status = data[offset]
            if status >= 128:
                offset += 1
            elif running is None:
                raise ValueError('Running status without channel status')
            else:
                status = running
            event = dict(track=track, tick=tick, ordinal=ordinal,
                         id=f'midi-t{track}-e{ordinal}', status=status)
            if status == 255:
                if offset >= end:
                    raise ValueError('Missing meta event type')
                event['meta'] = data[offset]
                offset += 1
                length, offset = vlq(offset, end)
                event['payload'] = data[offset:offset+length]
                offset += length
                ended = event['meta'] == 47
                if ended and length:
                    raise ValueError('Malformed end-of-track')
            elif status in (240, 247):
                length, offset = vlq(offset, end)
                offset += length
            elif 128 <= status <= 239:
                running = status
                length = 1 if status >> 4 in (12, 13) else 2
                payload = data[offset:offset+length]
                offset += length
                if len(payload) != length or any(b > 127 for b in payload):
                    raise ValueError('Invalid channel payload')
                event.update(channel=status & 15, payload=payload)
                if status >> 4 in (8, 9):
                    event.update(pitch=payload[0], velocity=payload[1],
                                 attack=status >> 4 == 9 and payload[1] > 0)
            else:
                raise ValueError('Unsupported SMF event status')
            if offset > end:
                raise ValueError('Event overruns track')
            events.append(event)
            ordinal += 1
        if not ended:
            raise ValueError('Missing end-of-track')
    if offset != len(data):
        raise ValueError('Unaccounted trailing SMF bytes')
    return ppq, events


def _source(a):
    a.ppq, a.raw = _smf(a.path.read_bytes())
    a.notes, a.names, a.changes, a.warnings, a.dispositions = [], {}, [], [], []
    pending = defaultdict(deque)
    percussion, unterminated = [], []
    zero = orphan = 0
    for e in a.raw:
        if e.get('meta') == 3:
            a.names[e['track']] = e['payload'].decode('latin1')
        if e.get('meta') == 88:
            p = e['payload']
            if len(p) != 4 or not p[0] or p[1] > 30:
                raise ValueError('Invalid meter meta event')
            a.changes.append((Fraction(e['tick'], a.ppq), p[0], 2**p[1]))
        if 'attack' not in e:
            continue
        if e['channel'] == 9:
            percussion.append(e['id'])
            continue
        key = e['track'], e['channel'], e['pitch']
        if e['attack']:
            if pending[key]:
                a.warnings.append(
                    f"Ambiguous overlapping MIDI notes on track {e['track']}, "
                    f"channel {e['channel']}, pitch {e['pitch']}: attack "
                    f"{e['id']} at tick {e['tick']}; releases paired "
                    'FIFO (oldest attack first). All attack/release times retained; '
                    'individual pairing is not uniquely specified by MIDI.')
            pending[key].append(e)
        elif pending[key]:
            attack = pending[key].popleft()
            if attack['tick'] == e['tick']:
                zero += 1
                a.dispositions.append(dict(attack_id=attack['id'], release_id=e['id'], policy='skip_zero'))
            else:
                a.notes.append(dict(id=attack['id'], release_id=e['id'],
                    onset_beats=Fraction(attack['tick'], a.ppq),
                    duration_beats=Fraction(e['tick']-attack['tick'], a.ppq),
                    midi_pitch=e['pitch'], velocity=attack['velocity'],
                    track=e['track'], channel=e['channel'],
                    voice=f"midi-t{e['track']}-c{e['channel']}"))
        else:
            orphan += 1
            a.dispositions.append(dict(release_id=e['id'], policy='ignore_orphan'))
    for queue in pending.values():
        unterminated.extend(e['id'] for e in queue)
    if zero:
        a.warnings.append(f'Skipped {zero} zero-duration MIDI note(s) with no audible length.')
    if orphan:
        a.warnings.append(f'Ignored {orphan} unmatched MIDI note-off event(s).')
    repaired = [f'{n}/{d} at beat {float(b):g}' for b,n,d in sorted(set(a.changes)) if n > 32 or d > 32]
    if repaired:
        a.warnings.append('Ignored implausible time signature(s): '+', '.join(repaired)+'.')
    a.check('source_decode', 'smf', dict(timed_pitched_attacks=True, unterminated=[]),
            dict(timed_pitched_attacks=bool(a.notes), unterminated=unterminated),
            evidence=dict(ppq=a.ppq, raw_events=len(a.raw), timed_attacks=len(a.notes),
                          dispositions=a.dispositions))
    if percussion:
        a.check('source_decode', 'percussion', 'implemented pitched piano input', percussion,
                status='unverified', evidence=dict(reason='Channel 10 percussion is outside this rule set'))


def _hands(a):
    groups = defaultdict(list)
    for n in a.notes:
        groups[n['track']].append(n['midi_pitch'])
    named = {}
    for track, name in a.names.items():
        for hand, pattern in [('left', r'(^|\W)(left|lh|mano sinistra)(\W|$)'),
                              ('right', r'(^|\W)(right|rh|mano destra)(\W|$)')]:
            if re.search(pattern, name, re.I):
                named[track] = hand
                break
    ranked = sorted(groups, key=lambda t: (median(groups[t]), t))
    policy = dict(named)
    if len(ranked) == 2:
        policy.setdefault(ranked[0], 'left')
        policy.setdefault(ranked[1], 'right')
    actual = defaultdict(list)
    for n in a.model.get('notes', []):
        actual[n.get('id')].append(n.get('hand'))
    for n in a.notes:
        n['hand'] = policy.get(n['track'], 'left' if n['midi_pitch'] < 60 else 'right')
        a.check('hand_policy', n['id'], [n['hand']], actual[n['id']],
                evidence=dict(policy='named > two-track median (track-index tie break) > pitch60',
                    track_name=a.names.get(n['track']), ranked_tracks=ranked))


def _performance(a):
    fields = ('id', 'onset_beats', 'duration_beats', 'midi_pitch', 'velocity', 'track', 'channel', 'voice')
    actual = defaultdict(list)
    for n in a.model.get('notes', []):
        actual[n.get('id')].append({f:n.get(f) for f in fields})
    for n in a.notes:
        matches = actual.pop(n['id'], [])
        a.check('physical_performance', n['id'], {f:n[f] for f in fields},
                matches[0] if len(matches)==1 else matches,
                evidence=dict(release_id=n['release_id'], release_beat=n['onset_beats']+n['duration_beats'],
                              pairing='FIFO per track/channel/pitch; physical key endpoints only'))
    a.check('physical_performance', 'extra-native-attacks', {}, dict(actual))


def _warnings(a):
    observed = a.model.get('import_warnings', [])
    if not isinstance(observed, (list, tuple)) or not all(isinstance(w, str) for w in observed):
        observed = ['<malformed warning inventory>']
    a.check('warning_dispositions', 'warnings', sorted(a.warnings), sorted(observed),
            evidence=dict(dispositions=a.dispositions, policy='warn every overlap; count skipped zero pairs/orphan releases/meter repairs'))
    native_ids = {n.get('id') for n in a.model.get('notes', [])}
    bindings = {e.get('source_id') for e in a.model.get('notation_events', [])}
    for d in a.dispositions:
        forbidden = {d['release_id'], d.get('attack_id')} - {None}
        a.check('warning_dispositions', d.get('attack_id', d['release_id']), [],
                sorted(forbidden & (native_ids | bindings)), evidence=d)


def _grid(a):
    changes = []
    for beat,n,d in sorted(set(a.changes)):
        if n > 32 or d > 32:
            continue
        if changes and changes[-1][0] == beat and changes[-1][1:] != (n,d):
            raise ValueError('Conflicting original meter events')
        if not changes or changes[-1][1:] != (n,d):
            changes.append((beat,n,d))
    if not changes or changes[0][0] != 0:
        changes.insert(0,(Fraction(0),4,4))
    end = max(Fraction(e['tick'], a.ppq) for e in a.raw)
    a.grid, a.meters = [Fraction(0)], []
    pos = Fraction(0)
    for i,(beat,n,d) in enumerate(changes):
        if beat > end:
            break
        limit = changes[i+1][0] if i+1 < len(changes) else end
        while pos < min(end,limit):
            next_pos = min(pos+Fraction(4*n,d),limit) if i+1 < len(changes) else pos+Fraction(4*n,d)
            a.meters.append((n,d))
            a.grid.append(next_pos)
            pos = next_pos
    expected = [dict(number=i+1, start_beat=a.grid[i], end_beat=a.grid[i+1], meter=m)
                for i,m in enumerate(a.meters)]
    actual = [{f:m.get(f) for f in ('number','start_beat','end_beat','meter')}
              for m in a.model.get('measures', [])]
    a.check('meter_grid', 'source-measures', expected, actual,
            evidence=dict(default_meter=[4,4], repaired_implausible_meters=[m for m in a.changes if m[1]>32 or m[2]>32]))
    a.check('meter_grid', 'duration', a.grid[-1], a.model.get('duration_beats'))


def _printed(a):
    if not a.xml:
        raise ValueError('Generated MusicXML is required')
    root = ET.fromstring(a.xml)
    if root.tag != 'score-partwise':
        raise ValueError('Only unnamespaced generated score-partwise XML is implemented')
    parts = root.findall('part')
    a.check('printed_rhythm', 'piano-parts', ['LH','RH'], sorted(p.get('id','') for p in parts))
    a.events, a.fills = [], []
    for pi,part in enumerate(parts):
        hand = {'RH':'right','LH':'left'}.get(part.get('id'), '<unknown>')
        bars = part.findall('measure')
        a.check('meter_grid', f'xml-{pi}-measure-count', len(a.meters), len(bars))
        divisions, meter = None, None
        for mi,bar in enumerate(bars):
            if mi >= len(a.meters):
                continue
            length = Fraction(round(float(a.grid[mi+1]-a.grid[mi])*_DIVISIONS), _DIVISIONS)
            position, last, voices = Fraction(0), None, defaultdict(list)
            for ordinal,tag in enumerate(bar):
                if tag.tag == 'attributes':
                    if tag.find('divisions') is not None:
                        divisions = int(tag.findtext('divisions'))
                    if tag.find('time') is not None:
                        meter = (int(tag.findtext('time/beats')), int(tag.findtext('time/beat-type')))
                    if divisions != _DIVISIONS:
                        raise ValueError('Undeclared display resolution')
                    continue
                identity = f'xml-{pi}-{mi}-{ordinal}'
                if tag.tag in ('backup','forward'):
                    amount = Fraction(int(tag.findtext('duration')), divisions)
                    position += amount if tag.tag=='forward' else -amount
                    a.check('bar_fill', identity, True, amount>0 and 0<=position<=length)
                    last = None
                    continue
                if tag.tag != 'note':
                    continue
                if tag.find('grace') is not None or tag.find('unpitched') is not None:
                    raise ValueError('Grace/unpitched transcription rules are unimplemented')
                duration = Fraction(int(tag.findtext('duration')), divisions)
                voice = tag.findtext('voice','1')
                chord = tag.find('chord') is not None
                onset = last['onset'] if chord and last else position
                a.check('bar_fill', identity+':chord', True,
                        not chord or bool(last and last['voice']==voice and last['duration']==duration and last['pitched']))
                rest = tag.find('rest') is not None
                pitch_tag = tag.find('pitch')
                spelling = None
                pitch = None
                if pitch_tag is not None:
                    spelling = dict(step=pitch_tag.findtext('step'), alter=int(pitch_tag.findtext('alter','0')),
                                    octave=int(pitch_tag.findtext('octave')))
                    pitch = (spelling['octave']+1)*12 + dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)[spelling['step']] + spelling['alter']
                a.check('printed_rhythm', identity+':kind', True, rest != (pitch_tag is not None))
                note_type, dots = tag.findtext('type'), len(tag.findall('dot'))
                modification = tag.find('time-modification')
                mod = None
                ratio = Fraction(1)
                if modification is not None:
                    mod = dict(actual=int(modification.findtext('actual-notes')), normal=int(modification.findtext('normal-notes')))
                    if min(mod.values()) <= 0:
                        raise ValueError('Nonpositive rhythm ratio')
                    ratio = Fraction(mod['normal'],mod['actual'])
                written = _VALUES.get(note_type,Fraction(0))*sum((Fraction(1,2**d) for d in range(dots+1)),Fraction(0))*ratio
                a.check('printed_rhythm', identity, duration, written,
                        evidence=dict(note_type=note_type, dots=dots, time_modification=mod))
                a.check('bar_fill', identity+':bounds', True, duration>0 and 0<=onset<onset+duration<=length)
                ties = [t.get('type') for t in tag.findall('tie')]
                written_ties = [t.get('type') for t in tag.findall('notations/tied')]
                a.check('tie_continuity', identity+':marks', sorted(ties), sorted(written_ties))
                a.check('tie_continuity', identity+':legal', True,
                        len(ties)==len(set(ties)) and set(ties)<= {'start','stop'} and (not rest or not ties))
                event = dict(id=tag.get('id'), staff=hand, voice=voice, measure=mi+1,
                    beat=a.grid[mi]+onset, duration_beats=duration, kind='rest' if rest else 'note',
                    midi_pitch=pitch, spelling=spelling, note_type=note_type, dots=dots, chord=chord,
                    tie_start='start' in ties, tie_stop='stop' in ties, accidental=tag.findtext('accidental'),
                    time_modification=mod, visible=tag.get('print-object')!='no',
                    tuplet_marks=[dict(type=t.get('type'), number=t.get('number','1'),
                        bracket=t.get('bracket','no'), show_number=t.get('show-number','actual'))
                        for t in tag.findall('notations/tuplet')])
                # Secondary reconstructed lanes suppress silence; the primary
                # lane suppresses only a short internal articulation gap.
                a.check('printed_rhythm', identity+':visibility', True,
                        event['visible'] or rest and (voice!='1' or
                            0<onset and duration<=Fraction(1,8) and onset+duration<length))
                a.events.append(event)
                if not chord:
                    voices[voice].append((onset,onset+duration))
                    last = dict(onset=onset, duration=duration, voice=voice, pitched=not rest)
                    position += duration
            a.check('meter_grid', f'xml-{pi}-{mi}-meter', a.meters[mi], meter)
            a.check('meter_grid', f'xml-{pi}-{mi}-label', str(mi+1), bar.get('number'))
            partial = Fraction(4*a.meters[mi][0],a.meters[mi][1]) != length
            a.check('meter_grid', f'xml-{pi}-{mi}-implicit', partial, bar.get('implicit')=='yes')
            a.fills.append((f'xml-{pi}-{mi}', position, length, voices))
    _tuplet_groups(a)


def _tuplet_groups(a):
    lanes = defaultdict(list)
    for e in a.events:
        if not e['chord']:
            lanes[e['staff'],e['measure'],e['voice']].append(e)
        elif e['tuplet_marks']:
            # Nonconventional expressive chord tones retain local hidden
            # timing pairs; conventional chord tones inherit their anchor.
            a.check('printed_rhythm', str(e['id'])+':chord-tuplet', True,
                    [m['type'] for m in e['tuplet_marks']]==['start','stop'] and
                    all(m['show_number']=='none' for m in e['tuplet_marks'] if m['type']=='start'))
    for lane,events in lanes.items():
        opened = {}
        for e in events:
            identity = str(e['id'] or (lane,e['beat']))
            marks = e['tuplet_marks']
            for mark in marks:
                if mark['type']=='start':
                    a.check('printed_rhythm', identity+':tuplet-start', True,
                            mark['number'] not in opened and e['time_modification'] is not None)
                    opened[mark['number']] = (mark,[])
                elif mark['type']!='stop':
                    a.check('printed_rhythm', identity+':tuplet-mark', ['start','stop'],mark['type'])
            for _,members in opened.values():
                members.append(e)
            if e['time_modification'] is not None:
                a.check('printed_rhythm', identity+':ratio-group', True, bool(opened),
                        evidence=dict(policy='explicit local timing pair or balanced complete conventional group'))
            for mark in marks:
                if mark['type']!='stop':
                    continue
                group = opened.pop(mark['number'],None)
                a.check('printed_rhythm', identity+':tuplet-stop', True, group is not None)
                if group is None:
                    continue
                start,members = group
                mod = members[0]['time_modification']
                consistent = mod is not None and all(m['time_modification']==mod and
                    m['note_type']==members[0]['note_type'] for m in members)
                contiguous = all(x['beat']+x['duration_beats']==y['beat'] for x,y in zip(members,members[1:]))
                visible = start['show_number']!='none' or start['bracket']=='yes'
                legal = consistent and contiguous and (len(members)==mod['actual'] if visible else len(members)==1)
                a.check('printed_rhythm', identity+':tuplet-group', True, legal,
                        evidence=dict(members=len(members), ratio=mod, visible=visible))
        a.check('printed_rhythm', str(lane)+':closed-tuplets', [], sorted(opened))


def _fill(a):
    for identity,position,length,voices in a.fills:
        a.check('bar_fill', identity+':cursor', length, position)
        a.check('bar_fill', identity+':nonempty', True, bool(voices))
        for voice,intervals in voices.items():
            ordered = sorted(intervals)
            contiguous = bool(ordered) and ordered[0][0]==0 and ordered[-1][1]==length
            contiguous = contiguous and all(x[1]==y[0] for x,y in zip(ordered,ordered[1:]))
            a.check('bar_fill', identity+':'+voice, True, contiguous,
                    evidence=dict(intervals=ordered, policy='every voice tiles its source bar; hidden rests retain cursor time'))


def _mapping(a):
    prefixes = {'pt'+hashlib.sha256(n['id'].encode()).hexdigest()[:32]: n for n in a.notes}
    a.chains = defaultdict(list)
    seen = Counter()
    for e in a.events:
        if e['kind']!='note':
            continue
        identifier = e['id'] or ''
        match = re.fullmatch(r'(pt[0-9a-f]{32})s(0|[1-9][0-9]*)',identifier)
        n = prefixes.get(match[1]) if match else None
        seen[identifier] += 1
        a.check('source_mapping', identifier, True, n is not None and seen[identifier]==1 and e['visible'])
        if n is None:
            continue
        e.update(source_id=n['id'], segment=int(match[2]), is_attack=int(match[2])==0)
        a.chains[n['id']].append(e)
        a.check('source_mapping', identifier+':pitch-hand', [n['midi_pitch'],n['hand']], [e['midi_pitch'],e['staff']])
    for n in a.notes:
        chain = sorted(a.chains[n['id']], key=lambda e:e['segment'])
        a.chains[n['id']] = chain
        a.check('source_mapping', n['id'], list(range(len(chain))) if chain else [0],
                [e['segment'] for e in chain], evidence=dict(policy='sha256(original attack ID) prefix; contiguous segment suffixes'))


def _ties(a):
    for source_id,chain in a.chains.items():
        for i,e in enumerate(chain):
            a.check('tie_continuity', e['id'], [i>0, i+1<len(chain)], [e['tie_stop'],e['tie_start']])
            if i:
                previous = chain[i-1]
                a.check('tie_continuity', e['id']+':continuation',
                        [previous['beat']+previous['duration_beats'], previous['voice'],previous['spelling']],
                        [e['beat'],e['voice'],e['spelling']], evidence=dict(source_id=source_id))


def _quantization(a):
    def ticks(beat):
        return round(float(beat)*_DIVISIONS)

    def tuplet(length):
        return any(Fraction(length,_DIVISIONS)==v*Fraction(normal,actual)
                   for v in _VALUES.values() for actual,normal in ((3,2),(5,4),(7,4),(9,8)))

    # Discover complete four-onset ornaments from original source owners only.
    owners = defaultdict(set)
    for n in a.notes:
        owners[n['track'],n['voice'],n['hand']].add(n['onset_beats'])
    ornaments = {}
    for owner,times in owners.items():
        times = sorted(times)
        for i in range(len(times)-3):
            origin = Fraction(round(float(times[i])*4),4)
            if all(abs(float(times[i+j]-origin-Fraction(j,12)))<=.004 for j in range(4)):
                for j in range(4):
                    ornaments[owner,times[i+j]] = ticks(origin+Fraction(j,12))
    grid = [ticks(b) for b in a.grid]
    by_id = {n['id']:n for n in a.notes}
    lanes = defaultdict(list)
    for source_id,chain in a.chains.items():
        if chain:
            lanes[chain[0]['staff'],chain[0]['voice']].append((source_id,chain))
    for lane,members in lanes.items():
        owner_set = {(by_id[s]['track'],by_id[s]['voice']) for s,_ in members}
        a.check('display_quantization', 'lane:'+str(lane), 1, len(owner_set),
                evidence=dict(policy='one stable source owner per written lane; no authored voice claim'))
        members.sort(key=lambda item:(item[1][0]['beat'],item[1][-1]['beat']+item[1][-1]['duration_beats']))
        for i,(source_id,chain) in enumerate(members):
            n = by_id[source_id]
            start = ticks(n['onset_beats'])
            owner = n['track'],n['voice'],n['hand']
            allowed_start = ornaments.get((owner,n['onset_beats']),start)
            a.check('display_quantization', source_id+':onset', Fraction(allowed_start,_DIVISIONS), chain[0]['beat'],
                    evidence=dict(source_beat=n['onset_beats'], mode='complete 32nd-triplet ornament' if allowed_start!=start else 'exact grid; swing retained'))
            end = ticks(n['onset_beats']+n['duration_beats'])
            rounded = round(end/(_DIVISIONS//4))*(_DIVISIONS//4)
            long = end-allowed_start>=_DIVISIONS
            close = next((b for b in grid if 0<b-end<=ticks(.25)),None) if long else None
            if close is not None:
                rounded = close
            tolerance = .08 if rounded<end else .15
            if rounded>end and long and rounded in grid:
                tolerance = .25
            ends = {end}
            following = next((ticks(other[0]['beat']) for _,other in members[i+1:]
                              if other[0]['beat']>chain[0]['beat']),grid[-1])
            if not tuplet(end-allowed_start) and rounded>allowed_start and abs(rounded-end)<=ticks(tolerance):
                ends.add(min(rounded,following,grid[-1]))
            for candidate in tuple(ends):
                if 0<following-candidate<=_DIVISIONS/64 and not any(candidate<=b<following for b in grid):
                    ends.add(following)
            actual_end = chain[-1]['beat']+chain[-1]['duration_beats']
            a.check('display_quantization', source_id+':release', True,
                    any(_json(actual_end)==_json(Fraction(e,_DIVISIONS)) for e in ends),
                    evidence=dict(source_release=n['onset_beats']+n['duration_beats'],
                                  allowed_display_releases=[Fraction(e,_DIVISIONS) for e in sorted(ends)], actual_display_release=actual_end))
            # Chords may coincide only with identical duration and distinct pitch.
            for other_id,other in members[i+1:]:
                if other[0]['beat']>=actual_end:
                    break
                a.check('display_quantization', source_id+':overlap:'+other_id, True,
                    other[0]['beat']==chain[0]['beat'] and other[-1]['beat']+other[-1]['duration_beats']==actual_end
                    and by_id[other_id]['midi_pitch']!=n['midi_pitch'])


def _native(a):
    fields = ('staff','voice','measure','beat','duration_beats','kind','midi_pitch','spelling',
              'note_type','dots','chord','tie_start','tie_stop','accidental','time_modification','tuplet_marks')
    expected, actual = [], []
    for e in a.events:
        if not e['visible']:
            continue
        row = {f:e[f] for f in fields}
        row.update(source_id=e.get('source_id'), is_attack=e.get('is_attack',False))
        if e['kind']=='note':
            row['id'] = e['id']
        expected.append(_json(row))
    for e in a.model.get('notation_events', []):
        row = {f:e.get(f) for f in fields}
        row.update(source_id=e.get('source_id'), is_attack=e.get('is_attack'))
        if e.get('kind')=='note':
            row['id'] = e.get('id')
        actual.append(_json(row))
    # Multiset comparison retains duplicate and missing rests as well as notes.
    import json
    a.check('native_notation', 'visible-inventory',
            sorted(expected,key=lambda r:json.dumps(r,sort_keys=True)),
            sorted(actual,key=lambda r:json.dumps(r,sort_keys=True)))


def _mode(a):
    expected = sorted(n['id'] for n in a.notes if a.hand=='both' or n['hand']==a.hand)
    a.check('hand_mode', 'active-source-attacks', [a.hand,expected],
            [a.model.get('active_hand'),sorted(a.model.get('active_note_ids',[]))])


RULE_CHECKS = dict(zip(REQUIRED_RULES, (
    _source, _performance, _hands, _warnings, _grid, _printed, _fill, _mapping,
    _ties, _quantization, _native, _mode,
)))


def verify_midi_transcription(path, generated_xml, native_model, *, hand='both') -> dict:
    """Check an entire original SMF against generated XML and its native model.

    `passed` means no mismatches, while `complete` requires every declared rule
    verified. Callers bind original/generated/model bytes and hashes. No proof
    flags in the model or generated output are trusted.
    """
    if hand not in ('both','right','left'):
        raise ValueError('Invalid hand')
    a = _Audit(path,generated_xml,native_model,hand)
    for rule in REQUIRED_RULES:
        start = len(a.elements)
        check = RULE_CHECKS.get(rule)
        if check is None:
            a.check(rule,'rule-implementation','implemented independent check',None,status='unverified')
            continue
        try:
            check(a)
        except Exception as exc:
            a.check(rule,'rule-execution','complete independent check',None,status='unverified',
                    evidence=dict(reason=f'{type(exc).__name__}: {exc}'))
        if len(a.elements)==start:
            a.check(rule,'empty-rule-evidence','nonempty independent evidence',None,status='unverified')
    rules = {}
    for rule in REQUIRED_RULES:
        elements = [e for e in a.elements if e['rule']==rule]
        status = ('mismatch' if any(e['status']=='mismatch' for e in elements) else
                  'verified' if elements and all(e['status']=='verified' for e in elements) else 'unverified')
        rules[rule] = dict(status=status, evidence=dict(element_count=len(elements),
            verified=sum(e['status']=='verified' for e in elements),
            mismatch=sum(e['status']=='mismatch' for e in elements),
            unverified=sum(e['status']=='unverified' for e in elements)))
    discrepancies = [e for e in a.elements if e['status']=='mismatch']
    return dict(schema_version=1, rule_version=RULE_VERSION, passed=not discrepancies,
                complete=all(r['status']=='verified' for r in rules.values()), rules=rules,
                elements=a.elements, discrepancies=discrepancies)
