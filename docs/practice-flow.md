# Practice flow for one piece

This is the owner specification for the default `practice-flow` course.
Production code must follow it. Where another document or an older stored
policy disagrees, this contract governs the normal desktop flow.
[Architecture](architecture.md) describes its owners; [ROADMAP](../ROADMAP.md)
records implementation and dated verification. The owner accepts the experience
by playing at the piano; headless checks do not establish physical acceptance.

The learner plays the real notes of the piece unless the app has explicitly
announced a simplified exercise. Every state should be recognisable from a
piano lesson.

## Open a piece

Opening a new MIDI or MusicXML file starts the first measure window with its
own Listen step. It does not first play the whole piece. The source supplies
target tempo, authored measure boundaries, notes, hands and complete releases;
MusicXML is read as the same timeline (each staff one hand, repeats as
written). Fingers written in the MusicXML are kept as authored fingering;
your own corrections still win and automatic fingering fills the rest.

## Learn moving measure windows

Introduce each new authored measure alone, then repeat it with successively
more preceding measures, up to four measures in a routine window:

**1; 2, 1–2; 3, 2–3, 1–3; 4, 3–4, 2–4, 1–4;
5, 4–5, 3–5, 2–5; …**

Complete each window before advancing. Every window has its own progress,
tempo and mastery identity; overlapping music does not imply shared completion.
Practise right hand, then left hand, then both together when those hands have
notes. Skip empty hands without inventing notes or achievements.

A note attacked within the selected window keeps its full original release,
even beyond the last barline. A silent authored bar creates no MIDI attack.
The routine four-bar cap does not truncate a sustained ending.

### Listen

Play the selected window once at the original target tempo. Notes scroll past
the playhead and light as they sound. Nothing is graded. Then enter Free.

**Listen again** repeats the current passage at target tempo without awarding
progress or bypassing its learning steps.

### Free

The learner finds all notes of the **complete current window** in order at any
pace, without rhythm scoring. Free does not silently shrink the selected
window to an earlier two-bar guided unit.

- The next target waits at the playhead. The axis stays still while thinking.
- Keys count from 250 ms before the target's scheduled arrival at the playhead.
  Earlier keys earn nothing and a short message asks the learner to wait.
  The staff still follows its declared travel and hold timeline. The target travels in from beyond the
  right edge and stops exactly at the playhead, within about three seconds
  (on a slow piece the staff moves faster than the tempo to get there).
- A correct note turns green; the staff moves to the next target.
- A wrong note turns the intended note red, shows the keyboard hint and waits
  for the correct key.
- A target is found only by its own keys. Keys pressed within 80 ms of each
  other are one movement of the hand: a cluster, a sweep over the keyboard or
  a smudge from a neighbouring key that includes the right note finds nothing
  and turns the target red. No keyboard appears simply because the learner waits.
- After every target has been found, Tempo begins automatically.

### Tempo

Start at a calculated tempo. For a single hand with at most four single-note attacks separated by at least 450 ms at the nominal target tempo, start at 100% (one or two attacks) or 80% (three or four attacks). Dense material, chords, two-handed practice and the whole-piece final test start at 50%. The recovery floor remains 50% of target so a learner who struggles can slow down.
Each attempt has one authored
bar of count-in ending immediately before the first note. Skip a leading rest
or pickup inside the selected window, including a short rest within its first
bar; do not make the learner sit through it.

| Attempt result | Next action |
| --- | --- |
| Clean below target | Increase by **10% × (1 + timing quality) × length factor** of target, capped at target |
| Failed attempt with accuracy at or above the recovery threshold (70%) | Repeat at the same tempo; clear consecutive recovery failures |
| One failed attempt below the recovery threshold | Repeat at the same tempo |
| Two consecutive failures below the recovery threshold above 50% tempo | Decrease by 10% of target, never below 50% |
| Two consecutive failures below the recovery threshold at 50% tempo | Return to Free (except the final test) |
| Two consecutive clean attempts at target | Complete this hand; automatically enter the next hand, or offer the section choice after the final hand |

