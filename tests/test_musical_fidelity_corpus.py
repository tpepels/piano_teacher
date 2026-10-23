"""Actual source files must survive the complete grading/engraving pipeline."""
from collections import Counter
from fractions import Fraction
from io import BytesIO
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import mido
import pytest

from piano_teacher.exercise_generator import generate_variants
from piano_teacher.feedback import project_assessment
from piano_teacher.lesson_score import build_lesson_score
from piano_teacher.lesson_validation import require_lesson_alignment
from piano_teacher.music import Phrase
from piano_teacher.practice import Assessment, NoteAssessment, PlayedNote, evaluate
from piano_teacher.raster import rasterize_score
from piano_teacher.score import import_piece, render_layout
from piano_teacher.score_geometry import locate_beat


CORPUS = Path(__file__).parent / "fixtures" / "musical_fidelity"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text())
SUPPORTED = MANIFEST["supported"]
UNSUPPORTED = MANIFEST["unsupported"]
AMBIGUOUS = MANIFEST["ambiguous"]


def number(value):
    return float(Fraction(str(value)))


def _event(note):
    return (note.start, note.end, note.pitch, note.hand)


def check_source_facts(case):
    """Compare imports with source facts, never with regenerated expectations."""
    piece, _ = import_piece(CORPUS / case["file"])
    expected = sorted((number(a), number(b), p, hand) for a, b, p, hand in case["notes"])
    actual = sorted(_event(note) for note in piece.notes)
    assert len(actual) == len(expected), f"{case['file']}: source attacks were lost or invented"
    for got, want in zip(actual, expected):
        assert got[:2] == pytest.approx(want[:2], abs=1e-10)
        assert got[2:] == want[2:]
    assert piece.bar_boundaries == pytest.approx([number(x) for x in case["bars"]], abs=1e-10)
    if "meters" in case:
        assert piece.time_signatures == tuple((number(beat), num, den) for beat, num, den in case["meters"])
    if "keys" in case:
        actual_keys = {(key.beat, key.fifths) for key in piece.key_signatures}
        assert actual_keys == {(number(beat), fifths) for beat, fifths in case["keys"]}
    for beat, pitch, step, alter, octave in case.get("source_spellings", []):
        note = next(n for n in piece.notes if n.start == number(beat) and n.pitch == pitch)
        assert note.spelling == (step, alter, octave)
    if case.get("distinct_voices"):
        assert len({note.voice for note in piece.notes}) >= 2
    return piece


def _assert_png(svg, path):
    """Rasterize the real SVG and establish that it contains actual score ink."""
    from PIL import Image
    path.with_suffix(".svg").write_text(svg)
    with Image.open(BytesIO(rasterize_score(svg))) as raster:
        assert raster.format == "PNG" and min(raster.size) >= 100
        # The production PNG is transparent. Composite its actual ink on white
        # for review and count visible ink rather than transparent black pixels.
        rendered = Image.new("RGBA", raster.size, "white")
        rendered.alpha_composite(raster.convert("RGBA"))
        rendered = rendered.convert("RGB")
        rendered.save(path)
        histogram = rendered.convert("L").histogram()
        assert sum(histogram[:100]) > 100, f"No visible score ink: {path}"
        return {"file": str(path), "width": rendered.width, "height": rendered.height,
                "dark_pixels": sum(histogram[:100])}


