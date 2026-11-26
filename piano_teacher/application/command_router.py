"""Learner commands: UI-intent resolution, the lesson decision, one route.

Runs inside PracticeSession's lock. Which workflow executes a route is
wired by the composition root (`session_routes`); this class only
validates the displayed score, resolves UI intents, prepares the lesson
decision and records the manual action.
"""
from __future__ import annotations

from .control_projection import UI_INTENTS, resolve_ui_intent, project_command_outcome
from .stage_change import prepare_stage_change

# Unknown action names fall through to the lesson stage validator.
COMMAND_ROUTES = {
    **dict.fromkeys(("calibration_start", "calibration_cancel",
                     "calibration_apply", "calibration_reset"), "calibration"),
    **dict.fromkeys(("midi_range_start", "midi_range_cancel"), "device_range"),
    "reset_path": "reset",
    **dict.fromkeys(("score_ready", "demo_ready"), "acknowledgement"),
    **dict.fromkeys(("listen", "perform"), "listening"),
    **dict.fromkeys(("learn", "learn_retry",
                     "open_at", "hints"), "learning"),
    **dict.fromkeys(("practice", "stop", "start", "restart", "pause", "resume",
                     "section_repeat", "section_next"), "transport"),
}
_TEACHING_ROUTES = ("listening", "learning", "transport", "stage")


class CommandRouter:
    def __init__(self, *, lesson, transport, read_models, presentation, measurement,
                 listen_outcomes, routes):
        self.lesson = lesson
        self.transport = transport
        self.read_models = read_models
        self.presentation = presentation
        self.measurement = measurement
        self.listen_outcomes = listen_outcomes
        missing = set(COMMAND_ROUTES.values()) | {"stage"}
        missing -= set(routes)
        if missing:
            raise ValueError(f"Unrouted command families: {sorted(missing)}")
        self.routes = routes

    def _resolve_ui(self, action: str, kwargs: dict) -> str | None:
        ready = kwargs.pop("score_ready", None)
        error = kwargs.pop("score_error", "")
        score_revision = kwargs.pop("score_revision", None)
        score_fingerprint = kwargs.pop("score_fingerprint", None)
        if action not in ("ui_suspend","ui_stop") and (
                type(ready) is not bool or type(error) is not str
                or type(score_revision) is not int
                or type(score_fingerprint) is not str):
            raise ValueError("UI control requires source-bound renderer readiness")
        current = self.read_models.control_snapshot()
        if action == "ui_review_previous":
            # The dialog retains a snapshot only to identify the
            # source that was offered. Python selects the actual
            # previous step from the current lesson, never the
            # outdated step number on the screen.
            context_revision = kwargs.pop("context_revision", None)
            context_fingerprint = kwargs.pop("context_fingerprint", None)
            if (type(context_revision) is not int
                    or type(context_fingerprint) is not str
                    or context_revision != current.get("revision")
                    or context_fingerprint != current.get("piece_fingerprint")):
                raise ValueError("Resume prompt belongs to an obsolete lesson")
        if action not in ("ui_suspend","ui_stop") and ready and (
                score_revision != current.get("revision")
                or score_fingerprint != current.get("piece_fingerprint")):
            raise ValueError("Displayed score belongs to an earlier source revision")
        resolved, options = resolve_ui_intent(
            action, current, score_ready=bool(ready), score_error=error)
        if resolved is not None:
            kwargs.update(options)
        return resolved

    def _lesson_facts(self) -> dict:
        plan = self.lesson.plan
        return {"fingerprint": self.lesson.fingerprint,
                "stage_key": plan.identity if plan else None,
                "bpm": plan.bpm if plan else None, "mode": self.transport.mode}

    def apply(self, action: str, **kwargs) -> dict:
        # Explicit Stop is a one-way cancellation, including while Godot
        # is replaying a queued Stop after a delayed command acknowledgement.
        # It must not require a healthy score/read-model projection or an
        # unrelated curriculum decision to invalidate an active take.
        if action == "ui_stop":
            action = "stop"
        if action in UI_INTENTS:
            action = self._resolve_ui(action, kwargs)
            if action is None:
                return project_command_outcome(None)
        if action in ("section_repeat", "section_next") and not self.lesson.section_choice_active:
            raise ValueError("No section choice is available")
        before = self._lesson_facts()
        effect = None
        route = COMMAND_ROUTES.get(action, "stage")
        # Stop/Pause/Resume only mutate transport state. The selected lesson
        # never consumes their teaching effect, so they cannot be blocked by
        # curriculum generators, learner-history reads or stale evidence.
        needs_teaching = action not in ("stop", "pause", "resume")
        if (needs_teaching and self.lesson.plan is not None
                and route in _TEACHING_ROUTES):
            change = (prepare_stage_change(self.lesson.plan, action, kwargs)
                      if route == "stage" else None)
            effect = self.lesson.prepare_decision("manual", manual=change,
                action=action, from_beat=kwargs.get("from_beat",kwargs.get("start_beat")), store=False, values=kwargs)
        self.listen_outcomes.apply_failure()
        self.routes[route](action, kwargs, effect)
        self.presentation.prepare_score_presentation()
        if action not in ("score_ready", "demo_ready", "reset_path"):
            self.measurement.event("manual_action", {"action": action,
                "fingerprint": before["fingerprint"] or None,
                "parameters": kwargs, "before": before,
                "after": self._lesson_facts()})
        return project_command_outcome(action)
