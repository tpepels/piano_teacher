# Lesson tempo and measure policy

This is a **tracked algorithm configuration**, not a preference in the UI.

Edit [`piano_teacher/lesson_settings.json`](../piano_teacher/lesson_settings.json),
commit the changed values, then restart the Python backend. No code changes
are required to experiment with another pace. Settings are validated on startup.

| Setting | Default | Meaning |
| --- | ---: | --- |
| `focus_measures` | 2 | Measures in a new focused learn section and error window |
| `repeated_tempo_min_attacks` | 2 | Minimum number of source note attacks before transferring a practice tempo to another identical passage |
| `start_tempo_bpm` | 40 | Common starting BPM for every new non-warm-up stage, unless the song target is lower |
| `automatic_tempo_steps` | 12 | Number of roughly equal tempo intervals from the common start to each song's target BPM |
| `manual_tempo_step_bpm` | 5 | BPM change when the student chooses **− BPM** or **+ BPM** |
| `minimum_tempo_step_bpm` | 1 | Floor for automatic BPM increases |
| `minimum_bpm`, `maximum_bpm` | 12, 300 | Allowed target/manual tempo bounds |
| `clean_runs_to_master` | 3 | Full clean runs *at target BPM* to unlock next hand/variant/section |
| `recovery_errors_in_window` | 5 | Errors that trigger an automatic slowdown |
| `warmup_recovery_errors` | 2 | Warm-up slowdown threshold |
| `recovery_tempo_multiplier` | 0.90 | Multiply BPM on recovery |
| `guided_recovery_after_failures` | 2 | Repeated failures before a guided recovery |
| `feedback_seconds` | 1.5 | Seconds for post-take feedback before auto restart |
| `grading_onset_tolerance_seconds` | 0.10 | Accepted attack timing error |
| `grading_duration_tolerance_fraction` | 0.20 | Allowed relative held-note duration error |
| `grading_duration_floor_seconds` | 0.055 | Minimum allowed held-duration error |
| `grading_match_window_min_seconds` | 0.35 | Minimum window to associate a played note with its expected pitch |
| `grading_match_window_beats` | 0.65 | Tempo-scaled matching window |
| `count_in_max_seconds` | 4.0 | Maximum count-in length before practice starts |

## Route and credit

The route teaches 1–2 at increasing speeds, then 3–4, connects 1–4,
continues with 5–6 and connects 3–6. The source grid (including
pickups and mixed time signatures) defines every boundary.

A new stage starts at the configured 40 BPM regardless of the source MIDI
tempo. Songs whose target is below 40 BPM instead start at that target.
For a song at 160 BPM and 12 automatic steps the ladder is 40, 50, 60,
70, 80, 90, 100, 110, 120, 130, 140, 150, 160 BPM. Intermediate values
are rounded to whole BPM and duplicates are removed for slower songs.

When a full focused take is clean, the backend advances to the next BPM rung
after feedback, without changing any note onset. Tempo never changes in the
middle of a take. The learner may use **− BPM** or **+ BPM** on the practice
screen while stopped, including slower than the shared start (down to the
configured minimum). These change only the saved tempo of the current stage.
Neither manual tempo change awards a clean performance or mastery.
They must still perform `clean_runs_to_master` clean takes at target BPM.
The active tempo is saved **for each stage** (source measure span, hand and
variant) across restarts and lesson-path navigation. Returning to earlier
measures restores their previous BPM, unless the overall target changes.

Error-driven slowdowns remain active. If the piano is disconnected, a
non-assessed preview does not increase tempo or earn mastery.

Changing `focus_measures` changes the composition of the route and stage
identities. Existing progress is safely located at the nearest source
measure, but mastery from incompatible old stages is not silently credited.

## Repeated passages

A new two-measure **learn** stage can start at the *earned* BPM already reached for an
exactly repeated musical passage elsewhere in the same imported piece. Matching
requires the same hand, simplification level, source-measure durations, pitches,
onsets and held durations. Absolute measure number, source-note IDs and track
numbers do not matter. Transposed passages or different note durations do not
match. Very short motifs below `repeated_tempo_min_attacks` never transfer BPM.

Only **tempo** transfers, not mastery, clean-run streaks, feedback results or
piano input. Every occurrence must still be played and graded independently.
An already-visited section keeps its own current tempo and error recovery,
including automatic slowdowns; another section's improvement cannot cancel
its recovery. The shared tempo survives ordinary application restarts through
the existing per-stage SQLite progress store. Changes to the overall target
invalidate all inherited stage tempos, just as they invalidate other ladders.

Only a clean attempt or explicit +BPM tempo increase marks a source stage as
transferable; slowing back to or below the shared start removes that eligibility. Choosing a new target in Settings does **not** propagate that
number to repeated passages. Eligibility is saved separately in SQLite, so
reloading the app cannot turn an unplayed target into evidence of progress.

## Direct practice navigation

The Practice screen shows every curriculum step, including measure range,
hand and note-variant level. The selector and previous/next arrows can jump
forward or backward without assigning mastery. The selected step resumes its
previously saved tempo and clears its current clean-run streak; returning to
an already-visited step restores its stored tempo.
