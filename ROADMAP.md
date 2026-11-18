# Piano Teacher — roadmap

**Updated 2026-11-18 • MIDI input only**

The development record before this date (phase logs, CI and audit history) is
in git history. [Documentation index](docs/README.md) lists the technical
contracts.

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
(`practice-flow`): musical phrases of 2-4 bars; right hand, left hand, both;
per hand Listen -> Free -> Tempo on the real notes; tempo from 50% in steps of
10% of the target; done after two clean takes at the original tempo; links
1+2, 2+3, ...; a final whole-piece test. Adaptive Coda + Fukuda remains
selectable and is meant to become the announced aid for a phrase that keeps
failing.

## Owner decisions

| Date | Decision |
|---|---|
| 2026-11-08 | Count-in is one full bar of the starting measure at any tempo. |
| 2026-11-16 | Notation is drawn the way Verovio itself would render it at the size shown; what matters is correct notation, not identical pixels. |
| 2026-11-17 | The practice flow and on-screen behaviour in docs/practice-flow.md. It takes priority over notation-oracle work. |
| 2026-11-18 | Opening a piece does not play the whole piece first; each phrase starts with its own Listen. |
| 2026-11-18 | Listen playback is normalised to about -1 dBFS; quick notes get more horizontal room. |
| 2026-11-18 | The test suite is a small core (`bash scripts/test.sh`, one GitHub workflow). No pixel, parity, audit or infrastructure tests. A regression test is added only after the owner confirms the behaviour at the piano. |

## Status

| Area | State |
|---|---|
| Foundation: MIDI import, library, native start, one process | Done |
| Practice flow, backend (phrases, hands, links, Listen/Free/Tempo, tempo and error rules, final test, resume) | Built 2026-11-18; owner testing at the piano |
| Practice flow, screen (status line, messages, Pause + Listen again, metronome switch, two colours, count-in numbers) | Built 2026-11-18; owner testing at the piano |
| Notation (native Verovio ink, display-scale glyphs) | Working; judged on screen |
| MIDI calibration | Built; USB/Bluetooth accuracy not measured on hardware |
| Packaging (`scripts/package-inprocess.sh`) | Staged runtime audit exists; clean-machine release not done |

## Open work

1. Owner test of the practice flow at the piano; fix what deviates.
2. Remaining practice-flow items (see docs/practice-flow.md, "Not built
   yet"): the Coda/Fukuda aid, skipping a short pickup rest inside the first
   bar, a red ghost note for a wrong key, notes lighting up during Listen,
   the other hand dimmed instead of hidden, dimmed neighbour bars.
3. Regression tests for the practice-flow behaviour the owner confirms.
4. Physical checks that software cannot certify: MIDI latency over USB and
   Bluetooth, reconnect, audio/visual drift under load.
5. Clean-machine release package.

## Commands

```bash
bash run.sh                 # start the app (rebuilds stale native inputs)
bash scripts/test.sh        # core tests + Godot check
bash scripts/package-inprocess.sh   # standalone package
```
