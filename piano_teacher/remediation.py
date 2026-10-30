"""Source-bound remedial assignment selection after assessed repeated errors.

A planner returns a *real exercise* and a source-measure interval, without
mutating the curriculum, earning mastery, or touching MIDI/transport state.
The application may route the assignment to guided key-finding or a timed
partial retry. These two modes keep the existing source-note binding.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict

from .diagnosis_policies import PracticeRecommendation
from .exercise_generator import ExerciseVariant
from .measure_grid import phrase_grid, two_bar_chunks
from .music import Note, Phrase
from .practice import Assessment


@dataclass(frozen=True)
class RemedialAssignment:
    action: str
    focus: str
    start_beat: float
    end_beat: float
    variant: ExerciseVariant
    stage_key: str
    reason: str

    @property
    def guided(self) -> bool:
        return self.action == "note-isolation"


class RemediationPlanner:
    """Deterministic local error selection; no learned learner model."""

    name = "source-error-focus"

    _STATUS = {
        "note-isolation": frozenset(("missed", "wrong")),
        "timing-practice": frozenset(("early", "late")),
        "sustain-practice": frozenset(("short", "long")),
    }

    def plan(self, recommendation: PracticeRecommendation,
             assessed: Assessment, selected: ExerciseVariant,
             *, stage_key: str, boundaries: tuple[float, ...] = ()
             ) -> RemedialAssignment | None:
        wanted = self._STATUS.get(recommendation.action)
        if not wanted or not assessed.notes or not stage_key:
            return None
        phrase = selected.phrase
        grid = phrase_grid(phrase, boundaries)
        chunks = two_bar_chunks(grid)
        if not chunks:
            return None
        by_chunk: dict[int, set[int]] = defaultdict(set)
        # The original source index is the only canonical note identity.
        # Pitch duplicates at one onset remain distinct source events.
        for entry in assessed.notes:
            if entry.status not in wanted:
                continue
            for i, note in enumerate(selected.notes):
                if note is entry.note or note == entry.note:
                    offset = note.start - phrase.start
                    for chunk_index, (start, end) in enumerate(chunks):
                        if start - 1e-7 <= offset < end - 1e-7:
                            by_chunk[chunk_index].add(i)
                            break
                    break
        if not by_chunk:
            return None
        best = max(by_chunk, key=lambda idx: (len(by_chunk[idx]), -idx))
        start, end = chunks[best]
        target = by_chunk[best]
        if recommendation.action == "note-isolation":
            # Keep all pitches of a simultaneous chord together. Selecting
            # only one chord tone would misteach the source harmony.
            onsets = {round(selected.notes[i].start, 6) for i in target}
            indices = tuple(i for i, n in enumerate(selected.notes)
                            if round(n.start, 6) in onsets
                            and start - 1e-7 <= n.start-phrase.start < end - 1e-7)
        else:
            # A timed remedial review needs complete rhythmic context.
            indices = tuple(i for i, n in enumerate(selected.notes)
                            if start - 1e-7 <= n.start-phrase.start < end - 1e-7)
        if not indices:
            return None
        chosen = tuple(selected.notes[i] for i in indices)
        exercise = ExerciseVariant(
            "remedial-" + recommendation.action,
            Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                   phrase.start, phrase.end, chosen),
            tuple(selected.source_indices[i] for i in indices))
        return RemedialAssignment(
            recommendation.action, recommendation.focus, start, end,
            exercise, stage_key, recommendation.basis)
