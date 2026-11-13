"""Native chord availability: every chord of a score gets its Verovio template."""
from pathlib import Path

import pytest

from verovio_test_score import (chord_xml, chords_by_names, prepare_musicxml,
                                rest_xml, score_xml)


ROOT = Path(__file__).resolve().parents[1]
_TICKS = {"whole": 64, "half": 32, "quarter": 16, "eighth": 8, "16th": 4, "32nd": 2, "64th": 1}


def _rests(ticks: int) -> str:
    out = []
    for kind, length in _TICKS.items():
        while ticks >= length:
            out.append(rest_xml(length, kind))
            ticks -= length
    return "".join(out)


def _mapped(prepared) -> dict:
    return {leader: key for key, item in prepared["layout"]["native_chord_templates"].items()
            for leader in item.get("leaders", {})}


def _assert_every_chord_mapped(prepared):
    from piano_teacher.notation.assets.chords import chord_lanes
    mapped = _mapped(prepared)
    chords = list(chord_lanes(prepared["model"]))
    assert chords
    for leader, notes, _ in chords:
        assert leader["id"] in mapped, (leader["measure"], leader["id"])
        heads = prepared["layout"]["native_chord_templates"][mapped[leader["id"]]]["leaders"][leader["id"]]
        assert sorted(heads) == sorted(n["id"] for n in notes)
    return mapped, chords


def test_chord_catalogue_is_not_silently_truncated(tmp_path):
    # Forty distinct shapes (twenty intervals, two note values), four per bar.
    letters = "CDEFGAB"
    chords = []
    for kind, ticks in (("quarter", 16), ("eighth", 8)):
        for interval in range(1, 21):
            upper = 6 + interval
            chords.append(chord_xml(f"B4 {letters[upper % 7]}{4 + upper // 7}", kind, ticks // 4)
                          + ("" if kind == "quarter" else rest_xml(2, "eighth")))
    measures = ["".join(chords[i:i + 4]) for i in range(0, len(chords), 4)]
    prepared = prepare_musicxml(score_xml(measures), tmp_path)
    mapped, found = _assert_every_chord_mapped(prepared)
    assert len(found) == 40 and len(set(mapped.values())) == 40


def test_every_note_value_keeps_its_own_templates(tmp_path):
    measures = []
    for kind in ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th"):
        for upper in ("D5", "E5", "G5"):
            measures.append(chord_xml(f"B4 {upper}", kind, _TICKS[kind]) + _rests(64 - _TICKS[kind]))
    prepared = prepare_musicxml(score_xml(measures, divisions=16), tmp_path)
    mapped, found = _assert_every_chord_mapped(prepared)
    assert len(found) == 21 and len(set(mapped.values())) == 21


def test_ala_measure_nine_chords_have_instance_templates(tmp_path):
    """A real user MIDI: every chord of Ala's measure-9 exercise is engraved."""
    from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
    from piano_teacher.music import load_midi
    from piano_teacher.preprocessing_cache import PreprocessingCache

    path = ROOT/"midi/Ala_–_Joep_Beving.midi"
    piece = load_midi(path)
    phrase = next(p for p in piece.phrases if p.first_bar <= 9 <= p.last_bar)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path))
    selected = ScoreSelection(piece, phrase, "both", "ala", 1, path.name)
    _assert_every_chord_mapped({"layout": artifacts.geometry(selected),
                                "model": artifacts.semantic_score(selected)})


def test_augmented_unison_and_triple_unison_are_engraved_side_by_side(tmp_path):
    # N1: Rachmaninoff Op. 3 No. 2 bar 3 holds E4, G4 and G#4 in one voice.
    # G and G-sharp share a staff position; Verovio engraves them side by side.
    # G1: three heads on one position are a chord too.
    prepared = prepare_musicxml(score_xml([
        chord_xml("E4 G4 G#4") + chord_xml("E4 Gb4 G4 G#4") + rest_xml(8, "half")]), tmp_path)
    mapped, _ = _assert_every_chord_mapped(prepared)
    atlas = prepared["layout"]["native_chord_templates"]
    chords = chords_by_names(prepared["model"])
    (x0, y0), (x1, y1), (x2, y2) = atlas[mapped[chords[(1, "E4 G4 G#4")]["id"]]]["head_positions"]
    assert y1 == y2 and x1 != x2 and y0 > y1
    assert len(atlas[mapped[chords[(1, "E4 Gb4 G4 G#4")]["id"]]]["head_positions"]) == 4


