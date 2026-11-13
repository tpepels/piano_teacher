"""Independent whole-piece lesson generators and immutable course definitions.

Every generator analyzes the complete Piece and provides every exercise plus
its hand-specific playable stages. LearningPlan owns navigation and progress,
not algorithm-specific passage selection.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, Protocol

from .exercise_pipeline import ExerciseStage
from .exercise_generator import ExerciseVariant
from .exercise_strategies import WARMUP_STRATEGY
from .music import Piece,Phrase
from .musical_groups import MusicalGrouping
from .lesson_source_planner import (
    Exercise,build_exercises,_hands_for_learning,source_variants,
)

@dataclass(frozen=True)
class LessonPlanDefinition:
    """Entire executable course produced before any practice takes place."""
    exercises: tuple[Exercise, ...]
    stage_sequences: Mapping[tuple[str, str], tuple[ExerciseStage, ...]]
    generator_name: str
    requires_unique_source_ids: bool = False

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
                source=tuple(n for n in exercise.phrase.notes
                             if hand=="both" or n.hand==hand)
                # Existing built-in warmups intentionally expose all hand
                # tabs, even when the source has no notes for one hand.
                if not stages and exercise.kind=="warmup" and not source:
                    continue
                if not stages or stages[-1].variant.level!="original":
                    raise ValueError("Every generated lesson must end at original MIDI attacks")
                # Existing score fixtures can use repeated/blank source IDs
                # and present their original notes in a different stable
                # order. Compare full source-note multiplicities, not IDs.
                if Counter(stages[-1].variant.notes)!=Counter(source):
                    raise ValueError("Lesson generator changed the terminal original performance")
                levels=[stage.variant.level for stage in stages]
                if len(set(levels))!=len(levels):
                    raise ValueError("Generated lesson contains duplicate stage levels")
                source_ids={n.source_id for n in source}
                for stage in stages:
                    v=stage.variant
                    if v.phrase.start!=exercise.phrase.start or v.phrase.end!=exercise.phrase.end:
                        raise ValueError("Generated stage changed the source passage boundary")
                    if self.requires_unique_source_ids:
                        # MIDI-native generator contracts preserve unique
                        # source identities through notation, Listen and grading.
                        if not v.notes or len({n.source_id for n in v.notes})!=len(v.notes):
                            raise ValueError("Coda stage lost or duplicated MIDI source identities")
                        if not {n.source_id for n in v.notes}<=source_ids:
                            raise ValueError("Coda stage references attacks outside its source hand")
                    else:
                        # Old heuristic strategies use index ownership and
                        # permit synthetic fixtures without stable MIDI IDs.
                        # Do not reinterpret those scores as strict MIDI.
                        if len(set(v.source_indices))!=len(v.source_indices):
                            raise ValueError("Duplicate source indices in generated lesson")
                        if not set(v.source_indices)<=set(range(len(exercise.phrase.notes))):
                            raise ValueError("Lesson stage references an unknown source index")
        object.__setattr__(self,"stage_sequences",
                           MappingProxyType(dict(self.stage_sequences)))

    def stages(self, exercise: Exercise, hand: str) -> tuple[ExerciseStage, ...]:
        return self.stage_sequences[(exercise.key,hand)]


class LessonGenerator(Protocol):
    @property
    def name(self) -> str: ...
    def generate(self, piece: Piece) -> LessonPlanDefinition: ...
    def decide_teaching(self, event, state): ...


def lesson_hands(exercise: Exercise) -> tuple[str,...]:
    if exercise.hands:
        if any(h not in ("right","left","both") for h in exercise.hands):
            raise ValueError("Unknown hand in generated lesson")
        return exercise.hands
    if exercise.kind=="warmup":
        return ("right","left","both")
    if exercise.kind!="learn":
        return ("both",)
    return _hands_for_learning(exercise)


@dataclass(frozen=True)
class SourceLessonGenerator:
    """Source-preserving passage course: the fixed built-in warm-up route.

    Never offered in the strategy picker. It is also the baseline course
    for pieces that no MIDI-only generator accepts (fixtures, tools).
    """
    consolidate: bool = False
    warmup: bool = False
    grouping: MusicalGrouping | None = None
    name: str = WARMUP_STRATEGY

    def decide_teaching(self, event, state):
        from .teaching_decisions import decide_standard_teaching
        return decide_standard_teaching(event, state, generator=self)

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
        result={}
        for ex in exercises:
            for hand in lesson_hands(ex):
                result[(ex.key,hand)]=tuple(
                    ExerciseStage(variant) for variant in source_variants(
                        ex,hand,grouping=self.grouping))
        return LessonPlanDefinition(exercises,result,self.name)


def _coda_piece_sections(piece: Piece, *,
                         first_measure: int = 1,
                         last_measure: int | None = None) -> tuple[Exercise,...]:
    """Adapt the published author endpoint's explicitly chosen excerpt.

    The original /generate route accepts start_measure and end_measure.
    It does not select sections or prescribe learning order. By default
    this MIDI adapter selects the *entire* score, from first to last bar.
    The final performance step is an application teaching policy.
    """
    boundaries=piece.bar_boundaries
    if len(boundaries)<2 or not piece.notes:
        raise ValueError("Coda needs an imported MIDI score with bar boundaries")
    bars=len(boundaries)-1
    last_measure=bars if last_measure is None else last_measure
    if (type(first_measure) is not int or type(last_measure) is not int
            or first_measure<1 or last_measure<first_measure
            or last_measure>bars):
        raise ValueError("Coda excerpt must select an existing measure range")
    start,end=boundaries[first_measure-1],boundaries[last_measure]
    for note in piece.notes:
        if note.start<start-1e-7 and note.end>start+1e-7:
            raise ValueError("MIDI note sustains across Coda excerpt start")
        if note.start<end-1e-7 and note.end>end+1e-7:
            raise ValueError("MIDI note sustains across Coda excerpt end")
    selected=tuple(n for n in piece.notes
                   if start-1e-7<=n.start<end-1e-7)
    if not selected:
        raise ValueError("Coda selected measure range has no MIDI attacks")
    complete=Phrase(1,first_measure,last_measure,start,end,selected)
    present={n.hand for n in selected}
    if not present <= {"right","left"}:
        raise ValueError("Coda requires known MIDI hand assignment")
    hands=tuple(h for h in ("right","left") if h in present)
    if len(hands)==2:
        hands+=("both",)
    if not hands:
        raise ValueError("No playable MIDI hands")
    return (
        Exercise("learn",complete,
                 f"coda:excerpt:{first_measure}-{last_measure}",hands),
        Exercise("perform",complete,
                 f"perform:{first_measure}-{last_measure}"),
    )


@dataclass(frozen=True)
class CodaLessonGenerator:
    """Generate original Coda categories for a caller-selected MIDI excerpt.

    Whole piece (measures 1..end) is the default request. The author does
    not select these measures or define an automatic learning sequence.
    """
    name: str = "coda-midi"
    first_measure: int = 1
    last_measure: int | None = None
    # The research generator still defaults to the complete author-selected
    # excerpt. Only the desktop registration enables bounded teaching units.
    teaching_passages: bool = False

    def decide_teaching(self, event, state):
        from .teaching_decisions import decide_standard_teaching
        return decide_standard_teaching(event, state, generator=self)

    def passage_stages(self, piece: Piece, original: ExerciseVariant, *,
                       kind: str) -> tuple[ExerciseStage, ...]:
        """Contribute source-backed passage stages to any adaptive composer."""
        from .application.coda_midi_curriculum import midi_coda_stages
        phrase = original.phrase
        if (kind == "learn" and
                abs(phrase.end - piece.bar_boundaries[phrase.last_bar]) > 1e-7):
            # Preserve a sounding MIDI release beyond the barline. This
            # particular passage cannot be transformed at authored meter
            # boundaries, but it can still be practised as original notes.
            return (ExerciseStage(original, origin="original",
                                  technique="original",
                                  display_name="Original notes and rhythm"),)
        return midi_coda_stages(piece, (original,), kind=kind)

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if (piece.source_format!="midi" or piece.source_musicxml or
                piece.midi_ticks_per_beat<=0):
            raise ValueError("Coda lesson generation needs an original MIDI piece")
        from .application.coda_midi_curriculum import midi_coda_stages
        if self.teaching_passages:
            if self.first_measure != 1 or self.last_measure is not None:
                raise ValueError("Bounded Coda teaching and explicit excerpts cannot be combined")
            from .adaptive_hybrid_curriculum import _segments
            passages = _segments(piece)
            exercises = []
            for phrase in passages:
                present = {n.hand for n in phrase.notes}
                hands = tuple(h for h in ("right", "left") if h in present)
                if len(hands) == 2:
                    hands += ("both",)
                exercises.append(Exercise(
                    "learn", phrase,
                    f"coda:excerpt:{phrase.first_bar}-{phrase.last_bar}", hands))
            # The original full-piece ending is preserved as one ordinary
            # perform stage; it is never reduced or graded from a scaffold.
            original = _coda_piece_sections(piece)[-1]
            exercises.append(original)
            exercises = tuple(exercises)
        else:
            exercises = _coda_piece_sections(
                piece, first_measure=self.first_measure, last_measure=self.last_measure)
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
                # A note sustained beyond a written bar boundary makes
                # author-style excerpt transformations inapplicable. Keep
                # the original playable passage rather than truncate it.
                applicable = (not self.teaching_passages or ex.kind != "learn"
                    or abs(ex.phrase.end -
                           piece.bar_boundaries[ex.phrase.last_bar]) <= 1e-7)
                stages = (
                    midi_coda_stages(piece,(original,),kind=ex.kind)
                    if applicable else (ExerciseStage(original),))
                if self.teaching_passages and ex.kind == "learn":
                    from .lesson_stage_semantics import distinct_stages
                    stages = (*distinct_stages(stages[:-1], stages[-1]), stages[-1])
                result[(ex.key,hand)] = stages
        return LessonPlanDefinition(exercises,result,self.name,
                                    requires_unique_source_ids=True)


def _fukuda_error_sections(piece: Piece, mistakes: frozenset[str]) -> tuple[Exercise, ...]:
    """Select real source measures around graded MIDI attack mistakes.

    Source boundaries are never retimed or clipped. The entire original
    score remains a separate final performance. Consecutive error bars
    are consolidated and sparse passages expand up to eight bars.
    """
    from bisect import bisect_right
    from .lesson_source_planner import Exercise
    grid=piece.bar_boundaries
    count=len(grid)-1
    errored={max(1,min(count,bisect_right(grid,n.start)-0))
             for n in piece.notes if n.source_id in mistakes}
    if not errored:
        return ()
    segments=[]
    for bar in sorted(errored):
        first=max(1,bar)
        last=min(count,first+1)
        # An error bar may begin while an earlier MIDI note is sounding.
        # Include its original attack, then recheck the earlier boundary:
        # overlapping sustains can require more than one preceding bar.
        while first>1 and any(
                n.start<grid[first-1]-1e-7 and n.end>grid[first-1]+1e-7
                for n in piece.notes):
            first-=1
        while last<count and last-first+1<8:
            chosen=tuple(n for n in piece.notes
                         if grid[first-1]-1e-7<=n.start<grid[last]-1e-7)
            hands={n.hand for n in chosen}
            attacks=[len({round(n.start,7) for n in chosen if n.hand==h})
                     for h in hands]
            sustains=any(n.end>grid[last]+1e-7 for n in chosen)
            if not sustains and attacks and min(attacks)>=3:
                break
            last+=1
        if segments and first<=segments[-1][1]:
            segments[-1]=(segments[-1][0],max(last,segments[-1][1]))
        else:
            segments.append((first,last))
    result=[]
    for first,last in segments:
        selected=tuple(n for n in piece.notes
                       if grid[first-1]-1e-7<=n.start<grid[last]-1e-7)
        if any(n.end>grid[last]+1e-7 for n in selected):
            # Expand the section or reject; never cut a sounding note.
            while last<count and any(n.end>grid[last]+1e-7 for n in selected):
                last+=1
                selected=tuple(n for n in piece.notes
                       if grid[first-1]-1e-7<=n.start<grid[last]-1e-7)
            if any(n.end>grid[last]+1e-7 for n in selected):
                raise ValueError("Fukuda score contains notes past its source grid")
        present=tuple(h for h in ("right","left")
                      if any(n.hand==h for n in selected))
        hands=present+("both",) if len(present)>1 else present
        result.append(Exercise("learn",
            Phrase(len(result)+1,first,last,grid[first-1],grid[last],selected),
            f"fukuda:errors:{first}-{last}",hands))
    return tuple(result)


@dataclass(frozen=True)
class FukudaMidiLessonGenerator:
    """MIDI-only whole-piece Fukuda score reduction.

    Uses the whole source Piece to identify playable source sections and
    build three rule families per hand. An optional note-ID set from
    correctly identified MIDI mistakes restricts simplification to
    previously failed original-source notes. No audio input is accepted.
    """
    mistakes: frozenset[str] | None = None
    name: str = "fukuda-midi"
    consolidate: bool = False

    def decide_teaching(self, event, state):
        from .teaching_decisions import decide_standard_teaching
        return decide_standard_teaching(event, state, generator=self)

    def passage_stages(self, piece: Piece, original: ExerciseVariant, *,
                       kind: str) -> tuple[ExerciseStage, ...]:
        """Contribute MIDI-native reductions without owning passage choice."""
        from .fukuda_midi import fukuda_midi_variants, as_fukuda_stage
        variants = (fukuda_midi_variants(original, bpm=piece.bpm,
                    mistakes=self.mistakes) if kind == "learn" else (original,))
        return tuple(as_fukuda_stage(variant) for variant in variants)

    def with_feedback(
        self, evidence: Mapping[str, str],
        definition: LessonPlanDefinition,
    ) -> "FukudaMidiLessonGenerator":
        """Use graded source events; note-reduction rules select failed IDs."""
        from dataclasses import replace
        failed = frozenset(evidence)
        return replace(self, mistakes=failed) if failed != self.mistakes else self

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if piece.source_format!="midi" or piece.source_musicxml:
            raise ValueError("Fukuda MIDI requires an imported MIDI piece")
        # Whole-score assessment first gives Fukuda's three rule families
        # access to any musical pattern across the original piece, not only
        # whichever two-bar focus window another strategy selected.
        from .lesson_source_planner import Exercise
        last_bar=len(piece.bar_boundaries)-1
        complete=Phrase(1,1,last_bar,piece.bar_boundaries[0],
            max(piece.bar_boundaries[-1],max(n.end for n in piece.notes)),
            piece.notes)
        individual=tuple(h for h in ("right","left")
                         if any(n.hand==h for n in piece.notes))
        exercises=(*(_fukuda_error_sections(piece,self.mistakes)
                       if self.mistakes else (
                           Exercise("learn",complete,"fukuda:whole-score",
                                    individual+("both",) if len(individual)>1 else individual),)),
                   Exercise("perform",complete,"perform:all"))
        result={}
        for exercise in exercises:
            for hand in lesson_hands(exercise):
                selected=tuple((i,n) for i,n in enumerate(exercise.phrase.notes)
                    if hand=="both" or n.hand==hand)
                if not selected:
                    raise ValueError("Fukuda created an empty MIDI hand")
                original=ExerciseVariant("original",
                    Phrase(exercise.phrase.number,exercise.phrase.first_bar,
                        exercise.phrase.last_bar,exercise.phrase.start,
                        exercise.phrase.end,tuple(n for _,n in selected)),
                    tuple(i for i,_ in selected))
                result[(exercise.key, hand)] = self.passage_stages(
                    piece, original, kind=exercise.kind)
        return LessonPlanDefinition(exercises,result,self.name,
                                    requires_unique_source_ids=True)

def compose_lesson_definitions(
    primary: LessonPlanDefinition, augmentation: LessonPlanDefinition, *,
    name: str, merge_matching: bool = True,
) -> LessonPlanDefinition:
    """Combine independent course plans with one original performance.

    Only an equivalent complete learn passage (same note multiset, time grid,
    and hand schedule) may merge its stages. Distinct remedial passages
    remain separate exercises. Every non-original stage retains its author's
    exact notes, tempo policy and source IDs. Colliding level names fail.
    """
    result = dict(primary.stage_sequences)
    base = list(primary.exercises)
    inserted: list[Exercise] = []
    terminal = [ex for ex in base if ex.kind == "perform"]
    if len(terminal) != 1:
        raise ValueError("Composed course requires one terminal performance")
    for overlay in augmentation.exercises:
        if overlay.kind == "perform":
            if (Counter(overlay.phrase.notes) != Counter(terminal[0].phrase.notes)
                    or overlay.phrase.start != terminal[0].phrase.start
                    or overlay.phrase.end != terminal[0].phrase.end):
                raise ValueError("Composed generator changed full-score performance")
            continue
        matching = next((
            ex for ex in base if merge_matching and ex.kind == overlay.kind
            and ex.phrase.start == overlay.phrase.start
            and ex.phrase.end == overlay.phrase.end
            and Counter(ex.phrase.notes) == Counter(overlay.phrase.notes)
            and lesson_hands(ex) == lesson_hands(overlay)
        ), None)
        if matching is None:
            if any(ex.key == overlay.key for ex in (*base, *inserted)):
                raise ValueError("Composed generators collide on lesson key")
            inserted.append(overlay)
            for hand in lesson_hands(overlay):
                result[(overlay.key, hand)] = augmentation.stages(overlay, hand)
            continue
        for hand in lesson_hands(matching):
            before = result[(matching.key, hand)]
            extra = augmentation.stages(overlay, hand)
            if (before[-1].variant.notes != extra[-1].variant.notes or
                    before[-1].variant.phrase != extra[-1].variant.phrase):
                raise ValueError("Cannot merge unrelated source hands")
            prefixes = tuple(s.variant.level for s in (*extra[:-1], *before))
            if len(prefixes) != len(set(prefixes)):
                raise ValueError("Composed algorithms collide on exercise levels")
            result[(matching.key, hand)] = (*extra[:-1], *before)
    if any(ex.kind == "perform" for ex in inserted):
        raise ValueError("Only one final original-score performance is permitted")
    return LessonPlanDefinition(
        (*inserted, *base), result, name,
        requires_unique_source_ids=(
            primary.requires_unique_source_ids or
            augmentation.requires_unique_source_ids))


@dataclass(frozen=True)
class ComposedLessonGenerator:
    """Independent registered whole-piece policies composed in declared order.

    Any registered whole-course generator may participate. Participants
    generate the ungraded core exactly once per initial compilation.
    A feedback-capable participant may additionally supply repaired
    source passages based on assessed original MIDI attacks.
    """
    components: tuple[LessonGenerator, ...]
    name: str
    mistakes: frozenset[str] | None = None
    core: LessonPlanDefinition | None = None
    # Graded source-ID error families use one generator feedback contract.
    # Contributors decide which statuses their musical rules require.
    error_status: tuple[tuple[str, str], ...] = ()

    def decide_teaching(self, event, state):
        from .teaching_decisions import decide_standard_teaching
        return decide_standard_teaching(event, state, generator=self)

    def with_feedback(
        self, evidence: Mapping[str, str], definition: LessonPlanDefinition,
    ) -> "ComposedLessonGenerator":
        from dataclasses import replace
        statuses = tuple(sorted(evidence.items()))
        if statuses == self.error_status and frozenset(evidence) == self.mistakes:
            return self
        core = self.core or (definition if not self.mistakes else None)
        return replace(self, mistakes=frozenset(evidence),
                       error_status=statuses, core=core)

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        if not self.components:
            raise ValueError("Composed curriculum requires generators")
        if self.core is not None:
            combined = self.core
        else:
            combined = self.components[0].generate(piece)
            for generator in self.components[1:]:
                combined = compose_lesson_definitions(
                    combined, generator.generate(piece),
                    name=self.name, merge_matching=True)
            if combined.generator_name != self.name:
                from dataclasses import replace
                combined = replace(combined, generator_name=self.name)
        if self.mistakes:
            # Only feedback-capable components may create remedial lessons.
            # Filter out the baseline score exercise, which is already
            # represented in the full curriculum.
            evidence = dict(self.error_status)
            for generator in self.components:
                feedback_hook = getattr(generator, "with_feedback", None)
                if not callable(feedback_hook):
                    continue
                informed = feedback_hook(evidence, combined)
                responsive = informed.generate(piece)
                repair_exercises = tuple(ex for ex in responsive.exercises
                                         if ex.kind == "learn"
                                         and not any(
                                             old.kind == "learn" and
                                             old.phrase.start == ex.phrase.start and
                                             old.phrase.end == ex.phrase.end and
                                             Counter(old.phrase.notes) ==
                                             Counter(ex.phrase.notes)
                                             for old in combined.exercises))
                if not repair_exercises:
                    continue
                final = next((ex for ex in responsive.exercises
                              if ex.kind == "perform"), None)
                if final is None:
                    raise ValueError("Feedback generator omitted original performance")
                keep_keys = {ex.key for ex in (*repair_exercises, final)}
                subset = LessonPlanDefinition(
                    (*repair_exercises, final),
                    {key: value for key, value in responsive.stage_sequences.items()
                     if key[0] in keep_keys}, informed.name,
                    responsive.requires_unique_source_ids)
                combined = compose_lesson_definitions(
                    combined, subset, name=self.name, merge_matching=False)
        return combined


@dataclass(frozen=True)
class AdaptiveComposedLessonGenerator(ComposedLessonGenerator):
    """Pluggable source-bound passage teaching over independent generators.

    Unlike ordinary complete-course composition, this policy compiles
    contributors' passage stages once, then reselects by the error family.
    It contains no knowledge of any participating algorithm's names.
    """
    catalog: LessonPlanDefinition | None = None
    compiled_components: tuple[tuple[str, str], ...] = ()
    compiled_piece: Piece | None = None

    def with_feedback(
        self, evidence: Mapping[str, str], definition: LessonPlanDefinition,
    ) -> "AdaptiveComposedLessonGenerator":
        from dataclasses import replace
        statuses = tuple(sorted(evidence.items()))
        if statuses == self.error_status and frozenset(evidence) == self.mistakes:
            return self
        return replace(self, mistakes=frozenset(evidence),
                       error_status=statuses)

    def generate(self, piece: Piece) -> LessonPlanDefinition:
        import os
        import time
        from .adaptive_hybrid_curriculum import (
            compile_hybrid_catalog, select_hybrid_stages)
        diagnose = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = time.perf_counter()
        # A dataclass copy can change the contributor set; never serve
        # an old source catalog after an algorithm is replaced.
        component_key = tuple((generator.name, repr(generator))
                              for generator in self.components)
        catalog = self.catalog
        if (catalog is None or self.compiled_components != component_key
                or self.compiled_piece is not piece):
            catalog = compile_hybrid_catalog(
                piece, components=self.components, name=self.name)
            # Immutable catalog is reused for the same source/participants
            # across evidence updates and remains independent of old plans.
            object.__setattr__(self, "catalog", catalog)
            object.__setattr__(self, "compiled_components", component_key)
            object.__setattr__(self, "compiled_piece", piece)
        status = dict(self.error_status)
        for sid in self.mistakes or ():
            status.setdefault(sid, "missed")
        selected = select_hybrid_stages(catalog, status)
        if diagnose:
            print("HYBRID_CATALOG: select",round((time.perf_counter()-began)*1000,1),
                  "ms exercises",len(selected.exercises),flush=True)
        return selected


@dataclass(frozen=True)
class CodaFukudaMidiLessonGenerator(AdaptiveComposedLessonGenerator):
    """Default adaptive MIDI preset using two interchangeable contributors."""
    def decide_teaching(self, event, state):
        from .teaching_decisions import decide_coda_fukuda_teaching
        return decide_coda_fukuda_teaching(event, state, generator=self)

    components: tuple[LessonGenerator, ...] = (
        FukudaMidiLessonGenerator(), CodaLessonGenerator())
    name: str = "coda-fukuda-midi"


@dataclass(frozen=True)
class LessonGeneratorRegistration:
    """One registered whole-course generator, including playback/feedback policy."""
    name: str
    factory: Callable[..., LessonGenerator]
    course_version: int
    midi_only: bool = False
    requires_grouping: bool = False


_REGISTRY: dict[str, LessonGeneratorRegistration] = {}


def register_lesson_generator(registration: LessonGeneratorRegistration) -> None:
    """Register an independent generator without changing LearningPlan or PracticeEngine.

    A registered generator can be built by name; it is not added to the
    settings picker, which offers only the default strategy.
    """
    if not registration.name or registration.course_version < 1:
        raise ValueError("Invalid lesson generator registration")
    if registration.name in _REGISTRY:
        raise ValueError(f"Duplicate lesson generator: {registration.name}")
    _REGISTRY[registration.name] = registration


def lesson_generator_registration(name: str) -> LessonGeneratorRegistration | None:
    return _REGISTRY.get(name)


def build_lesson_generator(
    name: str, *, consolidate: bool, warmup: bool,
    grouping: MusicalGrouping | None, mistakes: frozenset[str] | None,
    feedback: Mapping[str, str] | None = None,
) -> LessonGenerator:
    registered = lesson_generator_registration(name)
    if registered is None:
        raise ValueError(f"No registered lesson generator for {name!r}")
    return registered.factory(
        consolidate=consolidate, warmup=warmup, grouping=grouping,
        mistakes=mistakes, feedback=feedback)


# The built-in warm-up route and the source baseline; not selectable.
register_lesson_generator(LessonGeneratorRegistration(
    WARMUP_STRATEGY,
    lambda **options: SourceLessonGenerator(
        consolidate=options["consolidate"],
        warmup=options["warmup"], grouping=options["grouping"]),
    course_version=4, requires_grouping=True))
# The one selectable strategy (owner decision 2026-11-11).
register_lesson_generator(LessonGeneratorRegistration(
    "coda-fukuda-midi",
    lambda **options: CodaFukudaMidiLessonGenerator(
        mistakes=options["mistakes"],
        error_status=tuple(sorted((options.get("feedback") or {}).items()))),
    course_version=3, midi_only=True))
