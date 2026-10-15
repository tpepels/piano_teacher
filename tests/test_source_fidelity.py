"""Real source files retain attack identity, exact time, and written context."""
from pathlib import Path
from xml.etree import ElementTree as ET

import mido
import pytest

from piano_teacher import music
from piano_teacher.score import import_piece
from piano_teacher.learning import LearningPlan


def write_midi(path, tracks, *, ppq=997):
    midi = mido.MidiFile(ticks_per_beat=ppq)
    for messages in tracks:
        midi.tracks.append(mido.MidiTrack(messages))
    midi.save(path)
    return path


def attributes(beats=4, *, fifths=None, clef=None, staves=None):
    return ('<attributes><divisions>1</divisions>'
            + ('' if fifths is None else f'<key><fifths>{fifths}</fifths><mode>major</mode></key>')
            + f'<time><beats>{beats}</beats><beat-type>4</beat-type></time>'
            + ('' if staves is None else f'<staves>{staves}</staves>')
            + ('' if clef is None else f'<clef><sign>{clef[0]}</sign><line>{clef[1]}</line></clef>')
            + '</attributes>')


def xml_note(step='C', octave=4, duration=1, *, alter=None, voice=None, staff=None, tie=None, grace=False):
    return ('<note>' + ('<grace/>' if grace else '') + '<pitch>'
            + f'<step>{step}</step>' + ('' if alter is None else f'<alter>{alter}</alter>')
            + f'<octave>{octave}</octave></pitch><duration>{duration}</duration>'
            + ('' if voice is None else f'<voice>{voice}</voice>')
            + ('' if staff is None else f'<staff>{staff}</staff>')
            + ('' if tie is None else f'<tie type="{tie}"/>') + '</note>')


def write_xml(path, parts):
    listing = ''.join(f'<score-part id="P{i}"><part-name>{name}</part-name></score-part>'
                      for i, (name, _) in enumerate(parts))
    body = ''.join(f'<part id="P{i}">{body}</part>' for i, (_, body) in enumerate(parts))
    path.write_text(f'<score-partwise version="4.0"><part-list>{listing}</part-list>{body}</score-partwise>')
    return path


def test_legacy_note_constructor_stays_compatible_and_import_ids_are_path_independent(tmp_path):
    legacy = music.Note(0, 1, 60, 0, 0, 'right')
    assert legacy.source_id == '' and legacy.voice == '' and legacy.spelling is None
    assert music.source_note_id(legacy, 0) != music.source_note_id(legacy, 1)
    path = write_midi(tmp_path/'attacks.mid', [[
        mido.Message('note_on', note=60, velocity=80),
        mido.Message('note_off', note=60, time=100),
        mido.Message('note_on', note=60, velocity=80),
        mido.Message('note_off', note=60, time=100),
    ], [mido.Message('note_on', note=60, velocity=80), mido.Message('note_off', note=60, time=200)]])
    first = music.load_midi(path)
    copy = tmp_path/'renamed.mid'
    copy.write_bytes(path.read_bytes())
    second = music.load_midi(copy)
    ids = [note.source_id for note in first.notes]
    assert all(ids) and len(set(ids)) == 3
    assert ids == [note.source_id for note in second.notes]
    assert all(music.source_note_id(note, 100) == note.source_id for note in first.notes)


def test_midi_retains_ppq_timing_explicit_key_and_no_invented_key(tmp_path):
    path = write_midi(tmp_path/'ppq.mid', [[
        mido.MetaMessage('key_signature', key='Bb'),
        mido.Message('note_on', note=70, velocity=80, time=101),
        mido.Message('note_off', note=70, time=1237),
    ]])
    piece = music.load_midi(path)
    assert piece.notes[0].start == 101/997 and piece.notes[0].end == 1338/997
    assert piece.notes[0].spelling is None
    assert [(key.beat, key.fifths, key.mode) for key in piece.key_signatures] == [(0, -2, 'major')]
    anonymous = write_midi(tmp_path/'unkeyed.mid', [[mido.Message('note_on', note=60, velocity=80),
                                                   mido.Message('note_off', note=60, time=997)]])
    assert music.load_midi(anonymous).key_signatures == ()


