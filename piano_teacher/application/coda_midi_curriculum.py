"""MIDI-domain Coda catalog, including all requests and explicit outcomes.

The pinned backend selects an excerpt and exposes unordered Score/Part/Voice,
dotted, chordified and x2/x4 slowdown alternatives. This adapter preserves
that inventory while the application chooses its own practice order. A no-op,
invalid author parameter or unsafe MIDI transformation is recorded rather
than silently mistaken for successfully reproduced Coda output.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..exercise_contracts import TempoMap, TempoSegment
from ..exercise_generator import ExerciseVariant
from ..exercise_pipeline import ExerciseStage
from ..lesson_settings import SETTINGS
from ..music import Phrase, Piece
from ..research.coda_midi_grid import midi_coda_quantization
from ..research.coda_midi_sparse import sparse_midi_coda
from ..research.coda_reference_exercises import original_coda_levels
from ..research.coda_author_catalog import (
    AUTHOR_SLOWDOWN_FACTORS, catalog_requests,
)


@dataclass(frozen=True)
class CodaHalfSpeed:
    """MIDI playback equivalent of the author's x2/x4 written slowdown.

    The learner's selected (ladder) BPM is divided by the factor, but a
    slow stage never sounds below the app's minimum tempo (owner decision
    2026-11-11). Transport, Listen and grading all read this one map.
    """
    factor: int = 2
    name: str = "coda-slowdown-tempo"

    def effective_bpm(self, bpm: float) -> float:
        if bpm <= 0 or self.factor not in AUTHOR_SLOWDOWN_FACTORS:
            raise ValueError("Coda slowdown factor must be 2 or 4 and BPM positive")
        return max(float(SETTINGS.minimum_bpm), float(bpm)/self.factor)

    def ladder_bpm(self, effective_bpm: float) -> float:
        """Selected BPM at which this stage sounds at effective_bpm."""
        return float(effective_bpm)*self.factor

    def generate(self, plan, bpm: float) -> TempoMap:
        return TempoMap(self.name, (
            TempoSegment(0.0, plan.duration_beats, self.effective_bpm(bpm)),
        ))


@dataclass(frozen=True)
class CodaMidiCatalogEntry:
    """One author-category result: never drop a requested operation.

    'inventory' is an untransformed Score/Part/Voice; 'generated' is a
    playable stage; 'unchanged' is a well-formed no-op; 'author-invalid'
    covers a known invalid upstream request, and 'unrepresentable'
    records a MIDI safety/capacity/ambiguity rejection with its reason.
    """
    category: str
    request: str
    voice: str | None
    status: str
    stage: ExerciseStage | None = None
    reason: str = ""
    changed_sources: tuple[str, ...] = ()


def _retimed(original: ExerciseVariant, timing, name: str) -> ExerciseStage | None:
    """Use source-indexed musical timing; reject event loss or bad windows."""
    if len(timing.events) != len(original.notes):
        raise ValueError("Coda lost source note ownership")
    phrase = original.phrase
    if abs(timing.duration_beats - (phrase.end - phrase.start)) > 1e-7:
        raise ValueError("Coda stage must retain its selected source length")
    altered = tuple(replace(
        note, start=phrase.start + event.exercise_start,
        end=phrase.start + event.exercise_end)
        for note, event in zip(original.notes, timing.events))
    if altered == original.notes:
        return None
    if (len({n.source_id for n in altered}) != len(altered) or
            {n.source_id for n in altered} !=
            {n.source_id for n in original.notes}):
        raise ValueError("Coda changed original MIDI attack identities")
    if any(n.start < phrase.start - 1e-7 or n.end > phrase.end + 1e-7 or
           n.end <= n.start for n in altered):
        raise ValueError("Coda exercise crosses the selected source passage")
    return ExerciseStage(
        ExerciseVariant(name, replace(phrase, notes=altered),
                        original.source_indices),
        transformed_rhythm=True)


def _first_meter(piece: Piece, beat: float) -> tuple[int, int]:
    """Use the meter active at the start of the requested excerpt."""
    meter = (4, 4)
    for start, numerator, denominator in sorted(piece.time_signatures):
        if start > beat + 1e-7:
            break
        meter = (numerator, denominator)
    return meter


def _excerpt_quantization(piece: Piece, phrase: Phrase) -> int:
    """Derive one common grid from ALL score parts, not the current hand.

    The original author computes quantization once on the score excerpt.
    The MIDI adaptation substitutes a lossless PPQ/GCD grid, but it must
    still share that grid across every part and voice.
    """
    source = tuple(n for n in piece.notes
                   if phrase.start - 1e-7 <= n.start < phrase.end - 1e-7)
    whole = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                   phrase.start, phrase.end, source)
    return midi_coda_quantization(piece, whole, compact=True, max_cells=None)


def midi_coda_catalog(piece: Piece, original: ExerciseVariant
                      ) -> tuple[CodaMidiCatalogEntry, ...]:
    """Inventory every source category, voice and requested transformation.

    The result is auditable for a complete mixed-hand MIDI excerpt as well
    as for the hand-specific teaching path. Unsafe author behavior is never
    represented as a successful result. See entries with non-success status.
    """
    if piece.source_format != "midi" or piece.source_musicxml:
        raise ValueError("Coda catalog requires imported MIDI")
    phrase = original.phrase
    boundaries = tuple(t for t in piece.bar_boundaries
                       if phrase.start - 1e-7 <= t <= phrase.end + 1e-7)
    if (len(boundaries) < 2 or
            abs(boundaries[0] - phrase.start) > 1e-7 or
            abs(boundaries[-1] - phrase.end) > 1e-7):
        raise ValueError("Coda excerpt needs complete MIDI measure boundaries")
    hierarchy = original_coda_levels(
        original, boundaries=boundaries, source_musicxml="")
    entries = [CodaMidiCatalogEntry(
        "Score Level", "original", None, "inventory", ExerciseStage(original))]
    parts = tuple(item for item in hierarchy if item.level == "part")
    voices = tuple(item for item in hierarchy if item.level == "voice")
    for part in parts:
        entries.append(CodaMidiCatalogEntry(
            "Part Level", part.hand, None, "inventory",
            ExerciseStage(part.variant)))
    if not voices:
        raise ValueError("Coda excerpt has no source voices")
    try:
        quantization = _excerpt_quantization(piece, phrase)
        grid_error = ""
    except ValueError as exc:
        quantization = None
        grid_error = str(exc)
    numerator, denominator = _first_meter(piece, phrase.start)
    for index, voice in enumerate(voices):
        # Preserve pre-existing short names for the ordinary single-voice
        # hand lesson; suffix when there are multiple independent voices.
        suffix = f"-voice-{index + 1}" if len(voices) > 1 else ""
        owner = f"{voice.hand}:{voice.voice}"
        entries.append(CodaMidiCatalogEntry(
            "Voice Level: Original", "original", owner, "inventory",
            ExerciseStage(ExerciseVariant(
                "coda-voice-original" + suffix, voice.variant.phrase,
                voice.variant.source_indices))))
        if quantization is None:
            for variant in ("dotted-long-short", "dotted-short-long",
                            "all-chord-widths"):
                category = ("Voice Level: Dotted" if variant.startswith("dotted")
                            else "Voice Level: Chordified")
                entries.append(CodaMidiCatalogEntry(
                    category, variant, owner, "unrepresentable",
                    reason=grid_error))
        else:
            for request in catalog_requests(
                    quantization, numerator, denominator):
                if request.category in (
                        "Voice Level: Original", "Voice Level: Slowed Down"):
                    continue
                name = "coda-" + request.variant + suffix
                if (request.category == "Voice Level: Chordified" and
                        (not isinstance(request.parameter, int)
                         or request.parameter <= 0)):
                    entries.append(CodaMidiCatalogEntry(
                        request.category, request.variant, owner,
                        "author-invalid", reason="Original Coda requested zero chord width"))
                    continue
                try:
                    if request.category == "Voice Level: Dotted":
                        result = sparse_midi_coda(
                            voice.variant, family="dotted",
                            quantization=quantization,
                            long_first=request.parameter == (1.5, 0.5))
                    elif request.category == "Voice Level: Chordified":
                        result = sparse_midi_coda(
                            voice.variant, family="chord",
                            quantization=quantization,
                            chord_width=request.parameter)
                    else:
                        raise ValueError("Unknown Coda catalog category")
                    stage = _retimed(voice.variant, result.timing, name)
                    entries.append(CodaMidiCatalogEntry(
                        request.category, request.variant, owner,
                        "generated" if stage is not None else "unchanged",
                        stage, changed_sources=result.changed_sources))
                except ValueError as exc:
                    entries.append(CodaMidiCatalogEntry(
                        request.category, request.variant, owner,
                        "unrepresentable", reason=str(exc)))
        for factor in AUTHOR_SLOWDOWN_FACTORS:
            entries.append(CodaMidiCatalogEntry(
                "Voice Level: Slowed Down", f"slow-x{factor}", owner,
                "generated", ExerciseStage(ExerciseVariant(
                    f"coda-slowdown-x{factor}" + suffix,
                    voice.variant.phrase, voice.variant.source_indices),
                    tempo_policy=CodaHalfSpeed(factor=factor))))
    return tuple(entries)


def midi_coda_stages(
    piece: Piece, variants: tuple[ExerciseVariant, ...], *,
    kind: str,
) -> tuple[ExerciseStage, ...]:
    """Turn the source-author catalog into ordered, ordinary lesson stages.

    A mixed-hand learning lesson is Score Level: individual Part/Voice
    catalogs occur in the existing RH/LH hand lessons, not as duplicated
    or mixed-voice dotted stages in the both-hands route.
    """
    if piece.source_format != "midi" or piece.source_musicxml:
        raise ValueError("Coda exercises need imported MIDI notes")
    if not variants:
        return ()
    original = variants[-1]
    if original.level != "original":
        raise ValueError("Coda lesson must end with original MIDI notes")
    if kind != "learn" or len({n.hand for n in original.notes}) > 1:
        return (ExerciseStage(original, origin="original", technique="original",
                              display_name="Original notes and rhythm"),)
    entries = midi_coda_catalog(piece, original)
    stages = []
    used_levels: set[str] = set()
    for entry in entries:
        stage = entry.stage
        if stage is None:
            continue
        if entry.category == "Voice Level: Original":
            if stage.variant.notes == original.notes:
                continue
        elif entry.category not in (
                "Voice Level: Dotted", "Voice Level: Chordified",
                "Voice Level: Slowed Down"):
            continue
        if entry.status not in ("generated", "inventory"):
            continue
        if stage.variant.level in used_levels:
            raise ValueError("Duplicate Coda exercise level")
        used_levels.add(stage.variant.level)
        if entry.category == "Voice Level: Dotted":
            kind_name = ("dotted-long-short" if entry.request == "dotted-long-short"
                         else "dotted-short-long")
            readable = ("Long–short rhythm" if kind_name == "dotted-long-short"
                        else "Short–long rhythm")
        elif entry.category == "Voice Level: Chordified":
            kind_name, readable = "chordified", "Chordified rhythm"
        elif entry.category == "Voice Level: Slowed Down":
            kind_name, readable = "slowdown", "Slowed playback"
        else:
            kind_name, readable = "voice", "Isolated source voice"
        # This metadata belongs to the author adapter, not the shared
        # selection policy, notation renderer or UI.
        stages.append(replace(stage, origin="coda-midi",
                              technique=kind_name, display_name=readable))
    stages.append(ExerciseStage(original, origin="original",
                                technique="original",
                                display_name="Original notes and rhythm"))
    return tuple(stages)
