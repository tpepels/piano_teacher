"""A compact course with variable focus length for sparse musical material."""
from __future__ import annotations
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, replace
from typing import Mapping
import hashlib
import json
import math
from .exercise_strategies import ExerciseStrategy, resolve_strategy
from .exercise_pipeline import ExerciseStage
from .music import Phrase, Piece
from .exercise_generator import ExerciseVariant
from .exercise_contracts import resolve_timing_strategy, resolve_tempo_strategy
from .musical_groups import grouping_for_piece, MusicalGrouping
from .lesson_settings import SETTINGS
from .tempo_difficulty import suggested_start_bpm
from .repeated_passages import exact_repetition_signature
from .lesson_generators import (
    Exercise, LessonGenerator, build_lesson_generator,
    lesson_generator_registration,
    lesson_hands,
)

@dataclass(frozen=True)
class LessonStep:
    """One teachable stage; three accepted full-target passes earn mastery."""
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
                 tempo_strategy: str = "constant-tempo",
                 lesson_generator: LessonGenerator | None = None,
                 fukuda_mistakes: frozenset[str] | None = None,
                 feedback: Mapping[str, str] | None = None) -> None:
        self.piece = piece
        self.timing_strategy = resolve_timing_strategy(timing_strategy)
        self.tempo_strategy = resolve_tempo_strategy(tempo_strategy)
        # Warmups have their own fixed route; a selected MIDI-Coda policy
        # applies to imported pieces, not the built-in warmup catalog.
        requested = exercise_strategy if exercise_strategy is not None else "source-progression"
        if warmup and (registration := lesson_generator_registration(
                requested if isinstance(requested, str) else requested.name)
                ) is not None and registration.midi_only:
            requested = "source-progression"
        self.exercise_strategy = resolve_strategy(requested,piece=piece)
        self.generator_registration = lesson_generator_registration(
            self.exercise_strategy.name)
        if (self.generator_registration is not None
                and self.generator_registration.owns_timing and
                (self.timing_strategy.name!="original-timing" or
                 self.tempo_strategy.name!="constant-tempo")):
            raise ValueError("Coda MIDI lessons generate their own timing and tempo stages")
        self.warmup = warmup
        # Full-piece MIDI beam inference constructs and reparses MusicXML
        # for *every source attack*. It is only required by generators
        # explicitly declaring grouped-source pedagogy. MIDI-domain Coda /
        # Fukuda authors derive their own groups from their selected passage;
        # compiling source-wide beams for them blocks startup unnecessarily.
        needs_grouping = bool(
            self.generator_registration is not None
            and self.generator_registration.requires_grouping)
        self.grouping = (grouping_for_piece(piece)
                         if not warmup and needs_grouping else None)
        # Produce a complete, immutable course from the entire MIDI Piece
        # before this stateful player owns navigation and mastery.
        self.lesson_generator = lesson_generator or build_lesson_generator(
            self.exercise_strategy.name,
            strategy=self.exercise_strategy, timing=self.timing_strategy,
            tempo=self.tempo_strategy, consolidate=consolidate, warmup=warmup,
            grouping=self.grouping, mistakes=fukuda_mistakes,
            feedback=feedback)
        self.lesson_definition = self.lesson_generator.generate(piece)
        self.exercises = self.lesson_definition.exercises
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
        self._lesson_step_numbers: dict[str, int] = {}

    route_version = 3

    @property
    def profile(self) -> str:
        profile = self.lesson_generator.name
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
        baseline = min(target, max(SETTINGS.minimum_bpm, SETTINGS.start_tempo_bpm))
        return min(target, suggested_start_bpm(
            self.active_phrase, self.hand,
            default_bpm=baseline, minimum_bpm=SETTINGS.minimum_bpm))

    @property
    def exercise(self) -> Exercise:
        return self.exercises[self.index]

    @property
    def hands(self) -> tuple[str, ...]:
        return lesson_hands(self.exercise)

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

    @property
    def accepts_performance_feedback(self) -> bool:
        """Generators opt in through a common immutable feedback hook."""
        return callable(getattr(self.lesson_generator, "with_feedback", None))

    def refresh_from_feedback(
        self, evidence: Mapping[str, str], *, prefer_repair: bool = True,
        focus_ids: frozenset[str] | None = None,
    ) -> bool:
        """Rebuild selected stages from actual original-attack error families."""
        if not isinstance(evidence, Mapping) or any(
                not isinstance(k, str) or not isinstance(v, str)
                for k, v in evidence.items()):
            raise TypeError("Generator needs source-identified MIDI feedback")
        if focus_ids is not None and (
                not isinstance(focus_ids, frozenset)
                or not focus_ids <= evidence.keys()):
            raise ValueError("Focus must identify currently failed source attacks")
        # Previously stored errors may belong to another passage. Never
        # relocate the learner for old evidence during a new assessment.
        target_ids = ((frozenset(evidence) if focus_ids is None else focus_ids)
                      if prefer_repair else frozenset())
        hook = getattr(self.lesson_generator, "with_feedback", None)
        if callable(hook):
            updated = hook(evidence, self.lesson_definition)
            return self._refresh_generator(updated, focus_ids=target_ids)
        return False

    def _refresh_generator(
        self, updated: LessonGenerator, *, focus_ids: frozenset[str],
    ) -> bool:
        """Replan without discarding unaffected progress, BPM or active cursor.

        A failed original-score attempt may enter the relevant new scaffold;
        a successful correction keeps the current lesson if it still exists.
        Repairs that disappear resolve to the nearest remaining source phrase.
        """
        if updated is self.lesson_generator:
            return False
        previous_key = self.identity
        previous_exercise_key = self.exercise.key
        previous_range = (self.active_phrase.first_bar,
                          self.active_phrase.last_bar)
        previous_kind = self.exercise.kind
        previous_hand = self.hand
        previous_level = self.active_variant.level
        previous_bpm = self.bpm
        previous_streak = self.streak
        definition = updated.generate(self.piece)
        old_exercises = self.exercises
        self.lesson_generator = updated
        self.lesson_definition = definition
        self.exercises = definition.exercises
        self._variants_cached = None
        self._lesson_steps_cache = None
        self._lesson_step_numbers = {}
        self._repeated_groups = None
        # Focus a newly diagnosed, actually failed source attack on the first
        # source passage containing it. An existing selected step survives when
        # its source IDs and stage definition are unchanged.
        candidate = None
        if focus_ids and previous_level == "original":
            matching = [(i, ex) for i, ex in enumerate(self.exercises)
                        if ex.kind == "learn" and any(
                            n.source_id in focus_ids for n in ex.phrase.notes)]
            # Prefer the previous source range when a user practised a
            # particular passage, otherwise the earliest diagnosed passage.
            candidate = next(((i, ex) for i, ex in matching
                              if ex.key == previous_exercise_key),
                             matching[0] if matching else None)
        if candidate is not None:
            self.index, target = candidate
            self.hand_index = (self.hands.index(previous_hand)
                               if previous_hand in self.hands else 0)
            self.variant_index = 0
            self.streak = self.failures = 0
            self.bpm = self._tempo_for_current_stage()
            return True
        retained = next((step for step in self.lesson_steps
                         if step.key == previous_key), None)
        if retained is not None:
            self.index = retained.exercise_index
            self.hand_index = self.hands.index(retained.hand)
            self.variant_index = next(i for i, v in enumerate(self.variants)
                                      if v.level == retained.level)
            self.bpm = previous_bpm
            self.streak = previous_streak
            return True
        # Source content may change when a repair disappears. Prefer the same
        # passage and hand; otherwise resume at the next surviving source
        # section instead of arbitrarily restarting at exercise zero.
        nearby = next(((i, ex) for i, ex in enumerate(self.exercises)
                       if ex.key == previous_exercise_key), None)
        if nearby is None:
            nearby = next(((i, ex) for i, ex in enumerate(self.exercises)
                           if ex.kind == previous_kind and
                           ex.phrase.first_bar >= previous_range[0]),
                          (len(self.exercises) - 1, self.exercises[-1]))
        self.index = nearby[0]
        self.hand_index = (self.hands.index(previous_hand)
                           if previous_hand in self.hands else 0)
        self.variant_index = next(
            (i for i, variant in enumerate(self.variants)
             if variant.level == previous_level),
            len(self.variants) - 1 if previous_level == "original" else 0)
        self.streak = self.failures = 0
        self.bpm = self._tempo_for_current_stage()
        return True

    def revisit_source_errors(self, ids: frozenset[str]) -> bool:
        """Repeat a relevant scaffold after a *repeated* original-note failure.

        A second failure can contain the same status/ID as the previous take.
        It still warrants a return to the previously generated simplification;
        no recompilation or mastery transfer is necessary.
        """
        if not ids or self.active_variant.level != "original":
            return False
        target = next(((i, ex) for i, ex in enumerate(self.exercises)
                       if ex.kind == "learn" and any(
                           n.source_id in ids for n in ex.phrase.notes)
                       and any(len(self.lesson_definition.stages(ex, hand)) > 1
                               for hand in lesson_hands(ex))),
                      None)
        if target is None:
            return False
        i, ex = target
        previous_hand = self.hand
        error_hands = {n.hand for n in ex.phrase.notes
                       if n.source_id in ids}
        available = lesson_hands(ex)
        hand = next((h for h in (previous_hand, "right", "left", "both")
                     if h in available
                     and (h == "both" or h in error_hands)
                     and len(self.lesson_definition.stages(ex, h)) > 1),
                    None)
        if hand is None:
            return False
        self.index = i
        self.hand_index = available.index(hand)
        self.variant_index = 0
        self._variants_cached = None
        self.streak = self.failures = 0
        self.bpm = self._tempo_for_current_stage()
        return True

    def _pipeline_stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        """Read the generated course; never choose passages on navigation."""
        return self.lesson_definition.stages(exercise,hand)

    def _stage_variants(self, exercise: Exercise, hand: str) -> tuple[ExerciseVariant, ...]:
        return tuple(stage.variant for stage in self.lesson_definition.stages(exercise,hand))

    def _stage_key(self, exercise: Exercise, hand: str, variant: ExerciseVariant) -> str:
        phrase = variant.phrase
        events = [(n.start - phrase.start, n.end - phrase.start, n.pitch, n.track, n.channel, n.hand)
                  for n in phrase.notes]
        signature = hashlib.sha256(json.dumps((phrase.end - phrase.start, events),
                                             separators=(",", ":")).encode()).hexdigest()[:16]
        # Unique generator identity forbids unrelated mastery or BPM migration.
        profile = ":warmup" if self.warmup else f":{self.profile}"
        # Sparse MIDI-domain Coda transformations change source attack
        # placement relative to the previous v5 catalog. Do not inherit
        # completed steps or tempo mastery under different musical content.
        version = (self.generator_registration.course_version
                   if self.generator_registration is not None
                   else self.route_version)
        return f"course:{version}{profile}:{exercise.key}:{hand}:{variant.level}:{signature}"

    @property
    def lesson_steps(self) -> tuple[LessonStep, ...]:
        """Build once; progress is across hands and levels, not MIDI measures."""
        if self._lesson_steps_cache is None:
            steps: list[LessonStep] = []
            for index, ex in enumerate(self.exercises):
                hands = lesson_hands(ex)
                for hand in hands:
                    for variant in self._stage_variants(ex, hand):
                        steps.append(LessonStep(
                            index, hand, variant.level, self._stage_key(ex, hand, variant),
                            ex.phrase.first_bar, ex.phrase.last_bar,
                            len(variant.notes), ex.kind))
            self._lesson_steps_cache = tuple(steps)
            self._lesson_step_numbers = {
                step.key: index for index, step in enumerate(steps, start=1)}
        return self._lesson_steps_cache

    @property
    def lesson_step_number(self) -> int:
        # The UI queries the current cursor every 20ms. Its stable stage key
        # already identifies the selected lesson; avoid scanning thousands
        # of immutable Hanon course stages for each state snapshot.
        self.lesson_steps
        return self._lesson_step_numbers.get(self.identity, 1)

    @property
    def lesson_steps_mastered(self) -> int:
        self.lesson_steps
        return sum(key in self._lesson_step_numbers for key in self.mastered)

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
        if not preferred and kind == "learn":
            # A previously saved whole-score Coda learn (1..73) must not
            # silently reopen as the final full-piece performance after
            # switching the desktop course to bounded teaching passages.
            # Preserve the starting source measure and seek within the
            # new learning route, even when the old interval no longer fits.
            preferred = [(i, ex) for i, ex in enumerate(self.exercises)
                         if ex.kind == "learn"
                         and ex.phrase.first_bar <= first_bar <= ex.phrase.last_bar]
            if not preferred:
                following = [(i, ex) for i, ex in enumerate(self.exercises)
                             if ex.kind == "learn" and ex.phrase.first_bar >= first_bar]
                if following:
                    closest_bar = min(ex.phrase.first_bar for _, ex in following)
                    preferred = [(i, ex) for i, ex in following
                                 if ex.phrase.first_bar == closest_bar]
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
        """Integer tempo ladder from the active MIDI stage to song target."""
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

    def apply_result(self, *, correct: int, total: int, extras: int = 0,
                     accepted: bool | None = None) -> str:
        """Accepted takes restore tempo; three full target-speed passes earn mastery.

        Recovery slowdowns happen on five pitch errors in a two-bar window.
        Partial retries never call this method.
        """
        if total <= 0:
            return "No notes to assess"
        clean = correct == total and extras == 0 if accepted is None else accepted
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
            label = "Clean" if correct == total and extras == 0 else "Accepted"
            return f"{label} pass {self.streak}/{SETTINGS.clean_runs_to_master} - repeat"
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