def check_pipeline(case, output=None):
    """Import → all generated hands/variants → real Verovio → grading/feedback."""
    piece = check_source_facts(case)
    ids = [note.source_id for note in piece.notes]
    assert all(ids), f"{case['file']}: imported attacks need canonical source IDs"
    assert len(set(ids)) == len(ids), f"{case['file']}: repeated/unison attacks share an ID"
    repeated, _ = import_piece(CORPUS / case["file"])
    assert [note.source_id for note in repeated.notes] == ids
    phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1, 0, piece.bar_boundaries[-1], piece.notes)
    source_by_id = {note.source_id: note for note in piece.notes}
    report = {"file": case["file"], "source_attacks": len(ids), "variants": [], "pngs": [],
              "source_notes": [{"source_id": n.source_id, "start": n.start, "end": n.end,
                                "pitch": n.pitch, "hand": n.hand, "voice": n.voice} for n in piece.notes]}
    for hand in (*sorted({n.hand for n in piece.notes}), "both"):
        for variant in generate_variants(phrase, hand):
            required = {n.source_id: n for n in variant.notes}
            assert len(required) == len(variant.notes)
            assert set(required) <= set(ids)
            for source_id, note in required.items():
                assert note == source_by_id[source_id], "Simplification changed a precise source event"
            score = build_lesson_score(variant.phrase, boundaries=piece.bar_boundaries,
                                      time_signatures=piece.time_signatures,
                                      key_signatures=piece.key_signatures, clef_changes=piece.clef_changes)
            engraved = render_layout(score, phrase.first_bar, phrase.last_bar, hand,
                                     total_beats=phrase.end, bpm=120)
            layout = engraved.layout
            assert layout.get("mapping_schema"), "Imported lessons must use strict source mappings"
            require_lesson_alignment(variant.phrase, layout, hand)
            glyphs = {glyph["id"]: glyph for glyph in layout["notes"]}
            assert len(glyphs) == len(layout["notes"]), "Two displayed glyphs share an ID"
            assert set(score.note_bindings) == set(glyphs), "Every emitted source binding needs a real notehead"
            attacks = [glyph for glyph in layout["notes"] if glyph["is_attack"]]
            assert Counter(g["source_id"] for g in attacks) == Counter(required.keys())
            assert set(layout["attack_map"]) == set(required)
            for source_id, note in required.items():
                glyph = glyphs[layout["attack_map"][source_id]]
                assert glyph["source_id"] == source_id and glyph["is_attack"] is True
                assert glyph["segment_index"] == 0
                assert glyph["pitch"] == note.pitch and glyph["hand"] == note.hand
                assert glyph["source_beat"] == pytest.approx(note.start - phrase.start, abs=1e-10)
                assert 0 <= glyph["page"] < len(engraved.pages)
                assert 0 <= glyph["x"] <= 1 and 0 <= glyph["y"] <= 1
                assert glyph["id"] in engraved.pages[glyph["page"]]
                if case.get("raw_timing"):
                    point = locate_beat(layout, note.start - phrase.start)
                    assert point["page"] == glyph["page"]
                    assert point["x"] == pytest.approx(glyph["x"], abs=1e-10)
                for continuation_id in layout["continuation_map"].get(source_id, []):
                    continuation = glyphs[continuation_id]
                    assert continuation["source_id"] == source_id and continuation["is_attack"] is False
                    assert continuation["pitch"] == note.pitch and continuation["hand"] == note.hand
                    assert continuation["source_beat"] == pytest.approx(note.start, abs=1e-10)
                    assert continuation["segment_index"] > 0
            assert all(g["source_id"] in required for g in layout["notes"])
            assert {item for values in layout["continuation_map"].values() for item in values} == {
                g["id"] for g in layout["notes"] if not g["is_attack"]}
            # Real evaluation consumes the precise imported events, not display qstamps.
            played = [PlayedNote(n.pitch, n.start * .5, n.end * .5) for n in variant.notes]
            assessment = evaluate(variant.phrase, hand, 120, played)
            assert assessment.clean and len(assessment.notes) == len(required)
            feedback = project_assessment(assessment, variant.phrase, 120, layout)
            assert feedback["unmapped"] == 0
            assert {mark["source_id"]: mark["note_id"] for mark in feedback["marks"]} == layout["attack_map"]
            # Distinct statuses on identical pitch/onset events must stay on their own staff/voice.
            annotated = Assessment(tuple(NoteAssessment(n, ("correct", "missed", "late")[i % 3])
                                         for i, n in enumerate(variant.notes)), 0)
            marks = project_assessment(annotated, variant.phrase, 120, layout)
            assert {m["source_id"]: m["status"] for m in marks["marks"]} == {
                entry.note.source_id: entry.status for entry in annotated.notes}
            xml = ET.fromstring(score.musicxml)
            if "keys" in case:
                assert {int(key.text) for key in xml.findall(".//key/fifths")} == {fifths for _, fifths in case["keys"]}
            for expected_hand, sign in case.get("clefs", {}).items():
                if any(n.hand == expected_hand for n in variant.notes):
                    part = xml.find(f"part[@id='{ 'RH' if expected_hand == 'right' else 'LH' }']")
                    assert part.findtext("measure/attributes/clef/sign") == sign
            for beat, pitch, step, alter, octave in case.get("display_spellings", []):
                matching = [binding_id for binding_id, binding in score.note_bindings.items()
                            if binding["is_attack"] and binding["source_beat"] == number(beat)
                            and binding["pitch"] == pitch]
                for binding_id in matching:
                    element = xml.find(f".//note[@id='{binding_id}']/pitch")
                    assert (element.findtext("step"), int(element.findtext("alter", "0")),
                            int(element.findtext("octave"))) == (step, alter, octave)
            if case.get("tuplet") and variant.level == "original":
                assert xml.findall(".//time-modification"), "Tuplets require explicit rational display durations"
            if hand == "both" and variant.level == "original":
                assert len(engraved.pages) >= case.get("minimum_pages", 1)
                if case.get("continuations"):
                    assert any(not g["is_attack"] for g in layout["notes"])
                if output is not None and case.get("raster"):
                    output.mkdir(parents=True, exist_ok=True)
                    (output / f"{Path(case['file']).stem}.layout.json").write_text(json.dumps(layout, indent=2) + "\n")
                    (output / f"{Path(case['file']).stem}.generated.musicxml").write_text(score.musicxml)
                    for page, svg in enumerate(engraved.pages):
                        report["pngs"].append(_assert_png(svg, output / f"{Path(case['file']).stem}-{page + 1}.png"))
            report["variants"].append({"hand": hand, "level": variant.level, "attacks": len(attacks),
                                       "glyphs": len(glyphs), "pages": len(engraved.pages),
                                       "attack_map": layout["attack_map"]})
    return report


