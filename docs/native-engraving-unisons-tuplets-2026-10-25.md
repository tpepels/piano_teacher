# Native unisons and Moonlight tuplet follow-up

Continues from `833e1d9`. This work changes engraving and independent pixel
recognition; audit recovery, resource limits, checkpointing and capture
scheduling are unchanged. No corpus audit was run.

## Engraving corrections

Simultaneous hollow half and filled quarter heads previously occupied the
same position, with overlapping voices falling through to a common pitch-only
stem rule. The half head could disappear under the quarter head.

The renderer now resolves overlapping two-voice stem defaults from source voice
order, preserving explicit stem and beam directions. Colliding voice columns
separate using authentic head bounds. Every chord retains its internal Verovio
head/stem arrangement. Compatible heads with opposing stems remain shared;
same-direction shafts and incompatible heads separate. Only connected collision
components recenter, so unrelated third voices remain at their original onset.

Chord sprites, stems, beam endpoints, ties, accidentals, spacing bounds and
tuplet endpoints consume the same column translation. The sprite-envelope
regression checks both edges after a controlled translation, preventing density
and rest placement from underestimating the shifted ink.

This follows the distinction between compatible shared heads and independently
readable half/quarter heads described in
[LilyPond's collision rules](https://lilypond.org/doc/v2.27/Documentation/notation/multiple-voices).

## Moonlight diagnosis

The retained Moonlight bracket was present. Its three retained frames place the
coloured playhead over required bracket ink. A one-pixel best fit moved the
occlusion check away from the actual hidden hook, producing a misleading
missing/detached diagnosis. The verifier now checks the full permitted fit
corridor before fitting; those frames remain unverified.

A fresh production framebuffer at beat 1.0 exposes the complete bracket and
verifies it. That clock already belongs to the canonical source capture
schedule. Erasing, moving, interrupting or detaching either hook still fails.
No Moonlight-specific drawing change, extra schedule or fabricated geometry
was needed. A separate overlapping-voice tuplet regression also exposed and
corrected bracket endpoints that had ignored column translations.

## Independent proof and regressions

The source reader now retains explicit stem declarations. Source polyphony
bounds displaced-head searches; photographed staff rails, external glyph
families and actual PNG support establish the matches. Incompatible heads
retain exclusive pixel ownership. Compatible shared heads require their own
independent physical shafts in the feature checker. The pitch-only oracle no
longer rejects every unison indiscriminately: it verifies distinct required
heads while keeping genuinely inseparable shared identities ambiguous.

Dice, family margin, visibility, pitch, hook and bracket thresholds are
unchanged. Renderer-reported head coordinates do not authorize these proofs.
New actual-framebuffer cases cover overlapping mixed chords, compatible shared
heads, same-direction unisons, an unrelated third voice, a shifted beam and a
bracketed tuplet. Head and shaft erasure cannot borrow the other voice's ink.

Focused validation scopes (counts overlap):

- Native voice/chord/tie/beam/spacing scope: **62 passed**.
- Tuplet/connector scope, including fresh Moonlight and mutations: **77 passed**.
- Independent feature/raster scope: **110 passed**.
- After the pitch-only unison correction, canonical head/raster scope:
  **91 passed**; new live collision matrix: **24 passed**.
- Expanded fast suite under Xvfb: **176 passed**, plus Godot parsing.

## Remaining limits

The pitch-only oracle intentionally leaves compatible shared-head source
identities ambiguous; the feature checker proves their common head and separate
shafts. Dense or occluded contours still fail closed.

An ascending beam with a nearby sloped tuplet bracket/numeral can contaminate
the existing beam/bracket bounding-box probes. That combined oracle limitation
remains unresolved; no annotation mask or relaxed threshold was introduced.
The repeated-pitch overlapping-tuplet case isolates endpoint attachment, while
the separate shifted-beam case proves complete beam attachment. Neither is a
claim of full-library correctness.

Historical archive branches and the external preservation bundle remain
untouched. Work stays in the sole main checkout.

Recommended focused local command (includes real framebuffer regressions,
fast tests and Godot parsing; never starts a corpus batch):

```bash
LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a ./scripts/verify-notation.sh --ci
```
