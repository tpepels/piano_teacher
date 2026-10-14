from pathlib import Path
import mido
import pytest
from piano_teacher.music import load_midi, note_name


def write_example(path: Path, two_tracks=False, meter=(4, 4)):
    mid = mido.MidiFile(ticks_per_beat=480)
    left = mido.MidiTrack()
    left.append(mido.MetaMessage('time_signature', numerator=meter[0], denominator=meter[1], time=0))
    left.append(mido.MetaMessage('set_tempo', tempo=600000, time=0))
    left.append(mido.MetaMessage('track_name', name='Left Hand', time=0))
    left.append(mido.Message('note_on', channel=0, note=48, velocity=80, time=0))
    left.append(mido.Message('note_off', channel=0, note=48, time=480))
    left.append(mido.Message('note_on', channel=0, note=50, velocity=80, time=1920))
    left.append(mido.Message('note_on', channel=0, note=50, velocity=0, time=480))
    mid.tracks.append(left)
    if two_tracks:
        right = mido.MidiTrack()
        right.append(mido.MetaMessage('track_name', name='Right Hand', time=0))
        right.append(mido.Message('note_on', channel=0, note=72, velocity=80, time=0))
        right.append(mido.Message('note_off', channel=0, note=72, time=480))
        mid.tracks.append(right)
    mid.save(path)


def test_import_notes_measures_and_tracks(tmp_path):
    source = tmp_path / 'example.mid'
    write_example(source, two_tracks=True)
    piece = load_midi(source, bars_per_phrase=1)
    assert piece.title == 'example'
    assert piece.bpm == 100
    assert len(piece.notes) == 3
    assert [n.hand for n in piece.notes] == ['left', 'right', 'left']
    assert len(piece.phrases) == 2
    assert piece.phrases[0].start == 0
    assert piece.phrases[0].end == 4
    assert piece.phrases[1].start == 4
    assert note_name(60) == 'C4'


def test_six_eight_is_three_quarter_beats(tmp_path):
    source = tmp_path / 'six-eight.mid'
    write_example(source, meter=(6, 8))
    piece = load_midi(source, bars_per_phrase=1)
    assert piece.phrases[0].end == 3
    assert piece.phrases[1].start == 3


def test_empty_and_drum_only_rejected(tmp_path):
    source = tmp_path / 'drums.mid'
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    track.append(mido.Message('note_on', note=36, channel=9, velocity=70))
    track.append(mido.Message('note_off', note=36, channel=9, time=480))
    mid.tracks.append(track)
    mid.save(source)
    with pytest.raises(ValueError, match='No pitched'):
        load_midi(source)


def test_two_tracks_with_crossing_registers_stay_separate(tmp_path):
    source = tmp_path / 'cross.mid'
    midi = mido.MidiFile()
    for name, pitch in [('Left Hand', 65), ('Right Hand', 55)]:
        t = mido.MidiTrack()
        t.append(mido.MetaMessage('track_name', name=name))
        t.append(mido.Message('note_on', note=pitch, velocity=90))
        t.append(mido.Message('note_off', note=pitch, time=480))
        midi.tracks.append(t)
    midi.save(source)
    piece = load_midi(source)
    assert [(n.pitch,n.hand) for n in piece.notes] == [(55,'right'),(65,'left')]

