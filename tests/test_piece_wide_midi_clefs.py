"""Stable grand-staff clefs for the user's original Joep Beving MIDI.

MIDI has no printed clef metadata. Its opening LH notes are higher than most
of the LH part; inferring from the first two bars alone incorrectly yields G.
Do not alter the imported notes or re-key the passage to force a bass clef.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

from piano_teacher.notation.lesson import (
    _readable_clef,
    build_lesson_score,
    infer_piece_clefs,
)
from piano_teacher.music import ClefChange, Note, Phrase
from piano_teacher.importing.pieces import import_piece
from piano_teacher.server import PracticeEngine


ALA = Path(__file__).resolve().parents[1] / "midi" / "Ala_–_Joep_Beving.midi"


def _opening_clefs(score):
    root = ET.fromstring(score.musicxml)
    result = {}
    for part in root.findall("part"):
        attrs = part.find("./measure/attributes/clef")
        result[part.attrib["id"]] = (
            attrs.findtext("sign"), int(attrs.findtext("line")))
    return result


def test_ala_midi_opener_and_whole_piece_differ_in_left_register():
    piece, _ = import_piece(ALA)
    first_phrase = piece.phrases[0]
    opening_left = [note for note in first_phrase.notes if note.hand == "left"]
    entire_left = [note.pitch for note in piece.notes if note.hand == "left"]
    assert opening_left and entire_left
    # Reproduces the broken version, while protecting the two-track
    # hand assignment from regressions.
    assert _readable_clef(opening_left, None, "left")["sign"] == "G"
    assert sorted(entire_left)[len(entire_left) // 2] < 60
    assert infer_piece_clefs(piece.notes) == {
        "right": {"sign": "G", "line": 2, "octave_change": 0},
        "left": {"sign": "F", "line": 4, "octave_change": 0},
    }


def test_ala_uses_same_bass_clef_in_every_short_lesson():
    piece, _ = import_piece(ALA)
    default = infer_piece_clefs(piece.notes)
    for phrase in piece.phrases[:5]:
        notation = build_lesson_score(
            phrase, boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,
            key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes,
            default_clefs=default,
        )
        assert _opening_clefs(notation) == {
            "RH": ("G", 2), "LH": ("F", 4)
        }, f"Measure {phrase.first_bar} changed the LH clef"


def test_explicit_source_clef_is_not_overwritten_by_piece_wide_default():
    phrase = Phrase(1, 1, 1, 0, 4, (
        Note(0, 2, 72, 0, 0, "right"),
        Note(0, 2, 76, 1, 0, "left"),
    ))
    explicit = ClefChange(0.0, "G", 2, hand="left")
    lesson = build_lesson_score(
        phrase, boundaries=(0, 4), time_signatures=((0, 4, 4),),
        clef_changes=(explicit,),
        default_clefs={"right": {"sign": "G", "line": 2, "octave_change": 0},
                       "left": {"sign": "F", "line": 4, "octave_change": 0}},
    )
    assert _opening_clefs(lesson)["LH"] == ("G", 2)


def test_actual_practice_engine_delivers_stable_clefs_to_verovio(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.load(str(ALA))
    engraved = engine.engraving()
    assert engraved.layout["staff_clefs"]["right"]["sign"] == "G"
    assert engraved.layout["staff_clefs"]["left"]["sign"] == "F"
    assert len(engraved.layout.get("notes", [])) > 0
    # The semantic timeline and visual engraver must agree on their clefs.
    model = engine.semantic_score()
    assert model["measures"][0]["clefs"]["left"]["sign"] == "F"


def test_unannotated_midi_right_hand_uses_bass_in_bass_register():
    # The Beethoven Op. 13 Adagio opening plays in the bass register with
    # the right hand. MIDI lacks a printed clef; forcing treble places
    # several unnecessary ledger lines below the five-line staff.
    notes = (Note(0, 1, 48, 0, 0, "right"),
             Note(1, 2, 53, 0, 0, "right"))
    defaults = infer_piece_clefs(notes)
    assert defaults["right"] == {
        "sign": "F", "line": 4, "octave_change": 0}
    phrase = Phrase(1, 1, 1, 0.0, 4.0, notes)
    lesson = build_lesson_score(
        phrase, boundaries=(0.0, 4.0),
        default_clefs=defaults)
    assert _opening_clefs(lesson)["RH"] == ("F", 4)


def test_unannotated_midi_right_hand_keeps_treble_in_treble_register():
    notes = (Note(0, 1, 72, 0, 0, "right"),
             Note(1, 2, 76, 0, 0, "right"))
    assert infer_piece_clefs(notes)["right"] == {
        "sign": "G", "line": 2, "octave_change": 0}


def test_authored_right_hand_treble_survives_conflicting_bass_register():
    # An actual MusicXML clef is authoritative, regardless of inferred MIDI
    # preference. This also protects mid-piece authored clef changes.
    notes = (Note(0, 2, 36, 0, 0, "right"),
             Note(2, 4, 40, 0, 0, "right"))
    phrase = Phrase(1, 1, 1, 0.0, 4.0, notes)
    defaults = infer_piece_clefs(notes)
    assert defaults["right"]["sign"] == "F"
    lesson = build_lesson_score(
        phrase, boundaries=(0.0, 4.0),
        clef_changes=(ClefChange(0.0, "G", 2, hand="right"),),
        default_clefs=defaults)
    assert _opening_clefs(lesson)["RH"] == ("G", 2)
