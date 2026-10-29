"""Source-bound learner progress queries and trouble persistence.

The caller holds the application lock while lending a live LearningPlan to a
call. Only the existing LearnerStateStore is retained here; its connection and
the plan's selection, transport, teaching and timed mastery remain caller-owned.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..learning import LearningPlan
from ..learner_state import LearnerStateStore, guided_units, next_guided_unit
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
        steps = []
        for i, step in enumerate(plan.lesson_steps):
            saved = self.saved(plan, fingerprint=fingerprint, stage_key=step.key)
            steps.append({
                "number": i+1, "exercise": step.exercise_index+1,
                "hand": step.hand, "level": step.level, "key": step.key,
                "kind": step.kind, "first_bar": step.first_bar,
                "last_bar": step.last_bar, "required_notes": step.required_notes,
                "completed": step.key in plan.mastered,
                "skip_status": saved["skip_status"], "skip_reason": saved["skip_reason"],
            })
        return {
            "trouble_spots": self.valid_trouble_spots(plan, fingerprint=fingerprint),
            "route_version": plan.route_version,
            "piece_fingerprint": fingerprint,
            "current_step": plan.lesson_step_number,
            "total_steps": len(plan.lesson_steps),
            "completed_steps": plan.lesson_steps_mastered,
            "steps": steps,
        }
