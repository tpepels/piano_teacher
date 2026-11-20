# Piano Teacher — roadmap

**Updated 2026-11-20 • MIDI input only**

The development record before this date (phase logs, CI and audit history) is
in git history. [Documentation index](docs/README.md) lists the technical
contracts; the [current owner map](docs/architecture/system.md) describes the
application architecture.

## Product

One Godot 4.7 desktop application with an embedded CPython practice engine,
connected by a typed in-memory GDExtension command queue. No network service,
HTTP adapter, Qt UI or compatibility facade. MIDI (.mid/.midi) is the only
user input; generated MusicXML is only used internally for engraving.

The canonical MIDI source IDs, authored durations, the selected lesson stage
and its tempo must agree across native notation, Listen, the visual
transport, MIDI grading, feedback and saved progress.

## How a piece is practised

The learner-facing behaviour is specified by the owner in
[docs/practice-flow.md](docs/practice-flow.md) and is the default course
(`practice-flow`): every newly encountered authored measure first alone,
then with one, two and three preceding measures, as available, in that order
(maximum four authored measures per routine window). For example,
1; 2, 1–2; 3, 2–3, 1–3; 4, 3–4, 2–4, 1–4; 5, 4–5, 3–5, 2–5.
Each distinct window is learned right hand, then left hand, then together
(skipping empty hands), with Listen -> Free -> Tempo on its real notes.
Tempo starts at 50% of the source target and rises by 10% of that target
after clean attempts; the current window is done after two clean takes at
the original tempo. The whole piece is a separate final test. Adaptive
Coda/Fukuda remains selectable and is planned as an explicitly announced
aid for repeatedly failed windows; routine practice never silently
substitutes simplified notes.

## Owner decisions

| Date | Decision |
|---|---|
| 2026-11-08 | Count-in is one full bar of the starting measure at any tempo. |
| 2026-11-16 | Notation is drawn the way Verovio itself would render it at the size shown; what matters is correct notation, not identical pixels. |
| 2026-11-17 | The practice flow and on-screen behaviour in docs/practice-flow.md. It takes priority over notation-oracle work. |
| 2026-11-18 | Opening a piece does not play the whole piece first; each phrase starts with its own Listen. |
| 2026-11-18 | Listen playback is normalised to about -1 dBFS; quick notes get more horizontal room. |
| 2026-11-18 | The test suite is a small core (`bash scripts/test.sh`, one GitHub workflow). No pixel, parity, audit or infrastructure tests. A regression test is added only after the owner confirms the behaviour at the piano. |
| 2026-11-19 | Every new measure is learned alone, then in a trailing moving window of 2, 3, and at most 4 measures. Independent window progress; separate whole-piece final test. |
| 2026-11-19 | Architectural remediation is tracked in [the implementation tracker](docs/architecture/ownership-and-practice-progression-remediation.md); a green core CI does not certify embedded/native physical acceptance. |

## Status

| Area | State |
|---|---|
| Foundation: MIDI import, library, native start, one process | Done |
| Practice flow, backend (authored moving windows, hands, Listen/Free/Tempo, tempo/error rules, separate final test, resume) | Source integrated 2026-11-19; physical piano acceptance open |
| Playback coordination (all timed routes, physical score admission, shared deadline, cancellation/reconciliation) | Source and existing embedded production checks pass at 9654d2a3; physical session acceptance outstanding |
| Practice flow, screen (status line, messages, Pause + Listen again, metronome switch, two colours, count-in numbers) | Built 2026-11-18; owner testing at the piano |
| Notation (native Verovio ink, display-scale glyphs) | Working; judged on screen |
| MIDI calibration | Built; USB/Bluetooth accuracy not measured on hardware |
| Packaging (`scripts/package-inprocess.sh`) | Strict relocated build/clean-HOME boot passes at 9654d2a3; clean-machine desktop acceptance open |
| Phase 5: ownership decomposition | Complete: owner transfers integrated, independent source review cleared, existing core/native checks pass |
| Phase 6: software and product acceptance | Software gates pass at 9654d2a3; phase remains incomplete for physical Kawai/USB/Bluetooth, speakers, latency, real playing and clean-machine acceptance |

The latest cited remote baseline is
[`12f50e66`, run 44736734032](https://github.com/tpepels/piano_teacher/actions/runs/44736734032).
Local software verification at `9654d2a3` passes: 335 Python tests (one
existing optional SF2/libfluidsynth check skipped), all existing Godot checks,
embedded Python/GDExtension registration, real-source Play/Pause/Resume,
Moonlight Retry/Listen/navigation/tempo/reopen, Peace Piece, Chopin, and the
strict relocated standalone package build/boot with an empty environment and
clean HOME. New commits remain local: no push or new remote CI run is claimed.
The [implementation tracker](docs/architecture/ownership-and-practice-progression-remediation.md)
records exact commands, earlier failures/fixes and manual gates.

## Open work

1. Owner verification of the integrated playback coordinator
   ([contract](docs/architecture/playback-coordinator.md)): real
   Listen → Free → Tempo, automatic repeats, Pause/Resume, physical-key
   restart and preloaded handoff. The implementation is integrated; the
   existing core CI cannot certify physical playback.
2. Owner test of the practice flow at the piano; fix what deviates.
3. Remaining practice-flow items (see docs/practice-flow.md, "Not built
   yet"): the Coda/Fukuda aid, skipping a short pickup rest inside the first
   bar, a red ghost note for a wrong key, notes lighting up during Listen,
   the other hand dimmed instead of hidden, dimmed neighbour bars.
4. Regression tests for the practice-flow behaviour the owner confirms.
5. Physical checks that software cannot certify: MIDI latency over USB and
   Bluetooth, reconnect, audio/visual drift under load.
6. Clean-machine release package.

## Commands

```bash
bash run.sh                 # start the app (rebuilds stale native inputs)
bash scripts/test.sh        # core tests + Godot check
bash scripts/package-inprocess.sh   # standalone package
```
