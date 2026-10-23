# Application visual and UX audit — 23 October 2026

The audited starting point is fetched `main` at
`25777ad16506f052e7e2ebac6b2e2c4d00c2a5fb`, containing Phases 1 and 2.
PRs #37 and #38 and the local Phase 5 branch are still unmerged. This record
does not imply that those phases or their release coverage have completed.

## Actual application inspection

The production `main.tscn`, real backend and original MIDI were launched under
software OpenGL. Raw viewport captures were reviewed at 1920×1080, 1280×800
and 800×600. Ready, playing, paused, Library, Lesson Path and Settings were
inspected, including Ala measures 9–10, Chopin's opening pickup and measures
9–10, and Moonlight measures 9–10. RH, LH and Both were exercised on Ala and
Chopin; the latter Both passage contains 63 native note events.

The forest/pine palette, serif music titles, quiet supporting type, mint Play
button, connected grand staff, fixed playhead and restrained lighting match
the direction in `moodboard/moodboard.png`, its detail boards and
[the established art direction](art-direction-2026-10-20.md). The current
Library uses music shelves and the backdrop uses generated silhouettes rather
than the board's illustrative cover artwork. These established choices remain;
the audit did not replace functioning screens with a new design. Earned
feedback remains distinct from idle atmosphere.

## Corrections

1. Floating lesson navigation covered the upper fallback staff on compact and
   Both layouts. A reserved header now keeps lesson and hand-stage context
   above the notation. The original staff pixel test reproduced nine failures;
   all 180 checks passed after correction with the `.97` white and `.98`
   visible-rail thresholds unchanged.
2. Previous displayed a right arrow beside its left chevron. Arrow-only
   navigation now uses one centered caption and symmetric padding, retaining
   keyboard focus styling and compact hit targets. Labeled navigation keeps
   its normal icon.
3. Invalid lesson-step requests stopped the current attempt before rejecting
   the selection; fractional values and booleans could select an unintended
   stage. Validation now precedes transport/progress mutation. Invalid input
   preserves count-in, playback, pause, feedback, revision and saved tempos.
4. Moonlight failed to load because same-channel, same-pitch attacks overlap.
   The focused Phase 5 importer correction is reused: each attack and physical
   release is retained using explicit FIFO pairing. Import warnings state that
   this pairing is ambiguous. Missing releases still fail. Eight literal MIDI
   regressions protect endpoints, velocities, unisons and track/channel isolation.
   All 17 locally discovered MIDI files now load; loading does not certify their
   written transcription.

Manual **−5 BPM and +5 BPM remain direct controls**. The real UI journey checks
both buttons, saved tempo after forward/backward navigation, paused −5 BPM,
Retry preserving the chosen BPM, count-in, Play/Pause, RH/LH/Both, actual PCM
Listen playback and return to Practice, plus Space/P shortcuts. It switches
away before testing the Right control. The rendered X11 variant opens the
native lesson popup with a real mouse and selects an earlier entry using real
keyboard events. The headless variant covers its selection binding separately.

Production-engine regressions interleave manual changes with clean-take tempo
progression, SQLite reloads and stage navigation. Manual speed changes cannot
award mastery or preserve an invalid target-speed streak. Wrong, extra, late
and short notes still fail the existing strict grading criteria.

## Screenshots and reproduction

These PNGs retain their original captured pixels:

- [Practice, desktop](evidence/ux-audit-2026-10-23/practice-desktop.png)
- [Practice, compact](evidence/ux-audit-2026-10-23/practice-compact.png)
- [Chopin, compact Both](evidence/ux-audit-2026-10-23/chopin-compact.png)
- [Moonlight playing](evidence/ux-audit-2026-10-23/moonlight-compact.png)
- [Library](evidence/ux-audit-2026-10-23/library-desktop.png)
- [Lesson Path](evidence/ux-audit-2026-10-23/lesson-path-desktop.png)
- [Settings](evidence/ux-audit-2026-10-23/settings-desktop.png)
- [Before: contradictory navigation icons](evidence/ux-audit-2026-10-23/before-navigation-compact.png)
- [Capture checks and image hashes](evidence/ux-audit-2026-10-23/capture-summary.json)

With the project environment on `PATH`, a free port 8765, X11 and `xdotool`:

```sh
PIANO_TEACHER_NATIVE_NOTATION=1 LIBGL_ALWAYS_SOFTWARE=1 \
  python scripts/review_art_direction.py --render --exercise-controls --native-input \
  --sizes 1920x1080 1280x800 800x600 --output /tmp/piano-practice-ux
```

The same rendered journey is included in the existing desktop CI job and
uploads its raw screenshots, state evidence and logs. Development checks run
locally before hosted verification.

## Verification boundaries

The full local suite and final hosted checks are pending in this working record.
Their final results must be recorded before this correction is merged.

No physical MIDI piano is connected; only the system MIDI Through port was
available. Injected real-time MIDI journeys and engine grading tests do not
prove hardware latency or physical-keyboard behavior. Listen checks actual
downloaded PCM playback through Godot's Dummy audio driver; speaker audibility
is not established. Native popup input is covered on X11, not Wayland.

This is a manual visual/interaction review with bounded automated guards. It
adds no verified credit to Phase 3's independent musical/graphical ledgers.
MIDI transcription ambiguity, dense pixel assignment and unsupported notation
features retain their existing release blockers. Phases 3–5 still require
coverage completion, hosted verification and ordered merges.