@pytest.mark.parametrize("case", SUPPORTED, ids=lambda case: case["file"])
def test_actual_corpus_source_facts(case):
    check_source_facts(case)


@pytest.mark.parametrize("case", SUPPORTED, ids=lambda case: case["file"])
def test_actual_corpus_variants_engraving_evaluation_feedback(case, tmp_path):
    check_pipeline(case, tmp_path)


@pytest.mark.parametrize("case", UNSUPPORTED, ids=lambda case: case["file"])
def test_actual_corpus_rejects_ambiguous_or_unsupported_input(case):
    with pytest.raises(ValueError, match=case["error"]):
        import_piece(CORPUS / case["file"])


def check_ambiguous_source_facts(case):
    """Check raw endpoints and stated FIFO policy, never expected written XML."""
    source = CORPUS / case["file"]
    raw = mido.MidiFile(source)
    assert raw.ticks_per_beat == case["ticks_per_beat"]
    raw_attacks, raw_releases = Counter(), Counter()
    for track_index, track in enumerate(raw.tracks):
        tick = 0
        for ordinal, message in enumerate(track):
            tick += message.time
            if message.type not in ("note_on", "note_off"):
                continue
            key = (track_index, message.channel, message.note, tick)
            if message.type == "note_on" and message.velocity:
                raw_attacks[key + (message.velocity, f"midi-t{track_index}-e{ordinal}")] += 1
            else:
                raw_releases[key] += 1
    attacks = Counter((a["track"], a["channel"], a["pitch"], a["tick"],
                       a["velocity"], a["source_id"]) for a in case["attacks"])
    releases = Counter((r["track"], r["channel"], r["pitch"], r["tick"])
                       for r in case["releases"])
    assert raw_attacks == attacks
    assert raw_releases == releases
    piece, _ = import_piece(source)
    ppq = case["ticks_per_beat"]
    assert Counter((n.track, n.channel, n.pitch, n.start, n.velocity, n.source_id)
                   for n in piece.notes) == Counter(
        (track, channel, pitch, tick/ppq, velocity, identity)
        for track, channel, pitch, tick, velocity, identity in attacks.elements())
    assert Counter((n.track, n.channel, n.pitch, n.end) for n in piece.notes) == Counter(
        (track, channel, pitch, tick/ppq) for track, channel, pitch, tick in releases.elements())
    assert Counter((n.source_id, n.end) for n in piece.notes) == Counter(
        (identity, tick/ppq) for identity, tick in case["fifo_pairs"])
    assert len(piece.import_warnings) == case["overlapping_attacks"]
    assert all("Ambiguous" in w and "FIFO" in w and "not uniquely" in w
               for w in piece.import_warnings)
    return dict(file=case["file"], source_attacks=len(piece.notes),
                source_releases=sum(releases.values()), pairing_policy="fifo",
                import_warnings=list(piece.import_warnings))


