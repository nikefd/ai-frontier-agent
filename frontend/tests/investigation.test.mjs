import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { boot } from '../../research/runtime-case/boot.mjs';
import { routeExperiment, experimentCode, routes } from '../src/runtime/route-experiment.js';
import { investigationSteps } from '../src/runtime/investigation-case.js';
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
async function observe(run, path) {
 let release;
 const auth = new Promise(resolve => { release=resolve; });
 const state = { landing:undefined,publicLoads:0,privateLoads:0 };
 const done=run({path,state,initAuth:()=>auth,loadPublic:()=>state.publicLoads++,loadPrivate:()=>state.privateLoads++});
 const pending={...state};release();await done;
 return {pending,settled:{...state}};
}
test('the failing simulation agrees with the actual reproduction before and after auth',async()=>{
 for(const path of routes){const observed=await observe(boot,path);const prediction=routeExperiment({path});assert.deepEqual(observed,{pending:prediction.pending,settled:prediction.settled});}
});
test('all displayed code variants agree with predicted states and preserve private/root boundaries',async()=>{
 for(const earlyShell of [false,true])for(const earlyPublic of [false,true])for(const path of routes){
  const policy={path,earlyShell,earlyPublic};
  const code=experimentCode(policy);
  const variant=new AsyncFunction('input',`const {path,state,initAuth,loadPublic,loadPrivate}=input;${code}`);
  const observed=await observe(variant,path),prediction=routeExperiment(policy);
  assert.deepEqual(observed,{pending:prediction.pending,settled:prediction.settled});
  assert.equal(observed.pending.privateLoads,0);
  assert.equal(observed.settled.privateLoads,Number(path==='/experiments'));
  if(path==='/')assert.equal(observed.pending.landing,true);
  assert.equal(prediction.checks[0].pass,earlyShell);
  assert.equal(prediction.checks[1].pass,earlyPublic);
 }
});
test('each interpretation links to existing evidence and the expected stage of the real capture',async()=>{
 const records=(await readFile(new URL('../public/runtime-cases/codex-route.jsonl',import.meta.url),'utf8')).trim().split('\n').map(JSON.parse);
 for(const step of investigationSteps){
  assert.ok(step.correct>=0&&step.correct<step.choices.length);
  for(const line of step.lines)assert.ok(records[line-1]);
 }
 assert.equal(records[6].item.exit_code,1);
 assert.equal(records[11].item.exit_code,0);
 assert.match(records[13].item.command,/git diff -- boot\.mjs/);
});
