# Transport, score admission, and spoken count-in: production contract

This document records the production ownership boundaries. Future fixes must
change the owning component and extend its acceptance test, not add another
playback path or special-case timer.

## Why repeated bugs happened

The earlier implementation allowed `main.gd` to withdraw future notation
before knowing whether the renderer could admit its replacement. The
renderer's own READY and Resume paths then recomputed positions against a
possibly changed queue. That permitted blank gaps, missing source strips and
the generic "Score is not ready" rejection. Test coverage mainly checked
individual renderers and calculated world coordinates, not the real
control-to-score transaction.

The spoken countdown was initially implemented with four independent
network downloads. Failure was silently converted into a metronome click
and the visual preference still said speech was enabled. After bundling
the files, `AudioStreamPlayer` remained a child of a UI countdown element,
and the metronome coordinator maintained separate tick counters for Start,
Resume and Retry. The old tests proved a mocked voice callback ran or
an audio player entered its "playing" state, but not that the same beat
and same persistent voice owner were used throughout the practice journey.

## Authoritative ownership

| Component | Sole responsibility | Must never do |
| --- | --- | --- |
| Python PracticeEngine / Coda-Fukuda | Musical source selection, tempo, graded deadlines and progression | Infer visual pixel placement |
| `ContinuousScoreFlow` | Monotonic presentation world clock | Pause, rewind, or alter music |
| `ScoreTransportReservation` | **Pure** Play/Resume/Retry preflight: check real source, exact printed header, viewport, peers, and hypothetical queue suffix | Mutate or instantiate score ink |
| `ScoreStreamQueue` | Online FIFO, immutable physical coordinates, archive, front expiry and maximum safe tail withdrawal | Change existing note positions or delete exposed items |
| `NativeView.reserve_transport_action` | **Only user-action commit route**: plan, withdraw safe suffix, reserve/arm future ink | Start backend transport without a valid reservation |
| `Main._send_action` | Pass authoritative musical opening to the reservation and only then command backend with returned lead | Independently trim the queue or invent another deadline |
| `CountInCueTimeline` | Deduplicate authoritative musical beat events, scoped by Start/Resume/Retry epoch | Run a timer, own sound, or alter the grading clock |
| `MetronomeFrameCoordinator` | Convert those beat events into either one spoken syllable or one click | Maintain separate counter/tempo rules per transport phase |
| `CountInVoicePlayer` | Root-owned audio playback, 4 shipped Ogg resources, persistent preference, clear diagnostics | Depend on rendered score, network, or UI widget lifecycle |
| `GameCountIn` | Draw the pulse circles for the same sampled beat | Own AudioStreamPlayer or infer timing |
| `FeedbackEventLog` / `FeedbackEventInbox` | The single acknowledged note-feedback channel; every event carries its own take identity (see `note-status-ink.md`) | Validate events against a state snapshot, or drop an unacknowledged event |

`score_stream_queue.gd.preview_tail_withdrawal()` and
`withdraw_tail()` share the **same exposure and protected-take
predicate**. A preflight examines a copy of the queue and leaves live
music untouched. If preflight fails, `command_state.abort_action()`
clears the provisional control and the backend receives nothing.
On commit, the queue's remaining length and the exact reserved graded
world coordinate are checked. A failed commit is reported in the terminal
with the `SCORE_TRANSPORT_PREFLIGHT` or `SCORE_TRANSPORT_COMMIT` prefix;
there is no legacy camera fallback.

## Non-negotiable temporal and visual rules

1. Every printed note/rest is inserted strictly beyond the right viewport
   edge, including its exact clef, key, and meter ink bounds, with one
   exception (rule 8). No later command may shift it, even by one pixel.
2. Play reuses its prepared READY owner when valid and other ink is still
   ahead of the playhead. An expired hidden reservation is withdrawn once
   and replaced from pre-engraved music. READY does not continuously
   re-enqueue on every frame.
