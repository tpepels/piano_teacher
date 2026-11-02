"""Execute pinned Coda algorithms on *MIDI-derived* matrices, compare attacks.

No MusicXML source is required: the original Coda source methods receive a
MIDI/PPQ-exact piano roll, onset map and duration matrix as their MMR. The
author's original exercise code executes unchanged; only its unused DB
initializer is stubbed. Output is normalized to sounding MIDI notes, with
written tie continuations merged, so engraving artifacts do not affect parity.

This is a diagnostic with exhaustive per-request outcomes, NOT a parity
certificate. --strict deliberately fails on all unmatched or untested cases.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import types

from piano_teacher.application.coda_midi_curriculum import (
    midi_coda_catalog, _excerpt_quantization, _first_meter,
)
from piano_teacher.exercise_generator import ExerciseVariant
from piano_teacher.music import Phrase, load_midi
from piano_teacher.research.coda_matrix import MatrixScore
from piano_teacher.research.coda_reference_matrix import score_voice_matrices
from piano_teacher.research.coda_differential import (
    written_from_music21, sounding_from_written,
)
from piano_teacher.research.coda_author_catalog import AUTHOR_REVISION

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests/fixtures/musical_fidelity"
MANIFEST = CORPUS / "manifest.json"


def canonical(notes, *, offset=0.0, scale=1.0):
    return tuple(sorted((n.pitch, round((n.start - offset) / scale, 6),
                         round((n.end - offset) / scale, 6))
                        for n in notes))


def canonical_author(stream, *, scale=1.0):
    written = written_from_music21(stream)
    sounded, tie_errors = sounding_from_written(written)
    return (tuple(sorted((n.pitch, round(n.onset / scale, 6),
                          round(n.end / scale, 6))
                         for n in sounded)), tie_errors)


def timing_equivalent(expected, actual, *, tolerance=0.000002):
    """Ignore sub-PPQ export rounding, never ignore pitch or note loss."""
    return (len(expected) == len(actual) and
            all(a[0] == b[0] and
                abs(a[1] - b[1]) <= tolerance and
                abs(a[2] - b[2]) <= tolerance
                for a, b in zip(expected, actual)))


def invalid_author_chord(events):
    """The paper's playable-blocked-chord bound is five simultaneous tones.

    The author's backend checks onset COUNT, and can export a six-note
    chord from just two original simultaneous note attacks.
    """
    by_onset = {}
    for pitch, onset, end in events:
        by_onset.setdefault(onset, []).append(pitch)
    return any(len(values) > 5 for values in by_onset.values())


def _original_line(voice_matrix, *, q, numerator, denominator, classes):
    ExerciseLine, MusicMatrixRepresentation, key, meter = classes
    line = ExerciseLine.__new__(ExerciseLine)
    line.quantization = q
    line.key_signature = key.KeySignature(0)
    line.time_signature = meter.TimeSignature(f"{numerator}/{denominator}")
    line.original_stream = None
    # Copy arrays so an author transformation cannot mutate our oracle input.
    line.music_matrix_representation = MusicMatrixRepresentation(
        line.key_signature, line.time_signature, q,
        voice_matrix.piano_roll.copy(), voice_matrix.onset_map.copy(),
        voice_matrix.durations_matrix.copy())
    return line


def _call_author(line, request: str):
    if request.startswith("dotted-"):
        pattern = ([1.5, 0.5] if request == "dotted-long-short"
                   else [0.5, 1.5])
        return line.generate_dotted_exercise(pattern)
    if request.startswith("chord-"):
        return line.generate_chordify_exercise(int(request[6:]))
    if request.startswith("slow-x"):
        return line.generate_slowed_down_exercise(int(request[6:]))
    raise ValueError("Unknown author transformation: " + request)


def compare_piece(path: Path, classes) -> dict:
    row = {"file": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
           "status": "compared", "cases": []}
    try:
        piece = load_midi(path)
        phrase = Phrase(1, 1, len(piece.bar_boundaries) - 1,
                        piece.bar_boundaries[0], piece.bar_boundaries[-1],
                        piece.notes)
        original = ExerciseVariant(
            "original", phrase, tuple(range(len(piece.notes))))
        catalog = midi_coda_catalog(piece, original)
        q = _excerpt_quantization(piece, phrase)
        meter = _first_meter(piece, phrase.start)
        source = MatrixScore.from_phrase(
            phrase, boundaries=piece.bar_boundaries, source_musicxml="")
        matrices = score_voice_matrices(source, quantization=q)
        grouped = {}
        for part in source.parts:
            for voice in part.voices:
                key = f"{part.hand}:{voice.name}"
                matching = [m for m in matrices
                            if m.hand == part.hand and m.voice == voice.name]
                if len(matching) != 1 or key in grouped:
                    raise ValueError("MIDI source voice ownership is ambiguous")
                grouped[key] = (voice, matching[0])
        row["source_attacks"] = len(piece.notes)
        row["voices"] = len(grouped)
        row["quantization"] = q
        row["meter"] = list(meter)
        row["inventory"] = [
            {"category": item.category, "request": item.request,
             "voice": item.voice}
            for item in catalog if item.status == "inventory"]
        for item in catalog:
            if item.status == "inventory":
                continue
            voice, matrix = grouped[item.voice]
            src_indices = {i for a in voice.attacks for i in a.source_indices}
            src_notes = tuple(phrase.notes[i] for i in sorted(src_indices))
            ref_line = _original_line(matrix, q=q, numerator=meter[0],
                                      denominator=meter[1], classes=classes)
            result = {"category": item.category, "voice": item.voice,
                      "request": item.request,
                      "adapter_status": item.status}
            if item.reason:
                result["adapter_reason"] = item.reason
            try:
                author = _call_author(ref_line, item.request)
            except Exception as exc:
                result["status"] = "author-exception"
                result["reason"] = f"{type(exc).__name__}: {exc}"
                row["cases"].append(result)
                continue
            if author is None:
                result["status"] = "author-none"
                row["cases"].append(result)
                continue
            try:
                factor = (int(item.request[6:]) if
                          item.request.startswith("slow-x") else 1)
                actual, tie_errors = canonical_author(author, scale=factor)
                source_expected = canonical(src_notes, offset=phrase.start)
                if item.stage is not None and factor == 1:
                    expected = canonical(item.stage.variant.notes,
                                         offset=phrase.start)
                else:
                    expected = source_expected
                source_pitches = Counter(x[0] for x in source_expected)
                output_pitches = Counter(x[0] for x in actual)
                if tie_errors or source_pitches != output_pitches:
                    result["status"] = "author-invalid"
                    result["reason"] = (
                        "disconnected written ties or loss/duplication of "
                        "original sounding note attacks")
                    result["tie_errors"] = [str(e) for e in tie_errors][:5]
                elif (item.category == "Voice Level: Chordified" and
                      invalid_author_chord(actual)):
                    result["status"] = "author-invalid"
                    result["reason"] = (
                        "Original emits blocked chord with more than five "
                        "simultaneous sounding tones")
                elif item.status == "unrepresentable":
                    result["status"] = "adapter-unrepresentable"
                elif actual == expected:
                    result["status"] = "exact-midi"
                elif timing_equivalent(expected, actual):
                    result["status"] = "rounding-equivalent"
                else:
                    result["status"] = "mismatch"
                if result["status"] not in ("exact-midi", "rounding-equivalent"):
                    result["author_events"] = actual[:12]
                    result["adapter_events"] = expected[:12]
                    result["source_events"] = source_expected[:12]
            except Exception as exc:
                result["status"] = "comparison-error"
                result["reason"] = f"{type(exc).__name__}: {exc}"
            row["cases"].append(result)
        requested = [item for item in catalog if item.status != "inventory"]
        if len(requested) != len(row["cases"]):
            raise AssertionError("MIDI author catalog lost a transformation request")
    except Exception as exc:
        row["status"] = "source-rejected"
        row["reason"] = f"{type(exc).__name__}: {exc}"
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    backend = args.upstream.resolve()
    if not (backend / "music/exercise.py").is_file():
        raise ValueError("Pinned original backend not available")
    module = types.ModuleType("services.database")
    module.MongoDatabase = type("NoDatabase", (), {"__init__": lambda self: None})
    sys.modules["services.database"] = module
    sys.path.insert(0, str(backend))
    from music21 import key, meter
    from music.exercise import ExerciseLine, MusicMatrixRepresentation
    classes = (ExerciseLine, MusicMatrixRepresentation, key, meter)

    data = json.loads(MANIFEST.read_text())
    files = sorted(item["file"] for item in data["supported"]
                   if item["file"].lower().endswith((".mid", ".midi")))
    rows = [compare_piece(CORPUS / path, classes) for path in files]
    counts = Counter(item["status"] for row in rows for item in row["cases"])
    report = {
        "reference_revision": AUTHOR_REVISION,
        "source_input": "raw MIDI", "author_algorithm_input": "MIDI-derived MMR",
        "comparison": "sounding pitch, onset, end (slowdown normalized by factor)",
        "source_files": len(rows),
        "source_rejected": sum(row["status"] != "compared" for row in rows),
        "requests": sum(len(row["cases"]) for row in rows),
        "outcomes": dict(sorted(counts.items())),
        "cases": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"},
                     sort_keys=True))
    if args.strict and (report["source_rejected"] or
                        counts["mismatch"] or counts["adapter-unrepresentable"] or
                        counts["comparison-error"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
