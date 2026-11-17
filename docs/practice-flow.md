# Practice flow for one piece (owner specification)

**Status: owner decisions of 2026-11-17, not yet implemented.** This is the
contract the practice state machine must follow. Where the current
application differs, the gap table at the end applies until the flow is
rebuilt. It supersedes the stage order in
[teaching methodology](teaching-methodology.md) for the desktop flow; the
Coda and Fukuda generators themselves stay unchanged and become an
announced aid (see "Simplified exercises").

The guiding rule: every state must be one a pianist recognises from a
lesson. The learner always plays the real notes of the piece unless the
app has said, in words, that an exercise is simplified.

## States and transitions

### 1. Open a piece

- The whole piece is played back once at the target tempo while the notes
  move over the staff, so the learner hears what it should sound like.
- Then the first phrase starts (state 2).

### 2. Learn a phrase

The piece is split into **musical phrases** (usually 2-4 bars), the way a
piano teacher would divide it.

Each phrase is learned with the **right hand**, then the **left hand**, then
**both hands together**. A hand with no notes in the phrase is skipped.
Every hand runs the same three steps:

**2a. Listen.** The phrase is played back once at the target tempo; the
notes move over the staff. No input is graded. Then Free.

**2b. Free (no tempo).** The learner plays the notes in order at any pace.

- On a wrong note the app waits for the correct one and shows which key
  it is.
- When every note has been played in order, Tempo starts.

**2c. Tempo.**

- Starts at **50% of the target tempo**.
- One bar of count-in that ends just before the first note: a rest or
  pickup at the start of the phrase is skipped, not sat out.
- After each attempt the next one follows **directly**, again with one bar
  of count-in; there is no extra pause.
- Clean attempt: **+10%** of the target tempo, capped at the target.
- Attempt with errors: repeat at the same tempo. After **2 failed attempts
  in a row**: **-10%**, never below 50%.
- At 50% and again 2 failed attempts: back to **Free** (2b).
- If the phrase still does not succeed after returning to Free, the app
  may offer a simplified exercise (see below).
- **Done** when the phrase is played **2 times in a row without errors at
  the target tempo**. Then the next hand, or after both hands together,
  linking (state 3).

The target tempo is the **original tempo** of the MIDI file.

### 3. Link phrases

After each new phrase (from the second one on), the previous and the new
phrase are played together: 1+2, then 2+3, 3+4, and so on. Linking runs for
the right hand, the left hand and both hands, each with the full
Listen -> Free -> Tempo steps and the same Tempo rules. Then the next
phrase (state 2).

### 4. Final test

After the last phrase and its link: the whole piece with both hands,
Tempo rules from 50% to the target tempo, done after 2 clean attempts in a
row at the target tempo. Then the piece is learned.

### 5. Resume

Reopening a piece continues at the **same phrase**, starting again at
**Free** as a warm-up (not at the saved tempo).

## Simplified exercises (Coda / Fukuda)

The Coda and Fukuda generators are not part of the normal order. They are
offered only as an aid when a phrase repeatedly fails, also at a slow
tempo, and they are **announced as a simplification** (for example
"Simplified: broken chords played together"). After the aid the learner
returns to the real notes.

## Current application versus this flow (2026-11-17)

| Moment | This flow | Application today |
|---|---|---|
| Open | Whole piece played back | No playback; first exercise starts |
| Division | Musical phrases of 2-4 bars | One bar per exercise (Beethoven Op. 13 II: 136 exercises) |
| Steps per hand | Listen -> Free -> Tempo on the real notes | 3-4 stages: Coda/Fukuda transformations first, then x2/x4 slowdowns, then the original |
| Coda/Fukuda | Announced aid only | Always the first stage, not clearly announced |
| Free step | Fixed step before Tempo | Only after 2 failed attempts or via a button; showed no notes until 7289fa80 |
| Start tempo | 50% of target | Fixed 40 BPM, about 12 steps to target |
| Done | 2 clean in a row at target | 3 clean at target, for every stage |
| Errors | 2 failed -> -10%, floor 50%, then Free | -10% after 5 errors in a window; guided mode after 2 failures |
| Between attempts | Directly, one bar count-in | Feedback pause, then the leading rest, then count-in |
| Leading rest/pickup | Skipped | Sat out in full |
| Linking | 1+2, 2+3, ... per hand and together | 1+2, 3+4, 1-4 (doubling), both hands only |
| Final test | Whole piece, 50% -> target, 2 clean | Whole piece at the end (present) |
| Resume | Same phrase, from Free | Same stage and tempo |

Open: what appears on screen in each state (notation, graphics, timing) is
being specified next and will be added here.
