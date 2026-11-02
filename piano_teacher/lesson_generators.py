"""Whole-piece lesson generators and immutable generated course definitions.

Every generator receives the complete Piece and returns ALL of its exercises
and hand-specific stages before a LearningPlan begins execution. The normal
teaching engine consumes these definitions without knowing which algorithm
selected passage boundaries or created the exercises.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from math import ceil
import math
from statistics import median
from types import MappingProxyType
from typing import Mapping, Protocol

from .exercise_contracts import resolve_timing_strategy, resolve_tempo_strategy
from .exercise_generator import ExerciseVariant, generate_variants
from .exercise_pipeline import ExercisePipeline, ExerciseStage
from .exercise_strategies import ExerciseContext, ExerciseStrategy
from .lesson_settings import SETTINGS
from .music import Piece, Phrase
from .musical_groups import MusicalGrouping, grouping_for_piece

@dataclass(frozen=True)
class Exercise:
    kind: str
    phrase: Phrase
    key: str


def _difficult(phrase: Phrase) -> bool:
    """Keep dense chords and fast/irregular figures in their original short unit.

    This is deliberately a bounded first-course heuristic, not a claim to
    infer musical phrases or a player's skill from a MIDI file.
    """
    duration = max(1.0, phrase.end - phrase.start)
    for hand in ("right", "left"):
        notes = [n for n in phrase.notes if n.hand == hand]
        onsets = sorted({round(n.start, 6) for n in notes})
        chords = Counter(round(n.start, 6) for n in notes)
        density = len(notes) / duration
        irregular = sum(abs(n.start * 2 - round(n.start * 2)) > .05 for n in notes)
        # Near-simultaneous MIDI attacks can be rolled chords, not fast
        # separate figures. A substantial run of short intervals is harder.
        quick = sum(.08 < b - a < .25 - 1e-6 for a, b in zip(onsets, onsets[1:]))
        if (density > 3 or max(chords.values(), default=0) > 4 or quick >= max(3, len(onsets) * .25)
                or (density > 1.5 and irregular > len(notes) * .5)):
            return True
    return False


def _course_phrases(piece: Piece) -> tuple[Phrase, ...]:
    groups: list[Phrase] = []
    pending: list[Phrase] = []

    def flush() -> None:
        if pending:
            first, last = pending[0], pending[-1]
            groups.append(Phrase(len(groups) + 1, first.first_bar, last.last_bar,
                                 first.start, last.end, tuple(n for p in pending for n in p.notes)))
            pending.clear()

    for phrase in piece.phrases:
        hard = _difficult(phrase)
        if pending:
            previous = pending[-1]
            crosses_meter = any(pending[0].start < beat <= phrase.start
                                for beat, _, _ in piece.time_signatures)
            if (hard or previous.last_bar + 1 != phrase.first_bar
                    or abs(previous.end - phrase.start) > 1e-6
                    or phrase.last_bar - pending[0].first_bar + 1 > 8 or crosses_meter):
                flush()
        pending.append(phrase)
        if hard:
            flush()
    flush()
    return tuple(groups)


def _focus_phrases(piece: Piece, *, adaptive: bool = True,
                   grouping: MusicalGrouping | None = None) -> tuple[Phrase, ...]:
    """Keep a short focus by default; extend it when attacks are very sparse.

    Count distinct attack times rather than noteheads: an entire chord is one
    action for the learner. Never split a source measure or exceed the configured
    measure cap. The fixed route is retained solely for older saved sessions.
    """
    if not piece.bar_boundaries:
        return piece.phrases  # Historical fixtures already contain source units.
    boundaries = piece.bar_boundaries
    bars = len(boundaries) - 1
    notes_by_bar: list[list] = [[] for _ in range(bars)]
    # Practice steps split by hand, so a busy left hand must not make a
    # one-note right-hand step look sufficiently dense (or vice versa).
    onsets_by_bar: list[dict[str, set[float]]] = [
        {"right": set(), "left": set()} for _ in range(bars)
    ]
    for note in piece.notes:
        bar = bisect_right(boundaries, note.start + 1e-7) - 1
        if 0 <= bar < bars and boundaries[bar] - 1e-7 <= note.start < boundaries[bar + 1] - 1e-7:
            notes_by_bar[bar].append(note)
            onsets_by_bar[bar][note.hand].add(round(note.start, 6))

    def onsets(first: int, last: int) -> int:
        return len(set().union(*(onsets_by_bar[bar][hand]
                                 for bar in range(first, last)
                                 for hand in ("right", "left"))))

    def within_attack_limit(first: int, last: int) -> bool:
        # The union of onset times is the number of rhythmic attacks a
        # both-hands learner would need. Individual hands are subsets.
        return onsets(first, last) <= SETTINGS.focus_max_attacks

    ranges: list[tuple[int, int]] = []
    start = 0
    while start < bars:
        end = min(bars, start + SETTINGS.focus_measures)
        if onsets(start, end) == 0:
            # Preserve source introduction/trailing rests for the complete
            # performance instead of padding a sparse practice unit with
            # entirely silent opening measures.
            start = end
            continue
        if adaptive:
            # Stop before a measure that would exceed the attack budget.
            # A single dense measure cannot be split at a barline: its
            # individual practice variants are simplified separately.
            while end > start + 1 and not within_attack_limit(start, end):
                end -= 1
            # An underused hand is introduced with BOTH hands instead of
            # forcing an overlong one-note solo lesson. Extend only when
            # the whole passage has too few distinct attacks.
            while (end < bars and end-start < SETTINGS.focus_max_measures
                   and onsets(start, end) < SETTINGS.focus_min_onsets):
                proposed = min(bars, start + SETTINGS.focus_max_measures,
                               end + SETTINGS.focus_measures)
                if not within_attack_limit(start, proposed):
                    # Try one more full measure if a two-measure increment
                    # would be too dense. Never split a musical measure.
                    proposed = end + 1
                if proposed <= end or not within_attack_limit(start, proposed):
                    break
                end = proposed
        # A short authored slur is one teachable unit, including when it
        # crosses a measure boundary. The attack target is soft: if a group
        # starts in this first measure, extend instead of deleting its end.
        # Resolve to a fixpoint because one extension may cross another slur.
        if adaptive and grouping is not None:
            short_slurs = []
            for group in grouping.groups:
                if group.kind == "slur" and group.attack_count <= SETTINGS.focus_max_attacks:
                    times = [piece.notes[next(iter(onset))].start for onset in group.onsets]
                    short_slurs.append((min(times), max(times)))
            for _ in range(len(short_slurs)):
                split = next(((first, last) for first, last in short_slurs
                              if first < boundaries[end] - 1e-7
                              and boundaries[end] <= last + 1e-7), None)
                if split is None:
                    break
                first, last = split
                needed = min(bars, bisect_right(boundaries, last + 1e-7))
                first_bar = bisect_right(boundaries, first + 1e-7) - 1
                # Prefer normal-budget extensions, then a clean boundary
                # before the phrase. If neither works, accept an overfull
                # lesson, provided the eight-measure safety cap still holds.
                if (needed - start <= SETTINGS.focus_max_measures
                        and within_attack_limit(start, needed)):
                    end = needed
                elif first_bar > start and onsets(start, first_bar):
                    end = first_bar
                elif needed - start <= SETTINGS.focus_max_measures:
                    end = needed
                else:
                    # Exceptionally long short-note slur (>8 measures).
                    # Preserve the hard bar cap and leave sectional practice.
                    break
        ranges.append((start, end))
        start = end

    # Avoid a final one-action fragment when its preceding unit has room.
    if adaptive and len(ranges) > 1:
        first, last = ranges[-1]
        previous_first, _ = ranges[-2]
        if (0 < onsets(first, last) < SETTINGS.focus_min_onsets
                and last - previous_first <= SETTINGS.focus_max_measures
                and within_attack_limit(previous_first, last)):
            ranges[-2:] = [(previous_first, last)]

    groups: list[Phrase] = []
    for first, last in ranges:
        selected = tuple(n for bar in notes_by_bar[first:last] for n in bar)
        if selected:
            groups.append(Phrase(len(groups) + 1, first + 1, last,
                                 boundaries[first], boundaries[last], selected))
    return tuple(groups)

def build_exercises(piece: Piece, *, consolidate: bool = True,
                    adaptive_focus: bool = True,
                    grouping: MusicalGrouping | None = None) -> tuple[Exercise, ...]:
    """Learn sections, bridge their boundaries, then perform the complete source.

    The original two-bar sequence remains reconstructible for old progress.
    """
    if not consolidate and adaptive_focus and grouping is None:
        grouping = grouping_for_piece(piece)
    phrases = (_course_phrases(piece) if consolidate
               else _focus_phrases(piece, adaptive=adaptive_focus,
                                   grouping=grouping))
    exercises: list[Exercise] = []
    for index, phrase in enumerate(phrases):
        exercises.append(Exercise("learn", phrase, f"learn:{phrase.first_bar}-{phrase.last_bar}"))
        if index > 0:
            prev = phrases[index - 1]
            # Do not imply continuity if there is a silent/gapped passage.
            if prev.last_bar + 1 == phrase.first_bar:
                # Connect the last two source measures of the preceding
                # focus to the first two of the next, even for long sparse units.
                first_bar = max(prev.first_bar, prev.last_bar - 1)
                last_bar = min(phrase.last_bar, phrase.first_bar + 1)
                if piece.bar_boundaries:
                    start = piece.bar_boundaries[first_bar - 1]
                    end = piece.bar_boundaries[last_bar]
                else:
                    source = [p for p in piece.phrases
                              if p.first_bar >= first_bar and p.last_bar <= last_bar]
                    start, end = (source[0].start, source[-1].end) if source else (prev.start, phrase.end)
                joined = Phrase(0, first_bar, last_bar, start, end,
                                tuple(n for n in piece.notes if start <= n.start < end))
                # A bridge must contain an attack on each side of the seam.
                # With widely spaced notes, adjacent printed measures can
                # be silent; do not create a misleading one-sided exercise.
                if (any(n.start < phrase.start for n in joined.notes)
                        and any(n.start >= phrase.start for n in joined.notes)
                        and len({round(n.start, 6) for n in joined.notes})
                            <= SETTINGS.focus_max_attacks):
                    exercises.append(Exercise("connect", joined,
                                              f"connect:{joined.first_bar}-{joined.last_bar}"))
    last_release = max((n.end for n in piece.notes), default=phrases[-1].end) if phrases else 0.0
    source_end = piece.bar_boundaries[-1] if piece.bar_boundaries else last_release
    source_start = piece.bar_boundaries[0] if piece.bar_boundaries else 0.0
    if phrases and (len(phrases) > 1 or (consolidate and len(piece.phrases) > 1)
                    or source_start < phrases[0].start - 1e-6
                    or max(last_release, source_end) > phrases[-1].end + 1e-6):
        # Empty-onset measures are omitted from targeted source passages, but
        # the complete performance includes introduction rests and held endings.
        start = piece.bar_boundaries[0] if piece.bar_boundaries else phrases[0].start
        end = max(phrases[-1].end, last_release, piece.bar_boundaries[-1] if piece.bar_boundaries else 0)
        first_bar = 1 if piece.bar_boundaries else phrases[0].first_bar
        if piece.bar_boundaries and piece.bar_boundaries[-1] >= last_release:
            last_bar = len(piece.bar_boundaries) - 1
        else:
            beats_per_bar = (phrases[-1].end - phrases[-1].start) / max(1, phrases[-1].last_bar - phrases[-1].first_bar + 1)
            last_bar = phrases[-1].last_bar + math.ceil(max(0, end - phrases[-1].end) / beats_per_bar)
        combined = Phrase(0, first_bar, last_bar, start, end, piece.notes)
        exercises.append(Exercise("perform", combined, "perform:all"))
    return tuple(exercises)



def _sample_attack_times(times: list[float], limit: int) -> set[float]:
    """Choose source attacks across the whole measure, including its ends."""
    if len(times) <= limit:
        return set(times)
    if limit <= 1:
        return {times[0]}
    return {times[round(i * (len(times) - 1) / (limit - 1))]
            for i in range(limit)}


def _dense_single_measure_variants(phrase: Phrase, hand: str, *,
                                   groups=()) -> tuple[ExerciseVariant, ...]:
    """Learn a too-dense source measure in nested subsets, then all notes.

    No MIDI note is synthesized or moved, and the final stage contains the
    complete original source, even though it necessarily exceeds the budget.
    A chord counts once because notes at the same onset remain together.
    """
    if groups:
        return generate_variants(phrase, hand, groups=groups,
                                 max_attacks=SETTINGS.focus_max_attacks)
    indexed = [(i, n) for i, n in enumerate(phrase.notes)
               if hand == "both" or n.hand == hand]
    times = sorted({round(n.start, 6) for _, n in indexed})
    limit = SETTINGS.focus_max_attacks
    if len(times) <= limit:
        return generate_variants(phrase, hand)
    # Existing on-beat skeleton provides musically meaningful landmarks;
    # spread additional attacks evenly rather than shifting MIDI timing.
    generated = generate_variants(phrase, hand)
    foundation_size = max(2, limit // 2)
    foundation_times = sorted({round(n.start, 6) for n in generated[0].notes})
    foundation = _sample_attack_times(foundation_times, foundation_size)
    if len(foundation) < min(foundation_size, len(times)):
        foundation.update(_sample_attack_times(times, foundation_size))
        if len(foundation) > foundation_size:
            foundation = _sample_attack_times(sorted(foundation), foundation_size)
    extra = [t for t in times if t not in foundation]
    outline = foundation | _sample_attack_times(extra, limit - len(foundation))
    variants: list[ExerciseVariant] = []
    for level, selected_times in (
        ("skeleton", foundation), ("outline", outline),
        ("original", set(times)),
    ):
        chosen = [(i, n) for i, n in indexed
                  if round(n.start, 6) in selected_times]
        indices = tuple(i for i, _ in chosen)
        if variants and indices == variants[-1].source_indices:
            continue
        subset = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                        phrase.start, phrase.end, tuple(n for _, n in chosen))
        variants.append(ExerciseVariant(level, subset, indices))
    return tuple(variants)


def _hands_for_learning(exercise: Exercise) -> tuple[str, ...]:
    """Omit unproductive solo-hand drills, never omit their source notes.

    For two-hand passages, a hand needs the configured minimum number of
    distinct rhythmic onsets to justify its own stage. Both hands together
    always remain in the course. If only one hand exists, keep that solo
    stage, including a genuine one-attack passage at the length limit.
    """
    available = {note.hand for note in exercise.phrase.notes}
    individual = tuple(hand for hand in ("right", "left") if hand in available)
    if len(individual) < 2:
        return individual
    useful = tuple(hand for hand in individual
                   if len({round(note.start, 6) for note in exercise.phrase.notes
                           if note.hand == hand}) >= SETTINGS.focus_min_onsets)
    return useful + ("both",)


def source_variants(exercise: Exercise, hand: str, *,
                    grouping: MusicalGrouping | None = None) -> tuple[ExerciseVariant, ...]:
    """Identical source-preserving baseline used by all course generators."""
        groups = (grouping.for_phrase(exercise.phrase, hand)
                  if grouping is not None else ())
        variants = generate_variants(exercise.phrase, hand, groups=groups,
                                     max_attacks=SETTINGS.focus_max_attacks)
        if exercise.kind != "learn":
            return variants[-1:]
        if (exercise.phrase.first_bar == exercise.phrase.last_bar
                and len({round(n.start, 6) for n in exercise.phrase.notes
                         if hand == "both" or n.hand == hand})
                    > SETTINGS.focus_max_attacks):
            return _dense_single_measure_variants(exercise.phrase, hand,
                                                   groups=groups)
        if hand == "both":
            return variants[-1:]
        if len(variants) == 3:
            skeleton, outline, original = variants
            # A nearly identical middle stage adds repetition without a
            # substantial change in the playable note set.
            if min(len(outline.notes) - len(skeleton.notes),
                   len(original.notes) - len(outline.notes)) <= len(original.notes) * .15:
                variants = (skeleton, original)
        notes = variants[-1].notes if variants else ()
        onsets = sorted({round(n.start, 6) for n in notes})
        # A simplified skeleton must not create a one-note lesson when the
        # original exercise has more playable attacks. Such a stage adds no
        # useful practice and looks like an accidental short passage.
        if len(onsets) >= SETTINGS.focus_min_onsets:
            variants = tuple(v for v in variants
                             if v.level == "original"
                             or len({round(n.start, 6) for n in v.notes})
                                >= SETTINGS.focus_min_onsets)
        trivial = (len(onsets) == len(notes)
                   and len(notes) <= max(1.0, exercise.phrase.end - exercise.phrase.start)
                   and all(b - a >= .5 - 1e-6 for a, b in zip(onsets, onsets[1:]))
                   and all(abs(n.start * 2 - round(n.start * 2)) < .05 for n in notes))
        return variants[-1:] if trivial else variants



@dataclass(frozen=True)
class LessonPlanDefinition:
    """Entire executable course produced before any practice takes place."""
    exercises: tuple[Exercise, ...]
    stage_sequences: Mapping[tuple[str, str], tuple[ExerciseStage, ...]]
    generator_name: str

    def __post_init__(self):
        if not self.exercises or len({x.key for x in self.exercises})!=len(self.exercises):
            raise ValueError("Lesson generator must return uniquely identified exercises")
        keys={(exercise.key,hand)
              for exercise in self.exercises
              for hand in lesson_hands(exercise)}
        if set(self.stage_sequences)!=keys:
            raise ValueError("Lesson generator omitted or invented a hand-specific lesson")
        for exercise in self.exercises:
            for hand in lesson_hands(exercise):
                stages=self.stage_sequences[(exercise.key,hand)]
                if not stages or stages[-1].variant.level!="original":
                    raise ValueError("Every generated lesson must end at original MIDI attacks")
                source=tuple(n for n in exercise.phrase.notes
                             if hand=="both" or n.hand==hand)
                if stages[-1].variant.notes!=source:
                    raise ValueError("Lesson generator changed the terminal original performance")
                levels=[stage.variant.level for stage in stages]
                if len(set(levels))!=len(levels):
                    raise ValueError("Generated lesson contains duplicate stage levels")
                source_ids={n.source_id for n in source}
                for stage in stages:
                    v=stage.variant
                    if v.phrase.start!=exercise.phrase.start or v.phrase.end!=exercise.phrase.end:
                        raise ValueError("Generated stage changed the source passage boundary")
                    if not v.notes or len({n.source_id for n in v.notes})!=len(v.notes):
                        raise ValueError("Generated stage lost or duplicated MIDI source identities")
                    if not {n.source_id for n in v.notes}<=source_ids:
                        raise ValueError("Generated stage references attacks outside its source hand")
        object.__setattr__(self,"stage_sequences",
                           MappingProxyType(dict(self.stage_sequences)))

    def stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        return self.stage_sequences[(exercise.key,hand)]


class LessonGenerator(Protocol):
    @property
    def name(self) -> str: ...
    def generate(self, piece: Piece) -> LessonPlanDefinition: ...


def lesson_hands(exercise: Exercise) -> tuple[str,...]:
    if exercise.kind=="warmup":
        return ("right","left","both")
    if exercise.kind!="learn":
        return ("both",)
    return _hands_for_learning(exercise)


@dataclass(frozen=True)
class HeuristicLessonGenerator:
    """Prior adaptive passage builder, isolated behind a whole-piece interface."""
    strategy: ExerciseStrategy
    timing_strategy: object
    tempo_strategy: object
    consolidate: bool = False
    warmup: bool = False
    grouping: MusicalGrouping | None = None

    @property
    def name(self) -> str:
        return self.strategy.name

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if self.warmup:
            duration=piece.bar_boundaries[-1] if piece.bar_boundaries else max(
                n.end for n in piece.notes)
            bars=(len(piece.bar_boundaries)-1 if piece.bar_boundaries
                  else piece.phrases[-1].last_bar)
            exercises=(Exercise("warmup",
                        Phrase(0,1,bars,0.0,duration,piece.notes),"warmup:all"),)
        else:
            exercises=build_exercises(piece,consolidate=self.consolidate,
                                      grouping=self.grouping)
        pipeline=ExercisePipeline(self.strategy,self.timing_strategy,self.tempo_strategy)
        result={}
        for ex in exercises:
            for hand in lesson_hands(ex):
                groups=(self.grouping.for_phrase(ex.phrase,hand)
                        if self.grouping is not None else ())
                context=ExerciseContext(
                    ex.phrase,hand,groups,SETTINGS.focus_max_attacks,
                    SETTINGS.focus_min_onsets,ex.kind,self.warmup)
                result[(ex.key,hand)]=pipeline.build(
                    context,
                    lambda ex=ex,hand=hand: source_variants(
                        ex,hand,grouping=self.grouping),
                    source_musicxml=piece.source_musicxml)
        return LessonPlanDefinition(exercises,result,self.name)


def _coda_piece_sections(piece: Piece) -> tuple[Exercise,...]:
    """Plan a whole MIDI score using global note density and score structure.

    Coda owns passage boundaries: no call to heuristic build_exercises(),
    _focus_phrases() or preselected LearningPlan exercises.
    """
    grid=piece.bar_boundaries
    if len(grid)<2:
        raise ValueError("Whole-piece Coda requires a reliable MIDI bar grid")
    bars=len(grid)-1
    note_bars=[[] for _ in range(bars)]
    attacks=[set() for _ in range(bars)]
    for note in piece.notes:
        i=bisect_right(grid,note.start+1e-7)-1
        if 0<=i<bars and note.start<grid[i+1]-1e-7:
            note_bars[i].append(note)
            attacks[i].add(round(note.start,7))
    nonempty=[len(a) for a in attacks if a]
    if not nonempty:
        raise ValueError("MIDI piece contains no rhythmic attacks")
    # This target comes from the WHOLE piece rather than a fixed 2-bar
    # local heuristic: dense scores shorten sections; sparse scores extend.
    target=min(SETTINGS.focus_max_attacks,
               max(SETTINGS.focus_min_onsets,int(round(2*median(nonempty)))))
    spans=[]
    start=0
    while start<bars:
        end=start
        count=0
        while end<bars and end-start<SETTINGS.focus_max_measures:
            if end>start and any(
                grid[end-1]+1e-7<t<=grid[end]+1e-7
                for t,_,_ in piece.time_signatures):
                break
            proposed=count+len(attacks[end])
            if end>start+1 and count>=SETTINGS.focus_min_onsets and proposed>target:
                break
            count=proposed
            end+=1
            if count>=target and end-start>=2:
                break
        if end<=start:
            end=start+1
        if count:
            spans.append((start,end))
        start=end
    exercises=[]
    for first,last in spans:
        notes=tuple(n for bar in note_bars[first:last] for n in bar)
        phrase=Phrase(len(exercises)+1,first+1,last,grid[first],grid[last],notes)
        exercises.append(Exercise("learn",phrase,f"learn:{first+1}-{last}"))
    if not exercises:
        raise ValueError("Whole MIDI piece has no teachable attacks")
    # A real full-piece performance is ALWAYS the terminal lesson, even
    # for a one-section piece or for long introductory/trailing rests.
    complete=Phrase(0,1,bars,grid[0],
                    max(grid[-1],max(n.end for n in piece.notes)),piece.notes)
    exercises.append(Exercise("perform",complete,"perform:all"))
    return tuple(exercises)


@dataclass(frozen=True)
class CodaLessonGenerator:
    """Analyze the whole MIDI Piece before selecting exercises and levels."""
    name: str = "coda-midi"

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if (piece.source_format!="midi" or piece.source_musicxml or
                piece.midi_ticks_per_beat<=0):
            raise ValueError("Coda lesson generation needs an original MIDI piece")
        from .application.coda_midi_curriculum import midi_coda_stages
        exercises=_coda_piece_sections(piece)
        result={}
        for ex in exercises:
            for hand in lesson_hands(ex):
                selected=tuple((i,n) for i,n in enumerate(ex.phrase.notes)
                               if hand=="both" or n.hand==hand)
                if not selected:
                    raise ValueError("Coda created an empty hand lesson")
                original=ExerciseVariant(
                    "original",
                    Phrase(ex.phrase.number,ex.phrase.first_bar,ex.phrase.last_bar,
                           ex.phrase.start,ex.phrase.end,tuple(n for _,n in selected)),
                    tuple(i for i,_ in selected))
                result[(ex.key,hand)]=midi_coda_stages(
                    piece,(original,),kind=ex.kind)
        return LessonPlanDefinition(exercises,result,self.name)
