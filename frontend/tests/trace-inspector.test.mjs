import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseTrace} from '../src/learn/trace-model.js';
Object.defineProperty(globalThis,'navigator',{value:{language:'zh-CN'},configurable:true});
globalThis.location={search:'?lang=zh'};globalThis.localStorage={getItem:()=>null};
const {contextRows,inspectCalls,inspectContext,inspectCode,readableToolOutput}=await import('../src/learn/trace-inspector.js');
const rows=parseTrace(await readFile(new URL('../public/learn/examples/search-child.jsonl',import.meta.url),'utf8')).rows;
const artifacts=JSON.parse(await readFile(new URL('../public/learn/examples/search-child-artifacts.json',import.meta.url),'utf8'));
test('scope inspector separates actual child messages and user-wrapped tool results',()=>{
 const child=contextRows(rows.slice(0,16),'child');assert.deepEqual(child.map(r=>r.line),[11,12,13,14,15]);
 assert.equal(child.filter(r=>r.kind==='tool_result').length,2);
 assert.ok(contextRows(rows,'main').every(r=>!r.data.parent_tool_use_id));
 assert.equal(contextRows(rows.slice(0,10),'child').length,0);
 assert.equal(child[0].byteLength,new TextEncoder().encode(JSON.stringify(child[0].content,null,2)).length);
 const html=inspectContext(rows.slice(0,16),{scope:'child'});assert.match(html,/不是某一轮实际发送的请求/);assert.match(html,/没有保留完整system提示词/);
});
test('inspector does not expose a subagent report until its result arrives',()=>{
 const before=inspectCalls(rows.slice(0,15),{line:10});assert.match(before,/此时还没有结果/);assert.ok(!before.includes('Subagent hand-back'));
 const after=inspectCalls(rows.slice(0,16),{line:10});assert.match(after,/Subagent hand-back/);assert.match(after,/Read-only bug inspection/);
 assert.equal(readableToolOutput('[{"type":"text","text":"one\\ntwo"}]'),'one\ntwo');
});
test('code and independent test evidence respect replay position and escape content',()=>{
 const marked={...artifacts,after_tests:'AFTER_ONLY',followup_tests:'RESUME_ONLY'};
 const before=inspectCode(rows.slice(0,16),marked);assert.ok(!before.includes('normalize(\'NFKC\')'));assert.ok(!before.includes('AFTER_ONLY'));
 const verified=inspectCode(rows.slice(0,21),marked);assert.ok(verified.includes('AFTER_ONLY'));assert.ok(!verified.includes('RESUME_ONLY'));
 const edited=inspectCode(rows.slice(0,19),artifacts);assert.match(edited,/new_string/);assert.match(edited,/normalize/);assert.ok(!edited.includes(artifacts.after_tests));
 const hostile=structuredClone(rows);hostile[9].data.message.content[0].input.prompt='<img src=x onerror=bad>';
 const html=inspectCalls(hostile.slice(0,16),{line:10});assert.ok(!html.includes('<img'));assert.match(html,/&lt;img/);
});
