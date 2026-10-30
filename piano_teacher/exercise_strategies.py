"""Research-inspired, source-preserving exercise strategies.

Fukuda et al. (SMC 2015): https://sap.ist.i.kyoto-u.ac.jp/EN/bib/intl/FUK-SMC15.pdf
Tang (Coda, 2025): https://digitalcommons.dartmouth.edu/cs_senior_theses/76/
Ramoneda et al. (ISMIR 2024): https://arxiv.org/abs/2408.00473

These are adapted *rules*, not reproductions of the complete research systems.
No notes are invented or retimed: the renderer/grader use original source IDs.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from math import ceil
from typing import Callable, Protocol
from .exercise_generator import ExerciseVariant
from .difficulty import DifficultyEstimator, HeuristicDifficulty
from .music import Phrase

Groups = tuple[tuple[str, tuple[frozenset[int], ...]], ...]
Baseline = Callable[[], tuple[ExerciseVariant, ...]]


@dataclass(frozen=True)
class ExerciseContext:
    phrase: Phrase
    hand: str
    groups: Groups = ()
    max_attacks: int = 8
    min_onsets: int = 2
    kind: str = "learn"
    warmup: bool = False

    @property
    def source_indices(self) -> tuple[int, ...]:
        return tuple(i for i, note in enumerate(self.phrase.notes)
                     if self.hand == "both" or note.hand == self.hand)


class ExerciseStrategy(Protocol):
    @property
    def name(self) -> str: ...

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]: ...


def _variant(context: ExerciseContext, level: str, indices: set[int]) -> ExerciseVariant:
    valid = set(context.source_indices)
    if not indices <= valid:
        raise ValueError(f"{level}: notes outside the original hand/source")
    ordered = tuple(i for i in context.source_indices if i in indices)
    phrase = context.phrase
    return ExerciseVariant(level, Phrase(
        phrase.number, phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
        tuple(phrase.notes[i] for i in ordered)), ordered)


def _finish(context: ExerciseContext,
            proposals: list[tuple[str, set[int]]]) -> tuple[ExerciseVariant, ...]:
    """Deduplicate proposals; require the exact source as the final stage."""
    complete = set(context.source_indices)
    if not complete:
        return ()
    result = []
    seen = set()
    for level, indices in [*proposals, ("original", complete)]:
        indices = set(indices)
        if not indices or (indices == complete and level != "original"):
            continue
        if not indices <= complete:
            raise ValueError(f"{level}: not source traceable")
        identity = frozenset(indices)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(_variant(context, level, indices))
    if result[-1].level != "original":
        result.append(_variant(context, "original", complete))
    return tuple(result)


@dataclass(frozen=True)
class LegacyStrategy:
    """Adapter for the original generator and its lesson-specific filters."""
    name: str = "legacy"

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        return baseline()


@dataclass(frozen=True)
class FukudaStrategy:
    """Outer-voice chord thinning + conservatively isolated returning leaps."""
    name: str = "fukuda"

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        available = set(context.source_indices)
        if not available:
            return ()
        chords = defaultdict(list)
        for i in available:
            note = context.phrase.notes[i]
            chords[(note.hand, note.track, note.voice, round(note.start, 6))].append(i)
        outer = set()
        for members in chords.values():
            members.sort(key=lambda i: (context.phrase.notes[i].pitch, i))
            outer.update((members[0], members[-1]))
        protected = {i for _, groups in context.groups for group in groups for i in group}
        voices = defaultdict(list)
        for members in chords.values():
            if len(members) == 1:
                i = members[0]
                n = context.phrase.notes[i]
                voices[(n.hand, n.track, n.voice)].append(i)
        omit = set()
        for members in voices.values():
            members.sort(key=lambda i: context.phrase.notes[i].start)
            for a, b, c in zip(members, members[1:], members[2:]):
                x, y, z = (context.phrase.notes[i] for i in (a, b, c))
                if (b not in protected and a not in omit and c not in omit
                    and x.start < y.start < z.start
                    and abs(x.pitch - y.pitch) >= 12
                    and abs(z.pitch - y.pitch) >= 12
                    and abs(x.pitch - z.pitch) <= 7):
                    omit.add(b)
        return _finish(context, [
            ("fukuda-leap-chords", outer - omit),
            ("fukuda-outer-voices", outer),
        ])


@dataclass(frozen=True)
class CodaPartStrategy:
    """Coda-inspired part splitting; never cut an authored beam or slur."""
    name: str = "coda-part"

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        source = context.source_indices
        if len(source) <= 1:
            return _finish(context, [])
        times = sorted({round(context.phrase.notes[i].start, 6) for i in source})
        if len(times) < 4:
            return _finish(context, [])
        parent = list(range(len(times)))
        pos = {t: i for i, t in enumerate(times)}

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            parent[find(b)] = find(a)

        for _, onsets in context.groups:
            members = sorted({pos[round(context.phrase.notes[i].start, 6)]
                              for onset in onsets for i in onset if i in source})
            for a, b in zip(members, members[1:]):
                union(a, b)

        blocks = defaultdict(set)
        for i, t in enumerate(times):
            blocks[find(i)].add(t)
        target = max(2, min(context.max_attacks, ceil(len(times) / 2)))
        # Advance through complete source-onset groups. Never split a
        # simultaneous chord, beam or slur; group boundaries remain atomic.
        ordered = sorted(blocks.values(), key=min)
        prefix = set()
        first = second = None
        for block in ordered:
            prefix.update(block)
            if first is None and len(prefix) >= target:
                first = prefix.copy()
            if (first is not None and second is None
                    and len(prefix) >= min(context.max_attacks,
                                            ceil(len(times) * .75))
                    and len(prefix) > len(first)):
                second = prefix.copy()
        proposals = []
        for label, chosen in (("coda-part-a", first), ("coda-part-b", second)):
            if chosen:
                proposals.append((label, {
                    i for i in source
                    if round(context.phrase.notes[i].start, 6) in chosen
                }))
        return _finish(context, proposals)


@dataclass(frozen=True)
class FeatureGatedStrategy:
    """Feature-guided strategy selection; no pretrained RubricNet model."""

    estimator: DifficultyEstimator = HeuristicDifficulty()
    name: str = "feature-gated"

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        notes = tuple(context.phrase.notes[i] for i in context.source_indices)
        estimate = self.estimator.estimate(
            notes, context.phrase.end - context.phrase.start)
        if estimate.level != "challenging":
            return baseline()
        if estimate.focus in ("chords", "leaps"):
            return FukudaStrategy().generate(context, baseline)
        if estimate.focus == "rhythm":
            return CodaPartStrategy().generate(context, baseline)
        return baseline()


@dataclass(frozen=True)
class CompositeStrategy:
    parts: tuple[ExerciseStrategy, ...]

    @property
    def name(self) -> str:
        return "+".join(part.name for part in self.parts)

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        complete = set(context.source_indices)
        proposals = []
        for part in self.parts:
            for variant in part.generate(context, baseline):
                indices = set(variant.source_indices)
                if indices and indices != complete:
                    proposals.append((variant.level, indices))
        proposals.sort(key=lambda pair: (len(pair[1]), pair[0]))
        intersection = set.intersection(*(indices for _, indices in proposals)) if proposals else set()
        cumulative = set()
        nested = []
        if len(intersection) >= 2 and intersection != complete:
            cumulative = intersection
            nested.append(("combined-common", set(cumulative)))
        for level, indices in proposals:
            expanded = cumulative | indices
            if expanded != cumulative and expanded != complete:
                cumulative = expanded
                nested.append((f"combined-{len(nested)+1}-{level}", set(cumulative)))
        return _finish(context, nested)


@dataclass(frozen=True)
class SourcePreservingAdapter:
    """Enforces applicability and common learning constraints for strategies.

    The application can call every strategy identically. The adapter alone
    decides when to delegate to the original generator, and whether proposed
    stages are suitable for the current hand and exercise kind.
    """
    delegate: ExerciseStrategy

    @property
    def name(self) -> str:
        return self.delegate.name

    def generate(self, context: ExerciseContext, baseline: Baseline) -> tuple[ExerciseVariant, ...]:
        if context.warmup or context.kind != "learn" or context.hand == "both":
            return baseline()
        proposed = self.delegate.generate(context, baseline)
        if not proposed or proposed[-1].level != "original":
            raise ValueError("Exercise strategy must finish with the original source")
        if proposed[-1].source_indices != context.source_indices:
            raise ValueError("Exercise strategy changed the original source")
        levels = set()
        for variant in proposed:
            indices = variant.source_indices
            if (not indices or len(set(indices)) != len(indices)
                    or any(i not in context.source_indices for i in indices)
                    or variant.notes != tuple(context.phrase.notes[i] for i in indices)
                    or variant.phrase.start != context.phrase.start
                    or variant.phrase.end != context.phrase.end):
                raise ValueError("Strategy produced an invalid or retimed source variant")
            if variant.level in levels:
                raise ValueError("Strategy produced duplicate level names")
            levels.add(variant.level)
        complete_onsets = len({round(n.start, 6) for n in proposed[-1].notes})
        def attacks(variant: ExerciseVariant) -> int:
            return len({round(n.start, 6) for n in variant.notes})
        prepared = tuple(variant for variant in proposed[:-1]
                         if (attacks(variant) <= context.max_attacks
                             and (complete_onsets < context.min_onsets
                                  or attacks(variant) >= context.min_onsets)))
        if (not prepared and context.phrase.first_bar == context.phrase.last_bar
                and complete_onsets > context.max_attacks):
            return baseline()
        return prepared + proposed[-1:]


_FACTORIES = {
    "legacy": LegacyStrategy,
    "fukuda": FukudaStrategy,
    "coda-part": CodaPartStrategy,
    "feature-gated": FeatureGatedStrategy,
}


# Safe to select in the application: all preserve existing notation/transport timing.
# Experimental timing transformations use a separate contract and are not yet
# live-selectable until rendering and MIDI transport share the same timing map.
APP_STRATEGIES = (
    ("legacy", "Original progression"),
    ("fukuda", "Fukuda · chord and leap simplification"),
    ("coda-part", "Coda · passage splitting"),
    ("feature-gated", "Feature-guided selection"),
    ("fukuda+coda-part", "Fukuda + Coda"),
)


def available_strategies() -> tuple[dict[str, str], ...]:
    return tuple({"id": key, "label": label} for key, label in APP_STRATEGIES)


def resolve_strategy(spec: str | ExerciseStrategy | None) -> ExerciseStrategy:
    if spec is None:
        spec = "legacy"
    if not isinstance(spec, str):
        if (not isinstance(getattr(spec, "name", None), str)
                or not callable(getattr(spec, "generate", None))):
            raise TypeError("Expected a strategy with name and generate")
        return SourcePreservingAdapter(spec)
    names = spec.split("+")
    if not names or any(name not in _FACTORIES for name in names):
        raise ValueError(f"Unknown exercise strategy {spec!r}; choose from "
                         f"{', '.join(_FACTORIES)} or compose with +")
    if len(set(names)) != len(names):
        raise ValueError("A strategy cannot be composed with itself")
    parts = tuple(_FACTORIES[name]() for name in names)
    strategy = parts[0] if len(parts) == 1 else CompositeStrategy(parts)
    return strategy if strategy.name == "legacy" else SourcePreservingAdapter(strategy)