def test_musicxml_pickup_and_explicit_trailing_rest_measures_are_preserved(tmp_path):
    path = write_xml(tmp_path/'pickup.musicxml', [('Right hand',
        '<measure number="0" implicit="yes">'+attributes()+xml_note()+'</measure>'
        '<measure number="1">'+xml_note('D', duration=4)+'</measure>'
        '<measure number="2"><note><rest measure="yes"/><duration>4</duration></note></measure>')])
    piece, _ = import_piece(path)
    assert piece.bar_boundaries == (0, 1, 5, 9)
    assert [(note.start, note.end) for note in piece.notes] == [(0, 1), (1, 5)]
    assert piece.phrases[0].end == 5
    assert LearningPlan(piece).exercises[-1].phrase.end == 9


def test_parallel_unison_ties_remain_two_voice_scoped_attacks_with_original_ids(tmp_path):
    path = write_xml(tmp_path/'parallel.musicxml', [('Right hand',
        '<measure number="1">'+attributes()+xml_note(duration=4, voice='1', tie='start')
        +'<backup><duration>4</duration></backup><note><rest/><duration>2</duration><voice>2</voice></note>'
        +xml_note(duration=2, voice='2', tie='start')+'</measure>'
        '<measure number="2">'+xml_note(duration=1, voice='1', tie='stop')
        +'<note><rest/><duration>3</duration><voice>1</voice></note>'
        +'<backup><duration>4</duration></backup>'+xml_note(duration=2, voice='2', tie='stop')
        +'<note><rest/><duration>2</duration><voice>2</voice></note></measure>')])
    piece, _ = import_piece(path)
    assert [(note.start, note.end, note.pitch) for note in piece.notes] == [(0, 5, 60), (2, 6, 60)]
    assert len({note.source_id for note in piece.notes}) == 2
    assert len({note.voice for note in piece.notes}) == 2
    again, _ = import_piece(path)
    assert piece.notes == again.notes


def test_explicit_xml_names_crossed_registers_spelling_keys_and_clefs_survive(tmp_path):
    path = write_xml(tmp_path/'crossed.musicxml', [
        ('Right hand', '<measure number="1">'+attributes(2, fifths=-2, clef=('F', 4))
         +xml_note('B', 3, alter=-1)+xml_note('E', 4, alter=-1)+'</measure>'),
        ('Left hand', '<measure number="1">'+attributes(2, fifths=-2, clef=('G', 2))
         +xml_note('B', 5, alter=-1)+xml_note('E', 6, alter=-1)+'</measure>')])
    piece, _ = import_piece(path)
    assert [(note.pitch, note.hand) for note in piece.notes] == [(58, 'right'), (82, 'left'), (63, 'right'), (87, 'left')]
    assert [note.spelling for note in piece.notes] == [('B', -1, 3), ('B', -1, 5), ('E', -1, 4), ('E', -1, 6)]
    assert {(key.fifths, key.hand) for key in piece.key_signatures} == {(-2, 'right'), (-2, 'left')}
    assert {(clef.sign, clef.line, clef.hand) for clef in piece.clef_changes} == {('F', 4, 'right'), ('G', 2, 'left')}


@pytest.mark.parametrize('body, message', [
    (xml_note(tie='stop'), 'orphan tie'),
    (xml_note(tie='start'), 'unterminated.*tie'),
    (xml_note(alter='.5'), 'microtonal'),
    (xml_note(grace=True), 'grace'),
    ('<note><unpitched><display-step>C</display-step><display-octave>4</display-octave></unpitched><duration>1</duration></note>', 'unpitched'),
])
def test_unsupported_xml_attacks_raise_meaningful_errors(tmp_path, body, message):
    path = write_xml(tmp_path/'unsupported.musicxml', [('Right hand', '<measure number="1">'+attributes(1)+body+'</measure>')])
    with pytest.raises(ValueError, match=message):
        import_piece(path)


