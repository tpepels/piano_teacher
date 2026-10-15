# Practice experience design — 2026-10-15

The supplied handoff is the product brief. Functional score movement is the first
acceptance gate; cosmetic completion cannot precede it. Python remains the sole
musical clock, with Godot extrapolating each HTTP snapshot between polls.

## A. Visible playback

Keep a stable timing rule at 42% of the score viewport. Project actual engraved
noteheads through the same transform as their raster, and move the notation
directly from musical position without camera lag or note-visibility clamps.
Use alpha-aware ink bounds and measured staff lines for cropping and count-in.
Test note pixels, note/line crossings, stable scale, pause/resume, slow tempos,
rests, endings, recovery and system transitions. If the page layout cannot meet
continuity, arrange its engraved systems in a horizontal strip, preload images,
and interpolate through system boundaries in strip coordinates.

## B. Dark application

Forest background, charcoal workspaces, pine controls, stone notation and text,
sage/slate secondary information, restrained teal timing rule. Searchable real
library metadata, dominant practice notation, a readable lesson path and settings
with actual MIDI activity, tempo and metronome. No invented artwork/difficulty,
placeholder controls or extra decorative imagery. The score is the visual anchor.
Use consistent focus/hover states; motion is functional score movement.

## C. Curriculum

Consolidate manageable adjoining passages, retain two-bar difficult work, teach
distinct hands only when useful, and use original notes for integration and final
performance. Preserve source coverage, three-clean mastery and recovery. Migrate
saved positions by stable musical identity; keep legacy mastery without granting
mastery to newly enlarged exercises. Preserve the chosen target tempo.

## D. Integration

Run all existing Python, parser and rendering checks and capture actual rendered
frames with the desktop renderer. Record software evidence separately from
physical USB MIDI and speaker validation, which requires the user's instrument.
Work on a local branch; publishing to shared main remains a separate action.
