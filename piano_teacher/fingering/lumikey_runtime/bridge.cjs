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
const expected = {
  left: '246f2fed013c27ca8c32ce9d070002afcc49da4f1dfb0c43e09a4a3f9f2fb86e',
  right: 'f931288302b87f5eec1c8af29a570ee0213a272a13eeb590991a285e1f1b67eb'
};
const EPS = 1e-5;
const overlaps = (a,b) => a.time < b.time+b.duration-EPS && b.time < a.time+a.duration-EPS;

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
    const keys=[...new Set(chord.map(a=>a.note))].sort((a,b)=>a-b);
    const futureFixed=fixed.filter(a=>a!==n && overlaps(a,n));
    const shared=active.find(a=>a.note===n.note);
    const allowed = finger => {
      if(fixed.some(a=>a.note===n.note && overlaps(a,n) && a.finger!==finger)) return false;
      if (active.some(a=>a.note!==n.note && a.finger===finger)) return false;
      if (futureFixed.some(a=>a.note!==n.note && a.finger===finger)) return false;
      if (shared && shared.finger!==finger) return false;
      // Within a chord, fingers follow pitch order; reserve room for every
      // higher key, and respect authored/manual hints on either side.
      const rank=keys.indexOf(n.note), ordinal=left ? 6-finger : finger;
      if (ordinal<rank+1 || ordinal>5-(keys.length-rank-1)) return false;
      for (const a of [...active,...chord.filter(a=>a.finger)]) {
        if (Math.abs(a.time-n.time)>EPS || a.note===n.note) continue;
        const other=left ? 6-a.finger : a.finger;
        if ((a.note<n.note && other>=ordinal) || (a.note>n.note && other<=ordinal)) return false;
      }
      return true;
    };
    const canFinishChord = finger => {
      const rank=keys.indexOf(n.note);
      const ordinal=f=>left?6-f:f;
      const visit=(position,previous) => {
        if(position===keys.length) return true;
        const pitch=keys[position];
        const members=chord.filter(a=>a.note===pitch);
        const bound=members.find(a=>a.finger);
        const existing=active.find(a=>a.note===pitch);
        for(let next=previous+1; next<=5; next++) {
          const f=left?6-next:next;
          if(bound && bound.finger!==f || existing && existing.finger!==f) continue;
          if(fixed.some(a=>a.note===pitch && a.finger!==f && members.some(b=>overlaps(a,b)))) continue;
          if(active.some(a=>a.note!==pitch && a.finger===f)) continue;
          if(fixed.some(a=>a.note!==pitch && a.finger===f && members.some(b=>overlaps(a,b)))) continue;
          if(visit(position+1,next)) return true;
        }
        return false;
      };
      return visit(rank+1,ordinal(finger));
    };
    let chosen=n.finger;
    if (chosen) {
      if (!allowed(chosen)) reasons.set(n.source_id,'Conflicting fixed fingering or unplayable overlap');
    } else {
      const candidates=raw.map((score,i)=>({score,finger:i+1}))
        .filter(a=>allowed(a.finger) && canFinishChord(a.finger));
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
  const result=[];
  for(const hand of ['left','right']) {
    const file=path.join(directory,`fingering_transformer_${hand}.onnx`);
    const bytes=fs.readFileSync(file);
    if(crypto.createHash('sha256').update(bytes).digest('hex')!==expected[hand]) throw new Error('Unexpected model weights: '+hand);
    const session=await ort.InferenceSession.create(bytes,{executionProviders:['cpu'],intraOpNumThreads:1,interOpNumThreads:1});
    try { result.push(...await handInference(request.notes,hand==='left',session)); }
    finally { await session.release(); }
  }
  process.stdout.write(JSON.stringify({assignments:result}));
}
main().catch(error=>{console.error(error.stack||String(error));process.exitCode=1;});
