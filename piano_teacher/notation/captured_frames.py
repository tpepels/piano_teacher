"""Per-verifier-call captured-frame, anchor, and translation ownership.

Decoded PNG evidence is LRU bounded to 16 frames. Registration caches retain
only scalar anchors, not image support sets. Each instance owns its own clock
index and caches; neither callers nor native telemetry provide coordinates.
"""
from bisect import bisect_left, bisect_right
from collections import OrderedDict, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from .head_registration import register_noteheads
from .pixel_context import rectangular_rest_orientation
from .pixel_ink import bright, translating_ink
from .pixel_motion import register_translation
from .pixel_proof import playhead_x
from .photographed_staff_rails import PhotographedStaffRails
from .raster_matching import _joint_candidates, match_glyph
from .reference_font import reference_glyphs

FRAME_CACHE_LIMIT = 16


class CapturedFrames:
    def __init__(self, folder, written):
        self.folder, self.written = Path(folder), written
        self.frames, self.registrations, self.translations = OrderedDict(), {}, {}
        self.notes_by_beat, self.rests_by_onset = defaultdict(list), defaultdict(list)
        for event in written.symbols:
            if not event['visible']:
                continue
            if event['kind'] == 'note':
                self.notes_by_beat[event['beat']].append(event)
            elif event['kind'] == 'rest':
                self.rests_by_onset[event['staff'], event['beat']].append(event)
        clocks = set()
        for path in self.folder.glob('native-*.png'):
            try:
                clocks.add(float(path.stem.removeprefix('native-')))
            except ValueError:
                continue
        self.clocks = tuple(sorted(clocks))
        self.staff_rails = PhotographedStaffRails(self.folder, captured_clocks=self.clocks)

    def nearby_clocks(self, targets, limit=4):
        center = float(sum(targets)/len(targets)) if targets else 0.
        excluded = {round(float(t), 5) for t in targets}
        right = bisect_left(self.clocks, center)
        left, selected = right-1, []
        while len(selected) < limit and (left >= 0 or right < len(self.clocks)):
            if right == len(self.clocks) or (left >= 0 and center-self.clocks[left] <= self.clocks[right]-center):
                clock = self.clocks[left]
                left -= 1
            else:
                clock = self.clocks[right]
                right += 1
            if clock not in excluded:
                selected.append(clock)
        return selected

    def post_group_clocks(self, targets, limit=4):
        """Additional REAL source-window photos after the final attack.

        A fixed playhead covers a beam's rightmost attachment at every
        onset in the group. At the first later photographed clock the whole
        group has moved left of that coloured line; only then can its actual
        uninterrupted body be inspected. Select existing PNG clocks only,
        within half a beat of the last authored event. The independent
        head/translation/visibility checks still decide if each photograph
        is usable. Never manufacture a frame, position or source obligation.
        """
        if not targets or limit < 1:
            return []
        end = max(float(value) for value in targets)
        selected = []
        index = bisect_right(self.clocks, end + 1e-5)
        latest = end + .5 + 1e-5
        while index < len(self.clocks) and len(selected) < limit:
            clock = self.clocks[index]
            if clock > latest:
                break
            selected.append(clock)
            index += 1
        return selected

    def frame(self, beat):
        beat = float(beat)
        if beat not in self.frames:
            name = f'native-{beat:.5f}.png'
            with Image.open(self.folder/name) as raw:
                image = raw.convert('RGB')
            rgb = np.asarray(image).astype(int)
            cyan = (rgb[:, :, 1]-rgb[:, :, 0] > 30) & (rgb[:, :, 2]-rgb[:, :, 0] > 15) & (rgb[:, :, 1] > 150)
            occluded = np.flatnonzero(cyan.sum(axis=0) > image.height*.35)
            # Texture resampling can leave a one-pixel subthreshold edge
            # inside a continuous beam. Retain that *photographed* dim ink
            # separately, never infer a missing beam from source geometry.
            # It is only consulted where two full-bright neighbors enclose
            # the same physical pixel; a genuinely erased pixel stays dark.
            beam_edge = ((rgb[:, :, 0] >= 115) &
                         (rgb[:, :, 1] >= 130) &
                         (rgb[:, :, 2] >= 120))
            self.frames[beat] = dict(name=name, pixels=bright(image),
                                     beam_edge=beam_edge,
                                     motion=translating_ink(image),
                                     staves=self.staff_rails.detect(image),
                                     occluded_columns=occluded, playhead_x=playhead_x(image))
            if len(self.frames) > FRAME_CACHE_LIMIT:
                self.frames.popitem(last=False)
        self.frames.move_to_end(beat)
        return self.frames[beat]

    def head(self, event):
        beat = event['beat']
        if beat not in self.registrations:
            frame = self.frame(beat)
            heads, errors = register_noteheads(frame['pixels'], frame['staves'], self.written,
                                     self.notes_by_beat[beat], reference_glyphs(),
                                     playhead_x=frame['playhead_x'])
            # Assignment support pixels are needed only during registration;
            # keep scalar anchors, never an image-sized support set per note.
            self.registrations[beat] = ({sid: {key: head[key] for key in ('x', 'y', 'bbox', 'score', 'gap')}
                                         for sid, head in heads.items()}, errors)
        heads, errors = self.registrations[beat]
        sid = event['source']['id']
        if sid not in heads:
            raise ValueError(errors.get(sid, 'Source head is not independently registered'))
        return heads[sid]

    def rest(self, event):
        if not event['visible']:
            raise ValueError('Hidden source rest has no graphical anchor')
        frame = self.frame(event['beat'])
        staff = frame['staves'][event['staff']]
        simultaneous = self.rests_by_onset[event['staff'], event['beat']]
        if len(simultaneous) != 1:
            raise ValueError('Simultaneous anonymous rest anchors are inseparable')
        glyph = reference_glyphs().get('rest_'+str(event['note_type']))
        if glyph is None:
            raise ValueError('External font does not identify this rest anchor')
        gap = staff.gap
        center = (staff.lines[0]+staff.lines[-1])/2
        request = dict(glyph=glyph, gap=gap, origin_y=center, dxs=range(-3, 4))
        candidates = _joint_candidates(frame['pixels'], request,
            round(frame['playhead_x']), range(-round(4*gap), round(4*gap)+1), .79)
        if not candidates:
            raise ValueError('Actual rest contour lacks a bounded external-font match')
        best = candidates[0]
        if any(c['score'] >= best['score']-.05 and abs(c['y']-best['y']) > gap*.3 for c in candidates[1:]):
            raise ValueError('Actual rest contour has multiple possible staff lanes')
        b = glyph['bounds']
        width, height = max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250))
        baseline = best['y']-b[1]*gap/250
        family = {'whole', 'half'} if event['note_type'] in {'whole', 'half'} else {event['note_type']}
        rivals = [match_glyph(frame['pixels'], other, gap,
                    round(frame['playhead_x']), baseline, centered=True,
                    dxs=range(-3, 4), dys=range(-2, 3))
                  for name, other in reference_glyphs().items()
                  if name.startswith('rest_') and name.removeprefix('rest_') not in family]
        if best['score']-max(rivals, default=0.) < .03:
            raise ValueError('Actual rest anchor does not distinguish the expected external-font family')
        step = 1. if event['note_type'] in {'whole', 'half'} else .5
        offset = (baseline-center)/gap
        if abs(offset-round(offset/step)*step) > .13:
            raise ValueError('Actual rest anchor baseline is off the type-specific staff grid')
        if event['note_type'] in {'whole', 'half'}:
            block = frame['pixels'][best['y']:best['y']+height, best['x']:best['x']+width]
            ys, xs = np.nonzero(block)
            box = [best['x']+int(xs.min()), best['y']+int(ys.min()),
                   best['x']+int(xs.max())+1, best['y']+int(ys.max())+1]
            if rectangular_rest_orientation(box, staff)['observed_rest'] != event['note_type']:
                raise ValueError('Rectangular rest anchor orientation does not identify the source type')
        return dict(x=best['x']+width/2, y=baseline,
                    bbox=[best['x'], best['y'], best['x']+width, best['y']+height],
                    score=best['score'], gap=gap)

    def shift(self, own, target, staff):
        if own == target:
            return 0, dict(pixels=0, agreement=1., margin=1.)
        key = own, target, staff
        if key not in self.translations:
            a, b = self.frame(own), self.frame(target)
            sa, sb = a['staves'][staff], b['staves'][staff]
            if max(abs(x-y) for x, y in zip(sa.lines, sb.lines)) > 1:
                raise ValueError('Staff rails changed between endpoint witnesses')
            top, bottom = max(0, round(sa.lines[0]-5*sa.gap)), min(a['pixels'].shape[0], round(sa.bottom+5*sa.gap))
            # register_translation already ignores the left 20% of the width,
            # which contains the fixed 32 px system gutter and brace, so only
            # the mint timing overlay has to be removed here.
            self.translations[key] = register_translation(a['motion'][top:bottom], b['motion'][top:bottom], sa.gap)
        return self.translations[key]

    def anchors(self, events, target):
        result = []
        frame = self.frame(target)
        for event in events:
            head = self.head(event) if event['kind'] == 'note' else self.rest(event)
            shift, registration = self.shift(event['beat'], target, event['staff'])
            x = head['x']+shift
            if not head['gap'] < x < frame['pixels'].shape[1]-head['gap']:
                raise ValueError('Source endpoint is offscreen in common witness')
            result.append(dict(source_id=event['source']['id'], x=float(x), y=float(head['y']),
                bbox=[head['bbox'][0]+shift, *head['bbox'][1:2], head['bbox'][2]+shift, head['bbox'][3]],
                gap=float(head['gap']), head_match=round(head['score'], 4), registration=registration))
        return result
