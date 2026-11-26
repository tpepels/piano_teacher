"""Backend-owned interpretation of visible piano transport controls."""
from __future__ import annotations
from collections.abc import Mapping
from .transport_commands import PAUSABLE_PHASES
from .midi_key_shortcuts import RESUME_NOTE

UI_INTENTS = frozenset((
    "ui_primary", "ui_pause", "ui_retry", "ui_listen",
    "ui_review_previous",
    "ui_tempo_up", "ui_tempo_down", "ui_midi_start", "ui_suspend",
    "ui_passage_previous", "ui_passage_next", "ui_stop"))
SCORE_WAIT = "Preparing sheet music - wait for the notes before starting"


def active(s: Mapping) -> bool:
    # The musical phase may still be "loading" after the bounded physical
    # admission budget is exhausted. That pending-score phase must not
    # offer Pause when the transaction has no live take or future intent.
    timeline = s.get("playback_timeline")
    if (isinstance(timeline, Mapping) and timeline.get("state") == "failed"
            and not s.get("running")):
        return False
    if s.get("running"):
        return True
    phase = s.get("phase")
    if phase == "feedback" and not (
            s.get("auto") or isinstance(s.get("playback_intent"), Mapping)
            or s.get("transition_in_seconds") is not None):
        # A retained result with no automatic continuation (for example a
        # failed save awaiting Play) is not learning or playing: offer Play.
        return False
    return phase in (PAUSABLE_PHASES | {"paused"})


def section_choice(s: Mapping) -> bool:
    flow = s.get("flow")
    return bool(s.get("loaded") and isinstance(flow, Mapping)
        and flow.get("step") == "section_choice" and not s.get("running")
        and not s.get("paused") and not isinstance(s.get("playback_intent"), Mapping))


def primary(s: Mapping, moving: bool) -> str | None:
    """Practice Flow advances by itself: the main control pauses/resumes,
    and only offers Play/Listen when the flow is waiting for the player."""
    if not s.get("loaded"):
        return None
    if s.get("paused"):
        return "resume"
    if section_choice(s):
        return "section_next"
    if moving:
        return "pause"
    return {"listen": "listen", "practice": "start"}.get(s.get("mode"))


def caption(s: Mapping, moving: bool) -> str:
    if s.get("paused"):
        return "Resume"
    if section_choice(s):
        return "Next section"
    if moving:
        return "Pause"
    return "Listen" if s.get("mode") == "listen" else "Play"


def project_controls(s: Mapping) -> dict:
    """Read-only control labels and available actions from authoritative state."""
    choosing = section_choice(s)
    moving = active(s) and not choosing
    main = primary(s, moving)
    pause = (None if not s.get("loaded") else "resume" if s.get("paused")
             else "pause" if moving else None)
    retry = ("learn_retry" if s.get("mode") == "learn" else
             "listen" if s.get("mode") == "listen" else "restart") if s.get("loaded") else None
    if choosing:
        retry = "section_repeat"
    retry_allowed = retry is not None and s.get("phase") not in ("admitting", "loading")
    tempo_allowed = bool(s.get("loaded")) and s.get("phase") not in (
        "count_in", "playing", "loading", "admitting")
    # A passage is an exercise group; it may contain several lesson steps.
    passage_previous = bool(s.get("loaded")) and int(s.get("exercise", 1)) > 1
    passage_next = (bool(s.get("loaded")) and
                    int(s.get("exercise", 1)) < int(s.get("exercise_count", 1)))
    mode = s.get("mode")
    phase = s.get("phase")
    stop_enabled = bool(s.get("loaded")) and (
        phase not in ("ready", "guided_complete", "disconnected")
        if mode == "learn" else
        bool(s.get("running")) or isinstance(s.get("playback_intent"),Mapping)
        or phase in ("count_in", "playing", "paused", "feedback",
                     "recovering", "loading", "admitting"))
    loaded = bool(s.get("loaded"))
    hands = {
        hand: {"enabled": loaded and hand != s.get("hand")}
        for hand in s.get("hands",[]) if isinstance(hand,str)
    }
    activity_modes = {
        "learn": {"enabled":loaded},
        "practice": {"enabled":loaded},
        "perform_current": {"enabled":loaded},
        "perform_whole": {"enabled":loaded},
    }
    listen = "listen" if s.get("loaded") and s.get("mode") != "listen" else None
    # A physical MIDI key is a gesture. The application determines
    # whether the current phase allows an initial start, manual retry
    # or course continuation. The input adapter only reports freshness.
    midi_action = None
    if (s.get("loaded") and s.get("device") and
            not s.get("paused") and not choosing):
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
    needs_score = main not in (None, "pause", "resume", "section_next")
    return {
        "transport_active": moving,
        "primary": {"action": main or "", "label": caption(s, moving),
                    "enabled": main is not None,
                    "requires_score": needs_score,
                    "piano_key": (RESUME_NOTE if main == "resume" else "F" if choosing else "") if s.get("device") else ""},
        "pause": {"action": pause or "", "enabled": pause is not None},
        "retry": {"action": retry or "", "enabled": retry_allowed,
                  "requires_score": True, "piano_key": "C" if choosing and s.get("device") else ""},
        "listen": {"action": listen or "", "enabled": listen is not None,
                   "label": "Listen again"},
        "review_previous": {
            "action": "select_step" if s.get("loaded") and
            int(s.get("lesson_step", 1)) > 1 else "",
            "enabled": bool(s.get("loaded")) and
            int(s.get("lesson_step", 1)) > 1},
        "hints": {"action": "hints" if loaded and mode == "learn" and
                   phase != "loading" else "",
                  "enabled": loaded and mode == "learn" and phase != "loading"},
        "activities": activity_modes,
        "hands": hands,
        "passage_previous": {"action": "previous" if passage_previous else "",
                             "enabled": passage_previous},
        "passage_next": {"action": "next" if passage_next else "",
                         "enabled": passage_next},
        "stop": {"action": "stop" if stop_enabled else "",
                 "enabled": stop_enabled},
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
    "select_step", "previous", "next", "hand", "open_at"))
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
    if intent == "ui_suspend":
        # Leaving a screen is a one-way request. A pending Start may finish
        # before this gesture is delivered, but an already paused lesson
        # must NEVER turn this into Resume. No score readiness is required.
        pause = project_controls(state)["pause"]
        return ("pause" if pause["enabled"] and pause["action"] == "pause" else None), {}
    choice = project_controls(state)[intent.removeprefix("ui_")]
    action = choice["action"]
    if not action or not choice.get("enabled", False):
        if intent in ("ui_review_previous",
                      "ui_passage_previous", "ui_passage_next",
                      "ui_tempo_up", "ui_tempo_down"):
            raise ValueError("This control is no longer available in the current lesson")
        return None, {}
    if action == "resume" and score_error:
        raise ValueError(score_error)
    if choice.get("requires_score") and not score_ready:
        raise ValueError(SCORE_WAIT)
    if intent == "ui_review_previous":
        return action, {"number": max(1, int(state["lesson_step"]) - 2)}
    return action, {}
