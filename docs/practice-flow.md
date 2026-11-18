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

Opening a piece goes straight to the first phrase (state 2), which starts
with its own Listen step. The whole piece is **not** played back first
(owner, 2026-11-18: too long for long pieces).

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
| Open | Phrase 1 starts with Listen | No playback; first exercise starts |
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
| Free display | Target waits on the playhead | Fixed in 7289fa80; previously an empty staff |
| Feedback colours | Green/red, plus a ghost note for a wrong key | Five status colours (hit, missed, late, early release, early onset) |
| Timing errors | Only clearly off counts | Timing deviations can fail an attempt |
| Count-in | Clicks and large numbers | Spoken count-in voice |
| Keyboard | Only as a hint after a wrong note in Free | Shown in guided mode and on hints |
| Quick-note spacing | At least ~3.3 staff spaces per 16th | 52 px per quick attack (about 2.4 spaces) |

## On screen

### Always

- **Staff:** scrolls from right to left past a fixed playhead, in every
  state including Listen and Tempo.
- **Phrase context:** the current phrase is shown with the bar before and
  the bar after it dimmed, for context.
- **Hands:** the hand that is not being practised stays visible but dimmed.
- **Fingering:** numbers are shown wherever they are available.
- **Spacing:** quick notes (16ths, 8ths) are spaced generously, at least
  about 3.3 staff spaces per 16th (owner: they were too close together).
- **Status:** minimal. A small label says where you are; the music is the
  focus.
- **Keyboard:** no piano keyboard, except as a hint after a wrong note in
  Free.
- **Controls:** Pause and Listen again. Everything else advances by itself.

### Listen

The notes scroll past the playhead and light up as they sound. Nothing is
graded.

### Free

- The target note waits on the playhead.
- After each correct note the staff moves on to the next one; the axis
  never moves while the learner thinks.
- A played note turns green.
- On a wrong note: the intended note turns red, the keyboard appears and
  shows the key to play, and the app waits for that note.

### Tempo

**Count-in**
- One bar of metronome clicks with large numbers 1-2-3-4.
- It ends just before the first note; a leading rest is not sat out.

**Metronome**
- Can be switched on the screen; on by default.

**Feedback while playing**
- Every note is coloured the moment it is played or missed.
- Two colours only: **green** for correct, **red** for wrong or missed.
- A wrong key also shows a red "ghost" note at the pitch that was played.

**Timing**
- A note that is a little early or late is accepted (still green).
- Only a note that is clearly off counts as an error.
- Proposed threshold, to confirm when building: more than a sixteenth note
  at the current tempo, and at least 150 ms.

**Next attempt**
- It follows directly: the staff keeps scrolling and the repeat comes in
  from the right after one count-in bar. It never jumps back.

### Transitions

- **Step change** (Listen -> Free -> Tempo): a short message for 1-2 s
  ("Now in tempo - 50%"), then the next step starts by itself.
- **Tempo change:** a short message ("Faster: 72 BPM", "Slower: 58 BPM").
- **Hand, phrase or link done:** a short compliment, then the next one
  starts automatically.
- **Simplified exercise:** starts automatically when a phrase keeps
  failing, with a clear message of what was simplified.
