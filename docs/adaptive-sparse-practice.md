## Adaptive practice passage length

Imported music normally uses two source measures per learning passage. If a
two-measure block has fewer than `focus_min_onsets` **distinct attack times**,
the learning path adds more complete source measures, up to
`focus_max_measures`. Notes played as a chord at the same instant count as
one rhythmic event. Length expansion uses the union of attacks across both
hands; the upper attack budget always wins over further expansion.
Once passage boundaries are chosen, solo-hand stages require at least
`focus_min_onsets` attacks **in that hand** when both hands participate.
A sparse solo hand is omitted, with its original notes retained in the
mandatory both-hands stage. Thus one sparse RH attack plus five LH attacks
means LH → Both; the mirror case means RH → Both. If neither hand reaches
the minimum but the combined passage does, teach Both alone. If only one
hand has any notes, preserve its solo stage even at the measure limit.
The simplified skeleton/outline stages are also skipped if they would contain
fewer attacks than the threshold while the original stage contains enough.
Dense passages retain their original two-measure focus.

The defaults in `piano_teacher/lesson_settings.json` are:

- `focus_measures: 2` - minimum focus length and expansion increment.
- `focus_min_onsets: 2` - expand a passage with only one note/chord onset.
- `focus_max_measures: 8` - maximum focus length, including silent measures.

Connection exercises continue to practice at most the final two measures
before a boundary and first two after it, rather than entire extended passages.
The final complete performance, saved-source progress recovery, independent
two-measure error windows, tempo ladder, and manual ±5 BPM controls remain in
place. Change the JSON settings and restart the backend to adjust these targets.

### Upper attack budget and single-measure simplification

`focus_max_attacks: 8` limits the number of distinct rhythmic onset times in
ordinary learning passages, including simultaneous attacks across both hands.
The lesson planner shortens a too-dense passage at a **whole source-measure
boundary**, even to a single measure, without moving any notes. The previous
`focus_min_onsets` and `focus_max_measures` still apply; expansion never
exceeds the attack budget. Too-dense connections are omitted, rather than
silently becoming overlarge exercises.

If one source measure already exceeds the limit, it stays one measure. Its
learning steps use the existing *skeleton → outline → original* progression.
Early stages select nested subsets of the original attack times, preserving
all notes in each selected chord and the original durations and pitches.
The **original** stage remains deliberately unlimited and contains every
source note, as does the final whole-piece performance. Otherwise a literal
maximum would make it impossible to learn the original music. No scoring
credit transfers between the simplified and full stages. The active tempo
ladder and manual ±5 BPM controls are unchanged.

The maximum is for learning material, not a promise that every single
original measure or the final performance can fit within the cap. Legacy
session migration can reconstruct the historical non-adaptive grouping.
