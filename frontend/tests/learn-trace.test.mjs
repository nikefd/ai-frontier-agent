import test from 'node:test';
import assert from 'node:assert/strict';
import {parseTrace,projectTrace,traceTree} from '../src/learn/trace-model.js';
const call=(id,name='Bash')=>({type:'tool_use',id,name,input:{command:'node --test'}});
const assistant=(content,extra={})=>({type:'assistant',message:{content},...extra});
const result=(id,extra={})=>({type:'user',message:{content:[{type:'tool_result',tool_use_id:id,content:'output',...extra}]}});
const parse=events=>parseTrace(events.map(JSON.stringify).join('\n'));
test('replay changes a call from pending to failed only once its result exists',()=>{
 const parsed=parse([assistant([call('a')]),result('a',{is_error:true})]);
 assert.equal(projectTrace(parsed.rows.slice(0,1)).calls[0].status,'pending');
 const full=projectTrace(parsed.rows);assert.equal(full.calls.length,1);assert.equal(full.calls[0].status,'failed');assert.deepEqual(full.calls[0].lines,[1,2]);
});
test('children are nested under actual spawning calls and scoped results do not collide',()=>{
 const parsed=parse([assistant([call('parent','Agent')]),assistant([call('a')],{parent_tool_use_id:'parent'}),{...result('a'),parent_tool_use_id:'parent'},assistant([call('a')]),result('a')]);
 const report=projectTrace(parsed.rows),tree=traceTree(report.nodes);assert.equal(report.calls.length,3);assert.equal(tree[0].children[0].title,'Bash');assert.equal(tree[0].children[0].status,'completed');assert.equal(tree[1].status,'completed');
});
test('duplicate and missing IDs do not manufacture an association',()=>{
 const report=projectTrace(parse([assistant([call('a'),call('a'),call(undefined)]),result('a'),result(undefined)]).rows);
 assert.equal(report.calls.filter(node=>node.status==='completed').length,0);assert.equal(report.diagnostics.length,2);
});
test('resume segments may reuse IDs; final is_error wins over success subtype',()=>{
 const report=projectTrace(parse([{type:'system',subtype:'init',session_id:'s',model:'test'},assistant([call('a')]),result('a'),{type:'result',subtype:'success',result:'first'},assistant([call('a')]),result('a',{is_error:true}),{type:'result',subtype:'success',is_error:true,result:'Not logged in'}]).rows);
 assert.equal(report.session,'s');assert.equal(report.calls[0].status,'completed');assert.equal(report.calls[1].status,'failed');assert.equal(report.nodes.at(-1).status,'failed');assert.equal(report.results.length,2);
});
test('assistant snapshots update rather than duplicate tool calls',()=>{
 const records=[assistant([call('a')]),assistant([call('a')])];records.forEach(row=>row.message.id='m');const report=projectTrace(parse(records).rows);assert.equal(report.calls.length,1);assert.deepEqual(report.calls[0].lines,[1,2]);
});
test('malformed lines retain source references, unknown input and oversized traces reject',()=>{
 const parsed=parseTrace('\n{"type":"system","subtype":"init"}\nnot json\n');assert.equal(parsed.rows[0].line,2);assert.equal(projectTrace(parsed.rows).diagnostics[0].line,3);assert.throws(()=>parseTrace('{}'),/Claude/);assert.throws(()=>parseTrace('x'.repeat(5*1024*1024+1)),/5 MiB/);
});
test('cyclic parent data produces finite roots rather than recursive rendering',()=>{
 const tree=traceTree([{key:'a',parentKey:'b'},{key:'b',parentKey:'a'},{key:'c',parentKey:'a'}]);assert.equal(tree.length,2);assert.equal(tree[0].children.length,1);
});

test('malformed metadata cannot invoke object string coercion',()=>{
 const report=projectTrace(parse([{type:'assistant',message:{id:{toString:1},content:[call('a')]}},{type:'result',subtype:{toString:1},is_error:true,result:'error'}]).rows);
 assert.equal(report.calls.length,1);assert.equal(report.nodes.at(-1).status,'failed');
});

test('public startup example is an actual error with no tool execution and no private identifiers',async()=>{
 const {readFile}=await import('node:fs/promises');
 const source=await readFile(new URL('../public/learn/examples/claude-startup.jsonl',import.meta.url),'utf8');
 const report=projectTrace(parseTrace(source).rows);
 assert.equal(report.calls.length,0);assert.equal(report.nodes.at(-1).status,'failed');assert.equal(report.results[0].is_error,true);assert.equal(report.results[0].subtype,'success');
 assert.ok(!source.includes('session_id'));assert.ok(!source.includes('cwd'));assert.ok(!source.includes('apiKeySource'));
});