The header shows live accuracy for the entire current graded take. Each correctly pitched note earns `max(0, 1 − |onset error| / onset tolerance)` credit; wrong and missed notes earn zero, and extra presses add zero-credit entries to the denominator. Future notes are excluded until played near their onset or their matching window expires. Before any evidence the display is blank (—); the final percentage uses the same metric. The separate timing-quality metric still controls tempo increases. The developer-tunable `minimum_accuracy_percent` in `lesson_settings.json` is set to 85; otherwise passing takes below 85% retry without weakening existing note or hold checks. Both target-tempo passes must satisfy the threshold. The separate developer-tunable `recovery_accuracy_percent` defaults to 70. A failed take at or above this percentage repeats the current step at its current tempo, clears the consecutive low-accuracy counter, and still breaks the mastery streak. Only consecutive failures below this threshold trigger slower tempo or a return to Free.

Timing quality is 1 when every attack is centred and 0 when attacks sit at
the edge of their window (1 − mean |onset error| / tolerance). The length
factor is 8 ÷ attacks, clamped to 1–2.5, so a short window climbs quickly:
two quarter notes played well reach the target after one take, while a
16-note window gains 10–20% per clean take. Two clean takes at target still
complete the window.

A slower success is practice, not target-tempo mastery. A failed attempt breaks
the target clean streak. A clean flow attempt has all required pitches and
accepted onsets with no extra keys. In Settings, **Grade how long I hold notes**
is off by default; when enabled, release errors also fail a take.
After an attempt, the next follows directly: the rest runs from the last
sounding note (ties included) to its barline, then one count-in bar whose
first half eases to the new tempo, with no added feedback break. The staff keeps moving forward; the
repeat comes from the right and never jumps back.

The one-bar repeat takes priority over decorative context: neighbour bars may
be limited during the repeat rather than delaying it or overlapping active ink.

## Grow the window and finish

After all required hands complete a window, save mastery and show the final
accuracy with a persistent choice: **C** repeats the final hand at target tempo;
**F** proceeds to the next unmastered window. The visible Repeat and Next
section controls offer the same actions. A repeat follows the normal two-clean
rule again. The choice is never offered between tempo increases or hand stages.
The staff continues through ungraded rests while awaiting the decision.
There is no separate phrase-link generator that silently selects longer or
different music. The next new measure starts alone again.

After the last moving window, play the **whole original piece with both hands**
as the final test. Apply Tempo rules from 50% to original tempo, finishing after
two consecutive clean attempts at target. Then the piece is learned. The final
test is separate from the four-bar routine window limit.

## Resume

With a connected piano, press a fresh C in any octave while paused to resume. It is consumed as a transport command, including its release, even if C is a note in the exercise. The Resume button displays a piano-key hint. Calibration and keyboard-range capture take precedence.

Reopening saved progress returns to the same window and hand at **Free** for
warm-up, rather than immediately running at saved tempo. This also applies to
saved final-test progress: reopen at whole-piece Free, then restart Tempo at
50%. A partial chord or held physical key is not saved as completed learning.

The music list shows how far each practised piece is: the share of its
windows (and the final test) mastered at target tempo, with the bar being
learned, for example “38% · bar 12 of 32”, and a thin bar under the title.
A finished piece reads “Learned”; a piece never practised shows none.

## Telling the learner

Whenever practice cannot continue by itself, the score banner says why and
what to do, in words that match the controls on screen:

- No piano connected, in Free: "No piano connected." with how to fix it.
  Free continues by itself, keeping the notes already found, as soon as the
  piano is found again (it is looked for every few seconds).
- The piano is lost during a Tempo take: the take stops, the banner says so,
  and once it is back: "Piano connected again … Press Play when you are
  ready."
- Keys outside a timed take's matching window are warm-up input:
  no grading or notification, only a briefly fading neutral played-pitch
  glyph. Explicit shortcuts still work.
- The first Tempo attempt reads its selected tempo percentage (the 50% floor
  is labelled 50% even when rounding to a whole BPM moves it slightly).

## Checkpoints

Every fourth measure (1, 5, 9, …) is a checkpoint. The pause menu shows them
as measure numbers: marked where you are, highlighted when every window that
ends in those measures is mastered for every hand. Choosing one starts that
measure's window from Listen; saved progress elsewhere is kept. After a
window is mastered, the next step is the next one not yet mastered, so a
jump back is a targeted review and the course then returns to where you were.

## Simplified exercises (Coda / Fukuda)

Coda/Fukuda is an aid, not part of the normal Listen → Free → Tempo order.
On the **second return to Free caused by repeated floor-tempo failure** for
the same source window/hand, enter an eligible simplified exercise automatically.
That return count is saved for the exact window and hand across reopening.
Announce exactly what changed, for example “Simplified: broken chords played
together”. Never present changed music as the original score.

