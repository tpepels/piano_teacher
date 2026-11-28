# Local piano difficulty recognition and adaptive practice

Status: research proposal; no production integration approved.

## 1. Motivation and research question

The present progression from Free (untimed) practice to Tempo (continuous pulse) can leave a learner stuck on a single difficult measure. Repeating the measure, reducing its tempo or separating the hands does not necessarily teach the specific physical movement that causes failure. The third measure of the Pathétique is the motivating example; its actual difficulty and cause have not yet been analysed.

An intermediate, single-hand practice approach may eventually help by introducing local timing requirements and gradually restoring the original rhythm. However, it must be applied selectively. A straightforward melody should normally proceed directly from Free to Tempo. Earlier experiments with exercise generation (Coda and Fukuyama) did not establish sufficient pedagogical value. We must not repeat that approach by building another integrated teaching system before validating the underlying diagnosis.

**Primary research question:** Can a computer identify, localize and explain technically difficult piano movements in symbolic scores, with sufficiently few false positives to justify selective intervention?

Three distinct questions must remain separate:

1. Does a particular technical pattern occur in the music?
2. How demanding is that pattern at a given tempo, with a given fingering and surrounding context?
3. Does that demand cause a specific learner difficulty, and can an intervention improve performance of the original passage?

Success at one level does not establish success at the next.

## 2. Scope and units of analysis

Start with one hand at a time. Analyse individual attacks, simultaneous attack groups, transitions and short movement sequences, preserving their relationship to the source score. Measures are a useful display and aggregation unit but must not be analysis boundaries: a difficult movement may begin in one measure and end in the next.

Use original pitches, durations, voices, ties, metrical positions, tempo map, hand assignments and the effective fingering (including user overrides). Distinguish a sustained note from a new attack, and a finger assignment from an observed finger movement. Where available, retain multiple plausible fingerings and their provenance. Do not infer hand assignment solely from staff or pitch.

Report difficulty at the intended performance tempo as well as the learner's current tempo. A passage can be straightforward at one speed and difficult at another.

## 3. Technical feature recognition

The initial analyser should identify and explain the following distinct dimensions. Feasibility estimates are hypotheses to validate, not established detection accuracy.

| Dimension | Observable evidence | Initial feasibility / limitation |
| --- | --- | --- |
| Jumps and hand displacement | Distance between feasible hand positions, available travel time, intervening releases, destination shape | High for candidate jumps; hand position is inferred |
| Octaves, wide intervals and stretches | Physical key spacing, simultaneous spans, finger-pair feasibility, retained notes | High for geometry; comfort depends on hand size |
| Chord shapes | Cardinality, span, black/white key geometry, assigned fingers and held voices | High for features; execution difficulty must be calibrated |
| Chord transitions | Changes of shape, position and finger assignment; common notes; time to release and prepare | High for descriptors; context matters |
| Fast runs and ornaments | Inter-attack intervals in seconds, local density, direction changes and sustained speed | High for speed; speed alone is insufficient |
| Repeated notes and repeated fingers | Same-pitch recurrence, repetition interval and available alternative fingering | High for patterns; technique remains inferred |
| Thumb-under and finger-over | Hand-specific pitch direction and finger sequence, key geometry and adjacent hand positions | Moderate; distinguish likely crossing from lateral repositioning |
| Finger substitution | Change of finger on a sustained key, overlapping notes, alternative paths | Moderate when explicitly annotated; otherwise uncertain |
| Finger independence / polyphony | Concurrent held and moving fingers, legato obligations, overlapping voices and release requirements | Moderate; actual tension is unobservable |
| Hand rotation / repositioning | Implied changes in hand orientation, reach, fingering and shape | Low to moderate; multiple physical realizations may fit |
| Rhythmic execution demands | Short/unequal intervals, syncopation, subdivisions, tuplets and changes of grouping | High for rhythmic features; separate from pitch mechanics |
| Physical tension or pain | Not directly observable from symbolic score or ordinary MIDI | Do not claim diagnosis |

