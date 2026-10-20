"""Native chord availability and fixed-beat readability regressions."""
from pathlib import Path

from piano_teacher.verovio_chord_templates import (
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
    from piano_teacher.lesson_score import build_lesson_score
    from piano_teacher.score_model import build_score_model

    piece = load_midi(ROOT/"midi/Ala_–_Joep_Beving.midi")
    from piano_teacher.verovio_chord_templates import chord_templates
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

