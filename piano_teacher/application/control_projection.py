"""Backend-owned interpretation of visible piano transport controls."""
from __future__ import annotations
from collections.abc import Mapping
from .transport_commands import PAUSABLE_PHASES

UI_INTENTS = frozenset((
    "ui_primary", "ui_pause", "ui_retry", "ui_listen",
    "ui_previous", "ui_review_previous", "ui_skip",
    "ui_tempo_up", "ui_tempo_down", "ui_midi_start"))
SCORE_WAIT = "Preparing sheet music - wait for the notes before starting"


def active(s: Mapping) -> bool:
    return bool(s.get("running")) or s.get("phase") in (PAUSABLE_PHASES | {"paused"})


def flow(s: Mapping) -> bool:
    return isinstance(s.get("flow"), dict) and bool(s["flow"])


def primary(s: Mapping, moving: bool, course: bool) -> str | None:
    if not s.get("loaded"):
        return None
    if s.get("paused"):
        return "resume"
    mode = s.get("mode")
    if course:
        return "pause" if moving else "listen" if mode == "listen" else "start" if mode == "practice" else None
    if mode == "listen" and not moving:
        return "practice" if s.get("warmup") else "listen"
    if mode == "learn":
        phase = s.get("phase")
        teaching = s.get("teaching") or {}
        if phase == "guided_complete" and teaching.get("has_more_units") and not s.get("guided_recovery"):
            return "learn_next"
        if phase in ("guided_complete", "disconnected"):
            return "practice"
        if phase in ("guided_wait", "loading"):
            return "pause"
        return "learn_retry"
    return "pause" if moving else "start"


def caption(s: Mapping, action: str | None, moving: bool, course: bool) -> str:
    if s.get("paused"):
        return "Resume"
    if course:
        return "Pause" if moving else "Listen" if s.get("mode") == "listen" else "Play"
    if s.get("mode") == "learn":
        if action == "learn_next":
            return "Next idea"
        if s.get("phase") == "guided_complete" and s.get("guided_recovery"):
            return "Retry rhythm"
        return {"practice": "Try rhythm", "pause": "Pause", "learn_retry": "Learn"}.get(action, "Learn")
    if s.get("mode") == "listen" and not moving:
        return "Back to warm-up" if s.get("warmup") else "Listen again"
    return "Pause" if action == "pause" else "Play"


