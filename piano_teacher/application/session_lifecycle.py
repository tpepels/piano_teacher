"""One transaction-side shutdown of an active take.

No domain owner imports the application facade. Stop invalidates any score
authorization, seals or censors the current episode, and resets all physical
and projected state in its established order. It never chooses the next
lesson or grades the recorder.
"""
from __future__ import annotations

from ..lesson_settings import SETTINGS


class SessionLifecycle:
    def __init__(self, *, playback, playback_session, attempt, settlement,
                 midi_ingress, visual_transport, continuation, guided_session,
                 live_input, listen, measurement, clock):
        self.playback = playback
        self.playback_session = playback_session
        self.attempt = attempt
        self.settlement = settlement
        self.midi_ingress = midi_ingress
        self.visual_transport = visual_transport
        self.continuation = continuation
        self.guided_session = guided_session
        self.live_input = live_input
        self.listen = listen
        self.measurement = measurement
        self.clock = clock

    def stop(self, *, reason: str, preserve_episode: bool = False,
             persist_evidence: bool = True) -> None:
        self.playback.invalidate(reason)
        self.playback_session.cancel_suspended_admission()
        played = (self.attempt.recorder.presses
                  if self.attempt.recorder is not None
                  else self.measurement.guided.presses)
        if persist_evidence:
            guidance = self.guided_session.controller
            extra = ({"guidance": guidance.snapshot(now=self.clock())}
                     if self.playback_session.mode == "learn"
                     and guidance is not None else None)
            self.settlement.interrupt_current(
                reason=reason, played=played, censor=not preserve_episode,
                extra=extra, now=self.clock(), flush=True)
        self.settlement.cancel(reason=reason, now=self.clock())
        self.midi_ingress.deferred.clear()
        self.midi_ingress.clear_resume_gate()
        self.visual_transport.clear_grading_floor()
        # Precompiled successors remain valid only for their source identity.
        self.continuation.stop()
        self.guided_session.stop()
        self.visual_transport.reset_for_stop(
            rewind_seconds=SETTINGS.feedback_seconds)
        self.playback_session.reset_for_stop()
        self.attempt.reset_for_stop()
        self.live_input.reset_attempt()
        self.listen.cancel()
