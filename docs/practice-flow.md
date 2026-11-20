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

Opening a new MIDI file starts the first measure window with its own Listen
step. It does not first play the whole piece. The original MIDI supplies target
tempo, authored measure boundaries, notes, hands and complete releases.

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
- A correct note turns green; the staff moves to the next target.
- A wrong note turns the intended note red, shows the keyboard hint and waits
  for the correct key. No keyboard appears simply because the learner waits.
- After every target has been found, Tempo begins automatically.

### Tempo

Start at **50% of the original target tempo**, rounded to a positive whole BPM.
Each attempt has one authored
bar of count-in ending immediately before the first note. Skip a leading rest
or pickup inside the selected window, including a short rest within its first
bar; do not make the learner sit through it.

| Attempt result | Next action |
| --- | --- |
| Clean below target | Increase by 10% of target, capped at target |
| One failed attempt | Repeat at the same tempo |
| Two failures in a row above 50% | Decrease by 10% of target, never below 50% |
| Two failures in a row at 50% | Return to Free |
| Two consecutive clean attempts at target | Complete this window/hand and advance |

A slower success is practice, not target-tempo mastery. A failed attempt breaks
the target clean streak. A clean flow attempt has all required pitches and
accepted onsets with no extra keys; key-release precision does not fail it.
After an attempt, the next follows directly with one
count-in bar and no added feedback break. The staff keeps moving forward; the
repeat comes from the right and never jumps back.

The one-bar repeat takes priority over decorative context: neighbour bars may
be limited during the repeat rather than delaying it or overlapping active ink.

## Grow the window and finish

After both hands complete a window, continue the trailing-window sequence.
There is no separate phrase-link generator that silently selects longer or
different music. The next new measure starts alone again.

After the last moving window, play the **whole original piece with both hands**
as the final test. Apply Tempo rules from 50% to original tempo, finishing after
two consecutive clean attempts at target. Then the piece is learned. The final
test is separate from the four-bar routine window limit.

## Resume

Reopening saved progress returns to the same window and hand at **Free** for
warm-up, rather than immediately running at saved tempo. This also applies to
saved final-test progress: reopen at whole-piece Free, then restart Tempo at
50%. A partial chord or held physical key is not saved as completed learning.

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
- Show the bar before and bar after the active phrase dimmed for context, when
  that does not obstruct the immediate one-bar repeat.
- Keep the hand not being practised visible but dimmed.
- Show finger numbers wherever known. Never invent an unavailable assignment.
- Space fast notes generously: about **3.3 staff spaces per sixteenth** at least.
- Use one small status label indicating the current window, hand and step.
- Hide the piano keyboard except for a wrong-note hint in Free.
- Keep **Pause/Resume** and **Listen again** as the practice controls. Everything
  else progresses automatically. This controls the visible normal flow;
  configured physical MIDI shortcuts and existing keyboard/API tools remain.

### Count-in and metronome

Use one bar of metronome clicks with large beat numbers, appropriate to the
authored meter. Count-in ends just before the first playable note. The metronome
is on by default and can be switched on screen. Clicks, spoken cues, note motion
and MIDI grading follow the same authorized musical deadline.

### Feedback

Colour every played or missed note promptly: **green** for correct and **red**
for wrong or missed. A wrong key also produces a red ghost at the played pitch.
Listen lighting is ungraded and cannot award performance credit.

A slightly early/late attack remains green. An onset error counts only outside
the greater of **150 ms** and **one sixteenth note at the current local tempo**.
This is an owner-selected tolerance, not a validated universal teaching constant.
Detailed timing/hold observations remain distinct in local evidence even though
the display uses two feedback colours. Key-release timing is recorded without
adding another failure rule or feedback colour to normal Practice Flow.

### Transitions

Show a short message for **1–2 seconds** during the automatic transition:
“Now in tempo — 50%”, “Faster: 72 BPM”, “Slower: 58 BPM”, or a short compliment
after a hand/window completes. Announce a simplified aid before it starts.
Messages overlay the single count-in/handoff; they do not add another pause.
The backend selects the transition deadline; message animation cannot create
another progression clock or independently delay an already authorized take.

## Acceptance

Implementation and automated checks do not by themselves accept the piano
experience. The owner checks MIDI response, sound, score motion, count-in,
feedback, aid return and saved reopen on the instrument. The exact software
revision and remaining physical/clean-machine gates belong in
[ROADMAP](../ROADMAP.md), with the [verification protocol](development.md#verification-and-acceptance).