Use a physical keyboard model rather than semitone distance alone. The geometry of black and white keys, thumb placement, finger-pair spans and the time needed to reach the next feasible hand position are relevant. Support left/right mirroring without assuming every crossing is symmetric.

Do not treat every chord, crossing or jump as inherently difficult. A long rest before a leap, a comfortable fingering of a scale, or a repeated familiar chord shape may be easy. Interactions between demands matter: a quick displacement from a held wide chord can be much harder than either demand in isolation.

Explicitly distinguish observed score facts, derived geometric features, inferred physical movements, and difficulty predictions. Missing fingering, uncertain hand assignment or ambiguous release timing must reduce confidence rather than silently become zero difficulty.

## 4. Ergonomic and difficulty modelling

Begin with an interpretable deterministic feature extractor and an ergonomic baseline. Investigate alternative models only against the same evaluation protocol.

- Model feasible hand configurations over a short sequence, including notes held through transitions.
- Compare movement distance and preparation time, rather than pitch distance alone.
- Keep separate feature dimensions and their interactions; avoid collapsing everything into an unexplained scalar.
- Compare multiple fingerings when available. Report whether a predicted bottleneck is robust or depends on one inferred fingering.
- Make hand-span assumptions explicit and configurable; avoid claiming precise biomechanics from notation.
- Preserve confidence and uncertainty for every candidate difficulty.
- Produce sparse, localized bottleneck candidates with reasons. Permit an empty result for a simple passage.

A global piece-level difficulty model or a fingering model's internal cost can provide a baseline or additional evidence, but cannot by itself establish that a specific movement is hard or that the learner needs intervention.

## 5. Pluggable research architecture

Keep all experimental code outside the production practice flow initially. The first deliverable is a standalone Python analysis module and CLI, not a new practice mode.

Suggested boundaries (names and paths are proposals, not existing APIs):

```text
Read-only score / effective fingering / tempo / hand
                    |
             Input adapter
                    |
          DifficultyAnalyser protocol
            /         |          \
   geometric      ergonomic     alternative
    baseline       model          model
            \         |          /
             DifficultyReport
                    |
          CLI / evaluation / reports

Optional later, after validation:
DifficultyReport + learner evidence
                    |
           PracticePrescription policy
                    |
           Existing practice infrastructure
```

The analyser accepts an immutable score window with sufficient preceding and following context. Its output is versioned and serializable. A candidate record should include source fingerprint and revision, hand, stable note/attack identifiers, beat interval, measure references, evaluated tempo, feature evidence and units, proposed difficulty type and severity, confidence, fingering provenance, model/version and explanatory reasons. It must support no candidates, insufficient evidence and unsupported inputs.

Keep model selection, weights and thresholds configurable. Cache only against the relevant score, fingering, tempo and model identities. Alternative analysers must be interchangeable without modifications to the renderer or application session.

The experiment must not own MIDI input, grading, rendering, transport, musical timeline state, lesson progression or mastery. It must not create a second authoritative clock, persist changes to original scores or automatically alter fingerings. No runtime dependency or behavioural change when the experiment is absent or disabled. An eventual policy may return a prescription, but the existing authoritative components must validate and execute it. Failure or abstention must leave the established practice flow available.

## 6. Research phases and completion gates

### D0 — Corpus and evaluation design

Before tuning a difficulty model, define an annotation rubric and a fixed evaluation protocol. Assemble checked-in repertoire excerpts, straightforward melodies as negative controls, controlled synthetic examples and more complex passages. Include the exact Pathétique passage when the source edition and hand are available; do not assume the cause from its reputation or the report of repeated failure.

Label the presence of a technical pattern separately from perceived severity and actual failure. Ask pianists or teachers to annotate localized events or transitions, with tempo, fingering assumptions and disagreement recorded. Use public datasets where licenses and reconstruction permit.

Separate development and held-out pieces by composition, not random neighbouring measures. Freeze the evaluation split and acceptance criteria before comparing models. Do not train or tune on the motivating passage and then present that passage as independent validation.

