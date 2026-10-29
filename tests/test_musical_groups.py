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
            scale = (("C", 0), ("C", 1), ("D", 0), ("D", 1),
                     ("E", 0), ("F", 0), ("F", 1), ("G", 0),
                     ("G", 1), ("A", 0), ("A", 1), ("B", 0))
            step, alter = scale[pitch % 12]
            ET.SubElement(note_pitch, "step").text = step
            if alter:
                ET.SubElement(note_pitch, "alter").text = str(alter)
            ET.SubElement(note_pitch, "octave").text = str(pitch // 12 - 1)
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
    all_indices = group.indices
    for variant in variants:
        present = set(variant.source_indices)
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
    from piano_teacher.learning import build_exercises

    direct = build_exercises(piece, consolidate=False)
    assert direct[0].phrase.last_bar >= 3
    plan = LearningPlan(piece)
    # An initial two-bar focus would sever the three-note phrase at beat 8.
    assert plan.exercise.phrase.first_bar == 1
    assert plan.exercise.phrase.last_bar >= 3
    # The sparse final bar may be merged backward; it must not sever the slur.
    assert plan.exercise.phrase.last_bar <= 4
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


def test_chord_pitches_can_be_reduced_without_breaking_a_slur():
    from piano_teacher.musical_groups import MusicalGroup, MusicalGrouping

    notes = (
        Note(0., .5, 60, 0, 0, "right", "c", voice="v"),
        Note(0., .5, 64, 0, 0, "right", "e", voice="v"),
        Note(.5, 1., 62, 0, 0, "right", "d", voice="v"),
        Note(1., 1.5, 65, 0, 0, "right", "f", voice="v"),
        Note(2., 2.5, 67, 0, 0, "right", "g", voice="v"),
    )
    phrase = Phrase(1, 1, 1, 0., 4., notes)
    group = MusicalGroup("slur", (frozenset({0, 1}),
                                  frozenset({2}), frozenset({3})))
    grouping = MusicalGrouping((group,), {id(note): i for i, note in enumerate(notes)})
    stages = generate_variants(phrase, "right",
        groups=grouping.for_phrase(phrase, "right"),
        max_attacks=SETTINGS.focus_max_attacks)
    _all_or_none(stages, group)
    assert sum(note.start == 0. for note in stages[0].notes) == 1
    assert sum(note.start == 0. for note in stages[-1].notes) == 2
    assert _onset_set(stages[0].notes).issuperset({0., .5, 1.})
    assert stages[-1].notes == notes


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


def test_thinned_source_chord_keeps_its_visible_slur():
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.assets.slurs import slur_pairs_from_xml

    xml = """<score-partwise version="4.0"><part-list>
      <score-part id="P1"><part-name>Right Hand</part-name></score-part>
      </part-list><part id="P1"><measure number="1"><attributes>
      <divisions>10080</divisions><time><beats>4</beats><beat-type>4</beat-type></time>
      </attributes>
      <note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>5040</duration><voice>1</voice><type>eighth</type>
        <notations><slur number="1" type="start"/></notations></note>
      <note><chord/><pitch><step>E</step><octave>4</octave></pitch>
        <duration>5040</duration><voice>1</voice><type>eighth</type></note>
      <note><pitch><step>D</step><octave>4</octave></pitch>
        <duration>5040</duration><voice>1</voice><type>eighth</type>
        <notations><slur number="1" type="stop"/></notations></note>
      <note><rest/><duration>30240</duration><voice>1</voice>
        <type>half</type><dot/></note>
      </measure></part></score-partwise>"""
    voice = "xml-p0-s1-v1"
    notes = (
        Note(0., .5, 60, 0, 0, "right", "xml-p0-m0-e1", voice=voice),
        Note(0., .5, 64, 0, 0, "right", "xml-p0-m0-e2", voice=voice),
        Note(.5, 1., 62, 0, 0, "right", "xml-p0-m0-e3", voice=voice),
    )
    piece = Piece("Slurred source chord", 100, notes, (),
                  bar_boundaries=(0., 4.),
                  time_signatures=((0., 4, 4),),
                  source_musicxml=xml)
    phrase = Phrase(1, 1, 1, 0., 4., notes)
    grouping = grouping_for_piece(piece)
    simplified = generate_variants(phrase, "right",
        groups=grouping.for_phrase(phrase, "right"))[0].phrase
    assert [n.pitch for n in simplified.notes] == [64, 62]
    lesson = build_lesson_score(
        simplified, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,
        source_musicxml=piece.source_musicxml)
    projected = ET.fromstring(lesson.musicxml)
    start_note = next((n for n in projected.findall(".//note")
                       if n.find("notations/slur[@type='start']") is not None), None)
    stop_note = next((n for n in projected.findall(".//note")
                      if n.find("notations/slur[@type='stop']") is not None), None)
    assert start_note is not None and stop_note is not None
    assert start_note.findtext("pitch/step") == "E"
    assert stop_note.findtext("pitch/step") == "D"
    assert slur_pairs_from_xml(lesson.musicxml) == (
        (start_note.get("id"), stop_note.get("id")),)


def test_no_invented_slurs_for_midi_and_no_change_to_grading_events():
    notes = tuple(Note(float(i), i+1., 60+i, 0, 0, "right",
                       f"n{i}") for i in range(4))
    piece = Piece("MIDI only", 90, notes, (),
                  bar_boundaries=(0., 4.))
    plan = LearningPlan(piece)
    assert not any(g.kind == "slur" for g in plan.grouping.groups)
    assert plan.variants[-1].notes == notes
