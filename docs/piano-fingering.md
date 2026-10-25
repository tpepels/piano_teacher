# Piano fingering

Install the CPU runtime once from the checkout (Node.js 20+ and npm required):

```bash
./scripts/setup-fingering.sh
./run.sh
```

The runtime and both pretrained models are installed locally. Opening a piece,
predicting fingers and correcting them never require a network connection.
The setup command verifies the two model hashes and performs real inference
for both hands. Python dependencies remain `pip install -e '.[godot,test]'`.

Open a MIDI/MusicXML file and choose its lesson path. Right-hand numbers appear
above the staff and left-hand numbers below. Right-click a note, or tap its
number, to choose 1–5. “Use original / automatic” removes the manual correction.
Shared keys with multiple source voices have separate source choices. An edit
is permanent and updates every exercise that contains that original note.

Plans and corrections live under
`$XDG_DATA_HOME/piano-teacher/fingering/` (normally
`~/.local/share/piano-teacher/fingering/`). Do not delete `overrides.json` when
clearing derived caches: it contains your corrections. A damaged corrections
file is reported rather than silently reset. A damaged derived plan is rebuilt.

`FingeringProvider` accepts the complete original `Piece` and fixed source-note
assignments. `FingeringPlan` belongs to that Piece; it records canonical source
IDs, hands, fingers or unknowns, original annotation text, manual overrides,
provider/model versions, input digest, configuration and diagnostics. Plans are
written atomically under an interprocess lock. Source/configuration/model changes
get a separate plan; reopening a compatible source reuses the saved result.
Removing an override can reuse the previously saved uncorrected plan.

Lumikey is isolated in `fingering/lumikey.py` and its Node bridge. The bridge uses
the published **@lumikey/piano-fingering-model 0.3.0** inference implementation
and its unmodified pretrained ONNX files, running **ONNX Runtime 1.30.0 CPU**
with one execution thread. See the runtime's
[third-party notices](../piano_teacher/fingering/lumikey_runtime/THIRD_PARTY_NOTICES.md)
for package/model licensing, provenance and exact hashes. The publisher declares
the package, including its model files, MIT; it supplies no separate model
license or copyright text. The Python training/inference source and training
dataset are not copied into this project.

The adapter masks only physically/fixed-constraint-incompatible real model
logits: distinct held keys need distinct fingers, simultaneous chord fingers
follow pitch order, future fixed fingers reserve their overlapping intervals,
and a chosen chord finger must leave enough available fingers for the remaining
tones. Equal-pitch written voices retain separate source identities and may
share one physical key. The highest remaining model score wins. There is no
heuristic fallback. If no score satisfies these constraints, the assignment is
unknown with a reason. Upstream inference still sees its own real prediction
for a rejected candidate as context; that candidate is never displayed or
registered as an available application assignment.

This is constrained sequential model inference, not an exhaustive search over
all possible whole-piece fingerings. It does not measure a player's hand reach,
reinterpret sustain/voice assignments, reassign imported hands or guarantee
concert-editorial fingering. Conflicting authored/manual constraints remain
visible and are reported. Authored substitutions/alternates are preserved as
text. An unambiguous primary finger stays fixed and is flagged for review when
secondary annotations exist; a lone substitution or conflicting primary
annotations need an explicit correction before receiving one displayed number.
Out-of-piano-range notes and unassignable dense overlaps stay unknown. Missing
runtime/weights or failed inference never produce fabricated numbers; saved
manual/authored fingers remain available and the UI reports the problem.

Automatic inference always receives both hands and the full original source,
using source BPM rather than practice BPM. Skeleton, outline, original,
single-hand, combined-hand, teaching, repeated and tempo-adjusted passages only
project by `source_id`. A tied continuation receives no new number. The grading
note set and event timing are unchanged. Authored fingering ink moves from
MusicXML to the native projected plan only when an actual known assignment owns
it; unrelated unsupported technical markings retain their existing fallback.

Focused validation imports the complete repository Hanon, Chopin and Peace
Piece files and checks every exercise/hand/variant subset, durable reloads,
fixed constraints and absence of held-key conflicts. Native framebuffer tests
exercise drawn digits, scrolling, collision avoidance, shared source editing,
ties, corrections and deliberately invalid assignments. Backend tests exercise
the HTTP path, restart/cache reuse, concurrency, tempo, grading and Listen.

Measured on the local Linux CPU runtime (adapter 3):

| Original source | Notes | Assigned | Unknown | Inference |
| --- | ---: | ---: | ---: | ---: |
| Hanon, exercises 1–20 | 18,058 | 18,058 | 0 | 4.11 s |
| Chopin, Nocturne Op. 9 No. 2 | 1,299 | 1,299 | 0 | 0.38 s |
| Bill Evans, Peace Piece | 1,990 | 1,640 | 350 | 0.55 s |

All original identities were covered across 5,695, 312 and 594 exercise/hand/
variant projections respectively. Peace Piece's imported RH track contains six
to ten concurrent distinct keys and very wide voicings. Its unknowns include
whole chord groups that cannot be completed under the held/fixed constraints
and earlier sequential predictions. This integration preserves the imported
hands and durations throughout inference and grading.

The complete application was also exercised with real Chopin and Hanon MIDI:
open Practice, build the full path, edit a visible number through its popup,
save through HTTP, compare the refreshed framebuffer, then restore the original.
Hanon exposes 5,651 actual lesson steps. This uncovered an existing allocation
problem: each label constructed a separate `SystemFont`, and the full path grew
beyond 8 GiB and stalled. Font faces now share resources by weight. The complete
Hanon application test finishes at about 181 MB of Godot-managed static memory.
Frame tests enforce a 512 MiB static-memory budget and a 1,536 MiB RSS watchdog.
Whole-piece actions have a longer HTTP timeout than quick transport controls.

Final local gate: **240 passed in 121.08 seconds**, followed by Godot script
validation. Another focused run passed 51 existing learning, import-cache,
Listen, grading and tempo lifecycle tests. No 24-shard audit was started.
The [Hanon correction](evidence/piano-fingering-2026-10-25/hanon-corrected.png)
and [Chopin prediction](evidence/piano-fingering-2026-10-25/chopin-predicted.png)
screenshots show the real application with model-generated assignments.

Godot MCP was verified against this checkout's `godot/` project, including
script checks, launching a live game, reading its native score/fingering state,
and a runtime screenshot. The MCP server must use `<checkout>/godot` as `cwd`
and `GODOT_MCP_PROJECT_PATH`; using the repository root permits editor commands
but breaks runtime registry lookup. Keep a graphical editor running for
playtests; a headless editor supports script checks but cannot launch a game.

Run the focused regressions and fast CI gate locally:

```bash
LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 xvfb-run -a -s '-screen 0 1600x1000x24' ./scripts/verify-notation.sh --ci
```

This command never starts the 24-shard corpus audit.
