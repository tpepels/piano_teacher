"""Native chord availability and fixed-beat readability regressions."""
from pathlib import Path

from piano_teacher.notation.assets.chords import (
    chord_pattern, patterns_from_model,
)


ROOT = Path(__file__).resolve().parents[1]


def test_chord_catalogue_is_not_silently_truncated_at_thirty_two():
    clefs = {"right": {"sign":"G","line":2}}
    events = []
    beat = 0
    for kind in ("quarter","eighth"):
        for interval in range(1,21):
            events.extend([
                {"id":f"a{beat}","kind":"note","staff":"right",
                 "voice":"1","measure":1,"beat":float(beat),
                 "chord":False,"note_type":kind,
                 "spelling":{"step":"B","octave":4}},
                {"id":f"b{beat}","kind":"note","staff":"right",
                 "voice":"1","measure":1,"beat":float(beat),
                 "chord":True,"note_type":kind,
                 "spelling":{"step":"CDEFGAB"[((6+interval)%7)],
                              "octave":4+(6+interval)//7}},
            ])
            beat += 1
    model = {"measures":[{"number":1,"clefs":clefs}],
             "notation_events":events}
    patterns=patterns_from_model(model)
    assert len(patterns) == 40, patterns
    assert any(x.startswith("quarter|") for x in patterns)
    assert any(x.startswith("eighth|") for x in patterns)


def test_long_score_keeps_every_distinct_chord_pattern():
    events = []
    beat = 0
    for kind in ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th"):
        for first, second in ((a, b) for a in range(1, 11) for b in range(a + 1, 12)):
            for index, offset in enumerate((0, first, second)):
                pitch = 34 + offset
                events.append({
                    "id": f"{beat}-{index}", "kind": "note", "staff": "right",
                    "voice": "1", "measure": 1, "beat": beat, "chord": index > 0,
                    "note_type": kind,
                    "spelling": {"step": "CDEFGAB"[pitch % 7], "octave": pitch // 7}})
            beat += 1
    model = {"measures": [{"number": 1, "clefs": {"right": {"sign": "G", "line": 2}}}],
             "notation_events": events}
    assert len(patterns_from_model(model)) == 385


def test_ala_original_source_chords_have_native_template_signatures():
    """A real user MIDI should never be rejected by a 32-item atlas cap."""
    from piano_teacher.music import load_midi
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model

    piece = load_midi(ROOT/"midi/Ala_–_Joep_Beving.midi")
    from piano_teacher.notation.assets.chords import chord_templates
    found = False
    total = 0
    target_pattern = None
    target_model = None
    for phrase in piece.phrases:
        score = build_lesson_score(
            phrase, boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,
            key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes)
        model = build_score_model(score,boundaries=piece.bar_boundaries)
        known = set(patterns_from_model(model))
        measures = {int(m["number"]):m for m in model["measures"]}
        by_attack = {}
        for event in model["notation_events"]:
            if event.get("kind") == "note":
                key=(event["staff"],event.get("voice","1"),
                     event["measure"],round(float(event["beat"]),6))
                by_attack.setdefault(key,[]).append(event)
        for (_,_,measure_id,_), notes in by_attack.items():
            leaders=[n for n in notes if not n.get("chord")]
            if len(leaders)!=1 or len(notes)<2:
                continue
            pattern=chord_pattern(leaders[0],notes,measures[measure_id])
            if pattern:
                assert pattern in known, (pattern,leaders[0]["id"])
                total += 1
            if any(n.get("id") ==
                    "pt2fa3797d60751961741d28759c09256as0" for n in notes):
                found = True
                assert pattern is not None, (notes,measure_id)
                assert pattern in known, pattern
                target_pattern = pattern
                target_model = model
    assert total > 0, "Ala has chords and must exercise the compound atlas"
    if found:
        atlas = chord_templates(target_model)
        assert target_pattern in atlas, (
            "Exact Ala chord ID could not be engraved by Verovio",
            target_pattern, list(atlas))
    else:
        # The source ID may be a lesson transformation. Nonetheless prove
        # that the original Ala passage containing measure 9 has a complete
        # authentic chord atlas, not just semantic pattern strings.
        section = next((p for p in piece.phrases
                        if p.first_bar <= 9 <= p.last_bar),None)
        assert section is not None, "Ala measure 9 must exist"
        notation = build_lesson_score(
            section, boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures,
            key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes)
        model = build_score_model(notation,boundaries=piece.bar_boundaries)
        requested = set(patterns_from_model(model))
        generated = chord_templates(model)
        assert requested <= set(generated), (
            "Verovio failed real Ala measure-9 chord patterns",
            requested-set(generated))



def _head(step, alter, octave):
    return {"staff":"right","note_type":"quarter","stem":None,
            "spelling":{"step":step,"alter":alter,"octave":octave}}


def test_augmented_unison_chord_has_a_pattern_and_authentic_two_head_sprite():
    # N1: Rachmaninoff Op. 3 No. 2 bar 3 holds E4, G4 and G#4 in one voice.
    # G and G-sharp share a staff position; Verovio engraves them side by side.
    from piano_teacher.notation.assets import chords
    notes = [_head("E",0,4), _head("G",0,4), _head("G",1,4)]
    measure = {"clefs":{"right":{"sign":"G","line":2}}}
    assert chord_pattern(notes[0],notes,measure) == "quarter|up|0,2,2"
    # G1: three heads on one position are a chord too; Verovio engraves it.
    triple = notes + [_head("G",-1,4)]
    assert chord_pattern(triple[0],triple,measure) == "quarter|up|0,2,2,2"
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom":"xml","scale":48,"pageWidth":900,
        "pageHeight":650,"svgViewBox":True,"adjustPageHeight":True,
        "svgBoundingBoxes":True,"svgContentBoundingBoxes":True})
    asset = chords._render(toolkit,"quarter|up|0,2,2")
    assert chords._valid_asset(asset,"quarter|up|0,2,2")
    (x0,y0),(x1,y1),(x2,y2) = asset["head_positions"]
    assert y1 == y2 and x1 != x2 and y0 > y1


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
    assert chord_pattern(notes[0], notes, measure) == "quarter|up|0,2,2"
    assert chords.chord_refusal(notes[0], notes, measure) is None
    model = {"measures": [measure], "notation_events": notes}
    assert chords.refused_chords(model) == []
    assert chords.patterns_from_model(model) == ["quarter|up|0,2,2"]


def test_only_input_that_is_not_one_chord_is_refused_with_its_cause():
    from piano_teacher.notation.assets import chords
    measure = {"number": 3, "clefs": {"right": {"sign": "G", "line": 2}}}
    mixed = [_head("C",0,4), {**_head("E",0,4), "note_type": "half"}]
    for index, note in enumerate(mixed):
        note.update(measure=3, id=f"m{index}", chord=index > 0)
    reason = chords.chord_refusal(mixed[0], mixed, measure)
    assert reason == ("measure 3, right staff: heads of different note values "
                      "are separate voices, not one chord")
    # Eleven heads, a five-octave span and stacked unisons all have a pattern.
    for names in (["C4","D4","E4","F4","G4","A4","B4","C5","D5","E5","F5"],
                  ["A0","C8"], ["G4","G4","G4","G4"]):
        heads = [_head(n[0], 0, int(n[1])) for n in names]
        assert chord_pattern(heads[0], heads, measure)


def test_every_corpus_chord_is_a_chord():
    """All 17 corpus MIDIs: no chord is refused at any lesson phrase."""
    from piano_teacher.music import load_midi
    from piano_teacher.notation.assets.chords import refused_chords
    from piano_teacher.notation.lesson import build_lesson_score
    from piano_teacher.notation.model import build_score_model

    pieces = sorted((ROOT / "midi").glob("*.midi"))
    assert len(pieces) == 17
    refused, chords = [], 0
    for path in pieces:
        piece = load_midi(path)
        for phrase in piece.phrases:
            score = build_lesson_score(
                phrase, boundaries=piece.bar_boundaries,
                time_signatures=piece.time_signatures,
                key_signatures=piece.key_signatures,
                clef_changes=piece.clef_changes)
            model = build_score_model(score, boundaries=piece.bar_boundaries)
            chords += len(patterns_from_model(model))
            refused += [f"{path.name}: {r}" for r in refused_chords(model)]
    assert chords > 0
    assert refused == []