After the aid, return to **Free on the original notes**, then the normal Tempo
ladder. Simplified success does not grant original-window mastery. If no genuine
source-safe simplification is available, retain original Free rather than
fabricating an exercise. Source IDs, sustained releases and hand identity remain
bound to the real piece throughout the aid.

## On screen

The music is the focus:

- One staff stream scrolls right to left past a fixed playhead in Listen and
  Tempo. Free holds the next target at that same playhead.
- Display only the currently selected authored practice window (one to four
  measures), with its full authentic held-note tails. Neighbouring measures
  may be used internally to engrave ties, clefs and safe clip boundaries,
  but must not appear as additional exercise measures. The selected
  window retains its original closing barline and any authored repeat mark.
- Keep the hand not being practised visible but dimmed.
- Show finger numbers wherever known. Never invent an unavailable assignment.
- Space fast notes generously: about **4.3 staff spaces per sixteenth** at least.
- Clef, key signature, meter and the first note each keep their own space; none touch.
- Use one small status label indicating the current window, hand and step.
- Hide the piano keyboard except for a wrong-note hint in Free. It is drawn
  as a small real keyboard (ivory and ebony keys, about two octaves) at the
  left end of the Pause/Resume row, not stretched across the screen.
- A small, bright grand staff (treble and bass clef) at the right end of that
  row shows the keys held on the piano right now as whole notes: nothing
  else, no history. The row keeps its height, so nothing under the score
  moves when the hint appears.
- No markers float above the score; the playhead marks where you are.
- Glows stay soft and inside their own control: no glow reaches a
  neighbouring button or shows a square edge.
- **Pause** freezes both the visible score and the graded/untimed exercise.
  Resume continues the selected passage after one complete count-in bar
  (from the paused beat, or from the window's opening when paused in its
  count-in), without presenting new notes during the pause. In Free, the
  next target holds still until the correct key.
- Every control type has its own look, so you can see what can be pressed:
  menu choices are large words with a key notch (lit when chosen); actions
  are raised key caps (danger ones rose); a pick-one group is a row of keys
  with the chosen one filled; list rows are cards with an ivory key edge and
  a play badge; checkpoints are small cards. Plain text is never framed.
- Keep **Pause/Resume** and **Listen again** as the practice controls; show
  **Repeat (C)** and **Next section (F)** only at a completed section boundary.
  Everything else progresses automatically. This controls the visible normal flow;
  configured physical MIDI shortcuts and existing keyboard/API tools remain.

### Count-in and metronome

Use one bar of metronome clicks with large beat numbers, appropriate to the
authored meter. Count-in ends just before the first playable note. The metronome
is on by default and can be switched on screen. Clicks, spoken cues, note motion
and MIDI grading follow the same authorized musical deadline.

### Feedback

Colour every played or missed note promptly: **green** for correct and **red**
for wrong or missed. The glow around a notehead is the notehead's own
colour. A wrong key also produces a red ghost at the played pitch that fades
out within 600 ms. Warm-up pitches fade within 380 ms, in neutral ink near the
playhead, without changing any authored note's assessment colour.
Transient pitch spelling follows the key signature at the played source
beat. In-key pitches have no printed accidental; natural cancellations and
other chromatic alterations are explicit. Ghosts do not change the measure's
authored accidental memory.

Every ordinary physical attack on the musical timeline also leaves a small
glowing dot at the actual played pitch on its staff, with the same
key-aware vertical placement as transient note glyphs. Its horizontal coordinate is
the calibrated hardware attack's actual world beat, never the expected note
position or feedback receipt time. The mark scrolls with the same score
world and fades within 1.1 seconds. Mint indicates accepted timing, amber
an early/late judgement, coral an unexpected attack, and muted ink ungraded
input. The trace is presentation only and cannot affect assessment.
Listen lighting is ungraded and cannot award performance credit.

A slightly early/late attack remains green. A note's matching window closes
at the earliest of the next distinct authored attack onset, the ordinary
matching deadline, or 200 ms after the scheduled attack (configurable
`grading_max_late_attack_seconds`). The cutoff is exclusive and independent
of practice tempo; simultaneous chord notes share a deadline.
No attack at or after that next onset may correct a previous note. Live
missing-note feedback and final grading use the same cutoff.
An onset error counts only outside
the greater of **150 ms** and **one sixteenth note at the current local tempo**.
Allow the original matching window before the first attack, including at a
measure boundary. Within a timed measure, grade ordinary attacks until the
last authored attack for the selected hand has passed its matching window.
New attacks after that window and before the next measure's early matching
window are ungraded warm-up, even during held notes or trailing rests.
Internal gaps before the final attack remain graded. Releases continue to
the recorder, including during a trailing rest, so hold grading is unchanged.
This is an owner-selected tolerance, not a validated universal teaching constant.
Detailed timing/hold observations remain distinct in local evidence even though
the display uses two feedback colours. Key-release timing is always recorded. With hold grading off, short, long
and unreleased keys remain green when the attack is correct. When enabled,
release errors affect both feedback and progression.