@pytest.mark.parametrize("case", AMBIGUOUS, ids=lambda case: case["file"])
def test_actual_corpus_imports_ambiguous_fifo_without_dropping_endpoints(case):
    check_ambiguous_source_facts(case)


def test_manifest_classifies_every_source_once():
    listed = Counter(case["file"] for group in (SUPPORTED, UNSUPPORTED, AMBIGUOUS)
                     for case in group)
    sources = {path.name for path in CORPUS.iterdir()
               if path.suffix in (".mid", ".midi", ".musicxml", ".xml", ".mxl")}
    assert set(listed) == sources
    assert all(count == 1 for count in listed.values())


def test_imported_source_identity_is_independent_of_filesystem_path(tmp_path):
    source = CORPUS / "midi_parallel_unisons.mid"
    original, _ = import_piece(source)
    renamed = tmp_path / "an arbitrary user import.mid"
    shutil.copyfile(source, renamed)
    copied, _ = import_piece(renamed)
    assert all(n.source_id for n in original.notes)
    assert [n.source_id for n in original.notes] == [n.source_id for n in copied.notes]


@pytest.mark.parametrize("filename", ["midi_mixed_meter.mid", "midi_held_crossbar.mid", "xml_keys_spelling.musicxml"])
def test_actual_imported_later_measure_keeps_source_ids_and_local_beats(filename):
    case = next(case for case in SUPPORTED if case["file"] == filename)
    piece = check_source_facts(case)
    start, end = piece.bar_boundaries[1:3]
    notes = tuple(note for note in piece.notes if start <= note.start < end)
    phrase = Phrase(2, 2, 2, start, end, notes)
    score = build_lesson_score(phrase, boundaries=piece.bar_boundaries, time_signatures=piece.time_signatures,
                              key_signatures=piece.key_signatures, clef_changes=piece.clef_changes)
    layout = render_layout(score, 2, 2, "both", total_beats=end - start, bpm=120).layout
    require_lesson_alignment(phrase, layout, "both")
    assert set(layout["attack_map"]) == {note.source_id for note in notes}
    by_source = {glyph["source_id"]: glyph for glyph in layout["notes"] if glyph["is_attack"]}
    for note in notes:
        assert by_source[note.source_id]["source_beat"] == pytest.approx(note.start - start, abs=1e-10)
    played = [PlayedNote(n.pitch, (n.start - start) * .5, (n.end - start) * .5) for n in notes]
    assessment = evaluate(phrase, "both", 120, played)
    assert assessment.clean
    marks = project_assessment(assessment, phrase, 120, layout)
    assert marks["unmapped"] == 0 and len(marks["marks"]) == len(notes)
