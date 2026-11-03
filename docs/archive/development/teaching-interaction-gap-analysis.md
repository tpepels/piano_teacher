# Simply Piano interaction and pedagogy - gap analysis

Research date: 2026-10-15. Scope: interaction, interface and method of learning music. **Not** the catalogue, licensed songs, subscription, courses containing fixed prerecorded materials, or exact proprietary visuals.

Repository compared: `tpepels/piano_teacher` at `66faf823bf50fc9b7d8e522e0d682481ee761203` (2026-10-15). The repository may advance; reconfirm `main` before editing.

## Evidence classification

- **Official**: Simply Piano's 2026 help center documents the actual product behaviours. Some features are iOS-only or appear in a particular Songs/PLAY workflow, not necessarily every lesson and platform.
- **Historical/secondary**: 2024-era independent reviews and a 2024 university dissertation help reconstruct the sequence of exercises; product features may have changed.
- **Piano Teacher**: Current code (`godot/main.gd`, `piano_teacher/server.py`, `piano_teacher/learning.py`, `piano_teacher/practice.py`, `piano_teacher/live_feedback.py`, `piano_teacher/recovery.py`) and the repository's `docs/verification-2026-10-15.md`; a user previously observed non-moving/incorrectly cropped score on their machine. Automated desktop verification has since been committed, but physical piano acceptance remains open.
- **Proposed**: Recommended design decisions for our app. These are not claims about Simply Piano's undisclosed implementation.

## What Simply Piano actually does

