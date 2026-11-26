"""One transaction-side shutdown of an active take.

No domain owner imports the application facade. Stop invalidates any score
authorization, seals or censors the current episode, and resets all physical
and projected state in its established order. It never chooses the next
lesson or grades the recorder.
"""
from __future__ import annotations



class SessionLifecycle:
    def __init__(self, *, transport, take, midi_input, score, lesson,
                 listen, measurement, clock, progress):
        self.transport = transport
        self.take = take
        self.midi_input = midi_input
        self.score = score
        self.lesson = lesson
        self.listen = listen
        self.measurement = measurement
        self.clock = clock
        self.progress = progress

    def stop(self, *, reason: str, preserve_episode: bool = False,
             persist_evidence: bool = True,
             preserve_musical: bool = False) -> None:
        self.transport.invalidate(reason)
        played = (self.take.recorder.presses
                  if self.take.recorder is not None
                  else self.measurement.guided.presses)
        if persist_evidence:
            try:
                guidance = self.lesson.guided_controller
                extra = ({"guidance": guidance.snapshot(now=self.clock())}
                         if self.transport.mode == "learn"
                         and guidance is not None else None)
                self.take.interrupt_current(
                    reason=reason, played=played, censor=not preserve_episode,
                    extra=extra, now=self.clock(), flush=True)
            except Exception:
                # The storage transaction rolls back the interrupted
                # evidence; keep the recorder/lesson available for a later
                # retry. Nevertheless the physical take must be inert now:
                # a failed disk flush cannot leave grading running after
                # Stop already invalidated its playback authorization.
                self.transport.finish_take()
                self.midi_input.deferred_midi.clear()
                self.transport.freeze_after_fault(self.clock())
                raise
        self.take.cancel_settlement(reason=reason, now=self.clock())
        self.midi_input.deferred_midi.clear()
        self.midi_input.clear_resume_gate()
        self.transport.clear_grading_floor()
        # Precompiled successors remain valid only for their source identity.
        self.score.stop_successor()
        self.lesson.stop_guided()
        self.lesson.clear_section_choice()
        if preserve_musical:
            self.transport.reset_for_stop(preserve_musical=True, now=self.clock())
        else:
            self.transport.reset_for_stop()
        self.take.reset_for_stop()
        self.midi_input.reset_live_input()
        self.listen.cancel()

    def shutdown(self, *, receive) -> None:
        """Close the active evidence/device/database once, in established order."""
        if self.measurement.closed:
            return
        self.stop(reason="shutdown")
        self.measurement.close()
        with self.midi_input.selecting_device("", callback=receive):
            pass
        self.progress.close()
