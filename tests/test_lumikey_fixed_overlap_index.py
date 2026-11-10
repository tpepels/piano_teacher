"""Exhaustive parity of full-piece Lumikey fixed-finger overlap checks.

The optimization may NOT change a single admissible finger/chord candidate.
No ONNX inference or large model download is required for this contract.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "piano_teacher" / "fingering" / "lumikey_runtime" / "fixed_overlap_index.cjs"


def test_lumikey_fixed_overlap_index_matches_original_exhaustive_predicate():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable")
    script = r"""
'use strict';
const assert = require('node:assert/strict');
const {FixedOverlapIndex, overlaps} = require(process.argv[1]);
let seed = 0x359a1;
const random = () => {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 2**32;
};
const fixed = [];
for (let i=0; i<2000; i++) {
  fixed.push({
    source_id: String(i),
    note: 21 + (i%88),
    finger: 1 + (i%5),
    time: Math.floor(random()*200)*125,
    duration: [.00001,.00002,1,60,125,500,5000][i%7]
  });
}
fixed.push({source_id:'whole',note:48,finger:1,time:0,duration:25000});
const index = new FixedOverlapIndex(fixed);
const queries = [];
for (let i=0; i<500; i++) {
  queries.push({
    time: random()*25100,
    duration: [.00001,.00002,0.125,125,2500,24900][i%6]
  });
}
for (let i=0; i<300; i++) queries.push(fixed[i]);
const check = (n) => {
  const expected = fixed.filter(a => overlaps(a,n));
  const actual = index.overlapping(n);
  assert.deepEqual(
    actual.map(a=>a.source_id).sort(),
    expected.map(a=>a.source_id).sort(),
    'indexed overlap set must match original exhaustive predicate');
  for (let finger=1; finger<=5; finger++) {
    // Exactly the two conditional families exercised by bridge.cjs:
    // note's fixed conflicts and other-key simultaneous constraints.
    assert.equal(actual.some(a=>a.note===n.note && a.finger!==finger),
      expected.some(a=>a.note===n.note && a.finger!==finger));
    assert.equal(actual.some(a=>a.note!==n.note && a.finger===finger),
      expected.some(a=>a.note!==n.note && a.finger===finger));
  }
};
for (const query of queries) check(query);
const chord = queries.slice(0,12);
const union = new Set(chord.flatMap(n=>index.overlapping(n)));
for (const candidate of fixed) {
  const old = chord.some(n=>overlaps(candidate,n));
  assert.equal(union.has(candidate),old,
    'grouped fixed set matches original members.some(overlaps)');
}
// Long-piece query must not mutate published authored order or fixed data.
assert.equal(fixed[0].source_id,'0');
assert.equal(fixed.at(-1).source_id,'whole');
process.stdout.write('LUMIKEY_FIXED_OVERLAP_PARITY:800\n');
"""
    result = subprocess.run(
        [node, "-e", script, str(INDEX)],
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "LUMIKEY_FIXED_OVERLAP_PARITY" in result.stdout
