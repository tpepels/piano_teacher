"""Independent attack/release accounting keeps same-pitch pairing ambiguous."""
from copy import deepcopy

import mido

from piano_teacher.notation.semantic_contract import verify_midi_performance, source_inventory
from scripts.aggregate_phase3_corpus import _account_inventory


def overlap(tmp_path):
    path = tmp_path / 'overlap.mid'
    midi = mido.MidiFile(ticks_per_beat=120)
    midi.tracks.append(mido.MidiTrack([
        mido.MetaMessage('track_name', name='Right Hand'),
        mido.Message('note_on', note=64, velocity=71, time=0),
        mido.Message('note_on', note=64, velocity=72, time=120),
        mido.Message('note_off', note=64, time=240),
        mido.Message('note_off', note=64, time=120),
    ]))
    midi.save(path)
    notes = [dict(id=f'midi-t0-e{i}', onset_beats=start, duration_beats=3,
                  midi_pitch=64, velocity=velocity, track=0, channel=0,
                  voice='midi-t0-c0', hand='right')
             for i, start, velocity in [(1,0,71),(2,1,72)]]
    return path, dict(notes=notes, notation_events=[], active_hand='both',
                      active_note_ids=[n['id'] for n in notes])


def test_all_overlapping_attacks_and_releases_are_compared(tmp_path):
    path, model = overlap(tmp_path)
    report = verify_midi_performance(path, model)
    assert report['passed'], report['discrepancies']
    for construct in ('midi_performance', 'midi_release'):
        rows = [r for r in report['elements'] if r['construct']==construct]
        assert len(rows)==2 and all(r['status']=='verified' for r in rows)
    pairing = [r for r in report['elements'] if r['construct']=='midi_note_pairing']
    assert {r['source']['id'] for r in pairing} == {'midi-t0-e1','midi-t0-e2'}
    assert all(r['status']=='ambiguous' for r in pairing)
    assert not report['complete']


def test_overlap_does_not_hide_an_incorrect_physical_release(tmp_path):
    path, model = overlap(tmp_path)
    model['notes'][1]['duration_beats'] = 2
    report = verify_midi_performance(path, model)
    assert not report['passed']
    assert any(r['construct']=='midi_performance' and r['source']['id']=='midi-t0-e2'
               for r in report['discrepancies'])


def test_raw_inventory_requires_ambiguity_and_rejects_forged_verified_pairing(tmp_path):
    path, model = overlap(tmp_path)
    required = source_inventory(path)
    expected = [r for r in required if r['construct']=='midi_note_pairing']
    assert len(expected)==2
    report = verify_midi_performance(path, model)
    for row in report['elements']:
        if row['construct']=='midi_note_pairing':
            row['status']='verified'
    errors = []
    accounted = _account_inventory(report, required, errors, boundary='semantic', midi=True)
    assert any('pairing' in e.lower() for e in errors)
    assert all(r['status']=='unverified' for r in accounted['elements']
               if r['construct']=='midi_note_pairing')