@pytest.mark.parametrize('events, message', [
    ([mido.Message('note_on', note=60, velocity=80), mido.MetaMessage('end_of_track', time=997)], 'unterminated MIDI note'),
    ([mido.Message('note_off', note=60, time=997)], 'No pitched MIDI notes found'),
    ([mido.Message('note_on', note=60, velocity=80), mido.Message('note_off', note=60)], 'No pitched MIDI notes found'),
    ([mido.Message('note_on', note=60, velocity=80), mido.Message('note_on', note=60, velocity=80, time=10),
      mido.Message('note_off', note=60, time=100), mido.Message('note_off', note=60, time=100)], 'overlapping MIDI note'),
])
def test_midi_with_no_sounding_notes_or_unrepairable_pairings_still_fails(tmp_path, events, message):
    path = write_midi(tmp_path/'unsupported.mid', [events])
    with pytest.raises(ValueError, match=message):
        music.load_midi(path)


def test_conflicting_xml_measure_grids_are_rejected_before_constructing_a_piece(tmp_path):
    path = write_xml(tmp_path/'conflict.musicxml', [
        ('Right hand', '<measure number="1">'+attributes(4)+xml_note(duration=4)+'</measure>'),
        ('Left hand', '<measure number="1">'+attributes(3)+xml_note(duration=3)+'</measure>')])
    with pytest.raises(ValueError, match='conflicting'):
        import_piece(path)


def test_source_key_clef_changes_and_octave_context_remain_timed_to_the_source(tmp_path):
    path = write_xml(tmp_path/'context.musicxml', [('Right hand',
        '<measure number="1">'+attributes(4, fifths=0, clef=('G', 2))+xml_note(duration=4)+'</measure>'
        '<measure number="2"><attributes><key><fifths>-3</fifths><mode>minor</mode></key>'
        '<clef><sign>F</sign><line>4</line><clef-octave-change>-1</clef-octave-change></clef></attributes>'
        +xml_note('E', 4, 4, alter=-1)+'</measure>')])
    piece, _ = import_piece(path)
    assert [(key.beat, key.fifths, key.mode) for key in piece.key_signatures] == [(0, 0, 'major'), (4, -3, 'minor')]
    assert [(clef.beat, clef.sign, clef.line, clef.octave_change) for clef in piece.clef_changes] == [(0, 'G', 2, 0), (4, 'F', 4, -1)]


def test_musicxml_compressed_container_preserves_the_same_canonical_ids(tmp_path):
    import zipfile
    source = write_xml(tmp_path/'source.musicxml', [('Right hand',
        '<measure number="1">'+attributes(1)+xml_note()+'</measure>')])
    compressed = tmp_path/'relocated.mxl'
    with zipfile.ZipFile(compressed, 'w') as package:
        package.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="scores/actual.musicxml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>')
        package.writestr('scores/actual.musicxml', source.read_bytes())
    plain, _ = import_piece(source)
    packed, _ = import_piece(compressed)
    assert packed.notes == plain.notes and packed.bar_boundaries == plain.bar_boundaries


def test_grandstaff_clef_metadata_keeps_empty_lower_staff_scoped_to_left_hand(tmp_path):
    body = ('<measure number="1">'+attributes(1, staves=2)
            +'<attributes><clef number="1"><sign>G</sign><line>2</line></clef>'
             '<clef number="2"><sign>F</sign><line>4</line></clef></attributes>'
            +xml_note(staff='1')+'<backup><duration>1</duration></backup>'
             '<note><rest/><duration>1</duration><staff>2</staff></note></measure>')
    path = write_xml(tmp_path/'empty-staff.musicxml', [('Piano', body)])
    piece, _ = import_piece(path)
    assert [(clef.sign, clef.hand) for clef in piece.clef_changes] == [('G', 'right'), ('F', 'left')]


