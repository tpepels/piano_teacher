"""Read-only presentation of practice facts. No engine or renderer imports."""
from __future__ import annotations
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field, fields
from types import MappingProxyType

from .measure_grid import bar_number_at
from .music import note_name


def _freeze(value):
    """Copy JSON values into an immutable graph; reject live application objects."""
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, _Snapshot):
        return value
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise TypeError("A session snapshot needs string payload keys")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    raise TypeError("A session snapshot can contain only captured values")


def _payload(value):
    """Each response gets its own mutable JSON containers."""
    if isinstance(value, Mapping):
        return {key: _payload(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_payload(item) for item in value]
    return value


class _Snapshot:
    def __post_init__(self):
        for item in fields(self):
            object.__setattr__(self, item.name, _freeze(getattr(self, item.name)))


@dataclass(frozen=True)
class PhaseSnapshot(_Snapshot):
    paused: bool = False
    running: bool = False
    run_at: float = 0.0
    teaching_phase: str | None = None
    performance_complete: bool = False
    preview_loop_pending: bool = False
    review_complete: bool = False
    pending_result: bool = False
    awaiting_score: bool = False
    pending_rewind: bool = False


def project_phase(state: PhaseSnapshot, *, mode: str, now: float) -> str:
    if state.paused:
        return "paused"
    if mode == "learn" and state.teaching_phase is not None:
        return "loading" if state.awaiting_score else state.teaching_phase
    if state.running:
        return "count_in" if now < state.run_at else "playing"
    if mode == "perform" and state.performance_complete:
        return "performance_complete"
    if state.preview_loop_pending:
        return "preview_gap"
    if mode == "practice" and state.review_complete and state.performance_complete:
        return "review"
    return ("feedback" if state.pending_result else "loading" if state.awaiting_score
            else "recovering" if state.pending_rewind else "ready")


@dataclass(frozen=True)
class ActivitySnapshot(_Snapshot):
    sampled_at: float = 0.0
    transition_now: float = 0.0
    notice_now: float = 0.0
    midi_now: float = 0.0
    next_at: float = 0.0
    pending_transition: bool = False
    review_pending: bool = False
    learner: Mapping | None = None
    placement_available: bool = False
    skip_available: bool = False
    seek_available: bool = False
    seek_range: Mapping | None = None
    next_action: str = ""
    retry_range: Mapping | None = None
    recovery_notice: Mapping | None = None
    guided_recovery: bool = False
    pause_context: str | None = None
    demo: Mapping | None = None
    performance_summary: Mapping | None = None
    midi_input_count: int = 0
    midi_input_note: int | None = None
    midi_input_at: float | None = None
    metronome: bool = True
    hints_enabled: bool = False
    fingering: Mapping | None = None
    midi_display: Mapping = field(default_factory=dict)


@dataclass(frozen=True)
class TempoSnapshot(_Snapshot):
    bpm: float = 60.0
    original_bpm: float = 60.0
    target_bpm: float = 60.0
    start_bpm: float = 40.0
    streak: int = 0
    rungs: tuple[int, ...] = ()
    minimum_bpm: int = 12
    maximum_bpm: int = 300
    clean_runs_required: int = 3
    manual_tempo_step_bpm: int = 5
    automatic_tempo_steps: int = 12


@dataclass(frozen=True)
class LessonSnapshot(_Snapshot):
    title: str = ""
    kind: str = "learn"
    first_bar: int = 1
    last_bar: int = 1
    measure_boundaries: tuple[float, ...] = (0.0, 4.0)
    duration_beats: float = 4.0
    exercise_index: int = 0
    exercise_count: int = 1
    level: str = "original"
    exercise_strategy: str = "legacy"
    level_number: int = 1
    level_count: int = 1
    required_notes: int = 0
    warmup: bool = False
    piece_last_bar: int = 0
    import_warnings: tuple[str, ...] = ()
    hand: str = "both"
    hands: tuple[str, ...] = ("both",)
    lesson_steps: tuple[tuple[int, str, str], ...] = ()
    lesson_step: int = 1
    lesson_steps_mastered: int = 0
    mastered: tuple[str, ...] = ()
    fingerprint: str = ""
    tempo: TempoSnapshot = field(default_factory=TempoSnapshot)


@dataclass(frozen=True)
class TimingSnapshot(_Snapshot):
    sampled_at: float = 0.0
    now: float = 0.0
    run_at: float = 0.0
    running: bool = False
    paused: bool = False
    auto: bool = False
    preview_only: bool = False
    play_from_beat: float = 0.0
    open_from_beat: float = 0.0
    pending_rewind: float | None = None
    review_end_beat: float | None = None
    awaiting_score_revision: int | None = None
    count_in_beats: float = 0.0
    count_in_bar_beats: float = 4.0
    count_in_meter: tuple[int, int] = (4, 4)
    midi_notes: int = 0
    visual_offset_beats: float = 0.0
    visual_gap_beats: float = 4.0
    visual_motion: tuple[float, float, float] = (0.0, 0.0, 0.0)
    practice_timeline: Mapping = field(default_factory=dict)
    practice_preparation: Mapping | None = None
    take_result: Mapping | None = None
    feedback_marks: tuple[Mapping, ...] = ()
    live_marks: tuple[Mapping, ...] = ()
    feedback_unmapped: int = 0
    scoring_available: bool = False


@dataclass(frozen=True)
class GuidedSnapshot(_Snapshot):
    teaching: Mapping = field(default_factory=dict)
    fragment: Mapping = field(default_factory=dict)
    phase: str = "guided_wait"
    has_more_units: bool = False
    returning: bool = False
    required_notes: int = 0
    duration_beats: float = 0.0
    feedback_marks: tuple[Mapping, ...] = ()


@dataclass(frozen=True)
class SessionSnapshot(_Snapshot):
    mode: str = "practice"
    feedback: str = ""
    device: str = ""
    revision: int = 0
    transport_id: int = 0
    phase: str = "ready"
    activity: ActivitySnapshot = field(default_factory=ActivitySnapshot)
    lesson: LessonSnapshot | None = None
    timing: TimingSnapshot | None = None
    guided: GuidedSnapshot | None = None


def project_session_state(snapshot: SessionSnapshot) -> dict:
    """Render captured session values without clocks, I/O or live collaborators."""
    activity = snapshot.activity
    notice = activity.recovery_notice
    result = {
        "clock_sampled_at_ms": activity.sampled_at * 1000.0,
        "learner": _payload(activity.learner),
        "placement_available": activity.placement_available,
        "skip_available": activity.skip_available,
        "seek_available": activity.seek_available,
        "seek_range": _payload(activity.seek_range),
        "next_action": activity.next_action,
        "transition_in_seconds": (max(0.0, activity.next_at-activity.transition_now)
            if activity.next_at and activity.pending_transition else None),
        "retry_range": _payload(activity.retry_range),
        "recovery_notice": ({key: _payload(value) for key, value in notice.items()
                             if key != "expires_at"}
                            if notice is not None and activity.notice_now < notice["expires_at"] else None),
        "guided_recovery": activity.guided_recovery,
        "pause_context": activity.pause_context,
        "demo": _payload(activity.demo),
        "performance_summary": _payload(activity.performance_summary),
        "review_range": _payload(activity.retry_range) if activity.review_pending else None,
        "midi_input_count": activity.midi_input_count,
        "midi_input_note": activity.midi_input_note,
        "midi_input_age": (max(0.0, activity.midi_now-activity.midi_input_at)
                           if activity.midi_input_at is not None else None),
        "metronome": activity.metronome,
        "hints_enabled": activity.hints_enabled,
        "fingering": _payload(activity.fingering),
        **_payload(activity.midi_display),
        "mode": snapshot.mode, "teaching": None,
        "transport_id": snapshot.transport_id,
        "device": snapshot.device, "revision": snapshot.revision,
    }
    lesson, timing = snapshot.lesson, snapshot.timing
    if lesson is None:
        result.update(loaded=False, running=False, paused=False,
                      clock_beat=0.0, feedback=snapshot.feedback)
        return result
    if timing is None:
        raise ValueError("A loaded session snapshot needs captured timing")
    tempo = lesson.tempo
    total_beats = lesson.duration_beats
    practice_end = min(total_beats, timing.review_end_beat) if timing.review_end_beat is not None else total_beats
    start_beat = timing.play_from_beat if timing.review_end_beat is not None else 0.0
    elapsed = timing.now-timing.run_at
    exercise_beat = timing.play_from_beat+max(0.0, elapsed*tempo.bpm/60)
    progress = (min(1.0, max(0.0, (exercise_beat-start_beat)/max(1e-6, practice_end-start_beat)))
                if timing.running else 0.0)
    live_errors = [mark for mark in timing.live_marks if mark.get("status") in ("missed", "wrong")]
    latest_error = max(live_errors, key=lambda mark: (mark.get("beat", -1), mark.get("pitch", -1)), default=None)
    feedback_phase = activity.pause_context if timing.paused else snapshot.phase
    result.update({
        "loaded": True, "title": lesson.title, "kind": lesson.kind,
        "clock_sampled_at_ms": timing.sampled_at*1000.0,
        "first_bar": lesson.first_bar, "last_bar": lesson.last_bar,
        "current_bar": bar_number_at(lesson.measure_boundaries,
            exercise_beat if timing.running else timing.play_from_beat, lesson.first_bar),
        "exercise": lesson.exercise_index+1, "exercise_count": lesson.exercise_count,
        "lesson_level": lesson.level, "lesson_level_number": lesson.level_number,
        "lesson_level_count": lesson.level_count, "required_notes": lesson.required_notes,
        "warmup": lesson.warmup, "piece_last_bar": lesson.piece_last_bar,
        "selected_start_bar": bar_number_at(lesson.measure_boundaries, timing.open_from_beat, lesson.first_bar),
        "hand_stages": hand_stage_rows(kind=lesson.kind, exercise_index=lesson.exercise_index,
            current_hand=lesson.hand, available_hands=lesson.hands, mastered=lesson.mastered,
            lesson_steps=lesson.lesson_steps, builtin_warmup=lesson.warmup),
        "measure_boundaries": list(lesson.measure_boundaries),
        "import_warnings": list(lesson.import_warnings),
        "lesson_step": lesson.lesson_step, "lesson_steps": len(lesson.lesson_steps),
        "lesson_steps_mastered": lesson.lesson_steps_mastered,
        "hand": lesson.hand, "hands": list(lesson.hands),
        "bpm": tempo.bpm, "original_bpm": tempo.original_bpm, "target_bpm": tempo.target_bpm,
        "streak": tempo.streak,
        "clean_runs_required": tempo.clean_runs_required,
        "manual_tempo_step_bpm": tempo.manual_tempo_step_bpm,
        "start_bpm": tempo.start_bpm, "automatic_tempo_steps": tempo.automatic_tempo_steps,
        "tempo_rungs": list(tempo.rungs), "can_decrease_tempo": tempo.bpm > tempo.minimum_bpm,
        "piece_fingerprint": lesson.fingerprint,
        "minimum_bpm": tempo.minimum_bpm, "maximum_bpm": tempo.maximum_bpm,
        "can_increase_tempo": tempo.bpm < tempo.target_bpm,
        "mastered": len(lesson.mastered), "phase": snapshot.phase, "auto": timing.auto,
        "take_result": _payload(timing.take_result) if snapshot.mode == "practice" else None,
        "countdown": max(0, -elapsed) if timing.running else 0,
        "lead_in_bars": 1, "play_from_beat": timing.play_from_beat,
        "recovery_beat": timing.pending_rewind,
        "clock_beat": elapsed*tempo.bpm/60 if timing.running else 0.0,
        "visual_offset_beats": timing.visual_offset_beats,
        "visual_scroll_beat": timing.visual_motion[0], "visual_target_beat": timing.visual_motion[2],
        "visual_scroll_speed": timing.visual_motion[1], "visual_gap_beats": timing.visual_gap_beats,
        "practice_timeline": _payload(timing.practice_timeline),
        "practice_preparation": _payload(timing.practice_preparation),
        "score_loop_enabled": snapshot.mode == "practice" and lesson.kind != "perform",
        "paused": timing.paused, "awaiting_score_revision": timing.awaiting_score_revision,
        "count_in_beats": timing.count_in_beats if timing.running else 0,
        "count_in_bar_beats": timing.count_in_bar_beats, "count_in_meter": list(timing.count_in_meter),
        "midi_notes": timing.midi_notes, "preview_only": timing.preview_only,
        "progress": progress, "duration": (practice_end-start_beat)*60/tempo.bpm,
        "beat": exercise_beat if timing.running else 0.0, "duration_beats": total_beats,
        "running": timing.running, "feedback": "Paused" if timing.paused else snapshot.feedback,
        "feedback_marks": _payload(timing.feedback_marks if feedback_phase in
            ("feedback", "recovering", "performance_complete", "review") else timing.live_marks),
        "live_note_feedback": ({"status": latest_error["status"], "pitch": latest_error["pitch"],
            "name": note_name(int(latest_error["pitch"])), "count": len(live_errors),
            "source_id": latest_error.get("source_id", "")} if latest_error is not None else None),
        "scoring_available": timing.scoring_available,
        "feedback_unmapped": timing.feedback_unmapped if feedback_phase in
            ("feedback", "recovering", "performance_complete") else 0,
    })
    guided = snapshot.guided
    if guided is not None:
        result.update(guided_learning_fields(
            teaching=_payload(guided.teaching), fragment=_payload(guided.fragment),
            session_id=snapshot.transport_id, has_more_units=guided.has_more_units,
            returning=guided.returning, phase=guided.phase,
            required_notes=guided.required_notes, duration_beats=guided.duration_beats))
        result["feedback_marks"] = _payload(guided.feedback_marks)
    return result


def hand_stage_rows(*, kind: str, exercise_index: int, current_hand: str,
                    available_hands: Collection[str], mastered: Collection[str],
                    lesson_steps: Iterable[tuple[int, str, str]],
                    builtin_warmup: bool) -> list[dict]:
    if kind not in ("learn", "warmup"):
        return []
    steps = tuple(lesson_steps)
    rows = []
    for hand in ("right", "left", "both"):
        matching = [key for index, step_hand, key in steps
                    if index == exercise_index and step_hand == hand]
        if not matching:
            continue
        complete = all(key in mastered for key in matching)
        locked = (builtin_warmup and hand != "right"
                  and not all(previous["complete"] for previous in rows))
        rows.append({"hand":hand, "active":hand == current_hand,
                     "complete":complete, "locked":locked,
                     "available":hand in available_hands})
    return rows


def guided_learning_fields(*, teaching: Mapping, fragment: Mapping, session_id: int,
                           has_more_units: bool, returning: bool, phase: str,
                           required_notes: int, duration_beats: float) -> dict:
    """Project a captured teaching snapshot; never sample clocks or change state."""
    snapshot = dict(teaching)
    snapshot["fragment"] = dict(fragment)
    snapshot["session_id"] = session_id
    snapshot["has_more_units"] = has_more_units
    feedback = str(snapshot.get("feedback", "Find the highlighted notes at your own pace."))
    fields = {}
    if phase == "loading":
        feedback = "Preparing a short idea to learn"
    elif phase == "disconnected":
        feedback = "No piano connected — timed preview only. Connect your piano in Settings to learn notes."
        fields["next_action"] = "Connect your piano in Settings to learn notes."
    elif phase == "guided_complete":
        feedback = "You found every note. Ready to add rhythm?"
        fields["next_action"] = ("Retry rhythm from these bars." if returning
                                  else "Ready to add rhythm? Choose Practice.")
        if has_more_units:
            feedback = "You found this idea. Continue with the next short idea."
            fields["next_action"] = "Choose Next idea to learn the next part of the passage."
    elif phase == "paused":
        feedback = "Paused — resume when you are ready."
    elif phase == "guided_wait":
        labels = list(dict.fromkeys(n["label"] for n in snapshot.get("expected_notes", [])))
        keys = " + ".join(labels)
        together = " together" if len(labels) > 1 else ""
        feedback = f"Play {keys}{together}. Take your time."
        if snapshot.get("hint_reason") == "wrong_note":
            feedback = f"Find {keys} on the keyboard below, then try again."
        elif snapshot.get("target_index", 0) > 0:
            feedback = "Good. Next: " + keys + together + "."
    fields.update(teaching=snapshot, phase=phase, running=False,
                  paused=phase == "paused", clock_beat=0.0, countdown=0.0,
                  first_bar=fragment["first_bar"], last_bar=fragment["last_bar"],
                  required_notes=required_notes, duration_beats=duration_beats,
                  progress=snapshot.get("target_index", 0)/max(1, snapshot.get("target_count", 0)),
                  feedback=feedback, feedback_unmapped=0)
    return fields
