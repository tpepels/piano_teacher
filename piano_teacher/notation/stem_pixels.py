"""Source-group physical shaft measurement and exclusive ownership.

An independent Verovio reference bounds extension. Assignment remains local
to each onset, including every competing source group and actual shaft.
"""
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
import re
from xml.etree import ElementTree as ET

from .feature_contract import feature_result
from .feature_source import event_identity
from .pixel_ink import pixel_runs


@lru_cache(maxsize=512)
def reference_stem_extension(kind: str, intervals: tuple[int, ...], direction: str) -> float:
    """Ask Verovio about the same chord interval pattern in a neutral register.

    This is independently engraved from source intervals, never read from a
    native atlas. Verovio legitimately shortens stems for some chord/flag
    combinations; a universal three-space rule rejects its own engraving.
    """
    import verovio
    values = {'half': 2, 'quarter': 1, 'eighth': .5, '16th': .25,
              '32nd': .125, '64th': .0625, '128th': .03125}
    if kind not in values:
        raise ValueError('No independent stem reference for this written type')
    notes = []
    for i, offset in enumerate(intervals):
        octave, index = divmod(34+offset, 7)
        notes.append(f'<note id="ref{i}">' + ('<chord/>' if i else '') +
                     f'<pitch><step>{"CDEFGAB"[index]}</step><octave>{octave}</octave></pitch>'
                     f'<duration>{round(values[kind]*10080)}</duration><type>{kind}</type>' +
                     (f'<stem>{direction}</stem>' if not i else '') + '</note>')
    xml = ('<score-partwise version="4.0"><part-list><score-part id="P1">'
           '<part-name>Piano</part-name></score-part></part-list><part id="P1">'
           '<measure number="1"><attributes><divisions>10080</divisions>'
           '<time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign>'
           '<line>2</line></clef></attributes>'+''.join(notes)+
           '</measure></part></score-partwise>')
    toolkit = verovio.toolkit()
    toolkit.setOptions({'breaks': 'none', 'header': 'none', 'footer': 'none', 'font': 'Leipzig'})
    if not toolkit.loadData(xml):
        raise ValueError('Independent chord stem reference failed to engrave')
    svg = ET.fromstring(toolkit.renderToSVG(1))
    ns = '{http://www.w3.org/2000/svg}'
    staff = next(n for n in svg.iter() if n.get('class') == 'staff')
    rails = [float(re.findall(r'-?[0-9.]+', n.get('d'))[1])
             for n in list(staff) if n.tag == ns+'path'][:5]
    gap = (max(rails)-min(rails))/4
    stem = next(n for n in staff.iter() if n.get('class') == 'stem')
    path = next(n for n in stem.iter() if n.tag == ns+'path')
    ends = list(map(float, re.findall(r'-?[0-9.]+', path.get('d'))))[1::2]
    ys = []
    for note in staff.iter():
        if note.get('id', '').startswith('ref') and note.get('class') == 'note':
            head = next(n for n in note.iter() if n.get('class') == 'notehead')
            use = next(n for n in head.iter() if n.tag == ns+'use')
            ys.append(float(re.search(r'translate\([^,]+,\s*([-0-9.]+)', use.get('transform')).group(1)))
    if len(ys) != len(intervals) or gap <= 0:
        raise ValueError('Independent chord stem/head accounting failed')
    return (min(ys)-min(ends))/gap if direction == 'up' else (max(ends)-max(ys))/gap


def _stem_runs_touch(first, second):
    """Adjacent continuous columns are one physical shaft, not two owners."""
    return any(abs(x-xx) <= 1 and max(top, yy) < min(bottom, end)
               for x, top, bottom in first for xx, yy, end in second)


def _stem_run_clusters(runs):
    remaining = list(runs)
    clusters = []
    while remaining:
        cluster = [remaining.pop(0)]
        while True:
            joined = [r for r in remaining if _stem_runs_touch(cluster, [r])]
            if not joined:
                break
            cluster.extend(joined)
            remaining = [r for r in remaining if r not in joined]
        clusters.append(sorted(cluster))
    return clusters


