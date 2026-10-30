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
    is_identity: bool = True

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
class TempoSegment:
    start_beat: float
    end_beat: float
    bpm: float


@dataclass(frozen=True)
class TempoMap:
    """Piecewise-constant tempo with exact beat-to-second conversion.

    Separate from Score/Phrase timing: grading and playback must consume
    this same map before tempo shaping becomes an interactive strategy.
    """
    name: str
    segments: tuple[TempoSegment, ...]

    def __post_init__(self) -> None:
        if not self.name or not self.segments:
            raise ValueError("Tempo map requires a name and segments")
        previous = 0.0
        for segment in self.segments:
            if (not all(isfinite(n) for n in
                        (segment.start_beat, segment.end_beat, segment.bpm))
                    or abs(segment.start_beat - previous) > 1e-7
                    or segment.end_beat <= segment.start_beat or segment.bpm <= 0):
                raise ValueError("Tempo segments must be contiguous, positive and finite")
            previous = segment.end_beat

    @property
    def duration_beats(self) -> float:
        return self.segments[-1].end_beat

    def seconds_at(self, beat: float) -> float:
        if not isfinite(beat) or not -1e-7 <= beat <= self.duration_beats + 1e-7:
            raise ValueError("Beat outside tempo map")
        elapsed = 0.0
        for segment in self.segments:
            if beat <= segment.start_beat:
                break
            elapsed += (min(beat, segment.end_beat) - segment.start_beat) * 60.0 / segment.bpm
            if beat <= segment.end_beat:
                break
        return elapsed

    @property
    def duration_seconds(self) -> float:
        return self.seconds_at(self.duration_beats)

    def beat_at(self, seconds: float) -> float:
        """Exact inverse of seconds_at; clamp during feedback and count-in."""
        if not isfinite(seconds):
            raise ValueError("Time must be finite")
        if seconds <= 0:
            return seconds * self.segments[0].bpm / 60.0
        elapsed = 0.0
        for segment in self.segments:
            end = elapsed + (segment.end_beat-segment.start_beat)*60/segment.bpm
            if seconds <= end:
                return segment.start_beat + (seconds-elapsed)*segment.bpm/60
            elapsed = end
        return self.duration_beats + (seconds-elapsed)*self.segments[-1].bpm/60.0

    def bpm_at(self, beat: float) -> float:
        for segment in self.segments:
            if beat < segment.end_beat:
                return segment.bpm
        return self.segments[-1].bpm

    def from_beat(self, start_beat: float) -> "TempoMap":
        """Return a local zero-origin map for a partial retry or seek."""
        if not 0 <= start_beat < self.duration_beats:
            raise ValueError("Starting beat is outside tempo map")
        remaining = tuple(
            TempoSegment(max(0.0, segment.start_beat - start_beat),
                         segment.end_beat - start_beat, segment.bpm)
            for segment in self.segments if segment.end_beat > start_beat + 1e-8)
        return TempoMap(self.name, remaining)

    def as_segments(self) -> tuple[dict, ...]:
        return tuple({"start_beat": s.start_beat, "end_beat": s.end_beat,
                      "bpm": s.bpm, "start_seconds": self.seconds_at(s.start_beat)}
                     for s in self.segments)


class TempoStrategy(Protocol):
    name: str
    def generate(self, plan: TimingPlan, target_bpm: float) -> TempoMap: ...


@dataclass(frozen=True)
class ConstantTempo:
    name: str = "constant-tempo"
    is_identity: bool = True

    def generate(self, plan: TimingPlan, target_bpm: float) -> TempoMap:
        return TempoMap(self.name, (TempoSegment(0, plan.duration_beats, float(target_bpm)),))


@dataclass(frozen=True)
class TwoPhaseTempo:
    """Deterministic Coda-inspired tempo shaping: slow half, target half."""
    speed_fraction: float = .8
    name: str = "two-phase-tempo"

    def generate(self, plan: TimingPlan, target_bpm: float) -> TempoMap:
        if (not isfinite(target_bpm) or target_bpm <= 0
                or not isfinite(self.speed_fraction) or not 0 < self.speed_fraction <= 1):
            raise ValueError("Invalid tempo-shaping parameters")
        middle = plan.duration_beats / 2
        return TempoMap(self.name, (
            TempoSegment(0, middle, target_bpm*self.speed_fraction),
            TempoSegment(middle, plan.duration_beats, target_bpm)))


