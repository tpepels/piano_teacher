# MIDI transcription rules, version 1

`midi-transcription-rules-v1` checks whether a **whole-file piano transcription**
obeys an explicit display policy. MIDI without an authoritative written score
can satisfy this policy. Passing does not establish an author's spelling,
written voices, hand pairing, beams, rests, or unique attack-to-release pairing.
Missing checks for supported notation remain blocking obligations of the
separate semantic, support, and pixel release gates.

The implementation is `piano_teacher/notation/midi_transcription_rules.py`.
Its only dependencies are Python's standard library. It independently decodes
the original SMF and reads the generated XML; it never calls `load_midi`,
`build_lesson_score`, `build_score_model`, their quantizers, or their validators
to obtain expected facts. Generated/native agreement alone is insufficient.

## Public contract and evidence

`verify_midi_transcription(path, generated_xml, native_model, *, hand='both')`
returns `schema_version=1`, `rule_version`, `passed`, `complete`, `rules`,
`elements`, and `discrepancies`. `RULE_VERSION` and the fixed `REQUIRED_RULES`
tuple are exported. Each rule has a status and counts of its detailed evidence
elements. Elements retain expected and actual facts, original event identities,
and policy evidence. A missing implementation, exception, missing XML, unsupported
input, or empty rule evidence cannot make that rule verified.

Following the existing ledger convention, `passed` means **no mismatches**.
It does not imply completeness. Only `complete=True` with every required rule
verified constitutes rule verification. Model flags such as `passed`,
`transcription_verified`, or embedded proof claims are ignored. Callers must
bind the original, generated, model, and evidence bytes to their hashes and
replay checks from those artifacts when establishing release evidence.

`verify_midi_performance` retains its existing call form and accepts the
optional keyword `generated_xml`. The one mandatory semantic ledger row has
construct `midi_transcription_rules`, source ID `midi:transcription-rules`,
and boundary `original->written`. Its evidence is
`{rule_version: RULE_VERSION, rule_report: report}`. It verifies only when the
independent report is both complete and passed. Missing generated XML leaves
the row unverified. Original authorial-limitation rows retain their statuses.

The audit script packages the complete rule report and hashes its artifact.
It records observed `import_warnings` in the native audit model. Warnings are
inputs to compare, never proof assertions.

## Required checks

| Rule ID | Independently checked obligation |
| --- | --- |
| `source_decode` | SMF type 0/1, positive PPQ, complete track chunks, raw event ordinals, running status, valid note payloads, end-of-track accounting, at least one positive-duration piano attack, and no unterminated attacks. |
| `physical_performance` | Exactly one native note per retained raw attack; unchanged original pitch, onset, physical key-release duration, attack velocity, track, channel, and stable track/channel owner. No invented or duplicate attacks. Native numbers compare at the existing eight-decimal serialization precision. |
| `hand_policy` | Named track hands take priority (`left`, `lh`, `mano sinistra`; `right`, `rh`, `mano destra`, case-insensitive word boundaries, left checked first). With exactly two retained pitched tracks, rank their pitch medians, breaking ties by original track index, and fill unnamed assignments left then right. Otherwise unnamed pitches below 60 are left and pitches 60 or above are right. These are deterministic application hands, not authorial hands. |
| `warning_dispositions` | Releases pair FIFO independently within each original track/channel/pitch queue. Each overlapping attack requires the explicit ambiguity/FIFO warning with track/channel/pitch, source attack ID, and tick. Paired zero-duration attacks are skipped with their counted warning; orphan releases are ignored with their counted warning. Their source IDs cannot appear as native attacks or notation bindings. No fabricated release is allowed. Implausible-meter repairs also require the observed counted/detail warning. |
| `meter_grid` | Independently reconstruct the whole-file bar grid from source time signatures and last track event. Default is 4/4; meter changes begin a fresh bar, including a shortened preceding bar; the final bar extends to a full meter boundary. Deduplicate repeated meter declarations. Numerator or denominator above 32 is ignored with a warning; conflicting usable declarations fail closed. Native and both generated hand parts must have the original-derived measure count, labels, meters, boundaries, and duration. A shortened bar needs `implicit="yes"`. |
| `printed_rhythm` | Two generated parts RH/LH; explicit 10080 divisions per quarter; positive timed notes/rests. Note type, dots, and positive actual/normal ratio must mathematically equal the stored duration. Supported base values are whole through 128th, with exact dotted values and exact rational expressive durations. Pitch spelling must represent the raw source pitch, without claiming a unique enharmonic choice. |
| `bar_fill` | Every written voice tiles its source-derived bar without gaps, overlaps, negative cursors, or overfull durations. Hidden rests still occupy exact cursor time. Chords require an immediately anchored pitched event in the same voice with equal duration. |
| `source_mapping` | Segment IDs must be `pt` + the first 32 hex digits of SHA-256 of the **original** attack ID + `s` + consecutive zero-based segment index. Exactly one nonempty chain per retained attack, unique visible generated segments, matching original-derived pitch and policy hand; no unknown source or extra note. Native binding expectations come from this source-derived chain, never from native self-attestation. |
| `tie_continuity` | A chain's first segment has no incoming tie, its final segment no outgoing tie, and each intervening boundary has both continuation ends. Sound `<tie>` and written `<tied>` types agree. Continuations are contiguous in time and retain lane and pitch spelling. Rests cannot carry ties. |
| `display_quantization` | Original-derived bounds below constrain displayed onsets and complete chain releases. Each written lane belongs to one original track/channel owner. Coincident chord tones have distinct pitches and equal endpoints; other lane overlaps fail. No unique authorial voice allocation is inferred. |
| `native_notation` | Exact multiset of generated visible events versus native notation, including source-derived note/segment bindings, attack flags, hand, lane, measure, pitch/spelling, rhythm, chord and tie flags, accidental and ratio. Duplicates, missing events and fabricated events fail. Hidden rests are cursor scaffolding, absent from the visible native inventory. |
| `hand_mode` | Requested active hand and active attack IDs equal the selection independently derived from source hands; both written staves remain present. |

