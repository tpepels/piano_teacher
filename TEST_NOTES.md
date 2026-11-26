# Testing notes
These notes are filled by Tom after he plays on the piano. These serve as input for the next steps in developing the application.

## Remarks
- Connecting or selecting the keyboard after the application started gives strange results. I think this needs a test because I'm not sure what happens.
  - **Implemented; verification pending (2026-11-26):** The backend alone restores the preferred MIDI device. Selecting the same connected device is idempotent; a physical port generation prevents stale callbacks and deferred messages from a replaced port. Guided held state is cleared on device change. Three connection regression tests added; local CI and live keyboard checks remain pending.
- Please keep track of accuracy and show it in the top-left corner next to the tempo ...
  - **Implemented; verification pending (2026-11-26):** Revised to live whole-take accuracy, combining pitch and timing credit with missed and extra presses. Upcoming unplayed notes do not count prematurely. Final accuracy uses the same metric.
- After performing correctly twice at 100% please ask if I want to do it again or if I want to proceed. Let me practice again at 100% by playing a C and proceed with the next by playing an F. Mention the accuracy, so I can make a good decision.
  - **Implemented; verification pending (2026-11-26):** Only the final required hand of each routine window offers the C/F decision, after two accepted target-tempo takes. Mastery is saved before the prompt; its accuracy remains visible. C repeats the final hand at target tempo, F enters the next unmastered window, and tempo/hand changes are automatic. Repeating uses the normal two-clean-take rule again. The prompt is transient; saved mastery survives reopening.
- The on-screen notifications are a bit wierd there are several kinds and they don't have a common place. Please make 1 type of notification, make sure that it's not overlapped by the count-in and display all messages there. Also make sure that the messages are "user-facing" not development speech leaking into the ui. Make them a bit interesting and fun. Examples:
  - New tempo
  - New hand
  - New section
  - Show accuracy in the relevant messages
  - Try again... 
  - Well done: xx% accuracy!
  - Try again: xx% accuracy!
  - Etc.
  - **Implemented; verification pending (2026-11-26):** Practice transitions, result accuracy, short input notices and command notices use one fixed notification row above the score, separate from the count-in. Removed the duplicate hand cue, phase cue and unused feedback badge from the practice stage. Score loading/recovery controls and per-note markings remain distinct. Backend course messages include measure/hand and graded result accuracy; no extra musical delay.
- Once we have a good measure for accuracy I will ask you to also force retry on low accuracy, you can add that functionality now, but I have to find a good value for it, so please let it always pass now (i.e. even 0% accuracy passes) and later we can increase it. But this is seperate from missed notes, missed notes or wrong notes always trigger a retry.
  - **Implemented; verification pending (2026-11-26):** The single Practice Flow verdict checks `minimum_accuracy_percent` (0–100, now 85). This uses the same combined metric as the live display. Existing failure conditions remain unchanged.
- For the non-tempo play, please be more tollerant regarding when the note can be pressed, now the bar really needs to be stopped, that's not necessary, though we should check if we are somewhat in range of the note, but not too strict.
  - **Implemented; verification pending (2026-11-26):** Free accepts the current target up to 250 ms before its scheduled arrival; earlier keys still do not count. The timeline, chord/gesture rules and Pause are unchanged.
- After the first measure, the key-signature and cleff symbols are no longer shown which is problematic because we need to know them for each practice session, so please just always show them.
  - **Implemented for every practice-window opening; visual verification pending (2026-11-26):** The painter now identifies the selected opening rather than the first atlas measure, and draws its full current clef, key signature and meter regardless of hidden predecessor context. Repeats reuse the same opening ink. This is a scrolling opening header, not a fixed screen overlay; check later measures, nonzero key signatures and repeats at the piano.
- In the Pathetique sonata for the first measures I still have to play the left-hand two quater notes starting at 50%, my god that takes a long time :) So we need to also calculate this base tempo because this is just annoying when it takes so long just to play two notes.
  - **Implemented; verification pending (2026-11-26):** Sparse single-hand windows with no chords and at least 450 ms between attacks at nominal target tempo start at 100% for 1–2 attacks or 80% for 3–4. Other windows and the final test retain 50%. The recovery floor remains 50%; recheck Pathétique at the piano.
