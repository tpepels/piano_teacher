# P4 — Learning HUD and pause navigation

The practice screen now foregrounds the musical task and clean-run goal.
Current/target tempo, hand, piano connection and mode remain visible. Numeric
curriculum counts live in the lesson path. Short instructions explain why a
variant is being learned. Error rings leave engraved noteheads intact and use
symbols alongside color; success has a check mark and assisted work a question
mark. A real pixel test verifies central notehead ink survives every status.

Pause opens a dark, keyboard-accessible sheet with Resume, Retry, Listen,
slower/faster tempo, hand selection, source-bar practice and Exit. Resume
preserves the same target/clock; explicit changes begin a new preparation or
attempt. Source-bar selection validates the original measure grid before
changing anything. Later-bar Practice cannot count as a full clean run.
Listen disables seeking. Tab/Shift-Tab and arrow navigation stay in the sheet;
the measure field retains ordinary text editing.

Actual desktop journey: **18 rendered frames**, exact 1536×960, 1024×768,
800×600 and fullscreen 3840×2400. All nine pause choices fit. Hinted Learn
retained score heights 421/229/206 px and detected notehead ink 258/109/111 px.
The journey exercises Resume, fresh Retry, 72/79 BPM controls, left hand,
measure 2 / local beat 4, actual Listen/retry and Exit using normal UI/HTTP.
Artifacts: `/tmp/piano-teaching-p4/`; final log
`/tmp/piano-teaching-p4-final.log`.

Independent review and real captures found paused-Listen null-range handling
and focus escaping to underlying controls. Regression tests reproduce both,
including a native editor's arrow behavior at the caret boundary. Backend
tests cover strict source-bar validation, mixed meter, stale score responses,
held guided keys and cancellation of uncommitted third-pass credit on seek.

Physical piano, speaker latency and pedal acceptance remain open. Saved
musical preparation, trouble revisits and optional placement are P5 work.

Verification gate: the full P0–P4 run passed **396 checks** and exposed two
obsolete test expectations (the removed numeric heading and controls replaced
by the modal). After updating those expectations, **29 focused checks passed**
and the affected **28-frame, 66-second recovery journey passed** with real
sheet Resume. Parser, independent review and whitespace checks pass. Final
P5 verification will run the complete suite again.
