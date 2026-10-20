from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

from piano_teacher.importing.musicxml import load_musicxml
from piano_teacher.notation.lesson import build_lesson_score
from piano_teacher.notation.model import build_score_model
from piano_teacher.music import Phrase

FIXTURE = Path(__file__).parent / 'fixtures/musical_fidelity/xml_expressions.musicxml'


def lesson(piece, notes=None, start=0, end=8):
    phrase = Phrase(1, int(start/4)+1, int(end/4), start, end,
                    tuple(n for n in (piece.notes if notes is None else notes)
                          if start <= n.start < end))
    return build_lesson_score(phrase, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, clef_changes=piece.clef_changes,
        source_notation=piece.source_notation)


def test_supported_annotations_survive_the_actual_lesson_and_semantic_model():
    piece = load_musicxml(FIXTURE, bpm=80)
    score = lesson(piece)
    root = ET.fromstring(score.musicxml)
    for path in ('.//dynamics/p', './/pedal[@type="start"]', './/pedal[@type="stop"]',
                 './/articulations/staccato', './/ornaments/turn',
                 './/slur[@type="start"]', './/slur[@type="stop"]',
                 './/wedge[@type="crescendo"]', './/wedge[@type="stop"]'):
        assert root.find(path) is not None, path
    model = build_score_model(score, boundaries=piece.bar_boundaries)
    assert len(model['notes']) == len(piece.notes)
    assert {'dynamics', 'pedal', 'wedge', 'articulations', 'ornaments'} <= {
        a['kind'] for a in model['annotations']}
    assert all(r['status'] == 'preserved' for r in model['projection_report'])


def test_removed_slur_endpoint_is_not_replaced_and_every_omission_is_explained():
    piece = load_musicxml(FIXTURE, bpm=80)
    score = lesson(piece, tuple(n for n in piece.notes if n.pitch != 76))
    root = ET.fromstring(score.musicxml)
    assert not root.findall('.//slur')
    assert root.find('.//articulations/staccato') is not None
    omitted = [r for r in score.projection_report if r['status'] == 'omitted']
    assert omitted and all(r['reason'] for r in omitted)
    assert any(r['reason'] == 'endpoint_removed' for r in omitted)
    assert all(n['pitch'] != 76 for n in score.note_bindings.values())


def test_single_hand_and_excerpt_inherit_relevant_state_without_other_hand_notes():
    piece = load_musicxml(FIXTURE, bpm=80)
    right = tuple(n for n in piece.notes if n.hand == 'right')
    score = lesson(piece, right, start=4)
    root = ET.fromstring(score.musicxml)
    assert root.find('.//dynamics/p') is not None
    assert root.find('.//pedal[@type="start"]') is not None
    assert any(r['status'] == 'inherited' for r in score.projection_report)
    assert {b['hand'] for b in score.note_bindings.values()} == {'right'}
    left_score = lesson(piece, tuple(n for n in piece.notes if n.hand == 'left'))
    assert ET.fromstring(left_score.musicxml).find('.//articulations/staccato') is None


def test_source_index_is_immutable_and_survives_the_real_disk_cache(tmp_path):
    from hashlib import sha256
    from dataclasses import FrozenInstanceError
    import pytest
    from piano_teacher.preprocessing_cache import PreprocessingCache
    cache = PreprocessingCache(tmp_path)
    fingerprint = sha256(FIXTURE.read_bytes()).hexdigest()
    piece, _ = cache.load_import(FIXTURE, fingerprint,
        importer=lambda path: (load_musicxml(path, bpm=80), None))
    reopened, _ = cache.load_import(FIXTURE, fingerprint,
        importer=lambda _: (_ for _ in ()).throw(AssertionError('reimport')))
    assert reopened.source_notation == piece.source_notation
    with pytest.raises(FrozenInstanceError):
        reopened.source_notation.events = ()
    assert lesson(reopened).musicxml == lesson(piece).musicxml


def test_removed_interior_note_becomes_a_source_rhythm_rest_inside_intact_span():
    piece=load_musicxml(FIXTURE,bpm=80)
    score=lesson(piece,tuple(n for n in piece.notes if n.pitch != 74))
    model=build_score_model(score,boundaries=piece.bar_boundaries)
    slur=next(g for g in model['groups'] if g['kind']=='slur')
    events={e['id']:e for e in model['notation_events']}
    assert len(slur['event_ids'])==3
    middle=events[slur['event_ids'][1]]
    assert middle['kind']=='rest' and middle['duration_beats']==1
    assert middle['note_type']=='quarter'
