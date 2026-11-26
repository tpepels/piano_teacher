<div align="center">

<img src=".github/assets/piano-teacher.svg" alt="Piano Teacher — Practice your music, one measure at a time." width="960">

An offline desktop companion for learning piano from your own MIDI or MusicXML files.

[Practice flow](docs/practice-flow.md) · [Build and run](docs/development.md) · [Project roadmap](ROADMAP.md)

</div>

## From listening to playing

Work on a small passage, hear how it sounds, find its notes at your own pace,
then bring it up to the original tempo. Piano Teacher guides each window through
**Listen → Free → Tempo**, with the right hand, left hand and both together.

- **Your music.** Open a `.mid` or `.midi` file. The lessons keep the original
  notes and complete held endings; simplified exercises are announced.
- **A manageable next step.** Introduce one measure, then connect it with up to
  three preceding measures. Each window keeps its own progress.
- **Room to learn.** Start timed practice at half speed. Clean attempts increase
  the tempo; repeated trouble returns to slower work and Free practice.
- **Music in focus.** A scrolling score, available finger numbers, green/red
  note feedback, count-in and metronome keep the next action clear.
- **Pick up where you left off.** Reopening returns to the saved window with
  a Free warm-up before timed practice.

Two clean attempts at the original tempo finish the current hand step. After
all moving windows, the final test brings the whole original piece together.

## Start a session

1. Launch Piano Teacher and connect your MIDI piano in Settings.
2. Open a MIDI file from your music.
3. Listen to the first measure, then play its notes when Free begins.

The flow advances automatically. **Pause/Resume** and **Listen again** stay on
screen, and the metronome can be switched on or off. **Grade how long I hold notes**
is available in Settings and is off by default. Correct pitches and note attacks
determine clean passes; actual key releases are still recorded. Turn it on to
include release duration in grading. Keyboard and configured
piano shortcuts remain available. The keyboard hint appears after a wrong note
in Free.

For timed sight-reading drills, open **Settings → Sight reading** and choose one of
five levels and a named tempo. Every start creates a fresh 16-bar round,
from single notes to inverted triads, seventh chords and tonal progressions.
The regular moving score and live accuracy apply at the chosen fixed tempo.

The current build targets Linux. Follow [development setup](docs/development.md#build-and-run)
to run from source; [packaging instructions](docs/development.md#standalone-linux-package)
describe the assembled standalone application. Release readiness and remaining
physical piano checks are recorded in [ROADMAP](ROADMAP.md).

## Local by design

Practice, automatic fingering and saved progress work offline after setup.
There is no account or background upload. Learning history stays locally with
your progress; Settings provides retention, JSON export and confirmed deletion.
Manual fingering corrections follow their original notes across exercises.

See [fingering and privacy](docs/reference.md) for model provenance, data limits
and exactly what export or deletion includes. Piano Teacher does not claim that
software tests establish teaching efficacy or physical MIDI/audio acceptance.

## Inside the project

The application uses Godot 4.7, embedded CPython and authentic Verovio notation
in one desktop process. The technical details live in four documents:

| Document | Read it for |
| --- | --- |
| [Practice flow](docs/practice-flow.md) | The learner-visible behaviour contract |
| [Architecture](docs/architecture.md) | Current owners, immutable score and timing contracts |
| [Development](docs/development.md) | Setup, checks, packaging and physical acceptance |
| [Reference](docs/reference.md) | Fingering, local evidence, privacy and research limits |

[ROADMAP](ROADMAP.md) remains the product and phase record. Superseded designs
and implementation history are available through Git.
