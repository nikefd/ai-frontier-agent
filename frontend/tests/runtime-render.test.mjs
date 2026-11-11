import test from 'node:test';
import assert from 'node:assert/strict';
globalThis.location={search:'?lang=en'};
Object.defineProperty(globalThis,'navigator',{value:{language:'en-US'},configurable:true});
const {analyzeTrace}=await import('../src/runtime/analyze-trace.js');
const {nodePanel,evidenceSummary,eventList}=await import('../src/runtime/runtime-panels.js');
const {sourceMap,sourceUrl,codexSnapshot}=await import('../src/runtime/source-map.js');
test('trace details and search render imported payload as text, not executable HTML',()=>{
 const payload='<img src=x onerror=alert(1)>';
 const r=analyzeTrace(JSON.stringify([{type:'turn.started'},{type:'item.completed',item:{id:'x',type:'command_execution',command:'cat AGENTS.md',aggregated_output:payload,exit_code:0}}]));
 const html=nodePanel(r,r.nodes.find(n=>n.kind==='result').order);assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));assert.ok(html.includes('#2'));assert.equal(eventList(r,{filter:'all',selected:0,limit:300,query:'AGENTS.md'}).total,1);assert.ok(!evidenceSummary(r).includes('[object Object]'));
});
test('source references use the immutable reviewed snapshot and real line anchors',()=>{
 assert.equal(sourceMap.length,7);for(const entry of sourceMap){assert.ok(sourceUrl(entry).includes(codexSnapshot));assert.ok(entry.line>0);assert.equal(entry.action.length,2);}
});
