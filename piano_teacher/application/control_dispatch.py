"""Locked practice command routing, separate from the transport state owner.

PracticeEngine acquires its existing RLock, clears pending Listen failures and
lends the live engine only for the duration of dispatch. Actions retain their
original validation order, clocks and methods. No persistent state lives here.
"""
from __future__ import annotations

import time


class ControlDispatcher:
    @staticmethod
    def dispatch(engine, action: str, kwargs: dict) -> None:
        # Explicit navigation, Stop and Restart abandon the current attempt.
        # Only the timed feedback lifecycle commits an assessment.
        if action == "reset_path":
            engine._reset_current_path(
                fingerprint=kwargs.get("fingerprint"),
                confirm=kwargs.get("confirm") is True)
            return
        if action == "score_ready":
            revision = int(kwargs.get("revision", -1))
            # Ignore delayed PNG acknowledgements from older passages.
            if engine.awaiting_score_revision == revision and revision == engine.score_revision:
                if engine.paused:
                    engine._deferred_score_ack = revision
                    return
                if engine.mode == "listen":
                    engine.listen.acknowledge_score(revision)
                    engine._start_listen_if_ready()
                elif engine.mode == "learn" and engine.teaching is not None:
                    engine.awaiting_score_revision = None
                    engine.teaching.start(now=time.monotonic())
                else:
                    engine.start(from_beat=engine.pending_rewind if engine.pending_rewind is not None
                               else engine.open_from_beat,
                               mode="perform" if engine.mode == "perform" else "practice")
            return
        if action == "demo_ready":
            # The token identifies unchanged PCM even when a fingering
            # correction advances the score revision during download.
            # Stop, tempo changes and navigation discard that token.
            if engine.mode == "listen" and engine.listen.acknowledge_audio(kwargs.get("token")):
                engine._start_listen_if_ready()
            return
        if action == "listen":
            engine._prepare_listen()
            return
        if action == "perform":
            engine._prepare_perform(scope=str(kwargs.get("scope", "current")))
            return
        if action == "practice_weak":
            engine._practice_weak()
            return
        if action == "review_retry":
            engine._review_retry(kwargs.get("first_bar"), kwargs.get("last_bar"))
            return
        if action == "seek":
            engine._seek(kwargs.get("bar"))
            return
        if action == "learn_next":
            if (engine.mode != "learn" or engine.teaching is None
                    or not engine.teaching.snapshot(now=time.monotonic())["completed"]):
                raise ValueError("Find the current notes before continuing to the next idea")
            engine._save_guided_preparation()
            if engine._guided_return is not None:
                engine._prepare_practice()
            else:
                engine._begin_course_stage()
            return
        if action == "skip_stage":
            if engine.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs, not skips")
            engine._skip_stage(kwargs.get("reason"))
            return
        if action == "place_original":
            if engine.is_builtin_warmup:
                raise ValueError("Warm-up stages unlock after three clean runs")
            engine._place_original()
            return
        if action == "revisit_trouble":
            engine._revisit_trouble(kwargs.get("stage_key"), kwargs.get("start_beat"))
            return
        if action in ("learn", "learn_retry"):
            if action == "learn":
                engine.course_guided = True
                if "from_beat" not in kwargs:
                    engine._begin_course_stage(explicit_learn=True)
                    return
            previous_start = engine.guided_range[0] if engine.guided_range else 0.0
            engine._begin_learn(from_beat=float(kwargs.get("from_beat", previous_start if action == "learn_retry" else 0.0)),
                              recovery=engine._guided_return is not None and action == "learn_retry")
            return
        if action == "open_at":
            return engine._open_selected_measure(kwargs)
        if action == "practice":
            engine._prepare_practice()
            if kwargs.get("wait_for_player", False):
                # Returning from Listen must not start a count-in simply
                # because the renderer completed. Wait for a fresh piano
                # note or the central Play action.
                engine.awaiting_score_revision = None
                engine.feedback = "Ready to play"
                engine.next_action = "Play one piano key to begin, or press Play."
            return
        if action == "hints":
            engine.persistent_hints = bool(kwargs.get("enabled", False))
            if engine.teaching is not None:
                engine.teaching.set_hints(engine.persistent_hints, now=time.monotonic())
            return
        if action == "stop":
            engine._stop()
            engine.feedback="Stopped"
            engine.next_action="Start when you are ready."
            return
        if action in ("start", "restart"):
            return engine._start_or_restart(action)
        if action == "pause":
            return engine._pause_current_session()
        if action == "resume":
            return engine._resume_current_session()
        return engine._change_stage(action, kwargs)
