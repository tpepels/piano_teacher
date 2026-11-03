"""Auditable teaching-stage differences, selection and presentation.

Research catalogs remain untouched. This adapter selects only stages that
actually remove source attacks, change their written timing, or apply an
effective tempo policy. Source identities are compared exactly; UI never
claims a transformation based solely on a differently named level.
"""
from __future__ import annotations

from dataclasses import dataclass

from .exercise_pipeline import ExerciseStage


def _notes(stage: ExerciseStage) -> tuple:
    return tuple(sorted(
        (n.source_id, n.pitch, round(n.start, 8), round(n.end, 8))
        for n in stage.variant.notes))


def _tempo(stage: ExerciseStage) -> tuple:
    policy = stage.tempo_policy
    if policy is None:
        return ()
    # A slowdown stage has the same authored note coordinates but a
    # distinct performance. Keep factors separate; do not clone variants.
    return (type(policy).__module__, type(policy).__qualname__,
            str(getattr(policy, "name", "")),
            getattr(policy, "factor", None))


def fingerprint(stage: ExerciseStage) -> tuple:
    return (_notes(stage), _tempo(stage))


@dataclass(frozen=True)
class StageDifference:
    removed: int
    retimed: int
    tempo_changed: bool
    source_count: int
    active_count: int

    @property
    def meaningful(self) -> bool:
        return self.removed > 0 or self.retimed > 0 or self.tempo_changed


def difference(stage: ExerciseStage, original: ExerciseStage) -> StageDifference:
    source = {n.source_id: n for n in original.variant.notes}
    chosen = {n.source_id: n for n in stage.variant.notes}
    if (len(source) != len(original.variant.notes)
            or len(chosen) != len(stage.variant.notes)
            or not set(chosen) <= set(source)):
        raise ValueError("Teaching stage must retain distinct original MIDI IDs")
    retimed = sum(
        abs(note.start - source[sid].start) > 1e-7
        or abs(note.end - source[sid].end) > 1e-7
        for sid, note in chosen.items())
    return StageDifference(
        removed=len(source)-len(chosen), retimed=retimed,
        tempo_changed=_tempo(stage) != _tempo(original),
        source_count=len(source), active_count=len(chosen))


def _attacks(stage: ExerciseStage) -> int:
    return len({round(n.start, 7) for n in stage.variant.notes})


def distinct_stages(candidates: tuple[ExerciseStage, ...],
                    original: ExerciseStage) -> tuple[ExerciseStage, ...]:
    """Exclude editorial renames and identical lesson performances.

    A slowdown is retained because the same notes are genuinely played at a
    different speed. Original is always last, even for single-note passages.
    """
    output = []
    seen = set()
    for stage in candidates:
        delta = difference(stage, original)
        if not delta.meaningful:
            continue
        # An extremely sparse scaffold should not become a completely
        # unplayable one-attack lesson when the original has multiple attacks.
        if _attacks(original) >= 3 and _attacks(stage) < 2:
            continue
        key = fingerprint(stage)
        if key in seen:
            continue
        seen.add(key)
        output.append(stage)
    return tuple(output)


def teaching_sequence(candidates: tuple[ExerciseStage, ...], *,
                      evidence: dict[str, str] | None = None,
                      limit: int = 3) -> tuple[ExerciseStage, ...]:
    """Choose real exercises, easiest source reduction first.

    For pitch errors, prefer a Fukuda reduction of the failed attack or its
    nearby context (caller supplies already relevance-ranked candidates).
    Rhythm errors select authored Coda timing changes; duration errors start
    with a real slowdown. Never substitute a category that is a no-op.
    """
    if not candidates or candidates[-1].variant.level != "original":
        raise ValueError("A teaching catalog must end in the original MIDI")
    original = candidates[-1]
    unique = distinct_stages(candidates[:-1], original)
    if not unique:
        return (original,)
    evidence = evidence or {}
    statuses = set(evidence.values())
    pitch = bool(statuses & {"wrong", "missed", "pitch"})
    rhythm = bool(statuses & {"early", "late", "timing"})
    duration = bool(statuses & {"short", "long", "duration"})
    # Selection is based on real musical effects, not generator names:
    # a new MIDI algorithm can contribute a reduction or altered rhythm
    # without changing any shared curriculum code. Candidate ordering
    # supplied by the caller is significant for source-localized repairs.
    reductions = [stage for stage in unique
                  if difference(stage, original).removed > 0]
    rhythms = [stage for stage in unique
               if difference(stage, original).retimed > 0]
    slows = [stage for stage in unique
             if difference(stage, original).tempo_changed]
    ranked_reductions = sorted(reductions, key=lambda stage: (
        -difference(stage, original).removed, _attacks(stage),
        unique.index(stage)))
    # During graded pitch repair the caller supplies reductions ordered by
    # note-ID relevance. Preserve that ordering rather than globally
    # favouring a large, unrelated simplification.
    ordered_reductions = reductions if pitch else ranked_reductions
    if pitch:
        candidates_by_priority = [
            *ordered_reductions, *slows, *rhythms, *unique]
    elif rhythm:
        candidates_by_priority = [
            *rhythms, *slows, *ordered_reductions, *unique]
    elif duration:
        candidates_by_priority = [
            *slows, *ordered_reductions, *rhythms, *unique]
    else:
        # Offer one genuine reduction, one authored rhythmic transformation
        # and one independent tempo change when the source supports them.
        # This works for any number of registered generator families.
        candidates_by_priority = [
            *ordered_reductions[:1], *rhythms[:1], *slows[:1],
            *ordered_reductions[1:], *rhythms[1:], *slows[1:], *unique]
    chosen = []
    signatures = set()
    for stage in candidates_by_priority:
        sign = fingerprint(stage)
        if sign in signatures:
            continue
        chosen.append(stage)
        signatures.add(sign)
        if len(chosen) == limit:
            break
    # Retain a genuinely distinct Coda exercise when the first selection
    # consists only of Fukuda reductions and one tempo slowdown.
    if not chosen:
        chosen = list(unique[:limit])
    return (*chosen, original)


def describe(stage: ExerciseStage, original: ExerciseStage) -> dict:
    """Present author-owned metadata with source-measured differences.

    No component in the application interprets level-string prefixes.
    Third-party generators can set origin/technique/display_name without
    changing the lesson UI, state projection or adaptive selection.
    """
    delta = difference(stage, original)
    level = stage.variant.level
    if level == "original":
        family = "Original"
        label = "Original notes and rhythm"
    else:
        family = {"fukuda-midi": "Fukuda", "coda-midi": "Coda"}.get(
            stage.origin, stage.origin.replace("-", " ").title()
            if stage.origin else "Practice")
        label = stage.display_name or level.replace("-", " ").capitalize()
    change = (
        f"{delta.active_count}/{delta.source_count} source notes" if delta.removed else
        f"{delta.retimed} retimed notes" if delta.retimed else
        "tempo adjustment" if delta.tempo_changed else
        "unchanged source")
    return {"family": family, "label": label, "change": change,
            "level": level, "origin": stage.origin,
            "technique": stage.technique,
            "removed": delta.removed, "retimed": delta.retimed,
            "tempo_changed": delta.tempo_changed,
            "meaningful": delta.meaningful}
