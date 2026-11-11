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
const {models}=await import('../src/academy/catalog.js');
const {modelDetail,modelComparison,priceText,exampleForModel}=await import('../src/academy/model-views.js');
const {lessonWalkthrough}=await import('../src/academy/lesson-walkthrough.js');
const {lessons,lessonTrace}=await import('../src/academy/lessons.js');
const {agentGuides,agentGuidePanel,agentComponentPanel}=await import('../src/academy/agent-guides.js');
const {agents}=await import('../src/academy/agents.js');
globalThis.document={documentElement:{lang:'en'}};
test('model details contain real specifications, readable prices and task-specific learning flows',()=>{
 for(const model of models){const html=modelDetail(model);assert.ok(html.includes('How this kind'));assert.ok(!html.includes('[object Object]'));if(model.protocol)assert.equal(inspectRequest(exampleForModel(model),model.protocol).protocol,model.protocol);}
 const text=modelComparison(new Set(models.filter(m=>m.pricing).slice(0,3).map(m=>m.id)));assert.ok(text.includes('$10'));assert.ok(!text.includes('[object Object]'));
 const gemini=models.find(m=>m.id==='google-gemini-4-carbon');assert.ok(priceText(gemini.pricing,Date.UTC(2026,11,2)).includes('Expired'));assert.ok(!priceText(gemini.pricing,Date.UTC(2026,10,11)).includes('Expired'));
});
test('every case explains each turn with actual IDs, results, and differences',()=>{
 for(const lesson of lessons){const trace=lessonTrace(lesson.id);for(let step=0;step<trace.length;step++){const html=lessonWalkthrough(lesson,trace,step);assert.ok(html.includes('Why does this turn exist'));assert.ok(html.includes('Full original request'));assert.ok(!html.includes('undefined'));}}
 const lesson=lessons.find(l=>l.id==='recovery');const html=lessonWalkthrough(lesson,lessonTrace(lesson.id),2);assert.ok(html.includes('failed_1'));assert.ok(html.includes('retry_2'));assert.ok(html.includes('ERROR'));
});
test('all agents have specific files, mechanism references, and inspectable component boundaries',()=>{
 for(const agent of agents){assert.ok(agentGuides[agent.id].source.startsWith('https://'));assert.ok(agentGuidePanel(agent).includes('Key files'));for(let i=0;i<agent.components.length;i++)assert.ok(agentComponentPanel(agent,i).includes('To inspect'));}
 assert.ok(agentGuidePanel(agents.find(a=>a.id==='handoff')).includes('input_filter'));
});