def test_midi_explicit_end_of_track_retains_trailing_source_silence(tmp_path):
    path = write_midi(tmp_path/'silence.mid', [[mido.Message('note_on', note=60, velocity=80),
        mido.Message('note_off', note=60, time=997), mido.MetaMessage('end_of_track', time=6979)]])
    piece = music.load_midi(path)
    assert piece.bar_boundaries == (0, 4, 8)
    assert piece.notes[0].end == 1 and LearningPlan(piece).exercises[-1].phrase.end == 8


def test_conflicting_midi_meter_metadata_is_not_silently_chosen_by_sort_order(tmp_path):
    path = write_midi(tmp_path/'meter-conflict.mid', [[mido.MetaMessage('time_signature', numerator=3, denominator=4),
        mido.Message('note_on', note=60, velocity=80), mido.Message('note_off', note=60, time=997)],
        [mido.MetaMessage('time_signature', numerator=4, denominator=4)]])
    with pytest.raises(ValueError, match='conflicting MIDI time signatures'):
        music.load_midi(path)


def test_noncontiguous_tie_cannot_turn_an_explicit_rest_into_a_held_note(tmp_path):
    path = write_xml(tmp_path/'tie-gap.musicxml', [('Right hand', '<measure number="1">'+attributes(3)
        +xml_note(tie='start')+'<note><rest/><duration>1</duration></note>'+xml_note(tie='stop')+'</measure>')])
    with pytest.raises(ValueError, match='non-contiguous tie'):
        import_piece(path)


def test_supplied_full_piece_keeps_all_source_attacks_and_legacy_stage_identity():
    import hashlib
    import json
    source = Path('/home/tom/Music/Piano Teacher/Merry-Go-Round-of-Life.midi')
    if not source.is_file():
        pytest.skip('The local 2,346-note user import is unavailable')
    piece = music.load_midi(source)
    plan = LearningPlan(piece)
    assert len(piece.notes) == len({note.source_id for note in piece.notes}) == 2346
    assert len(piece.bar_boundaries)-1 == 237 and piece.bar_boundaries[-1] == 712
    assert len(plan.lesson_steps) == 301
    # Recorded from f5e1957's original importer over this exact supplied MIDI.
    digest = hashlib.sha256(json.dumps([step.key for step in plan.lesson_steps], separators=(',', ':')).encode()).hexdigest()
    assert digest == 'c7940fab7bc768f4f4fadd722ddd216a3174bd2785eb7687e69492c7df0c8c81'
    assert plan.exercises[-1].phrase.notes == piece.notes


def test_unsupported_musicxml_layout_has_a_source_error_before_music21_conversion(tmp_path):
    path = tmp_path/'unsupported-layout.musicxml'
    path.write_text('<score-timewise version="4.0"><part-list/></score-timewise>')
    with pytest.raises(ValueError, match='score-partwise'):
        import_piece(path)


def test_conflicting_midi_key_signatures_are_rejected_but_equal_duplicates_are_allowed(tmp_path):
    def source(filename, second_key):
        return write_midi(tmp_path/filename, [[mido.MetaMessage('key_signature', key='C'),
            mido.Message('note_on', note=60, velocity=80), mido.Message('note_off', note=60, time=997)],
            [mido.MetaMessage('key_signature', key=second_key),
             mido.Message('note_on', note=67, velocity=80), mido.Message('note_off', note=67, time=997)]])
    duplicate = music.load_midi(source('duplicate-key.mid', 'C'))
    assert len(duplicate.notes) == 2
    assert [(key.beat, key.fifths, key.mode) for key in duplicate.key_signatures] == [(0, 0, 'major')]
    with pytest.raises(ValueError, match='conflicting MIDI key signatures'):
        import_piece(source('conflicting-keys.mid', 'Eb'))
