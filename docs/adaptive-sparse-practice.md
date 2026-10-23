## Adaptive practice passage length

Imported music normally uses two source measures per learning passage. If a
two-measure block has fewer than `focus_min_onsets` **distinct attack times**,
the learning path adds more complete source measures, up to
`focus_max_measures`. Notes played as a chord at the same instant count as
one rhythmic event. Dense passages retain their original two-measure focus.

The defaults in `piano_teacher/lesson_settings.json` are:

- `focus_measures: 2` - minimum focus length and expansion increment.
- `focus_min_onsets: 2` - expand a passage with only one note/chord onset.
- `focus_max_measures: 8` - maximum focus length, including silent measures.

Connection exercises continue to practice at most the final two measures
before a boundary and first two after it, rather than entire extended passages.
The final complete performance, saved-source progress recovery, independent
two-measure error windows, tempo ladder, and manual ±5 BPM controls remain in
place. Change the JSON settings and restart the backend to adjust these targets.
