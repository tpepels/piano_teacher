"""Progressive, source-bound Coda/Fukuda teaching over an imported MIDI piece.

Full original Coda remains an independent research strategy. This product
curriculum deliberately selects short, complete MIDI passages, exercises and
error-appropriate stages from both generator families. No additional clock,
renderer, MIDI grader or persistence system is introduced.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import replace
from typing import Mapping

from .application.coda_midi_curriculum import midi_coda_stages
from .exercise_generator import ExerciseVariant
from .exercise_pipeline import ExerciseStage
from .fukuda_midi import fukuda_midi_variants
from .lesson_settings import SETTINGS
from .lesson_source_planner import Exercise, _focus_phrases, _hands_for_learning
from .music import Phrase, Piece


def _segments(piece: Piece) -> tuple[Phrase, ...]:
    """Focus in two-bar units; join sections if a note sustains over the cut.

    The segmentation respects original measure boundaries and never crops or
    invents a MIDI attack/release. Entirely silent introductory bars are left
    for the last full-score performance.
    """
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
            crossing = tuple(n for n in piece.notes if
                             grid[first - 1] <= n.start < boundary - 1e-7
                             and n.end > boundary + 1e-7)
            if not crossing:
                break
            if last == bars:
                break
            last += 1
        # Other focus units subsumed by a held source note are merged.
        while i + 1 < len(base) and base[i + 1].first_bar <= last:
            i += 1
            last = max(last, base[i].last_bar)
            # The enlarged section might also cross another held note.
            while last < bars and any(
                    grid[first - 1] <= n.start < grid[last] - 1e-7
                    and n.end > grid[last] + 1e-7 for n in piece.notes):
                last += 1
        start, end = grid[first - 1], grid[last]
        selected = tuple(n for n in piece.notes
                         if start - 1e-7 <= n.start < end - 1e-7)
        if selected:
            # Some MIDI files end their measure grid before the final
            # sounding key-off. Keep the release in the lesson timeline.
            end = max(end, max(n.end for n in selected))
            groups.append(Phrase(
                len(groups) + 1, first, last, start, end, selected))
        i += 1
    return tuple(groups)


def _course_exercises(piece: Piece) -> tuple[Exercise, ...]:
    passages = _segments(piece)
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
        joined = tuple(n for n in piece.notes if start <= n.start < end)
        if (any(n.start < phrase.start for n in joined)
                and any(n.start >= phrase.start for n in joined)
                and all(n.end <= end + 1e-7 for n in joined)
                and len({round(n.start, 6) for n in joined})
                    <= SETTINGS.focus_max_attacks):
            out.insert(len(out) - 1, Exercise(
                "connect", Phrase(0, first_bar, last_bar, start, end, joined),
                f"hybrid:connect:{first_bar}-{last_bar}"))
    last = len(piece.bar_boundaries) - 1
    complete = Phrase(
        0, 1, last, piece.bar_boundaries[0],
        max(piece.bar_boundaries[-1], max(n.end for n in piece.notes)),
        piece.notes)
    out.append(Exercise("perform", complete, "perform:all"))
    return tuple(out)


def compile_hybrid_catalog(piece: Piece):
    """Compile *all* candidates once; later feedback only selects stages."""
    from .lesson_generators import LessonPlanDefinition, lesson_hands
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
                stages[(exercise.key, hand)] = (ExerciseStage(original),)
                continue
            # Keep every applicable author candidate in the immutable catalog.
            # Coda transforms only source-safe bar-boundary passages.
            coda = (midi_coda_stages(piece, (original,), kind="learn")
                    if (abs(exercise.phrase.end -
                            piece.bar_boundaries[exercise.phrase.last_bar])
                        <= 1e-7)
                    else (ExerciseStage(original),))
            fukuda = fukuda_midi_variants(original, bpm=piece.bpm)
            variants = (*tuple(ExerciseStage(v) for v in fukuda[:-1]),
                        *coda)
            levels = [stage.variant.level for stage in variants]
            if len(set(levels)) != len(levels):
                raise ValueError("Hybrid candidate stage names overlap")
            stages[(exercise.key, hand)] = variants
    return LessonPlanDefinition(
        exercises, stages, "coda-fukuda-midi",
        requires_unique_source_ids=True)


def _selection(candidates: tuple[ExerciseStage, ...], statuses: set[str],
               *, kind: str) -> tuple[ExerciseStage, ...]:
    if kind != "learn" or len(candidates) < 2:
        return candidates
    normal = candidates[-1]
    fukuda = [s for s in candidates[:-1]
              if s.variant.level.startswith("fukuda-midi-")]
    dotted = [s for s in candidates[:-1]
              if "dotted-" in s.variant.level]
    slow = [s for s in candidates[:-1]
            if "slowdown-" in s.variant.level]
    chord = [s for s in candidates[:-1]
             if "chord-" in s.variant.level]
    pitch = bool(statuses & {"wrong", "missed", "pitch"})
    rhythm = bool(statuses & {"early", "late", "timing"})
    duration = bool(statuses & {"short", "long", "duration"})
    if pitch:
        chosen = [*fukuda[:2], *slow[:1]]
    elif rhythm:
        chosen = [*dotted[:2], *slow[:1]]
    elif duration:
        chosen = slow[:2]
    else:
        # A short initial scaffold, not every generated author exercise.
        # The complete Coda catalog remains available in Coda-only mode.
        chosen = [*fukuda[:1], *(chord[:1] or dotted[:1]), *slow[:1]]
    if (pitch and rhythm) or (duration and rhythm):
        chosen.extend(dotted[:1])
    if pitch and duration:
        chosen.extend(slow[1:2])
    used = set()
    ordered = []
    for stage in chosen:
        if stage.variant.level not in used:
            used.add(stage.variant.level)
            ordered.append(stage)
    return (*ordered, normal)


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
            statuses = {evidence[n.source_id] for n in source
                        if n.source_id in evidence}
            stages[(ex.key, hand)] = _selection(
                catalog.stages(ex, hand), statuses, kind=ex.kind)
    return LessonPlanDefinition(
        catalog.exercises, stages, catalog.generator_name,
        requires_unique_source_ids=True)
