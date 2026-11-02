"""Source-bound learner progress queries and trouble persistence.

The caller holds the application lock while lending a live LearningPlan to a
call. Only the existing LearnerStateStore is retained here; its connection and
the plan's selection, transport, teaching and timed mastery remain caller-owned.
"""
from __future__ import annotations

from collections.abc import Iterable
import math

from ..learning import LearningPlan
from ..learner_state import LearnerStateStore, guided_units, next_guided_unit, placement_candidate
from ..practice import NoteAssessment


class LearnerProgress:
    def __init__(self, store: LearnerStateStore):
        self._store = store

    def saved(self, plan: LearningPlan | None, *, fingerprint: str,
              stage_key: str | None = None) -> dict:
        if fingerprint and plan is not None:
            return self._store.read(fingerprint, stage_key or plan.identity)
        # Older in-process clients can bind an unsaved plan directly.
        return {"resume_unit": None, "completed_units": [], "trouble_units": [],
                "skip_status": "active", "skip_reason": ""}

    @staticmethod
    def guided_unit(plan: LearningPlan | None, *, mode: str,
                    guided_range: tuple[float, float] | None) -> dict | None:
        if plan is None or mode != "learn" or guided_range is None:
            return None
        return next((unit for unit in guided_units(plan.active_variant, plan.piece.bar_boundaries)
                     if (unit["start_beat"], unit["end_beat"]) == guided_range), None)

    @staticmethod
    def next_course_unit(variant, boundaries: tuple[float, ...],
                         saved: dict, *, explicit_learn: bool) -> dict | None:
        """Find the first unfinished guided idea, or restart learning on request.

        Saved progress is an explicit input; this selection never mutates
        the plan, invokes the teaching controller or awards mastery.
        """
        unit = next_guided_unit(variant, boundaries, saved)
        if unit is None and explicit_learn:
            unit = next(iter(guided_units(variant, boundaries)), None)
        return unit

    def save_resume(self, *, fingerprint: str, stage_key: str,
                    unit: dict | None) -> None:
        if fingerprint and unit is not None:
            self._store.save_resume(fingerprint, stage_key, unit)

    def resolve_trouble(self, *, fingerprint: str, stage_key: str) -> None:
        if fingerprint:
            self._store.resolve_trouble(fingerprint, stage_key)

    def record_rolling_trouble(
        self, *, fingerprint: str, stage_key: str, unit: dict,
        assessed_notes: Iterable[NoteAssessment], phrase_start: float,
    ) -> None:
        """Record only errors inside the selected source-bound guided idea.

        Rolling assessment may include the preceding idea. Its other notes
        must not leak into this unit's persistent trouble fingerprint.
        """
        if not fingerprint:
            return
        begin = phrase_start + unit["start_beat"]
        end = phrase_start + unit["end_beat"]
        errors = [entry for entry in assessed_notes
                  if entry.status in ("missed", "wrong")
                  and begin <= entry.note.start < end]
        pitches = sorted({entry.note.pitch for entry in errors})
        self._store.record_trouble(
            fingerprint, stage_key, unit, errors=len(errors), pitches=pitches)
        self._store.save_resume(fingerprint, stage_key, unit)

    def record_guided_preparation(self, *, fingerprint: str,
                                  stage_key: str, unit: dict | None,
                                  assisted_count: int) -> None:
        """Persist a completed guided idea without changing lesson routing.

        The engine verifies that the teaching controller has completed the
        idea and prevents duplicate writes within the current attempt.
        """
        if unit is not None and fingerprint:
            self._store.complete_unit(fingerprint, stage_key, unit,
                                      assisted=assisted_count > 0)

    def snapshot(self, plan: LearningPlan, *, fingerprint: str, mode: str,
                 guided_range: tuple[float, float] | None, course_guided: bool) -> dict:
        units = guided_units(plan.active_variant, plan.piece.bar_boundaries)
        saved = self.saved(plan, fingerprint=fingerprint)
        saved["trouble_units"] = [{key: value for key, value in spot.items() if key != "stage_key"}
            for spot in self.valid_trouble_spots(plan, fingerprint=fingerprint,
                                                stage_key=plan.identity)]
        current = self.guided_unit(plan, mode=mode, guided_range=guided_range)
        completed = saved["completed_units"]
        prepared = sum(any(all(unit[field] == previous.get(field)
                               for field in ("start_beat", "end_beat", "source_indices"))
                           for previous in completed) for unit in units)
        next_state = saved if current is None else {**saved, "resume_unit": None,
                                                    "completed_units": completed+[current]}
        following = next_guided_unit(plan.active_variant, plan.piece.bar_boundaries, next_state)
        return {**saved, "course_guided": course_guided, "prepared_units": prepared,
                "total_units": len(units), "current_unit": current, "next_unit": following,
                "unit_number": next((i+1 for i, unit in enumerate(units) if unit == current), 0)}

    @staticmethod
    def next_skippable_step(plan: LearningPlan | None, reason):
        if (plan is None or not isinstance(reason, str) or not reason.strip()
                or plan.lesson_step_number >= len(plan.lesson_steps)):
            raise ValueError("Choose an available next step and explain the skip")
        return plan.lesson_steps[plan.lesson_step_number]

    def mark_skipped(self, *, fingerprint: str, stage_key: str, reason: str) -> None:
        if fingerprint:
            self._store.mark_skipped(fingerprint, stage_key, reason=reason)

    @staticmethod
    def original_placement_step(plan: LearningPlan):
        candidate = placement_candidate(plan)
        if candidate is None:
            raise ValueError("You are already playing the original notes")
        return candidate

    def mark_prior_steps_placed(self, plan: LearningPlan, *, fingerprint: str,
                                candidate) -> None:
        if not fingerprint:
            return
        for step in plan.lesson_steps[plan.lesson_step_number-1:]:
            if step.key == candidate.key:
                break
            self._store.mark_skipped(fingerprint, step.key,
                reason="Student chose to try the original notes", status="placed")

    def choose_trouble_spot(self, plan: LearningPlan | None, *, fingerprint: str,
                            stage_key, start_beat):
        """Validate the current source binding before interrupting playback."""
        if (plan is None or not fingerprint or not isinstance(stage_key, str)
                or isinstance(start_beat, bool) or not isinstance(start_beat, (int, float))
                or not math.isfinite(start_beat)):
            raise ValueError("Choose a saved trouble spot for this piece")
        step = next((step for step in plan.lesson_steps if step.key == stage_key), None)
        stored = next((unit for unit in self.valid_trouble_spots(
                           plan, fingerprint=fingerprint, stage_key=stage_key)
                       if unit["stage_key"] == stage_key
                       and unit["start_beat"] == start_beat), None)
        if step is None or stored is None:
            raise ValueError("This trouble spot is no longer available")
        return step, stored

    def reactivate_trouble(self, *, fingerprint: str, stage_key: str) -> None:
        self._store.reactivate(fingerprint, stage_key)

    def valid_trouble_spots(self, plan: LearningPlan | None, *, fingerprint: str,
                           stage_key: str | None = None) -> list[dict]:
        if plan is None or not fingerprint:
            return []
        steps = {step.key: step for step in plan.lesson_steps}
        canonical = {}
        valid = []
        for stored in self._store.trouble_for_piece(fingerprint):
            key = stored["stage_key"]
            step = steps.get(key)
            if step is None or (stage_key is not None and stage_key != key):
                continue
            if key not in canonical:
                variant = next((variant for variant in plan._stage_variants(
                    plan.exercises[step.exercise_index], step.hand) if variant.level == step.level), None)
                canonical[key] = guided_units(variant, plan.piece.bar_boundaries) if variant else ()
            unit = next((unit for unit in canonical[key]
                         if all(unit[field] == stored.get(field)
                                for field in ("start_beat", "end_beat", "source_indices"))), None)
            if unit is not None:
                valid.append({**stored, **unit})
        return valid

    def record_saved_trouble(self, plan: LearningPlan, *, fingerprint: str,
                             phrase_start: float, assessed_notes: Iterable[NoteAssessment],
                             start: float, end: float, errors: int) -> None:
        """Persist a canonical idea and resume cursor from settled assessment facts.

        Pitches describe the source notes that need work, including timing and
        duration errors. The caller decides whether a take is partial or earns
        mastery; this write grants neither preparation nor timed credit.
        """
        if not fingerprint:
            return
        unit = next((unit for unit in guided_units(plan.active_variant, plan.piece.bar_boundaries)
                     if unit["start_beat"] == start and unit["end_beat"] == end), None)
        # Silent or partial ranges cannot become a guided key-finding task.
        if unit is None:
            return
        pitches = sorted({entry.note.pitch for entry in assessed_notes if entry.status != "correct"
                          and phrase_start+start <= entry.note.start < phrase_start+end})
        self._store.record_trouble(fingerprint, plan.identity, unit, errors=errors, pitches=pitches)
        self._store.save_resume(fingerprint, plan.identity, unit)

    def lesson_overview(self, plan: LearningPlan | None, *, fingerprint: str) -> dict:
        """Return the readable curriculum without navigating or awarding credit."""
        if plan is None:
            raise ValueError("Open a piece first")
        from ..lesson_stage_semantics import describe
        steps = []
        for i, step in enumerate(plan.lesson_steps):
            saved = self.saved(plan, fingerprint=fingerprint, stage_key=step.key)
            label = step.level
            family = "Practice"
            change = "source notes"
            if plan.generator_registration is not None and plan.generator_registration.midi_only:
                ex = plan.exercises[step.exercise_index]
                candidates = plan.lesson_definition.stages(ex, step.hand)
                current = next(s for s in candidates if s.variant.level == step.level)
                detail = describe(current, candidates[-1])
                label = detail["label"]
                family = detail["family"]
                change = detail["change"]
            steps.append({
                "number": i+1, "exercise": step.exercise_index+1,
                "hand": step.hand, "level": step.level,
                "stage_label": label, "stage_family": family,
                "stage_change": change, "key": step.key,
                "kind": step.kind, "first_bar": step.first_bar,
                "last_bar": step.last_bar, "required_notes": step.required_notes,
                "completed": step.key in plan.mastered,
                "skip_status": saved["skip_status"], "skip_reason": saved["skip_reason"],
            })
        return {
            "trouble_spots": self.valid_trouble_spots(plan, fingerprint=fingerprint),
            "route_version": plan.route_version,
            "exercise_strategy": plan.exercise_strategy.name,
            "timing_strategy": plan.timing_strategy.name,
            "tempo_strategy": plan.tempo_strategy.name,
            "piece_fingerprint": fingerprint,
            "current_step": plan.lesson_step_number,
            "total_steps": len(plan.lesson_steps),
            "completed_steps": plan.lesson_steps_mastered,
            "steps": steps,
        }
