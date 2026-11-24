"""Source-bound learner progress queries and guided-unit persistence.

The caller holds the application lock while lending a live LearningPlan to a
call. Only the existing LearnerStateStore is retained here; its connection and
the plan's selection, transport, teaching and timed mastery remain caller-owned.
"""
from __future__ import annotations


from ..learning import LearningPlan
from ..learner_state import LearnerStateStore, guided_units, next_guided_unit


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

    def teaching_credits(self, fingerprint):
        from ..teaching_manual import GuidedCredits, unit_key
        if not fingerprint:
            return ()
        keys = self._store.db.execute("SELECT stage_key FROM learner_stages WHERE fingerprint=?", (fingerprint,)).fetchall()
        result = []
        for (key,) in keys:
            saved = self._store.read(fingerprint,key)
            result.append(GuidedCredits(key, unit_key(saved["resume_unit"]) if saved["resume_unit"] else None,
                tuple(unit_key(unit) for unit in saved["completed_units"])))
        return tuple(result)

    def save_resume(self, *, fingerprint: str, stage_key: str,
                    unit: dict | None) -> None:
        if fingerprint and unit is not None:
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

    def lesson_overview(self, plan: LearningPlan | None, *, fingerprint: str) -> dict:
        """Return the readable curriculum without navigating or awarding credit."""
        if plan is None:
            raise ValueError("Open a piece first")
        from ..lesson_stage_semantics import describe
        steps = []
        for i, step in enumerate(plan.lesson_steps):
            label = step.level
            family = "Practice"
            change = "source notes"
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
                "available": True,
            })
        return {
            "piece_fingerprint": fingerprint,
            "current_step": plan.lesson_step_number,
            "total_steps": len(plan.lesson_steps),
            "completed_steps": plan.lesson_steps_mastered,
            "steps": steps,
        }