**Exit:** documented corpus, annotation scheme, reproducible split, baseline methods and quantitative acceptance criteria. Proposed metrics are below; numerical targets should be agreed after establishing annotation reliability and before model tuning.

### D1 — Deterministic feature recognition

Implement the canonical input adapter, attack/transition representation, keyboard geometry, feature detectors for the dimensions in section 3, and machine-readable and human-readable reports. Include explicit unsupported/uncertain cases for features that cannot yet be reliably recognized.

Unit fixtures must cover hands, ties, held notes, chords, releases, repeated notes, changes in tempo and meter, crossings, alternatives in fingering, black/white key geometry, transposition, and transitions across barlines. Include ordinary melodies, comfortable scales and chords with sufficient preparation time.

**Exit:** feature-level ground-truth tests pass; independent inspection of real repertoire reports confirms correct localization and explanations. Feature recognition alone is not authorization to generate exercises.

### D2 — Difficulty estimation and model comparison

Develop an interpretable ergonomic model of movement sequences. Compare with simpler baselines such as note density, pitch distance and a model that assigns the same difficulty to each measure. Investigate fingering-derived learned representations where justified. Report uncertainty and sensitivity to tempo, fingering, and assumed hand span.

**Exit:** held-out evidence shows that the proposed model improves localization and severity estimation over the baselines without unacceptable false positives on easy material. A model that marks almost everything difficult fails this gate.

### D3 — Independent validation

Use expert annotations and separately collected performance data. Evaluate feature precision/recall by category, localization precision/recall and overlap, ranking of difficult versus easy transitions, ordinal severity agreement, calibration or selective accuracy, abstention coverage and false-positive rate on easy controls. Report per-hand and per-technique results, sample sizes, annotator agreement and uncertainty; do not rely on a pooled average alone.

Test counterfactuals: slower tempo should generally reduce speed-related demands without eliminating a wide span; an easier fingering should affect fingering-related estimates; a transposition may change black-key geometry; a rest may make the same jump easier. Include counterexamples to overly simple rules.

Review the actual Pathétique report and a broad sample of predictions and errors. If localization or selectivity is inadequate, revise the analyser or stop the experiment. Preserve negative results.

**Exit:** documented held-out results satisfy the agreed criteria and receive explicit approval before any adaptive practice integration.

### D4 — Learner-specific difficulty

Only after validating score-derived predictions, compare them with existing Free and Tempo evidence at attack/transition resolution. Useful signals include time between successful attacks in Free (accounting for staff travel and intentional pauses), wrong pitches, missing chord notes, onset deviations, incomplete or uneven attacks and repeated localized failures. Distinguish actual difficulty from MIDI admission faults, rendering delays, warm-up inputs and missing observations.

Use repeated observations to estimate which demands are specifically difficult for the learner. Do not interpret MIDI as direct evidence of which finger was used, wrist motion or tension. Keep the original score-based prediction separate from the learner-specific estimate.

**Exit:** prospective evidence demonstrates improved prediction of individual bottlenecks over score-only and performance-only baselines.

### D5 — Conditional future experiment: intermediate practice

This phase is not approved for implementation by this proposal. It requires the preceding validation and a separate decision.

For a confirmed bottleneck, insert an optional single-hand intermediate mode between Free and Tempo. Begin with original pitches, original effective fingering and a small source-linked window (normally one measure, with neighbouring context when necessary). Introduce timing requirements selectively: comfortable movements retain a local pulse, while a difficult transition may receive additional preparation time or a short isolated sequence. Reduce allowances progressively and reconstruct the original rhythm.

The prescription must state the targeted movement, source interval, local timing constraints, success criteria and conditions for returning to Free/Tempo. No blanket activation for every measure. Do not make every hard passage uniformly slower or invent unrelated musical exercises. Any later simplification of notes or chord structure requires separate justification and evaluation.

Regularly probe the original unmodified passage at its intended practice tempo. Measure accuracy and timing, number of attempts or time to reach criterion, and retention in later sessions. Compare against the existing Free-to-Tempo flow at comparable practice exposure. Success on a generated exercise never grants mastery of the original passage. Stop or remove the intervention if it fails to transfer or performs worse than the baseline.

