import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeTrace,priorEvidence} from '../src/runtime/analyze-trace.js';
const lines=items=>items.map(x=>JSON.stringify(x)).join('\n');
test('Codex item lifecycle updates one command, preserving source lines and real exit status',()=>{
 const r=analyzeTrace(lines([{type:'turn.started'},{type:'item.started',item:{id:'i1',type:'command_execution',command:'node --test',status:'in_progress'}},{type:'item.completed',item:{id:'i1',type:'command_execution',command:'node --test',aggregated_output:'fail 1',exit_code:1,status:'completed'}},{type:'turn.completed',usage:{input_tokens:200,cached_input_tokens:100,output_tokens:20}}]));
 assert.equal(r.links.length,1);assert.deepEqual(r.links[0].call.lines,[2,3]);assert.equal(r.failures.length,1);assert.equal(r.testRuns.length,1);assert.equal(r.usage.input_tokens,200);assert.equal(r.usageSource,4);
});
test('Codex repeated item IDs in different turns stay distinct, last-turn usage is not summed',()=>{
 const events=[];for(const n of [1,2])events.push({type:'turn.started'},{type:'item.completed',item:{id:'i1',type:'command_execution',command:'echo ok',exit_code:0,aggregated_output:'ok'}},{type:'turn.completed',usage:{input_tokens:n*100}});
 const r=analyzeTrace(lines(events));assert.equal(r.links.length,2);assert.equal(r.links[0].results.length,1);assert.equal(r.usage.input_tokens,200);assert.equal(r.metadata.usageSemantics,'last-turn');
});
test('Claude parallel calls, child scopes and final usage retain their distinct evidence',()=>{
 const r=analyzeTrace(lines([{type:'system',subtype:'init',model:'test-model',tools:['Read','Bash']},{type:'assistant',parent_tool_use_id:null,message:{id:'m1',role:'assistant',content:[{type:'tool_use',id:'c1',name:'Read',input:{file_path:'app.js'}},{type:'tool_use',id:'c2',name:'Bash',input:{command:'npm test'}}],usage:{input_tokens:50}}},{type:'user',parent_tool_use_id:'child',message:{content:[{type:'tool_result',tool_use_id:'c1',content:'child result'}]}},{type:'user',message:{content:[{type:'tool_result',tool_use_id:'c2',content:'error',is_error:true},{type:'tool_result',tool_use_id:'c1',content:'file'}]}},{type:'result',subtype:'success',usage:{input_tokens:70},total_cost_usd:.01}]));
 assert.equal(r.links.length,2);assert.equal(r.links[0].results.length,1);assert.equal(r.failures.length,1);assert.equal(r.usage.input_tokens,70);assert.equal(r.metadata.cost,.01);assert.ok(r.diagnostics.some(d=>d.message.includes('Orphan')));
});
test('Claude repeated final assistant snapshots do not duplicate calls; stream deltas remain raw observations',()=>{
 const m={type:'assistant',message:{id:'m',content:[{type:'tool_use',id:'c',name:'Read',input:{file_path:'x'}}]}};
 const r=analyzeTrace(lines([m,{type:'stream_event',event:{type:'content_block_delta'}},m]));assert.equal(r.links.length,1);assert.deepEqual(r.links[0].call.lines,[1,3]);assert.equal(r.records.length,3);
});
test('rollout compaction and cumulative usage do not pretend to reconstruct a request',()=>{
 const r=analyzeTrace(lines([{type:'session_meta',payload:{id:'demo',cwd:'/demo'}},{type:'turn_context',payload:{model:'test'}},{type:'response_item',payload:{type:'function_call',call_id:'c',name:'shell',arguments:'{"command":"ls"}'}},{type:'response_item',payload:{type:'function_call_output',call_id:'c',output:'app.js'}},{type:'compacted',payload:{message:'summary'}},{type:'event_msg',payload:{type:'token_count',info:{total_token_usage:{input_tokens:100}}}},{type:'event_msg',payload:{type:'token_count',info:{total_token_usage:{input_tokens:200}}}},{type:'response_item',payload:{type:'message',role:'assistant',content:[{type:'output_text',text:'done'}]}}]));
 assert.equal(r.usage.input_tokens,200);assert.equal(r.compactions.length,1);assert.ok(priorEvidence(r,r.nodes.at(-1)).compaction);assert.equal(r.links[0].results.length,1);
});
test('bad lines, ambiguous IDs and unknown events remain visible, with input limits',()=>{
 const data=lines([{type:'turn.started'},{type:'item.started',item:{id:'x',type:'command_execution',command:'ls'}},{type:'mystery',payload:'retained'}])+'\n{broken}';
 const r=analyzeTrace(data);assert.ok(r.diagnostics.length>=2);assert.equal(r.records.length,4);assert.equal(r.nodes.at(-1).kind,'unknown');assert.throws(()=>analyzeTrace('x'.repeat(8*1024*1024+1)));assert.throws(()=>analyzeTrace(''));
});
test('duplicate calls are not associated and malformed type metadata cannot coerce executable values',()=>{
 const r=analyzeTrace(lines([{type:'response_item',payload:{type:'function_call',call_id:'same',name:'a',arguments:'{}'}},{type:'response_item',payload:{type:'function_call',call_id:'same',name:'b',arguments:'{}'}},{type:'response_item',payload:{type:'function_call_output',call_id:'same',output:'x'}},{type:{toString:1},payload:{x:1}}]));assert.ok(r.links.every(l=>l.ambiguous&&l.results.length===0));assert.ok(r.diagnostics.some(d=>d.message.includes('Duplicate')));
});
test('permission denials reported in the final Claude result remain explicit events',()=>{
 const r=analyzeTrace(lines([{type:'system',subtype:'init'},{type:'result',subtype:'success',permission_denials:[{tool_name:'Bash',tool_use_id:'c1',tool_input:{command:'blocked'}}]}]));assert.equal(r.approvals.length,1);assert.equal(r.approvals[0].status,'denied');
});
test('reviewed public captures preserve real failures, changes and reported usage',async()=>{
 const fs=await import('node:fs/promises');const {runtimeCases}=await import('../src/runtime/runtime-cases.js');
 for(const entry of runtimeCases){const source=await fs.readFile(new URL('../public'+entry.file,import.meta.url),'utf8');assert.ok(!source.includes('/Users/'));assert.ok(!/sk-[A-Za-z0-9_-]{12,}/.test(source));const r=analyzeTrace(source);assert.equal(r.format,entry.format);for(const checkpoint of entry.checkpoints)assert.ok(r.nodes.some(n=>n.lines.includes(checkpoint.line)));if(entry.agent==='Codex'){assert.equal(r.records.length,16);assert.equal(r.links.length,4);assert.equal(r.failures.length,1);assert.equal(r.changes.length,1);assert.equal(r.usage.input_tokens,56578);assert.equal(r.usage.cached_input_tokens,49152);assert.ok(r.links.every(l=>l.call.identityKind==='cli-item'));}else{assert.equal(r.links.length,0);assert.ok(r.nodes.some(n=>n.kind==='error'&&n.text?.includes('Not logged in')));}}
});
test('a manual format mismatch is explicit instead of silently treating everything as a matching run',()=>{
 const r=analyzeTrace(lines([{type:'assistant',message:{id:'m',content:[{type:'text',text:'x'}]}}]),'codex-exec');assert.ok(r.diagnostics.some(d=>d.message.includes('differs from detected')));
});
