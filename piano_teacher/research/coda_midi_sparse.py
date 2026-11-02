"""Sparse, exact-PPQ Coda MIDI transformations.

The original Coda backend stores 128 * every tick in three dense matrices.
That representation prevents whole-song lessons on normal performed MIDI.
Here the same equal-duration run algorithms operate on note attacks instead.
This is the MIDI product path; the dense reference implementation remains
independent and can be compared on bounded excerpts.

No authored XML metadata is reconstructed or invented. Transformations
preserve every source note identity, voiced onset and pitch multiplicity.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from ..exercise_contracts import OriginalTiming, TimingPlan
from ..exercise_generator import ExerciseVariant
from .coda_reference_exercises import CodaReferenceResult


@dataclass(frozen=True)
class _Attack:
    tick: int
    duration: int
    indices: tuple[int, ...]


@dataclass(frozen=True)
class _Run:
    start: int
    stop: int
    attacks: tuple[_Attack, ...]


def _tick(beat: float, q: int) -> int:
    value = beat * q
    if not isfinite(value):
        raise ValueError("Coda cannot represent nonfinite MIDI beat")
    tick = round(value)
    if abs(value - tick) / q > 1e-8:
        raise ValueError("Coda MIDI source onset/release is not PPQ-representable")
    return tick


def _attacks(variant: ExerciseVariant, q: int) -> tuple[_Attack, ...]:
    if q <= 0:
        raise ValueError("Coda sparse grid must be positive")
    phrase = variant.phrase
    by_tick: dict[int, list[tuple[int, int]]] = {}
    pitches: dict[int, list[tuple[int, int]]] = {}
    for index, note in enumerate(variant.notes):
        start = _tick(note.start - phrase.start, q)
        end = _tick(note.end - phrase.start, q)
        if start < 0 or end <= start or note.end > phrase.end + 1e-7:
            raise ValueError("Coda note exceeds selected source excerpt")
        by_tick.setdefault(start, []).append((index, end - start))
        pitches.setdefault(note.pitch, []).append((start, end))
    for pitch, spans in pitches.items():
        spans.sort()
        if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
            raise ValueError(
                f"Coda piano roll cannot represent same-pitch overlap: {pitch}")
    attacks = []
    for tick, members in sorted(by_tick.items()):
        durations = {duration for _, duration in members}
        if len(durations) != 1:
            raise ValueError("Coda linear voice has unequal simultaneous durations")
        attacks.append(_Attack(
            tick, next(iter(durations)), tuple(index for index, _ in members)))
    return tuple(attacks)


def _runs(attacks: tuple[_Attack, ...], *, stop: int) -> tuple[_Run, ...]:
    """Original source: equal note-duration runs stop at the next change.

    Silence between same-duration onsets does not automatically terminate a
    run. The final run stops at the final sounding note, as in the MMR.
    """
    groups = []
    pending: list[_Attack] = []
    for attack in attacks:
        if pending and pending[-1].duration != attack.duration:
            if len(pending) > 1:
                groups.append(_Run(pending[0].tick, attack.tick, tuple(pending)))
            pending = []
        pending.append(attack)
    if len(pending) > 1:
        groups.append(_Run(pending[0].tick, stop, tuple(pending)))
    return tuple(groups)


def sparse_midi_coda(
    variant: ExerciseVariant, *,
    family: str,
    quantization: int,
    long_first: bool = True,
    chord_width: int | None = None,
) -> CodaReferenceResult:
    """Apply complete MIDI-safe dotted/chord requests without matrix allocation.

    Input is one true source voice, not an invented cross-hand line. Author
    bug compatibility (integer truncation, pitch loss, six-tone chord output)
    is intentionally excluded from playable MIDI lessons.
    """
    if family not in ("dotted", "chord"):
        raise ValueError("Coda sparse family must be dotted or chord")
    if family == "chord" and (chord_width is None or chord_width <= 0):
        raise ValueError("Chord grouping width must be positive")
    if not variant.notes:
        raise ValueError("Cannot transform an empty Coda voice")
    phrase = variant.phrase
    q = quantization * (2 if family == "dotted" else 1)
    if q <= 0:
        raise ValueError("Coda quantization must be positive")
    attacks = _attacks(variant, q)
    end = max(a.tick + a.duration for a in attacks)
    runs = _runs(attacks, stop=end)
    original = OriginalTiming().transform(variant)
    events = list(original.events)
    groups = []
    ids = []

    def set_time(indices: tuple[int, ...], start: int, finish: int) -> None:
        if not 0 <= start < finish <= _tick(phrase.end - phrase.start, q):
            raise ValueError("Coda transformation leaves the source excerpt")
        for i in indices:
            events[i] = replace(events[i],
                exercise_start=start / q, exercise_end=finish / q)

    if family == "dotted":
        for run in runs:
            sequence = run.attacks
            for a, b in zip(sequence[::2], sequence[1::2]):
                if a.duration != b.duration or b.tick - a.tick != a.duration:
                    continue
                # Source durations are doubled into the dotted grid, so
                # 3:1 and 1:3 give strictly integral destination ticks.
                length = a.duration * (3 if long_first else 1) // 2
                if a.duration % 2 or a.tick + 2 * a.duration > end:
                    continue
                set_time(a.indices, a.tick, a.tick + length)
                set_time(b.indices, a.tick + length, a.tick + 2 * a.duration)
                group = tuple(variant.notes[i].source_id
                              for i in (*a.indices, *b.indices))
                groups.append(group)
                ids.extend(group)
            if len(sequence) % 2:
                last = sequence[-1]
                length = last.duration * (3 if long_first else 1) // 2
                next_onset = next((attack.tick for attack in attacks
                                   if attack.tick > last.tick), None)
                new_end = last.tick + length
                if (last.duration % 2 == 0 and new_end > last.tick and
                        new_end <= _tick(phrase.end - phrase.start, q) and
                        (next_onset is None or new_end <= next_onset)):
                    set_time(last.indices, last.tick, new_end)
                    group = tuple(variant.notes[i].source_id for i in last.indices)
                    groups.append(group)
                    ids.extend(group)
        algorithm = "coda-sparse-dotted-" + (
            "long-short" if long_first else "short-long")
        label = "dotted-rhythms"
    else:
        width = chord_width
        for run in runs:
            # Sparse: visit only actual attack-containing author windows.
            # Iterating every empty 2-tick window in a long, high-PPQ
            # recording would recreate the dense algorithm's time cost.
            buckets: dict[int, list[_Attack]] = {}
            for attack in run.attacks:
                buckets.setdefault((attack.tick - run.start) // width, []).append(attack)
            for bucket, attacks_in_bucket in sorted(buckets.items()):
                start = run.start + bucket * width
                stop_tick = min(start + width, run.stop)
                members = tuple(attacks_in_bucket)
                if len(members) < 2 or members[0].tick != start:
                    continue
                n = members[0].duration
                if (any(a.duration != n for a in members) or
                        any(b.tick - a.tick != n
                            for a, b in zip(members, members[1:]))):
                    continue
                finish = members[-1].tick + n
                if finish > stop_tick:
                    continue
                indices = tuple(i for a in members for i in a.indices)
                pitches = tuple(variant.notes[i].pitch for i in indices)
                # The published piano-playability constraint is 5 distinct
                # chord tones within one octave; a same-pitch retrigger
                # cannot be played as a simultaneous new MIDI attack.
                if (len(pitches) > 5 or len(set(pitches)) != len(pitches) or
                        max(pitches) - min(pitches) > 12):
                    continue
                for a in members:
                    set_time(a.indices, start, finish)
                group = tuple(variant.notes[i].source_id for i in indices)
                groups.append(group)
                ids.extend(group)
        algorithm = f"coda-sparse-chord-{width}"
        label = "chordification"
    return CodaReferenceResult(
        label, TimingPlan(algorithm, variant, tuple(events),
                          original.duration_beats),
        tuple(ids), tuple(groups))
