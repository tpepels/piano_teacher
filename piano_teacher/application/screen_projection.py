"""What the practice screen shows (docs/practice-flow.md, "On screen").

The screen is the score, Pause/Resume, Listen again and one status line.
Godot displays this projection; it composes no lesson text of its own.
"""
from __future__ import annotations
from collections.abc import Mapping
from .control_projection import section_choice


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


_RESULT_CUES = {
    "faster": ("Tempo up!", "success"),
    "clean_once": ("Clean run!", "success"),
    "stage_done": ("Hand mastered!", "success"),
    "section_ready": ("Section cleared!", "milestone"),
    "piece_done": ("Piece mastered!", "milestone"),
    "again": ("Another run", "retry"),
    "slower": ("Ease the tempo", "retry"),
    "back_to_free": ("Back to the notes", "retry"),
}
_PHASE_CUES = {"listen": ("Listen", "listen"), "free": ("Your turn", "info"),
               "tempo": ("In tempo", "tempo"), "aid": ("Simplified passage", "info")}


def transition_cue(kind: str, message: str) -> dict:
    """Style the committed outcome without deciding anything about grading."""
    if not message:
        return {"title":"", "detail":"", "tone":"info"}
    if kind in _RESULT_CUES:
        title, tone = _RESULT_CUES[kind]
        parts = message.split(" · ")
        accuracy = next((part for part in parts if part.endswith("% accuracy")), "")
        detail = [part for part in parts if part not in (
            "Well played!", "Try again", accuracy, "Well done", "Piece mastered")]
        if accuracy:
            title = f"{title}  ·  {accuracy}"
        return {"title":title, "detail":" · ".join(detail), "tone":tone}
    if kind in _PHASE_CUES:
        title, tone = _PHASE_CUES[kind]
        return {"title":title, "detail":message if message != title else "", "tone":tone}
    return {"title":message, "detail":"", "tone":"info"}


def project_screen(s: Mapping, *, moving: bool, flash: tuple[int, str] = (0, ""),
                   accuracy: float | None = None, accuracy_live: bool = False) -> dict:
    flow = s.get("flow") if isinstance(s.get("flow"), Mapping) else {}
    status = str(flow.get("status", ""))
    if s.get("loaded") and (accuracy_live or accuracy is not None):
        value = "—" if accuracy is None else f"{accuracy:.1f}%"
        label = f"Accuracy: {value}" if accuracy_live else f"Last accuracy: {value}"
        status = f"{status} · {label}" if status else label
    prompt = notice(s, moving) if s.get("loaded") else ""
    cue = {"title":prompt, "detail":"", "tone":"warning"}
    if (flow.get("sight_reading") and not moving and not s.get("paused")
            and str(s.get("feedback","")).startswith("Round complete")):
        cue = {"title":str(s["feedback"]),
               "detail":"Settings for a new round · Play to repeat", "tone":"milestone"}
    if section_choice(s):
        value = "" if accuracy is None else f" · {accuracy:.1f}% accuracy"
        keys = "C to repeat at 100% · F for next section" if s.get("device") else "Repeat or choose Next section"
        prompt = f"Section complete{value} · {keys}"
        cue = {"title":f"Section cleared!{value}", "detail":keys, "tone":"milestone"}
    return {"status": status,
            "notice": prompt, "notice_cue": cue,
            "keyboard": keyboard(s),
            "flash": {"id": int(flash[0]), "text": str(flash[1])},
            "transition": {"id": int(flow.get("message_id", 0)),
                           "text": str(flow.get("message", "")) if s.get("loaded") else "",
                            "cue": transition_cue(str(flow.get("message_kind", "info")),
                                str(flow.get("message", "")) if s.get("loaded") else "")}}
