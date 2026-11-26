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
  - **Implemented; verification pending (2026-11-26):** The single Practice Flow verdict checks `minimum_accuracy_percent` (0–100, default 0). This uses the same combined metric as the live display. Existing failure conditions remain unchanged.
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
  - **Implemented; visual verification pending (2026-11-26):** The backend stamps the calibrated attack's musical-world coordinate and run identity onto existing feedback events. Godot projects the mark on the relevant outer staff rule using the same scrolling world, with mint/amber/coral/neutral ink and a 1.1-second fade. No snapping to a target note, and no changes to grading. Requires physical verification of early/late alignment, chord attacks, Free and handoffs.

- Simplify the saved-progress Review 2 prompt, remove Continue, and fade it on playback/input.
  - **Implemented; visual verification pending (2026-11-26):** Borderless saved-progress text and explicit Review previous steps / Choose measure links. Play or first MIDI input dismisses with a 220 ms fade, without score resize; input links are disabled during dismissal.
- Improve scrolling animation smoothness.
  - **Implemented; runtime verification pending (2026-11-26):** Explicit V-sync and display-paced FPS, no 33 ms low-power sleep during practice, stable monotonic clock offset for each musical run, binary timeline segment lookup. Low-power mode remains available outside practice. Actual frame pacing/GPU load needs measurement on the target display.
- An attack must no longer correct a previous note once the next note's authored onset has arrived.
  - **Implemented; verification pending (2026-11-26):** Both matching passes reject attacks at or beyond the next distinct onset; chords share the same deadline, and original tighter match windows remain. Live missing-note projection closes at that same deadline. New regression tests cover dense notes, wrong-pitch assignment, chord timing and live/final agreement.