1. **Bite-sized acquisition before a moving performance.** Official PLAY documentation calls the guided path **Teach Me** and describes a series of exercises culminating in a full-song moving stage. Independent walkthroughs describe first hearing a phrase, playing short sections, then combining them with moving notation. Sources: [Understanding PLAY](https://piano-help.hellosimply.com/en/articles/7943680-understanding-play), [Piano Dreamers review](https://www.pianodreamers.com/simply-piano-review/).
2. **Two kinds of playing interaction.** Moving stages follow a time-governed staff and vertical cursor, while an optional **Practice mode** can wait for a correct note, with hints, before continuing. The Song Library's manual wait mode is confirmed by official docs; the extent to which course lessons automatically invoke that mode can vary. Sources: [Understanding PLAY](https://piano-help.hellosimply.com/en/articles/7943680-understanding-play), [Song Library menu/navigation](https://piano-help.hellosimply.com/en/articles/16945914-simply-piano-song-library-menu-navigation).
3. **Feedback is immediate and localized to each musical note.** Official meanings: blue = correct without hint; yellow = correct after a keyboard hint; red = wrong in moving stages. When the learner struggles, a keyboard at the bottom appears with heard notes in grey and the correct key highlighted in yellow. Source: [Learning with Simply Piano: The basics](https://piano-help.hellosimply.com/en/articles/7943490-learning-with-simply-piano-the-basics).
4. **Automatic assistance after repeated errors.** The maker's archived FAQ explicitly describes automatic slow practice with a metronome after repeated mistakes, returning to original tempo after mastery. Contemporary reviews describe rewind/repeat of short sections. The exact current algorithm and thresholds for every app version are not public and should not be copied as facts. Sources: [JoyTunes FAQ](https://partners.hellosimply.com/faq), [MusicRadar review](https://www.musicradar.com/reviews/simply-piano-review), [academic account of the interaction](https://eprints.lancs.ac.uk/226859/3/2024gottlerphd.pdf).
5. **Controls stay near the moment of practice.** Official Song Library controls include pause, resume, restart, tempo, hands (RH/LH/both), wait-for-note practice, metronome and finger-number toggle; some support Listen and interactive rewind, subject to platform. Source: [Song Library menu/navigation](https://piano-help.hellosimply.com/en/articles/16945914-simply-piano-song-library-menu-navigation).
6. **Listen and play have different purposes.** Official PLAY offers Listen (hear a whole piece or section), Teach Me (guided exercises), Play (moving interactive stage) and sheet auto-scroll. Those should be distinct UI experiences rather than interchangeable buttons. Source: [Understanding PLAY](https://piano-help.hellosimply.com/en/articles/7943680-understanding-play).
7. **Progression has visible, contextual success.** A section's progress or successful notes are visible while playing; separate star exercises award up to three stars and show a per-level progress fraction. This is motivation/context, not a mandate to copy their stars. Sources: [Star Levels](https://piano-help.hellosimply.com/en/articles/7943591-understanding-star-levels), [Piano Dreamers review](https://www.pianodreamers.com/simply-piano-review/).

## Gap matrix (interaction/UI/training only)

| Interaction | Simply Piano evidence | Piano Teacher at inspected HEAD | Gap & suggested action | Priority |
|---|---|---|---|---|
| Visible musical time | Moving staff and vertical cursor in timed stages | Backend musical clock, Godot timing line and scrolling score; desktop-frame tests report correct movement, but user once observed frozen/cropped score | Preserve stable architecture; verify normal launch on target hardware with visible real notes and a bounded short lead-in. Never call this accepted without user test | P0 acceptance |
| Guided note acquisition | Wait for correct note; contextual hint keyboard | Primarily time-governed score; no independent wait-for-note teaching controller | Build discrete guided mode that waits for each target note/chord before advancing | **P0 build** |
| Visual keyboard hints | Appears on mistakes/stalls; expected/heard notes highlighted | On-score markers, text feedback, no dedicated teaching keyboard | Show compact contextual keyboard only when needed; distinguish expected vs pressed | **P0 build** |
| Immediate note feedback | Blue/yellow/red semantics localized to note | Assessment and live feedback exist; UI treatment mostly marks/labels | Smooth immediate expected-note states: pending, correct, assisted, wrong, missed, held. Preserve information without forcing bright colors | P1 |
| Listen to sample | Audible whole phrase or segment | No complete playable demonstration/synthesis documented | Add a true sound preview of the *active generated* notes, at selected BPM, without advancing mastery | **P1** |
| Timed practice | Moving score independent of error; metronome optionally | Existing backend `clock_beat`, current tempo, image/geometry transport | Introduce **Practice** as an explicit mode, distinct from guided and uninterrupted Perform | P1 |
| Automatic remedial practice | Slowdown/metronome/wait-after-error in certain flows | Five-error two-bar-boundary recovery, 10% slowdown, target-BPM recovery | After threshold, present a short explanation, temporarily enable Learn-mode focused section, then return to timed Practice | P1 |
| Repetition and passing | Repeat trouble spots, then return to fuller play | 3 clean target-tempo full takes; partial recovery doesn't confer mastery | Show 1/3, 2/3, 3/3 with short rest; distinguish helped completion vs clean, avoid spamming repetitions | P1 |
| Hand selection | RH/LH/both practice controls | Hand sequencing exists | Quick, clearly marked practice hand selection; keep non-played hand visually secondary, not invisible if musical context useful | P2 |
| Tempo controls | Manual speed in moving stages | Adjustable target/current tempo exists | Make current vs target obvious, restore speed after success, preserve setting between modes | P2 |
| Pause/restart/rewind | Compact pause menu; seek in Songs but not Courses | Start/stop/pause/restart; navigation; timed-recovery rewind | Small pause sheet with restart current phrase, hear phrase, change hands/tempo, retry; allow manual seek to bar while paused | P2 |
| Exercise course design | Short fragments → combination → complete performance | Generated skeleton/outline/original; consolidated from 1,209 to 301 steps for test song; basic density-based sections | Use diagnostic steps, demonstrate-audition-play transitions, mastered-skill skipping and higher-level progress groups; retain user's 3-clean standard where required | P2 |
| Modal clarity | Different screen feedback for listening, teaching and performance | Single main practice area with status labels; dark theme has been implemented | Three unmistakable interaction modes with consistent visual hierarchy | **P0/P1** |
| Dark low-glare design | Not a mandatory Simply Piano attribute | Moodboard-inspired dark UI is already present under `godot/practice_theme.gd` | Polish, not restart. Avoid pure-white notation/background and neon-overpowering line | P2 |
| Hardware trust | Live note detection is central | MIDI reconnect and no-input preview logic exist; real instrument unverified | Input status and live-key test in settings; clarify that no-input preview cannot assess mastery | P0 acceptance |

## Crucial distinction: this is NOT a cloning specification

The useful pattern is **introduce → demonstrate → wait-and-help → tempo practice → focused recovery → fluent performance → progress**. Simply Piano has different behaviours depending on feature, platform, release and lesson. The following are user-defined Piano Teacher policies, **not verified Simply Piano thresholds**:

- Five distinct wrong/missed required notes during a two-measure window before recovery.
- Wait until the relevant two-measure boundary rather than stopping the timed performance mid-note.
- 10% slowdown, returning in steps to the student's chosen target BPM.
- Three consecutive clean *full* takes at target tempo to master an exercise.
- A shortened preparation interval capped near four seconds at slow BPM; real notes already begin moving during it.
- Simplified MIDI variants → original note set; arbitrary files, not a supplied catalogue.

### Detailed observable experience to aim for

**Learn**: A very small musical idea appears at a readable scale. The app plays the idea once if asked, then waits for the student to press the required note/chord. Wrong note? Expected note remains visible; contextual keyboard opens; student can try again without losing the exercise. A hinted success is recognized as assisted, not a clean timed take. Musical time does not race away from the user in this mode.

**Practice**: Show a short preview of upcoming notes, a stable timing line and a tempo-limited moving lead-in. The score travels at the target/practice BPM regardless of input. Wrong/late/missed notes receive quiet color/status feedback. At a failed two-bar checkpoint, finish the musical group, give a brief reason and retry from its start, perhaps in Learn mode when struggling badly. After progress, return to target BPM and accrue the requested three clean attempts.

**Perform**: Play the complete phrase or piece with continuous musical time. No automatic rewind or stop for errors; evaluate at a meaningful endpoint. Optionally jump back to the weakest section afterwards. This is a musical experience, not another microtest.

## Sources

Official:
- https://piano-help.hellosimply.com/en/articles/7943680-understanding-play
- https://piano-help.hellosimply.com/en/articles/7943490-learning-with-simply-piano-the-basics
- https://piano-help.hellosimply.com/en/articles/16945914-simply-piano-song-library-menu-navigation
- https://piano-help.hellosimply.com/en/articles/7943591-understanding-star-levels
- https://partners.hellosimply.com/faq (archived/older content, behaviour may have changed)

Independent:
- https://www.musicradar.com/reviews/simply-piano-review
- https://www.pianodreamers.com/simply-piano-review/
- https://eprints.lancs.ac.uk/226859/3/2024gottlerphd.pdf

Project evidence:
- `ROADMAP.md`
- `docs/verification-2026-10-15.md`
- `godot/main.gd`, `godot/practice_theme.gd`
- `piano_teacher/server.py`, `learning.py`, `exercise_generator.py`, `practice.py`, `live_feedback.py`, `recovery.py`
- `scripts/check_visible_playback.py`, `scripts/check_desktop_ui.py`, `scripts/smoke_adaptive_godot.py`