- When the application switches from 1 hand to 2 hands, and switches from 1 section to another there is a visual blink that kind of moves everything on screen. But the application should never blink or suddenly change, the bar should just keep moving.
  - **Implemented; verification pending (2026-11-26):** Automatic source transitions retain the musical world clock and an open, ungraded rest; the outgoing staff owns the playhead until new engraving is published. Godot samples the old clock before adopting a new run. Explicit Stop still resets the transport. Check the hand/section transition at the piano, especially fitted score sizes and narrow viewports; no physical visual acceptance yet.
- Notes in the small measure in the lower-right-hand corner sometimes 'stick' they never get removed even though the notes are no longer held.
  - **Implemented; verification pending (2026-11-26):** Physical held-key state now observes current-device events before grading/shortcut filters. Deferred grading does not replay physical state. Channel-specific key tracking handles duplicate Note On and velocity-zero Note On releases; older timestamped events cannot overwrite newer state. Device clearing resets the physical state. Recheck at the piano across transitions and keyboard changes; local CI not run.

- Resume by playing C on a connected piano, with a visible note hint on the button.
  - **Implemented; verification pending (2026-11-26):** While paused, fresh C in any octave resumes; the attack and release are consumed before grading. Main transport button shows a miniature piano-key C hint; the advanced Pause menu shows C as well.

- Allow playing warm-up notes in the rests and count-ins between timed takes without registering or showing a message.
  - **Revised; verification pending (2026-11-26):** Ordinary attacks in inter-take rests and count-in outside the existing early matching window appear as neutral fading glyphs only. No assessment or notification. The new measure-tail rule also applies within takes.

- Ignore new attacks in the held-note or rest tail after each measure's last attack; preserve the existing first-note and late-note timing tolerance.
  - **Implemented; verification pending (2026-11-26):** Uses selected-hand attack times and authored measure boundaries on the grading clock. Internal rests remain graded; releases still reach the recorder. First attacks can be matched early, and admitted current-take notes bypass premature deferral. Five measure admission regression tests added.
- Redesign the large yellow notification banner so it is readable close to the music.
  - **Implemented; visual verification pending (2026-11-26):** Compact mint text aligned above the playhead, without a box or yellow border, with short fades and invariant layout. Count-in remains separate.
- Actual wrong-pitch ghosts must fade; show warm-up pitches briefly too.
  - **Implemented; visual verification pending (2026-11-26):** Red wrong-pitch ghosts fade over 600 ms, neutral warm-up ghosts over 380 ms. They never change authored note marks or the grading ledger; the warm-up layer works without a graded source strip.

- Spell wrong and warm-up pitches in the written key signature (e.g. G-flat without a flat in G-flat major; G-natural with a natural).
  - **Implemented; visual verification pending (2026-11-26):** Both transient glyph types use the measure's staff-specific signature, including enharmonic octave boundaries. Diatonic pitches omit accidentals; natural cancellations and out-of-key alterations are explicit. Ghosts do not mutate authored accidental state.
- Show every ordinary attack as a small glowing bump on the moving staff so actual timing is visible.
  - **Implemented; visual verification pending (2026-11-26):** The backend stamps the calibrated attack's musical-world coordinate and run identity onto existing feedback events. Godot projects the mark at the actual played pitch using the same key-aware vertical geometry as fading notes and the same scrolling world, with mint/amber/coral/neutral ink and a 1.1-second fade. No snapping to a target note, and no changes to grading. Requires physical verification of early/late alignment, chord attacks, Free and handoffs.

- Simplify the saved-progress Review 2 prompt, remove Continue, and fade it on playback/input.
  - **Implemented; visual verification pending (2026-11-26):** Borderless saved-progress text and explicit Review previous steps / Choose measure links. Play or first MIDI input dismisses with a 220 ms fade, without score resize; input links are disabled during dismissal.
- Improve scrolling animation smoothness.
  - **Implemented; runtime verification pending (2026-11-26):** Explicit V-sync and display-paced FPS, no 33 ms low-power sleep during practice, stable monotonic clock offset for each musical run, binary timeline segment lookup. Low-power mode remains available outside practice. Actual frame pacing/GPU load needs measurement on the target display.
