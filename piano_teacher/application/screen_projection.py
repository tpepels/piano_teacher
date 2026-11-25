"""What the practice screen shows (docs/practice-flow.md, "On screen").

The screen is the score, Pause/Resume, Listen again and one status line.
Godot displays this projection; it composes no lesson text of its own.
"""
from __future__ import annotations
from collections.abc import Mapping


def notice(s: Mapping, moving: bool) -> str:
    """One problem line, only while the flow cannot continue by itself."""
    timeline = s.get("playback_timeline")
    if isinstance(timeline, Mapping) and timeline.get("state") == "failed":
        return str(timeline.get("failure") or "The score could not be presented")
    teaching = s.get("teaching") if isinstance(s.get("teaching"), Mapping) else {}
    if s.get("mode") == "learn" and teaching.get("phase") == "disconnected" and not s.get("paused"):
        # Free waits for a piano: say so, or it looks as if it just stopped.
        parts = [str(s.get(key) or "") for key in ("feedback", "next_action")]
        return " ".join(part for part in parts if part)
    if moving or s.get("paused") or s.get("mode") == "learn":
        return ""
    parts = [str(s.get(key) or "") for key in ("feedback", "next_action")]
    return " · ".join(part for part in parts if part)


def keyboard(s: Mapping) -> str:
    """The keyboard appears only as a wrong-note hint in Free."""
    teaching = s.get("teaching") if isinstance(s.get("teaching"), Mapping) else {}
    return ("hint" if s.get("mode") == "learn" and teaching.get("hint_visible")
            and teaching.get("hint_reason") == "wrong_note" else "hidden")


def project_screen(s: Mapping, *, moving: bool, flash: tuple[int, str] = (0, "")) -> dict:
    flow = s.get("flow") if isinstance(s.get("flow"), Mapping) else {}
    return {"status": str(flow.get("status", "")),
            "notice": notice(s, moving) if s.get("loaded") else "",
            "keyboard": keyboard(s),
            "flash": {"id": int(flash[0]), "text": str(flash[1])}}
