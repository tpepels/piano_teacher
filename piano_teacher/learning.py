"""A compact course with variable focus length for sparse musical material."""
from __future__ import annotations
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math
from .exercise_strategies import ExerciseContext, ExerciseStrategy, resolve_strategy
from .exercise_pipeline import ExercisePipeline, ExerciseStage
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant, generate_variants
from .exercise_contracts import resolve_timing_strategy, resolve_tempo_strategy
from .musical_groups import grouping_for_piece, MusicalGrouping
from .lesson_settings import SETTINGS
from .repeated_passages import exact_repetition_signature

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


@dataclass(frozen=True)
class LessonStep:
    """One teachable stage; three clean target-tempo passes earn mastery."""
    exercise_index: int
    hand: str
    level: str
    key: str
    first_bar: int
    last_bar: int
    required_notes: int
    kind: str


class LearningPlan:
    """Adaptive, manually navigable practice sequence independent of the GUI."""
    def __init__(self, piece: Piece, *, warmup: bool = False,
                 consolidate: bool = False,
                 exercise_strategy: str | ExerciseStrategy | None = None,
                 timing_strategy: str = "original-timing",
                 tempo_strategy: str = "constant-tempo") -> None:
        self.piece = piece
        self.timing_strategy = resolve_timing_strategy(timing_strategy)
        self.tempo_strategy = resolve_tempo_strategy(tempo_strategy)
        self.exercise_strategy = resolve_strategy(
            exercise_strategy if exercise_strategy is not None else "legacy")
        self.pipeline = ExercisePipeline(self.exercise_strategy, self.timing_strategy,
                                         self.tempo_strategy)
        self.warmup = warmup
        self.grouping = (None if warmup else grouping_for_piece(piece))
        if warmup:
            # Warm-ups retain their deliberately complete phrase.
            duration = piece.bar_boundaries[-1] if piece.bar_boundaries else max(n.end for n in piece.notes)
            bars = len(piece.bar_boundaries) - 1 if piece.bar_boundaries else piece.phrases[-1].last_bar
            self.exercises = (Exercise("warmup", Phrase(0, 1, bars, 0.0, duration, piece.notes), "warmup:all"),)
        else:
            self.exercises = build_exercises(piece, consolidate=consolidate,
                                             grouping=self.grouping)
        if not self.exercises:
            raise ValueError("Piece has no practice passages")
        self.index = 0
        self.hand_index = 0
        self.variant_index = 0
        self._variants_cached: tuple | None = None
        self.streak = 0
        self.failures = 0
        self.bpm = self.start_bpm
        self.target_bpm = piece.bpm
        self.mastered: dict[str, int] = {}
        # Tempo is a ladder for each source passage/hand/variant, not just
        # the currently displayed take. Returning to an already practised
        # section must not silently discard its earned BPM progress.
        self.stage_tempos: dict[str, int] = {}
        # Only independently earned tempo advances (clean practice or
        # explicit +BPM), never a settings-target change, are transferable.
        self.transferable_tempos: set[str] = set()
        self._repeated_groups: tuple[dict[str, tuple], dict[tuple, list[str]]] | None = None
        self._lesson_steps_cache: tuple[LessonStep, ...] | None = None

    route_version = 3

    @property
    def profile(self) -> str:
        profile = self.exercise_strategy.name
        if not self.warmup and self.timing_strategy.name != "original-timing":
            profile += "~" + self.timing_strategy.name
        if not self.warmup and self.tempo_strategy.name != "constant-tempo":
            profile += "~" + self.tempo_strategy.name
        return profile

    @property
    def start_bpm(self) -> int:
        if self.warmup:
            return min(getattr(self, "target_bpm", self.piece.bpm), self.piece.bpm)
        target = getattr(self, "target_bpm", self.piece.bpm)
        return min(target, max(SETTINGS.minimum_bpm, SETTINGS.start_tempo_bpm))

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        if self.warmup:
            return ("right", "left", "both")
        if self.exercise.kind != "learn":
            return ("both",)
        return _hands_for_learning(self.exercise)

    @property
    def hand(self) -> str:
        return self.hands[self.hand_index]

    @property
    def stages(self) -> tuple[ExerciseStage, ...]:
        key = (self.index, self.hand)
        if self._variants_cached is None or self._variants_cached[0] != key:
            self._variants_cached = (key, self._pipeline_stages(self.exercise, self.hand))
        return self._variants_cached[1]

    @property
    def variants(self) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.stages)

    def _pipeline_stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        groups = (self.grouping.for_phrase(exercise.phrase, hand)
                  if self.grouping is not None else ())
        context = ExerciseContext(
            exercise.phrase, hand, groups, SETTINGS.focus_max_attacks,
            SETTINGS.focus_min_onsets, exercise.kind, self.warmup)
        return self.pipeline.build(
            context, lambda: self._legacy_stage_variants(exercise, hand),
            source_musicxml=self.piece.source_musicxml)

    def _stage_variants(self, exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        """Compatibility with existing curriculum and persisted stage keys."""
        return tuple(stage.variant for stage in self._pipeline_stages(exercise, hand))

    def _legacy_stage_variants(self, exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        groups = (self.grouping.for_phrase(exercise.phrase, hand)
                  if self.grouping is not None else ())
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

    def _stage_key(self, exercise: Exercise, hand: str, variant: ExerciseVariant) -> str:
        phrase = variant.phrase
        events = [(n.start - phrase.start, n.end - phrase.start, n.pitch, n.track, n.channel, n.hand)
                  for n in phrase.notes]
        signature = hashlib.sha256(json.dumps((phrase.end - phrase.start, events),
                                             separators=(",", ":")).encode()).hexdigest()[:16]
        # Legacy identifiers remain unchanged for existing saved courses.
        # Nonlegacy strategies cannot inherit unrelated completion/tempo credit.
        profile = ("" if self.warmup or self.profile == "legacy"
                   else f":{self.profile}")
        return f"course:{self.route_version}{profile}:{exercise.key}:{hand}:{variant.level}:{signature}"

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                if ex.kind == "learn":
                    hands = _hands_for_learning(ex)
                elif ex.kind == "warmup":
                    hands = ("right", "left", "both")
                else:
                    hands = ("both",)
                for hand in hands:
                    for variant in self._stage_variants(ex, hand):
                        steps.append(LessonStep(
                            index, hand, variant.level, self._stage_key(ex, hand, variant),
                            ex.phrase.first_bar, ex.phrase.last_bar,
                            len(variant.notes), ex.kind))
            self._lesson_steps_cache = tuple(steps)
        return self._lesson_steps_cache

    @property
    def lesson_step_number(self) -> int:
        return next((i + 1 for i, step in enumerate(self.lesson_steps)
                     if step.key == self.identity), 1)

    @property
    def lesson_steps_mastered(self) -> int:
        return sum(step.key in self.mastered for step in self.lesson_steps)

    @property
    def active_stage(self) -> ExerciseStage:
        return self.stages[self.variant_index]

    @property
    def active_variant(self) -> ExerciseVariant:
        return self.active_stage.variant

    @property
    def active_phrase(self) -> Phrase:
        return self.active_variant.phrase

    @property
    def identity(self) -> str:
        return self._stage_key(self.exercise, self.hand, self.active_variant)

    def _repeated_stage_index(self) -> tuple[dict[str, tuple], dict[tuple, list[str]]]:
        if self._repeated_groups is not None:
            return self._repeated_groups
        by_key: dict[str, tuple] = {}
        by_signature: dict[tuple, list[str]] = {}
        for step in self.lesson_steps:
            if step.kind != "learn":
                continue  # Longer bridges/performances must prove themselves.
            exercise = self.exercises[step.exercise_index]
            variant = next(v for v in self._stage_variants(exercise, step.hand)
                           if v.level == step.level)
            signature = exact_repetition_signature(
                self.piece, variant.phrase, step.hand, step.level,
                minimum_attacks=SETTINGS.repeated_tempo_min_attacks)
            if signature is None:
                continue
            by_key[step.key] = signature
            by_signature.setdefault(signature, []).append(step.key)
        self._repeated_groups = by_key, by_signature
        return self._repeated_groups

    def _tempo_for_current_stage(self) -> int:
        # A stage with its own local history keeps its own BPM, including
        # failure-driven slowdowns. Only genuinely UNSEEN repeated passages
        # may inherit a higher starting tempo from already visited stages.
        key = self.identity
        if key in self.stage_tempos:
            return self.stage_tempos[key]
        by_key, by_signature = self._repeated_stage_index()
        signature = by_key.get(key)
        if signature is None:
            return self.start_bpm
        shared = (self.stage_tempos[other]
                  for other in by_signature[signature]
                  if other != key and other in self.stage_tempos
                  and other in self.transferable_tempos)
        return min(self.target_bpm, max([self.start_bpm, *shared]))

    def restore_location(self, *, kind: str, first_bar: int, last_bar: int,
                         hand: str, level: str) -> None:
        """Find saved source material in this course without reusing a stale index."""
        candidates = [(i, ex) for i, ex in enumerate(self.exercises)
                      if ex.phrase.first_bar <= first_bar and ex.phrase.last_bar >= last_bar]
        preferred = [(i, ex) for i, ex in candidates if ex.kind == kind]
        if not preferred:
            preferred = [(i, ex) for i, ex in candidates if ex.kind == "learn"]
        if not preferred and not candidates:
            # Migration from the old 8-bar route: resume at the focused
            # unit containing the old lesson's first source measure.
            preferred = [(i,ex) for i,ex in enumerate(self.exercises)
                         if ex.kind == "learn"
                         and ex.phrase.first_bar <= first_bar <= ex.phrase.last_bar]
        if preferred or candidates:
            self.select(min(preferred or candidates,
                            key=lambda pair: pair[1].phrase.last_bar - pair[1].phrase.first_bar)[0])
        if hand in self.hands:
            self.set_hand(hand)
        self.variant_index = next((i for i, variant in enumerate(self.variants) if variant.level == level), 0)
        self.bpm = self._tempo_for_current_stage()

    def jump(self, amount: int) -> None:
        self.select(min(len(self.exercises) - 1, max(0, self.index + amount)))

    def select_step(self, number: int) -> None:
        """Navigate directly to a hand and variant without awarding mastery."""
        if not 1 <= number <= len(self.lesson_steps):
            raise ValueError("Lesson step out of bounds")
        step = self.lesson_steps[number - 1]
        if step.key == self.identity:
            return
        self.stage_tempos[self.identity] = self.bpm
        self.index = step.exercise_index
        self.hand_index = self.hands.index(step.hand)
        self.variant_index = next(i for i, variant in enumerate(self.variants)
                                  if variant.level == step.level)
        self.bpm = self._tempo_for_current_stage()
        self.streak = 0
        self.failures = 0

    def select(self, index: int) -> None:
        if not 0 <= index < len(self.exercises):
            raise ValueError("Exercise index out of bounds")
        self.stage_tempos[self.identity] = self.bpm
        self.index = index
        self.hand_index = 0
        self.variant_index = 0
        self.bpm = self._tempo_for_current_stage()
        self.streak = 0
        self.failures = 0

    def set_hand(self, hand: str) -> None:
        if hand not in self.hands:
            raise ValueError(f"Hand {hand!r} unavailable")
        self.stage_tempos[self.identity] = self.bpm
        self.hand_index = self.hands.index(hand)
        self.variant_index = 0
        self.streak = self.failures = 0
        self.bpm = self._tempo_for_current_stage()

    def set_bpm(self, bpm: int) -> None:
        if bpm < SETTINGS.minimum_bpm or bpm > SETTINGS.maximum_bpm:
            raise ValueError(f"BPM must be between {SETTINGS.minimum_bpm} and {SETTINGS.maximum_bpm}")
        self.bpm = bpm
        self.target_bpm = bpm
        # Changing the target invalidates old tempo ladders globally.
        self.stage_tempos.clear()
        self.transferable_tempos.clear()
        self.streak = self.failures = 0

    def tempo_rungs(self) -> tuple[int, ...]:
        """Integer tempo ladder with a common start and exact song target."""
        start, target = self.start_bpm, self.target_bpm
        if start >= target:
            return (target,)
        return tuple(sorted(set(
            start + round((target - start) * i / SETTINGS.automatic_tempo_steps)
            for i in range(SETTINGS.automatic_tempo_steps + 1)
        )))

    def _next_automatic_bpm(self) -> int:
        rungs = self.tempo_rungs()
        if self.bpm < rungs[0]:
            # Deliberate manual slowdown below the shared start.
            return min(rungs[0], self.bpm + max(
                SETTINGS.minimum_tempo_step_bpm,
                round((self.target_bpm - rungs[0]) / SETTINGS.automatic_tempo_steps)))
        return next((bpm for bpm in rungs if bpm > self.bpm), self.target_bpm)

    def decrease_tempo(self) -> int:
        """Lower only the active stage tempo; keep the piece's target."""
        if self.bpm > SETTINGS.minimum_bpm:
            self.bpm = max(SETTINGS.minimum_bpm, self.bpm - SETTINGS.manual_tempo_step_bpm)
            self.streak = self.failures = 0
            self.stage_tempos[self.identity] = self.bpm
            if self.bpm <= self.start_bpm:
                self.transferable_tempos.discard(self.identity)
        return self.bpm

    def increase_tempo(self) -> int:
        """Learner skips the slow tempo rungs, not the proof of mastery.

        A manual increase is persisted for this source unit/hand/variant and
        counts towards its target, but never awards a clean run or a new step.
        """
        if self.bpm < self.target_bpm:
            self.bpm = min(self.target_bpm, self.bpm + SETTINGS.manual_tempo_step_bpm)
            self.streak = 0
            self.failures = 0
            self.stage_tempos[self.identity] = self.bpm
            self.transferable_tempos.add(self.identity)
        return self.bpm

    def apply_result(self, *, correct: int, total: int, extras: int = 0) -> str:
        """A clean run restores tempo; three target-speed clean runs confer mastery.

        Recovery slowdowns happen on five pitch errors in a two-bar window.
        Partial retries never call this method.
        """
        if total <= 0:
            return "No notes to assess"
        clean = correct == total and extras == 0
        if not clean:
            self.streak = 0
            self.failures += 1
            return f"Repeat - {correct}/{total} correct, {extras} extra"
        self.failures = 0
        if self.bpm < self.target_bpm:
            self.streak = 0
            self.bpm = self._next_automatic_bpm()
            self.stage_tempos[self.identity] = self.bpm
            self.transferable_tempos.add(self.identity)
            return f"Tempo increased to {self.bpm} BPM"
        self.transferable_tempos.add(self.identity)
        self.streak += 1
        if self.streak < SETTINGS.clean_runs_to_master:
            return f"Clean pass {self.streak}/{SETTINGS.clean_runs_to_master} - repeat"
        self.streak = 0
        previous = self.identity
        self.stage_tempos[previous] = self.bpm
        self.mastered[previous] = self.target_bpm
        if self.variant_index + 1 < len(self.variants):
            self.variant_index += 1
            self.bpm = self._tempo_for_current_stage()
            return f"Mastered {previous}; introducing {self.active_variant.level}"
        if self.hand_index + 1 < len(self.hands):
            self.hand_index += 1
            self.variant_index = 0
            self.bpm = self._tempo_for_current_stage()
            return f"Mastered {previous}; now {self.hand} hand"
        if self.index + 1 < len(self.exercises):
            self.select(self.index + 1)
            return f"Mastered {previous}; next passage"
        return "Piece mastered"