## Display timing bounds

Production behavior was read in `music.py`, `notation/lesson.py` and
`notation/model.py`; those modules are not imported by the verifier.

1. Source onsets and physical releases remain unchanged in native performance
   notes. Display ticks round to 10080 divisions per quarter. Ordinary displayed
   onsets equal that rounded source onset. A swung onset at .6 remains .6;
   straightening it to .5 fails.
2. The sole onset adjustment recognizes a complete four-distinct-onset pattern
   in an original track/channel/hand, at quarter-subdivision origin plus
   0, 1/12, 2/12, 3/12 quarters. Each source onset must be within .004 quarter
   beats of its corresponding point. The displayed onset may use that exact
   grid point. An output label such as `triplet` cannot authorize a move.
   This is a beat tolerance, not a fixed wall-clock millisecond tolerance.
3. A displayed chain release may preserve the rounded physical release or
   normalize it to the nearest 1/4-quarter subdivision (sixteenth note).
   Shortening is bounded by .08 quarter beats and extension by .15. For a
   note lasting at least one quarter, an approaching barline within .25 may
   supply the normalized endpoint; barline extension is bounded by .25.
   Conventional 3:2, 5:4, 7:4 and 9:8 durations keep their exact release.
   A normalized endpoint cannot cross the following source-backed attack in
   its written lane or the final source-derived bar boundary.
4. A remaining positive articulation gap no larger than 1/64 quarter may
   extend display release to the following lane attack if no barline lies
   in the gap. Physical key release remains exact. These checks accept a
   bounded set of legal display choices; they do not reproduce the generator's
   choice of a unique spelling or lane allocation.

## Inherent limits and fail-closed scope

This proves a transcription policy, not written authorship or engraving pixels.
MIDI has no authoritative notation for unique enharmonic spelling, written
rests/voices, graphical tuplets/beams, or pianist hand pairing. Overlapping
same-pitch releases lack attack IDs: verified FIFO policy does not remove
their authorial ambiguity. Only physical key-release duration is verified;
sustain/sostenuto sounding duration remains an explicit limitation.

The checker currently accepts entire SMF files and their whole generated piano
score, starting at beat zero. Partial exercise/simplification projections,
type-2 asynchronous files, SMPTE division, percussion, grace and unpitched
generated notes, and alternate/namespace-qualified output formats are outside
this version and remain unverified. A runtime error is recorded as incomplete
evidence. Unsupported cases, missing warnings, missing rule implementations,
and absent artifacts must block the rule gate. They are not score exemptions.

CPU validation uses the original project virtual environment with explicit
`PYTHONPATH=/home/tom/Projects/piano_teacher_phase5` and
`TMPDIR=/home/tom/tmp`. The tests mutate original pitch/onset/release/velocity,
native facts and bindings, generated inventories, meter/bar fill, rhythms,
ties, hand policy and FIFO pairing; they also exercise missing warnings,
missing XML, absent rule implementations and false proof assertions.
