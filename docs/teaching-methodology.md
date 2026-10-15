# Teaching method and progression

All learning material comes from the student's imported MIDI or MusicXML. The
same active source variant supplies notation, guided targets, timed assessment
and Listen audio. There is no built-in song catalogue or proprietary course.

## Current course construction

`learning.py` conservatively joins adjacent easy source passages into sections
of at most eight bars. It preserves source notes, stops at gaps and meter
changes, and keeps difficult material in its original short passage. Difficulty
is checked per hand: more than three notes per beat, a chord exceeding four
notes, a substantial sequence of fast separate attacks, or dense irregular
rhythm prevents consolidation. This heuristic organizes practice; it does not
diagnose the student's ability or infer musical phrasing.

Each learning section offers the hands actually present: right, then left,
then both when both exist. Single-hand stages use generated skeleton, outline
and original variants with these existing redundancy rules:

- Identical generated note sets do not create extra stages.
- If either skeleton-to-outline or outline-to-original adds at most 15% of
  the original note count, omit the outline stage.
- Use only the original stage for a simple single-note line: no simultaneous
  attacks, at most one note per beat on average, attacks at least half a beat
  apart, and attacks close to the half-beat grid. The implementation uses
  `abs(start * 2 - round(start * 2)) < .05` for that last condition.
- Both-hand work and connection/performance exercises use the original notes.

Adjacent sections also receive a connection exercise spanning the previous
section's final two bars and the next section's first two bars. The complete
performance retains every original source event, introductory rests and held
endings. These omissions of redundant stages never create mastery records.

Timed Practice alone earns mastery: three consecutive clean full attempts at
the selected target BPM. Slower full attempts restore tempo first. Partial
retries, guided completions, hints, Listen, Perform and disconnected previews
earn no clean-run credit. The selected target survives hand and passage changes.

## Guided course progression

The backend and `learner_state.py` use the following route:

1. Learn successive two-bar ideas from the exact active hand and variant.
   Source measure boundaries determine their length, including changing meter.
   Ideas without note attacks are omitted from guided acquisition; their time
   remains in timed Practice, Listen and Perform.
2. After those ideas are prepared, practice the full active variant in time.
   Assisted preparation advances learning only. Repeated timed trouble can
   revisit the relevant guided idea before returning to rhythm.
3. Keep the existing mastery route through useful variants, available hands,
   subsequent sections and their connections. Offer uninterrupted complete
   original Perform as a review experience, with Practice of weak sections.

Timed recovery preserves the existing transport policy: after five distinct
wrong or missed required notes, finish the two-bar chunk, show a short break,
slow by 10%, then retry from that chunk's start through the stage's end. The
two-bar range identifies the trouble location; it does not shorten the retry's
ending. A clean retry starting partway through the stage earns no mastery and
is followed by the full stage. Repeated trouble can first return to the same
source idea in Learn. Full clean Practice takes restore the selected target
before the three target-speed clean takes begin.

Perform continues through mistakes and finishes with a review and an offer to
practice a weak section. Its accuracy and timing summary, including a clean
result, never adds to the Practice streak or awards mastery.

An optional placement suggestion offers the original-note stage for the
current hand. It does not infer ability or change progress. Explicit skip and
placement decisions carry `skipped` or `placed` status and a stated reason;
they remain distinct from `mastered`. Choosing harder material still leaves
its normal three-clean-at-target requirement in place.

## Saved learner state

The existing session/mastery tables retain course position, target/current
tempo, valid clean streaks and earned mastery. Separate learner tables retain
the current guided unit, prepared units, explicit skip/placement decisions and
trouble ranges with settled error counts and pitches. A piece-wide trouble
query supports revisits across stages. Guided completion does not resolve
timed trouble; resolution requires an explicit call after evidence such as a
clean full attempt.

Resume granularity is one guided idea, not a partially played chord or an
individual key press. State is keyed by the piece fingerprint and exact stage
key, which includes hand, variant and source-event content. Each saved unit
also retains its local beat range and source-note indices. Resume and prepared
unit lookup accept only matching current ranges and source identities; stale
bindings cannot skip changed notes or manufacture completion. Old valid
mastery remains separate from these preparation records.

Manual Learn seeking may select a shifted two-bar range, such as bars 2–3,
outside the course's usual 1–2/3–4 units. That selection is temporary and does
not claim a canonical idea was prepared. After reopening, guided learning
resumes the last saved canonical idea, rather than the shifted manual range.
