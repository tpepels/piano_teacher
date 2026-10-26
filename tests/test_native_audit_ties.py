"""Source-owned ties in real Evans chords, measured only from framebuffer ink."""
from pathlib import Path
import json
import shutil

import numpy as np
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation import symbol_pixel_proof as proof
from piano_teacher.notation.proof import read_written_score

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ('pt5493b2bbe792941e6a48290d0b403145s0',
           'pt47d099f4d86542ab6538e88326caf578s0')
BEFORE = ROOT/'tests/fixtures/native_autumn_flag_tie_before'


def test_original_flag_collisions_remain_mismatches_under_the_current_oracle():
    """The admissible search bound cannot authorize the old obstructed curves."""
    from hashlib import sha256
    provenance = json.loads((BEFORE/'provenance.json').read_text())
    xml = (BEFORE/'score.musicxml').read_text()
    assert sha256(xml.encode()).hexdigest() == provenance['source_xml_sha256']
    manifest = json.loads((BEFORE/'capture-manifest.json').read_text())
    assert manifest['capture_config']['fingering_annotations'] is False
    for screenshot in manifest['screenshots']:
        assert sha256((BEFORE/screenshot['file']).read_bytes()).hexdigest() == screenshot['sha256']
    result = proof.verify_connector_pixels(xml, BEFORE, constructs=('tie',))
    rows = {row['source_ids'][0]: row for row in result['observations']}
    assert all(rows[identity]['status'] == 'mismatch' for identity in TARGETS)
    assert result['coverage']['verified'] == 6 and not result['complete']


@pytest.fixture(scope='module', params=((1536, 520), (1216, 455)),
                ids=('standard', 'compact'))
def autumn_ties(tmp_path_factory, request):
    from scripts.check_native_verovio_overlay import AuditCase, AUTUMN_FILE, fixture, run
    from test_native_fingering import _godot

    folder = tmp_path_factory.mktemp('autumn-audit-ties')
    case = AuditCase('autumn-tie-ownership', AUTUMN_FILE, 37, 40, 'both')
    data, engraving = fixture(case)
    data['sample_beats'] = [3.6, 4., 11.6, 12.]
    data['viewport_size'] = list(request.param)
    assert not data['source_errors']
    sources = {note['id']: note for note in data['model']['notes']}
    for source_id, pitch, beat in (('midi-t0-e360', 67, 3.6),
                                   ('midi-t0-e389', 65, 11.6)):
        source = sources[source_id]
        assert (source['midi_pitch'], source['velocity'], source['hand'],
                source['voice'], source['track'], source['channel']) == (
                    pitch, 80, 'right', 'midi-t0-c0', 0, 0)
        assert source['onset_beats'] == beat
        # Real MIDI release is intentionally distinct from the existing
        # quantized written eighth/half segmentation. Grading retains it.
        assert source['duration_beats'] == pytest.approx(1093/480)
    # Existing run() retains exact producer/source/renderer identities. The
    # editorial report is diagnostic; this test's truth is independent ink.
    run(folder, _godot()[-1], case, prepared=(data, engraving), strict=False)
    result = proof.verify_connector_pixels(data['xml'], folder, constructs=('tie',))
    (folder/'tie-proof.json').write_text(json.dumps(result, indent=2))
    return folder, data['xml'], result


def test_real_autumn_chord_ties_attach_without_borrowing_the_flag(autumn_ties):
    _, _, result = autumn_ties
    assert result['coverage']['expected'] == 8
    assert result['complete'], [(row['source_ids'], row['status'], row['evidence'].get('reason'))
                                for row in result['observations']]
    for identity in TARGETS:
        row = next(row for row in result['observations'] if row['source_ids'][0] == identity)
        assert row['status'] == 'verified'
        assert row['evidence']['pixel_runs']
        assert max(row['evidence']['endpoint_distances_spaces']) <= .9


@pytest.mark.parametrize('identity', TARGETS)
@pytest.mark.parametrize('damage', ('erased', 'detached', 'straight', 'broken'))
def test_real_autumn_damaged_tie_is_not_authorized_by_intact_heads(
        autumn_ties, tmp_path, identity, damage):
    folder, xml, baseline = autumn_ties
    assert baseline['complete'], baseline
    written = read_written_score(xml)
    pair = next(pair for pair in proof._connector_pairs(xml, written, ('tie',), 'both')
                if pair['notes'][0]['id'] == identity)
    for path in folder.glob('native-*.png'):
        shutil.copyfile(path, tmp_path/path.name)
    mutated = 0
    for path in tmp_path.glob('native-*.png'):
        with Image.open(path) as raw:
            original = raw.convert('RGB')
        heads = []
        for note in pair['notes']:
            source_path = next(p for p in folder.glob('native-*.png')
                               if abs(float(p.stem[7:])-float(note['beat'])) < 5e-6)
            with Image.open(source_path) as raw:
                source = raw.convert('RGB')
            own = proof._connector_head(source, written, note, source.width*.42)
            shift = proof._connector_shift(original, source)
            if own is None or shift is None:
                break
            head = proof._connector_head(original, written, note, own['x']+shift['shift'])
            if head is None:
                break
            heads.append(head)
        if len(heads) != 2:
            continue
        ink = proof._connector_curve(original, heads, 'tie')
        if ink['status'] != 'verified':
            continue
        mutated += 1
        image = original.copy()
        pen = ImageDraw.Draw(image)
        points = [(x, y) for y, start, end in ink['pixel_runs'] for x in range(start, end)]
        middle = (min(x for x, _ in points)+max(x for x, _ in points))//2
        for x, y in points:
            if damage != 'broken' or middle-2 <= x <= middle+2:
                pen.point((x, y), fill=original.getpixel((0, 0)))
        if damage == 'detached':
            for x, y in points:
                pen.point((x, y+round(2*heads[0]['gap'])), fill=(231, 240, 232))
        elif damage == 'straight':
            first, last = min(points), max(points)
            pen.line((*first, *last), fill=(231, 240, 232), width=2)
        # No endpoint pixels were replaced, and neither native assets nor
        # diagnostic coordinates are available to the independent verifier.
        for head in heads:
            box = tuple(head['bbox'])
            assert np.array_equal(np.asarray(original.crop(box)), np.asarray(image.crop(box)))
        image.save(path)
    assert mutated > 0
    result = proof.verify_connector_pixels(xml, tmp_path, constructs=('tie',))
    row = next(row for row in result['observations'] if row['source_ids'][0] == identity)
    assert row['status'] != 'verified', row
