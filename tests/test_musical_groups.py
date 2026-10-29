"""Grouping is derived from complete source, then preserved in lesson steps."""
from collections import defaultdict
from xml.etree import ElementTree as ET

from piano_teacher.exercise_generator import generate_variants
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.musical_groups import grouping_for_piece


def written_piece(bars, attacks, *, slurs=(), beams=()):
    """Author a minimal MusicXML score and matching original attack identities.

    attacks: (absolute beat, duration, MIDI pitch); the source importer uses
    the source element's ordinal (including attributes and rests) as the ID.
    """
    root = ET.Element("score-partwise")
    partlist = ET.SubElement(root, "part-list")
    ET.SubElement(ET.SubElement(partlist, "score-part", id="P1"),
                  "part-name").text = "Right Hand"
    part = ET.SubElement(root, "part", id="P1")
    notes = []
    for measure_index in range(bars):
        measure = ET.SubElement(part, "measure", number=str(measure_index + 1))
        if measure_index == 0:
            attrs = ET.SubElement(measure, "attributes")
            ET.SubElement(attrs, "divisions").text = "10080"
            time = ET.SubElement(attrs, "time")
            ET.SubElement(time, "beats").text = "4"
            ET.SubElement(time, "beat-type").text = "4"
        cursor = 0.
        for attack_index, (beat, duration, pitch) in enumerate(attacks):
            if not measure_index * 4 <= beat < (measure_index + 1) * 4:
                continue
            start = beat - measure_index * 4
            if start > cursor:
                rest = ET.SubElement(measure, "note")
                ET.SubElement(rest, "rest")
                ET.SubElement(rest, "duration").text = str(round((start-cursor) * 10080))
                ET.SubElement(rest, "voice").text = "1"
            ordinal = len(measure)
            el = ET.SubElement(measure, "note")
            note_pitch = ET.SubElement(el, "pitch")
            ET.SubElement(note_pitch, "step").text = "C"
            ET.SubElement(note_pitch, "octave").text = str(4+attack_index//8)
            ET.SubElement(el, "duration").text = str(round(duration * 10080))
            ET.SubElement(el, "voice").text = "1"
            ET.SubElement(el, "type").text = ("16th" if duration == .25 else
                                               "eighth" if duration == .5 else "quarter")
            if any(attack_index in group for group in slurs):
                notations = ET.SubElement(el, "notations")
                for number, group in enumerate(slurs, 1):
                    if attack_index == group[0]:
                        ET.SubElement(notations, "slur", number=str(number), type="start")
                    if attack_index == group[-1]:
                        ET.SubElement(notations, "slur", number=str(number), type="stop")
            for group in beams:
                if attack_index in group:
                    mark = ET.SubElement(el, "beam", number="1")
                    mark.text = ("begin" if attack_index == group[0] else
                                 "end" if attack_index == group[-1] else "continue")
            notes.append(Note(beat, beat+duration, pitch, 0, 0, "right",
                              f"xml-p0-m{measure_index}-e{ordinal}", voice="xml-p0-s1-v1"))
            cursor = start + duration
        if cursor < 4:
            rest = ET.SubElement(measure, "note")
            ET.SubElement(rest, "rest")
            ET.SubElement(rest, "duration").text = str(round((4 - cursor) * 10080))
            ET.SubElement(rest, "voice").text = "1"
    boundaries = tuple(i * 4. for i in range(bars + 1))
    return Piece("Written groups", 100, tuple(notes), (), bar_boundaries=boundaries,
                 time_signatures=((0., 4, 4),),
                 source_musicxml=ET.tostring(root, encoding="unicode"))


def _onset_set(notes):
    return {round(n.start, 6) for n in notes}


def _all_or_none(variants, group):
    required = {tuple(sorted(onset)) for onset in group.onsets}
    all_indices = group.indices
    for variant in variants:
        present = set(variant.source_indices)
        for onset in group.onsets:
            assert not (present & onset) or bool(present & onset)
        hits = [bool(present & onset) for onset in group.onsets]
        assert len(set(hits)) == 1, (variant.level, hits)
    assert all_indices.issuperset(set().union(*group.onsets))


def test_authored_short_slur_is_atomic_while_chords_can_be_thinned():
    source = written_piece(2, [
        (0., .5, 60), (.5, .5, 62), (1., .5, 64),
        (2., .5, 65), (2.5, .5, 67),
    ], slurs=((0, 1, 2),))
    grouping = grouping_for_piece(source)
    slur, = [g for g in grouping.groups if g.kind == "slur"]
    assert slur.attack_count == 3
    phrase = Phrase(1, 1, 2, 0., 8., source.notes)
    variants = generate_variants(phrase, "right",
        groups=grouping.for_phrase(phrase, "right"),
        max_attacks=SETTINGS.focus_max_attacks)
    _all_or_none(variants, slur)
    assert variants[-1].notes == source.notes


def test_short_slur_across_two_measure_focus_boundary_is_kept_together():
    piece = written_piece(4, [
        (0., 1., 60), (4., .5, 62), (7.5, .5, 64),
        (8., .5, 65), (8.5, .5, 67), (12., 1., 69),
    ], slurs=((2, 3, 4),))
    plan = LearningPlan(piece)
    # An initial two-bar focus would sever the three-note phrase at beat 8.
    assert (plan.exercise.phrase.first_bar, plan.exercise.phrase.last_bar) == (1, 3)
    slur, = [g for g in plan.grouping.groups if g.kind == "slur"]
    _all_or_none(plan.variants, slur)


def test_long_slur_uses_contiguous_beam_aligned_windows_then_original():
    attacks = [(i * .25, .25, 60 + i) for i in range(12)]
    piece = written_piece(1, attacks,
        slurs=(tuple(range(12)),),
        beams=(tuple(range(0, 4)), tuple(range(4, 8)),
               tuple(range(8, 12))))
    plan = LearningPlan(piece)
    assert sorted(g.attack_count for g in plan.grouping.groups) == [4, 4, 4, 12]
    stages = plan.variants
    assert [stage.level for stage in stages] == ["skeleton", "outline", "original"]
    assert [_onset_set(stage.notes) for stage in stages] == [
        {i*.25 for i in range(4)},
        {i*.25 for i in range(8)},
        {i*.25 for i in range(12)}]
    assert len(stages[1].notes) <= SETTINGS.focus_max_attacks
    assert stages[-1].notes == piece.notes
    for group in plan.grouping.groups:
        if group.kind == "beam":
            _all_or_none(stages, group)


def test_midi_beaming_model_is_derived_before_exercise_simplification():
    notes = tuple(Note(i*.25, (i+1)*.25, 60+i, 0, 0, "right",
                       f"midi-{i}", voice="v") for i in range(8))
    piece = Piece("MIDI groups", 100, notes, (),
                  bar_boundaries=(0., 4.),
                  time_signatures=((0., 4, 4),))
    plan = LearningPlan(piece)
    beams = [g for g in plan.grouping.groups if g.kind == "beam"]
    assert [g.attack_count for g in beams] == [4, 4]
    assert not any(g.kind == "slur" for g in plan.grouping.groups)
    for group in beams:
        _all_or_none(plan.variants, group)
    assert plan.variants[-1].notes == notes


def test_no_invented_slurs_for_midi_and_no_change_to_grading_events():
    notes = tuple(Note(float(i), i+1., 60+i, 0, 0, "right",
                       f"n{i}") for i in range(4))
    piece = Piece("MIDI only", 90, notes, (),
                  bar_boundaries=(0., 4.))
    plan = LearningPlan(piece)
    assert not any(g.kind == "slur" for g in plan.grouping.groups)
    assert plan.variants[-1].notes == notes
