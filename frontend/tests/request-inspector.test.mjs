import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectRequest, compareRequests, stripInstructions, parameterRows } from '../src/academy/inspect-request.js';
import { protocolExample } from '../src/academy/protocol-examples.js';
for (const protocol of ['chat','claude','responses','gemini']) {
  test(`${protocol}: preserve all request data and associate call/result`, () => {
    const raw = protocolExample(protocol), report = inspectRequest(JSON.stringify(raw), protocol);
    assert.deepEqual(report.raw, raw);
    assert.equal(report.links.length,1);
    assert.equal(report.links[0].matches.length,1);
    assert.equal(report.links[0].matches[0].id, report.links[0].id);
    assert.equal(report.tools[0].name,'search_notes');
    assert.equal(parameterRows(report.tools[0].schema)[0].required,true);
    assert.ok(report.groups.some(g=>g.kind==='system'&&g.bytes>0));
    const diff=compareRequests(inspectRequest(protocolExample(protocol,false),protocol),report);
    assert.ok(diff.some(r=>r.change==='added'));
    const stripped=stripInstructions(raw,protocol,true);
    assert.equal(inspectRequest(stripped,protocol).items.filter(i=>i.kind==='system'||i.kind==='tools').length,0);
    assert.deepEqual(raw,protocolExample(protocol));
  });
}
test('missing, duplicate and unmatched call IDs are reported, never silently linked',()=>{
  const raw=protocolExample('chat');raw.messages[3].tool_call_id='wrong';
  let report=inspectRequest(raw,'chat');assert.equal(report.links[0].matches.length,0);assert.ok(report.warnings.some(w=>w.includes('without a preceding')));
  raw.messages[2].tool_calls.push(raw.messages[2].tool_calls[0]);report=inspectRequest(raw,'chat');assert.ok(report.warnings.some(w=>w.includes('Duplicate')));
});
test('Gemini name fallback is explicit, not reported as a unique ID match',()=>{
  const raw=protocolExample('gemini');delete raw.contents[1].parts[0].functionCall.id;delete raw.contents[2].parts[0].functionResponse.id;
  const report=inspectRequest(raw,'gemini');assert.equal(report.links[0].matches.length,1);assert.ok(report.warnings.some(w=>w.includes('by name')));
});
test('server-side history, unknown controls and mixed content remain observable',()=>{
  const raw=protocolExample('responses');raw.previous_response_id='previous';raw.custom_field={enabled:true};
  const report=inspectRequest(raw,'responses');assert.ok(report.items.some(i=>i.path==='custom_field'));assert.ok(report.warnings.some(w=>w.includes('complete context')));
});
test('reject oversized, unsupported and malformed inputs with bounded schema traversal',()=>{
  for(const value of ['null','[]','42','{"contents":{}}','{"messages":[null]}','{"messages":[],"tools":{}}'])assert.throws(()=>inspectRequest(value));
  assert.throws(()=>inspectRequest(' '.repeat(1024*1024+1)));
  assert.throws(()=>inspectRequest({messages:Array.from({length:201},()=>({role:'user',content:'x'}))}));
  assert.equal(parameterRows({properties:{data:{type:'array',items:{properties:{value:{type:'string'}},required:['value']}}}})[1].path,'data[].value');
});
test('Claude and Gemini tool-result-only messages contribute to result composition',()=>{
 for(const p of ['claude','gemini']) {const r=inspectRequest(protocolExample(p),p);assert.ok(r.groups.find(g=>g.kind==='result').bytes>0);}
 const raw=protocolExample('chat');delete raw.tools;assert.ok(inspectRequest(raw,'chat').warnings.some(w=>w.includes('no matching definition')));
});