@dataclass(frozen=True)
class TimingAssessment:
    """Assessment of the transformed target, with original note identity."""
    timing_name: str
    assessment: Assessment
    timed_notes: tuple[NoteAssessment, ...]
    tempo_name: str = "constant-tempo"


def assess_timed(plan: TimingPlan, hand: str, bpm: float,
                 played: list[PlayedNote], *, tempo_map: TempoMap | None = None) -> TimingAssessment:
    """Assess transformed beats, then rebind annotations to original notes.

    This never credits source mastery by itself: the caller must distinguish
    the transformed stage from the mandatory original stage.
    """
    phrase = plan.exercise_phrase
    if tempo_map is None:
        timed = evaluate(phrase, hand, bpm, played)
    else:
        if abs(tempo_map.duration_beats - plan.duration_beats) > 1e-7:
            raise ValueError("Tempo map must cover the whole timed exercise")
        from .assessment_clock import expected_note_seconds
        timed = evaluate(
            phrase, hand, bpm, played,
            expected_seconds=expected_note_seconds(phrase, tempo_map))
    # Assessment only returns notes for the selected hand, in phrase order.
    originals = [n for n in plan.original.notes if hand == "both" or n.hand == hand]
    if len(timed.notes) != len(originals):
        raise ValueError("Grader lost transformed source correspondence")
    bound = tuple(replace(entry, note=note)
                  for entry, note in zip(timed.notes, originals))
    return TimingAssessment(plan.name, Assessment(bound, timed.extra_notes,
                                                   timed.unmatched_played), timed.notes,
                            tempo_map.name if tempo_map is not None else "constant-tempo")


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


@dataclass(frozen=True)
class AccuracyOnlyDiagnosis:
    """Uninformed baseline for controlled error-diagnosis comparison."""
    name: str = "accuracy-only"

    def diagnose(self, evidence: AssessmentEvidence) -> str:
        if not evidence.assessed or not evidence.statuses:
            return "unassessed"
        return "accuracy"


@dataclass(frozen=True)
class RepeatOnlyPolicy:
    """Baseline policy without error-triggered intervention."""
    name: str = "repeat-only"

    def recommend(self, snapshot: LearnerSnapshot,
                  diagnosis: AssessmentDiagnosisStrategy) -> PracticeRecommendation:
        if snapshot.recent and snapshot.recent[-1].clean:
            return PracticeRecommendation("none", "advance", "clean assessed take")
        return PracticeRecommendation("accuracy", "repeat", "baseline practice policy")


_TIMING_STRATEGIES = {
    "original-timing": OriginalTiming,
    "dotted-long-short": lambda: DottedPairTiming(True),
    "dotted-short-long": lambda: DottedPairTiming(False),
}
_TEMPO_STRATEGIES = {
    "constant-tempo": ConstantTempo,
    "two-phase-tempo": TwoPhaseTempo,
}
_DIAGNOSIS_STRATEGIES = {
    "error-family": ErrorFamilyDiagnosis,
    "accuracy-only": AccuracyOnlyDiagnosis,
}
_LEARNER_STRATEGIES = {
    "repeated-error": RepeatedErrorPolicy,
    "repeat-only": RepeatOnlyPolicy,
}


def _resolve_strategy(spec, options: dict, method: str):
    if isinstance(spec, str):
        try:
            return options[spec]()
        except KeyError as error:
            raise ValueError(f"Unknown strategy {spec!r}; choose from {tuple(options)}") from error
    if not isinstance(getattr(spec, "name", None), str) or not callable(getattr(spec, method, None)):
        raise TypeError(f"Custom strategy needs a name and {method} method")
    return spec


def resolve_timing_strategy(spec: str | TimingStrategy = "original-timing") -> TimingStrategy:
    return _resolve_strategy(spec, _TIMING_STRATEGIES, "transform")


def resolve_tempo_strategy(spec: str | TempoStrategy = "constant-tempo") -> TempoStrategy:
    return _resolve_strategy(spec, _TEMPO_STRATEGIES, "generate")


def resolve_diagnosis_strategy(spec: str | AssessmentDiagnosisStrategy = "error-family") -> AssessmentDiagnosisStrategy:
    return _resolve_strategy(spec, _DIAGNOSIS_STRATEGIES, "diagnose")


def resolve_learner_strategy(spec: str | LearnerStateStrategy = "repeated-error") -> LearnerStateStrategy:
    return _resolve_strategy(spec, _LEARNER_STRATEGIES, "recommend")