def test_rachmaninoff_prelude_builds_complete_native_assets(tmp_path):
    # N1: the piece must reach READY, so every chord of its first stage
    # (and of the whole piece) needs an engraved template.
    import glob
    from piano_teacher.server import PracticeEngine
    path, = glob.glob(str(ROOT/"midi"/"Prelude_in_C*Rachmaninoff.midi"))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.load(path)
        layout, model = engine.geometry(), engine.semantic_score()
    finally:
        engine.db.close()
    templates = layout["native_chord_templates"]
    notes = {}
    for event in model["notation_events"]:
        if event["kind"] == "note":
            notes.setdefault((event["staff"],event["voice"],event["measure"],
                              round(event["beat"],6)),[]).append(event)
    # Every chord has its own Verovio instance template, naming its heads.
    mapped = {leader: heads for item in templates.values()
              for leader, heads in item.get("leaders", {}).items()}
    chords = 0
    for key, members in notes.items():
        leaders = [n for n in members if not n["chord"]]
        if len(members) > 1:
            chords += 1
            assert leaders[0]["id"] in mapped, f"bar {key[2]} chord has no engraving"
            assert sorted(mapped[leaders[0]["id"]]) == sorted(m["id"] for m in members)
    assert chords


def _head(step, alter, octave):
    return {"staff":"right","note_type":"quarter","stem":None,
            "spelling":{"step":step,"alter":alter,"octave":octave}}


def test_identical_spelling_and_pitch_on_one_position_is_a_chord():
    # G1: a chord draws whatever its shape. Import splits identical pitches
    # into separate voices, but a hand-built chord with a doubled head still
    # engraves: Verovio places the two heads side by side.
    from piano_teacher.notation.assets import chords
    notes = [_head("E",0,4), _head("G",0,4), _head("G",0,4)]
    for index, note in enumerate(notes):
        note.update(measure=9, id=f"n{index}", chord=index > 0, kind="note",
                    voice="1", beat=0.0)
    measure = {"number": 9, "clefs": {"right": {"sign": "G", "line": 2}}}
    assert chords.chord_refusal(notes[0], notes, measure) is None
    model = {"measures": [measure], "notation_events": notes}
    assert chords.refused_chords(model) == []
    assert [leader["id"] for leader, _, _ in chords.chord_lanes(model)] == ["n0"]


def test_only_input_that_is_not_one_chord_is_refused_with_its_cause():
    from piano_teacher.notation.assets import chords
    measure = {"number": 3, "clefs": {"right": {"sign": "G", "line": 2}}}
    mixed = [_head("C",0,4), {**_head("E",0,4), "note_type": "half"}]
    for index, note in enumerate(mixed):
        note.update(measure=3, id=f"m{index}", chord=index > 0)
    reason = chords.chord_refusal(mixed[0], mixed, measure)
    assert reason == ("measure 3, right staff: heads of different note values "
                      "are separate voices, not one chord")
    # Eleven heads, a five-octave span and stacked unisons are chords.
    for names in (["C4","D4","E4","F4","G4","A4","B4","C5","D5","E5","F5"],
                  ["A0","C8"], ["G4","G4","G4","G4"]):
        heads = [_head(n[0], 0, int(n[1])) for n in names]
        assert chords.chord_refusal(heads[0], heads, measure) is None


CORPUS = sorted((ROOT / "midi").glob("*.midi"))


def test_corpus_has_seventeen_pieces():
    assert len(CORPUS) == 17


@pytest.mark.slow
@pytest.mark.parametrize("path", CORPUS, ids=[p.stem[:24] for p in CORPUS])
def test_every_corpus_chord_is_engraved(path, tmp_path):
    """Every lesson phrase of a corpus MIDI through the production path:
    ScoreArtifacts engraving and native preparation. Each chord has its
    Verovio instance template naming exactly its heads, and none is refused.
    """
    from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.notation.assets.chords import refused_chords
    from piano_teacher.preprocessing_cache import PreprocessingCache

    piece, _ = import_piece(path)
    artifacts = ScoreArtifacts(PreprocessingCache(tmp_path))
    for phrase in piece.phrases:
        selected = ScoreSelection(piece, phrase, "both", "corpus", 1, path.name)
        layout = artifacts.geometry(selected)
        prepared = {"layout": layout, "model": artifacts.semantic_score(selected)}
        assert refused_chords(prepared["model"]) == [], phrase.first_bar
        from piano_teacher.notation.assets.chords import chord_lanes
        if any(True for _ in chord_lanes(prepared["model"])):
            _assert_every_chord_mapped(prepared)
