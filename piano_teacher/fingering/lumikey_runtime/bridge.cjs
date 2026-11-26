/* Production adapter: use upstream tokenization/inference and pretrained weights.
 * Only hard physical/fixed constraints mask actual ONNX logits. No fallback
 * finger generation: impossible candidates are explicitly returned as unknown.
 */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const ort = require('onnxruntime-node');
const {predictHandFingerings} = require('@lumikey/piano-fingering-model');
const {FixedOverlapIndex, overlaps} = require('./fixed_overlap_index.cjs');
const expected = {
  left: '246f2fed013c27ca8c32ce9d070002afcc49da4f1dfb0c43e09a4a3f9f2fb86e',
  right: 'f931288302b87f5eec1c8af29a570ee0213a272a13eeb590991a285e1f1b67eb'
};
const EPS = 1e-5;

function sharedThumb(a,b) {
  // The thumb can depress two neighbouring keys at the same height.
  // Mixed black/white keys and the wider gap between black-key groups
  // are deliberately excluded. Sharing is a simultaneous attack, not
  // a second attack while a previous thumb note is still held.
  const distance=Math.abs(a.note-b.note);
  const black=pitch=>[1,3,6,8,10].includes(pitch%12);
  return a.left===b.left && a.time===b.time &&
    distance>0 && distance<=2 && black(a.note)===black(b.note);
}

function chordCanFinish(chord, active, groupFixed, current, finger, left) {
  const keys=[...new Set(chord.map(a=>a.note))].sort((a,b)=>a-b);
  if(keys.length>6) return false;
  const occupied=[...active,...groupFixed];
  const choices=keys.map(pitch=>{
    const members=chord.filter(a=>a.note===pitch);
    const available=[];
    for(let ordinal=1;ordinal<=5;ordinal++) {
      const f=left?6-ordinal:ordinal;
      if(pitch===current.note && f!==finger) continue;
      if(members.some(a=>a.finger && a.finger!==f)) continue;
      if(members.some(a=>occupied.some(b=>{
        if(!overlaps(a,b)) return false;
        if(a.note===b.note) return f!==b.finger;
        return f===b.finger && !(f===1 && sharedThumb(a,b));
      }))) continue;
      available.push(ordinal);
    }
    return available;
  });
  // Walk all distinct pitches in order. Equality is possible only for
  // a two-key thumb pair; all other fingers remain strictly ordered.
  // The earlier pitches are checked too, including rejected/unknown
  // notes, and held/fixed constraints are applied to each chord member.
  const visit=(position,previous,thumbCount)=>{
    if(position===keys.length) return true;
    for(const ordinal of choices[position]) {
      if(ordinal<previous) continue;
      const f=left?6-ordinal:ordinal;
      if(ordinal===previous && !(f===1 && thumbCount===1 &&
          sharedThumb(chord.find(a=>a.note===keys[position-1]),
                      chord.find(a=>a.note===keys[position])))) continue;
      if(f===1 && thumbCount===2) continue;
      if(visit(position+1,ordinal,thumbCount+(f===1?1:0))) return true;
    }
    return false;
  };
  return visit(0,0,0);
}

async function handInference(notes, left, session) {
  const sorted = notes.filter(n => n.left===left).sort((a,b)=>a.time-b.time || a.note-b.note);
  const reasons = new Map();
  const byId = new Map(sorted.map(n=>[n.source_id,n]));
  const chords = new Map();
  for(const n of sorted) {
    if(!chords.has(n.time)) chords.set(n.time,[]);
    chords.get(n.time).push(n);
  }
  const fixed = sorted.filter(n=>n.finger);
  // Original exhaustive fixed.some/filter checks scanned the complete
  // piece for EACH attack and every candidate/chord backtracking branch.
  // Query original fixed objects by source-time interval instead.
  const indexedFixed = new FixedOverlapIndex(fixed);
  const chordFixed = new Map();
  const held = [];
  let index=0;
  const wrapper = {run: async inputs => {
    const n=sorted[index++];
    const out=await session.run(inputs);
    const raw=Array.from(out.logits.data);
    if (raw.length!==5 || !raw.every(Number.isFinite)) throw new Error('Invalid model logits');
    // A shared physical key may belong to multiple simultaneous written voices.
    const active=held.filter(a=>a.time+a.duration>n.time+EPS);
    held.splice(0,held.length,...active);
    const chord=chords.get(n.time);
    let groupFixed = chordFixed.get(n.time);
    if (!groupFixed) {
      const all = new Set();
      for (const member of chord) {
        for (const match of indexedFixed.overlapping(member)) all.add(match);
      }
      groupFixed = [...all];
      chordFixed.set(n.time, groupFixed);
    }
    const allowed = finger => chordCanFinish(chord,active,groupFixed,n,finger,left);
    let chosen=n.finger;
    if (chosen) {
      if (!allowed(chosen)) reasons.set(n.source_id,'Conflicting fixed fingering or unplayable overlap');
    } else {
      const candidates=raw.map((score,i)=>({score,finger:i+1}))
        .filter(a=>allowed(a.finger));
      if (!candidates.length) {
        reasons.set(n.source_id,'No physically available finger for these overlapping keys/constraints');
        // Upstream still advances its model history using its genuine best
        // prediction. We reject that candidate, never display or hold it.
      } else {
        chosen=candidates.reduce((a,b)=>b.score>a.score?b:a).finger;
        for(let i=0;i<5;i++) if(i+1!==chosen) out.logits.data[i]=-Infinity;
      }
    }
    if(chosen) held.push({...n,finger:chosen});
    return out;
  }};
  const results=await predictHandFingerings(sorted,left,wrapper);
  return results.map(n=>({source_id:n.source_id,
    finger: reasons.has(n.source_id) && !byId.get(n.source_id).finger ? null : n.finger,
    reason:reasons.get(n.source_id)||''}));
}

async function main() {
  const request=JSON.parse(fs.readFileSync(0,'utf8'));
  const directory=path.resolve(path.dirname(require.resolve('@lumikey/piano-fingering-model')),'..','models');
  // RH and LH have independent pretrained weights and inference histories.
  // Loading and running them serially doubled cold/full-piece wall time on
  // multi-core CPUs. Run each original model in its own one-thread ONNX
  // session, preserving the original left-then-right output ordering.
  async function inferHand(hand) {
    const file=path.join(directory,`fingering_transformer_${hand}.onnx`);
    const bytes=fs.readFileSync(file);
    if(crypto.createHash('sha256').update(bytes).digest('hex')!==expected[hand]) throw new Error('Unexpected model weights: '+hand);
    const session=await ort.InferenceSession.create(bytes,{executionProviders:['cpu'],intraOpNumThreads:1,interOpNumThreads:1});
    try { return await handInference(request.notes,hand==='left',session); }
    finally { await session.release(); }
  }
  const [left, right] = await Promise.all([
    inferHand('left'), inferHand('right')]);
  process.stdout.write(JSON.stringify({assignments:[...left,...right]}));
}
main().catch(error=>{console.error(error.stack||String(error));process.exitCode=1;});
