"""Experimental contracts for timing transformations and adaptive practice.

These interfaces deliberately separate exercise timing, graded evidence and
learner history. The current live score still uses original source beats:
timing transformations must not be enabled as live variants until engraving,
transport and live scoring support the same timing plan.

Research inspirations: Tang (2025, Coda), Dannenberg et al. (1990,
Piano Tutor), Fukuda et al. (2015). They are not exact reproductions.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from math import isfinite
from typing import Protocol

from .exercise_generator import ExerciseVariant
from .music import Phrase
from .practice import Assessment, NoteAssessment, PlayedNote, evaluate


@dataclass(frozen=True)
class TimingEvent:
    """One source-indexed attack with transformed exercise beat coordinates."""
    source_index: int
    source_start: float
    source_end: float
    exercise_start: float
    exercise_end: float


@dataclass(frozen=True)
class TimingPlan:
    """Complete reversible event mapping for one source-indexed variant.

    An exercise note may be displaced or shortened without changing the
    imported source. No transformed stage may grant original-source mastery.
    """
    name: str
    original: ExerciseVariant
    events: tuple[TimingEvent, ...]
    duration_beats: float

    def __post_init__(self) -> None:
        if not self.name or not isfinite(self.duration_beats) or self.duration_beats <= 0:
            raise ValueError("Invalid timing plan")
        if len(self.events) != len(self.original.notes):
            raise ValueError("Each source note needs one exercise event")
        for index, event in enumerate(self.events):
            source = self.original.notes[index]
            if event.source_index != self.original.source_indices[index]:
                raise ValueError("Timing plan lost source mapping")
            if abs(event.source_start - source.start) > 1e-7 or abs(event.source_end - source.end) > 1e-7:
                raise ValueError("Timing plan source events differ from original")
            if (not all(isfinite(v) for v in
                        (event.exercise_start, event.exercise_end))
                    or event.exercise_start < -1e-7
                    or event.exercise_end <= event.exercise_start
                    or event.exercise_end > self.duration_beats + 1e-7):
                raise ValueError("Timing plan exceeds exercise timeline")

    @property
    def exercise_phrase(self) -> Phrase:
        """Independent timed phrase used only by timing-aware playback/grading."""
        p = self.original.phrase
        return Phrase(p.number, p.first_bar, p.last_bar, 0, self.duration_beats,
                      tuple(replace(note, start=event.exercise_start,
                                    end=event.exercise_end)
                            for note, event in zip(self.original.notes, self.events)))


class TimingStrategy(Protocol):
    name: str
    def transform(self, variant: ExerciseVariant) -> TimingPlan: ...


def _events(variant: ExerciseVariant) -> tuple[TimingEvent, ...]:
    origin = variant.phrase.start
    return tuple(TimingEvent(index, note.start, note.end,
                             note.start - origin, note.end - origin)
                 for index, note in zip(variant.source_indices, variant.notes))


@dataclass(frozen=True)
class OriginalTiming:
    name: str = "original-timing"

    def transform(self, variant: ExerciseVariant) -> TimingPlan:
        p = variant.phrase
        duration = max(p.end - p.start, max((n.end-p.start for n in variant.notes), default=0))
        return TimingPlan(self.name, variant, _events(variant), duration)


@dataclass(frozen=True)
class DottedPairTiming:
    """Coda-inspired long-short or short-long attack-pair rhythm.

    Transform only monophonic, strictly sequential single-note passages.
    Preserve each pair's total duration and the first onset. Keep the final
    original note duration and do not mutate shared chords or overlap/ties.
    """
    long_first: bool = True

    @property
    def name(self) -> str:
        return "dotted-long-short" if self.long_first else "dotted-short-long"

    def transform(self, variant: ExerciseVariant) -> TimingPlan:
        original = OriginalTiming().transform(variant)
        if len(variant.notes) < 2:
            return original
        notes = variant.notes
        order = sorted(range(len(notes)), key=lambda i: (notes[i].start, i))
        if any(a.hand != b.hand for a, b in zip(notes, notes[1:])):
            return original
        if any(notes[b].start < notes[a].end - 1e-7
               for a, b in zip(order, order[1:])):
            return original
        events = list(original.events)
        for i in range(0, len(order)-1, 2):
            left, right = order[i:i+2]
            a, b = events[left], events[right]
            # Rhythm pattern applies only to equal-duration adjacent attacks.
            gap = b.source_start - a.source_start
            if gap <= 1e-7 or abs(gap - (notes[right].end-notes[right].start)) > 1e-5:
                continue
            if abs(gap - (notes[left].end-notes[left].start)) > 1e-5:
                continue
            # Long-short pair spans two gaps; does not change following pair.
            pair_end = (events[order[i+2]].exercise_start
                        if i + 2 < len(order)
                        else b.exercise_start + gap)
            if abs(pair_end - (a.exercise_start + 2*gap)) > 1e-5:
                continue
            first = gap * (1.5 if self.long_first else .5)
            second = 2 * gap - first
            events[left] = replace(a, exercise_end=a.exercise_start+first)
            events[right] = replace(b, exercise_start=a.exercise_start+first,
                                    exercise_end=a.exercise_start+first+second)
        return TimingPlan(self.name, variant, tuple(events), original.duration_beats)


@dataclass(frozen=True)
class TimingAssessment:
    """Assessment of the transformed target, with original note identity."""
    timing_name: str
    assessment: Assessment
    timed_notes: tuple[NoteAssessment, ...]


def assess_timed(plan: TimingPlan, hand: str, bpm: float,
                 played: list[PlayedNote]) -> TimingAssessment:
    """Assess transformed beats, then rebind annotations to original notes.

    This never credits source mastery by itself: the caller must distinguish
    the transformed stage from the mandatory original stage.
    """
    timed = evaluate(plan.exercise_phrase, hand, bpm, played)
    # Assessment only returns notes for the selected hand, in phrase order.
    originals = [n for n in plan.original.notes if hand == "both" or n.hand == hand]
    if len(timed.notes) != len(originals):
        raise ValueError("Grader lost transformed source correspondence")
    bound = tuple(replace(entry, note=note)
                  for entry, note in zip(timed.notes, originals))
    return TimingAssessment(plan.name, Assessment(bound, timed.extra_notes,
                                                   timed.unmatched_played), timed.notes)


@dataclass(frozen=True)
class AssessmentEvidence:
    """Immutable diagnostic summary; avoid treating an ungraded preview as data."""
    stage_key: str
    statuses: tuple[str, ...]
    extra_notes: int
    bpm: float
    assessed: bool = True

    @classmethod
    def from_result(cls, stage_key: str, result: Assessment, bpm: float):
        return cls(stage_key, tuple(entry.status for entry in result.notes),
                   result.extra_notes, bpm)

    def __post_init__(self):
        allowed = {"correct", "early", "late", "short", "long", "missed", "wrong"}
        if (not self.stage_key or any(s not in allowed for s in self.statuses)
                or self.extra_notes < 0 or not isfinite(self.bpm) or self.bpm <= 0):
            raise ValueError("Invalid graded assessment evidence")

    @property
    def clean(self) -> bool:
        return self.assessed and bool(self.statuses) and all(
            status == "correct" for status in self.statuses) and not self.extra_notes


@dataclass(frozen=True)
class LearnerSnapshot:
    stage_key: str
    recent: tuple[AssessmentEvidence, ...]

    def __post_init__(self):
        if any(not e.assessed or e.stage_key != self.stage_key for e in self.recent):
            raise ValueError("History must be graded and scoped to one exact stage")


@dataclass(frozen=True)
class PracticeRecommendation:
    focus: str  # pitch, rhythm, duration, accuracy, or none
    action: str  # note-isolation, timing-practice, sustain-practice, repeat, advance
    basis: str


class AssessmentDiagnosisStrategy(Protocol):
    name: str
    def diagnose(self, evidence: AssessmentEvidence) -> str: ...


@dataclass(frozen=True)
class ErrorFamilyDiagnosis:
    """Piano Tutor-inspired error categories, not an inferred root cause."""
    name: str = "error-family"

    def diagnose(self, evidence: AssessmentEvidence) -> str:
        if not evidence.assessed or not evidence.statuses:
            return "unassessed"
        counts = Counter(evidence.statuses)
        families = {
            "pitch": counts["wrong"] + counts["missed"] + evidence.extra_notes,
            "rhythm": counts["early"] + counts["late"],
            "duration": counts["short"] + counts["long"],
        }
        peak = max(families.values())
        if peak == 0:
            return "accuracy"
        tied = [kind for kind, value in families.items() if value == peak]
        return tied[0] if len(tied) == 1 else "mixed"


class LearnerStateStrategy(Protocol):
    name: str
    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation: ...


@dataclass(frozen=True)
class RepeatedErrorPolicy:
    """Advisory-only rule: never change BPM or grant mastery without consent."""
    name: str = "repeated-error"

    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation:
        if not snapshot.recent:
            return PracticeRecommendation("none", "repeat", "no assessed history")
        latest = snapshot.recent[-1]
        if latest.clean:
            return PracticeRecommendation("none", "advance", "clean assessed take")
        if len(snapshot.recent) < 2:
            return PracticeRecommendation("accuracy", "repeat", "first assessed difficulty")
        prior, current = snapshot.recent[-2:]
        a, b = diagnosis.diagnose(prior), diagnosis.diagnose(current)
        if a != b or b in ("mixed", "unassessed", "accuracy"):
            return PracticeRecommendation("accuracy", "repeat", "inconsistent error families")
        actions = {"pitch": "note-isolation", "rhythm": "timing-practice",
                   "duration": "sustain-practice"}
        return PracticeRecommendation(b, actions[b], "same dominant error family in two consecutive takes")
