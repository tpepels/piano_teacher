/* Exact fixed-fingering overlap index for whole-piece inference.
 * The interval predicate is IDENTICAL to the original bridge's overlap
 * relation, including EPS. This module changes query cost, not constraint
 * semantics, source order, model logits or the choice of fingers.
 */
'use strict';

const EPS = 1e-5;
const overlaps = (a, b) =>
  a.time < b.time + b.duration - EPS &&
  b.time < a.time + a.duration - EPS;

class FixedOverlapIndex {
  constructor(fixed) {
    // Do not mutate the input array (the model and callers own its order).
    this.items = fixed.map((note, order) => ({note, order}))
      .sort((a, b) => a.note.time - b.note.time || a.order - b.order);
    this.prefixEnd = new Float64Array(this.items.length);
    let farthest = -Infinity;
    for (let i = 0; i < this.items.length; i++) {
      const note = this.items[i].note;
      farthest = Math.max(farthest, note.time + note.duration);
      this.prefixEnd[i] = farthest;
    }
  }

  overlapping(note) {
    const latestStart = note.time + note.duration - EPS;
    const earliestEnd = note.time + EPS;
    // prefixEnd is monotonically nondecreasing, even with nested/long
    // held notes. A long fixed note starting many bars earlier survives.
    let lo = 0, hi = this.items.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.prefixEnd[mid] <= earliestEnd) lo = mid + 1;
      else hi = mid;
    }
    const first = lo;
    lo = first;
    hi = this.items.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.items[mid].note.time < latestStart) lo = mid + 1;
      else hi = mid;
    }
    const found = [];
    for (let i = first; i < lo; i++) {
      const item = this.items[i].note;
      if (overlaps(item, note)) found.push(item);
    }
    return found;
  }
}

module.exports = {FixedOverlapIndex, overlaps, EPS};
