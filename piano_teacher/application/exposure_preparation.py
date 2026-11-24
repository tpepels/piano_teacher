"""Prepare source-bound exposure changes before interrupting a live take.

The teaching decision selects the source interval and mode once. These typed
preparations materialize that selection and decide the guided/rhythm return,
score gate and learner-facing guidance. They retain no engine, mutable plan,
transport or callback; the application applies their effects under its lock.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ..exercise_generator import ExerciseVariant
from ..exercise_contracts import TempoMap
from ..teaching_decisions import TeachingExposure
from ..remediation import RemedialAssignment
from .guided_session import GuidedFragment, materialize_fragment
from .listen_session import ListenSelection


RetryRange = tuple[tuple[str, int | float | str], ...] | None


@dataclass(frozen=True, slots=True)
class ExposureSource:
    stage_key: str
    variant: ExerciseVariant
    boundaries: tuple[float, ...]
    time_signatures: tuple[tuple[float, int, int], ...]

    @property
    def duration(self) -> float:
        return self.variant.phrase.end-self.variant.phrase.start


@dataclass(frozen=True, slots=True)
class GuidedPreparation:
    source: ExposureSource
    fragment: GuidedFragment
    revision: int
    recovery: bool
    remediation: RemedialAssignment | None
    retry_range: RetryRange
    feedback: str
    next_action: str

    @property
    def stop_reason(self) -> str:
        return "guided_recovery" if self.recovery else "learn"


@dataclass(frozen=True, slots=True)
class TimedPreparation:
    mode: Literal["practice", "perform"]
    from_beat: float
    end_beat: float | None
    revision: int
    awaiting_score: int | None
    return_context: tuple[str, float] | None
    retry_range: RetryRange
    feedback: str
    next_action: str

    @property
    def preserve_episode(self) -> bool:
        return self.return_context is not None


@dataclass(frozen=True, slots=True)
class ListenPreparation:
    selection: ListenSelection
    feedback: str = "Preparing an audible example"
    next_action: str = "Listen to the notes, then choose Learn or Practice."

    @property
    def revision(self) -> int:
        return self.selection.revision


def prepare_guided(source: ExposureSource, selected: TeachingExposure, *,
                   revision: int, bump_revision: bool, recovery: bool,
                   remediation: RemedialAssignment | None,
                   retry_range: dict | None) -> GuidedPreparation:
    start = selected.from_beat
    end = selected.end_beat if selected.end_beat is not None else source.duration
    # Validate/materialize the exact selected interval before stopping the
    # current teaching controller or interrupting its durable exposure.
    original = materialize_fragment(source.variant,source.boundaries,
                                   start=start,end=end)
    fragment = (materialize_fragment(remediation.variant,source.boundaries,start=start,end=end)
                if remediation is not None else original)
    return GuidedPreparation(
        source,fragment,revision+int(bump_revision),recovery,remediation,
        tuple(retry_range.items()) if recovery and retry_range is not None else None,
        remediation.focus if remediation is not None else
        "Now without tempo",
        f"Learn the selected {remediation.focus} notes, then retry the original."
        if remediation is not None else
        f"Learn bars {original.phrase.first_bar}-{original.phrase.last_bar} "
        "at your own pace, then retry the rhythm.")


def prepare_timed(source: ExposureSource, selected: TeachingExposure, *,
                  mode: Literal["practice", "perform"], revision: int,
                  return_context: tuple[str, float] | None = None,
                  retry_range: dict | None = None) -> TimedPreparation:
    revision += 1
    if mode == "perform":
        return TimedPreparation(mode,selected.from_beat,selected.end_beat,
            revision,revision,None,None,"Preparing your performance",
            "Keep playing through the passage. Review comes at the end.")
    return TimedPreparation(mode,selected.from_beat,selected.end_beat,
        revision,revision,return_context,
        tuple(retry_range.items()) if return_context is not None and retry_range is not None else None,
        "Preparing rhythm practice",
        "Get ready to retry the rhythm." if return_context else
        "Get ready to play in time.")


def prepare_listen(source: ExposureSource, *, revision: int, bpm: float,
                   tempo_map: TempoMap | None) -> ListenPreparation:
    return ListenPreparation(ListenSelection(
        variant=source.variant,bpm=bpm,stage_key=source.stage_key,
        revision=revision+1,bar_boundaries=source.boundaries,
        time_signatures=source.time_signatures,tempo_map=tempo_map,
        from_beat=source.variant.phrase.first_attack_beat))


def prepare_remedial(source: ExposureSource, assignment: RemedialAssignment,
                     exposure) -> RemedialAssignment | None:
    """The Free aid for this exact source stage, over the selected window;
    None when the assignment belongs to a superseded stage."""
    if assignment.stage_key != source.stage_key:
        return None
    if exposure is not None:
        assignment = replace(assignment,start_beat=exposure.from_beat,
            end_beat=exposure.end_beat if exposure.end_beat is not None else source.duration)
    return assignment
