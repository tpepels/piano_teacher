"""Progressive, source-bound Coda/Fukuda teaching over an imported MIDI piece.

Full original Coda remains an independent research strategy. This product
curriculum deliberately selects short, complete MIDI passages, exercises and
error-appropriate stages from both generator families. No additional clock,
renderer, MIDI grader or persistence system is introduced.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import replace
from typing import Mapping, Protocol

from .exercise_generator import ExerciseVariant
from .exercise_pipeline import ExerciseStage
from .fukuda_midi import as_fukuda_stage
from .lesson_settings import SETTINGS
from .lesson_source_planner import Exercise, _focus_phrases, _hands_for_learning
from .music import Phrase, Piece


class _SourceAttackIndex:
    """One source-order-preserving index for repeated passage range queries.

    The long Hanon score previously re-scanned every source note for each
    passage, seam and consolidation candidate. Sorting once by attack
    position bounds each query to the notes actually inside that passage.
    Returned tuples retain the original source note order and identities.
    """

    def __init__(self, piece: Piece):
        self._notes = piece.notes
        onsets = sorted((note.start, index)
                        for index, note in enumerate(piece.notes))
        self._starts = tuple(start for start, _ in onsets)
        self._indices = tuple(index for _, index in onsets)

    def notes_in(self, start: float, end: float) -> tuple:
        low = bisect_left(self._starts, start)
        high = bisect_left(self._starts, end)
        return tuple(self._notes[i] for i in sorted(self._indices[low:high]))

    def crossing(self, start: float, end: float) -> bool:
        return any(note.end > end + 1e-7
                   for note in self.notes_in(start, end - 1e-7))


def _segments(piece: Piece, *, source: _SourceAttackIndex | None = None) -> tuple[Phrase, ...]:
    """Focus in two-bar units; join sections if a note sustains over the cut.

    The segmentation respects original measure boundaries and never crops or
    invents a MIDI attack/release. Entirely silent introductory bars are left
    for the last full-score performance.
    """
    source = source if source is not None else _SourceAttackIndex(piece)
    base = _focus_phrases(piece)
    if not base:
        raise ValueError("Hybrid curriculum needs at least one playable passage")
    grid = piece.bar_boundaries
    bars = len(grid) - 1
    groups = []
    i = 0
    while i < len(base):
        first, last = base[i].first_bar, base[i].last_bar
        # Find a safe source cut. If the last note crosses into the following
        # bar, it belongs to this lesson, including its complete duration.
        while True:
            boundary = grid[last]
            if not source.crossing(grid[first - 1], boundary):
                break
            if last == bars:
                break
            last += 1
        # Other focus units subsumed by a held source note are merged.
        while i + 1 < len(base) and base[i + 1].first_bar <= last:
            i += 1
            last = max(last, base[i].last_bar)
            # The enlarged section might also cross another held note.
            while last < bars and source.crossing(
                    grid[first - 1], grid[last]):
                last += 1
        start, end = grid[first - 1], grid[last]
        selected = source.notes_in(start - 1e-7, end - 1e-7)
        if selected:
            # Some MIDI files end their measure grid before the final
            # sounding key-off. Keep the release in the lesson timeline.
            end = max(end, max(n.end for n in selected))
            groups.append(Phrase(
                len(groups) + 1, first, last, start, end, selected))
        i += 1
    return tuple(groups)


def _course_exercises(piece: Piece) -> tuple[Exercise, ...]:
    source = _SourceAttackIndex(piece)
    passages = _segments(piece, source=source)
    out = []
    for i, phrase in enumerate(passages):
        ex = Exercise("learn", phrase,
                      f"hybrid:learn:{phrase.first_bar}-{phrase.last_bar}")
        out.append(ex)
        if i == 0:
            continue
        previous = passages[i - 1]
        if previous.last_bar + 1 != phrase.first_bar:
            continue
        # Boundary connection: two authored measures from either side,
        # introduced once the preceding phrase has been learned.
        first_bar = max(previous.first_bar, previous.last_bar - 1)
        last_bar = min(phrase.last_bar, phrase.first_bar + 1)
        start, end = piece.bar_boundaries[first_bar - 1], piece.bar_boundaries[last_bar]
        joined = source.notes_in(start, end)
        if (any(n.start < phrase.start for n in joined)
                and any(n.start >= phrase.start for n in joined)
                and all(n.end <= end + 1e-7 for n in joined)
                and len({round(n.start, 6) for n in joined})
                    <= SETTINGS.focus_max_attacks):
            out.insert(len(out) - 1, Exercise(
                "connect", Phrase(0, first_bar, last_bar, start, end, joined),
                f"hybrid:connect:{first_bar}-{last_bar}"))
        # Hierarchical consolidation: after two, four and eight adjacent
        # focus passages, practise their full original notes together.
        # Only source-safe contiguous ranges participate, and a seam drill
        # with identical content is not duplicated.
        for size in (2, 4, 8):
            if (i + 1) % size or i + 1 < size:
                continue
            group = passages[i + 1 - size:i + 1]
            if any(a.last_bar + 1 != b.first_bar
                   for a, b in zip(group, group[1:])):
                continue
            first_bar, last_bar = group[0].first_bar, group[-1].last_bar
            start = piece.bar_boundaries[first_bar - 1]
            end = piece.bar_boundaries[last_bar]
            selected = source.notes_in(start - 1e-7, end - 1e-7)
            if not selected or any(n.end > end + 1e-7 for n in selected):
                continue
            # Avoid offering the same measure range twice as a connector.
            if any(ex.kind == "connect"
                   and ex.phrase.first_bar == first_bar
                   and ex.phrase.last_bar == last_bar for ex in out):
                continue
            out.append(Exercise(
                "connect", Phrase(0, first_bar, last_bar, start, end, selected),
                f"hybrid:join:{size}:{first_bar}-{last_bar}"))
    last = len(piece.bar_boundaries) - 1
    complete = Phrase(
        0, 1, last, piece.bar_boundaries[0],
        max(piece.bar_boundaries[-1], max(n.end for n in piece.notes)),
        piece.notes)
    out.append(Exercise("perform", complete, "perform:all"))
    return tuple(out)


class PassageContributor(Protocol):
    """A generator capable of supplying stages for a selected MIDI passage."""
    @property
    def name(self) -> str: ...
    def passage_stages(self, piece: Piece, original: ExerciseVariant, *,
                       kind: str) -> tuple[ExerciseStage, ...]: ...


def compile_hybrid_catalog(
    piece: Piece, *, components: tuple[PassageContributor, ...] | None = None,
    name: str = "coda-fukuda-midi",
):
    """Compile independent contributor stages once, then select via feedback.

    The composer owns segmentation, not any generator. Adding a MIDI
    algorithm requires a passage_stages method and source-safe terminal
    original notes; the catalog compiler contains no author-name branches.
    """
    from .lesson_generators import LessonPlanDefinition, lesson_hands
    if components is None:
        from .lesson_generators import (
            CodaLessonGenerator, FukudaMidiLessonGenerator)
        components = (FukudaMidiLessonGenerator(), CodaLessonGenerator())
    if not components or len({component.name for component in components}) != len(components):
        raise ValueError("Adaptive composition requires unique passage contributors")
    if (piece.source_format != "midi" or piece.source_musicxml
            or piece.midi_ticks_per_beat <= 0):
        raise ValueError("Hybrid lessons require imported MIDI with PPQ")
    exercises = _course_exercises(piece)
    stages = {}
    for exercise in exercises:
        for hand in lesson_hands(exercise):
            selected = tuple((i, n) for i, n in enumerate(exercise.phrase.notes)
                             if hand == "both" or n.hand == hand)
            original = ExerciseVariant(
                "original", replace(exercise.phrase,
                                    notes=tuple(n for _, n in selected)),
                tuple(i for i, _ in selected))
            if exercise.kind != "learn":
                stages[(exercise.key, hand)] = (as_fukuda_stage(original),)
                continue
            produced = []
            for component in components:
                stages_for_passage = component.passage_stages(
                    piece, original, kind=exercise.kind)
                if (not stages_for_passage or
                        stages_for_passage[-1].variant.level != "original" or
                        Counter(stages_for_passage[-1].variant.notes) !=
                        Counter(original.notes)):
                    raise ValueError(
                        "Passage contributor must end in the exact original MIDI")
                produced.extend(stages_for_passage[:-1])
            variants = (*produced, as_fukuda_stage(original))
            levels = [stage.variant.level for stage in variants]
            if len(set(levels)) != len(levels):
                raise ValueError("Adaptive passage contributors collide on stage names")
            stages[(exercise.key, hand)] = variants
    return LessonPlanDefinition(
        exercises, stages, name,
        requires_unique_source_ids=True)


def _reduction_relevance(stage: ExerciseStage, original: ExerciseStage,
                      affected_source_ids: frozenset[str]) -> tuple[int, float] | None:
    """Prefer simplifications of the failed notes or their immediate context.

    A rule operating on an unrelated chord in the same passage would produce
    a valid MIDI exercise but teach the wrong difficulty. Score once from
    actual *removed* source attacks; never infer relevance from a shared pitch.
    """
    if not affected_source_ids:
        return None
    source = {n.source_id: n for n in original.variant.notes}
    removed = set(source) - {n.source_id for n in stage.variant.notes}
    if not removed:
        return None
    failed = tuple(source[sid] for sid in affected_source_ids if sid in source)
    if not failed:
        return None
    distance = min(abs(source[sid].start - n.start)
                   for sid in removed for n in failed)
    if distance > 2.0 + 1e-7:
        return None
    # A direct reduction of the actually failed note is preferred to a
    # general neighboring reduction, independent of the contributor's name.
    return (0 if removed & affected_source_ids else 1, distance)


def _selection(candidates: tuple[ExerciseStage, ...],
               evidence: Mapping[str, str], *, kind: str
               ) -> tuple[ExerciseStage, ...]:
    """Choose genuinely changed stages using measured source-note differences.

    The complete immutable Coda/Fukuda catalog remains available for
    research. The desktop teaching path cannot include unchanged aliases
    or multiple stages with identical audible performances.
    """
    if kind != "learn" or len(candidates) < 2:
        return candidates
    from .lesson_stage_semantics import teaching_sequence
    original = candidates[-1]
    pitch_ids = frozenset(sid for sid, status in evidence.items()
                          if status in {"wrong", "missed", "pitch"})
    if pitch_ids:
        # Every reduction contributor uses the same source-ID relevance
        # constraint. No future algorithm must add a special-case branch:
        # reductions unrelated to the failed notes are excluded, while
        # genuine rhythm and tempo exercises remain available.
        from .lesson_stage_semantics import difference
        ranked = sorted((
            (relevance, index, stage)
            for index, stage in enumerate(candidates[:-1])
            if difference(stage, original).removed > 0
            if (relevance := _reduction_relevance(
                stage, original, pitch_ids)) is not None
        ), key=lambda row: (*row[0], row[1]))
        candidates = (
            *(stage for _, _, stage in ranked),
            *(stage for stage in candidates[:-1]
              if difference(stage, original).removed == 0),
            original,
        )
    return teaching_sequence(candidates, evidence=dict(evidence))



def select_hybrid_stages(catalog, evidence: Mapping[str, str]):
    """Select lesson exercises from graded source notes, retaining stable keys.

    The stage selection policy is deliberately independent of the app/UI.
    Exact original MIDI attacks remain the final stage for every hand,
    every passage, and the complete final performance.
    """
    from .lesson_generators import LessonPlanDefinition, lesson_hands
    stages = {}
    for ex in catalog.exercises:
        for hand in lesson_hands(ex):
            source = (n for n in ex.phrase.notes
                      if hand == "both" or n.hand == hand)
            current_evidence = {n.source_id: evidence[n.source_id]
                                for n in source if n.source_id in evidence}
            stages[(ex.key, hand)] = _selection(
                catalog.stages(ex, hand), current_evidence, kind=ex.kind)
    return LessonPlanDefinition(
        catalog.exercises, stages, catalog.generator_name,
        requires_unique_source_ids=True)
