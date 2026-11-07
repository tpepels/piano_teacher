# P2 — Instructional Practice and guided recovery

Practice still finishes the current two-bar chunk before reacting to five
distinct wrong or missed notes. A 1.5-second feedback break names the retry
bars and 10% slower tempo. A second failed take of the same chunk offers
source-derived, note-by-note help, then returns to that chunk with a fresh
count-in. A clean partial retry leads to the whole passage; it earns no credit.

Full clean takes restore the selected tempo before the three required clean
target-speed passes. Each break explains the next action. Pause, Resume and
Stop work during feedback, recovery and score loading, including deferred
geometry acknowledgements. Paused feedback retains its score position.

Fresh full-suite verification: **321 passed in 105.86 seconds**. Godot parser
and `git diff --check` pass.

Verification includes real callback timing at 30/40/80/120 BPM with mixed
meters and ±30 ms jitter. An actual desktop journey imports a temporary MIDI
through the normal UI, reveals a wrong-note hint, fails bars 3–4 twice,
pauses/resumes feedback, learns those exact bars, returns to rhythm, completes
a partial retry, restores 194 → 213 → 234 → 240 BPM, then earns three complete
240 BPM passes before advancement. It used 258 timestamped MIDI events,
28 rendered frames and 65.8 seconds. During mistakes the same note moved
898.75 → 842.75 px while the timing line drifted less than 0.001 px.

The journey rejects the committed P1 baseline before testing the new behavior.
Independent review found two loading/resume edge cases; both have regression
coverage. A separate score test was verified red without the Stop reset.

Artifacts: `/tmp/piano-teaching-p2/live/` (PNGs, MIDI journal and phase log),
`/tmp/piano-teaching-p2/before-p2.log` (baseline rejection).

Physical USB/audio/pedal acceptance remains pending. Audible Listen and
uninterrupted Perform belong to P3; broader pause/HUD polish and saved
progression follow in P4/P5. No catalogue was added.
