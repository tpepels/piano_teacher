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
    fukuda = [s for s in unique if s.variant.level.startswith("fukuda-midi-")]
    coda = [s for s in unique if s.variant.level.startswith("coda-")]
    dotted = [s for s in coda if "dotted-" in s.variant.level]
    chord = [s for s in coda if "chord-" in s.variant.level]
    slow = [s for s in coda if "slowdown-" in s.variant.level]

    # A full 4-note chord reduced to 2 outer notes is more useful than a
    # 16th-note thinning which changes a single already-easy attack.
    ranked_fukuda = sorted(fukuda, key=lambda s: (
        -difference(s, original).removed, _attacks(s),
        s.variant.level))
    candidates_by_priority = (
        [*fukuda, *slow, *dotted] if pitch else
        [*dotted, *slow, *ranked_fukuda] if rhythm else
        [*slow, *ranked_fukuda, *dotted] if duration else
        [*ranked_fukuda, *(chord[:1] or dotted[:1]), *slow, *dotted]
    )
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
    delta = difference(stage, original)
    level = stage.variant.level
    family = ("Fukuda" if level.startswith("fukuda-midi-") else
              "Coda" if level.startswith("coda-") else "Original")
    if level == "original":
        label = "Original notes and rhythm"
    elif level.startswith("fukuda-midi-chord"):
        label = "Outer chord notes"
    elif level.startswith("fukuda-midi-fast"):
        label = "Fewer fast notes"
    elif level.startswith("fukuda-midi-return"):
        label = "Simplified wide leaps"
    elif level.startswith("fukuda-midi-leap"):
        label = "Neighboring leap practice"
    elif "dotted-long-short" in level:
        label = "Long–short rhythm"
    elif "dotted-short-long" in level:
        label = "Short–long rhythm"
    elif "chord-" in level:
        label = "Chordified rhythm"
    elif "slowdown-" in level:
        label = "Slowed playback"
    elif "voice-original" in level:
        label = "Isolated source voice"
    else:
        label = level.replace("coda-", "").replace("fukuda-midi-", "").replace("-", " ").capitalize()
    change = (
        f"{delta.active_count}/{delta.source_count} source notes" if delta.removed else
        f"{delta.retimed} retimed notes" if delta.retimed else
        "tempo adjustment" if delta.tempo_changed else
        "unchanged source")
    return {"family": family, "label": label, "change": change,
            "level": level, "removed": delta.removed,
            "retimed": delta.retimed, "tempo_changed": delta.tempo_changed,
            "meaningful": delta.meaningful}
