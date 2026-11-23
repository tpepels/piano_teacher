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
        played = (self.attempt.recorder.presses
                  if self.attempt.recorder is not None
                  else self.measurement.guided.presses)
        if persist_evidence:
            try:
                guidance = self.guided_session.controller
                extra = ({"guidance": guidance.snapshot(now=self.clock())}
                         if self.playback_session.mode == "learn"
                         and guidance is not None else None)
                self.settlement.interrupt_current(
                    reason=reason, played=played, censor=not preserve_episode,
                    extra=extra, now=self.clock(), flush=True)
            except Exception:
                # The storage transaction rolls back the interrupted
                # evidence; keep the recorder/lesson available for a later
                # retry. Nevertheless the physical take must be inert now:
                # a failed disk flush cannot leave grading running after
                # Stop already invalidated its playback authorization.
                self.playback_session.finish_take()
                self.midi_ingress.deferred.clear()
                if not self.visual_transport.paused:
                    self.visual_transport.pause(at=self.clock())
                raise
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

    def shutdown(self, *, midi, progress, receive) -> None:
        """Close the active evidence/device/database once, in established order."""
        if self.measurement.closed:
            return
        self.stop(reason="shutdown")
        self.measurement.close()
        with midi.selecting("", callback=receive):
            pass
        progress.close()
