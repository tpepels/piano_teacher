"""Generated exercises progressively restore pitches and retain source IDs."""
from piano_teacher.exercise_generator import generate_variants
from piano_teacher.music import Note, Phrase


def note(pitch,start,hand="right"):
    return Note(start,start+.5,pitch,0,0,hand)


def phrase(notes):
    return Phrase(1,1,2,0,8,tuple(notes))


def test_complex_passage_generates_progressive_levels():
    p=phrase([note(60,0),note(64,0),note(67,0),note(72,.25),
              note(62,1),note(65,1),note(69,1),note(74,1.25),
              note(48,0,"left"),note(52,0,"left"),note(55,0,"left")])
    stages=generate_variants(p)
    assert [v.level for v in stages]==["skeleton","outline","original"]
    assert len(stages[0].notes)<len(stages[1].notes)<len(stages[2].notes)
    assert set(stages[0].source_indices).issubset(stages[1].source_indices)
    assert set(stages[1].source_indices).issubset(stages[2].source_indices)
    assert all(p.notes[i]==n for v in stages for i,n in zip(v.source_indices,v.notes))


def test_easy_melody_needs_only_original_stage():
    p=phrase([note(60,0),note(62,1),note(64,2),note(65,3)])
    stages=generate_variants(p,"right")
    assert len(stages)==1 and stages[0].level=="original"
    assert stages[0].notes==p.notes


def test_hand_specific_variant_retains_source_mapping():
    p=phrase([note(48,0,"left"),note(52,0,"left"),note(67,0),note(72,0)])
    stages=generate_variants(p,"right")
    assert stages[-1].source_indices==(2,3)
    assert all(n.hand=="right" for stage in stages for n in stage.notes)


def test_two_note_chord_skips_duplicate_outline():
    p=phrase([note(60,0),note(64,0)])
    assert [v.level for v in generate_variants(p)]==["skeleton","original"]


def test_source_unchanged():
    p=phrase([note(60,0),note(64,0),note(67,0)])
    original=p.notes
    assert generate_variants(p)[-1].notes==original
    assert p.notes==original


def test_invalid_hand_rejected():
    try:
        generate_variants(phrase([note(60,0)]),"middle")
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid hand must fail")