def project_controls(s: Mapping) -> dict:
    """Read-only control labels and available actions from authoritative state."""
    moving, course = active(s), flow(s)
    main = primary(s, moving, course)
    pause = ("resume" if s.get("paused") else "pause") if (
        s.get("loaded") and (moving or (s.get("mode") == "learn" and
        s.get("phase") in ("guided_wait", "paused")))) else None
    if course and not moving and not s.get("paused"):
        pause = None
    retry = ("learn_retry" if s.get("mode") == "learn" else "restart") if s.get("loaded") else None
    retry_allowed = retry is not None and s.get("phase") not in ("admitting", "loading")
    tempo_allowed = bool(s.get("loaded")) and s.get("phase") not in (
        "count_in", "playing", "loading", "admitting")
    previous_visible = bool(s.get("loaded")) and not course
    previous_enabled = previous_visible and int(s.get("lesson_step", 1)) > 1
    skip_enabled = previous_visible and bool(s.get("skip_available"))
    listen = None
    if s.get("loaded"):
        listen = (None if s.get("mode") == "listen" else "listen") if course else (
            "practice" if s.get("mode") == "listen" else "listen")
    # A physical MIDI key is a gesture. The application determines
    # whether the current phase allows an initial start, manual retry
    # or course continuation. The input adapter only reports freshness.
    midi_action = None
    if (s.get("loaded") and s.get("device") and
            not s.get("paused")):
        phase = s.get("phase")
        mode = s.get("mode")
        if phase in ("ready", "performance_complete", "guided_complete"):
            if mode == "learn":
                midi_action = main
            elif mode in ("practice", "perform"):
                midi_action = "start"
        elif (phase == "feedback" and mode == "practice"
              and not s.get("auto")):
            midi_action = "restart"
    # Returning from standalone Listen is a mode action, not score
    # admission; the prior UI permitted it without ready notation.
    needs_score = (main not in (None, "pause", "resume") and
                   not (not course and s.get("mode") == "listen" and not moving))
    return {
        "transport_active": moving, "flow_active": course,
        "primary": {"action": main or "", "label": caption(s, main, moving, course),
                    "enabled": main is not None,
                    "requires_score": needs_score},
        "pause": {"action": pause or "", "enabled": pause is not None},
        "retry": {"action": retry or "", "enabled": retry_allowed,
                  "requires_score": True, "visible": not course},
        "listen": {"action": listen or "", "enabled": listen is not None,
                   "label": "Listen again" if course else "Practice" if s.get("mode") == "listen" else "Listen"},
        "previous": {"action": "select_step" if previous_enabled else "",
                     "enabled": previous_enabled, "visible": previous_visible},
        "review_previous": {
            "action": "select_step" if s.get("loaded") and
            int(s.get("lesson_step", 1)) > 1 else "",
            "enabled": bool(s.get("loaded")) and
            int(s.get("lesson_step", 1)) > 1},
        "skip": {"action": "skip_stage" if skip_enabled else "",
                 "enabled": skip_enabled, "visible": previous_visible},
        "midi_start": {"action": midi_action or "",
                       "enabled": midi_action is not None,
                       "requires_score": True},
        "tempo_up": {"action": "tempo_up" if tempo_allowed and s.get("can_increase_tempo") else "",
                     "enabled": tempo_allowed and bool(s.get("can_increase_tempo"))},
        "tempo_down": {"action": "tempo_down" if tempo_allowed and s.get("can_decrease_tempo") else "",
                       "enabled": tempo_allowed and bool(s.get("can_decrease_tempo"))},
    }


# View effects of the action ACTUALLY executed by the backend, never of a
# stale raw gesture or a label reconstructed by the Godot screen.
NAVIGATION_ACTIONS = frozenset((
    "select_step", "skip_stage", "place_original",
    "revisit_trouble", "learn_next", "open_at"))
CALIBRATION_ACTIONS = frozenset(("calibration_apply", "calibration_reset"))


def project_command_outcome(action: str | None) -> dict:
    """Transient, versioned command result; never a persistent state field."""
    return {
        "version": 1,
        "executed": action is not None,
        "action": action or "",
        "effects": {
            "navigate_practice": action in NAVIGATION_ACTIONS,
            "refresh_settings": action in CALIBRATION_ACTIONS,
            "invalidate_lesson": action == "reset_path",
        },
    }


def resolve_ui_intent(intent: str, state: Mapping, *,
                      score_ready: bool, score_error: str = "") -> tuple[str | None, dict]:
    """Resolve the raw gesture under the session lock; renderer supplies readiness."""
    if intent not in UI_INTENTS:
        raise ValueError(f"Unknown UI intent: {intent}")
    choice = project_controls(state)[intent.removeprefix("ui_")]
    action = choice["action"]
    if not action or not choice.get("enabled", False):
        if intent in ("ui_previous", "ui_review_previous", "ui_skip",
                      "ui_tempo_up", "ui_tempo_down"):
            raise ValueError("This control is no longer available in the current lesson")
        return None, {}
    if action == "resume" and score_error:
        raise ValueError(score_error)
    if choice.get("requires_score") and not score_ready:
        raise ValueError(SCORE_WAIT)
    if intent == "ui_previous":
        return action, {"number": int(state["lesson_step"]) - 1}
    if intent == "ui_review_previous":
        return action, {"number": max(1, int(state["lesson_step"]) - 2)}
    if intent == "ui_skip":
        return action, {"reason": "Learner skipped to the next lesson from the practice screen"}
    if intent == "ui_listen" and action == "practice" and not flow(state):
        return action, {"wait_for_player": True}
    return action, {}
