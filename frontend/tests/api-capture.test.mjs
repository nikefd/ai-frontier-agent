import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
Object.defineProperty(globalThis,'navigator',{value:{language:'zh-CN'},configurable:true});
globalThis.location={search:'?lang=zh'};globalThis.localStorage={getItem:()=>null};
const {inspectorPayload,apiCaptureView}=await import('../src/learn/api-capture.js');
const load=async kind=>JSON.parse(await readFile(new URL(`../public/learn/examples/http-${kind}.json`,import.meta.url),'utf8'));
test('HTTP repair contains actual System schemas main/child requests and Inspector-compatible exports',async()=>{
 const capture=await load('repair');assert.equal(capture.exchanges.length,7);
 assert.deepEqual(capture.exchanges.filter(e=>e.scope==='child').map(e=>e.sequence),[3,4]);
 const first=capture.exchanges[0];assert.ok(first.request.system[2].text.length>1000);
 assert.ok(first.request.tools.find(t=>t.name==='Read').input_schema.properties.file_path);
 const exported=JSON.parse(inspectorPayload(first));assert.deepEqual(exported,first.request);assert.equal(exported.exchanges,undefined);
 const sse=inspectorPayload(first,'response');assert.match(sse,/event: content_block_start/);assert.match(sse,/partial_json/);assert.ok(!sse.includes('capture_merged_deltas'));
 const events=sse.split('\n').filter(line=>line.startsWith('data: ')).map(line=>JSON.parse(line.slice(6)));
 assert.equal(events.filter(e=>e.content_block?.type==='tool_use').length,4);assert.equal(events.at(-1).type,'message_stop');
});
test('native Skill declaration call and subsequent injected body are all observed',async()=>{
 const capture=await load('skill');assert.equal(capture.files_unchanged,true);
 assert.ok(capture.exchanges[0].request.tools.some(t=>t.name==='Skill'));
 const events=capture.exchanges[0].response_events;
 assert.ok(events.some(e=>e.content_block?.name==='Skill'));
 assert.ok(inspectorPayload(capture.exchanges[0],'response').includes('search-check:verify-search'));
 assert.match(JSON.stringify(capture.exchanges[1].request.messages),/A failed test is an observed finding/);
 assert.match(capture.skill_source,/name: verify-search/);
});
test('public HTTP bodies exclude account metadata private paths and thinking content; HTML escapes System',async()=>{
 for(const kind of ['repair','skill']){
  const capture=await load(kind);assert.ok(!JSON.stringify(capture).includes('/Users/'));
  for(const e of capture.exchanges){assert.equal(e.request.metadata,undefined);assert.ok(e.response_events.every(v=>!['thinking_delta','signature_delta'].includes(v.delta?.type)));assert.ok(!inspectorPayload(e,'response').includes('/Users/'));}
 }
 const capture=await load('repair');capture.exchanges[0].request.system[2].text='<script>bad()</script>';
 const html=apiCaptureView(capture);assert.ok(!html.includes('<script>'));assert.match(html,/&lt;script&gt;/);assert.match(html,/https:\/\/inspector.zhangyangbin.com\//);assert.ok(!html.includes('data-wire-tab'));assert.ok(!html.includes('?data='));
});
