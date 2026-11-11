import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectRequest, byteSize, parameterRows } from '../src/academy/inspect-request.js';
import { inspectStream } from '../src/academy/inspect-stream.js';
import { associateStream } from '../src/academy/stream-association.js';
globalThis.location={search:'?lang=en'};globalThis.navigator ??= {language:'en'};
const { requestOverview, streamPanel }=await import('../src/academy/inspect-panels.js');
test('render imported HTML as escaped text and preserve Responses string byte size',()=>{
 const attack='<img src=x onerror=alert(1)>';
 const r=inspectRequest({input:attack},'responses');assert.equal(r.items[0].value,attack);assert.equal(r.items[0].bytes,byteSize(attack));
 assert.ok(!requestOverview(r,0).includes('<img'));assert.ok(requestOverview(r,0).includes('&lt;img'));
 const stream=inspectStream('data: '+JSON.stringify({choices:[{delta:{content:attack},finish_reason:'stop'}]})+'\n\n','chat');assert.ok(!streamPanel(stream).includes('<img'));
});
test('malformed metadata remains inspectable without coercing objects into markup',()=>{
 const r=inspectRequest({messages:[{role:{toString:1},content:'x'}],tools:[{function:{name:{toString:1},description:{x:1},parameters:{properties:{x:{type:{x:1}}}}}}]},'chat');assert.doesNotThrow(()=>requestOverview(r,1));assert.equal(parameterRows(r.tools[0].schema)[0].type,'unknown');
});
test('stream associations use supplied definitions and ID results only',()=>{
 const request={messages:[{role:'assistant',tool_calls:[{id:'c1',function:{name:'lookup',arguments:'{}'}}]},{role:'tool',tool_call_id:'c1',content:'ok'}],tools:[{type:'function',function:{name:'lookup',parameters:{}}}]};
 const rows=associateStream({protocol:'chat',calls:[{id:'c1',name:'lookup'},{id:'other',name:'lookup'}]},JSON.stringify(request));assert.deepEqual(rows[0].definitions,['tools[0]']);assert.deepEqual(rows[0].results,['messages[1]']);assert.deepEqual(rows[1].results,[]);
});
