"""Independent original-source semantic ledger; no renderer expectations."""
from __future__ import annotations

from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
import re
import struct
from statistics import median

from .proof import read_written_score


STATUSES = ('verified', 'ambiguous', 'unsupported', 'unverified', 'mismatch')
WRITTEN = ('kind', 'staff', 'onset', 'duration', 'pitch', 'spelling',
           'note_type', 'dots', 'chord', 'accidental', 'visible')
TIES = ('tie_start', 'tie_stop')
TUPLETS = ('time_modification', 'tuplet_marks')


def _json(value):
    if isinstance(value, (Fraction, float)):
        return round(float(value), 8)
    if isinstance(value, dict):
        return {k: _json(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(v) for v in value]
    return value


def _fields(event, fields):
    return _json({f: event.get(f, '<missing>') for f in fields}) if event is not None else None


class _Ledger:
    def __init__(self):
        self.elements = []
        self.ids = Counter()

    def add(self, boundary, construct, source, expected=None, actual=None, *,
            status=None, reason=None, evidence=None, target=None):
        source = {**dict(id=None, measure=None, staff=None, voice=None), **(source or {})}
        expected, actual = _json(expected), _json(actual)
        if status is None:
            status = 'verified' if expected == actual else 'mismatch'
        key = f'{boundary}:{source["id"]}:{construct}'
        ordinal = self.ids[key]
        self.ids[key] += 1
        row = dict(id=key + (f':{ordinal}' if ordinal else ''), boundary=boundary,
                   construct=construct, status=status, source=source,
                   expected=expected, actual=actual)
        if status == 'mismatch':
            if isinstance(expected, dict) and isinstance(actual, dict):
                row['differences'] = [dict(field=f, expected=expected.get(f), actual=actual.get(f))
                                      for f in sorted(expected.keys() | actual.keys())
                                      if expected.get(f) != actual.get(f)]
            else:
                row['differences'] = [dict(field='event' if expected is None or actual is None else 'value',
                                          expected=expected, actual=actual)]
        if reason:
            row['reason'] = reason
        if evidence:
            row['evidence'] = _json(evidence)
        if target:
            row['target'] = target
        self.elements.append(row)

    def report(self):
        coverage = {s: sum(e['status'] == s for e in self.elements) for s in STATUSES}
        coverage['expected'] = len(self.elements)
        mismatches = [e for e in self.elements if e['status'] == 'mismatch']
        return dict(passed=not mismatches, complete=bool(self.elements) and
                    coverage['verified'] == len(self.elements), coverage=coverage,
                    elements=self.elements, discrepancies=mismatches)


def _lane(event):
    return event['part_index'], event['raw_staff'], event['voice']


def _voices(original, actual):
    """Infer a fixed injective lane rename from independent timed pitch anchors.

    Equal best candidates remain ambiguous. A one-off reassignment cannot rename
    the whole voice: the remaining original members anchor its expected lane.
    """
    source_groups, target_groups = defaultdict(list), defaultdict(list)
    for e in original:
        source_groups[_lane(e)].append(e)
    for e in actual:
        target_groups[e['staff'], e['voice']].append(e)
    mapping, ambiguity = {}, set()
    for lane, events in source_groups.items():
        hand = events[0]['staff']
        pitched = [e for e in events if e['kind'] == 'note'] or events
        signature = Counter((e['index'], _json(e['onset']), e['pitch'], e['kind']) for e in pitched)
        scores = {}
        for (target_hand, voice), members in target_groups.items():
            if hand != target_hand:
                continue
            candidates = [e for e in members if e['kind'] == 'note'] or members
            other = Counter((e['index'], _json(e['onset']), e['pitch'], e['kind']) for e in candidates)
            scores[voice] = sum((signature & other).values())
        if scores:
            best = max(scores.values())
            choices = [voice for voice, score in scores.items() if score == best]
            if len(choices) == 1 and (best or len(scores) == 1):
                mapping[lane] = choices[0]
            else:
                ambiguity.add(lane)
        else:
            ambiguity.add(lane)
    # A rename cannot merge distinct source voices into the same target voice.
    owners = defaultdict(list)
    for lane, voice in mapping.items():
        owners[source_groups[lane][0]['staff'], voice].append(lane)
    merged = {lane for lanes in owners.values() if len(lanes) > 1 for lane in lanes}
    return mapping, ambiguity, merged


def _native_events(model):
    indices = {m['number']: i for i, m in enumerate(model['measures'])}
    starts = {i: m['start_beat'] for i, m in enumerate(model['measures'])}
    events = []
    for ordinal, e in enumerate(model['notation_events']):
        index = indices.get(e['measure'], int(e['measure']) - 1)
        spelling = e.get('spelling')
        if isinstance(spelling, dict):
            spelling = (spelling.get('step'), spelling.get('alter'), spelling.get('octave'))
        mod = e.get('time_modification')
        if isinstance(mod, dict):
            mod = (mod.get('actual'), mod.get('normal'))
        marks = tuple((m['type'], m['number'], m['bracket'], m['show_number'])
                      for m in e.get('tuplet_marks', ()))
        events.append(dict(e, index=index, part_index=0, raw_staff=e['staff'],
                           onset=_json(e['beat'] - starts.get(index, 0)),
                           duration=e['duration_beats'], pitch=e.get('midi_pitch'),
                           spelling=spelling, time_modification=mod, tuplet_marks=marks,
                           visible=True, source=dict(id=e['id'], measure=str(e['measure']),
                           staff=e['staff'], voice=e['voice'], ordinal=ordinal)))
    return events


def _match_events(original, actual, mapping, *, direct=False):
    unused = set(range(len(actual)))
    pairs = []
    for source in original:
        expected_voice = source['voice'] if direct else mapping.get(_lane(source))
        candidates = [i for i in unused if actual[i]['index'] == source['index']
                      and actual[i]['staff'] == source['staff']
                      and _json(actual[i]['onset']) == _json(source['onset'])]
        for field, value in [('voice', expected_voice), ('kind', source['kind']),
                             ('pitch', source['pitch']), ('duration', _json(source['duration']))]:
            preferred = [i for i in candidates if _json(actual[i].get(field)) == value]
            if preferred:
                candidates = preferred
        if len(candidates) == 1:
            target = actual[candidates[0]]
            unused.remove(candidates[0])
            pairs.append((source, target, False))
        else:
            pairs.append((source, None, len(candidates) > 1))
    return pairs, [actual[i] for i in sorted(unused)]


def _authored_tuplet_events(events):
    """Only paired authored intervals determine grouping, including continuations.

    Another same-ratio group later in the same voice/measure may be unmarked.
    Whole-measure ratio buckets cannot establish its graphical limits.
    """
    lanes = defaultdict(list)
    for event in events:
        lanes[_lane(event)].append(event)
    authored = set()
    for members in lanes.values():
        opened = {}
        for event in sorted(members, key=lambda e: (e['index'], e['onset'], e['source'].get('ordinal', 0))):
            ratio = tuple(event.get('time_modification') or ())
            marks = event.get('tuplet_marks', ())
            for mark in marks:
                if mark[0] == 'start':
                    opened[mark[1]] = ratio
            if marks or ratio and ratio in opened.values():
                authored.add(event['source']['id'])
            for mark in marks:
                if mark[0] == 'stop':
                    opened.pop(mark[1], None)
    return authored


def _compare_events(ledger, original, actual, boundary, *, direct=False, generated_targets=None):
    mapping, ambiguity, merged = _voices(original, actual) if not direct else ({}, set(), set())
    authored = _authored_tuplet_events(original)
    target_ids = Counter(e.get('id') for e in actual if e.get('id'))
    generated_ids = Counter(e.get('id') for e in (generated_targets or {}).values() if e and e.get('id'))
    pairs, extras = _match_events(original, actual, mapping, direct=direct)
    for source, target, ambiguous in pairs:
        identity = source['source']
        construct = 'written_notes' if source['kind'] == 'note' else 'written_rests'
        if boundary == 'original->native' and not source['visible'] and target is None:
            # Native notation_events describe visible ink only. Preserve the
            # unrepresented logical symbol explicitly; pitched performance is
            # still independently mandatory in _attacks below.
            kinds = [construct, 'voices', 'ties', 'tuplets']
            if source['kind'] == 'note':
                kinds.append('source_binding')
            if source.get('beams'):
                kinds.append('beams')
            if source.get('tied_marks'):
                kinds.append('written_tie_attributes')
            if any(source.get('tuplet_extras', ())):
                kinds.append('tuplet_attributes')
            if source.get('time_modification') is not None and identity['id'] not in authored:
                kinds.append('tuplet_grouping')
            for kind in kinds:
                ledger.add(boundary, kind, identity, _fields(source, WRITTEN), None,
                           status='unsupported', reason='Nonprinting source event has no native visible-event representation')
            continue
        ledger.add(boundary, construct, identity, _fields(source, WRITTEN), _fields(target, WRITTEN),
                   status='ambiguous' if ambiguous else None,
                   reason='Multiple indistinguishable target events' if ambiguous else None,
                   target=target['source'] if target else None)
        if source['kind'] == 'note' and direct:
            ledger.add(boundary, 'segment_identity', identity, source.get('id'),
                       target.get('id') if target else None,
                       status='mismatch' if target is None or target_ids[target.get('id')] > 1 else None)
        if source['kind'] == 'note' and boundary == 'original->native':
            generated = (generated_targets or {}).get(identity['id'])
            expected_binding = dict(source_id=source['attack_id'],
                                    is_attack=not source['tie_stop'],
                                    segment_id=generated.get('id') if generated else None)
            actual_binding = dict(source_id=target.get('source_id'),
                                  is_attack=target.get('is_attack'), segment_id=target.get('id')) if target else None
            ledger.add(boundary, 'source_binding', identity, expected_binding, actual_binding,
                       status='ambiguous' if ambiguous else
                       'mismatch' if target is None or generated is None or
                       target_ids[target.get('id')] > 1 or generated_ids[generated.get('id')] > 1 else None,
                       reason='Segment identity must be unique in generated and native inventories')
        lane = _lane(source)
        expected_voice = source['voice'] if direct else mapping.get(lane)
        ledger.add(boundary, 'voices', identity, expected_voice,
                   target['voice'] if target else None,
                   status=('ambiguous' if lane in ambiguity or ambiguous else
                           'mismatch' if lane in merged or target is None else None),
                   reason='Distinct source voices merged' if lane in merged else None,
                   evidence=dict(source_voice=source['voice'], generated_voice=expected_voice,
                                 rule='one consistent injective lane rename'))
        ledger.add(boundary, 'ties', identity, _fields(source, TIES), _fields(target, TIES),
                   status='ambiguous' if ambiguous else None)
        inferred_group = (not direct and source.get('time_modification') is not None and
                          identity['id'] not in authored)
        tuplet_fields = ('time_modification',) if inferred_group else TUPLETS
        ledger.add(boundary, 'tuplets', identity, _fields(source, tuplet_fields), _fields(target, tuplet_fields),
                   status='ambiguous' if ambiguous else None)
        if inferred_group:
            ledger.add(boundary, 'tuplet_grouping', identity, source['tuplet_marks'],
                       target.get('tuplet_marks') if target else None, status='unsupported',
                       reason='Original authors a ratio but no graphical group limits; generated grouping is inferred')
        if any(source.get('tuplet_extras', ())):
            ledger.add(boundary, 'tuplet_attributes', identity, source['tuplet_extras'],
                       target.get('tuplet_extras') if target else None,
                       status='unsupported' if boundary.endswith('native') else None,
                       reason='Native model retains only type/number/bracket/show-number' if boundary.endswith('native') else None)
        if boundary.endswith('native'):
            if source.get('beams'):
                ledger.add(boundary, 'beams', identity, source['beams'], None,
                           status='unsupported', reason='Native notation_events have no beam metadata')
        else:
            ledger.add(boundary, 'beams', identity, source.get('beams'),
                       target.get('beams') if target else None,
                       status='ambiguous' if ambiguous else None)
        # Additional written tie attributes have no native semantic field.
        if source.get('tied_marks'):
            ledger.add(boundary, 'written_tie_attributes', identity, source['tied_marks'],
                       target.get('tied_marks') if target else None,
                       status='unsupported' if boundary.endswith('native') else None,
                       reason='Native model only retains start/stop' if boundary.endswith('native') else None)
    for extra in extras:
        # Generated full piano lessons add an otherwise absent hand. Its blank
        # staff is a provable scaffolding normalization, not an original rest.
        absent_hand = not any(e['staff'] == extra['staff'] for e in original)
        scaffold = not direct and extra['kind'] == 'rest' and absent_hand
        ledger.add(boundary, 'staff_scaffolding' if scaffold else
                   'written_notes' if extra['kind'] == 'note' else 'written_rests',
                   extra['source'], None, _fields(extra, WRITTEN),
                   status='verified' if scaffold else None,
                   reason='Empty added hand staff; no source events assigned to it' if scaffold else
                          'Target event has no original written counterpart')
    return pairs


def _compare_measures(ledger, original, generated, model):
    by_index = defaultdict(list)
    for m in generated.measures:
        by_index[m['index']].append(m)
    for source in original.measures:
        index = source['index']
        expected = dict(label=source['label'], start_beat=source['start_beat'],
                        end_beat=source['end_beat'], meter=source['meter'],
                        keys=source['keys'], clefs=source['clefs'])
        # Multiple generated hand parts share a global grid. Compare the
        # inherited source attributes on each corresponding original hand.
        relevant = [m for m in by_index[index] if set(m['clefs']) & set(source['clefs'])]
        if not relevant:
            relevant = by_index[index]
        actual = None
        if relevant:
            first = relevant[0]
            actual = {k: first[k] for k in ('label', 'start_beat', 'end_beat', 'meter')}
            actual['keys'] = {h: next((m['keys'][h] for m in relevant if h in m['keys']), None)
                              for h in source['keys']}
            actual['clefs'] = {h: next((m['clefs'][h] for m in relevant if h in m['clefs']), None)
                               for h in source['clefs']}
        source_labels = [m['label'] for m in original.measures if m['part_index'] == source['part_index']]
        generated_labels = [m['label'] for m in generated.measures
                            if relevant and m['part_index'] == relevant[0]['part_index']]
        _measure_row(ledger, 'original->generated', source, expected, actual,
                     source_labels, generated_labels)
        native = model['measures'][index] if index < len(model['measures']) else None
        actual = None
        if native:
            actual = dict(label=str(native['number']), start_beat=native['start_beat'],
                          end_beat=native['end_beat'], meter=native['meter'],
                          keys={h: native.get('keys', {}).get(h) for h in source['keys']},
                          clefs={h: (native.get('clefs', {}).get(h, {}).get('sign'),
                                     native.get('clefs', {}).get(h, {}).get('line'),
                                     native.get('clefs', {}).get(h, {}).get('octave_change', 0))
                                 for h in source['clefs']})
        _measure_row(ledger, 'original->native', source, expected, actual,
                     source_labels, [str(m['number']) for m in model['measures']])
        for mark in source['metadata']:
            expected_timeline = _attribute_timeline([source], mark['kind'], mark['hand'])
            candidates = [m for m in by_index[index] if mark['hand'] is None or
                          mark['hand'] in m['clefs'] or mark['hand'] in m['keys']]
            timelines = [_attribute_timeline([m], mark['kind'], mark['hand']) for m in candidates]
            actual_timeline = timelines[0] if timelines and all(t == timelines[0] for t in timelines) else timelines
            ledger.add('original->generated', 'measure_attributes', mark['source'],
                       dict(kind=mark['kind'], hand=mark['hand'], timeline=expected_timeline),
                       dict(kind=mark['kind'], hand=mark['hand'], timeline=actual_timeline))
            if mark['onset']:
                ledger.add('original->native', 'mid_measure_attributes', mark['source'],
                           mark, None, status='unsupported',
                           reason='Model stores measure-start metadata only')
    expected_count = len(original.bars) - 1
    identity = dict(id='score:measure-inventory', measure=None, staff=None, voice=None)
    for boundary, count in [('original->generated', len(generated.bars)-1),
                            ('original->native', len(model['measures']))]:
        ledger.add(boundary, 'measure_structure', identity, expected_count, count)


def _attribute_timeline(measures, kind, hand):
    points = []
    for measure in measures:
        if kind == 'meter':
            inherited = measure['initial_meter']
        else:
            inherited = measure['initial_keys' if kind == 'key' else 'initial_clefs'].get(hand)
        if inherited is not None:
            points.append((0, _json(inherited)))
        for mark in measure['metadata']:
            if mark['kind'] == kind and mark['hand'] == hand:
                points.append((mark['onset'], _json(mark['value'])))
    # Repeated declarations and reprinted headers are legitimate normalization;
    # changes and the exact onset at which each takes effect are musical facts.
    by_onset = {}
    for onset, value in points:
        by_onset[onset] = value
    result = []
    for onset, value in sorted(by_onset.items()):
        if not result or result[-1][1] != value:
            result.append((onset, value))
    return result


def _measure_row(ledger, boundary, source, expected, actual, source_labels, target_labels):
    consistent = source_labels == target_labels
    textual = not all(label.lstrip('-').isdigit() for label in source_labels + target_labels)
    if not consistent and source_labels and len(source_labels) == len(target_labels):
        if textual:
            consistent = True  # Order/grid are known; textual label projection is unsupported.
        else:
            offsets = {int(b) - int(a) for a, b in zip(source_labels, target_labels)}
            consistent = len(offsets) == 1
    structure_expected = {k: v for k, v in expected.items() if k != 'label'}
    structure_expected['numbering_consistent'] = True
    structure_actual = None if actual is None else {k: v for k, v in actual.items() if k != 'label'}
    if structure_actual is not None:
        structure_actual['numbering_consistent'] = consistent
    ledger.add(boundary, 'measure_structure', source['source'], structure_expected, structure_actual)
    target_label = actual['label'] if actual else None
    ledger.add(boundary, 'measure_labels', source['source'], source['label'], target_label,
               status='unsupported' if consistent and source['label'] != target_label else None,
               reason='Consistent original-label to generated ordinal projection; original label retained in source identity'
               if consistent and source['label'] != target_label else None,
               evidence=dict(source_label=source['label'], target_label=target_label,
                             source_ordinal=source['index']+1))


def _mode(ledger, attacks, model, hand):
    expected_ids = [n['id'] for n in attacks if hand == 'both' or n['hand'] == hand]
    source = dict(id='score:hand-mode', measure=None, staff=None, voice=None)
    ledger.add('original->native', 'hand_mode', source,
               dict(active_hand=hand, active_note_ids=sorted(expected_ids)),
               dict(active_hand=model.get('active_hand'),
                    active_note_ids=sorted(model.get('active_note_ids', []))),
               evidence=dict(rule='Original-source hands select original attacks; both staves retained'))


def _original_attacks(written):
    attacks = {}
    for event in written.symbols:
        if event['kind'] != 'note':
            continue
        identifier = event['attack_id']
        if identifier not in attacks:
            attacks[identifier] = dict(id=identifier, hand=event['staff'],
                voice=f'xml-p{event["part_index"]}-s{event["raw_staff"]}-v{event["voice"]}',
                onset_beats=event['beat'], duration_beats=event['duration'],
                midi_pitch=event['pitch'], spelling=event['spelling'], source=event['source'])
        else:
            attacks[identifier]['duration_beats'] += event['duration']
    return list(attacks.values())


def _attacks(ledger, expected, model, fields, construct):
    actual = defaultdict(list)
    for n in model['notes']:
        actual[n['id']].append(n)
    expected_voices, actual_voices = defaultdict(set), defaultdict(set)
    for n in expected:
        expected_voices[n['hand'], n['voice']].add(n['id'])
    for n in model['notes']:
        actual_voices[n['hand'], n['voice']].add(n['id'])
    renamed, owners = {}, defaultdict(list)
    for key, ids in expected_voices.items():
        scores = {other: len(ids & members) for other, members in actual_voices.items() if other[0] == key[0]}
        best = max(scores.values(), default=0)
        choices = [other for other, score in scores.items() if score == best and score]
        if len(choices) == 1:
            renamed[key] = choices[0][1]
            owners[choices[0]].append(key)
    merged = {key for keys in owners.values() if len(keys) > 1 for key in keys}
    for source in expected:
        candidates = actual.pop(source['id'], [])
        target = candidates[0] if len(candidates) == 1 else None
        voice_key = source['hand'], source['voice']
        normalized = dict(source, voice=renamed.get(voice_key, source['voice']))
        ledger.add('original->native', construct, source['source'],
                   _fields(normalized, fields), _fields(target, fields),
                   status='mismatch' if voice_key in merged else None,
                   reason='Distinct original voice memberships merged' if voice_key in merged else
                          'Duplicate native attack identity' if len(candidates) > 1 else None,
                   evidence=dict(source_voice=source['voice'], native_voice=renamed.get(voice_key),
                                 rule='One injective voice rename by original physical attack identities'))
    for identifier, notes in actual.items():
        for n in notes:
            ledger.add('original->native', construct, dict(id=identifier), None, _fields(n, fields),
                       reason='Native attack has no original counterpart')


def verify_musicxml_contract(original_xml: str, generated_xml: str, native_model: dict,
                             *, hand: str = 'both') -> dict:
    """Audit original written events against BOTH independently parsed boundaries.

    Generated notation cannot define source expectations. Lane numbers may be
    renamed; membership, visibility and written segmentation may not disappear.
    Unsupported native fields and ambiguous lane anchors stay in the ledger.
    """
    if hand not in ('both', 'right', 'left'):
        raise ValueError('Invalid hand')
    original = read_written_score(original_xml, strict=False)
    generated = read_written_score(generated_xml, strict=False)
    ledger = _Ledger()
    ledger.add('original->native', 'beams', dict(id='score:beam-metadata'),
               status='unsupported', reason='Native notation_events schema has no beam membership/level fields')
    native = _native_events(native_model)
    pairs = _compare_events(ledger, original.symbols, generated.symbols, 'original->generated')
    generated_targets = {source['source']['id']: target for source, target, _ in pairs}
    _compare_events(ledger, original.symbols, native, 'original->native', generated_targets=generated_targets)
    # This third boundary also catches synthetic symbols not present in source.
    _compare_events(ledger, [e for e in generated.symbols if e['visible']], native,
                    'generated->native', direct=True)
    _compare_measures(ledger, original, generated, native_model)
    attacks = _original_attacks(original)
    _attacks(ledger, attacks, native_model,
             ('id', 'hand', 'voice', 'onset_beats', 'duration_beats', 'midi_pitch', 'spelling'),
             'source_attacks')
    _mode(ledger, attacks, native_model, hand)
    for boundary, written in [('original', original), ('generated', generated)]:
        for issue in written.issues:
            ledger.add(boundary, 'invalid_structure', issue['source'],
                       'valid timed notation', issue['reason'])
        for missing in written.uncovered:
            ledger.add(boundary, missing['construct'], missing['source'], status='unsupported',
                       reason=missing['reason'], evidence=dict(xml=missing['xml']) if 'xml' in missing else None)
    return ledger.report()


def verify_midi_performance(path: str | Path, native_model: dict, *, hand='both') -> dict:
    """Decode original MIDI ticks with Mido; never call the application loader.

    This proves physical attacks/releases/dynamics, not a unique transcription.
    Inferred hands follow the stated independent policy and remain ambiguous as
    source notation evidence when tracks do not explicitly name their hand.
    """
    import mido
    midi = mido.MidiFile(str(path))
    if midi.type == 2 or midi.ticks_per_beat <= 0:
        raise ValueError('No supported common MIDI quarter-note timeline')
    if hand not in ('both', 'right', 'left'):
        raise ValueError('Invalid hand')
    ledger = _Ledger()
    ledger.add('original->native', 'beams', dict(id='score:beam-metadata'),
               status='unsupported', reason='Native notation_events schema has no beam membership/level fields')
    notes, names, attack_tracks = [], {}, set()
    for track_index, track in enumerate(midi.tracks):
        tick, opened = 0, {}
        for ordinal, msg in enumerate(track):
            tick += msg.time
            identity = dict(id=f'midi-t{track_index}-e{ordinal}', measure=None,
                            staff=None, voice=f'midi-t{track_index}-c{getattr(msg, "channel", 0)}',
                            track=track_index, event_index=ordinal, tick=tick)
            if msg.type == 'track_name':
                names[track_index] = msg.name
            if msg.type not in ('note_on', 'note_off'):
                continue
            if msg.channel == 9:
                ledger.add('original->native', 'percussion', identity, status='unsupported',
                           reason='Percussion channel is outside piano performance comparison')
                continue
            key = msg.channel, msg.note
            if msg.type == 'note_on' and msg.velocity:
                attack_tracks.add(track_index)
                if key in opened:
                    ledger.add('original->native', 'midi_performance', identity,
                               'unambiguous note pairing', 'overlapping same-pitch attack',
                               status='ambiguous')
                    continue
                opened[key] = tick, msg.velocity, identity
            elif key in opened:
                start, velocity, attack = opened.pop(key)
                ledger.add('original->native', 'midi_release', identity, True, True,
                           evidence=dict(attack_id=attack['id'], release_tick=tick))
                if start == tick:
                    ledger.add('original->native', 'midi_performance', attack,
                               status='unsupported', reason='Zero duration is not a timed piano attack')
                    continue
                notes.append(dict(id=attack['id'], source=attack, track=track_index,
                                  channel=msg.channel, midi_pitch=msg.note, velocity=velocity,
                                  voice=attack['voice'], onset_beats=Fraction(start, midi.ticks_per_beat),
                                  duration_beats=Fraction(tick-start, midi.ticks_per_beat)))
            else:
                ledger.add('original->native', 'midi_release', identity,
                           status='unsupported', reason='Release has no source attack to compare')
        for _, _, attack in opened.values():
            ledger.add('original->native', 'midi_performance', attack,
                       'paired source release', None, reason='Unterminated original attack')
    tracks = defaultdict(list)
    for n in notes:
        tracks[n['track']].append(n['midi_pitch'])
    named = {}
    for track, name in names.items():
        for mode, pattern in [('left', r'(^|\W)(left|lh|mano sinistra)(\W|$)'),
                              ('right', r'(^|\W)(right|rh|mano destra)(\W|$)')]:
            if re.search(pattern, name, re.I):
                named[track] = mode
                break
    ranked = sorted(tracks, key=lambda t: (median(tracks[t]), t))
    policy = dict(named)
    if len(ranked) == 2:
        policy.setdefault(ranked[0], 'left')
        policy.setdefault(ranked[1], 'right')
    for n in notes:
        n['hand'] = policy.get(n['track'], 'left' if n['midi_pitch'] < 60 else 'right')
        n['source']['staff'] = n['hand']
    for track in attack_tracks:
        ledger.add('original->native', 'source_hand_assignment', dict(id=f'midi-t{track}',
                   measure=None, staff=policy.get(track), voice=None),
                   status='verified' if track in named else 'ambiguous',
                   reason='Explicit named hand' if track in named else
                          'MIDI does not author hands: two-track median rank, otherwise split at C4',
                   evidence=dict(track_name=names.get(track), policy='named > two-track rank > pitch60'))
    _attacks(ledger, notes, native_model,
             ('id', 'onset_beats', 'duration_beats', 'midi_pitch', 'velocity', 'track',
              'channel', 'voice', 'hand'), 'midi_performance')
    _mode(ledger, notes, native_model, hand)
    if not notes:
        ledger.add('original->native', 'midi_performance', dict(id='midi:empty'),
                   'at least one timed pitched attack', None)
    for construct in ('written_notes', 'written_rests', 'voices', 'ties', 'beams', 'tuplets',
                      'measure_structure', 'pedal_sounding_duration'):
        ledger.add('original->written', construct, dict(id=f'midi:unspecified:{construct}'),
                   status='unsupported', reason='MIDI performance does not uniquely specify written notation'
                   if construct != 'pedal_sounding_duration' else
                   'Only physical key release compared; sustain/sostenuto sounding durations unverified')
    ledger.add('original->written', 'midi_written_transcription', dict(id='midi:written-transcription'),
               status='unsupported', reason='MIDI has no independently authored written score to compare')
    return ledger.report()


def verify_generated_contract(generated_xml: str, native_model: dict) -> dict:
    """Generated/native consistency only; never substitute for original checks."""
    generated = read_written_score(generated_xml, strict=False)
    ledger = _Ledger()
    ledger.add('generated->native', 'beams', dict(id='score:beam-metadata'), status='unsupported',
               reason='Native notation_events schema has no beam membership/level fields')
    _compare_events(ledger, [e for e in generated.symbols if e['visible']],
                    _native_events(native_model), 'generated->native', direct=True)
    for issue in generated.issues:
        ledger.add('generated', 'invalid_structure', issue['source'],
                   'valid timed notation', issue['reason'])
    for missing in generated.uncovered:
        ledger.add('generated', missing['construct'], missing['source'], status='unsupported',
                   reason=missing['reason'])
    return ledger.report()


def combine_reports(*reports):
    ledger = _Ledger()
    for report in reports:
        ledger.elements.extend(report['elements'])
    return ledger.report()


def _raw_midi_events(data):
    """Read source event identities using stdlib only for independent accounting.

    This does not decide note pairing, hands, transcription or audit outcomes.
    It handles SMF running status, meta events and SysEx while preserving raw
    per-track event ordinals (including metadata), as defined by the file.
    """
    if data[:4] != b'MThd':
        raise ValueError('Missing MIDI header')
    header_size = int.from_bytes(data[4:8], 'big')
    if header_size < 6:
        raise ValueError('Truncated MIDI header')
    _, track_count, division = struct.unpack('>HHH', data[8:14])
    if division & 0x8000 or not division:
        raise ValueError('Unsupported MIDI time division')
    offset = 8 + header_size

    def vlq(position, end):
        value = 0
        for _ in range(4):
            if position >= end:
                raise ValueError('Truncated MIDI variable integer')
            byte = data[position]
            value = (value << 7) | (byte & 127)
            position += 1
            if byte < 128:
                return value, position
        raise ValueError('Invalid MIDI variable integer')

    for track in range(track_count):
        if data[offset:offset+4] != b'MTrk':
            raise ValueError('Missing MIDI track')
        size = int.from_bytes(data[offset+4:offset+8], 'big')
        offset += 8
        end = offset + size
        if end > len(data):
            raise ValueError('Truncated MIDI track')
        ordinal, tick, running = 0, 0, None
        while offset < end:
            delta, offset = vlq(offset, end)
            tick += delta
            status = data[offset]
            if status >= 128:
                offset += 1
            elif running is not None:
                status = running
            else:
                raise ValueError('MIDI running status without preceding channel message')
            if status == 0xff:
                offset += 1  # meta type
                size, offset = vlq(offset, end)
                offset += size
            elif status in (0xf0, 0xf7):
                size, offset = vlq(offset, end)
                offset += size
            elif 0x80 <= status <= 0xef:
                running = status
                size = 1 if status >> 4 in (0xc, 0xd) else 2
                payload = data[offset:offset+size]
                offset += size
                if len(payload) != size:
                    raise ValueError('Truncated MIDI channel message')
                if status >> 4 in (0x8, 0x9):
                    yield dict(track=track, event_index=ordinal, tick=tick,
                               channel=status & 15, pitch=payload[0],
                               attack=(status >> 4 == 0x9 and payload[1] > 0))
            else:
                raise ValueError(f'Unsupported MIDI status {status:x}')
            if offset > end:
                raise ValueError('MIDI event extends past its track')
            ordinal += 1


def source_inventory(path: str | Path) -> list[dict]:
    """Required ledger projection reconstructed from ORIGINAL bytes, stdlib only.

    Aggregators must require every returned ID exactly once in the report, in
    addition to validating all observed statuses. Extra generated/native rows
    are allowed and are also subject to the gate. Neither counters supplied by
    the producer nor a report's own copy of this inventory establish coverage.
    No model, lesson builder, application importer, Mido or visual code runs.
    """
    path = Path(path)
    ledger = _Ledger()
    if path.suffix.lower() in ('.mid', '.midi'):
        tracks = set()
        ledger.add('original->native', 'beams', dict(id='score:beam-metadata'))
        for event in _raw_midi_events(path.read_bytes()):
            identity = dict(id=f'midi-t{event["track"]}-e{event["event_index"]}',
                            measure=None, staff=None,
                            voice=f'midi-t{event["track"]}-c{event["channel"]}')
            construct = ('percussion' if event['channel'] == 9 else
                         'midi_performance' if event['attack'] else 'midi_release')
            ledger.add('original->native', construct, identity)
            if event['attack'] and event['channel'] != 9:
                tracks.add(event['track'])
        for track in sorted(tracks):
            ledger.add('original->native', 'source_hand_assignment', dict(id=f'midi-t{track}'))
        for construct in ('written_notes', 'written_rests', 'voices', 'ties', 'beams', 'tuplets',
                          'measure_structure', 'pedal_sounding_duration'):
            ledger.add('original->written', construct, dict(id=f'midi:unspecified:{construct}'))
        ledger.add('original->written', 'midi_written_transcription', dict(id='midi:written-transcription'))
    else:
        original = read_written_score(path.read_text(encoding='utf-8'), strict=False)
        authored = _authored_tuplet_events(original.symbols)
        ledger.add('original->native', 'beams', dict(id='score:beam-metadata'))
        for source in original.symbols:
            for boundary in ('original->generated', 'original->native'):
                construct = 'written_notes' if source['kind'] == 'note' else 'written_rests'
                for kind in (construct, 'voices', 'ties', 'tuplets'):
                    ledger.add(boundary, kind, source['source'])
                if boundary == 'original->native' and source['kind'] == 'note':
                    ledger.add(boundary, 'source_binding', source['source'])
                if source.get('time_modification') is not None and source['source']['id'] not in authored:
                    ledger.add(boundary, 'tuplet_grouping', source['source'])
                if any(source.get('tuplet_extras', ())):
                    ledger.add(boundary, 'tuplet_attributes', source['source'])
                if boundary == 'original->generated' or source.get('beams'):
                    ledger.add(boundary, 'beams', source['source'])
                if source.get('tied_marks'):
                    ledger.add(boundary, 'written_tie_attributes', source['source'])
        for source in original.measures:
            for boundary in ('original->generated', 'original->native'):
                ledger.add(boundary, 'measure_structure', source['source'])
                ledger.add(boundary, 'measure_labels', source['source'])
            for mark in source['metadata']:
                ledger.add('original->generated', 'measure_attributes', mark['source'])
                if mark['onset']:
                    ledger.add('original->native', 'mid_measure_attributes', mark['source'])
        for boundary in ('original->generated', 'original->native'):
            ledger.add(boundary, 'measure_structure', dict(id='score:measure-inventory'))
        for source in _original_attacks(original):
            ledger.add('original->native', 'source_attacks', source['source'])
        for missing in original.uncovered:
            ledger.add('original', missing['construct'], missing['source'])
        for issue in original.issues:
            ledger.add('original', 'invalid_structure', issue['source'])
    ledger.add('original->native', 'hand_mode', dict(id='score:hand-mode'))
    return [{k: row[k] for k in ('id', 'boundary', 'construct', 'source')}
            for row in ledger.elements]
