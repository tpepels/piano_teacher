"""Project immutable source events onto an exercise, with an omission ledger."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from math import lcm
from xml.etree import ElementTree as ET

from .source import SourceNotation, identity

SUPPORTED_MARKS = frozenset({'dynamics', 'wedge', 'pedal', 'articulations',
    'ornaments', 'fermata', 'arpeggiate', 'non-arpeggiate', 'technical', 'words',
    'octave-shift', 'rehearsal', 'segno', 'coda', 'bracket', 'dashes'})


def project_lesson(phrase, source: SourceNotation, **context):
    from .lesson import build_lesson_score, DIVISIONS, _append_note
    # Generate only staff/meter/key/clef context, not a second rendition of
    # the selected notes. Event projection below owns every emitted note.
    shell = build_lesson_score(replace(phrase, notes=()), **context)
    root = ET.fromstring(shell.musicxml)
    retained = {n.source_id: n for n in phrase.notes}
    active_hands = {n.hand for n in phrase.notes}
    start, end = Fraction(str(phrase.start)), Fraction(str(phrase.end))
    from ..measure_grid import phrase_grid
    grid = phrase_grid(phrase, context.get('boundaries', ()))
    written_grid = [Fraction(*value) for value in source.measure_boundaries[
        phrase.first_bar-1:phrase.last_bar+1]]
    if (len(written_grid) == len(grid)
            and abs(float(written_grid[0])-phrase.start) < 1e-7
            and abs(float(written_grid[-1])-phrase.end) < 1e-7):
        # Reconcile the public float boundary with its original rational
        # value, never round a written event onto a different rhythmic grid.
        start, end = written_grid[0], written_grid[-1]
    else:
        written_grid = [start+Fraction(str(value)) for value in grid]
    events = {e.id: e for e in source.events}
    selected = {e.id for e in source.events if e.source_id in retained
                and start <= Fraction(*e.beat) < end}
    lane_hands = {(e.voice, e.hand) for e in source.events if e.id in selected}
    pitched_lanes = {(e.voice,e.hand) for e in source.events if e.source_id is not None
                     and start <= Fraction(*e.beat) < end}
    # A staff containing original rests alone is still written music. It is
    # distinct from a voice whose pitched attacks the exercise removed.
    lane_hands.update((e.voice,e.hand) for e in source.events
        if (e.voice,e.hand) not in pitched_lanes
        and ET.fromstring(e.xml).find('rest') is not None
        and start <= Fraction(*e.beat) < end)
    visible_rests = {e.id for e in source.events if e.source_id is None
        and ET.fromstring(e.xml).find('rest') is not None
        and (e.voice, e.hand) in lane_hands and start <= Fraction(*e.beat) < end}
    kept_ids = selected | visible_rests
    report, omitted_marks = [], set()
    kept_groups = []
    for group in source.groups:
        intact = (len(group.mark_ids) == 2 and group.event_ids
                  and group.event_ids[0] in kept_ids and group.event_ids[-1] in kept_ids)
        reason = '' if intact else ('unclosed_source_span' if len(group.mark_ids) != 2 else 'endpoint_removed')
        report.append({'id': group.id, 'kind': group.kind,
                       'status': 'preserved' if intact else 'omitted', 'reason': reason})
        if intact:
            kept_groups.append(group)
        else:
            omitted_marks.update(group.mark_ids)
            omitted_marks.update(group.continuation_ids)

    divisions = DIVISIONS
    for event in source.events:
        if event.id in kept_ids:
            divisions = lcm(divisions, event.beat[1], event.duration[1])
    for mark in source.marks:
        divisions = lcm(divisions, mark.beat[1])
    divisions = lcm(divisions, start.denominator, end.denominator)
    for boundary in written_grid:
        divisions = lcm(divisions, boundary.denominator)
    # A source division declaration is independent of grading precision.
    # Preserve representable written values, including many dots, exactly.
    lane_numbers = {hand: {voice: index+1 for index, voice in enumerate(sorted(
        v for v, h in lane_hands if h == hand))} for hand in ('right', 'left')}
    emitted, bindings, grace_events = {}, {}, []
    global_event_map = {}
    source_first = {}
    for event in source.events:
        if event.id in selected:
            source_first.setdefault(event.source_id, event.id)

    graces_by_event = defaultdict(list)
    for grace in source.events:
        if not grace.anchor_id or grace.anchor_id not in retained:
            continue
        node = ET.fromstring(grace.xml)
        after = node.find('grace').get('steal-time-previous') is not None
        if after:
            # An after-grace belongs to the written release, including the
            # final segment of a tied principal, rather than its first attack.
            principal = next((e for e in source.events if e.id in selected
                and e.source_id == grace.anchor_id and e.voice == grace.voice
                and Fraction(*e.beat)+Fraction(*e.duration) == Fraction(*grace.beat)), None)
        else:
            principal = events.get(source_first.get(grace.anchor_id))
        if principal is not None and start <= Fraction(*grace.beat) <= end:
            graces_by_event[principal.id].append((grace, after))

    marks_by_id = {m.id: m for m in source.marks}
    annotations = []
    projected_endings = []
    projected_directions = []
    inherited = {}
    state = {}
    for mark in sorted(source.marks, key=lambda m: Fraction(*m.beat)):
        if mark.kind == 'ending':
            at=Fraction(*mark.beat)
            keep=start <= at <= end
            report.append({'id':mark.id,'kind':'ending','status':'preserved' if keep else 'omitted',
                'reason':'' if keep else 'outside_excerpt'})
            if keep:
                projected_endings.append(mark)
            continue
        if mark.event_id:
            keep = mark.event_id in kept_ids
            report.append({'id': mark.id, 'kind': mark.kind,
                'status': ('preserved' if mark.kind in SUPPORTED_MARKS else 'unsupported') if keep else 'omitted',
                'reason': '' if keep and mark.kind in SUPPORTED_MARKS else 'unsupported_instruction' if keep else 'note_removed'})
            if keep:
                annotations.append({'id': mark.id, 'kind': mark.kind,
                    'beat': float(Fraction(*mark.beat)-start), 'staff': mark.hand,
                    'voice': mark.voice, 'event_ids': [mark.event_id],
                    'attributes': dict(ET.fromstring(mark.xml).attrib)})
            continue
        at = Fraction(*mark.beat)
        hand_ok = mark.hand == 'both' or mark.hand in active_hands
        node = ET.fromstring(mark.xml)
        instruction = node.find('direction-type')[0]
        value = instruction.get('type', '')
        key = mark.kind, mark.hand, mark.voice
        if at < start and hand_ok and mark.kind in ('dynamics', 'pedal', 'octave-shift'):
            if value in ('stop', 'discontinue'):
                inherited.pop(key, None)
            else:
                inherited[key] = mark
        keep = hand_ok and start <= at <= end
        report.append({'id': mark.id, 'kind': mark.kind,
            'status': ('preserved' if mark.kind in SUPPORTED_MARKS else 'unsupported') if keep else 'omitted',
            'reason': '' if keep and mark.kind in SUPPORTED_MARKS else 'unsupported_instruction' if keep else 'outside_excerpt' if hand_ok else 'staff_removed'})
        if keep:
            projected_directions.append((mark, at, False))
    for mark in inherited.values():
        row = next(r for r in report if r['id'] == mark.id)
        row.update(status='inherited', reason='active_at_excerpt_start')
        projected_directions.append((mark, start, True))

    # Build complete voice streams from selected source records. Omitted
    # pitches become rests; their articulations and identity never transfer.
    for hand, part in zip(('right', 'left'), root.findall('part')):
        measures = part.findall('measure')
        for measure in measures:
            for child in list(measure):
                if child.tag not in ('attributes', 'barline'):
                    measure.remove(child)
            attrs = measure.find('attributes')
            if attrs is not None and attrs.find('divisions') is not None:
                attrs.find('divisions').text = str(divisions)
        for mi, measure in enumerate(measures):
            lo, hi = written_grid[mi:mi+2]
            duration_ticks = round((hi-lo)*divisions)
            right_bars = [b for b in measure.findall('barline') if b.get('location','right') == 'right']
            for bar in right_bars:
                measure.remove(bar)
            for li, (voice, number) in enumerate(lane_numbers[hand].items() or [('empty', 1)]):
                if li:
                    ET.SubElement(ET.SubElement(measure, 'backup'), 'duration').text = str(duration_ticks)
                position = lo
                candidates = [e for e in source.events if e.voice == voice and e.hand == hand
                    and Fraction(*e.duration) > 0 and lo <= Fraction(*e.beat) < hi]
                by_onset = defaultdict(list)
                for event in candidates:
                    by_onset[Fraction(*event.beat)].append(event)
                def rest(a, b):
                    if b <= a:
                        return
                    # Gap rests have exact values, but are never source notes.
                    _append_note(measure, None, round((b-a)*divisions), number)
                    tag = measure[-1]
                    tag.set('id', identity(f'rest:{hand}:{voice}:{a}:{b}'))
                    # _append_note's type helper uses DIVISIONS. Correct the
                    # notation ratio if this source needs finer divisions.
                    if divisions != DIVISIONS:
                        for child in list(tag):
                            if child.tag in ('type','dot','time-modification','notations'):
                                tag.remove(child)
                        ET.SubElement(tag,'type').text='quarter'
                        mod=ET.SubElement(tag,'time-modification')
                        rat=(b-a)
                        ET.SubElement(mod,'actual-notes').text=str(rat.denominator)
                        ET.SubElement(mod,'normal-notes').text=str(rat.numerator)
                def append_grace(grace, principal, after):
                    g = ET.fromstring(grace.xml)
                    g.set('id', grace.id)
                    gv = g.find('voice')
                    if gv is None:
                        gv = ET.SubElement(g, 'voice')
                    gv.text = str(number)
                    gs = g.find('staff')
                    if gs is not None:
                        g.remove(gs)
                    measure.append(g)
                    pitch = g.find('pitch')
                    spelling = {'step':pitch.findtext('step'),
                        'alter':int(pitch.findtext('alter','0')),
                        'octave':int(pitch.findtext('octave'))}
                    midi = (spelling['octave']+1)*12+{'C':0,'D':2,'E':4,
                        'F':5,'G':7,'A':9,'B':11}[spelling['step']]+spelling['alter']
                    grace_events.append({'id':grace.id,'kind':'grace',
                        'anchor_id':principal.id,'anchor_source_id':principal.source_id,
                        'beat':float(Fraction(*grace.beat)-start),'staff':hand,
                        'layout_beat':float(Fraction(*principal.beat)-start),
                        'voice':str(number),'midi_pitch':midi,'spelling':spelling,
                        'note_type':g.findtext('type','eighth'),'dots':len(g.findall('dot')),
                        'slash':g.find('grace').get('slash','no'),
                        'position':'after' if after else 'before'})
                for at, cluster in sorted(by_onset.items()):
                    retained_cluster = [e for e in cluster if e.id in selected]
                    source_rests = [e for e in cluster if e.id in visible_rests]
                    chosen = retained_cluster or source_rests or cluster[:1]
                    rest(position, at)
                    cluster_graces = [(grace, event, after) for event in chosen
                        for grace, after in graces_by_event[event.id]]
                    for grace, principal, after in cluster_graces:
                        if not after:
                            append_grace(grace, principal, after)
                    for ci, event in enumerate(chosen):
                        node = ET.fromstring(event.xml)
                        placeholder = event.source_id is not None and event.id not in selected
                        if placeholder:
                            for child in list(node):
                                if child.tag not in ('duration','voice','type','dot','time-modification','notations'):
                                    node.remove(child)
                                elif child.tag == 'notations':
                                    for mark in list(child):
                                        if mark.tag != 'tuplet':
                                            child.remove(mark)
                            node.insert(0,ET.Element('rest'))
                        length = min(Fraction(*event.duration), hi-at)
                        node.find('duration').text = str(round(length*divisions))
                        v = node.find('voice')
                        if v is None:
                            v = ET.SubElement(node,'voice')
                        v.text = str(number)
                        staff = node.find('staff')
                        if staff is not None:
                            node.remove(staff)
                        old_chord = node.find('chord')
                        if ci == 0 and old_chord is not None:
                            node.remove(old_chord)
                        elif ci > 0 and old_chord is None:
                            node.insert(0, ET.Element('chord'))
                        for parent in node.iter():
                            for tag in list(parent):
                                if tag.get('id') in omitted_marks:
                                    parent.remove(tag)
                        if event.source_id and not placeholder:
                            n = retained[event.source_id]
                            bindings[event.id] = {'source_id': event.source_id,
                                'source_beat': n.start-phrase.start, 'pitch': n.pitch,
                                'hand': hand, 'is_attack': event.id == source_first[event.source_id],
                                'segment_index': sum(b['source_id'] == event.source_id for b in bindings.values()),
                                'display_beat': float(at-start)}
                        emitted[event.id] = node
                        global_event_map[event.id] = event.id
                        measure.append(node)
                    # Keep the complete chord contiguous; grace notes cannot
                    # become an intervening principal for a chord follower.
                    for grace, principal, after in cluster_graces:
                        if after:
                            append_grace(grace, principal, after)
                    position = at + min(Fraction(*chosen[0].duration), hi-at)
                rest(position, hi)
            for mark, at, inherited_mark in sorted(projected_directions, key=lambda r:r[1]):
                target_hand = ('left' if 'left' in active_hands else 'right') if mark.hand == 'both' else mark.hand
                if target_hand != hand or not (lo <= at < hi or (mi == len(measures)-1 and at == hi)):
                    continue
                direction=ET.fromstring(mark.xml)
                for tag in list(direction):
                    if tag.tag in ('offset','staff','voice'):
                        direction.remove(tag)
                # Directions are inserted at the beginning, with offsets that
                # do not advance or rewind any source note/voice cursor.
                ET.SubElement(direction,'offset').text=str(round((at-lo)*divisions))
                insert_at = next((i for i,c in enumerate(measure) if c.tag not in ('attributes','direction')),len(measure))
                measure.insert(insert_at,direction)
                instruction=direction.find('direction-type')[0]
                record={'id':mark.id,'kind':mark.kind,'beat':float(at-start),
                    'staff':hand,'voice':mark.voice,'event_ids':[],
                    'attributes':dict(instruction.attrib),'inherited':inherited_mark}
                value=instruction.get('type','')
                key=(mark.kind,hand,instruction.get('number','1'))
                if value in ('stop','discontinue') and key in state:
                    state[key]['end_beat']=float(at-start)
                    state[key]['end_id']=mark.id
                    del state[key]
                else:
                    annotations.append(record)
                    if mark.kind in ('wedge','pedal','octave-shift','bracket','dashes') and value not in ('stop','discontinue'):
                        state[key]=record
            measure.extend(right_bars)
    for record in state.values():
        record['end_beat']=float(end-start)
        record['continues_after_excerpt']=True
    pending_endings={}
    for mark in projected_endings:
        original=ET.fromstring(mark.xml)
        attributes=dict(original.attrib)
        at=float(Fraction(*mark.beat)-start)
        for measure in root.find('part').findall('measure'):
            for tag in measure.findall('barline/ending'):
                if tag.get('number') == original.get('number') and tag.get('type') == original.get('type') and tag.get('id') is None:
                    tag.set('id',mark.id)
                    break
        number=original.get('number','1')
        if original.get('type') == 'start':
            record={'id':mark.id,'kind':'ending','beat':at,'end_beat':float(end-start),
                'staff':'right','voice':'','event_ids':[],'attributes':attributes}
            pending_endings[number]=record
            annotations.append(record)
        elif number in pending_endings:
            pending_endings.pop(number)['end_beat']=at
    group_records=[]
    for group in kept_groups:
        members=[e for e in group.event_ids if e in global_event_map]
        if not members:
            continue
        first,last=events[members[0]],events[members[-1]]
        group_records.append({'id':group.id,'kind':group.kind,'event_ids':members,
            'start_beat':float(Fraction(*first.beat)-start),'end_beat':float(Fraction(*last.beat)-start),
            'staff':first.hand,'voice':first.voice,'attributes':dict(group.attributes)})
    for grace in source.events:
        if ET.fromstring(grace.xml).find('grace') is not None:
            keep=any(g['id']==grace.id for g in grace_events)
            report.append({'id':grace.id,'kind':'grace','status':'preserved' if keep else 'omitted',
                'reason':'' if keep else 'anchor_removed'})
    return replace(shell, musicxml=ET.tostring(root,encoding='unicode'), phrase=phrase,
        note_bindings=bindings, annotations=tuple(annotations), groups=tuple(group_records),
        visual_events=tuple(grace_events), projection_report=tuple(report), divisions=divisions,
        source_projected=True)
