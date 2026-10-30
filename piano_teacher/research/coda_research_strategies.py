"""Source-traceable Coda exercise experiments, isolated from live strategies.

These methods implement documented *categories*, not reference-equivalent
algorithms. No research-fidelity claim without the full Coda specification.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from xml.etree import ElementTree as ET

from ..exercise_contracts import (
    OriginalTiming, TempoMap, TempoSegment, TimingPlan,
)
from ..exercise_generator import ExerciseVariant
from ..music import Phrase
from ..notation.rhythm_safety import (
    rhythm_protected_source_ids, slur_endpoint_source_ids, beamed_source_ids,
)
from .coda_matrix import MatrixScore, MatrixAttack, MatrixVoice


def _source_protection(xml: str) -> frozenset[str]:
    if not xml:
        return frozenset()
    return frozenset().union(
        rhythm_protected_source_ids(xml),
        slur_endpoint_source_ids(xml), beamed_source_ids(xml),
    )


def _is_safe_cut(matrix: MatrixScore, beat: float) -> bool:
    # A sounded note held across the boundary must not disappear on the
    # subsequent passage. Tied notes have been merged by the importer.
    if any(note.start < beat - 1e-7 and note.end > beat + 1e-7
           for note in matrix.phrase.notes):
        return False
    # Distinct source voice/pitch/part arcs (and unresolved partial
    # windows) decide whether a MusicXML measure boundary is cuttable.
    # Do not infer links from nearest pitched attacks or native engraving.
    return not any(link.crosses(beat) for link in matrix.source_connectors())

@dataclass(frozen=True)
class ResearchPassage:
    """One source measure interval and its selected attack mapping."""
    variant: ExerciseVariant
    matrix: MatrixScore


@dataclass(frozen=True)
class ResearchPartSplitter:
    """Split into aligned source-measure passages without severing ties/slurs."""

    measures_per_passage: int = 1
    name: str = "coda-research-measure-parts"

    def split(self, variant: ExerciseVariant, *, boundaries: tuple[float, ...],
              source_musicxml: str = "") -> tuple[ResearchPassage, ...]:
        if self.measures_per_passage <= 0:
            raise ValueError("measures_per_passage must be positive")
        source = MatrixScore.from_phrase(
            variant.phrase, boundaries=boundaries, source_musicxml=source_musicxml)
        grid = source.boundaries
        if len(grid) != variant.phrase.last_bar - variant.phrase.first_bar + 2:
            raise ValueError("Incomplete source measure grid")
        intervals = [(i, min(i+self.measures_per_passage, len(grid)-1))
                     for i in range(0, len(grid)-1, self.measures_per_passage)]
        cuts = [grid[stop] for _, stop in intervals[:-1]]
        if any(not _is_safe_cut(source, cut) for cut in cuts):
            raise ValueError("Source tie/slur or sustained note crosses passage boundary")
        parts = []
        phrase = variant.phrase
        for start, stop in intervals:
            first, end = grid[start], grid[stop]
            kept = [i for i, note in enumerate(phrase.notes)
                    if first-1e-7 <= note.start < end-1e-7]
            subphrase = Phrase(phrase.number, phrase.first_bar+start,
                               phrase.first_bar+stop-1, first, end,
                               tuple(phrase.notes[i] for i in kept))
            subset = ExerciseVariant(
                f"coda-research-bars-{subphrase.first_bar}-{subphrase.last_bar}",
                subphrase, tuple(variant.source_indices[i] for i in kept))
            parts.append(ResearchPassage(subset, MatrixScore.from_phrase(
                subphrase, boundaries=grid[start:stop+1],
                source_musicxml=source_musicxml)))
        return tuple(parts)


@dataclass(frozen=True)
class ResearchTempoShaper:
    """Measure-level tempo steps over a shared TempoMap, not Coda parity."""

    slow_fraction: float = .65
    reverse: bool = False
    name: str = "coda-research-tempo-steps"

    def generate(self, plan: TimingPlan, target_bpm: float, *,
                 boundaries: tuple[float, ...]) -> TempoMap:
        if (not isfinite(target_bpm) or target_bpm <= 0
                or not isfinite(self.slow_fraction)
                or not 0 < self.slow_fraction <= 1):
            raise ValueError("Invalid shaping parameters")
        source = plan.original.phrase
        grid = MatrixScore.from_phrase(
            source, boundaries=boundaries).boundaries
        if len(grid) != source.last_bar - source.first_bar + 2:
            raise ValueError("Incomplete source measure grid")
        local = tuple(value - source.start for value in grid)
        # A held source attack can legitimately extend the phrase. Tempo
        # shaping must still cover the full transformed TimingPlan.
        if plan.duration_beats > local[-1] + 1e-7:
            local += (plan.duration_beats,)
        length = len(local)-1
        segments = []
        for i, (a,b) in enumerate(zip(local, local[1:])):
            fraction = 1 if length == 1 else (
                i if not self.reverse else length-1-i) / (length-1)
            bpm = target_bpm*(self.slow_fraction
                              + (1-self.slow_fraction)*fraction)
            segments.append(TempoSegment(a,b,bpm))
        return TempoMap(self.name, tuple(segments))


@dataclass(frozen=True)
class DottedDecision:
    voice: str
    measure: int
    first_source_ids: tuple[str, ...]
    second_source_ids: tuple[str, ...]


@dataclass(frozen=True)
class DottedResult:
    timing: TimingPlan
    decisions: tuple[DottedDecision, ...]


@dataclass(frozen=True)
class ResearchPolyphonicDottedRhythm:
    """Per-voice 3:1 or 1:3 rhythm pairs, with source-notation safeguards."""

    long_first: bool = True

    @property
    def name(self) -> str:
        return ("coda-research-dotted-long-short" if self.long_first
                else "coda-research-dotted-short-long")

    def transform(self, variant: ExerciseVariant, *,
                  boundaries: tuple[float, ...] = (),
                  source_musicxml: str = "") -> DottedResult:
        matrix = MatrixScore.from_phrase(
            variant.phrase, boundaries=boundaries,
            source_musicxml=source_musicxml)
        if len(matrix.boundaries) != (variant.phrase.last_bar -
                                     variant.phrase.first_bar + 2):
            raise ValueError("Incomplete source measure grid")
        original = OriginalTiming().transform(variant)
        protected = _source_protection(source_musicxml)
        # Authored slurs/ties also protect *interior* source notes. Endpoint
        # guards alone can silently alter a middle phrase under one curve.
        protected = (protected | matrix.connector_protected_source_ids()
                     | matrix.context_protected_source_ids())
        # Unprojected expressive notation would not survive arbitrary
        # retiming. Treat its source attacks as ineligible too.
        for source in matrix.notation_elements:
            if source.kind != "note":
                continue
            node = ET.fromstring(source.xml)
            if (node.find("{*}notations") is not None or
                    node.find("{*}beam") is not None or
                    node.find("{*}time-modification") is not None):
                protected = protected.union((source.source_id,))
        events = list(original.events)
        decisions = []
        for part in matrix.parts:
            for voice in part.voices:
                for i in range(0, len(voice.attacks)-1, 2):
                    a, b = voice.attacks[i:i+2]
                    if not self._eligible(matrix, voice, a, b, protected):
                        continue
                    duration = b.onset-a.onset
                    first_duration = duration * (1.5 if self.long_first else .5)
                    origin = variant.phrase.start
                    for index in a.source_indices:
                        e = events[index]
                        events[index] = replace(
                            e, exercise_end=a.onset-origin+first_duration)
                    for index in b.source_indices:
                        e = events[index]
                        events[index] = replace(
                            e, exercise_start=a.onset-origin+first_duration,
                            exercise_end=a.onset-origin+2*duration)
                    decisions.append(DottedDecision(
                        voice.name, a.measure, a.source_ids, b.source_ids))
        return DottedResult(
            TimingPlan(self.name, variant, tuple(events),
                       original.duration_beats), tuple(decisions))

    @staticmethod
    def _eligible(matrix: MatrixScore, voice: MatrixVoice,
                  a: MatrixAttack, b: MatrixAttack,
                  protected: frozenset[str]) -> bool:
        if a.measure != b.measure or protected.intersection(
                (*a.source_ids, *b.source_ids)):
            return False
        durations = (*[end-a.onset for end in a.ends],
                     *[end-b.onset for end in b.ends])
        if (not durations or max(durations)-min(durations) > 1e-7
                or abs((b.onset-a.onset)-durations[0]) > 1e-7):
            return False
        duration = durations[0]
        bar = a.measure-matrix.phrase.first_bar
        if b.onset+duration > matrix.boundaries[bar+1]+1e-7:
            return False
        if any(rest.onset < b.onset+duration-1e-7
               and rest.end > a.onset+1e-7 for rest in voice.written_rests):
            return False
        return True
