"""Bounded, actual-native Peace Piece register/preparation regressions.

Expected source facts come from raw MIDI; expected gap is the literal four
quarter beats required for this pickup. Pixel geometry comes only from PNG
staff rails and independent Verovio font outlines, never native diagnostics.
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import mido
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import pytest

from continuous_repeat_pixel_helpers import DENSITY, PLAYHEAD, _glyph_hits, notation_ink
from piano_teacher.notation.reference_font import feature_glyphs
from piano_teacher.notation.feature_pixels import _reference_stem_extension
from piano_teacher.notation.phase3_pixels import verify_translation_sequence
from piano_teacher.notation.pixel_proof import detect_staff_lines, expected_y
from piano_teacher.notation.proof import read_written_score
from piano_teacher.notation.symbol_pixel_proof import _match_glyph
from piano_teacher.notation.pixel_ink import rasterize_outline, bright
from test_repeat_recovery_context_pixels import _boundaries

ROOT = Path(__file__).resolve().parents[1]
MIDI = ROOT / 'midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
STEPS = (2, 3, 7, 9, 10)
GAP = 4.0  # Independently specified; canonical opening 1/8 remains .5 beats.


@lru_cache(maxsize=1)
def _raw_notes():
    midi = mido.MidiFile(MIDI)
    notes = {}
    for track_index, track in enumerate(midi.tracks):
        tick, pending = 0, {}
        for ordinal, message in enumerate(track):
            tick += message.time
            if message.type == 'note_on' and message.velocity:
                sid = f'midi-t{track_index}-e{ordinal}'
                pending.setdefault((message.channel, message.note), []).append((sid, tick, message.velocity))
            elif message.type == 'note_off' or message.type == 'note_on' and not message.velocity:
                active = pending.get((message.channel, message.note), [])
                if not active:
                    continue  # Captured MIDI can begin with an already-held key's release.
                sid, start, velocity = active.pop(0)
                notes[sid] = dict(pitch=message.note, start=start / midi.ticks_per_beat,
                                  end=tick / midi.ticks_per_beat, track=track_index,
                                  channel=message.channel, velocity=velocity,
                                  hand='right' if track_index == 0 else 'left')
    first = [note for note in notes.values() if note['track'] == 0 and note['start'] == .5]
    assert {note['pitch'] for note in first} == {36, 60, 64, 67}
    assert all(note['end'] == 2.5 and note['channel'] == 1 for note in first)
    return notes


def _assert_source(data):
    raw, expected = _raw_notes(), data['peace_expected']
    start, end = expected['source_start'], expected['source_end']
    for note in data['model']['notes']:
        original = raw[note['id']]
        assert (note['midi_pitch'], note['hand'], note['track'], note['channel'], note['voice']) == (
            original['pitch'], original['hand'], original['track'], original['channel'],
            f"midi-t{original['track']}-c{original['channel']}")
        assert note['onset_beats'] == pytest.approx(original['start'] - start)
        assert note['duration_beats'] == pytest.approx(min(original['end'], end) - original['start'])
    if expected['step'] in (3, 7, 10):
        wanted = {sid for sid, note in raw.items() if start <= note['start'] < end
                  and (data['hand'] == 'both' or note['hand'] == data['hand'])}
        assert {note['id'] for note in data['model']['notes']} == wanted
    for beat, pitch in zip(expected['onsets'], (36, 43)):
        remote = [event for event in data['model']['notation_events']
                  if event['kind'] == 'note' and event['beat'] == beat and event['midi_pitch'] == pitch
                  and raw[event['source_id']]['hand'] == 'right']
        assert len(remote) == 1
        event = remote[0]
        assert (event['staff'], event['hand'], event['note_type']) == ('left', 'right', 'half')


@pytest.fixture(scope='module')
def peace_captures(tmp_path_factory):
    from piano_teacher.fingering import FingeringService, project_model
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.learning import LearningPlan
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from test_native_fingering import _godot, _run_godot

    folder_root = tmp_path_factory.mktemp('peace-pixels')
    piece, _ = import_piece(MIDI)
    service = FingeringService(tmp_path_factory.mktemp('peace-whole-piece-plan'))
    fingers = service.prepare(piece, sha256(MIDI.read_bytes()).hexdigest())
    assert fingers.status in ('ready', 'partial'), fingers.error
    captures = {}
    failures = {}

    def capture(step):
        if step in captures:
            return captures[step]
        if step in failures:
            pytest.fail(failures[step])
        retained = os.environ.get('PEACE_PIXEL_CAPTURE_ROOT')
        if retained:
            folder = Path(retained) / f'step-{step}'
            result = folder, json.loads((folder / 'fixture.json').read_text()), json.loads((folder / 'repeat-report.json').read_text())
            captures[step] = result
            return result
        plan = LearningPlan(piece)
        plan.select_step(step)
        phrase = plan.active_phrase
        case = AuditCase(f'peace-step-{step}', str(MIDI), phrase.first_bar, phrase.last_bar, plan.hand)
        data, _ = fixture(case, piece=piece, phrase=phrase)
        data['model'] = project_model(data['model'], fingers, source_musicxml=piece.source_musicxml)
        first = step in (2, 3, 7)
        duration, onsets = (4.5, [.5, 2.5]) if first else (8., [0., 2.])
        assert data['model']['duration_beats'] == duration
        data['peace_expected'] = dict(step=step, duration=duration, onsets=onsets,
                                      source_start=0. if first else 4.5, source_end=4.5 if first else 12.5)
        _assert_source(data)
        data['gap_beats'] = GAP
        data['state'] = {'practice_timeline': data['model']['practice_timeline']}
        data['repeat_frames'] = [dict(name='opening', clock=-.5),
            dict(name='source-c2', clock=onsets[0]), dict(name='source-g2', clock=onsets[1])]
        if step == 7:
            data['repeat_frames'].append(dict(name='selected-right', clock=.5, state={'hand': 'right'}))
            data['repeat_frames'].append(dict(name='selected-right-g2', clock=2.5, state={'hand': 'right'}))
        data['repeat_frames'] += [dict(name=name, clock=clock) for name, clock in (
            ('rest-before', duration + 2 - .125), ('rest', duration + 2),
            ('rest-after', duration + 2 + .125), ('repeat-c2', duration + GAP + onsets[0]),
            ('repeat-g2', duration + GAP + onsets[1]))]
        folder = folder_root / f'step-{step}'
        folder.mkdir()
        payload = folder / 'fixture.json'
        payload.write_text(json.dumps(data))
        (folder / 'score.musicxml').write_text(data['xml'])
        result = _run_godot([*_godot(), '--path', str(ROOT / 'godot'), '--rendering-method',
            'gl_compatibility', '--audio-driver', 'Dummy', '--script',
            str(ROOT / 'tests/godot/continuous_repeat_capture.gd'), '--', str(payload), str(folder)], timeout=90)
        (folder / 'godot.log').write_text(result.stdout + result.stderr)
        if result.returncode != 0 or 'SCRIPT ERROR' in result.stdout + result.stderr:
            failures[step] = f'Native capture failed; see {folder / "godot.log"}'
            pytest.fail(failures[step])
        captures[step] = folder, data, json.loads((folder / 'repeat-report.json').read_text())
        return captures[step]
    return capture


@pytest.fixture(params=STEPS, ids=[f'step-{step}' for step in STEPS])
def peace_capture(request, peace_captures):
    return peace_captures(request.param)


def _image(folder, frame):
    with Image.open(folder / frame['base']) as raw:
        image = raw.convert('RGB')
    assert image.size == (1536, 520)
    return image


def measure_bass_half(image, pitch, x, *, tolerance=None):
    """Locate a hollow RH half head, not the resident filled LH quarter."""
    staff = detect_staff_lines(image)['left']
    y = expected_y(staff, ('C', 0, 2) if pitch == 36 else ('G', 0, 2), ('F', 4, 0))
    radius = round(1.8 * staff.gap) if tolerance is None else tolerance
    pixels, glyphs = bright(image), feature_glyphs()
    score, actual_x = max((_match_glyph(pixels, glyphs['head_half'], staff.gap, col, y,
                                       centered=True, dxs=[0], dys=range(-2, 3)), col)
                          for col in range(round(x) - radius, round(x) + radius + 1))
    assert score >= .80, f'RH {pitch}: missing authentic bass-staff half head ({score:.3f})'
    filled = _match_glyph(pixels, glyphs['head_black'], staff.gap, actual_x, y,
                          centered=True, dxs=range(-2, 3), dys=range(-2, 3))
    assert score - filled >= .05, f'RH half head was confused with resident LH quarter ({score:.3f}/{filled:.3f})'
    return dict(x=actual_x, y=y, score=score, gap=staff.gap)


@lru_cache(maxsize=1)
def _reference_ledger_span():
    """Engrave standalone C4s to distinguish a ledger rule from a broad head."""
    import verovio
    spans=[]
    for kind,duration in (('quarter',4),('half',8)):
        xml=f'''<score-partwise version="4.0"><part-list><score-part id="P1">
        <part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1">
        <attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
        <clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave>
        </pitch><duration>{duration}</duration><type>{kind}</type></note></measure></part></score-partwise>'''
        toolkit=verovio.toolkit()
        toolkit.setOptions({'breaks':'none','header':'none','footer':'none','font':'Leipzig'})
        assert toolkit.loadData(xml)
        root=ET.fromstring(toolkit.renderToSVG(1))
        staff=next(node for node in root.iter() if node.get('class')=='staff')
        rails=[float(re.findall(r'-?[0-9.]+',node.get('d'))[1])
               for node in staff if node.tag.endswith('path')][:5]
        gap=(max(rails)-min(rails))/4
        for group in staff.iter():
            if 'ledgerLines' not in group.get('class','').split():
                continue
            for path in group:
                x0,y0,x1,y1=map(float,re.findall(r'-?[0-9.]+',path.get('d')))
                assert y0==y1
                spans.append(abs(x1-x0)/gap)
    assert len(spans)==2
    return min(spans)


def _no_bridge_ladder(image, x, data, clock):
    staves = detect_staff_lines(image)
    top, bottom = round(staves['right'].bottom) + 4, round(staves['left'].lines[0]) - 4
    ink=bright(image)
    pixels = ink[top:bottom, round(x - 2 * staves['left'].gap):round(x + 2 * staves['left'].gap)]
    assert pixels.mean(axis=0).max() < .90, 'Spanning stem crosses the grand-staff bridge'
    # Compact bass chords and a treble C4 can require genuine ledger rows in
    # this corridor. Read their exact levels from source pitch/clef. A rule
    # must be a continuous run wider than a head, with its minimum span taken
    # from independently engraved Verovio rules, not a count of white pixels.
    written=read_written_score(data['xml'])
    allowed_rows=[]
    for note in written.symbols:
        if note['kind']!='note' or abs(float(note['beat'])-clock)>1e-7:
            continue
        staff=staves[note['staff']]
        clef=next((sign,line,octave) for at,hand,sign,line,octave in reversed(written.clefs)
                  if hand==note['staff'] and at<=note['index'])
        y=expected_y(staff,tuple(note['spelling']),clef)
        step=round(2*(staff.bottom-y)/staff.gap)
        levels=range(-2,step-1,-2) if step<0 else range(10,step+1,2)
        allowed_rows.extend(staff.bottom-level*staff.gap/2 for level in levels
                            if top-2<=staff.bottom-level*staff.gap/2<=bottom+2)
    minimum=_reference_ledger_span()*min(staff.gap for staff in staves.values())-2
    rows=[]
    for index,row in enumerate(pixels):
        edges=np.flatnonzero(np.diff(np.r_[False,row,False].astype(int)))
        if any(length>=minimum for length in edges[1::2]-edges[::2]):
            rows.append(top+index)
    assert all(any(abs(row-expected)<=2 for expected in allowed_rows) for row in rows), \
        f'Ledger ladder has rows unsupported by the source: {rows} versus {allowed_rows}'


def _complete_half_stem(image, head):
    """Measure the attached shaft and its visible endpoint, not atlas bounds."""
    ink = bright(image)
    gap, x, y = head['gap'], head['x'], head['y']
    half_width = (feature_glyphs()['head_half']['bounds'][2] - 24) * gap / 500
    candidates = []
    for direction, sign, edge in [('up', -1, x + half_width), ('down', 1, x - half_width)]:
        rows = sorted((round(y + sign * gap * .4), round(y + sign * gap * 2)))
        for col in range(round(edge) - 3, round(edge) + 4):
            coverage = float(ink[max(0, rows[0]):min(image.height, rows[1]), col].mean())
            candidates.append((coverage, direction, sign, col))
    coverage, direction, sign, col = max(candidates)
    assert coverage >= .80, 'RH bass half note has no complete attached stem'
    tip, missing = round(y), 0
    for row in range(round(y + sign * gap * .4), image.height if sign == 1 else -1, sign):
        if ink[row, col]:
            tip, missing = row, 0
        else:
            missing += 1
            if missing > 2:
                break
    assert 2 < tip < image.height - 3, f'RH bass half stem clipped at framebuffer edge (tip row {tip})'
    extension = (tip - y) * sign
    required = _reference_stem_extension('half', (0,), direction) * gap
    assert extension >= required - 2, f'RH bass half stem is truncated ({extension:.2f}px versus {required:.2f}px reference)'
    return dict(direction=direction,sign=sign,column=col,tip=tip)


def verify_peace_register_pixels(folder, data, report):
    _assert_source(data)
    frames = {frame['name']: frame for frame in report['frames']}
    x = 1536 * PLAYHEAD
    measured = {}
    for name, pitch in [('source-c2', 36), ('source-g2', 43)]:
        image = _image(folder, frames[name])
        measured[pitch] = measure_bass_half(image, pitch, x)
        _complete_half_stem(image, measured[pitch])
        _no_bridge_ladder(image,x,data,frames[name]['clock'])
        if data['hand']=='both':
            # The same geometry must remain legible with only RH selected.
            # A real hand-selection control proves that the bass half remains
            # active and the required LH source chord stays independently dim.
            selected='selected-right' if pitch==36 else 'selected-right-g2'
            controlled=_image(folder,frames[selected])
            again=measure_bass_half(controlled,pitch,measured[pitch]['x'],tolerance=2)
            _complete_half_stem(controlled,again)
            _no_bridge_ladder(controlled,x,data,frames[selected]['clock'])
            if pitch==43:
                staff=detect_staff_lines(controlled)['left']
                rgb=np.asarray(controlled).astype(int)
                dim=(rgb[:,:,0]>int(rgb[0,-1,0])+25)&(rgb[:,:,0]<120)
                y=expected_y(staff,('G',0,3),('F',4,0))
                score=_match_glyph(dim,feature_glyphs()['head_black'],staff.gap,x,y,
                    centered=True,dxs=range(-round(staff.gap*1.8),round(staff.gap*1.8)+1),dys=range(-2,3))
                assert score>=.80,'Required LH chord disappeared in the hand-selection control'
    if 'selected-right' in frames:
        image = _image(folder, frames['selected-right'])
        remote = measure_bass_half(image, 36, x)
        _complete_half_stem(image, remote)
        staff = detect_staff_lines(image)['left']
        rgb = np.asarray(image).astype(int)
        dim = (rgb[:, :, 0] > int(rgb[0, -1, 0]) + 25) & (rgb[:, :, 0] < 120)
        score = _match_glyph(dim, feature_glyphs()['head_black'], staff.gap, x, remote['y'],
                             centered=True, dxs=range(-round(staff.gap * 1.8), round(staff.gap * 1.8) + 1), dys=range(-2, 3))
        assert score >= .80, f'Resident LH quarter is not independently dim and filled ({score:.3f})'
    expected = data['peace_expected']
    last = frames['repeat-g2']
    for pass_index in ((1, 2) if expected['duration'] == 4.5 else (1,)):
        for onset, pitch in zip(expected['onsets'], (36, 43)):
            target = x + (pass_index * (expected['duration'] + GAP) + onset - last['clock']) * DENSITY
            target += measured[pitch]['x'] - x
            measure_bass_half(_image(folder, last), pitch, target, tolerance=2)
    if expected['duration']==4.5 and data['hand']=='right':
        clicks=report['clicks']
        assert len(clicks)==2 and all(click['opened'] for click in clicks)
        assert {click['pass_index'] for click in clicks}=={1,2}
        assert {click['expected_source_id'] for click in clicks}=={'midi-t0-e29'}
        assert report['interactions']==[{'source_id':'midi-t0-e29','finger':5}]*2
    return measured


def _rest_box(staff, x):
    bounds = feature_glyphs()['rest_whole']['bounds']
    scale = staff.gap / 250
    left, top = round(x - bounds[2] * scale / 2) - 3, round(staff.lines[1] + bounds[1] * scale) - 3
    return left, top, left + round(bounds[2] * scale) + 6, top + round(bounds[3] * scale) + 6


def _meter_mask(image, staff, meter, interval, origins, *, scale=1., dim=False):
    """Authentic, independently registered digits; only their silhouettes count."""
    from dataclasses import replace
    rail = replace(staff, gap=staff.gap * scale)
    pixels = notation_ink(image) & (np.asarray(image)[:, :, 0] < 120) if dim else bright(image)
    allowed = np.zeros(pixels.shape, dtype=np.uint8)
    columns = []
    for number, y in zip(meter, origins):
        glyph = feature_glyphs()[f'time_{number}']
        hits = _glyph_hits(pixels, glyph, rail, interval, y)
        assert hits, f'Missing authentic {meter[0]}/{meter[1]} source meter digit {number}'
        seed = max(hits, key=lambda hit: hit['score'])['x']
        score, x, actual_y = max((_match_glyph(pixels, glyph, rail.gap, col, y + dy,
                                              centered=True, dxs=[0], dys=[0]), col, y + dy)
                                 for col in range(seed - 2, seed + 3)
                                 for dy in range(-round(rail.gap / 4), round(rail.gap / 4) + 1))
        assert score >= .80
        bounds = glyph['bounds']
        width, height = round(bounds[2] * rail.gap / 250), round(bounds[3] * rail.gap / 250)
        left, top = round(x - bounds[2] * rail.gap / 500), round(actual_y + bounds[1] * rail.gap / 250)
        allowed[top:top + height, left:left + width] |= rasterize_outline(glyph['svg'], width, height).astype(np.uint8) * 255
        columns.append(x)
    assert abs(columns[0] - columns[1]) <= 2, 'Meter digits do not share an authentic signature column'
    # One antialiasing pixel around a matched external contour is not a
    # discarded rectangle; unrelated heads, clefs and rules remain blocking.
    return np.asarray(Image.fromarray(allowed).filter(ImageFilter.MaxFilter(3))) > 0


def _source_meters(folder, data, frames):
    image = _image(folder, frames['opening'])
    staves = detect_staff_lines(image)
    source_x = image.width * PLAYHEAD + .5 * DENSITY
    first = data['peace_expected']['duration'] == 4.5
    for hand, staff in staves.items():
        middle = (staff.lines[0] + staff.bottom) / 2
        _meter_mask(image, staff, (1, 8) if first else (4, 4),
                    (source_x - 19 * staff.gap, source_x - staff.gap),
                    (middle - staff.gap, middle + staff.gap), dim=data['hand'] == 'right' and hand == 'left')
    if first:
        staff = staves['right']
        middle = (staff.lines[0] + staff.bottom) / 2
        source_change_x = source_x + .5 * DENSITY
        _meter_mask(image, staff, (4, 4), (source_change_x - 4 * staff.gap, source_change_x + staff.gap),
                    (middle - 4.5 * staff.gap, middle - 3.05 * staff.gap), scale=.72)


def verify_peace_preparation_pixels(folder, data, report):
    expected = data['peace_expected']
    duration = expected['duration']
    frames = {frame['name']: frame for frame in report['frames']}
    assert data['gap_beats'] == GAP
    _source_meters(folder, data, frames)
    for tag, delta in [('rest-before', -.125), ('rest', 0.), ('rest-after', .125)]:
        frame = frames[tag]
        assert frame['clock'] == duration + 2 + delta
        image = _image(folder, frame)
        staves, (left, right) = _boundaries(image, {'start': duration, 'end': duration + GAP}, frame['clock'])
        center = (left + right) / 2
        ink = notation_ink(image)
        for hand, staff in staves.items():
            if duration == 4.5:
                middle = (staff.lines[0] + staff.bottom) / 2
                mask = _meter_mask(image, staff, (1, 8), (right - 8 * staff.gap, right - staff.gap * .6),
                                   (middle - staff.gap, middle + staff.gap),
                                   dim=data['hand'] == 'right' and hand == 'left')
                ink[mask] = False
            score = _match_glyph(ink, feature_glyphs()['rest_whole'], staff.gap, center,
                                 staff.lines[1], centered=True, dxs=range(-2, 3), dys=range(-2, 3))
            assert score >= .80, f'{hand}: missing centered four-beat whole rest ({score:.3f})'
            x0, y0, x1, y1 = _rest_box(staff, center)
            ink[y0:y1, x0:x1] = False
            for rail in staff.lines:
                ink[round(rail) - 1:round(rail) + 2] = False
        assert int(ink[:, round(left) + 4:round(right) - 3].sum()) <= 8, 'Extra ink inside full preparation measure'
    motion = verify_translation_sequence(*[_image(folder, frames[name])
                                           for name in ('rest-before', 'rest', 'rest-after')])
    assert motion['passed'] and motion['pixel_steps'] == [12, 12], motion
    # Voice-column displacement is measured in the original PNG; it cannot
    # authorize a horizontal shift of the incoming copy.
    source = measure_bass_half(_image(folder, frames['source-c2']), 36, 1536 * PLAYHEAD)
    incoming = frames['repeat-c2']
    assert incoming['clock'] == duration + GAP + expected['onsets'][0]
    measure_bass_half(_image(folder, incoming), 36, source['x'], tolerance=2)
    return motion


def test_real_peace_source_registers_and_performing_hand_pixels(peace_capture):
    verify_peace_register_pixels(*peace_capture)


def test_real_peace_full_four_beat_preparation_and_repeat_arrival(peace_capture):
    verify_peace_preparation_pixels(*peace_capture)


def _copied(capture, folder):
    original, data, report = capture
    for frame in report['frames']:
        for key in ('base', 'file'):
            shutil.copy2(original / frame[key], folder / frame[key])
    return folder, data, report


@pytest.mark.parametrize('corruption', ['erase-half-head', 'truncate-stem', 'spanning-stem', 'ledger-ladder'])
def test_actual_register_pixel_corruptions_fail(peace_captures, tmp_path, corruption):
    capture = _copied(peace_captures(3), tmp_path)
    folder, data, report = capture
    verify_peace_register_pixels(*capture)
    frame = next(frame for frame in report['frames'] if frame['name'] == 'source-c2')
    image = _image(folder, frame)
    measured = measure_bass_half(image, 36, image.width * PLAYHEAD)
    staves = detect_staff_lines(image)
    pen = ImageDraw.Draw(image)
    if corruption == 'erase-half-head':
        x, y, gap = measured['x'], measured['y'], measured['gap']
        pixels = np.asarray(image).copy()
        x0, x1, y0, y1 = round(x - gap), round(x + gap), round(y - gap / 2), round(y + gap / 2)
        pixels[y0:y1, x0:x1] = pixels[y0:y1, x0 - 10:x0 - 9]
        image = Image.fromarray(pixels)
    elif corruption=='truncate-stem':
        stem=_complete_half_stem(image,measured)
        y0,y1=sorted((stem['tip']-stem['sign']*2,round(stem['tip']-stem['sign']*measured['gap'])))
        pixels=np.asarray(image).copy()
        for row in range(y0,y1+1):
            pixels[row,stem['column']-3:stem['column']+4]=np.median(pixels[row],axis=0).astype(np.uint8)
        image=Image.fromarray(pixels)
    elif corruption == 'spanning-stem':
        pen.line((measured['x'], staves['right'].bottom, measured['x'], staves['left'].bottom), fill=(234, 244, 237), width=2)
    else:
        for y in np.linspace(staves['right'].bottom + 10, staves['left'].lines[0] - 10, 4):
            pen.line((measured['x'] - 22, y, measured['x'] + 22, y), fill=(234, 244, 237), width=2)
    image.save(folder / frame['base'])
    with pytest.raises(AssertionError, match='half head|stem is truncated|complete attached stem|Spanning stem|Ledger ladder'):
        verify_peace_register_pixels(*capture)


@pytest.mark.parametrize('corruption', ['shortened-rest', 'lengthened-rest', 'shifted-incoming'])
def test_actual_preparation_pixel_corruptions_fail(peace_captures, tmp_path, corruption):
    capture = _copied(peace_captures(3), tmp_path)
    folder, data, report = capture
    verify_peace_preparation_pixels(*capture)
    name = 'rest' if corruption in ('shortened-rest','lengthened-rest') else 'repeat-c2'
    frame = next(frame for frame in report['frames'] if frame['name'] == name)
    image = _image(folder, frame)
    pixels = np.asarray(image).copy()
    if corruption in ('shortened-rest','lengthened-rest'):
        _, (left, right) = _boundaries(image, {'start': 4.5, 'end': 8.5}, frame['clock'])
        col = round(right) - 3
        if corruption=='shortened-rest':
            pixels[:, col-96:-96] = pixels[:, col:]
        else:
            pixels[:, col:] = pixels[:, col - 96:pixels.shape[1] - 96]
    else:
        col = round(image.width * PLAYHEAD) - 40
        pixels[:, col + 24:] = pixels[:, col:-24]
        pixels[:, col:col + 24] = pixels[:, col - 20:col - 19]
    Image.fromarray(pixels).save(folder / frame['base'])
    with pytest.raises(AssertionError, match='boundary|whole rest|half head|preparation'):
        verify_peace_preparation_pixels(*capture)
