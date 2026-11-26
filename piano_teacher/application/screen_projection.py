"""What the practice screen shows (docs/practice-flow.md, "On screen").

The screen is the score, Pause/Resume, Listen again and one status line.
Godot displays this projection; it composes no lesson text of its own.
"""
from __future__ import annotations
from collections.abc import Mapping


FREE_WITHOUT_PIANO = ("No piano connected. Switch on or plug in your MIDI piano; practice "
                      "continues as soon as it is found. A new piano: choose it in Settings.")


def notice(s: Mapping, moving: bool) -> str:
    """One problem line, only while the flow cannot continue by itself."""
    timeline = s.get("playback_timeline")
    if isinstance(timeline, Mapping) and timeline.get("state") == "failed":
        return "The music could not start. Press Play to try again."
    teaching = s.get("teaching") if isinstance(s.get("teaching"), Mapping) else {}
    if s.get("mode") == "learn" and teaching.get("phase") == "disconnected" and not s.get("paused"):
        # Free waits for a piano: say so, or it looks as if it just stopped.
        # One fixed text: the feedback line may still describe an earlier
        # step ("Preparing a short idea") while the piano is missing.
        return FREE_WITHOUT_PIANO
    if moving or s.get("paused") or s.get("mode") == "learn":
        return ""
    parts = [str(s.get(key) or "") for key in ("feedback", "next_action")]
    return " · ".join(part for part in parts if part)


def keyboard(s: Mapping) -> str:
    """The keyboard appears only as a wrong-note hint in Free."""
    teaching = s.get("teaching") if isinstance(s.get("teaching"), Mapping) else {}
    return ("hint" if s.get("mode") == "learn" and teaching.get("hint_visible")
            and teaching.get("hint_reason") == "wrong_note" else "hidden")


def project_screen(s: Mapping, *, moving: bool, flash: tuple[int, str] = (0, ""),
                   latest_timing_accuracy: float | None = None) -> dict:
    flow = s.get("flow") if isinstance(s.get("flow"), Mapping) else {}
    status = str(flow.get("status", ""))
    if s.get("loaded") and latest_timing_accuracy is not None:
        accuracy = f"Last accuracy: {latest_timing_accuracy:.1f}%"
        status = f"{status} · {accuracy}" if status else accuracy
    return {"status": status,
            "notice": notice(s, moving) if s.get("loaded") else "",
            "keyboard": keyboard(s),
            "flash": {"id": int(flash[0]), "text": str(flash[1])},
            "transition": {"id": int(flow.get("message_id", 0)),
                           "text": str(flow.get("message", "")) if s.get("loaded") else ""}}