## 7. Report and CLI deliverables

The standalone tool should make it possible to analyse one passage, a whole score or the repertoire in batch; choose hand, tempo, fingering and model; export JSON for reproducibility and a readable report for manual inspection.

A human report should expose an attack/transition-level explanation and separate per-hand, per-measure heatmaps for movement, chord transitions, crossing, stretch, attack rate, independence and other supported dimensions. A heatmap must distinguish low predicted difficulty from unknown or unanalysed material. Display units and actual feature values alongside scores. Show the top localized candidates and the surrounding notes rather than only measure totals.

Example (hypothetical, not a diagnosis of the Pathétique):

- Right hand, transition from attack A to B across measure 3: large inferred displacement with short preparation interval after a held chord.
- Evidence: key displacement, release-to-onset interval, chord geometry, effective fingering.
- Confidence: depends on fingering and release assumptions.
- No recommendation to intervene until severity and learner difficulty are supported.

Evaluation artifacts must include corpus provenance, model/version, configuration, annotation rubric, split, metrics, error cases and reproducible invocation.

## 8. Research starting points

These works motivate methods and evaluation; none proves the proposed local diagnostic or teaching system works.

- Parncutt, Sloboda, Clarke, Raekallio and Desain (1997), [An Ergonomic Model of Keyboard Fingering for Melodic Fragments](https://online.ucpress.edu/mp/article-abstract/14/4/341/61993/An-Ergonomic-Model-of-Keyboard-Fingering-for). A rule-based ergonomic starting point for melodic fingering; do not assume it handles general polyphonic passages.
- [Refinements to the Ergonomic Model for Keyboard Fingering](https://online.ucpress.edu/mp/article-abstract/18/4/505/62095/Refinements-to-the-Ergonomic-Model-for-Keyboard) (2001). Relevant to physical finger spans and limitations of semitone-only cost rules.
- [Statistical Learning and Estimation of Piano Fingering](https://www.sciencedirect.com/science/article/pii/S0020025519311879) (2020). Statistical fingering estimation and pianist-annotated fingering data (PIG).
- Ramoneda et al. (2022), [Score Difficulty Analysis for Piano Performance Education Based on Fingering](https://arxiv.org/abs/2203.13010), [code](https://github.com/PRamoneda/ICASSP22), [Mikrokosmos-difficulty dataset](https://zenodo.org/records/6092709). Fingering-derived representations for difficulty classification; investigate how much they support reliable localization.
- Ramoneda et al., [Combining Piano Performance Dimensions for Score Difficulty Classification](https://arxiv.org/abs/2306.08480), [CIPI dataset](https://zenodo.org/records/8037327). Piece-level difficulty labels for comparison; not direct ground truth for individual technical movements.
- [Piano Difficulty Dataset](https://github.com/cperezs/piano-difficulty-dataset). Repository describes 64 MusicXML scores with difficulty-relevant measure annotations. Investigate the accompanying paper, annotation definitions, reconstruction procedure and licenses before use. Measure labels alone are not technique-specific transition annotations.
- [Towards Explainable and Interpretable Musical Difficulty Estimation — research companion](https://pramoneda.github.io/rubricnet/). Additional lead for examining localized and interpretable evidence.

Review full papers, methods, licenses, annotation quality and reproducibility in D0. Do not import external code or model weights into the application until the research boundary and licensing requirements have been established.

## 9. Definition of success

A useful analyser must reliably identify where a technical difficulty occurs, what observable features explain it, when it is uncertain and when no special difficulty exists. It must outperform trivial baselines on held-out material and avoid turning normal melodies into unnecessary remedial exercises.

The eventual teaching experiment must demonstrate improvement on the original passage, not merely better performance of an adaptive exercise. Until then, the production Free-to-Tempo progression remains unchanged.

No implementation or integration phase is considered complete without its corresponding deliverables, evidence and exit gate. If research fails to establish validity, keep the experiment isolated or remove it rather than expanding the production architecture.
