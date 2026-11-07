# P5 — Saved musical learning and complete learner journey

Final fresh verification: **450 tests passed in 157.57 seconds**. Godot
parser, independent review and `git diff --check` pass. All P0–P5 tests run
together, including the continuous real learner journey and actual UI/audio.

The existing consolidated course now teaches successive source-derived short
ideas before full-passage rhythm. Each hand/variant keeps its own prepared
units. After three clean full target-speed Practice passes, the course opens
the next learning stage; the final original all-note stage opens Perform.
Direct legacy timed clients retain their existing behavior.

Separate SQLite tables retain guided-unit resume/preparation, settled trouble
ranges and explicit skipped/placed decisions. They never write mastery.
The lesson path can revisit validated trouble from another stage, preserving
the selected tempo. Obsolete source bindings stay in history and cannot create
dead revisit controls or credit. Optional original-note placement and skips
remain visibly unmastered. Required stages still need three clean full runs.

One continuous actual desktop journey imports its own temporary MIDI and uses
ordinary controls, HTTP polling and timestamped MIDI callbacks. It prepares
both ideas (including wrong-note help), fails the same section twice, learns
that section, completes a partial retry without credit, restores
194 → 213 → 234 → 240 BPM and earns three full 240 BPM passes. It then enters
the earned original stage, plays the real 32-note audio example, misses all
32 notes in uninterrupted Perform, and reopens a saved trouble unit.
Result: **36 rendered frames, 274 callback events, 77.5 seconds, zero failures**.
Artifacts: `/tmp/piano-teaching-p5/final/`; the committed P4 baseline is rejected
by `/tmp/piano-teaching-p5/before-p5.log`.

Representative real-MIDI backend fixtures cover 16-bar easy melody, mixed
meter, sparse long rests, dense fast attacks, repeated chords and missing input.
Persistence/reopen, assisted preparation, explicit skips/placement, old source
identity rejection, deferred mastery and guided-course opt-in are covered.
Settings tempo changes retain the current guided idea instead of advancing it
or starting timed Practice behind Settings.

The actual imported piece independently retains **2,346 original events,
237 bars and 712 beats**, with 301 stages, 45 sections and 44 connections.
Complete-song engraving at 40 BPM passes required-note alignment with
**2,679 positioned glyphs across 60 pages**. Artifacts:
`/tmp/piano-teaching-complete-source/`.

Final playback preservation: **40 actual rendered samples at 30/40/80/120 BPM**,
plus a natural no-input preview ending. Maximum fixed-line drift is 0.0001 px;
paused-note drift is zero and active noteheads retain at least 100 detected ink
pixels. The pause-modal captures verify readable Resume text and frozen note
geometry; unpaused frames continue to require visible notehead pixels.
Artifacts: `/tmp/piano-teaching-final-playback/` (1536×886 actual desktop canvas,
window-manager clamped from the requested height).

## Remaining limitations

- Physical USB piano behavior, speaker audibility/latency and pedal acceptance
  still require a real instrument session. Simulated callbacks and audio PCM
  tests establish software behavior only.
- Listen uses a simple harmonic tone. Backend synthesis/transfer stream bounded
  chunks, but Godot decodes the whole WAV; the disk cache has no eviction policy.
- Resume is at a canonical guided idea, rather than a partially played chord.
  A manually shifted Learn selection such as bars 2–3 is temporary; reopening
  resumes the last canonical idea. It never grants preparation/mastery credit
  to a different unit.
- Timed recovery preserves the existing policy of restarting at the selected
  chunk and continuing through the passage ending. It is not an arbitrary
  start/end loop editor. Source timing/quantization and pedal scoring retain
  the existing engine's limitations.

No supplied song/exercise catalogue, new content service, proprietary assets
or new synthesis dependency was added.