### Transitions

Show a short message for about **2 seconds** during the automatic transition,
as compact mint text aligned just above the fixed playhead, without a box or
yellow border. Course changes, graded results with accuracy, command notices
and input messages use this same softly fading lane, separate from count-in
and source ink. Its reserved height never changes score geometry:
“Now in tempo — 50%”, “Faster: 72 BPM”, “Slower: 58 BPM”, or a short compliment
after a hand/window completes. Announce a simplified aid before it starts.
Messages overlay the single count-in/handoff; they do not add another pause.
The backend selects the transition deadline; message animation cannot create
another progression clock or independently delay an already authorized take.
Automatic handoffs preserve the musical world through ungraded rests while
preparing the next score. The outgoing renderer retains the staff/playhead
until the incoming engraving is published. Explicit Stop resets the run;
Pause and Free target holds retain their existing semantics.

## Acceptance

Implementation and automated checks do not by themselves accept the piano
experience. The owner checks MIDI response, sound, score motion, count-in,
feedback, aid return and saved reopen on the instrument. The exact software
revision and remaining physical/clean-machine gates belong in
[ROADMAP](../ROADMAP.md), with the [verification protocol](development.md#verification-and-acceptance).

### Warm-up between takes

Ordinary attacks in inter-take rests, early count-in outside the matching
window, and the silent tail after a measure's final attack window produce
only a brief neutral fading pitch. They do not affect assessment or trigger
messages. Explicit transport gestures and physical held-key display remain
available. Internal authored rests before the last attack remain graded.

The playhead-aligned notification lane uses semantic outcome cues: bold mint success, champagne mastery, muted peach retry, teal tempo and blue-green Listen. Headline and smaller continuation text share one fixed lane; success and milestones scale in gently. Presentation never delays the musical timeline.

## Sight reading

The gear menu's Sight reading page offers five levels and a fixed named tempo. Each Start creates a fresh 16-bar score, with a normal count-in, scrolling notation, physical MIDI grading and live accuracy. It skips Listen, Free and the lesson tempo ladder. The completed round stops and reports its accuracy; return to Sight reading in the gear menu to generate another. Rounds do not enter the music library.

Levels: single diatonic quarter/eighth notes; add sixteenths; half-note major/minor/diminished/augmented triads in all inversions; add seventh chords in all inversions; half-note tonal major/minor chord progressions mixing triads and sevenths with randomized nearby inversions. Single-note pitch distances follow a discrete truncated Gaussian (5-semitone standard deviation); chord voicings favor small motion without prohibiting leaps. Range A1–E6 (six diatonic steps beyond the outer staff lines). Tempo presets range from Largo 40 to Presto 184 BPM. No adaptive tempo or lesson mastery is awarded for this mode.

A timed graded take below `ignored_accuracy_below_percent` (default 5%) is unscored: preserve BPM, mastery streak, failure counters, stage and earlier learning decision. Automatic practice repeats at the same tempo, including sight-reading rounds; manual Stop remains authoritative. Remove the open attempt and its checkpoint/event evidence from the learning ledger; retain aggregate elapsed session time. Do not publish a final accuracy or failed review for that take. Exactly 5% is a normal graded failure.

Fingering corrections change only the original-note annotation projection. They do not publish a new musical score revision or invalidate admitted geometry or transport. The current display window receives a versioned annotation overlay (including automatic recalculations and removals); the renderer clears only its fingering placement cache. Later score bundles independently project the latest fingering plan.

Fingering inference permits a single thumb (finger 1) to depress two distinct neighbouring keys of the same hand at the same onset, provided both are white keys or adjacent black keys separated by two semitones. The chord search counts the pair as one finger, preserves pitch order and all overlapping fixed assignments, and does not allow sharing a thumb across staggered attacks, three keys, or other fingers. Manual and authored choices remain fixed; incompatible choices are marked for review. The upstream model weights and logits are unchanged except for the existing feasibility mask. MIDI grading still uses distinct physical pitches.
