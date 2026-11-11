import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectStream, streamEvents } from '../src/academy/inspect-stream.js';
import { streamExample } from '../src/academy/protocol-examples.js';
const frame=d=>'data: '+JSON.stringify(d)+'\n\n';
for(const protocol of ['chat','claude','responses','gemini'])test(`${protocol}: reconstruct teaching stream with supplied usage`,()=>{
 const result=inspectStream(streamExample(protocol),protocol);assert.equal(result.complete,true);assert.ok(Object.keys(result.usage).length);assert.equal(result.errors.length,0);
 if(protocol==='claude')assert.deepEqual(result.calls[0].parsedArguments,{query:'tools'});
 else assert.equal(result.outputs[0].text,'A tool executes an operation.');
});
test('parallel Chat tool fragments stay separated by choice and call index',()=>{
 const source=frame({choices:[{index:0,delta:{tool_calls:[{index:0,id:'a',function:{name:'one',arguments:'{"a":'}},{index:1,id:'b',function:{name:'two',arguments:'{"b":'}}]}}]})+frame({choices:[{index:0,delta:{tool_calls:[{index:1,function:{arguments:'2}'}},{index:0,function:{arguments:'1}'}}]},finish_reason:'tool_calls'}]});
 const r=inspectStream(source,'chat');assert.deepEqual(r.calls.map(c=>c.parsedArguments),[{a:1},{b:2}]);
});
test('incomplete, malformed, unknown and error events remain visible',()=>{
 const r=inspectStream(frame({choices:[{index:0,delta:{content:'partial'}}]})+'data: {bad}\n\n'+frame({type:'unrecognized',value:1}),'chat');
 assert.equal(r.complete,false);assert.equal(r.events.length,3);assert.ok(r.warnings.length>=2);assert.equal(r.events[2].data.value,1);
 const failed=inspectStream(frame({type:'error',error:{message:'denied'}}),'claude');assert.equal(failed.errors.length,1);assert.equal(failed.complete,false);
});
test('SSE multiline data and CRLF, and Gemini JSON chunk arrays are accepted',()=>{
 const e=streamEvents('event: x\r\ndata: {"x":\r\ndata: 1}\r\n\r\n');assert.deepEqual(e[0].data,{x:1});
 const r=inspectStream(JSON.stringify([{candidates:[{content:{parts:[{text:'x'}]},finishReason:'STOP'}]}]),'gemini');assert.equal(r.outputs[0].text,'x');
 assert.throws(()=>inspectStream('x'.repeat(2*1024*1024+1),'chat'));
});
test('Responses item IDs map arguments to the original output index',()=>{
 const r=inspectStream(frame({type:'response.output_item.added',output_index:2,item:{id:'item_a',type:'function_call',call_id:'call_a',name:'lookup',arguments:''}})+frame({type:'response.function_call_arguments.delta',item_id:'item_a',delta:'{"q":1}'})+frame({type:'response.completed',response:{status:'completed'}}),'responses');
 assert.equal(r.calls.length,1);assert.deepEqual(r.calls[0].parsedArguments,{q:1});
 const bad=inspectStream(frame({choices:[{delta:{tool_calls:[{index:0,function:{name:'x',arguments:'{'}}]},finish_reason:'tool_calls'}]}),'chat');assert.equal(bad.complete,false);
});
test('SSE comments do not discard data in the same frame',()=>{
 assert.equal(streamEvents(': keepalive\ndata: {"ok":true}\n\n')[0].data.ok,true);
});