- An attack must no longer correct a previous note once the next note's authored onset has arrived.
  - **Implemented; verification pending (2026-11-26):** Both matching passes reject attacks at or beyond the next distinct onset; chords share the same deadline, and original tighter match windows remain. Live missing-note projection closes at that same deadline. New regression tests cover dense notes, wrong-pitch assignment, chord timing and live/final agreement.

- Attack dots should appear at the actual played pitch rather than on the outer staff rule.
  - **Implemented; visual verification pending (2026-11-26):** The sequenced trace retains physical pitch, played source beat and score revision. The dot and transient note share the exact key/clef/staff geometry, including ledger positions. Outgoing dots retain the renderer of their source revision during handoffs. Horizontal timing, colours, fades and assessment are unchanged.

- Prevent long-delayed note corrections and require 85% accuracy for progression.
  - **Implemented; verification pending (2026-11-26):** Configurable absolute late-match limit of 200 ms, exclusive, combined with the next distinct onset and the existing matching window. Both pitch-assignment passes, live missing-note publication and measure-tail admission share the limit. Earlier matching tolerance and note-release handling remain unchanged. Practice Flow requires at least 85% combined accuracy as well as its existing error checks, including both target-tempo passes. Updated admission regression expectations and added three regression tests.

- Make on-score messages more game-like with distinct positive and retry feedback.
  - **Implemented; visual verification pending (2026-11-26):** Typed course outcomes supply distinct headlines, accuracy and next instructions. Mint successes, champagne milestones, muted peach retries and teal/blue-green phase cues share the same playhead-aligned lane, with a subtle success pulse and fade. No changes to grading or progression.

## Local CI triage (2026-11-26)
Uploaded Python run: 215 passed, 140 failed, 3 warnings. No commit SHA in log; it predates at least some latest notification/late-cutoff changes. Godot was not reached. First batch: replace exact result-caption assertions in failure-grading/repertoire tests with typed outcome assertions, update changed warm-up and note-cutoff expectations, and restore the half-tempo recovery entry after Free. Remaining test failures and any newly exposed assertions must be rerun and investigated; no acceptance claimed.

- Avoid tedious recovery from near-passes.
  - **Implemented; verification pending:** `recovery_accuracy_percent` defaults to 70. Failed takes at or above it repeat the same stage and BPM, clearing consecutive recovery failures without awarding mastery. Only consecutive below-threshold failures trigger the existing slower/Free policy. The 85% pass threshold and independent note checks are unchanged.

- Reduce further scrolling frame overhead.
  - **Implemented; verification pending:** Share cached exact-time timeline calculations across source beat, world position, rate and holds; index take IDs when a timeline is published; measure monotonic offsets once per run/process instead of every state poll. Fully visible retained clips preserve their exact width and local source position during translation. No smoothing filter, delayed MIDI or secondary clock. Frame diagnostics remain available; target-display measurement required.

- Smooth the practice background and playhead glow (visible concentric colour bands).
  - **Implemented; visual verification pending (2026-11-26):** Dedicated practice backdrop shader with a continuous teal gradient and static sub-code-value screen-space dithering; softer elongated capsule playhead bloom with a pixel-sized core/halo, smoothly feathered ends, stationary alpha dithering and no playhead brightness pulse. Existing placement, notation and other glow shapes remain unchanged. No extra viewport, texture or postprocessing pass. Verify on the target OpenGL display.

- Ignore AFK-like takes below 5% accuracy.
  - **Implemented; verification pending:** Configurable `ignored_accuracy_below_percent` is checked in the canonical verdict. Preserve progress and preceding valid recovery/verification decision, discard open attempt and cascade checkpoint/evidence rows, and retry automatic practice at the same BPM. No mastery/failure count or assessment row. Session elapsed-time totals are retained; no completed review is shown. Existing 70% recovery and 85% pass thresholds remain.

