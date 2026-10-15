# P3 — Audible Listen and uninterrupted Perform

Listen synthesizes the exact active variant at the selected BPM into local
PCM16 WAV audio. Pitches, simultaneous chord voices, source rests, durations
and held endings come from the same notes used for engraving and assessment.
Godot downloads and decodes the WAV and starts an AudioStreamPlayer only after
the current score/audio acknowledgements. Pause freezes sound and musical
time; changing mode or Stop invalidates the session. Listen never records or
grades input and cannot earn Practice credit.

Audio synthesis streams bounded waveform chunks in a background worker.
Long rendering does not hold the MIDI/transport lock; obsolete workers cannot
replace a new lesson. Cached files are content/BPM keyed. Independent review
found a duplicate-ready replay edge case; regression coverage verifies that
finished or stopped examples cannot be restarted by an old acknowledgement.

Perform uses the existing count-in, clock and assessment, continues through
mistakes and finishes with accuracy, timing, missed pitches, extras and ranked
weak source sections. The weakest-section action starts real rhythm practice.
Later-starting partial work earns no mastery. Perform itself is a review mode;
the three required full target-speed Practice passes remain authoritative.
Whole-piece Perform selects the existing original all-note final exercise.

Real desktop acceptance: 20 rendered frames across normal and compact journeys
under `/tmp/piano-teaching-p3/{final,compact}/`. A four-second example contains
110,235 nonzero samples at 44.1 kHz; opening/internal rests are silent and its
held ending contains sound. The actual AudioStreamPlayer advances. MIDI during
Listen creates no recorder or credit. An all-missed Perform crosses the first
six-error boundary uninterrupted, grades all 13 required notes at the endpoint
and starts the weakest bars 3–4 through the visible control. The committed P2
baseline fails the missing Listen contract.

At the actual 800×526 compact canvas the score retains 140 px height, the
review and weak-section button fit, and the primary/Stop row ends at y=516.
Navigation text widths are checked, following a real screenshot finding and fix.

Focused audio tests independently check spectral peaks, attack/release/rest
timing, selected BPM, source identity, cache invalidation and output chunk
bounds. A 237-bar/30-BPM render produces 30,336,000 bytes with less than 1 MB
of traced synthesis-buffer memory.

Limitations: the local harmonic synthesizer is a simple piano-like tone, not a
sampled acoustic instrument. Godot decodes the complete WAV in memory, although
backend generation/HTTP transfer stream chunks. The disk cache has no eviction
policy yet. Physical speaker audibility, audio/MIDI latency, USB piano and pedal
acceptance remain unverified. No song or exercise catalogue was introduced.

Fresh root verification: **378 passed in 124.25 seconds**, running the full
P0–P3 suite (`pytest -q --ignore=tests/test_learner_state.py`; that isolated
P5 module is prepared separately). Godot parser and whitespace checks pass.
