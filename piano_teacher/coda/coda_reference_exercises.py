"""Source-traceable exercises following the original Coda backend's categories.

This is an independent research adapter, not a copy of the author's code.
Reference: Tang (2025), §2.3, pp.11–16; annieetang/coda_backend
music/exercise.py at a4eb85dfc2bd418818ca9ff775c0a11ccccb3530.

The author's backend uses equal-duration runs, per-voice matrices and
factors 2/4 for written slowdown. Known unguarded bugs (out-of-bounds
subgroups, nested pitch list, silent rounding) are deliberately not
reproduced. Unsupported inputs fail closed and the differences are
documented; this is reference-guided, not blanket parity.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from math import isfinite

from ..exercise_contracts import TimingPlan
from ..exercise_generator import ExerciseVariant
from ..music import source_note_id


@dataclass(frozen=True)
class CodaLevelSelection:
    level: str
    variant: ExerciseVariant
    hand: str
    voice: str | None


@dataclass(frozen=True)
class CodaReferenceResult:
    family: str
    timing: TimingPlan
    changed_sources: tuple[str,...]
    groups: tuple[tuple[str,...],...]


def original_coda_levels(variant: ExerciseVariant, *,
                         boundaries: tuple[float, ...]) -> tuple[CodaLevelSelection, ...]:
    """Group original indices by hand, then by MIDI track/channel/voice."""
    phrase = variant.phrase
    if (len(boundaries) < 2 or not all(isfinite(b) for b in boundaries)
            or any(b <= a for a, b in zip(boundaries, boundaries[1:]))):
        raise ValueError("Invalid measure grid")
    hands = defaultdict(list)
    voices = defaultdict(list)
    seen = set()
    for index, note in enumerate(phrase.notes):
        identifier = source_note_id(note, index)
        if (identifier in seen or note.hand not in ("left", "right")
                or not isfinite(note.start) or not isfinite(note.end)
                or not phrase.start - 1e-7 <= note.start < phrase.end - 1e-7
                or note.end <= note.start):
            raise ValueError("Invalid or duplicate score note identity")
        if not boundaries[0] <= round(note.start, 8) < boundaries[-1]:
            raise ValueError("Attack outside the measure grid")
        seen.add(identifier)
        hands[note.hand].append(index)
        voices[note.hand, note.track, note.channel, note.voice].append(index)

    def select(level, name, indices, hand, voice=None):
        excerpt = replace(phrase, notes=tuple(phrase.notes[i] for i in indices))
        selected = ExerciseVariant(name, excerpt, tuple(variant.source_indices[i] for i in indices))
        return CodaLevelSelection(level, selected, hand, voice)

    result = [CodaLevelSelection("score", variant, "both", None)]
    for hand in ("right", "left"):
        if hand in hands:
            result.append(select("part", "coda-part-" + hand, hands[hand], hand))
            for (owner, _, _, name), indices in sorted(voices.items()):
                if owner == hand:
                    result.append(select("voice", "coda-voice-" + name, indices, hand, name))
    return tuple(result)