3. Pause stops speculative admission, not the monotonic scroll. Resume
   keeps a safely reusable exact source; otherwise it withdraws the
   *maximum still-unseen suffix* and allocates a distinct future passage.
   Visible strips, historical source content, and the offline FIFO persist.
4. Repeated backend snapshots cannot enqueue another attempt with the same
   ID or produce another audible cue for the same beat. Retried passages
   have unique backend-epoch identifiers.
5. When no old ink blocks the screen, the extra travel budget is 0.12
   beat offscreen margin + 0.30 beat READY cushion (about 0.81 seconds
   at 31 BPM to first printed ink). A long passage still takes its real
   musical travel time to reach the fixed playhead; this is not a pause.
6. Audio is shipped in `godot/assets/countin/{ichi,ni,san,shi}.ogg`.
   Normal launches and practice never download, synthesize, or fetch
   third-party recordings. The voice player survives replacement of the
   countdown and score UI.
7. A missing/undecodable sample or muted Master bus is visible under
   **Practice → More**, including a manual **Test voice** control. A click
   fallback never reports itself as spoken playback. Headless CI verifies
   decoding and playback activation; physical speaker output requires a
   real-device check, which headless tests cannot establish.
8. **One count-in bar, short start** (owner decision 2026-11-08). The
   engine publishes `next_count_in_beats`: one full bar of the starting
   measure at any tempo (no seconds cap). When nothing of this queue or any live
   peer layer is printed right of the playhead, Play or Resume places the
   opening's first source beat exactly that far ahead
   (`ScoreStreamAdmission.empty_strip_start`); the never-seen hidden READY
   take is withdrawn, not reused from beyond the right edge. The new ink
   appears on the empty staff; it never pops in over, or ahead of, visible
   ink. Otherwise the append-only offscreen rule applies. In both cases the
   engine's `count_in_beats` stays that one bar: `run_at` equals the
   reserved score deadline, and any longer lead is silent. `CountInCueTimeline`
   and `GameCountIn` count and show only the last `count_in_beats` before
   beat 0 (`CountInCueTimeline.WHOLE_BAR`, one bar of the meter, for Retry
   preparation; a real `count_in_beats` of 0 counts nothing), so every take
   start speaks exactly one "Ichi, Ni, San, Shi". The count-in is always the
   whole bar at any tempo (owner decision 2026-11-08; the former
   `count_in_max_seconds` cap was removed). Resume reuses a paused take whose
   onset is still strictly ahead of the playhead (no reading floor), so
   Pause inside the count-in resumes with only the rest of that bar; the
   Resume countdown continues the same epoch and never repeats a syllable.

## Required regression gates

- `tests/godot/transport_reservation_integration.gd`: actual native queue
  and rendering path, preflight purity, Play, Pause, Resume, first visible
  measure conservation, future deadline and invalid request.
- `tests/godot/stream_rendered_note_overlap.gd`: no overlap, exact source
  windows, rollback, long exercise tail withdrawal and stale READY handling.
- `tests/godot/score_stream_admission.gd`: offscreen edge and entry latency.
- `tests/godot/countin_cue_timeline.gd`: unique epoch/tick emission,
  duplicate/stale snapshots, Pause/Resume and independent automatic retries.
- `tests/godot/countin_voice_assets.gd`: original bundled Oggs, direct
  decoding, root-owned service surviving countdown UI replacement, and
  actual frame-coordinator-to-voice event path.
- `tests/test_phase1_transport.py`: backend-sampled monotonic timing and
  source meter, without coupling to names of removed UI tick counters.
- `tests/test_note_reactions.py`: feedback events of a new transport reach
  the production ledger exactly once while the UI snapshot still names the
  previous transport.
- `godot/production_ui_smoke.gd`: actual Godot scene and embedded Python
  Play/Pause/Resume with immutable notation and audible cue scheduling.

All new presentation or transport changes must pass these gates on Godot
4.7.2 before being considered integrated. No heuristic rewind, silent
failure, optional download, or compatibility path may bypass them.
