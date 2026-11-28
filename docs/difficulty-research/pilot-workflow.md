# D0 pilot workflow

The plan selects six real development windows, each hand separately, at source and half-source tempo, plus eight original synthetic controls. There are 32 conditions. The pilot is deliberately separate from the held-out repertoire and synthetic families. No predictions or expected labels are shown to raters.

1. Generate a source inventory from the pinned MIDI files:

   ```bash
   .venv/bin/python docs/difficulty-research/pilot.py inventory /tmp/d0-review
   ```

   Review the source against an identified score edition. A qualified source reviewer fills in hand, effective finger (1–5 or unknown), provenance, score attack/release ticks, displayed measure, voice, edition reference and reviewer ID. Immutable MIDI note identity/ticks/pitch cannot be changed. A rolled chord may have a shared reviewed attack tick. Context includes at least four quarter notes and two seconds on either side, including notes still held at its start; do not assume a MIDI track or staff determines hand. Unknown target hands are blocked; unresolved context is included separately in the packet; unknown fingers are allowed and must be accounted for in category ratings. The original MIDI is not copied outside the checkout by the inventory. Local source review has to be actually completed; the template is not evidence.

2. Generate the rating packet:

   ```bash
   .venv/bin/python docs/difficulty-research/pilot.py prepare /tmp/d0-review/source-review.csv /tmp/d0-packet
   ```

   Give each of three independent experienced pianists or teachers the packet.json, one ratings CSV, this rubric and the relevant score editions (with permission to distribute). Keep the coordinator-key.json private. The packet is a structured note/attack index for alignment with notation, not a replacement for reading the score. For synthetic cases, the note table itself defines the complete score; render or play it if needed, without exposing its expected feature labels. For real cases, use the identified notated source, including original ties and voice assignments. Tempo maps are in microseconds per quarter note; the factor scales tempo, not beat positions. Review all target attacks; the other notes provide context. Do not share any other rater's responses. Do not test painful fingerings.

   Each rater supplies a unique pseudonym, playing/teaching background, judgment mode (score/played), severity 0–3 or unknown, each category's presence (present/absent/unknown/not_applicable), confidence (low/medium/high), brief evidence and optional alternative fingering. Use the main protocol definitions. Use not_applicable only when the category genuinely does not apply, not when evidence is missing. Rotation/tension are intentionally not rated as observed features. Source hand and finger data are not ground truth for actual movement. Do not enter invented or AI-generated ratings as independent human data.

3. Assess the three completed sheets:

   ```bash
   .venv/bin/python docs/difficulty-research/pilot.py assess /tmp/d0-packet/packet.json \
     /tmp/d0-packet/ratings-1.csv /tmp/d0-packet/ratings-2.csv /tmp/d0-packet/ratings-3.csv \
     --output /tmp/d0-packet/agreement.json
   ```

   The command validates one row per attack per rater, checks packet/plan/corpus identity and the packet ID on every rating row, records packet, plan, corpus, source-review and rating-sheet digests in agreement.json, computes ordinal Krippendorff alpha with finite-sample coincidence weighting, overall and fully-rated severity coverage, and per-category positive agreement and coverage. Categories need at least 20 majority-positive and 20 majority-negative units in the pilot; otherwise mark insufficient sample, not success. Unknown/not applicable are excluded from valid pair agreement, with coverage and denominators retained. A failed or undefined alpha, insufficient severity coverage, or inadequate agreement for a sufficiently sampled category blocks the pilot. At least one category must pass; under-sampled categories remain explicitly unvalidated. This is a screening calculation, not proof of agreement across composers, and passing does not by itself authorize D1 model tuning.

4. Coordinator checks source-review provenance, actual independent rater participation and permission/consent, resolves mapping errors without deleting disagreements, reviews rare categories, and signs final numerical criteria before any model tuning. If reliability is insufficient, revise the rubric and repeat a separately frozen development pilot. Keep consent and identifiable files outside Git; store only approved de-identified labels and report. The original user Pathétique source remains a separate case. No data has been invented, no ratings collected in this commit, and no D0 gate waived.

## Status

D0 research design and execution tooling are ready. Independent annotation and source review remain empirical tasks. No local score-derived estimate is substituted for them. The public-domain reference score is useful for eventual held-out evaluation; it does not identify the exact original user source.