def _stem(pixels, group, heads, marks):
    ids = [event_identity(n) for n in group]
    evidence = dict(group_id=group[0]['source']['id'], shared_source_ids=ids)
    if len(group) > 6:
        return feature_result('unsupported', 'Bounded stem grouping is limited to six source chord tones', **evidence)
    if any(n['source']['id'] not in heads for n in group):
        return feature_result('unverified', 'Every source chord head must first register in the current image', **evidence)
    hs = [heads[n['source']['id']] for n in group]
    gap = hs[0]['gap']
    directions = {marks[n['source']['id']]['stem'] or heads[n['source']['id']].get('shared_stem_direction')
                  for n in group} - {None}
    if directions - {'up', 'down'} or len(directions) > 1:
        return feature_result('unsupported', 'Conflicting, absent or specialized explicit stem declarations', **evidence)
    low, high = min(h['y'] for h in hs), max(h['y'] for h in hs)
    absolute = [int(n['spelling'][2])*7+'CDEFGAB'.index(n['spelling'][0]) for n in group]
    intervals = tuple(n-absolute[0] for n in absolute)
    candidates = []
    references = {}
    # Require an unbroken actual column attached to every source chord head.
    # Its minimum outer extension comes from independent Verovio engraving,
    # retaining a sub-step raster tolerance, rather than a fixed print length.
    for direction in directions or ('up', 'down'):
        try:
            extension = reference_stem_extension(group[0]['note_type'], intervals, direction)
        except (ValueError, StopIteration, TypeError) as exc:
            return feature_result('unsupported', str(exc), **evidence)
        references[direction] = extension
        minimum = max(0, extension-.21)*gap
        sign = 1 if direction == 'up' else -1
        columns=None
        for h in hs:
            xs=[p % pixels.shape[1] for p in h['support']]
            # Seconds sit on opposite sides of their ONE shared stem.
            # Require the same actual column beside either edge of every
            # independently registered head; do not average displaced Xs.
            edges=(min(xs),max(xs)) if len(hs)>1 else ((max(xs) if sign==1 else min(xs)),)
            attached={x for edge in edges for x in range(edge-2,edge+3)}
            columns=attached if columns is None else columns & attached
        for x in sorted(columns):
            if not 0 <= x < pixels.shape[1]:
                continue
            for top, bottom in pixel_runs(pixels[:, x]):
                if direction == 'up':
                    valid = low-8*gap <= top <= low-minimum and high-.5*gap <= bottom <= high+.5*gap
                else:
                    valid = low-.5*gap <= top <= low+.5*gap and high+minimum <= bottom <= high+8*gap
                if valid and all(top <= h['y'] <= bottom for h in hs):
                    candidates.append((direction, x, top, bottom))
    if not candidates:
        return feature_result('unverified', 'No continuous stem attached to every registered head with reference-supported extension',
                       **evidence, reference_extensions=references)
    options = []
    for direction in ('up', 'down'):
        for runs in _stem_run_clusters([c[1:] for c in candidates if c[0] == direction]):
            x = round(sum(c[0] for c in runs)/len(runs))
            top, bottom = min(c[1] for c in runs), max(c[2] for c in runs)
            bbox = [min(c[0] for c in runs), top, max(c[0] for c in runs)+1, bottom]
            options.append(feature_result('verified', 'Continuous pixel stem attaches the source chord heads',
                **evidence, bbox=bbox, direction=direction, x=x,
                tip_y=top if direction == 'up' else bottom-1,
                reference_extension_spaces=references[direction],
                head_matches=[round(h['score'], 4) for h in hs], shaft_runs=[list(r) for r in runs]))
    result = dict(options[0]) if len(options) == 1 else feature_result(
        'ambiguous', 'Multiple physical shafts or directions attach to this source group', **evidence)
    result['_shaft_options'] = options
    return result


def measure_stem_ownership(pixels, groups, heads, marks):
    """Assign physical shafts once, allowing only declared chords to share.

    A column may cross another voice's head. Joint ownership can still be
    unique when both voices have separate valid shafts. A single compound
    shaft touching several independent groups cannot certify just its lowest
    head while silently ignoring the other attached source obligations.
    """
    measured = [_stem(pixels, group, heads, marks) for group in groups]
    options = [(i, value) for i, result in enumerate(measured)
               for value in result.get('_shaft_options', [])]
    physical = []
    for i, value in options:
        runs = value['evidence']['shaft_runs']
        joined = [node for node in physical if _stem_runs_touch(runs, node['runs'])]
        node = dict(runs=list(runs), options=[(i, value)])
        for other in joined:
            node['runs'].extend(other['runs'])
            node['options'].extend(other['options'])
            physical.remove(other)
        node['runs'] = sorted(set(map(tuple, node['runs'])))
        physical.append(node)
    eligible = defaultdict(set)
    attachments = defaultdict(set)
    for index, node in enumerate(physical):
        for i, _value in node['options']:
            eligible[i].add(index)
            attachments[i].add(index)
        for i, group in enumerate(groups):
            for note in group:
                head = heads.get(note['source']['id'])
                if head is None or note['note_type'] in ('whole', 'breve', 'long', 'maxima'):
                    continue
                xs = [p % pixels.shape[1] for p in head['support']]
                if any(top <= head['y'] < bottom and
                       min(abs(x-min(xs)), abs(x-max(xs))) <= 2
                       for x, top, bottom in node['runs']):
                    attachments[i].add(index)
    remaining = set(attachments)
    while remaining:
        component, nodes = {min(remaining)}, set()
        while True:
            expanded = set().union(*(attachments[i] for i in component))
            neighbors = {i for i in remaining if attachments[i] & expanded}
            if neighbors <= component:
                nodes = expanded
                break
            component.update(neighbors)
        remaining.difference_update(component)
        def matching(forbidden=None):
            owners = {}

            def attach(i, seen):
                for node in sorted(eligible[i]):
                    if node in seen or forbidden == (i, node):
                        continue
                    seen.add(node)
                    if node not in owners or attach(owners[node], seen):
                        owners[node] = i
                        return True
                return False

            if all(attach(i, set()) for i in sorted(component)):
                return {i:node for node, i in owners.items()}
            return None

        assignment = matching()
        # Another complete assignment must omit at least one chosen edge.
        # Rechecking those edges avoids enumerating factorial permutations
        # when a dense full-performance onset has insufficient shafts.
        unique = assignment is not None and not any(
            matching((i, node)) is not None for i, node in assignment.items())
        for i in component:
            if unique:
                node_index = assignment[i]
                choices = [value for owner, value in physical[node_index]['options'] if owner == i]
                if len(choices) == 1:
                    measured[i] = deepcopy(choices[0])
                    runs = physical[node_index]['runs']
                    measured[i]['evidence']['physical_shaft_id'] = 'shaft:'+':'.join(map(str, (
                        min(r[0] for r in runs), min(r[1] for r in runs),
                        max(r[0] for r in runs)+1, max(r[2] for r in runs))))
                    continue
            evidence = dict(measured[i]['evidence'],
                competing_group_ids=[groups[j][0]['source']['id'] for j in sorted(component)],
                physical_shaft_count=len(nodes))
            measured[i] = feature_result('ambiguous',
                'Source groups do not have a unique assignment to separate physical stem shafts', **evidence)
    for result in measured:
        result.pop('_shaft_options', None)
    return measured
