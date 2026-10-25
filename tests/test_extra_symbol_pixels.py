"""Absence observations on actual GL captures, with foreign-ink mutations."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import weakref

import cairosvg
import numpy as np
from PIL import Image
import pytest

from test_extra_symbol_schedule import ROOT, godot_run


def verify(xml, folder, **kwargs):
    from piano_teacher.notation import extra_symbol_pixels as checker
    assert callable(getattr(checker, 'verify_extra_symbol_pixels', None))
    return checker.verify_extra_symbol_pixels(xml, folder, **kwargs)


@pytest.fixture(scope='module')
def captured(tmp_path_factory):
    if not os.environ.get('DISPLAY'):
        pytest.skip('Actual framebuffer captures require a display')
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    folder = tmp_path_factory.mktemp('extra-symbols-real')
    source = folder/'input.musicxml'
    source.write_text('''<score-partwise><part-list>
      <score-part id="RH"><part-name>Right Hand</part-name></score-part>
      <score-part id="LH"><part-name>Left Hand</part-name></score-part></part-list>
      <part id="RH"><measure number="1"><attributes><divisions>1</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>
      </attributes><note id="c"><pitch><step>C</step><octave>5</octave></pitch>
      <duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note id="e"><chord/><pitch><step>E</step><octave>5</octave></pitch>
      <duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note id="g"><chord/><pitch><step>G</step><octave>5</octave></pitch>
      <duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note id="r1"><rest/><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note id="r2"><rest/><duration>2</duration><voice>1</voice><type>half</type></note>
      </measure></part><part id="LH"><measure number="1"><attributes><divisions>1</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef>
      </attributes><note id="l0"><rest/><duration>2</duration><voice>1</voice><type>half</type></note>
      <note id="l2"><pitch><step>C</step><octave>3</octave></pitch><duration>2</duration>
      <voice>1</voice><type>half</type></note></measure></part></score-partwise>''')
    data, engraving = fixture(AuditCase('extra-symbols', str(source), 1, 1, 'right'))
    xml = data.pop('xml')
    data.update(phase3_full=True, full_symbol_inventory=True, sample_beats=[0., 1., 2., 4.])
    path = folder/'fixture.json'
    path.write_text(json.dumps(data))
    run = godot_run(ROOT/'tests/godot/native_verovio_overlay.gd', [path, folder],
                    graphical=True, timeout=90)
    assert run.returncode == 0, run.stdout+run.stderr
    for index, svg in enumerate(engraving.pages):
        (folder/f'verovio-{index}.svg').write_text(svg)
    (folder/'score.musicxml').write_text(xml)
    return xml, folder


def test_real_chord_silent_rest_and_inactive_ink_are_inventoried(captured, monkeypatch):
    from piano_teacher.notation import extra_symbol_pixels as checker
    original = checker._photo
    live = []
    def bounded_photo(path):
        photo = original(path)
        live.append(weakref.ref(photo['ink']))
        assert sum(ref() is not None for ref in live) <= 2
        return photo
    monkeypatch.setattr(checker, '_photo', bounded_photo)
    xml, folder = captured
    report = verify(xml, folder, hand='right')
    assert report['coverage']['frames'] > 20
    assert report['coverage']['initial_viewport'] and report['coverage']['terminal_viewport']
    viewport = [r for r in report['measured'] if r['region'] == 'viewport']
    assert viewport[0]['evidence']['scanned_areas'] == [[0, 0, 1536, 520]]
    assert viewport[-1]['evidence']['scanned_areas'] == [[0, 0, 1536, 520]]
    assert report['coverage']['motion_status'] == 'verified', report['coverage']
    assert report['coverage']['bound_heads'] == 4, report['coverage']
    assert report['coverage']['bound_rests'] == 3, report['coverage']
    assert not [r for r in report['measured'] if r['status'] == 'mismatch'], report
    assert any(r['status'] == 'verified' for r in report['measured'])
    # Recognition is not complete ink ownership. Brace/header antialiasing
    # and opaque intersections must stay unknown until actually explained.
    assert report['coverage']['unowned_pixels'] > 0
    assert not report['complete'] and report['scope'] == 'bounded sampled regions'
    assert report['limits'] and 'passed' not in report
    json.dumps(report)


def paste_glyph(folder, name, *, fixed=False, inactive=False, x=1190, y=65):
    from piano_teacher.notation.feature_pixels import _feature_glyphs
    glyph = _feature_glyphs()[name]
    b = glyph['bounds']
    svg = glyph['svg'].replace('fill="white"',
                              'fill="#596960"' if inactive else 'fill="#eaf4ed"')
    png = cairosvg.svg2png(bytestring=svg.encode(),
        output_width=round(b[2]*22/250), output_height=round(b[3]*22/250))
    files = sorted(folder.glob('native-*.png'))
    files = files if fixed else [files[len(files)//2]]
    for path in files:
        with Image.open(path) as raw:
            image = raw.convert('RGB')
        with Image.open(BytesIO(png)) as graphic:
            image.paste(graphic, (x, y), graphic)
        image.save(path)
    return files


@pytest.mark.parametrize(('name', 'fixed', 'inactive'), [
    ('head_black', False, False), ('head_half', True, False),
    ('augmentation_dot', True, False), ('rest_quarter', False, False),
    ('rest_half', True, True), ('flag_up_1', False, False)])
def test_foreign_families_elsewhere_or_fixed_screen_are_not_authorized(
        captured, tmp_path, name, fixed, inactive):
    xml, source = captured
    folder = tmp_path/'changed'
    shutil.copytree(source, folder)
    # Rectangular identity needs a real measured hanging/sitting phase;
    # a free-floating rectangle off the staff grid remains ambiguous ink.
    changed = paste_glyph(folder, name, fixed=fixed, inactive=inactive,
                          y=347 if name == 'rest_half' else 65)
    # Corrupt/forged renderer metadata cannot supply any ownership or RGB.
    (folder/'fixture.json').write_text('{"all_pixels_owned":true}')
    (folder/'native-overlay-report.json').write_text('{"rgb":"verified","density":0}')
    report = verify(xml, folder)
    mismatches = [r for r in report['measured'] if r['status'] == 'mismatch']
    assert mismatches, report
    assert any(r['frame'] in {p.name for p in changed} for r in mismatches)
    assert any(r['evidence'].get('unexpected') for r in mismatches)
    assert not report['complete']


def test_missing_uniform_frames_and_forged_density_cannot_prove_coverage(captured, tmp_path):
    xml, source = captured
    folder = tmp_path/'sparse'
    folder.mkdir()
    for clock in (0., 1., 2., 4.):
        shutil.copy(source/f'native-{clock:.5f}.png', folder)
    (folder/'native-overlay-report.json').write_text('{"density":1,"coverage":"verified"}')
    report = verify(xml, folder)
    assert report['coverage']['motion_status'] != 'verified'
    assert report['coverage']['clock_gaps']
    assert not report['complete']


def test_unknown_residual_is_not_swallowed_by_claim_box(captured, tmp_path):
    xml, source = captured
    folder = tmp_path/'residual'
    shutil.copytree(source, folder)
    path = sorted(folder.glob('native-*.png'))[10]
    with Image.open(path) as raw:
        image = raw.convert('RGB')
    pixels = np.asarray(image).copy()
    pixels[80:82, 1150:1152] = [234, 244, 237]
    Image.fromarray(pixels).save(path)
    report = verify(xml, folder)
    row = next(r for r in report['measured'] if r['frame'] == path.name and r['region'] == 'viewport')
    assert row['status'] != 'verified'
    assert row['evidence']['unowned_pixels'] >= 4
    assert not report['complete']


def test_source_pitch_does_not_authorize_a_second_head_at_another_x(captured, tmp_path):
    xml, source = captured
    folder = tmp_path/'same-pitch'
    shutil.copytree(source, folder)
    paste_glyph(folder, 'head_black', fixed=True, x=1180, y=164)
    report = verify(xml, folder)
    assert any(o['family'] == 'head' and o['bbox'][0] > 1100
               for row in report['measured'] for o in row['evidence'].get('unexpected', [])), report


def test_missing_endcaps_and_empty_folder_remain_unknown(captured, tmp_path):
    xml, _ = captured
    report = verify(xml, tmp_path)
    assert not report['complete']
    assert not report['coverage']['initial_viewport']
    assert not report['coverage']['terminal_viewport']
    assert report['coverage']['missing_source_clocks']
    with pytest.raises(ValueError):
        verify(xml, tmp_path, hand='feet')


def test_fft_search_is_the_original_dice_without_owning_box_background():
    from piano_teacher.notation.extra_symbol_pixels import _scores
    pixels = np.zeros((30, 40), bool)
    template = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
    pixels[8:11, 17:20] = template
    scores = _scores(pixels, template)
    assert scores.shape == (28, 38)
    assert scores[8, 17] == pytest.approx(1., abs=1e-6)
    pixels[8, 17] = True  # Extra pixel INSIDE the correct template's box.
    assert _scores(pixels, template)[8, 17] < 1.


def test_authentic_template_spectra_are_reused_and_byte_bounded(monkeypatch):
    from piano_teacher.notation import extra_symbol_pixels as checker
    assert callable(getattr(checker, '_spectrum', None)), 'Repeated template FFTs are not cached'
    checker._SPECTRA.clear()
    first = checker._spectrum('head_black', 22., (128, 256))
    assert checker._spectrum('head_black', 22., (128, 256)) is first
    monkeypatch.setattr(checker, 'TEMPLATE_FFT_CACHE_BYTES', first.nbytes*2)
    for name in ('head_half', 'head_whole', 'rest_quarter', 'flag_up_1'):
        checker._spectrum(name, 22., (128, 256))
        assert sum(s.nbytes for s in checker._SPECTRA.values()) <= first.nbytes*2
    checker._SPECTRA.clear()


def test_real_head_ledger_rectangles_cannot_be_invented_rests():
    from piano_teacher.notation.extra_symbol_pixels import _photo, _scan, _isolated_rectangle
    photo = _photo(ROOT/'tests/fixtures/native_ledger_chord/native-0.00000.png')
    candidates = [o for o in _scan(photo, [[600, 200, 730, 285]])
                  if o['name'] in ('rest_whole', 'rest_half')]
    assert candidates and max(o['score'] for o in candidates) > .90
    assert all(not _isolated_rectangle(photo, obj) for obj in candidates)


def test_search_crop_cannot_remove_a_threshold_passing_original_translation():
    from piano_teacher.notation import extra_symbol_pixels as checker
    assert callable(getattr(checker, '_search_crop', None))
    rng = np.random.default_rng(42)
    pixels = np.zeros((100, 160), bool)
    pixels[30:70, 40:120] = rng.random((40, 80)) > .8
    template = checker._template('head_black', 22.)
    pixels[40:40+template.shape[0], 60:60+template.shape[1]] |= template
    minimum = .79
    crop = checker._search_crop([pixels], template, minimum)
    assert crop is not None
    left, top, right, bottom = crop
    original = checker._scores(pixels, template)
    limited = checker._scores(pixels[top:bottom, left:right], template)
    for y, x in np.argwhere(original >= minimum):
        assert top <= y <= bottom-template.shape[0]
        assert left <= x <= right-template.shape[1]
        assert limited[y-top, x-left] == pytest.approx(original[y, x], abs=1e-7)
    assert checker._search_crop([np.zeros_like(pixels)], template, minimum) is None


def test_packed_rail_mode_is_identical_to_actual_rgb_tuple_mode():
    from piano_teacher.notation import extra_symbol_pixels as checker
    assert callable(getattr(checker, '_modal_rule_row', None))
    with Image.open(ROOT/'tests/fixtures/native_ledger_chord/native-0.00000.png') as image:
        rgb = np.asarray(image.convert('RGB'))
    for y in (141, 142, 143, 144, 145, 314, 315, 336, 337, 358, 402):
        colors, counts = np.unique(rgb[y], axis=0, return_counts=True)
        expected = np.all(rgb[y] == colors[np.argmax(counts)], axis=1)
        if counts.max() <= rgb.shape[1]*.4:
            expected[:] = False
        assert np.array_equal(checker._modal_rule_row(rgb[y]), expected)


def test_erasure_can_create_an_unexpected_family_without_adding_foreground():
    from piano_teacher.notation.extra_symbol_pixels import _areas, _template
    previous = np.zeros((520, 1536), bool)
    current = previous.copy()
    template = _template('flag_up_1', 22.)
    h, w = template.shape
    previous[60:70+h, 1170:1240+w] = True
    current[65:65+h, 1190:1190+w] = template
    photo = lambda mask: dict(shape=mask.shape, layers=[mask, mask], camera=645.)
    areas = _areas(photo(current), photo(previous), -10, False)
    assert any(a[0] <= 1190 and a[2] >= 1190+w for a in areas), areas
    # Exact stationary ink was already scanned in the initial whole viewport;
    # it needs contour rechecks, not all-family FFTs on every later clock.
    areas = _areas(photo(current), photo(current), -10, False)
    assert areas == [[581, 0, 709, 520]], areas


def test_real_playhead_overlap_is_ambiguous_without_exempting_detached_heads():
    from piano_teacher.notation.extra_symbol_pixels import _playhead_occludes_candidate
    photo = {'occlusion': np.zeros((60, 140), dtype=bool)}
    photo['occlusion'][20:50, 62:64] = True
    under_playhead = {'bbox':[60,24,81,44]}
    detached = {'bbox':[98,24,119,44]}
    assert _playhead_occludes_candidate(photo, under_playhead)
    assert not _playhead_occludes_candidate(photo, detached)