- Improve residual scrolling jitter despite nominal 60 FPS.
  - **Implemented; verification pending:** Microsecond-resolution frame sampling, same-publication source beat/world calculation, explicitly disabled 2D pixel snapping. Opt-in wall-time and projected pixel displacement/speed diagnostics distinguish actual callback pacing from Godot delta and within-passage movement. No display timing or physical MIDI verification yet.

- Move sight reading out of Settings and into the gear drawer as its own page, alongside Play, Music and Settings. **Implemented; visual verification pending.** Level and named tempo choices are preserved in the page for subsequent rounds; command busy/error handling uses the existing command coordinator. No changes to generated music or assessment.

- Remove the navigation-owned 60 FPS limiter that undid native-refresh playback. **Implemented; verification pending.** Practice and active calibration remain uncapped (V-sync), idle pages retain power saving. Removed the conflicting per-frame sleep toggle from Main. Added pacing regression checks to the existing Godot practice-controls suite and display configuration to diagnostics. Uploaded log showed stable projected motion in 47 playing windows, occasional actual frame intervals up to 22.128 ms, and a separate 445.917 ms loading stall. Display presentation and the loading stall remain unverified/unresolved respectively.

- Fix repeated fingering corrections in Pathétique. **Implemented; verification pending.** Fingering-only commits preserve musical revision, current take and admitted geometry. The semantic-model cache tracks the derived fingering plan separately. Accepted snapshots carry a cached display-window annotation version and assignments, so the renderer updates the fingering overlay without replacing the score, including on subsequent polls and late bundle responses. Errors are scoped to fingering rather than library loading. Verify sequential edits, removing a correction, neighbouring recomputed fingers, and edits during paused/running practice.

- Allow the double-thumb chord technique (e.g. neighbouring D-flat/E-flat black keys) in fingering inference. **Implemented; piano verification pending.** The adapter searches ordered chord assignments with an optional two-key simultaneous thumb pair, including manual/authored and automatic assignments and fixed/held overlap constraints. No sharing across separate onsets or keyboard heights, no third thumb key, and no sharing of fingers 2–5. Adapter version 4 invalidates derived plans only; durable overrides are retained. Eighteen direct constraint checks passed against the exact search helper; actual ONNX inference, full CI and piano acceptance not executed. Verify on a six-key chord, two consecutive manual thumb corrections and removal of a correction.

- Further animation responsiveness audit. **Implemented; verification pending.** Limit ambient barline coverage to visible printed strips, calculate exact visible meter extensions beyond the former 80-bar cutoff, avoid creating a full take-start map every count-in frame, and report main-thread bundle/retained-readiness timing breakdowns. No alterations to MIDI timing, world clock, visual interpolation or admission policy. Manual source review only; Godot syntax, CI, and comparative hardware timing not executed. The earlier fingering partial-chord regression remains a separate open issue.

- Move score preparation off the rendering thread and reduce lesson-handoff loading overlay/glow flicker. **Implemented; verification pending.** Detached worker builds validated CPU-only engraving; render thread uploads in slices and installs the same owner, then compiles initial retained strips incrementally. Source request and viewport identities guard publication. Old staff and playhead glow persist until replacement readiness. GPU creation, scene-tree updates, retained draw calls and status-head warmup remain on main. Godot syntax, CI and physical display verification not executed. Verify rapid navigation, retry, resize, long scores and lesson transitions on hardware.

- Follow-up: prepare notehead interior masks off-thread and reuse authentic CPU pixels during display resampling. **Implemented; unverified at runtime.** Null interior for a solid head is a valid cached result. Status GPU warmup and size-dependent texture resampling still run on main.

- Review recent rendering/fingering commits: repaired stale loading status, hidden-page retained compilation timeout, initial strip invalidation on resize and staff ownership when closing music; kept playable finger assignments when another note makes a complete chord infeasible. Added real-worker score readiness and retry checks, long-range meter checks and real-model double-thumb/partial chord tests. Re-enabled automatic core and dedicated fingering CI on main pushes; full remains manual. Await actual CI results before marking verified.

- CI follow-up: independent Godot job, all Godot scenarios attempted, and exact-commit status reporting for Python, Godot and fingering. Strengthened readiness test to inspect two actual annotation edits and removal on the same engraving. Full package and physical acceptance remain separate. No completed CI result available during this review.
